import os
import pytest
import sqlite3
import datetime
from fastapi.testclient import TestClient
from src.storage.database import DatabaseManager
from src.copilot.mcp_bridge import QuantMCPBridge
from src.api.main import app

def test_ohlcv_daily_series_normalization_and_split_brain(tmp_path):
    db_file = str(tmp_path / "test_truth.db")
    db = DatabaseManager(db_file)

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with db.get_connection() as conn:
        # Insert older row with series = 'EQ'
        conn.execute("""
            INSERT INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("SUZLON", "2026-11-12", "EQ", 38.0, 39.0, 37.5, 38.72, 100000, "NSE", "2026-11-12T16:00:00Z"))

        # Insert newer row with series = '' (empty string simulating legacy or non-EQ series)
        conn.execute("""
            INSERT INTO ohlcv_daily (
                symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, ("SUZLON", "2026-11-18", "", 38.5, 39.5, 38.0, 38.88, 150000, "DYNAMIC", "2026-11-18T16:00:00Z"))
        conn.commit()

    # 1. QuantMCPBridge must pick the newer 38.88 bar even if series was empty
    bridge = QuantMCPBridge(db)
    funds = bridge.get_stock_fundamentals("SUZLON")
    assert funds["current_price"] == 38.88
    assert funds["as_of_date"] == "2026-11-18"

    # 2. Drawdown telemetry must also process without crashing
    telemetry = bridge.get_historical_drawdown_telemetry("SUZLON")
    assert "symbol" in telemetry

    # 3. Running init_schema() normalizes series to 'EQ' without unique constraint failure
    db.init_schema()
    with db.get_connection() as conn:
        row = conn.execute("SELECT series FROM ohlcv_daily WHERE symbol = 'SUZLON' AND trading_date = '2026-11-18'").fetchone()
        assert row is not None
        assert row["series"] == "EQ"


def test_internal_export_state_fundamentals(monkeypatch):
    monkeypatch.setenv("INTERNAL_SYNC_TOKEN", "test-secret-token")
    client = TestClient(app)
    resp = client.get("/api/v1/internal/export-state", headers={"X-Internal-Token": "test-secret-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "latest_fundamentals" in data
    assert isinstance(data["latest_fundamentals"], list)


def test_internal_sync_downstream_orchestration(monkeypatch):
    monkeypatch.setenv("INTERNAL_SYNC_TOKEN", "test-secret-token")
    client = TestClient(app)

    today_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")

    payload = {
        "tournament_summary": {
            "overall_summary": {
                "last_trained_at": today_str,
                "champion_model": "LGBMRegressor_20D_Champion",
                "feature_importance_pct": {
                    "news_sentiment_7d": 0.05,
                    "tactical_20d": 0.15,
                    "trend_60d": 0.20
                }
            },
            "champion_model": "LGBMRegressor_20D_Champion",
            "evaluated_at": today_str
        },
        "ml_forecasts": {
            "RELIANCE": {
                "symbol": "RELIANCE",
                "conviction_score": 85,
                "conviction_tier": "STRONG_ALPHA",
                "forecasts": {
                    "20D": {"expected_return_pct": 4.5, "model": "LGBMRegressor_20D_Champion"}
                }
            }
        },
        "ohlcv_bars": [
            {
                "symbol": "RELIANCE",
                "trading_date": today_str,
                "series": "EQ",
                "open": 2400.0,
                "high": 2450.0,
                "low": 2390.0,
                "close": 2445.0,
                "volume": 2000000
            }
        ],
        "factor_updates": [
            {
                "symbol": "RELIANCE",
                "trading_date": today_str,
                "ret_1d": 0.015,
                "ret_5d": 0.035,
                "ret_20d": 0.05
            }
        ]
    }

    resp = client.post("/api/v1/internal/sync", json=payload, headers={"X-Internal-Token": "test-secret-token"})
    assert resp.status_code == 200
    res_data = resp.json()
    assert res_data["status"] == "synced"
    counts = res_data["counts"]
    assert counts["ohlcv_bars"] == 1
    assert counts["factor_updates"] == 1
    assert counts["ml_forecasts"] == 1
    assert counts.get("rebalance_proposals_generated", 0) >= 0
