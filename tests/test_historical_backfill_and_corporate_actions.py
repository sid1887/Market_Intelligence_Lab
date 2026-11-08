"""
tests/test_historical_backfill_and_corporate_actions.py
Hermetic Acceptance and Regression Tests for Phase 10.1:
1. Split adjustment math: 10:1 split scales pre-split prices by 0.10 and post-split by 1.00.
2. Raw settlement immutability: ohlcv_daily rows in database remain strictly unmutated.
3. Checkpoint matrix resumption: FAILED chunks resume without duplicate errors or corruption.
4. Factor engine burn-in: Long-term metrics (sma_200, momentum_1y, vol_ann) strictly return NULL for sessions < 252.
"""

import os
import sqlite3
import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timezone

from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.data.corporate_actions import CorporateActionsManager
from src.data.historical_backfill import HistoricalBackfillCoordinator
from src.factors.engine import FactorEngine


@pytest.fixture
def hermetic_db(tmp_path):
    """Hermetic SQLite database fixture with Migration 0001-0011 applied."""
    db_path = str(tmp_path / "test_phase10_1.db")
    db = DatabaseManager(db_path)
    db.init_schema()
    with db.get_connection() as conn:
        run_all_migrations(conn)
    return db


def test_01_split_adjustment_math(hermetic_db):
    """
    Test 1: Verifies retroactive compounding split multiplier M(t).
    A 10:1 split on 2022-06-15 (split_multiplier=0.10):
    - Pre-split dates (< 2022-06-15) scaled by 0.10
    - Post-split dates (>= 2022-06-15) scaled by 1.00
    - Volume scaled inversely (1.0 / M)
    """
    ca_manager = CorporateActionsManager(hermetic_db)
    sym = "TATACONSUM"

    # Record 10:1 split on 2022-06-15
    action_id = ca_manager.record_action(
        symbol=sym,
        ex_date="2022-06-15",
        action_type="SPLIT",
        ratio_from=10.0,
        ratio_to=1.0
    )
    assert action_id is not None

    # Test dates
    test_dates = ["2021-03-01", "2022-06-14", "2022-06-15", "2023-01-01"]
    factors = ca_manager.get_adjustment_factors_series(sym, dates=test_dates)

    assert factors["2021-03-01"] == pytest.approx(0.10, rel=1e-5)
    assert factors["2022-06-14"] == pytest.approx(0.10, rel=1e-5)
    assert factors["2022-06-15"] == pytest.approx(1.00, rel=1e-5)  # ex_date is already post-split
    assert factors["2023-01-01"] == pytest.approx(1.00, rel=1e-5)

    # Test full OHLCV DataFrame scaling
    df_raw = pd.DataFrame([
        {"symbol": sym, "trading_date": "2021-03-01", "open": 2500.0, "high": 2550.0, "low": 2480.0, "close": 2500.0, "volume": 100000},
        {"symbol": sym, "trading_date": "2022-06-14", "open": 2600.0, "high": 2650.0, "low": 2580.0, "close": 2600.0, "volume": 120000},
        {"symbol": sym, "trading_date": "2022-06-15", "open": 265.0, "high": 270.0, "low": 262.0, "close": 265.0, "volume": 1500000},
        {"symbol": sym, "trading_date": "2023-01-01", "open": 300.0, "high": 310.0, "low": 298.0, "close": 300.0, "volume": 800000},
    ])

    df_adj = ca_manager.apply_adjustments_to_ohlcv(df_raw)

    # 1. Raw columns must remain unmutated
    assert df_adj["close"].iloc[0] == 2500.0
    assert df_adj["volume"].iloc[0] == 100000

    # 2. Adjusted columns must be scaled correctly
    assert df_adj["adj_close"].iloc[0] == pytest.approx(250.0, rel=1e-2)
    assert df_adj["adj_volume"].iloc[0] == 1000000  # 100k / 0.1 = 1,000,000

    assert df_adj["adj_close"].iloc[1] == pytest.approx(260.0, rel=1e-2)
    assert df_adj["adj_volume"].iloc[1] == 1200000

    assert df_adj["adj_close"].iloc[2] == pytest.approx(265.0, rel=1e-2)
    assert df_adj["adj_volume"].iloc[2] == 1500000

    assert df_adj["adj_close"].iloc[3] == pytest.approx(300.0, rel=1e-2)
    assert df_adj["adj_volume"].iloc[3] == 800000


