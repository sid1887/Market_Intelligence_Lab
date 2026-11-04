import unittest
import os
import datetime
from src.storage.database import DatabaseManager
from src.reporting.daily_market_report import DailyMarketReportBuilder
from src.reporting.company_tearsheet import CompanyTearsheetBuilder

class TestMilestone24Reports(unittest.TestCase):
    """
    Acceptance and regression test suite for Milestone 2.4 Research Reports:
    - Daily Market Overview generator produces complete, structured, source-linked reports.
    - Company Tearsheet generator produces detailed single-stock profiles with direct document links.
    - Epistemic boundaries, non-causal language, and disabled execution notices are verified.
    - Verified disclosures vs SOURCE_UNVERIFIED and AWAITING_POST_EVENT_DATA badges are present.
    """

    def setUp(self):
        # Point to the actual local lab database
        self.db = DatabaseManager("data/market_lab.db")
        self.output_dir = "reports"
        self.daily_builder = DailyMarketReportBuilder(self.db, output_dir=self.output_dir)
        self.tearsheet_builder = CompanyTearsheetBuilder(self.db, output_dir=self.output_dir)

    def test_daily_market_overview_generation(self):
        """
        Verifies Daily Market Overview generation, sections, and metrics.
        """
        report_path = self.daily_builder.generate_report(as_of_date="2026-10-23", index_name="NIFTY 50", benchmark_mode="PRI")
        self.assertTrue(os.path.exists(report_path))
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check key sections
        self.assertIn("# Daily Market Overview — NIFTY 50", content)
        self.assertIn("## 1. Benchmark Index Performance & Market Pulse", content)
        self.assertIn("## 2. Market Breadth & Moving Average Participation", content)
        self.assertIn("## 3. Relative Strength Leaderboards (Excess Return vs Nifty 50)", content)
        self.assertIn("## 4. Statistical Volume Anomaly Scanner", content)
        self.assertIn("## 5. Corporate Disclosures & Material Filings Audit", content)
        self.assertIn("## 6. Explanatory Hypotheses & Epistemic Boundaries", content)

        # Check key metrics
        self.assertIn("50 / 50", content)  # 100% coverage
        self.assertIn("100.0%", content)
        self.assertIn("Advance / Decline Ratio", content)
        self.assertIn("TCS", content)
        self.assertIn("Non-Execution Notice", content)
        self.assertIn("Strictly Disabled", content)

    def test_company_tearsheet_generation(self):
        """
        Verifies Company Tearsheet generation for INFY with direct PDF links,
        revenue growth fields, and event study guardrails.
        """
        tearsheet_path = self.tearsheet_builder.generate_tearsheet(symbol="INFY", as_of_date="2026-10-23", benchmark_name="NIFTY 50")
        self.assertTrue(os.path.exists(tearsheet_path))
        with open(tearsheet_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Check security profile
        self.assertIn("# Company Research Tearsheet — INFY (Infosys Ltd.)", content)
        self.assertIn("INE009A01021", content)
        self.assertIn("Information Technology", content)

        # Check direct PDF URLs
        self.assertIn("notice-board-meeting-15sep2026.pdf", content)
        self.assertIn("outcome-board-meeting23oct2026.pdf", content)

        # Check separated revenue fields and audit status
        self.assertIn("AUDITED", content)
        self.assertIn("CC YoY: `+1.5%`", content)
        self.assertIn("Reported YoY: `+10.7%`", content)
        self.assertIn("₹26.00/sh", content)
        self.assertIn("21.0%", content)

        # Check event study guardrail badges
        self.assertIn("SOURCE_UNVERIFIED", content)
        self.assertIn("AWAITING_POST_EVENT_DATA", content)

        # Check corporate action quarantine note
        self.assertIn("Future Dividend Quarantine", content)
        self.assertIn("Record Date: Nov 3, 2026", content)

        # Check epistemic disclaimer
        self.assertIn("Epistemic Limitation", content)
        self.assertIn("Permanently Disabled", content)

if __name__ == "__main__":
    unittest.main()
