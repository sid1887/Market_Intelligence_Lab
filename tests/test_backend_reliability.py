"""
Unit and Integration Tests for Backend Reliability, Optional Dependencies & Daemon Lifecycle.
Workstream 4 / Audit Ticket: Finding 4, MIL-P0-008, MIL-BE-001, MIL-BE-003.

Verifies:
1. Module imports are resilient when optional dependencies like yfinance are unavailable.
2. Daemon _execute_eod_pipeline returns structured dict telemetry.
3. Settlement completion check uses dynamic securities_master count instead of hardcoded 150.
4. Failed settlement pipeline runs do not advance last_eod_date.
"""

import pytest
import asyncio
from unittest.mock import patch, MagicMock
from datetime import datetime, timezone

from src.storage.database import DatabaseManager
from src.tasks.daemon import AutonomousPlatformDaemon
import src.client.macro_client as macro_client_module
import src.pipeline.universe_ingestion as universe_ingestion_module


@pytest.fixture
def daemon_test_db(tmp_path):
    db_file = str(tmp_path / "test_daemon.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active)
            VALUES ('TCS', 'Tata Consultancy Services', 'INE467B01029', 'IT', 'Tech', 'IT', '2026-11-06T00:00:00Z', 1);
        """)
        conn.commit()
    return db_file


def test_optional_dependency_isolation():
    """Ensure modules gracefully handle absence of yfinance."""
    with patch.object(macro_client_module, "yf", None):
        client = macro_client_module.MacroClient()
        data = client.get_macro_telemetry(force_refresh=True)
        assert "indicators" in data
        assert len(data["indicators"]) >= 3

    with patch.object(universe_ingestion_module, "yf", None):
        mgr = universe_ingestion_module.UniverseIngestionManager()
        sym, candles = mgr._fetch_symbol_candles("TCS")
        assert sym == "TCS"
        assert candles == []
        bench = mgr._fetch_benchmark_candles()
        assert bench == []


def test_daemon_eod_pipeline_structured_result(daemon_test_db):
    """Daemon _execute_eod_pipeline must return a structured dictionary."""
    daemon = AutonomousPlatformDaemon(db_path=daemon_test_db)
    
    with patch("src.pipeline.universe_ingestion.UniverseIngestionManager.execute_universe_ingestion") as mock_ingest:
        mock_ingest.return_value = {
            "status": "SUCCESS",
            "settled_date": "2026-11-06",
            "symbols_updated": 1,
            "records_ingested": 1,
            "factors_computed": 1,
            "duration_seconds": 0.5,
            "message": "Success"
        }
        res = daemon._execute_eod_pipeline("2026-11-06")
        assert isinstance(res, dict)
        assert res["status"] == "SUCCESS"
        assert res["target_date"] == "2026-11-06"
        assert res["factors_written"] == 1
        assert res["error"] is None


@pytest.mark.asyncio
async def test_daemon_failed_settlement_does_not_advance_date(daemon_test_db):
    """If EOD settlement fails, last_eod_date must NOT advance, allowing retry."""
    daemon = AutonomousPlatformDaemon(db_path=daemon_test_db)
    daemon.last_eod_date = None

    # Mock time to after 16:15 IST on a trading session
    ist_time = datetime(2026, 11, 6, 17, 0, 0)
    with patch.object(daemon, "_get_ist_now", return_value=ist_time), \
         patch("src.tasks.daemon.is_trading_session", return_value=True), \
         patch.object(daemon, "_execute_eod_pipeline", return_value={"status": "FAILED", "factors_written": 0}):
        
        await daemon.check_and_run_eod_settlement()
        # Must still be None because the pipeline failed!
        assert daemon.last_eod_date is None


@pytest.mark.asyncio
async def test_daemon_successful_settlement_advances_date(daemon_test_db):
    """If EOD settlement succeeds with new bars for today, last_eod_date advances."""
    daemon = AutonomousPlatformDaemon(db_path=daemon_test_db)
    daemon.last_eod_date = None

    ist_time = datetime(2026, 11, 6, 17, 0, 0)
    with patch.object(daemon, "_get_ist_now", return_value=ist_time), \
         patch("src.tasks.daemon.is_trading_session", return_value=True), \
         patch.object(daemon, "_execute_eod_pipeline", return_value={
             "status": "SUCCESS",
             "settled_date": "2026-11-06",
             "records_ingested": 181,
             "factors_written": 181
         }):
        
        await daemon.check_and_run_eod_settlement()
        assert daemon.last_eod_date == "2026-11-06"


def test_zero_candles_ingestion_fails_closed(tmp_path):
    """Ingestion fetching 0 bars must fail closed with FAILED / NO_NEW_BARS and not advance settlement."""
    db_file = str(tmp_path / "test_zero_ingest.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active)
            VALUES ('TCS', 'Tata Consultancy Services', 'INE467B01029', 'IT', 'Tech', 'IT', '2026-11-06T00:00:00Z', 1);
        """)
        conn.commit()

    mgr = universe_ingestion_module.UniverseIngestionManager(db_file)

    # Mock _fetch_symbol_candles to return 0 candles
    with patch.object(mgr, "_fetch_symbol_candles", return_value=("TCS", [])):
        res = mgr.execute_universe_ingestion()
        assert res["status"] == "FAILED"
        assert res["reason"] == "NO_NEW_BARS"
        assert res["settled_date"] is None
        assert res["records_ingested"] == 0


