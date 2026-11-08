"""
tests/test_portfolio_backtester.py
Hermetic Unit & Integration Tests for Walk-Forward Portfolio Backtester (Phase 9.0).
Verifies:
1. Point-in-time walk-forward simulation produces valid daily NAV and drawdown curves.
2. Cash solvency: Cash balance never drops below 0.0 at any historical step.
3. Friction drag: Statutory Indian delivery friction (15 bps + ₹15 DP) correctly penalizes returns vs zero-friction baseline.
4. FastAPI endpoints: GET /api/v1/backtest/presets and POST /api/v1/backtest/portfolio.
"""

import os
import json
import sqlite3
import pytest
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.quant.portfolio_backtester import PortfolioBacktester
from src.api.main import app


@pytest.fixture
def backtest_test_db(tmp_path):
    """Hermetic SQLite database fixture with initialized schema and test multi-session data."""
    db_file = tmp_path / "test_backtest.db"
    db_manager = DatabaseManager(str(db_file))
    db_manager.init_schema()

    with db_manager.get_connection() as conn:
        run_all_migrations(conn)

        now_iso = datetime.now(timezone.utc).isoformat()

        # Seed securities
        symbols = [f"TEST_SYM_{i}" for i in range(1, 16)]
        for s in symbols:
            conn.execute("""
                INSERT OR IGNORE INTO securities_master (
                    symbol, company_name, isin, industry, sector, is_active, updated_at
                ) VALUES (?, ?, ?, 'Financials', 'Banking', 1, ?)
            """, (s, f"{s} Ltd", f"INE_{s}", now_iso))

        # Seed 30 trading dates across the symbols
        dates = [f"2026-01-{i:02d}" for i in range(1, 31)]
        for d_idx, d in enumerate(dates):
            # Benchmark NIFTY 50 TRI
            bench_price = 20000.0 * (1.0 + 0.001 * d_idx)
            conn.execute("""
                INSERT INTO index_daily (
                    index_name, trading_date, open, high, low, close, volume, index_type, source, retrieval_timestamp
                ) VALUES ('NIFTY 50', ?, ?, ?, ?, ?, 1000000, 'TRI', 'exchange_official', ?)
            """, (d, bench_price, bench_price + 50, bench_price - 50, bench_price, now_iso))

            # Stock OHLCV and Factor records
            for s_idx, s in enumerate(symbols):
                # Price trend varies by symbol
                base_p = 100.0 * (s_idx + 1)
                daily_drift = (s_idx % 3 - 1) * 0.005  # -0.5%, 0%, +0.5%
                p = base_p * (1.0 + daily_drift * d_idx)
                p = max(5.0, round(p, 2))

                conn.execute("""
                    INSERT INTO ohlcv_daily (
                        symbol, trading_date, open, high, low, close, volume, series,
                        source, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                        retrieval_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, 50000, 'EQ', 'exchange_eod', 'EXCHANGE_OFFICIAL', 0, 1, ?)
                """, (s, d, p, p + 1.0, p - 1.0, p, now_iso))

                conn.execute("""
                    INSERT INTO quant_factors_daily (
                        symbol, trading_date, ret_1d, ret_5d, ret_20d,
                        vol_20d_annualized, roe_pct, debt_to_equity, opm_pct, is_orphaned, updated_at
                    ) VALUES (?, ?, ?, ?, ?, 0.25, 18.0, 0.4, 20.0, 0, ?)
                """, (s, d, 0.01 + s_idx * 0.002, 0.03 + s_idx * 0.005, 0.05 + s_idx * 0.01, now_iso))

        conn.commit()

    return db_manager


