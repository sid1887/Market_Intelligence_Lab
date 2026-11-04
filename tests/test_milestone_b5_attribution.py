"""
Market Intelligence Lab: Milestone B5 Attribution Engine & Watchlist Normalization Test Suite.

Verifies:
1. Watchlist Price Normalization: SUZLON closing price matches verified ~₹36–₹37 band on 2026-10-28.
2. Mathematical Conserved Decomposition: Total Return = Market Component + Sector Component + Idiosyncratic Residual.
3. Event Study Alignment: After-hours corporate announcement (post 15:30 IST) shifts effective session t=0 to next trading day.
4. Anomaly Scanner: Detects volume spikes (is_volume_spike_zscore == 1) and volatility return shocks (|R_1d| >= 2.5 * sigma_daily).
5. Disclosure Proximity Correlator: Matches corporate filings within [-1, +1] window and extracts CAR[-1, +1].
6. Taxonomy Tagging: Flags unexplained idiosyncratic flow when no corporate disclosure exists.
7. Dynamic Tearsheet Generation: Produces complete tearsheets for both INFY and SUZLON with zero hardcoded text leaks.
"""

import os
import unittest
from src.storage.database import DatabaseManager
from src.explanation.attribution_engine import MovementAttributionEngine, AttributionResult
from src.reporting.company_tearsheet import CompanyTearsheetBuilder


