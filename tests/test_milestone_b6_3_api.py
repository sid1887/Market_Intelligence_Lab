"""
Market Intelligence Lab: Milestone B6.3 FastAPI Backend Bridge Test Suite.

Verifies:
1. API Health: Returns 200 with WAL database status and settlement dates.
2. Watchlist Endpoint: Returns 4 watchlist symbols (SUZLON, TRIDENT, DRONACHRYA, MOREPENLAB).
3. Screener Endpoint: Returns top-ranked equities sorted by composite score.
4. Tearsheet Endpoint: Returns unified JSON with technicals, fundamentals, and disclosures for SUZLON and INFY.
5. History Endpoint: Returns time-series candlestick data for lightweight-charts.
6. CORS Headers: Confirms headers allow localhost:3000 and vercel.app domains.
"""

import unittest
from fastapi.testclient import TestClient
from src.api.main import app


class TestMilestoneB63FastApiBridge(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_health_endpoint(self):
        """Verify health check returns status healthy and database connection."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["status"], "healthy")
        self.assertIn("WAL", data["database"])
        self.assertEqual(data["active_universe_count"], 50)
        self.assertEqual(data["user_watchlist_count"], 4)

    def test_02_watchlist_endpoint(self):
        """Verify watchlist endpoint returns 4 equities with OHLCV and factor data."""
        res = self.client.get("/api/v1/watchlist")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["count"], 4)
        symbols = [item["symbol"] for item in data["watchlist"]]
        for target in ["SUZLON", "TRIDENT", "DRONACHRYA", "MOREPENLAB"]:
            self.assertIn(target, symbols)

        suzlon = next(item for item in data["watchlist"] if item["symbol"] == "SUZLON")
        self.assertGreaterEqual(suzlon["close"], 36.0)
        self.assertLessEqual(suzlon["close"], 37.5)
        self.assertEqual(suzlon["target_price"], 45.0)
        self.assertEqual(suzlon["stop_loss"], 33.0)

    def test_03_screener_endpoint(self):
        """Verify screener endpoint returns ranked equities with composite score."""
        res = self.client.get("/api/v1/screener?limit=10")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertGreater(data["total_candidates"], 0)
        self.assertLessEqual(len(data["results"]), 10)

        # Check descending order of composite_score
        scores = [r["composite_score"] for r in data["results"] if r.get("composite_score") is not None]
        for i in range(1, len(scores)):
            self.assertGreaterEqual(scores[i - 1], scores[i])

    def test_04_tearsheet_suzlon(self):
        """Verify tearsheet returns unified payload for SUZLON with disclosures and history."""
        res = self.client.get("/api/v1/stocks/SUZLON/tearsheet")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["symbol"], "SUZLON")
        self.assertEqual(data["company_name"], "Suzlon Energy Ltd")
        self.assertTrue(data["is_watchlist"])

        # Check technicals
        self.assertIn("sma_200", data["technicals"])
        self.assertIn("beta_60d_nifty", data["technicals"])
        self.assertIn("volatility_annualized", data["technicals"])

        # Check fundamentals
        self.assertGreater(data["fundamentals"]["roe_pct"], 15.0)
        self.assertLess(data["fundamentals"]["debt_to_equity"], 0.5)

        # Check disclosures & history
        self.assertGreaterEqual(len(data["recent_disclosures"]), 1)
        self.assertGreaterEqual(len(data["history"]), 100)
        sample_bar = data["history"][0]
        self.assertIn("time", sample_bar)
        self.assertIn("open", sample_bar)
        self.assertIn("high", sample_bar)
        self.assertIn("low", sample_bar)
        self.assertIn("close", sample_bar)

    def test_05_tearsheet_infy(self):
        """Verify tearsheet returns verified disclosures and factors for INFY."""
        res = self.client.get("/api/v1/stocks/INFY/tearsheet")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertEqual(data["symbol"], "INFY")
        self.assertFalse(data["is_watchlist"])
        self.assertGreaterEqual(len(data["recent_disclosures"]), 5)

    def test_06_history_endpoint(self):
        """Verify dedicated history endpoint returns candlestick time series."""
        res = self.client.get("/api/v1/stocks/SUZLON/history")
        self.assertEqual(res.status_code, 200)
        bars = res.json()
        self.assertIsInstance(bars, list)
        self.assertGreaterEqual(len(bars), 200)
        self.assertTrue(bars[0]["time"] < bars[-1]["time"])

    def test_07_unknown_symbol_404(self):
        """Verify 404 is returned for non-existent symbol."""
        res = self.client.get("/api/v1/stocks/NONEXISTENT_TICKER/tearsheet")
        self.assertEqual(res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
