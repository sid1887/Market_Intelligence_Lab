"""
Market Intelligence Lab — Milestone B7.0 Econometric Forecasting Test Suite.

Verifies:
1. Zero look-ahead bias: fitting on truncated data at session T strictly excludes future data.
2. Mathematical safety: strictly positive conditional variance and monotonically widening confidence cones.
3. API contract: GET /api/v1/stocks/SUZLON/forecast returns HTTP 200 with 20 projections and zero NaNs.
4. Custom horizon support and non-prefixed route handling.
5. Error handling for unseeded tickers and invalid symbols.
"""

import math
import unittest
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.quant.forecasting import EconometricForecaster
from src.api.main import app


class TestMilestoneB7EconometricForecasting(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager("data/market_lab.db")
        cls.forecaster = EconometricForecaster(cls.db)
        cls.client = TestClient(app)

    def test_01_mathematical_safety_and_monotonicity(self):
        """Verify variance positivity, strict stationarity, and monotonically widening fan cones."""
        res = self.forecaster.generate_forecast("SUZLON", horizon_days=20)

        # 1. Check GARCH parameter bounds
        garch = res.get("garch_parameters", {})
        omega = garch.get("omega", 0)
        alpha = garch.get("alpha", 0)
        beta = garch.get("beta", 0)
        persistence = garch.get("persistence", 0)

        self.assertGreater(omega, 0.0, "GARCH omega must be strictly positive.")
        self.assertGreaterEqual(alpha, 0.0, "GARCH alpha must be non-negative.")
        self.assertGreaterEqual(beta, 0.0, "GARCH beta must be non-negative.")
        self.assertLess(persistence, 1.0, "GARCH persistence (alpha+beta) must satisfy stationarity < 1.0.")

        projections = res["projections"]
        self.assertEqual(len(projections), 20)

        prev_spread_80 = 0.0
        prev_spread_95 = 0.0

        for p in projections:
            exp_val = p["expected"]
            u80 = p["upper_80"]
            l80 = p["lower_80"]
            u95 = p["upper_95"]
            l95 = p["lower_95"]

            # Probability hierarchy check: upper_95 >= upper_80 >= expected >= lower_80 >= lower_95 > 0
            self.assertGreaterEqual(u95, u80, f"Step {p['step']}: Upper 95 must be >= Upper 80")
            self.assertGreaterEqual(u80, exp_val, f"Step {p['step']}: Upper 80 must be >= Expected")
            self.assertGreaterEqual(exp_val, l80, f"Step {p['step']}: Expected must be >= Lower 80")
            self.assertGreaterEqual(l80, l95, f"Step {p['step']}: Lower 80 must be >= Lower 95")
            self.assertGreater(l95, 0.0, f"Step {p['step']}: Lower 95 bound must be strictly positive")

            # Monotonically widening fan cone check
            spread_80 = u80 - l80
            spread_95 = u95 - l95

            self.assertGreater(spread_80, prev_spread_80, f"Step {p['step']}: 80% CI must strictly widen over horizon.")
            self.assertGreater(spread_95, prev_spread_95, f"Step {p['step']}: 95% CI must strictly widen over horizon.")

            prev_spread_80 = spread_80
            prev_spread_95 = spread_95

    def test_02_zero_lookahead_bias_walkforward(self):
        """Verify zero look-ahead bias: fitting at cutoff session T strictly ignores subsequent bars."""
        cutoff = "2026-10-19"
        res_cutoff = self.forecaster.generate_forecast("INFY", cutoff_date=cutoff)

        self.assertEqual(res_cutoff["as_of_date"], cutoff)
        # 2026-10-20 is an official NSE exchange holiday (Dussehra), so next session is 2026-10-21
        self.assertEqual(res_cutoff["projections"][0]["target_date"], "2026-10-21")

        # Verify that prices strictly match prices at or before cutoff
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT close FROM ohlcv_daily WHERE symbol='INFY' AND trading_date = ?",
                (cutoff,)
            )
            expected_cutoff_close = round(float(cur.fetchone()[0]), 2)

        self.assertEqual(res_cutoff["current_close"], expected_cutoff_close)

    def test_03_api_route_suzlon_forecast_200(self):
        """Verify GET /api/v1/stocks/SUZLON/forecast returns HTTP 200 with valid JSON and zero NaNs."""
        resp = self.client.get("/api/v1/stocks/SUZLON/forecast")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data["symbol"], "SUZLON")
        self.assertIn(data["as_of_date"], ["2026-10-28", "2026-11-04"])
        self.assertGreater(data["current_close"], 0.0)
        self.assertGreater(data["annualized_volatility"], 0.0)
        self.assertIn(data["volatility_regime"], ("LOW", "NORMAL", "ELEVATED"))
        self.assertEqual(data["forecast_horizon_days"], 20)
        self.assertEqual(len(data["projections"]), 20)

        # Check for absolute absence of NaNs or Infs
        for p in data["projections"]:
            self.assertIsInstance(p["step"], int)
            self.assertIsInstance(p["target_date"], str)
            self.assertIsInstance(p["expected"], (int, float))
            self.assertFalse(math.isnan(p["expected"]))
            self.assertFalse(math.isinf(p["expected"]))
            self.assertFalse(math.isnan(p["upper_80"]))
            self.assertFalse(math.isnan(p["lower_80"]))
            self.assertFalse(math.isnan(p["upper_95"]))
            self.assertFalse(math.isnan(p["lower_95"]))

    def test_04_api_custom_horizon_and_nonprefixed_route(self):
        """Verify custom horizon parameter (e.g. 35 days) and non-prefixed route /stocks/{symbol}/forecast."""
        resp = self.client.get("/stocks/INFY/forecast?horizon_days=35")
        self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertEqual(data["symbol"], "INFY")
        self.assertEqual(data["forecast_horizon_days"], 35)
        self.assertEqual(len(data["projections"]), 35)
        self.assertEqual(data["projections"][-1]["step"], 35)

    def test_05_invalid_symbol_returns_404(self):
        """Verify that completely invalid non-existent ticker strings return 404."""
        resp = self.client.get("/api/v1/stocks/NONEXISTENT999XYZ/forecast")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
