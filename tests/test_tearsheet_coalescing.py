import pytest
import sqlite3
from fastapi.testclient import TestClient
from src.api.main import app

def test_bse_tearsheet_fundamentals_coalescing():
    client = TestClient(app)
    response = client.get("/api/v1/stocks/BSE/tearsheet")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "BSE"

    # Fundamentals should be non-null real numbers, not None
    fundamentals = data.get("fundamentals", {})
    assert fundamentals.get("roe_pct") is not None
    assert fundamentals.get("roe_pct") > 20.0
    assert fundamentals.get("debt_to_equity") is not None
    assert fundamentals.get("ttm_pe") is not None
    assert fundamentals.get("opm_pct") is not None

    # Technicals volatility and beta should be non-null
    technicals = data.get("technicals", {})
    assert technicals.get("volatility_annualized") is not None
    assert technicals.get("beta_60d_nifty") is not None

    # ML Forecast and Catalyst should be attached
    assert "ml_forecast" in data
    assert "catalyst" in data
