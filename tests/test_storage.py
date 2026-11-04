import unittest
import sqlite3
import os
from src.storage.database import DatabaseManager

class TestStorage(unittest.TestCase):
    """Unit tests for SQLite schema, upsert logic, null preservation, and audit logging."""

    def setUp(self):
        # Use an in-memory database or temporary file for tests
        self.db_path = ":memory:"
        self.db = DatabaseManager(db_path=self.db_path)

    def test_null_preservation_for_delivery_qty(self):
        """Verify Requirement 1: Missing delivery quantity is stored as NULL, not silently coerced to 0."""
        record_with_null = {
            "symbol": "INFY",
            "trading_date": "2026-10-23",
            "series": "EQ",
            "open": 1150.0,
            "high": 1160.0,
            "low": 1145.0,
            "close": 1153.8,
            "ltp": 1153.8,
            "prev_close": 1150.0,
            "volume": 5000000,
            "turnover": 5750000000.0,
            "delivery_qty": None,  # Explicitly None (unavailable)
            "source": "test_mcp",
            "retrieval_timestamp": "2026-10-25T12:00:00Z"
        }

        self.db.upsert_ohlcv_records([record_with_null])
        rows = self.db.get_stock_history("INFY")

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["symbol"], "INFY")
        self.assertIsNone(row["delivery_qty"], "delivery_qty must be NULL in the database when unavailable, NOT 0!")

    def test_upsert_deduplication(self):
        """Verify that duplicate upserts update existing records without creating duplicates."""
        rec1 = {
            "symbol": "TCS",
            "trading_date": "2026-10-20",
            "series": "EQ",
            "open": 3500.0,
            "high": 3550.0,
            "low": 3490.0,
            "close": 3520.0,
            "ltp": 3520.0,
            "prev_close": 3500.0,
            "volume": 1000000,
            "turnover": 3520000000.0,
            "delivery_qty": 500000,
            "source": "test_mcp",
            "retrieval_timestamp": "2026-10-25T12:00:00Z"
        }
        self.db.upsert_ohlcv_records([rec1])

        # Updated close price
        rec2 = dict(rec1)
        rec2["close"] = 3535.0
        self.db.upsert_ohlcv_records([rec2])

        rows = self.db.get_stock_history("TCS")
        self.assertEqual(len(rows), 1, "Should only have 1 row after upsert")
        self.assertEqual(rows[0]["close"], 3535.0, "Close price should be updated")

    def test_audit_logging(self):
        log_id = self.db.record_audit_log(
            source="test_mcp",
            endpoint="https://test.mcp/endpoint",
            symbol="INFY",
            date_range_start="2025-10-23",
            date_range_end="2026-10-23",
            records_retrieved=245,
            records_accepted=245,
            records_rejected=0,
            validation_summary={"status": "clean"},
            raw_payload_path="data/raw/test.json",
            status="SUCCESS",
            created_at="2026-10-25T12:00:00Z"
        )
        self.assertGreater(log_id, 0)

        with self.db.get_connection() as conn:
            row = conn.execute("SELECT * FROM ingestion_audit_log WHERE log_id = ?", (log_id,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["symbol"], "INFY")
            self.assertEqual(row["records_accepted"], 245)

if __name__ == "__main__":
    unittest.main()
