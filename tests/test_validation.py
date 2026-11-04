import unittest
from src.client.validator import RecordValidator
from src.quant.calendar import validate_trading_calendar, is_trading_holiday

class TestValidation(unittest.TestCase):
    """Unit tests for record validation invariants, null handling, and trading calendar checks."""

    def setUp(self):
        self.validator = RecordValidator()

    def test_valid_record(self):
        raw = {
            "date": "2026-10-23",
            "symbol": "INFY",
            "series": "EQ",
            "open": 1150.0,
            "high": 1160.0,
            "low": 1140.0,
            "close": 1155.0,
            "volume": 2000000,
            "totalTradedValue": 2300000000.0,
            "deliveryQty": 800000
        }
        valid, cleaned, err = self.validator.validate_record(raw)
        self.assertTrue(valid)
        self.assertIsNone(err)
        self.assertEqual(cleaned["symbol"], "INFY")
        self.assertEqual(cleaned["delivery_qty"], 800000)

    def test_unavailable_delivery_quantity_stored_as_none(self):
        """When delivery quantity is 0 on a high volume day in NSE MCP, it is treated as unavailable (None)."""
        raw = {
            "date": "2026-10-23",
            "symbol": "INFY",
            "series": "EQ",
            "open": 1150.0,
            "high": 1160.0,
            "low": 1140.0,
            "close": 1155.0,
            "volume": 2000000,
            "deliveryQty": 0  # Unpopulated in stream
        }
        valid, cleaned, err = self.validator.validate_record(raw)
        self.assertTrue(valid)
        self.assertIsNone(cleaned["delivery_qty"], "delivery_qty must be None/NULL, not 0")

    def test_invalid_high_low_invariant(self):
        """High price cannot be less than low price."""
        raw = {
            "date": "2026-10-23",
            "symbol": "INFY",
            "series": "EQ",
            "open": 1150.0,
            "high": 1130.0,  # Invalid: high < low
            "low": 1140.0,
            "close": 1135.0,
            "volume": 1000
        }
        valid, cleaned, err = self.validator.validate_record(raw)
        self.assertFalse(valid)
        self.assertIn("lower than low price", err)

    def test_duplicate_rejection(self):
        raw = {
            "date": "2026-10-23",
            "symbol": "INFY",
            "series": "EQ",
            "open": 100.0, "high": 110.0, "low": 90.0, "close": 105.0, "volume": 100
        }
        valid1, _, _ = self.validator.validate_record(raw)
        self.assertTrue(valid1)

        valid2, _, err2 = self.validator.validate_record(raw)
        self.assertFalse(valid2)
        self.assertIn("Duplicate observation", err2)

    def test_trading_calendar_holiday_recognition(self):
        # 2026-01-26 is Republic Day (Monday).
        # Sequence: Friday 2026-01-23 -> Tuesday 2026-01-27
        dates = ["2026-01-23", "2026-01-27"]
        val = validate_trading_calendar(dates)

        # 2026-01-26 is missing, but recognized as a known holiday!
        self.assertEqual(val["known_holidays_count"], 1)
        self.assertEqual(val["known_holidays"][0]["date"], "2026-01-26")
        self.assertEqual(val["known_holidays"][0]["reason"], "Republic Day")
        self.assertEqual(val["unexpected_missing_count"], 0)
        self.assertTrue(val["valid"])

if __name__ == "__main__":
    unittest.main()
