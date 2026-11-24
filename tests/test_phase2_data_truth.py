"""
tests/test_phase2_data_truth.py
Phase 2 Data-Truth Invariant & Verification Test Suite.

Verifies:
1. Total-return dividend + split + bonus backward adjustment math, continuity across ex-dividend dates, and idempotency.
2. Evening filing (19:15 IST on Day t) blocked at Day t 15:30 IST close decision, yet eligible at Day t+1 09:00 IST pre-open decision.
3. Survivorship universe inclusion of a delisted/renamed symbol before its delisting_date and exclusion afterward.
"""

import pytest
import sqlite3
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.data.corporate_actions import (
    CorporateActionsManager,
    extract_cash_dividend_amount
)
from src.storage.temporal_guard import (
    is_pit_eligible_at,
    get_eod_close_decision_timestamp,
    get_pre_market_decision_timestamp,
    parse_ist_timestamp
)
from src.fundamentals.ttm_builder import PointInTimeTTMBuilder
from src.client.symbol_resolver import (
    resolve_pit_symbol,
    get_pit_active_universe,
    HISTORICAL_ALIAS_MERGER_DATES
)


@pytest.fixture
def phase2_test_db(tmp_path):
    """Creates an isolated temporary database with schema migrations."""
    db_path = str(tmp_path / "test_phase2.db")
    db = DatabaseManager(db_path=db_path)
    with db.get_connection() as conn:
        run_all_migrations(conn)
    return db


# ==============================================================================
# DELIVERABLE 1: TOTAL RETURN DIVIDEND & CORPORATE ACTION ADJUSTMENTS
# ==============================================================================

def test_extract_cash_dividend_amounts():
    """Verifies cash dividend parsing across all standard NSE disclosure text variants."""
    assert extract_cash_dividend_amount("Interim Dividend - Rs 23 Per Share") == 23.0
    assert extract_cash_dividend_amount("Dividend - Rs 25 Per Share") == 25.0
    assert extract_cash_dividend_amount("Dividend Rs -7.65 Per Share") == 7.65
    assert extract_cash_dividend_amount("Interim Dividend Rs - 2.50 Per Share") == 2.50
    # Multi-component dividends
    assert extract_cash_dividend_amount("Interim Dividend - Rs 10 Per Share Special Dividend - Rs 66 Per Share") == 76.0
    # Percentage dividend with face value
    assert extract_cash_dividend_amount("Agm/Dividend - 100%", face_val=10.0) == 10.0
    assert extract_cash_dividend_amount("Dividend - 250%", face_val=2.0) == 5.0
    # Empty or zero
    assert extract_cash_dividend_amount("") == 0.0
    assert extract_cash_dividend_amount("Board Meeting Intimation") == 0.0


