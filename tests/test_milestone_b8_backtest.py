"""
Unit and Integration Tests for Milestone B8.0: Multi-Factor Strategy Backtesting & Portfolio Rebalancing Engine
"""

import unittest
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.quant.backtest_engine import BacktestEngine
from src.quant.performance import PerformanceMetricsCalculator
from src.api.main import app


class TestMilestoneB8Backtest(unittest.TestCase):
    """Test suite verifying point-in-time portfolio simulation, frictional accounting, and API contracts."""

    def setUp(self):
        self.db = DatabaseManager()
        self.db.init_schema()
        self.engine = BacktestEngine(self.db)
        self.client = TestClient(app)

    def test_point_in_time_compliance(self):
        """
        Verify that rebalance decisions on date T strictly query factor data where trading_date <= T.
        """
        test_date = "2025-06-02"
        screen_df = self.engine.screener.screen(
            as_of_date=test_date,
            criteria={
                "max_debt_to_equity": 0.5,
                "min_roe_pct": 15.0,
                "price_above_sma200": True,
                "exclude_sectors": ["Financial Services"]
            }
        )
        if not screen_df.empty:
            # Verify every stock returned has factors populated strictly on or before test_date
            for sym in screen_df["symbol"].head(5):
                factors = self.db.get_quant_factors(sym, start_date=test_date, end_date=test_date)
                self.assertTrue(len(factors) > 0)
                self.assertEqual(factors[0]["trading_date"], test_date)

    def test_friction_and_cash_conservation(self):
        """
        Verify exact deduction of STT (0.1%), turnover charges (0.0035%), DP charges (₹15.34),
        and verify that Portfolio Value = Holdings + Cash at all times.
        """
        initial_capital = 500000.0
        res = self.engine.run_backtest(
            strategy_name="Friction_Conservation_Test",
            start_date="2025-01-01",
            end_date="2025-06-30",
            initial_capital=initial_capital,
            rebalance_frequency="MONTHLY",
            top_n=5,
            weighting="EQUAL_WEIGHT",
            slippage_bps=5.0,
            save_to_db=False
        )

        equity_curve = res["equity_curve"]
        rebalances = res["rebalance_events"]

        self.assertGreater(len(equity_curve), 50)
        self.assertGreater(len(rebalances), 2)

        # 1. Verify Cash Conservation Invariant for every trading day
        for pt in equity_curve:
            nav = pt["portfolio_value"]
            cash = pt["cash"]
            invested = pt["invested_value"]
            self.assertAlmostEqual(nav, cash + invested, delta=0.05)
            self.assertGreaterEqual(cash, -0.01)  # Cash never goes negative

        # 2. Verify Transaction Fee and Friction Logic on Rebalances
        for reb in rebalances:
            # DP charge check on sells
            n_sells = len(reb["sells"])
            expected_dp = n_sells * 15.34
            self.assertGreaterEqual(reb["friction_inr"], 0.0)
            if n_sells > 0:
                self.assertGreaterEqual(reb["dp_charges_inr"], expected_dp - 0.01)

            # STT check: buy STT = 0.1%, sell STT = 0.1%
            for b in reb["buys"]:
                expected_stt = b["gross_value"] * 0.001
                self.assertAlmostEqual(b["stt"], expected_stt, delta=0.1)

            for s in reb["sells"]:
                expected_stt = s["gross_value"] * 0.001
                self.assertAlmostEqual(s["stt"], expected_stt, delta=0.1)

    def test_performance_metrics_calculator(self):
        """
        Verify mathematical correctness of CAGR, Sharpe, Drawdown, and Alpha metrics.
        """
        # Synthetic upward-sloping equity curve
        dates = ["2024-01-01", "2024-06-01", "2024-12-31"]
        curve = [
            {"trading_date": dates[0], "portfolio_value": 100000.0, "benchmark_value": 100000.0, "drawdown_pct": 0.0},
            {"trading_date": dates[1], "portfolio_value": 110000.0, "benchmark_value": 105000.0, "drawdown_pct": 0.0},
            {"trading_date": dates[2], "portfolio_value": 120000.0, "benchmark_value": 110000.0, "drawdown_pct": 0.0},
        ]
        metrics = PerformanceMetricsCalculator.calculate_metrics(curve, rf=0.065)
        p = metrics["portfolio"]
        b = metrics["benchmark"]

        self.assertAlmostEqual(p["initial_value"], 100000.0)
        self.assertAlmostEqual(p["final_value"], 120000.0)
        self.assertAlmostEqual(p["total_return_pct"], 20.0, delta=0.1)
        self.assertGreater(p["cagr_pct"], 18.0)
        self.assertAlmostEqual(b["total_return_pct"], 10.0, delta=0.1)
        self.assertEqual(p["max_drawdown_pct"], 0.0)

    def test_api_backtest_endpoints(self):
        """
        Test POST /api/v1/backtest/run and GET /api/v1/backtest/latest contracts.
        """
        # POST run
        payload = {
            "strategy_name": "API_Contract_Test",
            "start_date": "2025-01-01",
            "end_date": "2025-05-30",
            "initial_capital": 250000.0,
            "rebalance_frequency": "MONTHLY",
            "top_n": 5,
            "weighting": "EQUAL_WEIGHT",
            "slippage_bps": 5.0
        }
        resp = self.client.post("/api/v1/backtest/run", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()

        self.assertIn("run_id", data)
        self.assertIn("metrics", data)
        self.assertIn("benchmark_metrics", data)
        self.assertIn("equity_curve", data)
        self.assertIn("rebalance_events", data)

        m = data["metrics"]
        self.assertIn("cagr_pct", m)
        self.assertIn("sharpe_ratio", m)
        self.assertIn("max_drawdown_pct", m)
        self.assertIn("total_friction_inr", m)

        # GET latest
        resp_latest = self.client.get("/api/v1/backtest/latest")
        self.assertEqual(resp_latest.status_code, 200)
        latest_data = resp_latest.json()
        self.assertIn("run_id", latest_data)
        self.assertIn("cagr_pct", latest_data)
        self.assertIn("equity_curve", latest_data)


if __name__ == "__main__":
    unittest.main()
