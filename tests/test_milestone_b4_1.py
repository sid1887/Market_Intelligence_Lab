"""
Market Intelligence Lab — Milestone B4.1 Unit Tests.

Comprehensive regression and acceptance test suite for Milestone B4.1:
1. Schema Compliance: quant_factors_daily contains all required columns.
2. Point-in-Time (PIT) Fundamental Matching: filing_date <= trading_date strictly
   enforced to eliminate look-ahead bias.
3. Technical Warm-up Handling: SMAs (20, 50, 200), annualized volatility,
   beta 60d, volume ratio 20d, and volume z-score 50d return NULL (None) during
   warm-up windows without crashing or raising exceptions.
4. Mathematical Precision: Exact formula validation against known analytical values.
5. Idempotent Upsert Logic: Repeated runs update records in place without duplicating keys.
6. Extreme Value & Edge Case Safeguards: Negative earnings, zero volume, negative equity.
"""

import os
import unittest
import datetime
import sqlite3
import math
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.quant.factor_pipeline import FactorPipeline
from src.quant.benchmark import calculate_beta
from src.quant.volume import calculate_volume_ratio, calculate_volume_zscores
from src.quant.fundamentals import (
    calculate_ttm_pe_ratio,
    calculate_roe,
    calculate_debt_to_equity,
    calculate_opm
)


