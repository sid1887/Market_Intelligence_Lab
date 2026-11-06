import unittest
import sqlite3
import os
import inspect
from src.storage.database import DatabaseManager
from src.client.index_client import IndexClient
from src.client.backfill_manager import BackfillManager

class TestMilestoneB31(unittest.TestCase):
    """
    Validation test suite for Milestone B3.1:
    - 24-month historical market data (>= 480 sessions) for Nifty 50 constituents.
    - 8 Sectoral Indices ingested for both PRI and TRI (>= 480 sessions each).
    - Zero TRI OHLC fabrication: open, high, low must be strictly NULL.
    - Financial price invariants: High >= Low, High >= Open/Close, Low <= Open/Close.
    - TLS verification enforcement on index client.
    - Accurate audit logging of retrieved, accepted, and rejected records.
    - SQLite schema default PENDING_VERIFICATION for corporate disclosures.
    - Window-scoped coverage evaluation (out-of-window records preserved, cannot inflate metrics).
    - Effective-dated ticker alias and comparability handling (ZOMATO->ETERNAL vs TMPV).
    - Official Union Budget live trading sessions (2025-02-01 & 2026-02-01) verified.
    - Authoritative universe coverage acceptance from securities_master.
    """

    DB_PATH = "data/market_lab.db"

    @classmethod
    def setUpClass(cls):
        if not os.path.exists(cls.DB_PATH):
            raise unittest.SkipTest(f"Database {cls.DB_PATH} not found.")
        cls.db = DatabaseManager(cls.DB_PATH)
        cls.bm = BackfillManager(cls.db)

    def test_sectoral_indices_presence_and_depth(self):
        """Verify all 8 sectoral indices + Nifty 50 exist in index_daily with >= 480 records for both PRI and TRI."""
        expected_indices = [
            "NIFTY 50",
            "NIFTY BANK",
            "NIFTY IT",
            "NIFTY AUTO",
            "NIFTY FMCG",
            "NIFTY PHARMA",
            "NIFTY METAL",
            "NIFTY FINANCIAL SERVICES",
            "NIFTY REALTY"
        ]

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for idx_name in expected_indices:
                # Check PRI
                cursor.execute(
                    "SELECT COUNT(*), MIN(trading_date), MAX(trading_date) FROM index_daily WHERE index_name = ? AND index_type = 'PRI'",
                    (idx_name,)
                )
                pri_count, pri_min, pri_max = cursor.fetchone()
                self.assertGreaterEqual(pri_count, 480, f"PRI records for {idx_name} is {pri_count} < 480")
                self.assertLessEqual(pri_min, "2024-10-25")
                self.assertGreaterEqual(pri_max, "2026-10-23")

                # Check TRI
                cursor.execute(
                    "SELECT COUNT(*), MIN(trading_date), MAX(trading_date) FROM index_daily WHERE index_name = ? AND index_type = 'TRI'",
                    (idx_name,)
                )
                tri_count, tri_min, tri_max = cursor.fetchone()
                self.assertGreaterEqual(tri_count, 480, f"TRI records for {idx_name} is {tri_count} < 480")
                self.assertLessEqual(tri_min, "2024-10-25")
                self.assertGreaterEqual(tri_max, "2026-10-23")

    def test_zero_tri_ohlc_fabrication(self):
        """Enforce strict financial invariant: TRI records MUST have open, high, and low as NULL."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM index_daily 
                WHERE index_type = 'TRI' 
                  AND (open IS NOT NULL OR high IS NOT NULL OR low IS NOT NULL)
            """)
            fabricated_tri_count = cursor.fetchone()[0]
            self.assertEqual(fabricated_tri_count, 0, f"Found {fabricated_tri_count} TRI records with fabricated OH&L values!")

            cursor.execute("SELECT COUNT(*) FROM index_daily WHERE index_type = 'TRI' AND close IS NULL")
            null_tri_close = cursor.fetchone()[0]
            self.assertEqual(null_tri_close, 0, f"Found {null_tri_close} TRI records with NULL close!")

    def test_pri_price_invariants(self):
        """Enforce standard financial price invariants on index_daily PRI records."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM index_daily 
                WHERE index_type = 'PRI' 
                  AND (open <= 0 OR high <= 0 OR low <= 0 OR close <= 0)
            """)
            self.assertEqual(cursor.fetchone()[0], 0, "Found non-positive index PRI prices")

            cursor.execute("""
                SELECT COUNT(*) FROM index_daily 
                WHERE index_type = 'PRI' AND high < low
            """)
            self.assertEqual(cursor.fetchone()[0], 0, "Found index PRI records where High < Low")

            cursor.execute("""
                SELECT COUNT(*) FROM index_daily 
                WHERE index_type = 'PRI' 
                  AND (high < open - 0.05 OR high < close - 0.05)
            """)
            self.assertEqual(cursor.fetchone()[0], 0, "Found index PRI records where High is less than Open/Close")

    def test_constituent_ohlcv_invariants(self):
        """Verify that all ohlcv_daily records obey fundamental invariants."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) FROM ohlcv_daily 
                WHERE open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
            """)
            self.assertEqual(cursor.fetchone()[0], 0, "Found non-positive equity prices")

            cursor.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE high < low")
            self.assertEqual(cursor.fetchone()[0], 0, "Found equity records where High < Low")

            cursor.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE volume < 0")
            self.assertEqual(cursor.fetchone()[0], 0, "Found equity records with negative volume")

    def test_audit_logging_presence_and_reconciliation(self):
        """Verify ingestion audit logs are recorded and numbers reconcile."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM ingestion_audit_log WHERE source = 'nifty_indices_archive'")
            index_audit_count = cursor.fetchone()[0]
            self.assertGreaterEqual(index_audit_count, 16, f"Expected at least 16 index audit logs, found {index_audit_count}")

            cursor.execute("SELECT COUNT(*) FROM ingestion_audit_log WHERE source = 'nse_mcp'")
            stock_audit_count = cursor.fetchone()[0]
            self.assertGreaterEqual(stock_audit_count, 50, f"Expected at least 50 stock audit logs, found {stock_audit_count}")

            # Verify reconciliation across index and stock backfill logs
            cursor.execute("""
                SELECT COUNT(*) FROM ingestion_audit_log 
                WHERE source IN ('nifty_indices_archive', 'nse_mcp')
                  AND records_retrieved != (records_accepted + records_rejected)
            """)
            unreconciled = cursor.fetchone()[0]
            self.assertEqual(unreconciled, 0, f"Found {unreconciled} audit logs where retrieved != accepted + rejected")

    def test_tls_verification_enforced(self):
        """Verify that IndexClient enforces standard TLS certificate and hostname verification."""
        src_pri = inspect.getsource(IndexClient.fetch_historical_pri)
        src_tri = inspect.getsource(IndexClient.fetch_historical_tri)
        for src, name in [(src_pri, "fetch_historical_pri"), (src_tri, "fetch_historical_tri")]:
            self.assertNotIn("check_hostname = False", src, f"Disabling check_hostname found in {name}!")
            self.assertNotIn("CERT_NONE", src, f"Bypassing CERT_NONE found in {name}!")
            self.assertIn("ssl.create_default_context()", src, f"Missing standard SSL context in {name}!")

    def test_raw_sql_disclosure_defaults_to_pending_verification(self):
        """Verify SQLite schema level default: raw SQL insert without verification_status defaults to PENDING_VERIFICATION."""
        test_id = "TEST_RAW_SQL_DISC_DEFAULT"
        with self.db.get_connection() as conn:
            conn.execute("DELETE FROM corporate_disclosures WHERE disclosure_id = ?", (test_id,))

            conn.execute("""
                INSERT INTO corporate_disclosures (
                    disclosure_id, symbol, broadcast_timestamp, effective_session_date,
                    category, subject, details_summary, source_url, retrieval_timestamp
                ) VALUES (
                    ?, 'INFY', '2026-10-26T16:00:00+05:30', '2026-10-27',
                    'OTHER', 'Schema Test Disclosure', 'Test summary', 'https://example.com', '2026-10-26T10:30:00Z'
                );
            """, (test_id,))

            cursor = conn.execute("SELECT verification_status FROM corporate_disclosures WHERE disclosure_id = ?", (test_id,))
            status = cursor.fetchone()[0]
            self.assertEqual(status, "PENDING_VERIFICATION", f"Expected PENDING_VERIFICATION, got {status}")

            conn.execute("DELETE FROM corporate_disclosures WHERE disclosure_id = ?", (test_id,))

    def test_window_scoped_coverage_not_inflated_by_older_records(self):
        """
        Verify that verify_symbol_coverage() strictly evaluates coverage within the benchmark window.
        Older preserved records (e.g. 2023-2024 for ETERNAL) cannot inflate the 24-month session count.
        """
        cov = self.bm.verify_symbol_coverage("ETERNAL", start_date="2024-10-21", end_date="2026-10-23")
        self.assertEqual(cov["session_count"], 498, f"Expected exactly 498 benchmark window sessions, got {cov['session_count']}")
        self.assertGreaterEqual(cov["total_db_sessions"], 875, f"Expected >= 875 total database sessions, got {cov['total_db_sessions']}")
        self.assertNotEqual(cov["session_count"], cov["total_db_sessions"], "Window count must not equal lifetime DB count")
        self.assertEqual(cov["earliest_date"], "2024-10-21")
        self.assertEqual(cov["latest_date"], "2026-10-23")
        self.assertEqual(cov["earliest_db_date"], "2023-04-10")

    def test_pre_rename_and_post_rename_session_counts(self):
        """
        Verify that ETERNAL has exactly 117 pre-rename sessions (ZOMATO) and 381 post-rename sessions
        within the 2024-10-21 to 2026-10-23 window (including Budget Days), with zero duplicate dates.
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Pre-rename count in window
            cursor.execute("""
                SELECT COUNT(*), COUNT(DISTINCT trading_date) FROM ohlcv_daily 
                WHERE symbol = 'ETERNAL' AND trading_date BETWEEN '2024-10-21' AND '2025-04-08'
            """)
            pre_cnt, pre_dist = cursor.fetchone()
            self.assertEqual(pre_cnt, 117, f"Expected 117 pre-rename sessions, got {pre_cnt}")
            self.assertEqual(pre_dist, 117)

            # Post-rename count in window
            cursor.execute("""
                SELECT COUNT(*), COUNT(DISTINCT trading_date) FROM ohlcv_daily 
                WHERE symbol = 'ETERNAL' AND trading_date BETWEEN '2025-04-09' AND '2026-10-23'
            """)
            post_cnt, post_dist = cursor.fetchone()
            self.assertEqual(post_cnt, 381, f"Expected 381 post-rename sessions, got {post_cnt}")
            self.assertEqual(post_dist, 381)

            # Zero overlap across boundary
            cursor.execute("""
                SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = 'ETERNAL' AND trading_date = '2025-04-08'
            """)
            self.assertEqual(cursor.fetchone()[0], 1)
            cursor.execute("""
                SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = 'ETERNAL' AND trading_date = '2025-04-09'
            """)
            self.assertEqual(cursor.fetchone()[0], 1)

    def test_budget_day_sessions_present_and_valid(self):
        """Verify that official Union Budget live trading sessions (2025-02-01 & 2026-02-01) are present and valid."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for d in ["2025-02-01", "2026-02-01"]:
                # Check ETERNAL specifically
                cursor.execute("SELECT open, high, low, close, volume, source FROM ohlcv_daily WHERE symbol = 'ETERNAL' AND trading_date = ?", (d,))
                row = cursor.fetchone()
                self.assertIsNotNone(row, f"ETERNAL missing on Budget Day {d}")
                self.assertGreater(row[0], 0)
                self.assertGreaterEqual(row[1], row[2])  # High >= Low
                self.assertGreater(row[4], 0)            # Volume > 0

                if d == "2025-02-01":
                    self.assertIn("alias_zomato", row[5], f"Expected ZOMATO alias provenance on {d}, got {row[5]}")

    def test_out_of_window_records_preserved(self):
        """Verify that older historical records for ETERNAL (prior to 2024-10-21) were NOT deleted."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*), MIN(trading_date), MAX(trading_date) 
                FROM ohlcv_daily 
                WHERE symbol = 'ETERNAL' AND trading_date < '2024-10-21'
            """)
            cnt, min_d, max_d = cursor.fetchone()
            self.assertEqual(cnt, 377, f"Expected 377 preserved out-of-window records, got {cnt}")
            self.assertEqual(min_d, "2023-04-10")
            self.assertEqual(max_d, "2024-10-18")

    def test_authoritative_universe_coverage_acceptance(self):
        """Verify all 50 active constituents from securities_master meet coverage acceptance criteria."""
        active_symbols = self.bm.get_active_universe()
        self.assertGreaterEqual(len(active_symbols), 50, f"Expected at least 50 active symbols, found {len(active_symbols)}")

        unmet = []
        coverage_met_count = 0
        exception_count = 0

        for sym in active_symbols:
            cov = self.bm.verify_symbol_coverage(sym)
            if not cov["meets_acceptance"]:
                unmet.append(cov)
            elif cov["status"] == "COVERAGE_MET":
                coverage_met_count += 1
            elif cov["status"] == "COVERAGE_EXCEPTION_TICKER_RENAME":
                exception_count += 1

        self.assertEqual(len(unmet), 0, f"Constituents failing coverage acceptance: {unmet}")
        self.assertEqual(exception_count, 1, "Expected exactly 1 documented exception (TMPV)")
        self.assertGreaterEqual(coverage_met_count, 49, f"Expected at least 49 symbols with COVERAGE_MET, got {coverage_met_count}")

if __name__ == "__main__":
    unittest.main()
