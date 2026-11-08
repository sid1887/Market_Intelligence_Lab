"""
Hermetic test suite for Advanced Risk Regimes, Turnover Hysteresis,
Cash Hurdle Accrual, and Multi-Asset Comparison Engine.
"""

import json
from pathlib import Path
import pytest
from starlette.testclient import TestClient

from src.storage.database import DatabaseManager
from src.quant.portfolio_backtester import PortfolioBacktester
from src.api.main import app

DB_PATH = Path("data/market_lab.db")


@pytest.fixture
def backtester():
    db_manager = DatabaseManager(str(DB_PATH))
    return PortfolioBacktester(db_manager=db_manager)


@pytest.fixture
def api_client():
    return TestClient(app)


def test_turnover_hysteresis_reduces_churn(backtester):
    """
    Pillar 1: Verify turnover hysteresis buffer (5.0 percentile inertia)
    reduces rebalance turnover and total transaction friction relative to no hysteresis.
    """
    start_date = "2024-10-21"
    end_date = "2025-10-21"

    # Run without hysteresis
    res_no_hyst = backtester.run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=1000000,
        top_n=15,
        rebalance_cadence=20,
        strategy_mode="BLENDED_20D_60D",
        hysteresis_buffer=0.0,
        enable_dynamic_cash=False,
    )

    # Run with hysteresis
    res_with_hyst = backtester.run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=1000000,
        top_n=15,
        rebalance_cadence=20,
        strategy_mode="BLENDED_20D_60D",
        hysteresis_buffer=5.0,
        enable_dynamic_cash=False,
    )

    friction_no_hyst = res_no_hyst["summary_metrics"]["total_friction_paid"]
    friction_with_hyst = res_with_hyst["summary_metrics"]["total_friction_paid"]
    trades_no_hyst = res_no_hyst["summary_metrics"]["total_trades"]
    trades_with_hyst = res_with_hyst["summary_metrics"]["total_trades"]

    # Hysteresis must strictly reduce or maintain trade count and friction
    assert trades_with_hyst <= trades_no_hyst, (
        f"Hysteresis should reduce or match trade count: {trades_with_hyst} vs {trades_no_hyst}"
    )
    assert friction_with_hyst <= friction_no_hyst, (
        f"Hysteresis should reduce friction: {friction_with_hyst} vs {friction_no_hyst}"
    )


def test_market_breadth_and_dynamic_cash(backtester):
    """
    Pillar 2: Verify market breadth gating dynamically adjusts cash reserves
    and scales target weights without violating solvency.
    """
    start_date = "2022-01-03"
    end_date = "2022-12-30"

    res = backtester.run_backtest(
        start_date=start_date,
        end_date=end_date,
        initial_capital=1000000,
        top_n=15,
        rebalance_cadence=20,
        strategy_mode="BLENDED_20D_60D",
        hysteresis_buffer=5.0,
        enable_dynamic_cash=True,
        cash_hurdle_rate=0.065,
    )

    # Check rebalance log entries for breadth and cash allocation
    reb_logs = res["rebalance_log"]
    assert len(reb_logs) > 0, "Should have executed multiple rebalance cycles"

    breadth_seen = [r.get("market_breadth") for r in reb_logs if r.get("market_breadth") is not None]
    assert len(breadth_seen) > 0, "Rebalance log must capture market breadth"

    # In 2022 rate hike regime, breadth should drop below 50% at least once
    has_defensive_cash = any(r.get("target_cash_pct", 0) > 0 for r in reb_logs)
    assert has_defensive_cash, "2022 correction should have triggered defensive cash allocation"

    # All cash balances must remain non-negative
    for pt in res["equity_curve"]:
        cash_bal = pt.get("cash_balance", 0.0) if isinstance(pt, dict) else pt.cash_balance
        assert cash_bal >= -1e-6, f"Cash solvency violated on {pt.get('trading_date')}: {cash_bal}"


def test_cash_hurdle_rate_yield_accrual(backtester):
    """
    Pillar 2: Verify unallocated cash earns daily overnight repo yield (6.5% p.a.).
    """
    res = backtester.run_backtest(
        start_date="2024-10-21",
        end_date="2025-04-21",
        initial_capital=1000000,
        top_n=10,
        rebalance_cadence=20,
        strategy_mode="BLENDED_20D_60D",
        hysteresis_buffer=5.0,
        enable_dynamic_cash=True,
        cash_hurdle_rate=0.065,
    )

    # Total cash yield earned must be strictly positive
    total_yield = res["summary_metrics"].get("cash_yield_earned", 0.0)
    assert total_yield is not None and total_yield > 0, f"Expected positive cash yield, got {total_yield}"