def test_walk_forward_point_in_time_simulation(backtest_test_db):
    """Verifies that point-in-time walk-forward simulation produces valid daily NAV and drawdown curves."""
    tester = PortfolioBacktester(backtest_test_db)
    res = tester.run_backtest(
        start_date="2026-01-01",
        end_date="2026-01-30",
        initial_capital=1000000.0,
        top_n=5,
        rebalance_every_n_days=10,
        strategy_mode="BLENDED_20D_60D",
        apply_friction=True
    )

    metrics = res["summary_metrics"]
    equity_curve = res["equity_curve"]
    rebalance_log = res["rebalance_log"]

    # Invariants
    assert metrics["initial_capital"] == 1000000.0
    assert metrics["final_nav"] > 0
    assert metrics["trading_sessions"] == 30
    assert metrics["total_rebalances"] >= 3
    assert len(equity_curve) == 30
    assert len(rebalance_log) >= 3

    # Every point has valid NAV and drawdown
    for pt in equity_curve:
        assert pt["nav"] > 0
        assert pt["strategy_nav"] > 0
        assert pt["strategy_nav"] == pt["nav"]
        assert pt["benchmark_nav"] > 0
        assert pt["drawdown_pct"] <= 0.0  # Drawdown is non-positive
        assert pt["cash"] >= 0.0          # Strictly non-negative cash
        assert pt["cash_balance"] == pt["cash"]

    # Rebalance log has nav
    for r in rebalance_log:
        assert "nav" in r
        assert r["nav"] == r["nav_after"]

    # Alpha is CAGR - Benchmark CAGR
    assert metrics["alpha_pct"] == round(metrics["cagr_pct"] - metrics["benchmark_cagr_pct"], 2)
    assert metrics["rebalance_cadence"] == 10


def test_cash_solvency_and_strict_non_negative_balance(backtest_test_db):
    """Verifies cash never drops below 0.0 at any historical step."""
    tester = PortfolioBacktester(backtest_test_db)
    res = tester.run_backtest(
        start_date="2026-01-01",
        end_date="2026-01-30",
        initial_capital=50000.0,  # Tight capital
        top_n=10,                 # High stock count
        rebalance_every_n_days=5, # Frequent rebalancing
        apply_friction=True
    )

    for pt in res["equity_curve"]:
        assert pt["cash"] >= 0.0, f"Cash balance dropped below 0 on {pt['date']}: {pt['cash']}"


def test_friction_drag_reduces_final_nav(backtest_test_db):
    """Verifies that statutory delivery friction reduces final NAV compared to zero-friction run."""
    tester = PortfolioBacktester(backtest_test_db)

    res_friction = tester.run_backtest(
        start_date="2026-01-01",
        end_date="2026-01-30",
        initial_capital=1000000.0,
        top_n=5,
        rebalance_every_n_days=5,
        apply_friction=True
    )

    res_no_friction = tester.run_backtest(
        start_date="2026-01-01",
        end_date="2026-01-30",
        initial_capital=1000000.0,
        top_n=5,
        rebalance_every_n_days=5,
        apply_friction=False
    )

    friction_paid = res_friction["summary_metrics"]["total_friction_paid"]
    no_friction_paid = res_no_friction["summary_metrics"]["total_friction_paid"]

    assert friction_paid > 0.0
    assert no_friction_paid == 0.0
    assert res_friction["summary_metrics"]["final_nav"] < res_no_friction["summary_metrics"]["final_nav"]


def test_backtest_api_endpoints(backtest_test_db, monkeypatch):
    """Tests FastAPI backtest presets and execution endpoints."""
    monkeypatch.setattr("src.api.routes_backtest.DATABASE_PATH", backtest_test_db.db_path)
    client = TestClient(app)

    # 1. Presets endpoint
    pres_res = client.get("/api/v1/backtest/presets")
    assert pres_res.status_code == 200
    presets = pres_res.json()
    assert "strategy_modes" in presets
    assert len(presets["strategy_modes"]) == 3
    assert "default_config" in presets

    # 2. Portfolio backtest run endpoint (/portfolio and /run alias)
    run_res = client.post("/api/v1/backtest/run", json={
        "start_date": "2026-01-01",
        "end_date": "2026-01-20",
        "initial_capital": 1000000.0,
        "top_n": 5,
        "rebalance_cadence": 10,
        "strategy_mode": "BLENDED_20D_60D"
    })
    assert run_res.status_code == 200
    data = run_res.json()
    assert "summary_metrics" in data
    assert "equity_curve" in data
    assert "rebalance_log" in data
    assert data["summary_metrics"]["final_nav"] > 0
    assert data["summary_metrics"]["rebalance_cadence"] == 10
    assert data["equity_curve"][0]["strategy_nav"] > 0

    # Also test /portfolio backward compatibility
    port_res = client.post("/api/v1/backtest/portfolio", json={
        "start_date": "2026-01-01",
        "end_date": "2026-01-20",
        "initial_capital": 1000000.0,
        "top_n": 5,
        "rebalance_every_n_days": 10,
        "strategy_mode": "TACTICAL_20D"
    })
    assert port_res.status_code == 200
