import unittest
import math
from src.storage.database import DatabaseManager
from src.quant.alignment import AlignedSeries
from src.quant.benchmark import (
    calculate_excess_return,
    calculate_beta,
    calculate_split_bonus_adjustment_factors,
    ReturnModeMismatchError,
    BenchmarkMode
)
from src.quant.volume import (
    calculate_volume_ratio,
    calculate_volume_zscores,
    adjust_volume_for_corporate_actions,
    evaluate_volume_anomalies
)
from src.quant.breadth import MarketBreadthEngine
from src.quant.relative_strength import RelativeStrengthEngine

class TestMilestone22(unittest.TestCase):
    """
    Exhaustive regression test suite for Milestone 2.2:
    - Exact date alignment and synthetic beta verification
    - Market breadth coverage accounting (no silent zeros)
    - Moving average warm-up and restricted window flags
    - Corporate-action adjusted price and volume series
    - Strict Mode 1 (PRI) and Mode 2 (TRI) completeness checks
    - Volume ratio and Z-score edge cases (zero-variance, warm-up, outliers)
    """

    def setUp(self):
        self.db = DatabaseManager(":memory:")

    def test_synthetic_beta_known_outcomes(self):
        """
        Mandatory Condition 4:
        Test beta calculations on synthetic datasets with exact known analytical outcomes.
        """
        # Baseline benchmark returns
        b_rets = [0.01, -0.015, 0.02, 0.005, -0.008, 0.012, -0.018, 0.025, -0.01, 0.004] * 6  # 60 obs

        # Synthetic Case 1: Stock has exact beta = 1.5, alpha = 0
        s_rets_15 = [1.5 * b for b in b_rets]
        beta_15 = calculate_beta(s_rets_15, b_rets, "PRI", "PRI")
        self.assertAlmostEqual(beta_15, 1.500, places=4)

        # Synthetic Case 2: Stock has exact beta = -0.5, alpha = 0 (inverse mover)
        s_rets_neg05 = [-0.5 * b for b in b_rets]
        beta_neg05 = calculate_beta(s_rets_neg05, b_rets, "PRI", "PRI")
        self.assertAlmostEqual(beta_neg05, -0.500, places=4)

        # Synthetic Case 3: Stock has exact beta = 1.0 with constant alpha = 0.002
        s_rets_alpha = [b + 0.002 for b in b_rets]
        beta_10 = calculate_beta(s_rets_alpha, b_rets, "PRI", "PRI")
        self.assertAlmostEqual(beta_10, 1.000, places=4)

        # Synthetic Case 4: Zero variance in benchmark returns -> mathematically undefined, must return None
        zero_var_bench = [0.005] * 60
        s_normal = [0.01 * (i % 3) for i in range(60)]
        beta_zero = calculate_beta(s_normal, zero_var_bench, "PRI", "PRI")
        self.assertIsNone(beta_zero, "Beta must be None when benchmark variance is zero (undefined denominator)")

        # Synthetic Case 5: Insufficient observations (N < 10) -> must return None
        s_short = [0.01] * 8
        b_short = [0.02] * 8
        beta_short = calculate_beta(s_short, b_short, "PRI", "PRI", min_observations=10)
        self.assertIsNone(beta_short, "Beta must be None when observations are fewer than min_observations")

    def test_aligned_series_date_matching(self):
        """
        Mandatory Condition 4:
        Validates exact inner-join alignment of stock and benchmark trading dates.
        Drops unaligned sessions cleanly.
        """
        stock_data = [
            {"trading_date": "2026-10-20", "close": 100.0, "volume": 1000},
            {"trading_date": "2026-10-21", "close": 102.0, "volume": 1200},
            {"trading_date": "2026-10-22", "close": 101.0, "volume": 1100},
            {"trading_date": "2026-10-24", "close": 105.0, "volume": 1300}  # Special session / stock only
        ]
        bench_data = [
            {"trading_date": "2026-10-19", "close": 20000.0},  # Benchmark only
            {"trading_date": "2026-10-20", "close": 20100.0},
            {"trading_date": "2026-10-21", "close": 20200.0},
            {"trading_date": "2026-10-22", "close": 20150.0}
        ]

        aligned = AlignedSeries.align_stock_and_benchmark(stock_data, bench_data)
        self.assertEqual(len(aligned), 3)
        self.assertEqual([a["trading_date"] for a in aligned], ["2026-10-20", "2026-10-21", "2026-10-22"])

        dates, s_rets, b_rets = AlignedSeries.compute_aligned_returns(aligned, "PRI", "PRI")
        self.assertEqual(len(dates), 2)
        self.assertEqual(dates, ["2026-10-21", "2026-10-22"])
        self.assertAlmostEqual(s_rets[0], (102.0 - 100.0) / 100.0)
        self.assertAlmostEqual(b_rets[0], (20200.0 - 20100.0) / 20100.0)

    def test_breadth_coverage_and_missing_accounting(self):
        """
        Mandatory Condition 5:
        Ensures breadth reporting makes coverage explicit:
        Reports expected, valid, and missing constituent observations.
        Missing observations are never treated as unchanged price.
        """
        # Seed 3 constituents for index
        self.db.upsert_index_membership_history([
            {"symbol": "SYM1", "index_name": "TEST_IDX", "valid_from": "2026-01-01", "valid_to": None, "is_verified_historical": 1, "source": "test", "retrieved_at": "now"},
            {"symbol": "SYM2", "index_name": "TEST_IDX", "valid_from": "2026-01-01", "valid_to": None, "is_verified_historical": 1, "source": "test", "retrieved_at": "now"},
            {"symbol": "SYM3", "index_name": "TEST_IDX", "valid_from": "2026-01-01", "valid_to": None, "is_verified_historical": 1, "source": "test", "retrieved_at": "now"}
        ])

        # Insert today's bars for ONLY 2 of the 3 stocks (SYM3 missing)
        self.db.upsert_ohlcv_records([
            {"symbol": "SYM1", "trading_date": "2026-10-23", "series": "EQ", "open": 100, "high": 105, "low": 98, "close": 104, "prev_close": 100, "volume": 50000, "turnover": 5000000, "source": "test", "retrieval_timestamp": "now"},
            {"symbol": "SYM2", "trading_date": "2026-10-23", "series": "EQ", "open": 200, "high": 202, "low": 195, "close": 196, "prev_close": 200, "volume": 30000, "turnover": 6000000, "source": "test", "retrieval_timestamp": "now"}
        ])

        breadth_engine = MarketBreadthEngine(self.db)
        b = breadth_engine.compute_daily_breadth("2026-10-23", "TEST_IDX")

        self.assertEqual(b["expected_constituents_count"], 3)
        self.assertEqual(b["valid_observations_count"], 2)
        self.assertEqual(b["missing_observations_count"], 1)
        self.assertEqual(b["missing_symbols"], ["SYM3"])
        self.assertAlmostEqual(b["coverage_pct"], 66.67, places=1)

        # SYM1 advanced, SYM2 declined, SYM3 is missing (NOT unchanged)
        self.assertEqual(b["advances"], 1)
        self.assertEqual(b["declines"], 1)
        self.assertEqual(b["unchanged"], 0)
        self.assertEqual(b["advance_volume"], 50000)
        self.assertEqual(b["decline_volume"], 30000)
        self.assertAlmostEqual(b["volume_breadth_ratio"], 50000 / 30000, places=2)

    def test_moving_average_warmup_and_restricted_window(self):
        """
        Mandatory Condition 1:
        Verifies that when stocks have 30 days of data, 20-DMA is computed,
        while 50-DMA and 200-DMA report warmup status (None) rather than false values.
        """
        self.db.upsert_index_membership_history([
            {"symbol": "SYM1", "index_name": "TEST_IDX", "valid_from": "2026-01-01", "valid_to": None, "is_verified_historical": 1, "source": "test", "retrieved_at": "now"}
        ])

        # Insert 30 trading days
        records = []
        for i in range(1, 31):
            d_str = f"2026-09-{i:02d}"
            records.append({
                "symbol": "SYM1", "trading_date": d_str, "series": "EQ",
                "open": 100 + i, "high": 102 + i, "low": 99 + i, "close": 101 + i,
                "prev_close": 100 + i - 1, "volume": 10000, "turnover": 1000000,
                "source": "test", "retrieval_timestamp": "now"
            })
        self.db.upsert_ohlcv_records(records)

        breadth_engine = MarketBreadthEngine(self.db)
        b = breadth_engine.compute_daily_breadth("2026-09-30", "TEST_IDX")

        # 20-DMA should be eligible and computed
        self.assertEqual(b["sma20"]["eligible_count"], 1)
        self.assertFalse(b["sma20"]["is_warmup"])
        self.assertEqual(b["sma20"]["pct_above"], 100.0)

        # 50-DMA and 200-DMA should report warm-up / insufficient history
        self.assertEqual(b["sma50"]["eligible_count"], 0)
        self.assertTrue(b["sma50"]["is_warmup"])
        self.assertIsNone(b["sma50"]["pct_above"])

        self.assertEqual(b["sma200"]["eligible_count"], 0)
        self.assertTrue(b["sma200"]["is_warmup"])
        self.assertIsNone(b["sma200"]["pct_above"])

    def test_corporate_action_volume_adjustment(self):
        """
        Mandatory Condition 3:
        Verifies that across a 1:1 bonus issue (factor 0.5), historical volumes
        are adjusted by 1 / 0.5 = 2x so post-bonus volume does NOT create an artificial spike.
        """
        records = [
            {"trading_date": "2026-05-30", "close": 2000.0, "volume": 1000000},
            {"trading_date": "2026-06-01", "close": 1010.0, "volume": 2000000}  # Ex-date of 1:1 bonus
        ]
        cas = [
            {"symbol": "TEST", "action_type": "BONUS", "ex_date": "2026-06-01", "adjustment_factor": 0.5}
        ]

        # Raw volume comparison: 2,000,000 / 1,000,000 = 2.0x (false spike appearance)
        raw_vols = [r["volume"] for r in records]
        raw_ratio = raw_vols[1] / raw_vols[0]
        self.assertEqual(raw_ratio, 2.0)

        # Share-count adjusted volumes:
        # Pre-bonus volume is scaled to 1,000,000 / 0.5 = 2,000,000 shares!
        adj_vols = adjust_volume_for_corporate_actions(records, cas)
        self.assertEqual(adj_vols[0], 2000000)
        self.assertEqual(adj_vols[1], 2000000)

        adj_ratio = adj_vols[1] / adj_vols[0]
        self.assertEqual(adj_ratio, 1.0)  # Correct: normalized to current share units

    def test_relative_strength_mode_separation_and_completeness(self):
        """
        Mandatory Condition 2:
        Mode 2 (TRI) is ONLY computed when stock corporate actions pass completeness checks;
        otherwise marked as UNAVAILABLE.
        """
        rs_engine = RelativeStrengthEngine(self.db)

        # Case 1: Symbol with NO corporate action history
        res_tri_incomplete = rs_engine.compute_stock_relative_strength("UNKNOWN_STOCK", "2026-10-23", mode="TRI")
        self.assertEqual(res_tri_incomplete["status"], "UNAVAILABLE")
        self.assertIn("incomplete or unverified", res_tri_incomplete["reason"])

        # Case 2: Seed corporate action for INFY and check completeness check passes
        self.db.upsert_corporate_actions([
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2026-05-30", "record_date": "2026-06-01", "purpose": "Rs 20 dividend", "adjustment_factor": 1.0, "source": "nse", "retrieval_timestamp": "now"}
        ])
        is_complete = rs_engine.check_corporate_actions_completeness("INFY")
        self.assertTrue(is_complete)

        # Case 3: Verify ReturnModeMismatchError when trying to cross modes
        with self.assertRaises(ReturnModeMismatchError):
            calculate_excess_return(0.05, "PRI", 0.08, "TRI")

    def test_volume_anomaly_edge_cases(self):
        """
        Mandatory Condition 6:
        Tests volume-ratio and Z-score behaviour independently:
        - Warm-up periods return None
        - Zero-variance windows return 0.0 without ZeroDivisionError
        - Extreme outliers trigger independently
        """
        # 1. Warm-up
        short_vols = [100000] * 15
        self.assertIsNone(calculate_volume_ratio(short_vols, window=20))
        z_raw, z_log = calculate_volume_zscores(short_vols, window=50)
        self.assertIsNone(z_raw)
        self.assertIsNone(z_log)

        # 2. Zero-variance window: 50 identical volume days
        flat_vols = [100000] * 51
        z_flat, _ = calculate_volume_zscores(flat_vols, window=50)
        self.assertEqual(z_flat, 0.0)

        # 3. Independent triggering: Volume Ratio triggers (>= 2.5x)
        # 20 days of 100,000; today: 280,000 -> VR = 2.8x
        vr_history = [100000] * 20 + [280000]
        vr_val = calculate_volume_ratio(vr_history, window=20)
        self.assertAlmostEqual(vr_val, 2.8)
        self.assertTrue(vr_val >= 2.5)

        # 4. Independent triggering: Z-score triggers (>= 2.5 sigma)
        # 50 days with small variance, today is a massive outlier
        z_history = [100000 + (i % 3) * 5000 for i in range(50)] + [350000]
        z_val, _ = calculate_volume_zscores(z_history, window=50)
        self.assertIsNotNone(z_val)
        self.assertTrue(z_val >= 2.5)

if __name__ == "__main__":
    unittest.main()