def test_02_raw_settlement_immutability(hermetic_db):
    """
    Test 2: Asserts raw settlement prices in ohlcv_daily are never mutated by corporate action engine.
    """
    sym = "INFY"
    now_iso = datetime.now(timezone.utc).isoformat()

    # Insert raw bar directly into database
    with hermetic_db.get_connection() as conn:
        conn.execute("""
            INSERT INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume,
                source, retrieval_timestamp, data_status, provenance_class, is_synthetic
            ) VALUES (?, '2021-01-15', 'EQ', 1350.0, 1370.0, 1340.0, 1360.0, 2000000, 'test', ?, 'final_settled', 'EXCHANGE_OFFICIAL', 0)
        """, (sym, now_iso))
        conn.commit()

    ca_manager = CorporateActionsManager(hermetic_db)
    # Record 2:1 bonus / split
    ca_manager.record_action(
        symbol=sym,
        ex_date="2021-06-01",
        action_type="BONUS",
        ratio_from=2.0,
        ratio_to=1.0
    )

    # Fetch and apply adjustments in-memory
    with hermetic_db.get_connection() as conn:
        df_raw = pd.read_sql_query(
            "SELECT symbol, trading_date, open, high, low, close, volume FROM ohlcv_daily WHERE symbol = ?",
            conn,
            params=(sym,)
        )

    df_adj = ca_manager.apply_adjustments_to_ohlcv(df_raw)
    assert df_adj["adj_close"].iloc[0] == pytest.approx(680.0, rel=1e-2)

    # Re-query DB to verify raw storage immutability
    with hermetic_db.get_connection() as conn:
        cur = conn.execute("SELECT open, high, low, close, volume FROM ohlcv_daily WHERE symbol = ? AND trading_date = '2021-01-15'", (sym,))
        row = cur.fetchone()

    assert row[0] == 1350.0, "Database raw open was unexpectedly mutated!"
    assert row[1] == 1370.0, "Database raw high was unexpectedly mutated!"
    assert row[2] == 1340.0, "Database raw low was unexpectedly mutated!"
    assert row[3] == 1360.0, "Database raw close was unexpectedly mutated!"
    assert row[4] == 2000000, "Database raw volume was unexpectedly mutated!"


def test_03_checkpoint_resumption_and_fault_tolerance(hermetic_db, monkeypatch):
    """
    Test 3: Verifies checkpoint matrix initialization, failure isolation,
    and resumption without duplicate insertions.
    """
    coordinator = HistoricalBackfillCoordinator(hermetic_db)
    test_symbols = ["RELIANCE", "HDFCBANK"]

    def mock_load_bars(symbol, year, month):
        return [{
            "symbol": symbol,
            "trading_date": f"{year:04d}-{month:02d}-01",
            "series": "EQ",
            "open": 2000.0,
            "high": 2050.0,
            "low": 1980.0,
            "close": 2010.0,
            "volume": 500000,
            "source": "TEST_AUTHENTIC_FEED",
            "retrieval_timestamp": "2024-01-01T00:00:00Z",
            "data_status": "final_settled",
            "provenance_class": "EXCHANGE_OFFICIAL",
            "is_synthetic": 0,
            "is_eligible_for_live_analytics": 1,
            "is_eligible_for_backtest": 1,
            "is_eligible_for_training": 1
        }]

    monkeypatch.setattr(coordinator, "_load_authentic_bars_for_month", mock_load_bars)

    # Initialize 2 symbols x 2 months (2024-01 to 2024-02) = 4 units
    total_units = coordinator.initialize_checkpoint_matrix(
        symbols=test_symbols,
        start_year=2024,
        end_year=2024,
        end_month=2
    )
    assert total_units == 4

    stats = coordinator.get_checkpoint_stats()
    assert stats["total_work_units"] == 4
    assert stats["pending_units"] == 4
    assert stats["completed_units"] == 0

    # Execute first batch of 2 units
    res1 = coordinator.execute_backfill_batch(batch_size_months=2)
    assert res1["processed_chunks"] == 2
    assert res1["stats"]["completed_units"] == 2
    assert res1["stats"]["pending_units"] == 2

    # Simulate unexpected worker crash or failure on one completed unit
    with hermetic_db.get_connection() as conn:
        conn.execute("""
            UPDATE backfill_sync_checkpoints
            SET status = 'FAILED', error_message = 'Simulated network drop'
            WHERE symbol = 'RELIANCE' AND target_year = 2024 AND target_month = 1
        """)
        conn.commit()

    stats_after_fail = coordinator.get_checkpoint_stats()
    assert stats_after_fail["failed_units"] == 1
    assert stats_after_fail["completed_units"] == 1

    # Resume backfill (batch_size=4 to process the FAILED unit and the 2 PENDING units)
    res2 = coordinator.execute_backfill_batch(batch_size_months=4)
    assert res2["processed_chunks"] == 3  # 1 failed resumed + 2 pending processed
    assert res2["failed_chunks"] == 0

    final_stats = coordinator.get_checkpoint_stats()
    assert final_stats["completed_units"] == 4
    assert final_stats["pending_units"] == 0
    assert final_stats["failed_units"] == 0
    assert final_stats["completion_pct"] == 100.0