def test_total_return_adjustment_math_and_continuity(phase2_test_db):
    """
    Verifies total-return backward adjustment math:
        AdjClose_t = P_t * product_{s > t} (1 - D_s / P_{s-1}) * product_{s > t} (Ratio_{to, s} / Ratio_{from, s})
    Ensures:
    1. Continuity across ex-dividend and ex-split dates.
    2. Unadjusted close prices remain intact in ohlcv_daily.
    3. Volume scales strictly with share splits/bonuses, NOT with cash dividends.
    """
    sym = "TESTDIV"
    mgr = CorporateActionsManager(db=phase2_test_db)

    # 1. Populate raw OHLCV for 5 consecutive sessions
    # Day 1: 100.0, Day 2: 105.0 (Cum-div), Day 3: 100.0 (Ex-div, D=5.25), Day 4: 102.0, Day 5: 52.0 (Ex-split 2:1)
    dates = ["2026-05-01", "2026-05-02", "2026-05-03", "2026-05-04", "2026-05-05"]
    closes = [100.0, 105.0, 100.0, 102.0, 52.0]
    volumes = [10000, 12000, 15000, 11000, 25000]

    with phase2_test_db.get_connection() as conn:
        for d, c, v in zip(dates, closes, volumes):
            conn.execute("""
                INSERT INTO ohlcv_daily (
                    symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp
                ) VALUES (?, ?, 'EQ', ?, ?, ?, ?, ?, 'TEST', '2026-05-05T18:00:00Z')
            """, (sym, d, c, c + 2.0, c - 2.0, c, v))
        conn.commit()

    # 2. Record Corporate Actions:
    # Action A: Cash dividend on 2026-05-03: D_s = ₹5.25 per share.
    # P_{s-1} is Day 2 close = 105.0.
    # Div factor F_div = 1 - (5.25 / 105.0) = 1 - 0.05 = 0.95.
    act_div = mgr.record_dividend_action(
        symbol=sym,
        ex_date="2026-05-03",
        dividend_amount=5.25,
        cum_close_price=105.0,
        purpose="Interim Dividend - Rs 5.25 Per Share"
    )
    assert act_div is not None

    # Action B: 2:1 stock split on 2026-05-05: ratio_from=2.0, ratio_to=1.0 -> factor 0.50
    act_split = mgr.record_action(
        symbol=sym,
        ex_date="2026-05-05",
        action_type="SPLIT",
        ratio_from=2.0,
        ratio_to=1.0,
        source="TEST"
    )
    assert act_split is not None

    # 3. Retrieve adjustment multiplier series
    mult_series = mgr.get_adjustment_factors_series(sym, dates=dates, include_dividends=True)

    # Days 1 & 2 precede both dividend (2026-05-03) and split (2026-05-05):
    # M(t) = 0.95 * 0.50 = 0.475
    assert mult_series["2026-05-01"] == pytest.approx(0.475, abs=1e-5)
    assert mult_series["2026-05-02"] == pytest.approx(0.475, abs=1e-5)

    # Days 3 & 4 occur after dividend but precede split:
    # M(t) = 0.50
    assert mult_series["2026-05-03"] == pytest.approx(0.50, abs=1e-5)
    assert mult_series["2026-05-04"] == pytest.approx(0.50, abs=1e-5)

    # Day 5 occurs on/after split:
    # M(t) = 1.00
    assert mult_series["2026-05-05"] == pytest.approx(1.00, abs=1e-5)

    # 4. Apply adjustments to raw DataFrame
    raw_df = pd.DataFrame({
        "symbol": sym,
        "trading_date": dates,
        "open": closes,
        "high": [c + 2.0 for c in closes],
        "low": [c - 2.0 for c in closes],
        "close": closes,
        "volume": volumes
    })

    adj_df = mgr.apply_adjustments_to_ohlcv(raw_df, include_dividends=True)

    # Verify unadjusted close is strictly preserved
    assert list(adj_df["close"]) == closes

    # Verify adj_close:
    # Day 1: 100 * 0.475 = 47.50
    # Day 2: 105 * 0.475 = 49.88
    # Day 3: 100 * 0.50 = 50.00
    # Day 4: 102 * 0.50 = 51.00
    # Day 5: 52 * 1.00 = 52.00
    expected_adj_closes = [47.50, 49.88, 50.00, 51.00, 52.00]
    assert list(adj_df["adj_close"]) == expected_adj_closes

    # Verify Volume: Scales with split (2x on Days 1-4), but NOT with cash dividend
    # Split multiplier is 0.50 on Days 1-4, so volume is divided by 0.50 -> 2x volume
    assert adj_df.loc[0, "adj_volume"] == 20000  # 10000 / 0.5
    assert adj_df.loc[1, "adj_volume"] == 24000  # 12000 / 0.5
    assert adj_df.loc[2, "adj_volume"] == 30000  # 15000 / 0.5
    assert adj_df.loc[3, "adj_volume"] == 22000  # 11000 / 0.5
    assert adj_df.loc[4, "adj_volume"] == 25000  # 25000 / 1.0


