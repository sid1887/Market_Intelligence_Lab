import unittest
import sqlite3
import os
import json
import zipfile
import io
from src.storage.database import DatabaseManager
from src.client.universe_manager import UniverseManager
from src.client.udiff_client import UDiffClient
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
    evaluate_volume_anomalies
)

class TestMilestone21(unittest.TestCase):
    """
    Exhaustive acceptance test suite for Milestone 2.1:
    - Additive schema migration safety
    - Point-in-time constituent membership and survivorship-bias flags
    - TRI nullable OHLC schema enforcement
    - Return-mode consistency and mixing prevention
    - Rolling factor warm-up nullability
    - CM-UDiFF archive parsing, invariants, and rejection
    - Split/bonus factor propagation
    - Scheduler timing reconciliation
    """

    def setUp(self):
        # Use an in-memory database initialized with v1 and v2 schemas
        self.db = DatabaseManager(":memory:")

    def test_additive_schema_migration_safety(self):
        """Verifies that all Phase 2 tables and columns exist cleanly."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = {r["name"] for r in cursor.fetchall()}

            expected_tables = {
                "ohlcv_daily", "corporate_actions", "ingestion_audit_log",
                "securities_master", "index_membership_history", "index_daily",
                "corporate_disclosures", "quant_factors_daily", "event_study_results"
            }
            self.assertTrue(expected_tables.issubset(tables), f"Missing tables: {expected_tables - tables}")

            # Check ohlcv_daily columns
            cursor.execute("PRAGMA table_info(ohlcv_daily);")
            cols = {r["name"] for r in cursor.fetchall()}
            self.assertIn("trades_count", cols)
            self.assertIn("data_status", cols)

    def test_point_in_time_membership_history(self):
        """
        Verifies point-in-time constituent interval lookups:
        - Exact 50 count for all dates
        - Pre-March 2024 marked with current_proxy_unadjusted and is_survivorship_bias_free=False
        - March 2024 rebalancing: SHRIRAMFIN in, UPL out
        - Sept 2024 rebalancing: BEL & TRENT in, DIVISLAB & LTIM out
        - Sept 2026 rebalancing: BSE in, WIPRO out
        """
        mgr = UniverseManager(self.db)
        mgr.seed_point_in_time_membership("NIFTY 50")

        # 1. Pre-March 2024 proxy
        res_proxy = mgr.get_constituents_for_date("2023-11-01")
        self.assertEqual(res_proxy["count"], 50)
        self.assertFalse(res_proxy["is_survivorship_bias_free"])
        self.assertEqual(res_proxy["membership_basis"], "current_proxy_unadjusted")
        self.assertIsNotNone(res_proxy.get("warning"))

        # 2. May 2024 (Between Mar 2024 and Sep 2024)
        res_may24 = mgr.get_constituents_for_date("2024-05-15")
        self.assertEqual(res_may24["count"], 50)
        self.assertTrue(res_may24["is_survivorship_bias_free"])
        self.assertIn("SHRIRAMFIN", res_may24["constituents"])
        self.assertIn("DIVISLAB", res_may24["constituents"])
        self.assertIn("LTIM", res_may24["constituents"])
        self.assertNotIn("UPL", res_may24["constituents"])
        self.assertNotIn("BEL", res_may24["constituents"])
        self.assertNotIn("TRENT", res_may24["constituents"])

        # 3. November 2024 (Between Sep 2024 and Mar 2025)
        res_nov24 = mgr.get_constituents_for_date("2024-11-15")
        self.assertEqual(res_nov24["count"], 50)
        self.assertTrue(res_nov24["is_survivorship_bias_free"])
        self.assertIn("BEL", res_nov24["constituents"])
        self.assertIn("TRENT", res_nov24["constituents"])
        self.assertNotIn("DIVISLAB", res_nov24["constituents"])
        self.assertNotIn("LTIM", res_nov24["constituents"])

        # 4. October 2026 (Current post Sep 2026)
        res_oct26 = mgr.get_constituents_for_date("2026-10-15")
        self.assertEqual(res_oct26["count"], 50)
        self.assertTrue(res_oct26["is_survivorship_bias_free"])
        self.assertIn("BSE", res_oct26["constituents"])
        self.assertNotIn("WIPRO", res_oct26["constituents"])

    def test_tri_pri_schema_and_null_ohlc(self):
        """
        Verifies Mandatory Correction 1:
        TRI series allows open, high, low to be NULL and stores true index value in close.
        PRI series stores full OHLC.
        """
        # Insert TRI record with NULL open, high, low
        tri_record = [{
            "index_name": "NIFTY 50",
            "trading_date": "2026-10-23",
            "index_type": "TRI",
            "open": None,
            "high": None,
            "low": None,
            "close": 34351.79,
            "volume": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "div_yield": None,
            "source": "nifty_indices_archive",
            "retrieval_timestamp": "2026-10-25T12:00:00Z"
        }]
        c1 = self.db.upsert_index_daily(tri_record)
        self.assertEqual(c1, 1)

        # Insert PRI record with full OHLC
        pri_record = [{
            "index_name": "NIFTY 50",
            "trading_date": "2026-10-23",
            "index_type": "PRI",
            "open": 22742.20,
            "high": 22787.25,
            "low": 22372.00,
            "close": 22600.00,
            "volume": 364190826,
            "pe_ratio": 19.05,
            "pb_ratio": 2.78,
            "div_yield": 1.52,
            "source": "nifty_indices_archive",
            "retrieval_timestamp": "2026-10-25T12:00:00Z"
        }]
        c2 = self.db.upsert_index_daily(pri_record)
        self.assertEqual(c2, 1)

        # Retrieve and verify
        tri_rows = self.db.get_index_history("NIFTY 50", "TRI")
        self.assertEqual(len(tri_rows), 1)
        self.assertIsNone(tri_rows[0]["open"])
        self.assertIsNone(tri_rows[0]["high"])
        self.assertIsNone(tri_rows[0]["low"])
        self.assertEqual(tri_rows[0]["close"], 34351.79)

        pri_rows = self.db.get_index_history("NIFTY 50", "PRI")
        self.assertEqual(len(pri_rows), 1)
        self.assertEqual(pri_rows[0]["open"], 22742.20)
        self.assertEqual(pri_rows[0]["close"], 22600.00)

        # Invariant check: invalid index_type must be rejected by check constraint
        invalid_record = [{
            "index_name": "NIFTY 50",
            "trading_date": "2026-10-23",
            "index_type": "INVALID_TYPE",
            "open": 100.0,
            "high": 105.0,
            "low": 95.0,
            "close": 102.0,
            "volume": None,
            "pe_ratio": None,
            "pb_ratio": None,
            "div_yield": None,
            "source": "test",
            "retrieval_timestamp": "2026-10-25T12:00:00Z"
        }]
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.upsert_index_daily(invalid_record)

    def test_return_mode_mixing_guardrail(self):
        """
        Verifies Mandatory Correction 3:
        Strict rejection of mismatched return modes (e.g. Stock Price Return vs Benchmark TRI).
        """
        # Mode 1: PRI vs PRI -> allowed
        res1 = calculate_excess_return(0.08, "PRI", 0.05, "PRI")
        self.assertAlmostEqual(res1["excess_return"], 0.03)
        self.assertTrue(res1["is_outperforming"])

        # Mode 2: TRI vs TRI -> allowed
        res2 = calculate_excess_return(0.12, "TRI", 0.09, "TRI")
        self.assertAlmostEqual(res2["excess_return"], 0.03)
        self.assertTrue(res2["is_outperforming"])

        # Accidental mixing: Stock PRI vs Benchmark TRI -> MUST RAISE ReturnModeMismatchError
        with self.assertRaises(ReturnModeMismatchError):
            calculate_excess_return(0.08, "PRI", 0.12, "TRI")

        # Accidental mixing: Stock TRI vs Benchmark PRI -> MUST RAISE ReturnModeMismatchError
        with self.assertRaises(ReturnModeMismatchError):
            calculate_excess_return(0.12, "TRI", 0.08, "PRI")

        # Beta calculation with mismatched modes -> MUST RAISE ReturnModeMismatchError
        stock_rets = [0.01 * (i % 3) for i in range(20)]
        bench_rets = [0.008 * (i % 3) for i in range(20)]
        with self.assertRaises(ReturnModeMismatchError):
            calculate_beta(stock_rets, bench_rets, "PRI", "TRI")

    def test_rolling_factor_warmup_nullability(self):
        """
        Verifies Mandatory Correction 2:
        During the initial warm-up period, volume ratio and Z-scores return None (NULL)
        and can be stored in quant_factors_daily without violating NOT NULL constraints.
        """
        # Warm-up check: 10 volume observations are insufficient for 20-day VR or 50-day Z-score
        short_vols = [1000000 + i * 50000 for i in range(10)]
        vr = calculate_volume_ratio(short_vols, window=20)
        raw_z, log_z = calculate_volume_zscores(short_vols, window=50)

        self.assertIsNone(vr)
        self.assertIsNone(raw_z)
        self.assertIsNone(log_z)

        # Store in quant_factors_daily with NULLs
        factor_row = [{
            "symbol": "INFY",
            "trading_date": "2025-11-05",
            "ret_1d": 0.015,
            "ret_5d": None,
            "ret_20d": None,
            "vol_20d_annualized": None,
            "sma_20": None,
            "sma_50": None,
            "sma_200": None,
            "beta_60d_nifty": None,
            "volume_ratio_20d": None,        # Permitted NULL
            "volume_zscore_50d": None,       # Permitted NULL
            "volume_log_zscore_50d": None,   # Permitted NULL
            "is_volume_spike_ratio": 0,
            "is_volume_spike_zscore": 0,
            "distance_52w_high": None,
            "distance_52w_low": None
        }]
        c = self.db.upsert_quant_factors(factor_row)
        self.assertEqual(c, 1)

        factors = self.db.get_quant_factors("INFY")
        self.assertEqual(len(factors), 1)
        self.assertIsNone(factors[0]["volume_ratio_20d"])
        self.assertIsNone(factors[0]["volume_zscore_50d"])

    def test_volume_anomaly_metrics_distinction(self):
        """
        Verifies that Volume Ratio and Volume Z-Score test distinct statistical phenomena.
        """
        # Case 1: Low-dispersion, steady volume with a 2.6x jump
        # Baseline: 20 days of 100,000; today: 260,000
        baseline_vols_20 = [100000] * 20
        vols_case1 = baseline_vols_20 + [260000]
        vr1 = calculate_volume_ratio(vols_case1, window=20)
        self.assertIsNotNone(vr1)
        self.assertAlmostEqual(vr1, 2.6)
        self.assertTrue(vr1 >= 2.5)  # Triggers VR anomaly

        # Case 2: 50 days of volume with extreme outlier
        baseline_vols_50 = [100000] * 50
        # If std dev is 0, any deviation triggers max or handled cleanly
        vols_varied_50 = [100000 + (i % 5) * 10000 for i in range(50)]
        vols_case2 = vols_varied_50 + [400000]
        z_raw, z_log = calculate_volume_zscores(vols_case2, window=50)
        self.assertIsNotNone(z_raw)
        self.assertTrue(z_raw > 2.5)  # Extreme statistical tail event

    def test_udiff_client_parsing_and_invariants(self):
        """
        Tests UDiffClient parsing:
        - In-memory synthetic zip
        - Rejection of High < Low
        - Mapping of trades_count
        - Default NULL for delivery_qty
        """
        # Create an in-memory zip file simulating CM-UDiFF Bhavcopy
        csv_content = (
            "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,"
            "StrkPric,OptnTp,FinInstrmNm,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,UndrlygPric,"
            "SttlmPric,OpnIntrst,ChngInOpnIntrst,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd,SsnId,NewBrdLotQty,Rmks,Rsvd1,Rsvd2,Rsvd3,Rsvd4\n"
            "2026-10-23,2026-10-23,CM,NSE,STK,1594,INE009A01021,INFY,EQ,,,,,INFOSYS LIMITED,1187.00,1197.80,1038.05,1153.80,1153.80,1153.35,,1153.81,,,33044499,38480434197.50,406897,F1,1,,,,,\n"
            "2026-10-23,2026-10-23,CM,NSE,STK,9999,INE999A01099,CORRUPT,EQ,,,,,CORRUPT LTD,100.00,90.00,110.00,95.00,95.00,100.00,,95.00,,,1000,100000.00,50,F1,1,,,,,\n"
        )
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv", csv_content)
        zip_buf.seek(0)

        client = UDiffClient()
        records, summary = client.parse_udiff_archive(zip_buf, universe_symbols={"INFY", "CORRUPT"})

        self.assertEqual(summary["total_rows_read"], 2)
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["rejected_count"], 1)

        # Valid INFY record
        infy_rec = records[0]
        self.assertEqual(infy_rec["symbol"], "INFY")
        self.assertEqual(infy_rec["close"], 1153.80)
        self.assertEqual(infy_rec["trades_count"], 406897)
        self.assertIsNone(infy_rec["delivery_qty"])
        self.assertEqual(infy_rec["data_status"], "final_settled")

        # Rejected record reason
        rej = summary["rejections"][0]
        self.assertEqual(rej["symbol"], "CORRUPT")
        self.assertIn("High 90.0 < Low 110.0", rej["reason"])

    def test_corporate_action_split_bonus_adjustment(self):
        """
        Verifies split/bonus adjustment factor propagation:
        A 1:1 bonus issue (factor 0.5) on 2026-06-01 adjusts prior prices by 0.5.
        """
        records = [
            {"trading_date": "2026-05-30", "close": 2000.0, "open": 1990.0, "high": 2010.0, "low": 1980.0},
            {"trading_date": "2026-06-01", "close": 1020.0, "open": 1000.0, "high": 1030.0, "low": 995.0}
        ]
        cas = [
            {"symbol": "TEST", "action_type": "BONUS", "ex_date": "2026-06-01", "adjustment_factor": 0.5}
        ]
        adjusted = calculate_split_bonus_adjustment_factors(records, cas)
        self.assertEqual(len(adjusted), 2)

        # Pre-bonus close was 2000.0, adjusted becomes 1000.0
        self.assertEqual(adjusted[0]["adjusted_close"], 1000.0)
        self.assertEqual(adjusted[0]["split_bonus_cum_factor"], 0.5)

        # Post-bonus close remains 1020.0
        self.assertEqual(adjusted[1]["adjusted_close"], 1020.0)
        self.assertEqual(adjusted[1]["split_bonus_cum_factor"], 1.0)

        # Return from 1000.0 to 1020.0 is +2%, instead of artificial -49%
        ret = (adjusted[1]["adjusted_close"] - adjusted[0]["adjusted_close"]) / adjusted[0]["adjusted_close"]
        self.assertAlmostEqual(ret, 0.02)

    def test_scheduler_timing_reconciliation(self):
        """
        Verifies Mandatory Correction 4:
        Scheduler configuration specifies 16 retries after initial attempt = 17 attempts total,
        covering 16:30 to 20:30 IST at 15-minute intervals.
        """
        settings_path = "config/settings.json"
        with open(settings_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        sch = cfg["scheduler"]
        self.assertEqual(sch["eod_poll_start_ist"], "16:30")
        self.assertEqual(sch["eod_poll_end_ist"], "20:30")
        self.assertEqual(sch["poll_interval_minutes"], 15)
        self.assertEqual(sch["max_retries"], 16)
        self.assertEqual(sch["total_attempts"], 17)

        # Verify arithmetic
        # 16 intervals of 15 mins = 240 minutes = 4.0 hours (16:30 + 4h = 20:30)
        span_minutes = sch["max_retries"] * sch["poll_interval_minutes"]
        self.assertEqual(span_minutes, 240)

if __name__ == "__main__":
    unittest.main()
