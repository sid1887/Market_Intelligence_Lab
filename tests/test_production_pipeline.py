import unittest
import os
import io
import zipfile
import tempfile
import datetime
from src.storage.database import DatabaseManager
from src.pipeline.production_pipeline import (
    ProductionPipeline,
    SchedulerLock,
    SchedulerLockError,
    IST_TZ
)

class TestProductionPipeline(unittest.TestCase):
    """
    Exhaustive acceptance test suite for Milestone 2.5 Automated Production Pipeline:
    1. Duplicate execution prevention via SchedulerLock (raises SchedulerLockError).
    2. Simulated delayed publication with bounded retries (succeeds on attempt N).
    3. Missing archive handling (deadline expiry -> PENDING_EXCHANGE_RELEASE + 08:30 morning recovery).
    4. Corrupt archive detection and rejection.
    5. Invariant check: provisional snapshots NEVER overwrite final_settled records.
    6. Per-symbol failure isolation (partial failure does not terminate entire batch).
    7. End-to-end scheduled pipeline execution against actual database.
    """

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.lock_path = os.path.join(self.temp_dir, "test_scheduler.lock")
        self.db = DatabaseManager(":memory:")
        self.pipeline = ProductionPipeline(
            db=self.db,
            raw_udiff_dir=os.path.join(self.temp_dir, "udiff"),
            reports_dir=os.path.join(self.temp_dir, "reports"),
            lock_file_path=self.lock_path
        )

        # Seed securities_master & index_membership_history
        self.db.upsert_securities_master([{
            "symbol": "INFY", "company_name": "Infosys Ltd.", "isin": "INE009A01021",
            "industry": "IT", "sector": "IT", "macro_sector": "IT",
            "listing_date": "1993-01-01", "is_active": 1, "updated_at": "now"
        }])
        self.db.upsert_index_membership_history([{
            "symbol": "INFY", "index_name": "NIFTY 50", "valid_from": "2024-01-01",
            "valid_to": None, "is_verified_historical": 1, "source": "test",
            "retrieved_at": "now"
        }])

        # Create valid synthetic CM-UDiFF ZIP
        self.valid_zip_path = os.path.join(self.temp_dir, "BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv.zip")
        csv_content = (
            "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd\n"
            "2026-10-23,2026-10-23,CM,NSE,STK,1,INE009A01021,INFY,EQ,1187.00,1197.80,1038.05,1153.80,1153.80,1153.35,33044499,38126743000.0,450000\n"
        )
        with zipfile.ZipFile(self.valid_zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("BhavCopy_NSE_CM_0_0_0_20261023_F_0000.csv", csv_content)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_duplicate_execution_prevention(self):
        """
        Verifies that attempting to acquire the scheduler lock concurrently
        raises SchedulerLockError to prevent overlapping execution.
        """
        with SchedulerLock(self.lock_path):
            self.assertTrue(os.path.exists(self.lock_path))
            with self.assertRaises(SchedulerLockError):
                with SchedulerLock(self.lock_path):
                    pass
        # Once released, lock can be re-acquired
        with SchedulerLock(self.lock_path):
            self.assertTrue(os.path.exists(self.lock_path))

    def test_simulated_delayed_publication_retry(self):
        """
        Simulates exchange delaying archive release:
        - Fails on attempts 1 and 2.
        - Succeeds on attempt 3.
        """
        attempts = 0
        def delayed_download(date_str):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return None, "HTTP 404: Not published yet"
            return self.valid_zip_path, None

        zip_p, status, count = self.pipeline.poll_for_udiff_archive(
            trading_date_iso="2026-10-23",
            max_attempts=5,
            download_fn=delayed_download
        )
        self.assertEqual(status, "ARCHIVE_AVAILABLE")
        self.assertEqual(count, 3)
        self.assertEqual(zip_p, self.valid_zip_path)

    def test_missing_archive_deadline_and_morning_recovery(self):
        """
        Simulates archive not published by the 20:30 IST deadline.
        Must record PENDING_EXCHANGE_RELEASE and schedule 08:30 IST morning recovery.
        """
        def unavailable_download(date_str):
            return None, "HTTP 404: File not found"

        res = self.pipeline.execute_daily_workflow(
            trading_date_iso="2026-10-23",
            max_poll_attempts=3,
            custom_download_fn=unavailable_download
        )
        self.assertEqual(res["status"], "PENDING_EXCHANGE_RELEASE")
        self.assertIn("08:30:00+05:30", res["morning_recovery_scheduled_ist"])

        # Verify audit log was recorded
        audit_records = self.db.get_connection().execute("SELECT * FROM ingestion_audit_log").fetchall()
        self.assertEqual(len(audit_records), 1)
        self.assertEqual(audit_records[0]["status"], "PENDING_EXCHANGE_RELEASE")

    def test_corrupt_archive_handling(self):
        """
        Verifies that corrupted archives (invalid ZIP bytes) are cleanly rejected and logged.
        """
        corrupt_zip = os.path.join(self.temp_dir, "corrupt.zip")
        with open(corrupt_zip, "w") as f:
            f.write("NOT_A_ZIP_FILE_JUST_CORRUPT_BYTES")

        records, summary = self.pipeline.udiff_client.parse_udiff_archive(corrupt_zip)
        self.assertEqual(len(records), 0)
        self.assertGreater(len(summary["rejections"]), 0)
        self.assertIn("corrupted zip archive", summary["rejections"][0]["reason"])

    def test_provisional_snapshot_never_overwrites_final_settled(self):
        """
        Critical Rule: A provisional record must NEVER overwrite an existing final_settled record.
        """
        # 1. Insert final_settled record
        final_rec = [{
            "symbol": "INFY", "trading_date": "2026-10-23", "series": "EQ",
            "open": 1187.0, "high": 1197.8, "low": 1038.05, "close": 1153.8,
            "volume": 33044499, "data_status": "final_settled", "source": "cm_udiff",
            "retrieval_timestamp": "2026-10-23T16:30:00Z"
        }]
        self.db.upsert_ohlcv_records(final_rec)

        # 2. Attempt to upsert provisional record with conflicting prices
        provisional_rec = [{
            "symbol": "INFY", "trading_date": "2026-10-23", "series": "EQ",
            "open": 1200.0, "high": 1250.0, "low": 1100.0, "close": 1220.0,
            "volume": 5000000, "data_status": "provisional", "source": "intraday_snapshot",
            "retrieval_timestamp": "2026-10-23T14:30:00Z"
        }]
        self.db.upsert_ohlcv_records(provisional_rec)

        # 3. Verify final_settled record remains completely preserved
        stored = self.db.get_stock_history("INFY", start_date="2026-10-23", end_date="2026-10-23")[0]
        self.assertEqual(stored["close"], 1153.8)
        self.assertEqual(stored["data_status"], "final_settled")
        self.assertNotEqual(stored["close"], 1220.0)

    def test_per_symbol_failure_isolation(self):
        """
        Verifies that if one symbol in a CSV has corrupted numerical values,
        other valid symbols in the batch are still ingested and processed cleanly.
        """
        mixed_csv = (
            "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd\n"
            "2026-10-23,2026-10-23,CM,NSE,STK,1,INE009A01021,INFY,EQ,1187.00,1197.80,1038.05,1153.80,1153.80,1153.35,33044499,38126743000.0,450000\n"
            "2026-10-23,2026-10-23,CM,NSE,STK,2,INE000A00000,BADSYM,EQ,CORRUPT,PRICE,ERROR,NAN,NAN,NAN,0,0,0\n"
        )
        mixed_zip = os.path.join(self.temp_dir, "mixed.zip")
        with zipfile.ZipFile(mixed_zip, "w") as z:
            z.writestr("mixed.csv", mixed_csv)

        records, summary = self.pipeline.udiff_client.parse_udiff_archive(mixed_zip)
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["rejected_count"], 1)
        self.assertEqual(records[0]["symbol"], "INFY")
        self.assertEqual(summary["rejections"][0]["symbol"], "BADSYM")

    def test_trading_holiday_and_weekend_preflight_skips_polling(self):
        """
        Verifies that non-trading sessions (weekends and official NSE holidays)
        are caught immediately by calendar preflight, skipping CM-UDiFF polling
        and logging NON_TRADING_DAY in the audit log.
        """
        # 1. Weekend test (Saturday: 2026-10-24)
        res_weekend = self.pipeline.execute_daily_workflow(
            trading_date_iso="2026-10-24",
            max_poll_attempts=5
        )
        self.assertEqual(res_weekend["status"], "NON_TRADING_DAY")
        self.assertIn("Weekend (Saturday)", res_weekend["reason"])
        self.assertNotIn("udiff_polling", res_weekend.get("stages", {}))

        # 2. NSE Holiday test (Republic Day: 2026-01-26)
        res_holiday = self.pipeline.execute_daily_workflow(
            trading_date_iso="2026-01-26",
            max_poll_attempts=5
        )
        self.assertEqual(res_holiday["status"], "NON_TRADING_DAY")
        self.assertIn("Exchange Holiday (Republic Day)", res_holiday["reason"])
        self.assertNotIn("udiff_polling", res_holiday.get("stages", {}))

        # Verify audit entries
        conn = self.db.get_connection()
        logs = conn.execute(
            "SELECT endpoint, status, date_range_start FROM ingestion_audit_log WHERE status = 'NON_TRADING_DAY'"
        ).fetchall()
        self.assertEqual(len(logs), 2)
        dates_logged = {r["date_range_start"] for r in logs}
        self.assertIn("2026-10-24", dates_logged)
        self.assertIn("2026-01-26", dates_logged)

    def test_separate_pri_and_tri_benchmark_refresh_tracking(self):
        """
        Verifies Stage 2 benchmark refresh independently queries, tracks, and logs
        both Nifty 50 PRI and TRI indices with individual closes and statuses.
        """
        # Seed both PRI and TRI
        self.db.upsert_index_daily([
            {
                "index_name": "NIFTY 50", "trading_date": "2026-10-23", "index_type": "PRI",
                "open": 22742.20, "high": 22787.25, "low": 22372.00, "close": 22600.00,
                "volume": None, "source": "nifty_indices_archive", "retrieval_timestamp": "now"
            },
            {
                "index_name": "NIFTY 50", "trading_date": "2026-10-23", "index_type": "TRI",
                "open": None, "high": None, "low": None, "close": 34351.79,
                "volume": None, "source": "nifty_indices_archive", "retrieval_timestamp": "now"
            }
        ])

        res = self.pipeline.execute_daily_workflow(
            trading_date_iso="2026-10-23",
            index_name="NIFTY 50",
            custom_download_fn=lambda d: (self.valid_zip_path, None)
        )

        self.assertIn("benchmark_refresh", res["stages"])
        bm = res["stages"]["benchmark_refresh"]
        self.assertEqual(bm["index_name"], "NIFTY 50")
        self.assertEqual(bm["total_benchmark_records"], 2)

        # Separate PRI tracking
        self.assertEqual(bm["PRI"]["records_found"], 1)
        self.assertEqual(bm["PRI"]["close"], 22600.00)
        self.assertEqual(bm["PRI"]["data_status"], "AVAILABLE")
        self.assertEqual(bm["PRI"]["source"], "nifty_indices_archive")

        # Separate TRI tracking
        self.assertEqual(bm["TRI"]["records_found"], 1)
        self.assertEqual(bm["TRI"]["close"], 34351.79)
        self.assertEqual(bm["TRI"]["data_status"], "AVAILABLE")
        self.assertEqual(bm["TRI"]["source"], "nifty_indices_archive")

    def test_offline_downtime_recovery_identifies_specific_missed_sessions(self):
        """
        Verifies that downtime recovery identifies specific uningested or pending
        trading sessions, skips non-trading days, and executes recovery sequentially.
        """
        def make_synthetic_zip(date_str):
            z_path = os.path.join(self.temp_dir, f"BhavCopy_{date_str}.csv.zip")
            csv_str = (
                "TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,LastPric,PrvsClsgPric,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd\n"
                f"{date_str},{date_str},CM,NSE,STK,1,INE009A01021,INFY,EQ,1187.00,1197.80,1038.05,1153.80,1153.80,1153.35,33044499,38126743000.0,450000\n"
            )
            with zipfile.ZipFile(z_path, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr(f"BhavCopy_{date_str}.csv", csv_str)
            return z_path

        # Mark 2026-10-22 as pending exchange release in audit log
        self.db.record_audit_log(
            source="production_scheduler",
            endpoint="cm_udiff_bhavcopy_poll",
            symbol="UNIVERSE",
            date_range_start="2026-10-22",
            date_range_end="2026-10-22",
            records_retrieved=0,
            records_accepted=0,
            records_rejected=0,
            validation_summary={"status": "PENDING_EXCHANGE_RELEASE"},
            raw_payload_path="",
            status="PENDING_EXCHANGE_RELEASE",
            created_at="2026-10-22T20:30:00+05:30"
        )

        missing = self.pipeline.find_missing_or_pending_sessions(
            lookback_days=1,
            as_of_date="2026-10-22"
        )
        self.assertIn("2026-10-22", missing)

        # Execute recovery with dynamic synthetic file
        rec_summary = self.pipeline.recover_missing_sessions(
            lookback_days=0,
            as_of_date="2026-10-22",
            custom_download_fn=lambda d: (make_synthetic_zip(d), None)
        )
        self.assertEqual(rec_summary["status"], "ALL_RECOVERED")
        self.assertIn("2026-10-22", rec_summary["sessions_processed"])
        self.assertEqual(rec_summary["sessions_processed"]["2026-10-22"]["status"], "SUCCESS")

    def test_live_production_pipeline_run(self):
        """
        Executes the production pipeline against the actual local market_lab.db.
        Verifies end-to-end execution, audit log creation, and reports generation.
        """
        import shutil
        temp_db_path = os.path.join(self.temp_dir, "test_market_lab_copy.db")
        shutil.copy2("data/market_lab.db", temp_db_path)
        real_db = DatabaseManager(temp_db_path)
        prod = ProductionPipeline(
            db=real_db,
            reports_dir="reports",
            lock_file_path=os.path.join(self.temp_dir, "prod_live.lock")
        )

        res = prod.execute_daily_workflow(
            trading_date_iso="2026-10-23",
            index_name="NIFTY 50",
            benchmark_mode="PRI",
            symbols_to_tearsheet=["INFY"],
            max_poll_attempts=1
        )

        self.assertEqual(res["status"], "SUCCESS")
        self.assertIn("daily_report", res["stages"])
        self.assertEqual(res["stages"]["daily_report"]["status"], "SUCCESS")
        self.assertIn("INFY", res["stages"]["company_tearsheets"])
        self.assertEqual(res["stages"]["company_tearsheets"]["INFY"]["status"], "SUCCESS")
        self.assertGreater(res["audit_log_id"], 0)

if __name__ == "__main__":
    unittest.main()