def test_04_factor_engine_252_session_burn_in(hermetic_db):
    """
    Test 4: Verifies factor engine outputs NULL for long-term indicators (sma_200, momentum_1y, vol_ann)
    when historical depth is under 252 sessions, and computes them once >= 252 sessions.
    """
    factor_engine = FactorEngine(hermetic_db)
    sym = "TITAN"

    # 1. Synthesize 150 daily bars (< 252 sessions)
    dates_150 = [f"2022-01-{i:02d}" if i <= 31 else (f"2022-02-{i-31:02d}" if i <= 59 else f"2022-03-{i-59:02d}") for i in range(1, 151)]
    # Use continuous synthetic sequence
    dates_150 = [f"2022-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}" for i in range(150)]

    df_150 = pd.DataFrame({
        "symbol": sym,
        "trading_date": dates_150,
        "open": [100.0 + i * 0.5 for i in range(150)],
        "high": [102.0 + i * 0.5 for i in range(150)],
        "low": [99.0 + i * 0.5 for i in range(150)],
        "close": [101.0 + i * 0.5 for i in range(150)],
        "volume": [500000 for _ in range(150)],
    })

    res_150 = factor_engine.compute_factors_for_symbol(sym, df_ohlcv=df_150)
    assert len(res_150) == 150

    # Short-term metrics (sma_20) must be available for i >= 19
    assert pd.isna(res_150["sma_20"].iloc[18])
    assert not pd.isna(res_150["sma_20"].iloc[19])

    # Long-term metrics MUST be strictly NULL for all rows (< 252 sessions)
    for idx in range(len(res_150)):
        assert pd.isna(res_150["sma_200"].iloc[idx]), f"sma_200 must be NULL at index {idx}"
        assert pd.isna(res_150["momentum_1y"].iloc[idx]), f"momentum_1y must be NULL at index {idx}"
        assert pd.isna(res_150["volatility_annualized"].iloc[idx]), f"volatility_annualized must be NULL at index {idx}"
        assert bool(res_150["burn_in_complete"].iloc[idx]) is False

    # 2. Synthesize 260 daily bars (>= 252 sessions)
    dates_260 = [f"2020-{(i // 25) + 1:02d}-{(i % 25) + 1:02d}" for i in range(260)]
    df_260 = pd.DataFrame({
        "symbol": sym,
        "trading_date": dates_260,
        "open": [100.0 + i * 0.2 for i in range(260)],
        "high": [101.0 + i * 0.2 for i in range(260)],
        "low": [99.0 + i * 0.2 for i in range(260)],
        "close": [100.5 + i * 0.2 for i in range(260)],
        "volume": [600000 for _ in range(260)],
    })

    res_260 = factor_engine.compute_factors_for_symbol(sym, df_ohlcv=df_260)
    assert len(res_260) == 260

    # Prior to 252 sessions (i < 251): NULL
    assert pd.isna(res_260["sma_200"].iloc[250])
    assert pd.isna(res_260["momentum_1y"].iloc[250])
    assert pd.isna(res_260["volatility_annualized"].iloc[250])
    assert bool(res_260["burn_in_complete"].iloc[250]) is False

    # At and after 252 sessions (i >= 251): Computed
    assert not pd.isna(res_260["sma_200"].iloc[251])
    assert not pd.isna(res_260["momentum_1y"].iloc[251])
    assert not pd.isna(res_260["volatility_annualized"].iloc[251])
    assert bool(res_260["burn_in_complete"].iloc[251]) is True


