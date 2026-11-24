"""
tests/test_phase6_ui_endpoints.py
Unit and integration tests for MIL 2.0 Phase 6 UI and quantitative endpoints:
1. GET /api/v1/models/tournament
2. GET /api/v1/portfolio/trader-dna
3. Compact tournament summary moments verification (< 15 KB)
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.utils import DATABASE_PATH
from src.storage.database import DatabaseManager


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_compact_tournament_summary_size_and_moments():
    """Confirms tournament_summary.json is compact (< 15 KB) and contains exact moments without raw returns arrays."""
    p = Path("data/models/tournament_summary.json")
    assert p.exists(), "tournament_summary.json must exist"
    
    size_kb = p.stat().st_size / 1024.0
    assert size_kb < 15.0, f"tournament_summary.json size ({size_kb:.2f} KB) must be < 15 KB"

    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Invariants
    assert "baseline" in data
    assert "candidates" in data
    assert "champion" in data
    assert "returns" not in data.get("baseline", {}), "Raw returns array must NOT be present in baseline"

    base = data["baseline"]
    for moment in ["mean_return", "std_return", "skewness", "excess_kurtosis", "p05_return", "p50_return", "p95_return", "mean_net_sharpe"]:
        assert moment in base, f"Moment {moment} missing from baseline"

    for cand in data["candidates"]:
        assert "returns" not in cand, "Raw returns array must NOT be present in candidate"
        for moment in ["mean_return", "std_return", "skewness", "excess_kurtosis", "cpcv_mean_sharpe", "deflated_sharpe_ratio", "promotion_status"]:
            assert moment in cand, f"Moment {moment} missing from candidate {cand.get('candidate_id')}"


def test_get_models_tournament_endpoint(client):
    """Verifies GET /api/v1/models/tournament returns champion status, baseline, and candidate metrics."""
    res = client.get("/api/v1/models/tournament")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    body = res.json()
    assert body["status"] == "SUCCESS"
    assert "active_champion" in body
    assert "baseline" in body
    assert "candidates" in body
    assert "promotion_verdict" in body
    assert body["promotion_verdict"] in ("CHAMPION_PROMOTED", "REJECTED_BELOW_BASELINE")


def test_get_portfolio_trader_dna_endpoint(client):
    """Verifies GET /api/v1/portfolio/trader-dna returns behavioral discipline and DP fee metrics."""
    res = client.get("/api/v1/portfolio/trader-dna")
    assert res.status_code == 200, f"Expected 200, got {res.status_code}: {res.text}"
    body = res.json()
    
    # Required Phase 6 keys
    required_keys = [
        "win_rate_pct",
        "median_hold_days",
        "early_exit_rate_pct",
        "consecutive_losses",
        "cooldown_active",
        "size_multiplier",
        "total_trades",
        "total_dp_charges",
        "total_trade_taxes",
        "total_friction",
        "realized_gross_pnl",
        "realized_net_pnl",
        "fee_drag_pct",
    ]
    for key in required_keys:
        assert key in body, f"Key '{key}' missing from trader-dna response"

    assert isinstance(body["cooldown_active"], bool)
    assert isinstance(body["size_multiplier"], (int, float))
    assert body["size_multiplier"] in (0.5, 1.0)