def test_partial_ingestion_under_85_pct_fails_closed(tmp_path):
    """Partial ingestion returning < 85% of active universe must fail closed with INSUFFICIENT_COVERAGE."""
    db_file = str(tmp_path / "test_partial_coverage.db")
    db = DatabaseManager(db_file)
    with db.get_connection() as conn:
        for i in range(20):
            conn.execute(f"""
                INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, updated_at, is_active)
                VALUES ('SYM{i}', 'Test Company {i}', 'INE000000{i}', 'IT', 'Tech', 'IT', '2026-11-06T00:00:00Z', 1);
            """)
        conn.commit()

    mgr = universe_ingestion_module.UniverseIngestionManager(db_file)

    # Mock _fetch_symbol_candles to only return candles for 5 symbols (out of 20 = 25% < 85%)
    def mock_fetch(symbol):
        if symbol in ["SYM0", "SYM1", "SYM2", "SYM3", "SYM4"]:
            return symbol, [{
                "symbol": symbol, "trading_date": "2026-11-06", "series": "EQ",
                "open": 100.0, "high": 105.0, "low": 95.0, "close": 102.0, "ltp": 102.0,
                "prev_close": 100.0, "volume": 10000, "source": "test",
                "retrieval_timestamp": "2026-11-06T18:00:00Z", "data_status": "final_settled",
                "provenance_class": "EXCHANGE_OFFICIAL", "is_synthetic": 0,
                "is_eligible_for_live_analytics": 1, "is_eligible_for_backtest": 1, "is_eligible_for_training": 1
            }]
        return symbol, []

    with patch.object(mgr, "_fetch_symbol_candles", side_effect=mock_fetch):
        res = mgr.execute_universe_ingestion(target_date="2026-11-06")
        assert res["status"] == "FAILED"
        assert res["error_code"] == "INSUFFICIENT_COVERAGE"
        assert res["reason"] == "PARTIAL_UNIVERSE_COVERAGE"
        assert res["records_ingested"] == 5
        assert res["settled_date"] is None


@pytest.mark.asyncio
async def test_empty_ingestion_returns_failed_and_does_not_advance_daemon(daemon_test_db):
    """Zero-candle fetch must return status: 'FAILED', records_ingested: 0, and daemon must not advance last_eod_date."""
    daemon = AutonomousPlatformDaemon(db_path=daemon_test_db)
    daemon.last_eod_date = None

    ist_time = datetime(2026, 11, 6, 17, 0, 0)
    with patch.object(daemon, "_get_ist_now", return_value=ist_time), \
         patch("src.tasks.daemon.is_trading_session", return_value=True), \
         patch("src.pipeline.universe_ingestion.UniverseIngestionManager.execute_universe_ingestion", return_value={
             "status": "FAILED",
             "error_code": "NO_NEW_BARS",
             "records_ingested": 0,
             "reason": "NO_NEW_BARS"
         }):
        settled = await daemon.check_and_run_eod_settlement()
        assert settled is False
        assert daemon.last_eod_date is None


def test_macro_telemetry_truthfulness_on_provider_failure():
    """When external providers fail, values must be None and status must NOT masquerade as live_observed."""
    with patch.object(macro_client_module, "yf", None):
        data = macro_client_module.MacroClient.get_macro_telemetry(force_refresh=True)
        assert data["status"] in ("unavailable", "cached_eod")
        for ind in data["indicators"]:
            # Hardcoded fake numbers like 84.12, 74.85, 4.28 must NOT be present as live
            assert ind["source"] in ("yfinance", "unconfigured_ccil", "alphavantage_fx")
            if ind.get("freshness_status") == "UNAVAILABLE":
                assert ind["value"] is None
                assert ind["change_pct"] is None


def test_database_migration_fails_fast_on_error(tmp_path):
    """DatabaseManager.init_schema must fail loud and fast if a migration raises an error (P0-07)."""
    db_file = str(tmp_path / "test_migration_fail.db")
    db = DatabaseManager(db_file)

    with patch("src.storage.migrations.run_all_migrations", side_effect=RuntimeError("Syntax error in migration 005")):
        with pytest.raises(RuntimeError, match="Syntax error in migration 005"):
            db.init_schema()
