"""
Market Intelligence Lab — Milestone B6.4.1 Verification Test Suite.
Tests API NaN / Infinity JSON serialization, Route Handling, and Status Polling.

Verifies:
1. sanitize_for_json converts NaN, Infinity, -Infinity, np.nan, and DataFrames to valid JSON nulls.
2. /api/v1/screener with mocked factors containing NaN/Infinity/None returns HTTP 200 with null values.
3. /api/v1/screener?limit=54 on real database returns HTTP 200 with clean JSON (no ValueError: nan).
4. GET /api/v1/stocks/TATAPOWER/status returns HTTP 200 with status READY (not 404).
5. GET /api/v1/stocks/UNKNOWN_XYZ/status returns HTTP 200 with status NOT_STARTED (not 404).
6. GET /stocks/TATAPOWER/status (route without /api/v1) returns HTTP 200.
7. DynamicIngestionManager._active_jobs status retrieval during active jobs.
"""

import json
import math
import unittest
from unittest.mock import patch
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from src.api.main import app
from src.api.utils import sanitize_for_json, safe_float, safe_int
from src.pipeline.dynamic_ingestion import DynamicIngestionManager


class TestApiNanHandlingAndRoutes(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    def test_01_sanitize_for_json_unit(self):
        """Verify sanitize_for_json recursively converts NaN, Inf, and DataFrames to None."""
        raw_payload = {
            "normal_float": 12.34,
            "nan_val": float("nan"),
            "inf_val": float("inf"),
            "neg_inf_val": float("-inf"),
            "np_nan": np.nan,
            "nested_dict": {
                "inner_nan": float("nan"),
                "inner_list": [1.0, float("inf"), np.nan, 4.0]
            },
            "dataframe": pd.DataFrame({
                "col_a": [1.0, np.nan, float("inf")],
                "col_b": ["x", None, "z"]
            })
        }

        sanitized = sanitize_for_json(raw_payload)

        # Standard json.dumps must not raise ValueError
        encoded = json.dumps(sanitized)
        decoded = json.loads(encoded)

        self.assertEqual(decoded["normal_float"], 12.34)
        self.assertIsNone(decoded["nan_val"])
        self.assertIsNone(decoded["inf_val"])
        self.assertIsNone(decoded["neg_inf_val"])
        self.assertIsNone(decoded["np_nan"])
        self.assertIsNone(decoded["nested_dict"]["inner_nan"])
        self.assertIsNone(decoded["nested_dict"]["inner_list"][1])
        self.assertIsNone(decoded["nested_dict"]["inner_list"][2])
        self.assertEqual(decoded["nested_dict"]["inner_list"][0], 1.0)

        df_records = decoded["dataframe"]
        self.assertIsNone(df_records[1]["col_a"])
        self.assertIsNone(df_records[2]["col_a"])
        self.assertIsNone(df_records[1]["col_b"])

    def test_02_screener_mocked_nan_and_infinity(self):
        """Verify calling /api/v1/screener with mocked factors containing NaN/Inf returns HTTP 200 with null values."""
        mock_df = pd.DataFrame([
            {
                "symbol": "MOCK_NAN",
                "company_name": "Mock NaN Corp",
                "sector": "Technology",
                "close": float("nan"),
                "sma_200": float("inf"),
                "debt_to_equity": float("-inf"),
                "roe_pct": np.nan,
                "opm_pct": None,
                "excess_ret_20d": np.nan,
                "composite_score": float("nan"),
                "price_above_sma200": False,
                "is_watchlist": 0
            },
            {
                "symbol": "MOCK_CLEAN",
                "company_name": "Mock Clean Corp",
                "sector": "Energy",
                "close": 150.0,
                "sma_200": 140.0,
                "debt_to_equity": 0.25,
                "roe_pct": 18.5,
                "opm_pct": 22.0,
                "excess_ret_20d": 0.05,
                "composite_score": 85.0,
                "price_above_sma200": True,
                "is_watchlist": 1
            }
        ])

        with patch("src.quant.screener.FactorScreener.screen", return_value=mock_df):
            resp = self.client.get("/api/v1/screener?limit=10")
            self.assertEqual(resp.status_code, 200)

            # Ensure valid JSON without ValueError: nan
            data = resp.json()
            self.assertEqual(data["returned_count"], 2)

            nan_stock = next(r for r in data["results"] if r["symbol"] == "MOCK_NAN")
            self.assertIsNone(nan_stock["close"])
            self.assertIsNone(nan_stock["sma_200"])
            self.assertIsNone(nan_stock["debt_to_equity"])
            self.assertIsNone(nan_stock["roe_pct"])
            self.assertIsNone(nan_stock["opm_pct"])
            self.assertIsNone(nan_stock["excess_ret_20d"])
            self.assertIsNone(nan_stock["composite_score"])

            clean_stock = next(r for r in data["results"] if r["symbol"] == "MOCK_CLEAN")
            self.assertEqual(clean_stock["close"], 150.0)
            self.assertEqual(clean_stock["roe_pct"], 18.5)

    def test_03_screener_real_database_limit_54(self):
        """Verify calling /api/v1/screener?limit=54 on actual database returns HTTP 200 without NaN serialization crash."""
        resp = self.client.get("/api/v1/screener?limit=54")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(data["returned_count"], 50)
        self.assertIn("results", data)

        # Check that IDEA or other stocks with null factors have valid None/null values
        for item in data["results"]:
            self.assertIsInstance(item["symbol"], str)
            # Ensure none of the values are float('nan') or float('inf')
            for k, v in item.items():
                if isinstance(v, float):
                    self.assertFalse(math.isnan(v), f"Unsanitized NaN in {item['symbol']} -> {k}")
                    self.assertFalse(math.isinf(v), f"Unsanitized Inf in {item['symbol']} -> {k}")

    def test_04_tatapower_status_returns_200(self):
        """Verify GET /api/v1/stocks/TATAPOWER/status returns HTTP 200 with status READY (not 404)."""
        resp = self.client.get("/api/v1/stocks/TATAPOWER/status")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "READY")
        self.assertEqual(payload["symbol"], "TATAPOWER")
        self.assertEqual(payload["progress_pct"], 100)
        self.assertIn("detail", payload)

    def test_05_unknown_status_returns_200_not_started(self):
        """Verify GET /api/v1/stocks/UNKNOWN_XYZ/status returns HTTP 200 with NOT_STARTED (never 404)."""
        resp = self.client.get("/api/v1/stocks/UNKNOWN_XYZ/status")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "NOT_STARTED")
        self.assertEqual(payload["symbol"], "UNKNOWN_XYZ")
        self.assertEqual(payload["progress_pct"], 0)

    def test_06_route_without_prefix_returns_200(self):
        """Verify GET /stocks/{symbol}/status (without /api/v1) returns HTTP 200."""
        resp = self.client.get("/stocks/TATAPOWER/status")
        self.assertEqual(resp.status_code, 200)
        payload = resp.json()
        self.assertEqual(payload["status"], "READY")

    def test_07_active_ingestion_job_status(self):
        """Verify that when an ingestion job is active in _active_jobs, its progress dict is returned."""
        test_sym = "MOCK_INGEST_SYM"
        DynamicIngestionManager.update_ingestion_status(
            test_sym,
            status="INGESTING",
            progress_pct=45,
            step="BACKFILLING_OHLCV",
            detail="Mock backfill in progress..."
        )

        try:
            resp = self.client.get(f"/api/v1/stocks/{test_sym}/status")
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertEqual(data["status"], "INGESTING")
            self.assertEqual(data["progress_pct"], 45)
            self.assertEqual(data["step"], "BACKFILLING_OHLCV")
        finally:
            DynamicIngestionManager._active_jobs.pop(test_sym, None)


if __name__ == "__main__":
    unittest.main()
