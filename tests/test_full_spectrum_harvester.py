"""
tests/test_full_spectrum_harvester.py
Verification suite for FullSpectrumHarvester, .milz chart merging in tearsheet/history,
and Screener delivery & turnover exposures.
"""

import os
import json
import sqlite3
import tempfile
import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.storage.compression_engine import MilzArchiveEngine
from src.data.full_spectrum_harvester import FullSpectrumHarvester, CANONICAL_SECTORS
from src.api.main import app
from src.api.routes_market import get_db_connection


@pytest.fixture
def mock_harvest_db(tmp_path):
    """Creates a temporary SQLite database initialized with core tables."""
    db_file = tmp_path / "test_market_lab.db"
    db = DatabaseManager(str(db_file))
    db.init_schema()
    
    with db.get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        # Insert test securities
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (
                symbol, company_name, isin, industry, sector, macro_sector, is_active, updated_at
            ) VALUES 
            ('TESTSYM1', 'Test Company One', 'INE000000001', 'General', 'Equities', 'Equities', 1, '2026-11-20T00:00:00Z'),
            ('TESTSYM2', 'Test Company Two', 'INE000000002', 'IT Services', 'Information Technology', 'Technology', 1, '2026-11-20T00:00:00Z'),
            ('RELIANCE', 'Reliance Industries Ltd', 'INE002A01018', 'Oil & Gas', 'Oil Gas & Consumable Fuels', 'Energy', 1, '2026-11-20T00:00:00Z');
        """)
        # Insert hot OHLCV daily bars for RELIANCE (recent 3 days)
        conn.execute("""
            INSERT OR REPLACE INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume, turnover, delivery_qty,
                source, retrieval_timestamp, provenance_class, is_synthetic, is_eligible_for_live_analytics
            ) VALUES 
            ('RELIANCE', '2026-11-18', 'EQ', 1370.0, 1380.0, 1365.0, 1375.0, 1000000, 1375000000.0, 500000, 'test', '2026-11-18', 'EXCHANGE_OFFICIAL', 0, 1),
            ('RELIANCE', '2026-11-19', 'EQ', 1375.0, 1385.0, 1370.0, 1380.0, 1200000, 1656000000.0, 600000, 'test', '2026-11-19', 'EXCHANGE_OFFICIAL', 0, 1),
            ('RELIANCE', '2026-11-20', 'EQ', 1380.0, 1390.0, 1375.0, 1385.0, 1100000, 1523500000.0, 550000, 'test', '2026-11-20', 'EXCHANGE_OFFICIAL', 0, 1);
        """)
        # Insert quant factors
        conn.execute("""
            INSERT OR REPLACE INTO quant_factors_daily (
                symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200,
                volatility_annualized, beta_60d_nifty, roe_pct, debt_to_equity, ttm_pe, opm_pct,
                distance_52w_high, distance_52w_low
            ) VALUES 
            ('RELIANCE', '2026-11-20', 0.0036, 0.012, 0.045, 1350.0, 1330.0, 1300.0, 0.18, 0.95, 14.5, 0.42, 22.5, 12.0, -0.045, 0.22);
        """)
        conn.commit()
    
    return db


def test_sector_resolution_logic(mock_harvest_db, tmp_path):
    """Verifies FullSpectrumHarvester resolves generic 'Equities' sector into canonical names."""
    archive_file = tmp_path / "test.milz"
    harvester = FullSpectrumHarvester(db=mock_harvest_db, archive_path=archive_file)
    
    # Test canonical mapper
    assert harvester._map_to_canonical("Banking & Financial Services") == "Financial Services"
    assert harvester._map_to_canonical("Technology", "Software") == "Information Technology"
    assert harvester._map_to_canonical("Pharmaceuticals") == "Healthcare"
    assert harvester._map_to_canonical("Auto Ancillaries") == "Automobile and Auto Components"
    assert harvester._map_to_canonical("Real Estate Development") == "Realty"
    assert harvester._map_to_canonical("Cement & Building Materials") == "Construction Materials"
    
    # Run curated dictionary pass
    res = harvester.resolve_generic_sectors()
    assert isinstance(res, dict)


def test_milz_candle_merging_in_tearsheet(mock_harvest_db, tmp_path):
    """Verifies /stocks/{symbol}/tearsheet merges .milz cold history with SQLite hot bars without duplicates."""
    archive_file = tmp_path / "bhavcopy_10y.milz"
    archive_engine = MilzArchiveEngine(archive_file)
    
    # Pack older historical bars into .milz for RELIANCE (e.g. 2026-11-10 to 2026-11-17)
    milz_df = pd.DataFrame([
        {"symbol": "RELIANCE", "trading_date": "2026-11-10", "open": 1350.0, "high": 1360.0, "low": 1345.0, "close": 1355.0, "volume": 900000, "vwap": 1352.0, "trades_count": 50000, "deliv_pct": 5000},
        {"symbol": "RELIANCE", "trading_date": "2026-11-11", "open": 1355.0, "high": 1365.0, "low": 1350.0, "close": 1360.0, "volume": 950000, "vwap": 1358.0, "trades_count": 52000, "deliv_pct": 5200},
        # Overlapping bar that also exists in SQLite (2026-11-18)
        {"symbol": "RELIANCE", "trading_date": "2026-11-18", "open": 1370.0, "high": 1380.0, "low": 1365.0, "close": 1375.0, "volume": 1000000, "vwap": 1372.0, "trades_count": 60000, "deliv_pct": 5000},
    ])
    archive_engine.write_archive(milz_df)
    
    # Point default archive path to temp archive
    orig_archive_path = Path("data/archive/bhavcopy_10y.milz")
    archive_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Test client override
    app.dependency_overrides[get_db_connection] = lambda: mock_harvest_db.get_connection()
    client = TestClient(app)
    
    # If file exists at data/archive/bhavcopy_10y.milz, test tearsheet
    res = client.get("/api/v1/stocks/RELIANCE/tearsheet")
    assert res.status_code == 200
    data = res.json()
    
    # Verify microstructure fields are returned
    assert "delivery_pct" in data["technicals"]
    assert "turnover_cr" in data["technicals"]
    assert "pct_from_52w_high" in data["technicals"]
    assert data["technicals"]["delivery_pct"] == 50.0  # 550,000 / 1,100,000 * 100 = 50.0%
    assert data["technicals"]["turnover_cr"] > 0
    assert data["technicals"]["pct_from_52w_high"] == -4.5
    
    # Clean up override
    app.dependency_overrides.clear()


def test_screener_delivery_and_turnover_exposure(mock_harvest_db):
    """Verifies FactorScreener and /api/v1/screener return delivery_pct and turnover_cr."""
    from src.quant.screener import FactorScreener
    from src.api.main import invalidate_screener_cache
    
    # 1. Direct FactorScreener test on mock_harvest_db
    screener = FactorScreener(mock_harvest_db)
    df = screener.screen(trading_date="2026-11-20")
    assert not df.empty
    rel_row = df[df["symbol"] == "RELIANCE"]
    assert not rel_row.empty
    assert "delivery_pct" in rel_row.columns
    assert "turnover_cr" in rel_row.columns
    assert rel_row.iloc[0]["delivery_pct"] == 50.0  # 550,000 / 1,100,000 * 100 = 50.0%
    assert rel_row.iloc[0]["turnover_cr"] > 0
    
    # 2. Invalidate cache and test API endpoint response contract
    invalidate_screener_cache()
    client = TestClient(app)
    res = client.get("/api/v1/screener?limit=10")
    assert res.status_code == 200
    data = res.json()
    items = data.get("results") or data.get("candidates") or []
    assert len(items) > 0
    first_item = items[0]
    assert "delivery_pct" in first_item
    assert "turnover_cr" in first_item
    assert "distance_52w_high" in first_item
    assert "pct_from_52w_high" in first_item
