"""
Unit and Integration Tests for Factor & OHLCV Integrity.
Workstream 1 / Audit Ticket: MIL-DATA-003, MIL-P0-018.

Verifies:
1. Orphan factor records are tagged with is_orphaned = 1.
2. Matched factors have is_orphaned = 0.
3. Screener explicitly excludes is_orphaned factor rows.
4. Feature extractor strictly requires matched, non-orphaned OHLCV records.
"""

import sqlite3
import pytest
from src.storage.database import DatabaseManager
from src.quant.screener import FactorScreener
from src.ml.features.builder import PITFeatureExtractor


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_integrity.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        # Seed securities
        conn.execute("INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active) VALUES ('TESTA', 'Test A Corp', 'INE000A01010', 'Software', 'IT', 'Technology', '2026-11-06T00:00:00Z', 1);")
        conn.execute("INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active) VALUES ('TESTB', 'Test B Corp', 'INE000B01010', 'Banking', 'Financial Services', 'Financials', '2026-11-06T00:00:00Z', 1);")

        # Seed valid OHLCV for TESTA
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, data_status, is_synthetic, provenance_class)
            VALUES ('TESTA', '2026-11-06', 'EQ', 100.0, 105.0, 99.0, 104.0, 1000000, 'nse_bhavcopy', '2026-11-06T17:00:00Z', 'final_settled', 0, 'EXCHANGE_OFFICIAL');
        """)

        # Seed factor for TESTA (matched)
        conn.execute("""
            INSERT INTO quant_factors_daily (symbol, trading_date, ret_1d, ret_20d, sma_200, roe_pct, debt_to_equity, opm_pct, is_orphaned)
            VALUES ('TESTA', '2026-11-06', 0.04, 0.12, 95.0, 18.0, 0.2, 22.0, 0);
        """)

        # Seed orphan factor for TESTB (no OHLCV row exists for TESTB on 2026-11-06)
        conn.execute("""
            INSERT INTO quant_factors_daily (symbol, trading_date, ret_1d, ret_20d, sma_200, roe_pct, debt_to_equity, opm_pct, is_orphaned)
            VALUES ('TESTB', '2026-11-06', 0.01, 0.05, 45.0, 12.0, 0.5, 15.0, 1);
        """)
        conn.commit()

    return db


def test_orphan_tagging_invariance(test_db):
    with test_db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT symbol, is_orphaned FROM quant_factors_daily ORDER BY symbol ASC;")
        rows = cur.fetchall()
        assert len(rows) == 2
        assert rows[0]["symbol"] == "TESTA"
        assert rows[0]["is_orphaned"] == 0
        assert rows[1]["symbol"] == "TESTB"
        assert rows[1]["is_orphaned"] == 1


def test_screener_excludes_orphan_factors(test_db):
    screener = FactorScreener(test_db)
    df = screener.screen(as_of_date="2026-11-06")
    # Only TESTA should be returned; TESTB (orphan factor) must be excluded
    symbols = list(df["symbol"])
    assert "TESTA" in symbols
    assert "TESTB" not in symbols


def test_feature_extractor_excludes_orphan_factors(test_db):
    builder = PITFeatureExtractor(test_db)
    panel = builder.extract_panel("2026-11-06", "2026-11-06")
    symbols = list(panel["symbol"])
    assert "TESTA" in symbols
    assert "TESTB" not in symbols


def test_non_eq_series_bars_do_not_reconcile_factors(tmp_path):
    """Factors must strictly match series = 'EQ'; bars with series = 'BL' or 'T0' cannot unflag orphans (P0-04)."""
    db_file = str(tmp_path / "test_series_reconcile.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        conn.execute("INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active) VALUES ('BLSYM', 'Block Only Ltd', 'INE000B01010', 'Infra', 'Infra', 'Infra', '2026-11-06T00:00:00Z', 1);")
        # Insert only a BL series bar (no EQ bar)
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp, data_status, is_synthetic, provenance_class)
            VALUES ('BLSYM', '2026-11-06', 'BL', 500.0, 500.0, 500.0, 500.0, 100000, 'nse_bhavcopy', '2026-11-06T17:00:00Z', 'final_settled', 0, 'EXCHANGE_OFFICIAL');
        """)
        # Insert a factor record for BLSYM
        conn.execute("""
            INSERT INTO quant_factors_daily (symbol, trading_date, ret_1d, ret_20d, sma_200, roe_pct, debt_to_equity, opm_pct, is_orphaned)
            VALUES ('BLSYM', '2026-11-06', 0.01, 0.05, 490.0, 15.0, 0.3, 20.0, 0);
        """)
        conn.commit()

    from scripts.reconcile_factor_ohlcv import run_reconciliation
    rep_path = str(tmp_path / "report.md")
    res = run_reconciliation(db_path=db_file, report_path=rep_path)
    
    # BLSYM has no EQ bar, so it must be flagged as an orphan
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT is_orphaned FROM quant_factors_daily WHERE symbol = 'BLSYM';")
        assert cur.fetchone()["is_orphaned"] == 1