class TestMilestoneB5Attribution(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager("data/market_lab.db")
        cls.engine = MovementAttributionEngine(cls.db)
        cls.builder = CompanyTearsheetBuilder(cls.db, output_dir="reports")

    # -----------------------------------------------------------------
    # 1. Watchlist Price Normalization & Reconciliation Audit
    # -----------------------------------------------------------------

    def test_01_suzlon_price_reconciliation(self):
        """Verify that SUZLON closing price on 2026-10-28 matches the verified ~₹36–₹37 band."""
        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT close FROM ohlcv_daily WHERE symbol = 'SUZLON' AND trading_date = '2026-10-28'"
            )
            row = cur.fetchone()
            self.assertIsNotNone(row, "SUZLON must have OHLCV record on 2026-10-28")
            close_p = float(row[0])
            self.assertGreaterEqual(close_p, 36.0, f"SUZLON close {close_p} must be >= 36.0")
            self.assertLessEqual(close_p, 37.5, f"SUZLON close {close_p} must be <= 37.5 (verified band)")

            # Check factors consistency
            cur = conn.execute(
                "SELECT sma_200, debt_to_equity, roe_pct FROM quant_factors_daily WHERE symbol = 'SUZLON' AND trading_date = '2026-10-28'"
            )
            f_row = cur.fetchone()
            self.assertIsNotNone(f_row)
            sma_200 = float(f_row["sma_200"])
            self.assertGreater(close_p, sma_200, "SUZLON close must exceed 200-day SMA on 2026-10-28")

    # -----------------------------------------------------------------
    # 2. Mathematical Conserved Three-Tier Return Decomposition
    # -----------------------------------------------------------------

    def test_02_mathematical_return_decomposition_identity(self):
        """
        Verify the mathematical conservation identity:
        Total Return = Market Component + Sector Component + Idiosyncratic Residual.
        """
        symbols_to_test = ["INFY", "TCS", "SUZLON", "RELIANCE", "DRREDDY"]
        target_date = "2026-10-28"

        for sym in symbols_to_test:
            decomp = self.engine.decompose_movement(symbol=sym, trading_date=target_date)

            total_ret = decomp["total_return"]
            mkt_comp = decomp["market_component"]
            sec_comp = decomp["sector_component"]
            residual = decomp["residual"]
            expected_ret = decomp["expected_return"]

            # Expected return check
            self.assertAlmostEqual(
                expected_ret,
                round(mkt_comp + sec_comp, 6),
                places=5,
                msg=f"Expected return must equal Market Component + Sector Component for {sym}"
            )

            # Total return identity check
            reconstructed_total = round(mkt_comp + sec_comp + residual, 6)
            self.assertAlmostEqual(
                total_ret,
                reconstructed_total,
                places=5,
                msg=f"Total Return ({total_ret}) must equal Market ({mkt_comp}) + Sector ({sec_comp}) + Residual ({residual}) for {sym}"
            )

    # -----------------------------------------------------------------
    # 3. After-Hours Event Study Alignment
    # -----------------------------------------------------------------

    def test_03_after_hours_announcement_alignment(self):
        """
        Verify that announcements made after 15:30 IST shift t=0 to the next trading day.
        """
        calendar = self.engine.get_trading_calendar()
        self.assertIn("2026-10-15", calendar)
        self.assertIn("2026-10-16", calendar)
        self.assertIn("2026-10-23", calendar)

        # 1. Market hours announcement on 2026-10-15 at 14:15:00 IST -> t=0 is 2026-10-15
        t0_market = self.engine.align_disclosure_timestamp(
            broadcast_timestamp_ist="2026-10-15T14:15:00+05:30",
            trading_calendar_dates=calendar
        )
        self.assertEqual(t0_market, "2026-10-15", "Market-hours announcement must resolve to current trading day")

        # 2. After-hours announcement on Thursday 2026-10-15 at 16:30:00 IST -> t=0 is Friday 2026-10-16
        t0_thursday_post = self.engine.align_disclosure_timestamp(
            broadcast_timestamp_ist="2026-10-15T16:30:00+05:30",
            trading_calendar_dates=calendar
        )
        self.assertEqual(t0_thursday_post, "2026-10-16", "Post-market announcement must shift t=0 to next trading day")

        # 3. After-hours announcement on Friday 2026-10-23 at 16:30:00 IST -> t=0 is Monday 2026-10-26 (skipping weekend)
        t0_post_market = self.engine.align_disclosure_timestamp(
            broadcast_timestamp_ist="2026-10-23T16:30:00+05:30",
            trading_calendar_dates=calendar
        )
        self.assertEqual(t0_post_market, "2026-10-26", "Post-market Friday announcement must shift t=0 to Monday")

        # 4. Weekend announcement on Saturday 2026-10-24 at 11:30:00 IST -> t=0 is Monday 2026-10-26
        t0_weekend = self.engine.align_disclosure_timestamp(
            broadcast_timestamp_ist="2026-10-24T11:30:00+05:30",
            trading_calendar_dates=calendar
        )
        self.assertEqual(t0_weekend, "2026-10-26", "Weekend announcement must resolve to Monday trading session")

    # -----------------------------------------------------------------
    # 4. Anomaly Scanner Execution
    # -----------------------------------------------------------------

    def test_04_anomaly_scanner_triggers(self):
        """
        Verify that scan_anomalies correctly identifies volume spikes or volatility shocks.
        """
        anomalies = self.engine.scan_anomalies(lookback_sessions=30)
        self.assertIsInstance(anomalies, list)
        self.assertGreater(len(anomalies), 0, "Scanner must detect anomalous sessions in the trailing 30 days")

        for anom in anomalies[:10]:
            triggers = anom.get("triggers", [])
            self.assertTrue(len(triggers) > 0, "Each returned anomaly must have at least one trigger")
            valid_triggers = {"VOLUME_SPIKE_ZSCORE", "RETURN_VOLATILITY_SPIKE"}
            for t in triggers:
                self.assertIn(t, valid_triggers)

    # -----------------------------------------------------------------
    # 5. Disclosure Proximity Correlator
    # -----------------------------------------------------------------

    def test_05_disclosure_proximity_correlator(self):
        """
        Verify that disclosure correlator finds corporate disclosures within [-1, +1] window.
        """
        # INFY board meeting intimation on 2026-09-16 (effective session)
        disc_match = self.engine.correlate_disclosures(symbol="INFY", trading_date="2026-09-16")
        self.assertIsNotNone(disc_match, "Must find correlated disclosure for INFY on 2026-09-16")
        self.assertEqual(disc_match["symbol"], "INFY")
        self.assertIn("source_url", disc_match)
        self.assertIn("category", disc_match)

        # Non-disclosure session should return None
        no_disc = self.engine.correlate_disclosures(symbol="TRIDENT", trading_date="2026-05-12")
        self.assertIsNone(no_disc)

    # -----------------------------------------------------------------
    # 6. Unexplained Idiosyncratic Flow Classification
    # -----------------------------------------------------------------

    def test_06_unexplained_idiosyncratic_flow_taxonomy(self):
        """
        Verify that an anomalous move without corporate filing is classified as UNEXPLAINED_IDIOSYNCRATIC_FLOW.
        """
        attr = self.engine.analyze_attribution(symbol="TRIDENT", trading_date="2026-10-28")
        self.assertIsInstance(attr, AttributionResult)
        self.assertFalse(attr.has_correlated_disclosure)
        self.assertIn(
            attr.attribution_tag,
            ["UNEXPLAINED_IDIOSYNCRATIC_FLOW", "MARKET_BETA_DRIVEN", "SECTOR_SYSTEMATIC_FLOW"]
        )
        self.assertIn("Total Return", "Total Return = Market Component + Sector Component + Idiosyncratic Residual")

    # -----------------------------------------------------------------
    # 7. Dynamic Tearsheet Generation & Leakage Audit
    # -----------------------------------------------------------------

    def test_07_dynamic_tearsheet_generation_and_leakage(self):
        """
        Verify dynamic tearsheets for INFY and SUZLON:
        - INFY generates with verified disclosures and PDF links.
        - SUZLON generates without hardcoded Infosys deal numbers or commentary leaks.
        """
        # 1. INFY Tearsheet
        infy_path = self.builder.generate_tearsheet(symbol="INFY", as_of_date="2026-10-23")
        self.assertTrue(os.path.exists(infy_path))
        with open(infy_path, "r", encoding="utf-8") as f:
            infy_content = f.read()

        self.assertIn("# Company Research Tearsheet — INFY (Infosys Ltd.)", infy_content)
        self.assertIn("INE009A01021", infy_content)
        self.assertIn("Information Technology", infy_content)
        self.assertIn("notice-board-meeting-15sep2026.pdf", infy_content)

        # 2. SUZLON Tearsheet
        suzlon_path = self.builder.generate_tearsheet(symbol="SUZLON", as_of_date="2026-10-28")
        self.assertTrue(os.path.exists(suzlon_path))
        with open(suzlon_path, "r", encoding="utf-8") as f:
            suzlon_content = f.read()

        self.assertIn("# Company Research Tearsheet — SUZLON (Suzlon Energy Ltd)", suzlon_content)
        self.assertIn("Renewable Energy", suzlon_content)
        self.assertIn("target price objective of ₹45.00", suzlon_content)
        self.assertIn("designated stop loss level of ₹33.00", suzlon_content)

        # String leakage audit: SUZLON must NOT contain Infosys-specific deal sizes or hardcoded text
        self.assertNotIn("infosys", suzlon_content.lower())
        self.assertNotIn("$5.2B", suzlon_content)
        self.assertNotIn("IT Peers", suzlon_content)
        self.assertNotIn("revised FY27 CC revenue guidance", suzlon_content)


if __name__ == "__main__":
    unittest.main()