def test_multi_stock_comparison_endpoint(api_client):
    """
    Pillar 4: Verify POST /api/v1/backtest/compare returns normalized base-100 series,
    metrics, symmetric correlation matrix, and radar scores.
    """
    payload = {
        "symbols": ["TCS", "INFY", "HCLTECH"],
        "start_date": "2024-01-01",
        "end_date": "2025-01-01",
        "benchmark_symbol": "BENCHMARK",
    }
    response = api_client.post("/api/v1/backtest/compare", json=payload)
    assert response.status_code == 200, f"Compare failed: {response.text}"

    data = response.json()
    assert data["start_date"] == "2024-01-01"
    assert data["end_date"] == "2025-01-01"
    assert set(data["symbols"]) == {"TCS", "INFY", "HCLTECH"}

    # Series verification
    series = data["normalized_series"]
    assert len(series) > 100, f"Expected > 100 trading sessions, got {len(series)}"
    first_pt = series[0]
    assert "trading_date" in first_pt
    assert "BENCHMARK" in first_pt
    assert pytest.approx(first_pt["BENCHMARK"], abs=1.0) == 100.0

    # Metrics verification
    metrics = data["comparison_metrics"]
    for sym in ["TCS", "INFY", "HCLTECH", "BENCHMARK"]:
        assert sym in metrics
        m = metrics[sym]
        assert "cagr_pct" in m
        assert "sharpe_ratio" in m
        assert "max_drawdown_pct" in m
        assert "beta_to_bench" in m

    # Correlation matrix verification
    matrix = data["correlation_matrix"]
    for s1 in ["TCS", "INFY", "HCLTECH"]:
        assert s1 in matrix
        assert pytest.approx(matrix[s1][s1], abs=0.01) == 1.0
        for s2 in ["TCS", "INFY", "HCLTECH"]:
            # Matrix must be symmetric
            assert pytest.approx(matrix[s1][s2], abs=0.01) == matrix[s2][s1]

    # Radar scores verification
    radar = data["radar_scores"]
    for sym in ["TCS", "INFY", "HCLTECH"]:
        assert sym in radar
        assert 0 <= radar[sym]["quality"] <= 100
        assert 0 <= radar[sym]["momentum"] <= 100
        assert 0 <= radar[sym]["trend"] <= 100
        assert 0 <= radar[sym]["volatility"] <= 100


def test_tournament_summary_artifacts():
    """
    Pillar 3: Verify tournament summary artifact exists and contains valid
    4-fold evaluation metrics for both 20D and 60D models.
    """
    summary_path = Path("data/models/tournament_summary.json")
    assert summary_path.exists(), "tournament_summary.json must exist in data/models/"

    with open(summary_path, "r") as f:
        summary = json.load(f)

    assert "folds" in summary
    assert len(summary["folds"]) == 4, "Must contain exactly 4 walk-forward folds"
    assert "overall_summary" in summary

    overall = summary["overall_summary"]
    assert "tactical_20d" in overall
    assert "trend_60d" in overall
    assert "feature_importance_pct" in overall

    t20 = overall["tactical_20d"]
    assert "champion" in t20
    assert "champion_ic" in t20
    assert t20["champion_ic"] > 0

    t60 = overall["trend_60d"]
    assert "champion" in t60
    assert "champion_ic" in t60
    assert t60["champion_ic"] > 0

    feat_imp = overall["feature_importance_pct"]
    assert len(feat_imp) > 0
    assert "rsi_14" in feat_imp


def test_load_tournament_weights_normalization():
    """
    P1: Verify load_tournament_weights dynamically extracts and normalizes consensus weights
    from data/models/tournament_summary.json, and gracefully falls back on missing paths.
    """
    from src.quant.rebalance_engine import load_tournament_weights, DEFAULT_TOURNAMENT_WEIGHTS

    weights = load_tournament_weights("data/models/tournament_summary.json")
    assert isinstance(weights, dict)
    assert len(weights) >= 6

    # Normalization invariant: sum of weights == 1.0
    assert pytest.approx(sum(weights.values()), abs=1e-4) == 1.0

    # Key features must be present
    for feat in ["rsi_14", "volatility_20d", "momentum_20d", "momentum_252d", "sma_ratio_50_200"]:
        assert feat in weights
        assert weights[feat] > 0

    # Fallback verification on missing path
    fallback_w = load_tournament_weights("data/models/non_existent_file.json")
    assert fallback_w == DEFAULT_TOURNAMENT_WEIGHTS
    assert pytest.approx(sum(fallback_w.values()), abs=1e-4) == 1.0


def test_screener_api_standardized_payload(api_client):
    """
    P1: Verify GET /api/v1/screener?limit=10 outputs standardized JSON response
    with trading_date, total_candidates, and candidates array containing 10 objects.
    """
    res = api_client.get("/api/v1/screener?limit=10")
    assert res.status_code == 200, f"Screener request failed: {res.text}"

    data = res.json()
    assert "trading_date" in data
    assert "total_candidates" in data
    assert "candidates" in data
    assert isinstance(data["candidates"], list)
    assert len(data["candidates"]) == 10

    first = data["candidates"][0]
    required_fields = [
        "symbol",
        "blended_score",
        "score_20d",
        "score_60d",
        "target_allocation_pct",
        "rsi_14",
        "volatility_20d",
    ]
    for field in required_fields:
        assert field in first, f"Missing required field {field} in screener candidate payload"