def test_corporate_action_idempotency_and_guard_rail(phase2_test_db):
    """Verifies that re-running sync produces identical records and flags corrupt dividends."""
    mgr = CorporateActionsManager(db=phase2_test_db)
    sym = "IDEMPOTENT_CO"

    # Seed raw close price
    with phase2_test_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp
            ) VALUES (?, '2026-06-01', 'EQ', 100.0, 105.0, 98.0, 100.0, 5000, 'TEST', '2026-06-01T18:00:00Z')
        """, (sym,))

        # Insert 1 legitimate dividend and 1 corrupt dividend (> 50% price without special dividend flag)
        conn.execute("""
            INSERT INTO corporate_actions (
                symbol, action_type, ex_date, purpose, adjustment_factor, source, retrieval_timestamp
            ) VALUES
            (?, 'DIVIDEND', '2026-06-02', 'Interim Dividend - Rs 4 Per Share', 1.0, 'TEST', '2026-06-01T18:00:00Z'),
            (?, 'DIVIDEND', '2026-06-15', 'Ordinary Dividend - Rs 65 Per Share', 1.0, 'TEST', '2026-06-01T18:00:00Z')
        """, (sym, sym))
        conn.commit()

    # Sync first time
    s1 = mgr.sync_from_corporate_actions_table()
    # Legitimate dividend should sync; 65/100 (65%) without special dividend should be flagged and skipped
    actions1 = mgr.get_actions_for_symbol(sym)
    assert len(actions1) == 1
    assert actions1[0]["action_type"] == "DIVIDEND"
    assert actions1[0]["ratio_from"] == 100.0
    assert actions1[0]["ratio_to"] == 96.0

    # Sync second time (must be strictly idempotent, zero new records)
    s2 = mgr.sync_from_corporate_actions_table()
    actions2 = mgr.get_actions_for_symbol(sym)
    assert len(actions2) == 1
    assert actions1[0]["action_id"] == actions2[0]["action_id"]


# ==============================================================================
# DELIVERABLE 2: TIMESTAMP-EXACT POINT-IN-TIME (PIT) GATING
# ==============================================================================

def test_evening_filing_timestamp_pit_gating():
    """
    Verifies that an evening filing published at 19:15 IST on Session t:
    - Is BLOCKED at Session t EOD Close Decision (15:30 IST).
    - Is ELIGIBLE at Session t+1 Pre-Market Open Decision (09:00 IST).
    """
    evening_filing_ts = "2026-10-23T19:15:00+05:30"

    # Canonical decision timestamps
    eod_close_t = get_eod_close_decision_timestamp("2026-10-23")         # 2026-10-23T15:30:00+05:30
    pre_market_t_plus_1 = get_pre_market_decision_timestamp("2026-10-24") # 2026-10-24T09:00:00+05:30

    # 1. Direct boolean check
    # Blocked on Day t close (19:15 is NOT < 15:30)
    assert is_pit_eligible_at(evening_filing_ts, eod_close_t) is False

    # Eligible on Day t+1 open (2026-10-23T19:15 IS < 2026-10-24T09:00)
    assert is_pit_eligible_at(evening_filing_ts, pre_market_t_plus_1) is True

    # 2. Test integration in filter_eligible_statements
    statements = [
        {
            "symbol": "INFY",
            "period_end_date": "2026-09-30",
            "published_at_ist": evening_filing_ts,
            "net_profit": 6500.0
        }
    ]

    # At Day t close: Statement must be excluded (causality guard)
    eligible_close = PointInTimeTTMBuilder.filter_eligible_statements(
        statements,
        as_of_date="2026-10-23",
        decision_timestamp_ist=eod_close_t
    )
    assert len(eligible_close) == 0

    # At Day t+1 pre-market: Statement must be included and tagged
    eligible_open = PointInTimeTTMBuilder.filter_eligible_statements(
        statements,
        as_of_date="2026-10-24",
        decision_timestamp_ist=pre_market_t_plus_1
    )
    assert len(eligible_open) == 1
    assert eligible_open[0]["pit_provenance"] == "OBSERVED_TIMESTAMP"
    assert eligible_open[0]["pit_eligible"] is True


def test_statutory_fallback_lag_when_timestamp_missing():
    """
    Verifies that when publication timestamps are absent, statements fall back to
    conservative SEBI LODR lags (+45d quarterly, +60d annual) and are tagged explicitly.
    """
    statements = [
        {
            "symbol": "TCS",
            "period_end_date": "2026-03-31",
            # No published_at_ist or filing_date provided
            "net_profit": 11000.0
        }
    ]

    # 40 days after quarter close (2026-05-10): Under 45-day lag, statement is NOT eligible
    filtered_40d = PointInTimeTTMBuilder.filter_eligible_statements(
        statements,
        as_of_date="2026-05-10",
        is_annual=False
    )
    assert len(filtered_40d) == 0

    # 50 days after quarter close (2026-05-20): Past 45-day lag, statement becomes eligible
    filtered_50d = PointInTimeTTMBuilder.filter_eligible_statements(
        statements,
        as_of_date="2026-05-20",
        is_annual=False
    )
    assert len(filtered_50d) == 1
    assert filtered_50d[0]["pit_provenance"] == "STATUTORY_FALLBACK_LAG_45D"
    assert filtered_50d[0]["pit_eligible"] is True


# ==============================================================================
# DELIVERABLE 3: SURVIVORSHIP-AWARE HISTORICAL UNIVERSE QUERY
# ==============================================================================

def test_survivorship_universe_inclusion_and_delisting(phase2_test_db):
    """
    Verifies point-in-time active universe:
    - Lists equities listed on or before as_of_date.
    - Excludes equities delisted on or before as_of_date.
    - Resolves historical aliases (e.g. HDFC before 2023-07-13 vs HDFCBANK).
    """
    with phase2_test_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO securities_master (
                symbol, company_name, isin, industry, sector, macro_sector, listing_date, delisting_date, is_active, updated_at
            ) VALUES
            ('ACTIVE_EQ', 'Active Co', 'INE000000001', 'IT', 'Tech', 'Tech', '2015-01-01', NULL, 1, '2026-01-01'),
            ('DELISTED_EQ', 'Delisted Co', 'INE000000002', 'Finance', 'Finance', 'Financials', '2018-01-01', '2023-06-30', 0, '2026-01-01'),
            ('NEW_EQ', 'New Co', 'INE000000003', 'Auto', 'Auto', 'Consumer', '2025-01-01', NULL, 1, '2026-01-01')
        """)
        conn.commit()

    # Query as of 2022-01-01:
    # ACTIVE_EQ: Listed 2015, not delisted -> Included
    # DELISTED_EQ: Listed 2018, delisting 2023-06-30 -> Included (ACTIVE in 2022!)
    # NEW_EQ: Listed 2025 -> Excluded (Not yet born)
    u_2022 = phase2_test_db.get_pit_active_symbols("2022-01-01")
    assert "ACTIVE_EQ" in u_2022
    assert "DELISTED_EQ" in u_2022
    assert "NEW_EQ" not in u_2022

    # Query as of 2024-01-01:
    # ACTIVE_EQ: Included
    # DELISTED_EQ: Delisted 2023-06-30 -> Excluded (Survivorship protection!)
    # NEW_EQ: Listed 2025 -> Excluded
    u_2024 = phase2_test_db.get_pit_active_symbols("2024-01-01")
    assert "ACTIVE_EQ" in u_2024
    assert "DELISTED_EQ" not in u_2024
    assert "NEW_EQ" not in u_2024

    # Query as of 2026-01-01:
    # ACTIVE_EQ: Included
    # DELISTED_EQ: Excluded
    # NEW_EQ: Listed 2025 -> Included
    u_2026 = phase2_test_db.get_pit_active_symbols("2026-01-01")
    assert "ACTIVE_EQ" in u_2026
    assert "DELISTED_EQ" not in u_2026
    assert "NEW_EQ" in u_2026


def test_historical_ticker_alias_resolution():
    """Verifies historical ticker symbol resolution across known corporate merger dates."""
    # HDFC merged into HDFCBANK on 2023-07-13
    assert resolve_pit_symbol("HDFC", "2021-01-01") == "HDFC"
    assert resolve_pit_symbol("HDFC", "2023-07-12") == "HDFC"
    assert resolve_pit_symbol("HDFC", "2023-07-13") == "HDFCBANK"
    assert resolve_pit_symbol("HDFC", "2026-01-01") == "HDFCBANK"

    # LTI merged into LTIM on 2022-12-05
    assert resolve_pit_symbol("LTI", "2022-01-01") == "LTI"
    assert resolve_pit_symbol("LTI", "2023-01-01") == "LTIM"

    # CADILAHC rebranded to ZYDUSLIFE on 2022-03-07
    assert resolve_pit_symbol("CADILAHC", "2021-01-01") == "CADILAHC"
    assert resolve_pit_symbol("CADILAHC", "2022-03-08") == "ZYDUSLIFE"