def test_05_listing_date_guard_marks_not_yet_listed(hermetic_db):
    """
    Test 5: Verifies that pre-IPO monthly checkpoints for unlisted instruments
    are automatically marked NOT_YET_LISTED with 0 rows ingested, preventing
    ghost price fabrication prior to official exchange listing.
    """
    coordinator = HistoricalBackfillCoordinator(hermetic_db)
    sym = "AADHARHFC"  # Listed on NSE on 2024-05-15

    # Initialize single unit for 2020-01 (over 4 years prior to IPO)
    total_units = coordinator.initialize_checkpoint_matrix(
        symbols=[sym],
        start_year=2020,
        end_year=2020,
        end_month=1
    )
    assert total_units == 1

    # Execute batch
    res = coordinator.execute_backfill_batch(batch_size_months=1)
    assert res["processed_chunks"] == 1

    # Verify checkpoint row in database
    with hermetic_db.get_connection() as conn:
        cur = conn.execute("""
            SELECT status, rows_ingested, earliest_date_ingested, latest_date_ingested
            FROM backfill_sync_checkpoints
            WHERE symbol = ? AND target_year = 2020 AND target_month = 1
        """, (sym,))
        row = cur.fetchone()

    assert row is not None
    assert row[0] == "NOT_YET_LISTED"
    assert row[1] == 0
    assert row[2] is None
    assert row[3] is None

    # Verify zero rows in ohlcv_daily for AADHARHFC in 2020-01
    with hermetic_db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND trading_date LIKE '2020-01%'", (sym,))
        count = cur.fetchone()[0]
    assert count == 0, "No rows should exist for unlisted symbol prior to IPO!"


def test_06_missing_source_data_does_not_fabricate(hermetic_db):
    """
    Test 6: Verifies that when authentic exchange bhavcopy archives are missing
    for a listed instrument, the coordinator records MISSING_SOURCE_DATA with 0 rows,
    strictly prohibiting synthetic fallback price fabrication.
    """
    coordinator = HistoricalBackfillCoordinator(hermetic_db)
    sym = "TCS"  # Listed since 2004, but no local archive exists in test hermetic DB for 2020-01

    total_units = coordinator.initialize_checkpoint_matrix(
        symbols=[sym],
        start_year=2020,
        end_year=2020,
        end_month=1
    )
    assert total_units == 1

    res = coordinator.execute_backfill_batch(batch_size_months=1)
    assert res["processed_chunks"] == 1
    assert res["missing_source_chunks"] == 1
    assert res["stats"]["completed_units"] == 0
    assert res["stats"]["missing_source_units"] == 1

    # Verify checkpoint row in database
    with hermetic_db.get_connection() as conn:
        cur = conn.execute("""
            SELECT status, rows_ingested, earliest_date_ingested, latest_date_ingested
            FROM backfill_sync_checkpoints
            WHERE symbol = ? AND target_year = 2020 AND target_month = 1
        """, (sym,))
        row = cur.fetchone()

    assert row is not None
    assert row[0] == "MISSING_SOURCE_DATA"
    assert row[1] == 0

    # Verify zero synthetic rows in ohlcv_daily
    with hermetic_db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND trading_date LIKE '2020-01%'", (sym,))
        assert cur.fetchone()[0] == 0
        cur_synth = conn.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE is_synthetic = 1")
        assert cur_synth.fetchone()[0] == 0


def test_07_verified_corporate_actions_seeded(hermetic_db):
    """
    Test 7: Verifies that pre-seeding historical corporate actions populates
    verified splits and bonuses with correct multipliers.
    """
    ca_manager = CorporateActionsManager(hermetic_db)
    seeded_count = ca_manager.seed_verified_corporate_actions()
    assert seeded_count >= 18

    with hermetic_db.get_connection() as conn:
        # Check AARTIIND 1:1 bonus (ratio 2:1 -> multiplier 0.5)
        cur = conn.execute("""
            SELECT action_type, split_multiplier, is_applied
            FROM corporate_action_adjustments
            WHERE symbol = 'AARTIIND' AND ex_date = '2021-06-22'
        """)
        aarti = cur.fetchone()
        assert aarti is not None
        assert aarti[0] == "BONUS"
        assert aarti[1] == pytest.approx(0.5, rel=1e-5)
        assert aarti[2] == 1

        # Check IRCTC 5:1 split (ratio 5:1 -> multiplier 0.2)
        cur = conn.execute("""
            SELECT action_type, split_multiplier, is_applied
            FROM corporate_action_adjustments
            WHERE symbol = 'IRCTC' AND ex_date = '2021-10-28'
        """)
        irctc = cur.fetchone()
        assert irctc is not None
        assert irctc[0] == "SPLIT"
        assert irctc[1] == pytest.approx(0.2, rel=1e-5)
        assert irctc[2] == 1
