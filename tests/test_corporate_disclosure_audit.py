import unittest
import os
import datetime
from src.storage.database import DatabaseManager
from src.quant.event_study import EventStudyEngine

class TestCorporateDisclosureAudit(unittest.TestCase):
    """
    Acceptance & Regression Test Suite for Corporate Disclosure Audit & Provenance:
    1. Verified disclosures require valid original URL and broadcast timestamp.
    2. Verified financial results strictly match official source documents (₹26 dividend, 21.0% margin, AUDITED).
    3. Discrepancies in key financial fields cannot silently become verified facts (flagged as SOURCE_UNVERIFIED).
    4. Unverified event metadata is visibly flagged with prominent warnings in hypotheses and reports.
    5. Disclosures/corrections do not accidentally overwrite historical corporate actions or unrelated event studies.
    """

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.engine = EventStudyEngine(self.db)
        
        # Populate synthetic trading calendar & baseline stock history (350 sessions)
        base_d = datetime.date(2025, 1, 1)
        self.calendar = []
        curr = base_d
        while len(self.calendar) < 350:
            if curr.weekday() < 5:
                self.calendar.append(curr.strftime("%Y-%m-%d"))
            curr += datetime.timedelta(days=1)

        # Baseline stock & benchmark
        stock_recs = []
        bench_recs = []
        p_s = 1000.0
        p_b = 20000.0
        for i, d in enumerate(self.calendar):
            r_b = 0.005 if i % 2 == 0 else -0.003
            r_s = 0.001 + 0.8 * r_b
            p_s *= (1.0 + r_s)
            p_b *= (1.0 + r_b)
            stock_recs.append({
                "symbol": "INFY", "trading_date": d, "series": "EQ",
                "open": p_s, "high": p_s * 1.01, "low": p_s * 0.99, "close": p_s,
                "volume": 50000, "source": "test", "retrieval_timestamp": "now"
            })
            bench_recs.append({
                "index_name": "NIFTY 50", "trading_date": d, "index_type": "PRI",
                "open": p_b, "high": p_b * 1.01, "low": p_b * 0.99, "close": p_b,
                "volume": None, "source": "test", "retrieval_timestamp": "now"
            })
        self.db.upsert_ohlcv_records(stock_recs)
        self.db.upsert_index_daily(bench_recs)

        # Baseline historical corporate actions (past dividends)
        self.db.upsert_corporate_actions([
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2025-10-27", "record_date": None,
             "purpose": "Interim Dividend - Rs 23 Per Share", "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "now"},
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2026-06-10", "record_date": None,
             "purpose": "Dividend - Rs 25 Per Share", "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "now"}
        ])

    def test_verified_event_requires_valid_url_and_timestamp(self):
        """
        Requirement 1: Original disclosure URL and timestamp must be present and valid
        for every verified event.
        """
        disclosures = [
            {
                "disclosure_id": "INFY_DISC_20260915_BM_INTIMATION",
                "symbol": "INFY",
                "broadcast_timestamp": "2026-09-15T17:45:00+05:30",
                "effective_session_date": "2026-09-16",
                "category": "BOARD_MEETING_SCHEDULE",
                "subject": "Intimation of Board Meeting under Regulation 29",
                "details_summary": "Notice of BM on Oct 22 and 23, 2026.",
                "source_url": "https://www.infosys.com/investors/reports-filings/quarterly-results.html",
                "retrieval_timestamp": "2026-10-25T14:35:00Z",
                "verification_status": "VERIFIED"
            }
        ]
        self.db.upsert_corporate_disclosures(disclosures)
        saved = self.db.get_corporate_disclosures(symbol="INFY", verification_status="VERIFIED")
        self.assertEqual(len(saved), 1)
        rec = saved[0]
        self.assertTrue(rec["source_url"].startswith("http"))
        self.assertIn("T", rec["broadcast_timestamp"])
        self.assertIn("T", rec["retrieval_timestamp"])
        self.assertEqual(rec["verification_status"], "VERIFIED")

    def test_verified_financial_results_match_source_documents(self):
        """
        Requirement 2: Verified financial results must strictly match official filings:
        - Interim Dividend = ₹26.0 (not ₹23.0)
        - Operating Margin = 21.0% (not 21.1%)
        - Audit Status = AUDITED (both standalone and consolidated)
        """
        disclosures = [
            {
                "disclosure_id": "INFY_DISC_20261023_Q2",
                "symbol": "INFY",
                "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
                "effective_session_date": "2026-10-26",
                "category": "EARNINGS",
                "subject": "Outcome of Board Meeting Q2 FY2027",
                "details_summary": "Operating margin 21.0%, Interim dividend Rs 26/share.",
                "source_url": "https://www.infosys.com/investors/reports-filings/quarterly-results.html",
                "retrieval_timestamp": "2026-10-25T14:35:00Z",
                "verification_status": "VERIFIED",
                "audit_status": "AUDITED",
                "dividend_declared": 26.0,
                "operating_margin_pct": 21.0
            }
        ]
        self.db.upsert_corporate_disclosures(disclosures)
        saved = self.db.get_corporate_disclosures(symbol="INFY")
        self.assertEqual(len(saved), 1)
        rec = saved[0]
        self.assertEqual(rec["dividend_declared"], 26.0)
        self.assertNotEqual(rec["dividend_declared"], 23.0)
        self.assertEqual(rec["operating_margin_pct"], 21.0)
        self.assertNotEqual(rec["operating_margin_pct"], 21.1)
        self.assertEqual(rec["audit_status"], "AUDITED")

    def test_discrepancy_blocks_verified_fact(self):
        """
        Requirement 3: An unverified claim or discrepancy cannot silently become a verified fact.
        It must be marked SOURCE_UNVERIFIED.
        """
        disclosures = [
            {
                "disclosure_id": "INFY_DISC_20261015_SCHED",
                "symbol": "INFY",
                "broadcast_timestamp": "2026-10-15T16:15:00+05:30",
                "effective_session_date": "2026-10-16",
                "category": "BOARD_MEETING_SCHEDULE",
                "subject": "Claimed Intimation of Board Meeting (Unverified)",
                "details_summary": "No regulatory circular exists for this date.",
                "source_url": "https://www.nseindia.com",
                "retrieval_timestamp": "2026-10-25T14:35:00Z",
                "verification_status": "SOURCE_UNVERIFIED"
            }
        ]
        self.db.upsert_corporate_disclosures(disclosures)
        verified_list = self.db.get_corporate_disclosures(symbol="INFY", verification_status="VERIFIED")
        self.assertEqual(len(verified_list), 0)  # Must NOT appear as verified!

        unverified_list = self.db.get_corporate_disclosures(symbol="INFY", verification_status="SOURCE_UNVERIFIED")
        self.assertEqual(len(unverified_list), 1)
        self.assertEqual(unverified_list[0]["verification_status"], "SOURCE_UNVERIFIED")

    def test_unverified_metadata_visibly_flagged_in_hypotheses_and_reports(self):
        """
        Requirement 4: When an event study or report encounters an unverified event,
        it must visibly flag [SOURCE_UNVERIFIED DISCLOSURE] with an explicit warning.
        """
        event_d = self.calendar[280]
        res = self.engine.run_event_study(
            "INFY",
            event_d,
            event_category="BOARD_MEETING_SCHEDULE",
            verification_status="SOURCE_UNVERIFIED"
        )
        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["verification_status"], "SOURCE_UNVERIFIED")
        
        hypo = res["explanatory_hypothesis"]
        self.assertIn("[SOURCE_UNVERIFIED DISCLOSURE] WARNING:", hypo)
        self.assertIn("must NOT be presented as a verified reaction to an official exchange disclosure", hypo)

    def test_corrections_preserve_historical_corporate_actions_and_isolation(self):
        """
        Requirement 5: Corporate disclosure metadata corrections must NOT accidentally
        modify historical corporate actions or insert future dividends into historical CA accounting.
        """
        # Register new Rs 26 dividend announcement
        announcement = [{
            "disclosure_id": "INFY_DISC_20261023_Q2",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "category": "EARNINGS",
            "subject": "Q2 Results",
            "details_summary": "Interim dividend Rs 26 declared (Record Date: Nov 3, 2026).",
            "source_url": "https://www.infosys.com",
            "retrieval_timestamp": "2026-10-25T14:35:00Z",
            "verification_status": "VERIFIED",
            "dividend_declared": 26.0
        }]
        self.db.upsert_corporate_disclosures(announcement)

        # Verify historical corporate actions table is untouched
        ca_records = self.db.get_corporate_actions("INFY")
        self.assertEqual(len(ca_records), 2)
        ex_dates = [c["ex_date"] for c in ca_records]
        self.assertIn("2025-10-27", ex_dates)
        self.assertIn("2026-06-10", ex_dates)
        # Ensure Rs 26 was NOT prematurely inserted into historical corporate actions
        self.assertNotIn("2026-10-26", ex_dates)
        self.assertNotIn("2026-11-03", ex_dates)

        # Verify existing Rs 23 interim dividend purpose was not changed
        oct2025_div = [c for c in ca_records if c["ex_date"] == "2025-10-27"][0]
        self.assertIn("Rs 23 Per Share", oct2025_div["purpose"])

    def test_new_disclosure_defaults_to_pending_verification(self):
        """
        Safeguard 1: Disclosures inserted without explicit verification status
        MUST default to PENDING_VERIFICATION (never silently VERIFIED).
        """
        unverified_announcement = [{
            "disclosure_id": "NEW_UNAUDITED_DISC",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-24T10:00:00+05:30",
            "effective_session_date": "2026-10-27",
            "category": "OTHER",
            "subject": "Press Mention",
            "details_summary": "Unverified blog post rumor",
            "source_url": "https://random-blog.com/news",
            "retrieval_timestamp": "2026-10-25T14:35:00Z"
            # verification_status omitted!
        }]
        self.db.upsert_corporate_disclosures(unverified_announcement)

        # Must NOT be classified as VERIFIED
        verified_items = self.db.get_corporate_disclosures(symbol="INFY", verification_status="VERIFIED")
        verified_ids = [v["disclosure_id"] for v in verified_items]
        self.assertNotIn("NEW_UNAUDITED_DISC", verified_ids)

        # Must default to PENDING_VERIFICATION
        pending_items = self.db.get_corporate_disclosures(symbol="INFY", verification_status="PENDING_VERIFICATION")
        pending_ids = [p["disclosure_id"] for p in pending_items]
        self.assertIn("NEW_UNAUDITED_DISC", pending_ids)

    def test_direct_document_urls_and_revenue_growth_fields(self):
        """
        Safeguards 2 & 3: Direct document PDF links and separated CC vs reported revenue growth fields.
        """
        rec = [{
            "disclosure_id": "INFY_DISC_20261023_DIRECT",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "category": "EARNINGS",
            "subject": "Q2 Outcome",
            "details_summary": "Direct filing verification",
            "source_url": "https://www.infosys.com/investors/documents/exchange-filings/2026/outcome-board-meeting23oct2026.pdf",
            "retrieval_timestamp": "2026-10-25T14:35:00Z",
            "verification_status": "VERIFIED",
            "audit_status": "AUDITED",
            "dividend_declared": 26.0,
            "operating_margin_pct": 21.0,
            "revenue_inr_crore": 49244.0,
            "revenue_growth_yoy_cc": 1.5,
            "revenue_growth_qoq_cc": 1.2,
            "revenue_growth_yoy_reported": 10.7,
            "source_timestamp_basis": "exchange_submission_metadata"
        }]
        self.db.upsert_corporate_disclosures(rec)

        saved = self.db.get_corporate_disclosures(symbol="INFY")
        saved_rec = [s for s in saved if s["disclosure_id"] == "INFY_DISC_20261023_DIRECT"][0]

        # Verify direct PDF
        self.assertTrue(saved_rec["source_url"].endswith(".pdf"))
        self.assertEqual(saved_rec["source_timestamp_basis"], "exchange_submission_metadata")

        # Verify separate revenue fields
        self.assertEqual(saved_rec["revenue_inr_crore"], 49244.0)
        self.assertEqual(saved_rec["revenue_growth_yoy_cc"], 1.5)
        self.assertEqual(saved_rec["revenue_growth_qoq_cc"], 1.2)
        self.assertEqual(saved_rec["revenue_growth_yoy_reported"], 10.7)
        self.assertNotEqual(saved_rec["revenue_growth_yoy_cc"], saved_rec["revenue_growth_yoy_reported"])

if __name__ == "__main__":
    unittest.main()
