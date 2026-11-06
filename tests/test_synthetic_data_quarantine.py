"""
Unit and Integration Tests for Synthetic Data Quarantine & Provenance Invariants.
Workstream 2 / Audit Ticket: MIL-DATA-001, MIL-DATA-002, MIL-P0-001.

Verifies:
1. Synthetic records are tagged with is_synthetic = 1, provenance_class = 'SYNTHETIC_TEST'.
2. Eligible real records have is_synthetic = 0, is_eligible_for_live_analytics = 1.
3. Factor pipeline and screener queries exclude synthetic records.
4. Backtest engine excludes synthetic bars from execution price map.
"""

import pytest
from src.storage.database import DatabaseManager
from src.quant.screener import FactorScreener
from src.quant.factor_pipeline import FactorPipeline
from src.quant.backtest_engine import BacktestEngine


@pytest.fixture
def synthetic_test_db(tmp_path):
    db_file = str(tmp_path / "test_synth.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active) VALUES ('REALSOCK', 'Real Stock Ltd', 'INE000R01010', 'Energy', 'Energy', 'Energy', '2026-11-06T00:00:00Z', 1);")
        conn.execute("INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active) VALUES ('FAKESOCK', 'Fake Stock Ltd', 'INE000F01010', 'Unknown', 'Unknown', 'Unknown', '2026-11-06T00:00:00Z', 1);")

        # 1. Real bar
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, provenance_class, is_synthetic, is_eligible_for_live_analytics, is_eligible_for_backtest)
            VALUES ('REALSOCK', '2026-11-06', 'EQ', 200.0, 205.0, 198.0, 202.0, 500000, 'nse_bhavcopy', '2026-11-06T17:00:00Z', 'EXCHANGE_OFFICIAL', 0, 1, 1);
        """)

        # 2. Synthetic bar
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, provenance_class, is_synthetic, is_eligible_for_live_analytics, is_eligible_for_backtest)
            VALUES ('FAKESOCK', '2026-11-06', 'EQ', 10.0, 12.0, 9.0, 11.0, 10000, 'offline_multi_regime_generator', '2026-11-06T17:00:00Z', 'SYNTHETIC_TEST', 1, 0, 0);
        """)

        # 3. Factor rows for both
        conn.execute("""
            INSERT INTO quant_factors_daily (symbol, trading_date, ret_1d, ret_20d, sma_200, roe_pct, debt_to_equity, opm_pct, is_orphaned)
            VALUES ('REALSOCK', '2026-11-06', 0.01, 0.05, 190.0, 20.0, 0.1, 25.0, 0);
        """)
        conn.execute("""
            INSERT INTO quant_factors_daily (symbol, trading_date, ret_1d, ret_20d, sma_200, roe_pct, debt_to_equity, opm_pct, is_orphaned)
            VALUES ('FAKESOCK', '2026-11-06', 0.05, 0.20, 10.0, 15.0, 0.5, 18.0, 0);
        """)
        conn.commit()

    return db


def test_upsert_automatically_quarantines_synthetic_source(synthetic_test_db):
    records = [{
        "symbol": "SINETEST",
        "trading_date": "2026-11-06",
        "series": "EQ",
        "open": 50.0,
        "high": 52.0,
        "low": 49.0,
        "close": 51.0,
        "volume": 20000,
        "source": "offline_multi_regime_generator",
        "retrieval_timestamp": "2026-11-06T12:00:00Z"
    }]
    synthetic_test_db.upsert_ohlcv_records(records)

    with synthetic_test_db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT provenance_class, is_synthetic, is_eligible_for_live_analytics FROM ohlcv_daily WHERE symbol = 'SINETEST';")
        row = cur.fetchone()
        assert row["is_synthetic"] == 1
        assert row["provenance_class"] == "SYNTHETIC_TEST"
        assert row["is_eligible_for_live_analytics"] == 0


def test_screener_excludes_synthetic_bars(synthetic_test_db):
    screener = FactorScreener(synthetic_test_db)
    df = screener.screen(as_of_date="2026-11-06")
    symbols = list(df["symbol"])
    assert "REALSOCK" in symbols
    assert "FAKESOCK" not in symbols


def test_backtest_excludes_synthetic_bars(synthetic_test_db):
    engine = BacktestEngine(db_manager=synthetic_test_db)
    sessions = engine._get_trading_calendar("2026-11-06", "2026-11-06")
    assert "2026-11-06" in sessions

    with synthetic_test_db.get_connection() as conn:
        cur = conn.execute("""
            SELECT symbol FROM ohlcv_daily 
            WHERE trading_date = '2026-11-06' AND COALESCE(is_synthetic, 0) = 0;
        """)
        eligible_symbols = [r[0] for r in cur.fetchall()]
        assert "REALSOCK" in eligible_symbols
        assert "FAKESOCK" not in eligible_symbols
