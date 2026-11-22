"""
Market Intelligence Lab — Pytest Fixtures & Test Harness.
Provides isolated in-memory SQLite database and test client fixtures.
"""

import os
import sys
from pathlib import Path

# Ensure repository root is always in sys.path
ROOT_DIR = str(Path(__file__).resolve().parent.parent)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest
import sqlite3
import datetime
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager


@pytest.fixture
def in_memory_db():
    """Provides an isolated in-memory DatabaseManager with initialized schema."""
    db = DatabaseManager(":memory:")
    # Seed minimal baseline data for test isolation
    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO securities_master (
                symbol, company_name, isin, industry, sector, macro_sector, is_active, is_nifty50, updated_at
            ) VALUES ('TESTCO', 'Test Company Ltd', 'INE000A01010', 'Software', 'Information Technology', 'Technology', 1, 1, '2026-11-20T00:00:00Z')
        """)
        conn.execute("""
            INSERT OR IGNORE INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp,
                data_status, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                is_eligible_for_backtest, is_eligible_for_training
            ) VALUES ('TESTCO', '2026-11-20', 'EQ', 100.0, 105.0, 98.0, 102.5, 50000, 'EXCHANGE_OFFICIAL',
                      '2026-11-20T16:00:00Z', 'final_settled', 'EXCHANGE_OFFICIAL', 0, 1, 1, 1)
        """)
        conn.execute("""
            INSERT OR IGNORE INTO quant_factors_daily (
                symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200, roe_pct, debt_to_equity, opm_pct, ttm_pe
            ) VALUES ('TESTCO', '2026-11-20', 0.015, 0.04, 0.08, 100.0, 95.0, 90.0, 22.5, 0.2, 18.0, 25.0)
        """)
        conn.commit()
    return db


@pytest.fixture(scope="session", autouse=True)
def ensure_test_database_hydrated():
    """Guarantees data/market_lab.db exists and is hydrated from snapshot for all test runs."""
    from src.storage.hydration import hydrate_initial_cloud_database
    from src.api.utils import DATABASE_PATH
    os.makedirs(os.path.dirname(DATABASE_PATH), exist_ok=True)
    hydrate_initial_cloud_database(DATABASE_PATH)


@pytest.fixture
def test_client():
    """FastAPI TestClient instance for API route integration testing."""
    from src.api.main import app
    return TestClient(app)
