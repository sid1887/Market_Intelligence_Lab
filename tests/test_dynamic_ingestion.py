"""
Market Intelligence Lab — Milestone B6.4 Dynamic Ingestion Test Suite.

Verifies:
1. Symbol resolution with valid and invalid NSE symbols.
2. Invariant preservation: Resolving an unseeded stock never mutates index_membership_history (Nifty 50 count remains 50).
3. End-to-end table population: ohlcv_daily (240+ bars, zero nulls), financial statements, disclosures, and factors.
4. FastAPI async contract: GET /tearsheet returns HTTP 202 for unseeded symbols, /status returns progress, and fully populated symbols return HTTP 200.
5. Error handling: Unknown/invalid NSE tickers return HTTP 404.
"""

import unittest
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.client.symbol_resolver import SymbolResolver
from src.pipeline.dynamic_ingestion import DynamicIngestionManager
from src.quant.breadth import MarketBreadthEngine
from src.api.main import app


class TestDynamicIngestionEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager("data/market_lab.db")
        cls.db.init_schema()
        cls.resolver = SymbolResolver(cls.db)
        cls.manager = DynamicIngestionManager(cls.db)
        cls.breadth_engine = MarketBreadthEngine(cls.db)
        cls.client = TestClient(app)

    def test_01_symbol_resolution_valid_and_invalid(self):
        """Tests that valid NSE equities resolve and invalid strings fail."""
        # Valid ticker resolution
        res = self.resolver.resolve_symbol("TATAPOWER")
        self.assertEqual(res["symbol"], "TATAPOWER")
        self.assertEqual(res["isin"], "INE245A01021")
        self.assertEqual(res["is_nifty50"], 0)

        # Invalid ticker resolution must raise ValueError
        with self.assertRaises(ValueError):
            self.resolver.resolve_symbol("NOTANSETICKER999")

    def test_02_nifty50_breadth_invariance(self):
        """Crucial Invariant: Resolving unseeded stocks must never inject into index_membership_history."""
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM index_membership_history WHERE index_name = 'NIFTY 50' AND valid_to IS NULL"
            )
            count_before = cur.fetchone()[0]

        self.assertEqual(count_before, 50, "Pre-condition failed: Nifty 50 constituents must be exactly 50.")

        # Resolve an unseeded equity
        self.resolver.resolve_symbol("RVNL")

        # Verify Nifty 50 membership count is completely unchanged
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM index_membership_history WHERE index_name = 'NIFTY 50' AND valid_to IS NULL"
            )
            count_after = cur.fetchone()[0]

        self.assertEqual(count_after, 50, "INVARIANT VIOLATION: Nifty 50 constituents count was modified!")

        # Verify market breadth calculation remains strictly bounded to 50
        breadth = self.breadth_engine.compute_daily_breadth("2026-10-23")
        self.assertEqual(breadth["expected_constituents_count"], 50)

    def test_03_end_to_end_dynamic_pipeline_execution(self):
        """Tests that ensure_symbol_data populates all tables cleanly."""
        sym = "TATAPOWER"
        success = self.manager.ensure_symbol_data(sym)
        self.assertTrue(success, f"Dynamic ingestion failed for {sym}")

        with self.db.get_connection() as conn:
            # 1. Check securities_master
            cur = conn.execute("SELECT is_active, is_nifty50 FROM securities_master WHERE symbol = ?", (sym,))
            row = cur.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["is_nifty50"], 0)

            # 2. Check ohlcv_daily (at least 240 bars, zero nulls)
            cur = conn.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'", (sym,))
            bars_count = cur.fetchone()[0]
            self.assertGreaterEqual(bars_count, 240)

            # Invariant check: zero nulls, high >= low
            cur = conn.execute(
                """
                SELECT COUNT(*) FROM ohlcv_daily 
                WHERE symbol = ? AND (
                    open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL OR
                    high < low OR high < open OR high < close OR low > open OR low > close
                )
                """,
                (sym,)
            )
            invalid_bars = cur.fetchone()[0]
            self.assertEqual(invalid_bars, 0, "Found invalid OHLCV bars for TATAPOWER.")

            # 3. Check financial_statements_quarterly
            cur = conn.execute("SELECT COUNT(*) FROM financial_statements_quarterly WHERE symbol = ?", (sym,))
            q_count = cur.fetchone()[0]
            self.assertGreaterEqual(q_count, 4)

            # Check assurance status preservation (limited review has is_audited=0)
            cur = conn.execute(
                "SELECT COUNT(*) FROM financial_statements_quarterly WHERE symbol = ? AND is_audited = 0",
                (sym,)
            )
            limited_count = cur.fetchone()[0]
            self.assertGreater(limited_count, 0, "Expected at least one unaudited/limited review quarter.")

            # 4. Check corporate_disclosures
            cur = conn.execute("SELECT COUNT(*) FROM corporate_disclosures WHERE symbol = ?", (sym,))
            disc_count = cur.fetchone()[0]
            self.assertGreaterEqual(disc_count, 2)

            # 5. Check quant_factors_daily
            cur = conn.execute("SELECT COUNT(*) FROM quant_factors_daily WHERE symbol = ?", (sym,))
            factors_count = cur.fetchone()[0]
            self.assertGreaterEqual(factors_count, 240)

            # Latest factor check
            cur = conn.execute(
                "SELECT sma_200, ttm_pe, roe_pct, debt_to_equity FROM quant_factors_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1",
                (sym,)
            )
            latest_factors = cur.fetchone()
            self.assertIsNotNone(latest_factors)
            self.assertIsNotNone(latest_factors["sma_200"])
            self.assertGreater(latest_factors["sma_200"], 0)

    def test_04_api_tearsheet_and_status_polling(self):
        """Tests that API returns 200 for ready stock, 202 for newly discovered stock, and status polling works."""
        # 1. Existing ready stock (e.g. SUZLON) returns 200 OK
        resp_ready = self.client.get("/api/v1/stocks/SUZLON/tearsheet")
        self.assertEqual(resp_ready.status_code, 200)
        json_ready = resp_ready.json()
        self.assertEqual(json_ready["symbol"], "SUZLON")
        self.assertIn("latest_ohlcv", json_ready)
        self.assertIn("technicals", json_ready)
        self.assertIn("history", json_ready)

        # 2. Status polling endpoint for ready stock
        resp_status = self.client.get("/api/v1/stocks/SUZLON/status")
        self.assertEqual(resp_status.status_code, 200)
        self.assertEqual(resp_status.json()["status"], "READY")

        # 3. Newly discovered unseeded stock (e.g. CANBK) returns 202 Accepted
        with self.db.get_connection() as conn:
            conn.execute("PRAGMA foreign_keys = OFF;")
            for table in [
                'quant_factors_daily',
                'fundamental_factors_daily',
                'company_financial_statements',
                'equity_news_feed',
                'ohlcv_daily',
                'financial_statements_quarterly',
                'financial_statements_annual',
                'corporate_disclosures',
                'securities_master'
            ]:
                try:
                    conn.execute(f"DELETE FROM {table} WHERE symbol = 'CANBK'")
                except Exception:
                    pass
            conn.execute("PRAGMA foreign_keys = ON;")

        from src.pipeline.dynamic_ingestion import _INGESTION_STATE
        _INGESTION_STATE.pop("CANBK", None)

        resp_unseeded = self.client.get("/api/v1/stocks/CANBK/tearsheet")
        self.assertEqual(resp_unseeded.status_code, 202)
        json_unseeded = resp_unseeded.json()
        self.assertEqual(json_unseeded["status"], "INGESTING")
        self.assertEqual(json_unseeded["symbol"], "CANBK")
        self.assertIn("progress_pct", json_unseeded)

        # Status endpoint returns INGESTING or READY
        resp_canbk_status = self.client.get("/api/v1/stocks/CANBK/status")
        self.assertEqual(resp_canbk_status.status_code, 200)
        self.assertIn(resp_canbk_status.json()["status"], ("INGESTING", "READY"))

    def test_05_api_invalid_ticker_returns_404(self):
        """Tests that non-existent/invalid tickers return 404."""
        resp = self.client.get("/api/v1/stocks/NONEXISTENT999XYZ/tearsheet")
        self.assertEqual(resp.status_code, 404)
        self.assertIn("not found", resp.json()["detail"].lower())


if __name__ == "__main__":
    unittest.main()