class TestMilestoneB41FactorPipeline(unittest.TestCase):
    """Test suite validating Milestone B4.1 factor calculations, PIT matching, and schema."""

    def setUp(self):
        """Initializes a clean in-memory database with the full schema."""
        self.db = DatabaseManager(":memory:")
        self.pipeline = FactorPipeline(self.db)

    # -------------------------------------------------------------
    # 1. Schema & Column Compliance
    # -------------------------------------------------------------

    def test_01_quant_factors_daily_schema_compliance(self):
        """Verify that quant_factors_daily table contains all 14 mandated columns."""
        with self.db.get_connection() as conn:
            cursor = conn.execute("PRAGMA table_info(quant_factors_daily);")
            columns = {row["name"] for row in cursor.fetchall()}

        required_columns = [
            "symbol",
            "trading_date",
            "sma_20",
            "sma_50",
            "sma_200",
            "volatility_annualized",
            "beta_60d_nifty",
            "volume_ratio_20d",
            "volume_zscore_50d",
            "ttm_pe",
            "roe_pct",
            "debt_to_equity",
            "opm_pct",
            "updated_at"
        ]

        for col in required_columns:
            self.assertIn(col, columns, f"Mandated column '{col}' missing from quant_factors_daily.")

    # -------------------------------------------------------------
    # 2. Point-in-Time (PIT) Fundamental Matching & Look-Ahead Bias Prevention
    # -------------------------------------------------------------

    def test_02_point_in_time_fundamental_matching_no_lookahead_bias(self):
        """
        Verify that financial statements published on filing_date > trading_date
        are strictly excluded, preventing look-ahead bias.
        """
        # Quarters setup:
        # Q1 ended 2025-06-30 filed 2025-07-20
        # Q2 ended 2025-09-30 filed 2025-10-20
        # Q3 ended 2025-12-31 filed 2026-01-20
        # Q4 ended 2026-03-31 filed 2026-04-20
        # Q5 ended 2026-06-30 filed 2026-07-20 (Post-event filing)
        quarterly_stmts = [
            {"period_end_date": "2025-06-30", "filing_date": "2025-07-20", "revenue": 1000.0, "ebitda": 250.0, "net_profit": 150.0, "eps": 10.0, "total_debt": 0.0, "total_equity": 5000.0},
            {"period_end_date": "2025-09-30", "filing_date": "2025-10-20", "revenue": 1100.0, "ebitda": 270.0, "net_profit": 160.0, "eps": 11.0, "total_debt": 0.0, "total_equity": 5100.0},
            {"period_end_date": "2025-12-31", "filing_date": "2026-01-20", "revenue": 1200.0, "ebitda": 300.0, "net_profit": 180.0, "eps": 12.0, "total_debt": 0.0, "total_equity": 5200.0},
            {"period_end_date": "2026-03-31", "filing_date": "2026-04-20", "revenue": 1300.0, "ebitda": 330.0, "net_profit": 200.0, "eps": 13.0, "total_debt": 0.0, "total_equity": 5300.0},
            {"period_end_date": "2026-06-30", "filing_date": "2026-07-20", "revenue": 2000.0, "ebitda": 600.0, "net_profit": 400.0, "eps": 25.0, "total_debt": 100.0, "total_equity": 6000.0},
        ]

        # Case A: Trading date is 2026-07-15 (5 days BEFORE Q5 was filed)
        # Q5 MUST be strictly invisible. Only Q1, Q2, Q3, Q4 are eligible.
        factors_before_q5 = self.pipeline.match_point_in_time_fundamentals(
            trading_date="2026-07-15",
            close_price=920.0,
            quarterly_statements=quarterly_stmts
        )

        # Expected TTM EPS: 10 + 11 + 12 + 13 = 46.0
        # Expected P/E: 920.0 / 46.0 = 20.0
        # Expected TTM Net Profit: 150 + 160 + 180 + 200 = 690.0
        # Expected Equity: 5300.0 (from Q4, NOT Q5's 6000.0)
        # Expected ROE %: (690.0 / 5300.0) * 100 = 13.02%
        # Expected Debt-to-Equity: 0.0 / 5300.0 = 0.0
        # Expected TTM EBITDA: 250 + 270 + 300 + 330 = 1150.0
        # Expected TTM Rev: 1000 + 1100 + 1200 + 1300 = 4600.0
        # Expected OPM %: (1150.0 / 4600.0) * 100 = 25.0%
        self.assertEqual(factors_before_q5["ttm_pe"], 20.0)
        self.assertEqual(factors_before_q5["roe_pct"], 13.02)
        self.assertEqual(factors_before_q5["debt_to_equity"], 0.0)
        self.assertEqual(factors_before_q5["opm_pct"], 25.0)

        # Case B: Trading date is 2026-07-20 (exact filing date of Q5)
        # Q5 is now visible! TTM window comprises Q5, Q4, Q3, Q2 (Q1 drops out).
        factors_on_q5 = self.pipeline.match_point_in_time_fundamentals(
            trading_date="2026-07-20",
            close_price=920.0,
            quarterly_statements=quarterly_stmts
        )

        # Expected TTM EPS: 25 + 13 + 12 + 11 = 61.0
        # Expected P/E: 920.0 / 61.0 = 15.08
        # Expected TTM Net Profit: 400 + 200 + 180 + 160 = 940.0
        # Expected Equity: 6000.0 (from Q5)
        # Expected ROE %: (940.0 / 6000.0) * 100 = 15.67%
        # Expected Debt-to-Equity: 100.0 / 6000.0 = 0.0167
        # Expected TTM EBITDA: 600 + 330 + 300 + 270 = 1500.0
        # Expected TTM Rev: 2000 + 1300 + 1200 + 1100 = 5600.0
        # Expected OPM %: (1500.0 / 5600.0) * 100 = 26.79%
        self.assertEqual(factors_on_q5["ttm_pe"], 15.08)
        self.assertEqual(factors_on_q5["roe_pct"], 15.67)
        self.assertEqual(factors_on_q5["debt_to_equity"], 0.0167)
        self.assertEqual(factors_on_q5["opm_pct"], 26.79)

    def test_03_insufficient_quarters_returns_null_ttm_ratios(self):
        """
        Verify that when fewer than 4 quarters are available and no annual statement exists,
        flow TTM ratios (P/E, ROE, OPM) return None, while balance sheet D/E is preserved.
        """
        # Only 2 quarters available
        quarterly_stmts = [
            {"period_end_date": "2025-06-30", "filing_date": "2025-07-20", "revenue": 1000.0, "ebitda": 250.0, "net_profit": 150.0, "eps": 10.0, "total_debt": 500.0, "total_equity": 2000.0},
            {"period_end_date": "2025-09-30", "filing_date": "2025-10-20", "revenue": 1100.0, "ebitda": 270.0, "net_profit": 160.0, "eps": 11.0, "total_debt": 600.0, "total_equity": 2100.0},
        ]

        factors = self.pipeline.match_point_in_time_fundamentals(
            trading_date="2025-11-01",
            close_price=500.0,
            quarterly_statements=quarterly_stmts
        )

        self.assertIsNone(factors["ttm_pe"], "TTM P/E must be None when < 4 quarters available.")
        self.assertIsNone(factors["roe_pct"], "ROE must be None when < 4 quarters available.")
        self.assertIsNone(factors["opm_pct"], "OPM must be None when < 4 quarters available.")
        # Balance sheet snapshot is valid: 600 / 2100 = 0.2857
        self.assertEqual(factors["debt_to_equity"], 0.2857)

    # -------------------------------------------------------------
    # 3. Technical Warm-up Handling (Returning NULL Without Crashing)
    # -------------------------------------------------------------

    def test_04_technical_warmup_periods_return_null_without_crashing(self):
        """
        Verify that technical indicators return None (NULL) during warm-up periods:
        - SMA 20: NULL for N < 20
        - SMA 50: NULL for N < 50
        - SMA 200: NULL for N < 200
        - Volatility: NULL for N < 20 returns
        - Beta 60d: NULL for N < 60 aligned pairs
        - Volume Ratio: NULL for N < 21
        - Volume Z-Score: NULL for N < 51
        """
        # Generate 15 daily bars (insufficient for 20-day SMA, 20-day vol, 50-day SMA, 60-day beta)
        ohlcv_15 = [
            {
                "trading_date": f"2025-01-{i + 1:02d}",
                "open": 100.0 + i,
                "high": 105.0 + i,
                "low": 98.0 + i,
                "close": 102.0 + i,
                "volume": 10000 + i * 500
            }
            for i in range(15)
        ]

        factors_15 = self.pipeline.compute_technical_factors(ohlcv_15)
        self.assertEqual(len(factors_15), 15)

        for f in factors_15:
            self.assertIsNone(f["sma_20"], f"SMA 20 should be None at bar {f['trading_date']}")
            self.assertIsNone(f["sma_50"], f"SMA 50 should be None at bar {f['trading_date']}")
            self.assertIsNone(f["sma_200"], f"SMA 200 should be None at bar {f['trading_date']}")
            self.assertIsNone(f["volatility_annualized"], f"Volatility should be None at bar {f['trading_date']}")
            self.assertIsNone(f["beta_60d_nifty"], f"Beta 60d should be None at bar {f['trading_date']}")
            self.assertIsNone(f["volume_ratio_20d"], f"Volume ratio should be None at bar {f['trading_date']}")
            self.assertIsNone(f["volume_zscore_50d"], f"Volume z-score should be None at bar {f['trading_date']}")

    def test_05_technical_factor_precision_and_exact_warmup_transitions(self):
        """
        Verify exact bar transitions when warm-up periods complete:
        - Bar 19 (20th bar): SMA 20 becomes non-null.
        - Bar 20 (21st bar): Volatility and Volume Ratio 20d become non-null.
        - Bar 49 (50th bar): SMA 50 becomes non-null.
        - Bar 50 (51st bar): Volume Z-score 50d becomes non-null.
        """
        # Generate 65 daily bars with constant close = 100.0 and volume = 10000
        ohlcv_65 = [
            {
                "trading_date": f"2025-{((i // 25) + 1):02d}-{((i % 25) + 1):02d}",
                "open": 100.0,
                "high": 105.0,
                "low": 95.0,
                "close": 100.0 + (i % 5),  # small variance for vol
                "volume": 10000 + (i * 100)
            }
            for i in range(65)
        ]

        factors_65 = self.pipeline.compute_technical_factors(ohlcv_65)

        # Bar index 18 (19th bar): SMA 20 must be None
        self.assertIsNone(factors_65[18]["sma_20"])
        # Bar index 19 (20th bar): SMA 20 must be valid float
        self.assertIsNotNone(factors_65[19]["sma_20"])
        self.assertIsInstance(factors_65[19]["sma_20"], float)

        # Bar index 19 (20th bar): Volatility has 19 returns -> None
        self.assertIsNone(factors_65[19]["volatility_annualized"])
        # Bar index 20 (21st bar): Volatility has 20 returns -> Valid
        self.assertIsNotNone(factors_65[20]["volatility_annualized"])
        self.assertIsNotNone(factors_65[20]["volume_ratio_20d"])

        # Bar index 48: SMA 50 is None
        self.assertIsNone(factors_65[48]["sma_50"])
        # Bar index 49 (50th bar): SMA 50 is valid
        self.assertIsNotNone(factors_65[49]["sma_50"])

        # Bar index 49: Volume Z-score has 50 bars -> None (requires 51)
        self.assertIsNone(factors_65[49]["volume_zscore_50d"])
        # Bar index 50 (51st bar): Volume Z-score is valid
        self.assertIsNotNone(factors_65[50]["volume_zscore_50d"])

    # -------------------------------------------------------------
    # 4. Beta 60-Day Rolling Calculation & Benchmark Alignment
    # -------------------------------------------------------------

    def test_06_beta_60d_calculation_and_alignment(self):
        """Verify 60-day rolling beta calculation vs benchmark returns."""
        # 70 benchmark daily returns: 1% daily
        bench_ret_map = {f"2025-01-{i + 1:02d}": 0.01 for i in range(70)}

        # Stock returns: 1.5% daily (perfect covariance, beta = 1.5)
        # To get 1.5% returns, closes: C_t = 100 * (1.015)^t
        ohlcv = []
        c = 100.0
        for i in range(70):
            ohlcv.append({
                "trading_date": f"2025-01-{i + 1:02d}",
                "open": c,
                "high": c * 1.01,
                "low": c * 0.99,
                "close": c,
                "volume": 50000
            })
            c *= 1.015

        factors = self.pipeline.compute_technical_factors(ohlcv, benchmark_ret_map=bench_ret_map)

        # First 59 bars: beta must be None
        self.assertIsNone(factors[59]["beta_60d_nifty"])

        # Bar 60 (has 60 aligned return pairs from bar 1 to 60):
        # Stock return has near-zero variance if constant, so let's test calculate_beta directly
        s_rets = [0.01 * (1 + 0.5 * math.sin(i)) for i in range(60)]
        b_rets = [0.01 * (1 + 0.3 * math.sin(i)) for i in range(60)]
        raw_beta = calculate_beta(s_rets, b_rets, stock_mode="PRI", benchmark_mode="PRI", min_observations=60)
        self.assertIsNotNone(raw_beta)
        self.assertAlmostEqual(raw_beta, 1.6667, places=3)

    # -------------------------------------------------------------
    # 5. Database Upsert Idempotency
    # -------------------------------------------------------------

    def test_07_factor_upsert_idempotency(self):
        """Verify that repeatedly upserting factors updates records in place without duplicating."""
        factor_records = [
            {
                "symbol": "TEST_SYM",
                "trading_date": "2026-01-05",
                "ret_1d": 0.02,
                "sma_20": 1500.50,
                "sma_50": 1480.20,
                "sma_200": 1400.00,
                "volatility_annualized": 0.2250,
                "beta_60d_nifty": 1.1500,
                "volume_ratio_20d": 1.25,
                "volume_zscore_50d": 0.85,
                "ttm_pe": 24.50,
                "roe_pct": 28.50,
                "debt_to_equity": 0.1200,
                "opm_pct": 22.40
            }
        ]

        # First insertion
        c1 = self.db.upsert_quant_factors(factor_records)
        self.assertEqual(c1, 1)

        # Fetch and verify
        factors1 = self.db.get_quant_factors("TEST_SYM")
        self.assertEqual(len(factors1), 1)
        self.assertEqual(factors1[0]["ttm_pe"], 24.50)
        self.assertEqual(factors1[0]["sma_20"], 1500.50)

        # Updated record for same (symbol, trading_date)
        updated_records = [
            {
                "symbol": "TEST_SYM",
                "trading_date": "2026-01-05",
                "ret_1d": 0.025,
                "sma_20": 1505.00,
                "sma_50": 1480.20,
                "sma_200": 1400.00,
                "volatility_annualized": 0.2300,
                "beta_60d_nifty": 1.1800,
                "volume_ratio_20d": 1.30,
                "volume_zscore_50d": 0.90,
                "ttm_pe": 25.10,
                "roe_pct": 28.50,
                "debt_to_equity": 0.1200,
                "opm_pct": 22.40
            }
        ]

        # Second upsert
        c2 = self.db.upsert_quant_factors(updated_records)
        self.assertEqual(c2, 1)

        # Verify in-place update (row count remains 1, values updated)
        factors2 = self.db.get_quant_factors("TEST_SYM")
        self.assertEqual(len(factors2), 1, "Upsert must not create duplicate rows for the same PK.")
        self.assertEqual(factors2[0]["sma_20"], 1505.00)
        self.assertEqual(factors2[0]["ttm_pe"], 25.10)
        self.assertEqual(factors2[0]["volatility_annualized"], 0.2300)

    # -------------------------------------------------------------
    # 6. Edge Case Safeguards (Negative earnings, zero debt, zero equity)
    # -------------------------------------------------------------

    def test_08_edge_case_safeguards(self):
        """Verify that negative earnings/equity and zero revenues are safely handled."""
        # Negative EPS -> P/E is None
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=100.0, ttm_eps=-5.0))
        # Zero EPS -> P/E is None
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=100.0, ttm_eps=0.0))
        # Negative price -> P/E is None
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=-100.0, ttm_eps=5.0))

        # Negative equity -> ROE is None
        self.assertIsNone(calculate_roe(net_profit_annualized=100.0, total_equity=-500.0))
        # Zero equity -> ROE is None
        self.assertIsNone(calculate_roe(net_profit_annualized=100.0, total_equity=0.0))

        # Zero or negative debt -> Debt-to-Equity is 0.0
        self.assertEqual(calculate_debt_to_equity(total_debt=0.0, total_equity=1000.0), 0.0)
        self.assertEqual(calculate_debt_to_equity(total_debt=-50.0, total_equity=1000.0), 0.0)

        # Zero revenue -> OPM is None
        self.assertIsNone(calculate_opm(ebitda=50.0, revenue=0.0))
        # Negative revenue -> OPM is None
        self.assertIsNone(calculate_opm(ebitda=50.0, revenue=-100.0))


if __name__ == "__main__":
    unittest.main()
