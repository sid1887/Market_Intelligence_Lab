import unittest
import os
import sqlite3
import datetime
from src.storage.database import DatabaseManager
from src.client.validator import RecordValidator
from src.quant.event_study import EventStudyEngine

class TestMilestoneB32CorporateActionsAndDisclosures(unittest.TestCase):
    """
    Comprehensive regression and acceptance test suite for Milestone B3.2:
    - Corporate actions ingestion, normalization, and deduplication
    - Schema defaults and column migrations
    - Corporate disclosures validation, governance, and verification status safety
    - Downstream isolation of unverified disclosures and declared future events
    - Raw price preservation across corporate action events
    - Audit log traceability and exact count reconciliation
    """

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.validator = RecordValidator()

    def test_schema_defaults_and_columns(self):
        """1. Verify corporate_disclosures defaults to PENDING_VERIFICATION and corporate_actions has announcement/effective dates."""
        with self.db.get_connection() as conn:
            # Check corporate_disclosures DDL
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='corporate_disclosures';")
            ddl = cursor.fetchone()[0]
            self.assertIn("DEFAULT 'PENDING_VERIFICATION'", ddl)

            # Insert disclosure omitting verification_status
            conn.execute("""
                INSERT INTO corporate_disclosures (
                    disclosure_id, symbol, broadcast_timestamp, effective_session_date,
                    category, subject, retrieval_timestamp
                ) VALUES (
                    'TEST_DISC_01', 'INFY', '2026-10-23T16:30:00+05:30', '2026-10-26',
                    'EARNINGS', 'Q2 Results', '2026-10-26T12:00:00Z'
                );
            """)
            cursor = conn.execute("SELECT verification_status FROM corporate_disclosures WHERE disclosure_id = 'TEST_DISC_01';")
            self.assertEqual(cursor.fetchone()[0], "PENDING_VERIFICATION")

            # Check corporate_actions columns
            cursor = conn.execute("PRAGMA table_info(corporate_actions);")
            cols = {r["name"] for r in cursor.fetchall()}
            self.assertIn("announcement_date", cols)
            self.assertIn("effective_date", cols)
            self.assertIn("adjustment_factor", cols)

            # Check index exists
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_ca_action_type';")
            self.assertIsNotNone(cursor.fetchone())

    def test_corporate_action_validation_rules(self):
        """2. Validate corporate action records against format rules and financial invariants."""
        # A. Valid Dividend
        valid_div = {
            "symbol": "INFY",
            "exDate": "2025-10-27",
            "actionType": "DIVIDEND",
            "purpose": "Interim Dividend - Rs 23 Per Share",
            "adjustmentFactor": 1.0,
            "recordDate": "2025-10-28"
        }
        ok, cleaned, err = self.validator.validate_corporate_action(valid_div)
        self.assertTrue(ok)
        self.assertIsNone(err)
        self.assertEqual(cleaned["action_type"], "DIVIDEND")
        self.assertEqual(cleaned["adjustment_factor"], 1.0)
        self.assertEqual(cleaned["record_date"], "2025-10-28")

        # B. Valid Bonus with fractional adjustment factor
        valid_bonus = {
            "symbol": "RELIANCE",
            "exDate": "2024-10-28",
            "actionType": "bonus",  # lowercase normalization
            "purpose": "Bonus 1:1",
            "adjustmentFactor": "0.5"  # string to float coercion
        }
        ok, cleaned, err = self.validator.validate_corporate_action(valid_bonus)
        self.assertTrue(ok)
        self.assertEqual(cleaned["action_type"], "BONUS")
        self.assertEqual(cleaned["adjustment_factor"], 0.5)

        # C. Rejection: Invalid ex-date format
        bad_date = {
            "symbol": "TCS",
            "exDate": "28/10/2024",
            "actionType": "DIVIDEND",
            "purpose": "Interim Dividend",
            "adjustmentFactor": 1.0
        }
        ok, cleaned, err = self.validator.validate_corporate_action(bad_date)
        self.assertFalse(ok)
        self.assertIn("Invalid exDate format", err)

        # D. Rejection: Non-positive adjustment factor
        bad_factor = {
            "symbol": "TCS",
            "exDate": "2025-01-17",
            "actionType": "SPLIT",
            "purpose": "Split",
            "adjustmentFactor": 0.0
        }
        ok, cleaned, err = self.validator.validate_corporate_action(bad_factor)
        self.assertFalse(ok)
        self.assertIn("Non-positive adjustmentFactor", err)

        # E. Rejection: Missing symbol
        bad_sym = {
            "symbol": "",
            "exDate": "2025-01-17",
            "actionType": "DIVIDEND",
            "purpose": "Dividend"
        }
        ok, cleaned, err = self.validator.validate_corporate_action(bad_sym)
        self.assertFalse(ok)
        self.assertIn("Missing or invalid symbol", err)

        # F. Rejection: Derivatives/futures lot multiplier (> 1.0) mistakenly supplied for bonus/split
        futures_multiplier = {
            "symbol": "RELIANCE",
            "exDate": "2024-10-28",
            "actionType": "BONUS",
            "purpose": "Bonus 1:1",
            "adjustmentFactor": 2.0  # exchange derivatives lot factor, NOT historical price multiplier
        }
        ok, cleaned, err = self.validator.validate_corporate_action(futures_multiplier)
        self.assertFalse(ok)
        self.assertIn("historical-price multiplier must be <= 1.0", err)

    def test_corporate_action_deduplication(self):
        """3. Enforce deduplication on natural key (symbol, action_type, ex_date, purpose)."""
        ca_1 = {
            "symbol": "NESTLEIND",
            "exDate": "2026-07-10",
            "actionType": "DIVIDEND",
            "purpose": "Dividend - Rs 5 Per Share",
            "adjustmentFactor": 1.0
        }
        ca_special = {
            "symbol": "NESTLEIND",
            "exDate": "2026-07-10",
            "actionType": "DIVIDEND",
            "purpose": "Special Dividend - Rs 2 Per Share",
            "adjustmentFactor": 1.0
        }
        ca_exact_dup = {
            "symbol": "NESTLEIND",
            "exDate": "2026-07-10",
            "actionType": "DIVIDEND",
            "purpose": "Dividend - Rs 5 Per Share",  # identical purpose
            "adjustmentFactor": 1.0
        }

        # Step A: Distinct declarations sharing ex-date are BOTH accepted
        accepted, rejected, summary = self.validator.validate_corporate_actions_batch([ca_1, ca_special])
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len(rejected), 0)
        self.assertEqual(summary["total_input"], 2)
        self.assertEqual(summary["accepted_count"], 2)
        self.assertEqual(summary["rejected_count"], 0)

        # Step B: True duplicate (identical purpose) is rejected
        accepted_dup, rejected_dup, summary_dup = self.validator.validate_corporate_actions_batch([ca_exact_dup])
        self.assertEqual(len(accepted_dup), 0)
        self.assertEqual(len(rejected_dup), 1)
        self.assertIn("Duplicate corporate action", rejected_dup[0]["error"])

    def test_corporate_action_idempotent_upsert(self):
        """4. Verify that multiple upserts produce identical row counts and handle updates."""
        actions = [
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2025-10-27", "purpose": "Interim Dividend Rs 23",
             "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "2026-10-26T00:00:00Z"},
            {"symbol": "RELIANCE", "action_type": "BONUS", "ex_date": "2024-10-28", "purpose": "Bonus 1:1",
             "adjustment_factor": 0.5, "source": "test", "retrieval_timestamp": "2026-10-26T00:00:00Z"}
        ]
        # First upsert
        c1 = self.db.upsert_corporate_actions(actions)
        self.assertEqual(c1, 2)
        self.assertEqual(len(self.db.get_corporate_actions()), 2)

        # Second upsert of identical records
        c2 = self.db.upsert_corporate_actions(actions)
        self.assertEqual(c2, 2)
        self.assertEqual(len(self.db.get_corporate_actions()), 2)

        # Update fields on conflict (matching the 4-column natural key)
        updated_actions = [
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2025-10-27", "purpose": "Interim Dividend Rs 23",
             "record_date": "2025-10-28", "adjustment_factor": 1.0, "source": "test",
             "retrieval_timestamp": "2026-10-26T01:00:00Z", "announcement_date": "2025-10-15"}
        ]
        self.db.upsert_corporate_actions(updated_actions)
        self.assertEqual(len(self.db.get_corporate_actions()), 2)
        infy_ca = self.db.get_corporate_actions("INFY")[0]
        self.assertEqual(infy_ca["purpose"], "Interim Dividend Rs 23")
        self.assertEqual(infy_ca["record_date"], "2025-10-28")
        self.assertEqual(infy_ca["announcement_date"], "2025-10-15")

    def test_corporate_disclosure_validation_and_safety(self):
        """5. Validate disclosure fields and enforce verification status safety."""
        # A. Valid pending disclosure
        pending_disc = {
            "disclosure_id": "DISC_001",
            "symbol": "TCS",
            "broadcast_timestamp": "2026-10-10T17:00:00+05:30",
            "effective_session_date": "2026-10-11",
            "category": "EARNINGS",
            "subject": "Q2 Results Intimation"
        }
        ok, cleaned, err = self.validator.validate_corporate_disclosure(pending_disc)
        self.assertTrue(ok)
        self.assertEqual(cleaned["verification_status"], "PENDING_VERIFICATION")

        # B. Valid VERIFIED disclosure with source_url
        verified_disc = {
            "disclosure_id": "DISC_002",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "category": "EARNINGS",
            "subject": "Audited Financial Results",
            "verification_status": "VERIFIED",
            "source_url": "https://www.infosys.com/investors/filings/q2.pdf",
            "dividend_declared": 26.0,
            "operating_margin_pct": 21.0
        }
        ok, cleaned, err = self.validator.validate_corporate_disclosure(verified_disc)
        self.assertTrue(ok)
        self.assertEqual(cleaned["verification_status"], "VERIFIED")
        self.assertEqual(cleaned["dividend_declared"], 26.0)

        # C. Rejection: VERIFIED status without source_url
        unbacked_verified = {
            "disclosure_id": "DISC_003",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "category": "EARNINGS",
            "subject": "Audited Financial Results",
            "verification_status": "VERIFIED",
            "source_url": ""  # empty URL forbidden for VERIFIED
        }
        ok, cleaned, err = self.validator.validate_corporate_disclosure(unbacked_verified)
        self.assertFalse(ok)
        self.assertIn("VERIFIED status requires a non-empty source_url", err)

        # D. Rejection: Negative dividend declared
        negative_div = {
            "disclosure_id": "DISC_004",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "category": "EARNINGS",
            "dividend_declared": -10.0
        }
        ok, cleaned, err = self.validator.validate_corporate_disclosure(negative_div)
        self.assertFalse(ok)
        self.assertIn("cannot be negative", err)

    def test_unverified_disclosures_isolated_from_confirmed_models(self):
        """6. Ensure unverified disclosures cannot masquerade as confirmed facts in downstream queries."""
        disclosures = [
            {
                "disclosure_id": "DISC_VERIFIED",
                "symbol": "INFY",
                "broadcast_timestamp": "2026-09-15T17:45:00+05:30",
                "effective_session_date": "2026-09-16",
                "category": "BOARD_MEETING_SCHEDULE",
                "subject": "Verified Intimation",
                "source_url": "https://www.infosys.com/notice.pdf",
                "retrieval_timestamp": "2026-10-25T14:35:00Z",
                "verification_status": "VERIFIED"
            },
            {
                "disclosure_id": "DISC_UNVERIFIED",
                "symbol": "INFY",
                "broadcast_timestamp": "2026-10-15T16:15:00+05:30",
                "effective_session_date": "2026-10-16",
                "category": "BOARD_MEETING_SCHEDULE",
                "subject": "Unverified Intimation",
                "source_url": "https://www.nseindia.com/filings",
                "retrieval_timestamp": "2026-10-25T14:35:00Z",
                "verification_status": "SOURCE_UNVERIFIED"
            },
            {
                "disclosure_id": "DISC_PENDING",
                "symbol": "INFY",
                "broadcast_timestamp": "2026-10-20T10:00:00+05:30",
                "effective_session_date": "2026-10-21",
                "category": "PRESS_RELEASE",
                "subject": "Pending Release",
                "source_url": "https://www.infosys.com/pr.html",
                "retrieval_timestamp": "2026-10-25T14:35:00Z",
                "verification_status": "PENDING_VERIFICATION"
            }
        ]
        self.db.upsert_corporate_disclosures(disclosures)

        # Query only verified disclosures
        verified_only = self.db.get_corporate_disclosures(symbol="INFY", verification_status="VERIFIED")
        self.assertEqual(len(verified_only), 1)
        self.assertEqual(verified_only[0]["disclosure_id"], "DISC_VERIFIED")

        # Unverified disclosures are quarantined
        unverified = self.db.get_corporate_disclosures(symbol="INFY", verification_status="SOURCE_UNVERIFIED")
        self.assertEqual(len(unverified), 1)
        self.assertEqual(unverified[0]["disclosure_id"], "DISC_UNVERIFIED")

        pending = self.db.get_corporate_disclosures(symbol="INFY", verification_status="PENDING_VERIFICATION")
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["disclosure_id"], "DISC_PENDING")

    def test_declared_dividends_quarantined_from_corporate_actions(self):
        """7. Financial Analysis Safety: Declared future dividends are quarantined from corporate_actions until ex-date."""
        # A declared dividend on 2026-10-23 with future record date 2026-11-03
        disc = [{
            "disclosure_id": "INFY_DISC_20261023_Q2",
            "symbol": "INFY",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "category": "EARNINGS",
            "subject": "Audited Results & Interim Dividend Declaration",
            "source_url": "https://www.infosys.com/q2.pdf",
            "retrieval_timestamp": "2026-10-25T14:35:00Z",
            "verification_status": "VERIFIED",
            "dividend_declared": 26.0
        }]
        self.db.upsert_corporate_disclosures(disc)

        # Historical corporate actions in DB
        historical_ca = [
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2024-10-29", "purpose": "Rs 21 Dividend",
             "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "now"},
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2025-05-30", "purpose": "Rs 22 Dividend",
             "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "now"},
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2025-10-27", "purpose": "Rs 23 Dividend",
             "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "now"},
            {"symbol": "INFY", "action_type": "DIVIDEND", "ex_date": "2026-06-10", "purpose": "Rs 25 Dividend",
             "adjustment_factor": 1.0, "source": "test", "retrieval_timestamp": "now"}
        ]
        self.db.upsert_corporate_actions(historical_ca)

        # Verify: Rs 26 is in corporate_disclosures
        cd = self.db.get_corporate_disclosures(symbol="INFY", verification_status="VERIFIED")
        self.assertEqual(cd[0]["dividend_declared"], 26.0)

        # Verify: Rs 26 is NOT in corporate_actions
        cas = self.db.get_corporate_actions(symbol="INFY")
        self.assertEqual(len(cas), 4)
        ex_dates = [c["ex_date"] for c in cas]
        self.assertNotIn("2026-11-03", ex_dates)
        for ca in cas:
            self.assertNotIn("26", ca["purpose"])

    def test_audit_log_reconciliation(self):
        """8. Verify that ingestion audit logs accurately reconcile retrieved, accepted, and rejected counts."""
        log_id = self.db.record_audit_log(
            source="nse_mcp",
            endpoint="get_corporate_actions",
            symbol="NESTLEIND",
            date_range_start="2024-10-21",
            date_range_end="2026-10-23",
            records_retrieved=6,
            records_accepted=5,
            records_rejected=1,
            validation_summary={"accepted_count": 5, "rejected_count": 1},
            raw_payload_path="data/raw/corporate_actions/NESTLEIND.json",
            status="PARTIAL",
            created_at="2026-10-26T15:53:00Z"
        )
        self.assertGreater(log_id, 0)

        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT records_retrieved, records_accepted, records_rejected, status FROM ingestion_audit_log WHERE log_id = ?", (log_id,))
            row = cursor.fetchone()
            self.assertEqual(row["records_retrieved"], 6)
            self.assertEqual(row["records_accepted"], 5)
            self.assertEqual(row["records_rejected"], 1)
            self.assertEqual(row["records_retrieved"], row["records_accepted"] + row["records_rejected"])
            self.assertEqual(row["status"], "PARTIAL")

    def test_adjustment_factor_semantics_and_numerical_scaling(self):
        """9. Numerical verification of adjustment-factor semantics across 1:1 bonus, 1:2 bonus, and 5:1 split."""
        from src.quant.benchmark import calculate_split_bonus_adjustment_factors
        from src.quant.volume import adjust_volume_for_corporate_actions

        # A. 1:1 Bonus Issue (e.g. RELIANCE, factor 0.5)
        # Pre-event price scaled by 0.5, ex-date and post-event unscaled (1.0).
        # Pre-event volume scaled by 1/0.5 = 2.0.
        records_1_1 = [
            {"trading_date": "2024-10-25", "open": 2000.0, "high": 2020.0, "low": 1990.0, "close": 2000.0, "volume": 10000},
            {"trading_date": "2024-10-28", "open": 1040.0, "high": 1060.0, "low": 1030.0, "close": 1050.0, "volume": 25000}  # ex-date
        ]
        ca_1_1 = [{"symbol": "RELIANCE", "action_type": "BONUS", "ex_date": "2024-10-28", "purpose": "Bonus 1:1", "adjustment_factor": 0.5}]

        adj_prices_1_1 = calculate_split_bonus_adjustment_factors(records_1_1, ca_1_1)
        self.assertAlmostEqual(adj_prices_1_1[0]["adjusted_close"], 1000.0, places=2)
        self.assertAlmostEqual(adj_prices_1_1[0]["split_bonus_cum_factor"], 0.5, places=4)
        self.assertAlmostEqual(adj_prices_1_1[1]["adjusted_close"], 1050.0, places=2)
        self.assertAlmostEqual(adj_prices_1_1[1]["split_bonus_cum_factor"], 1.0, places=4)

        adj_vols_1_1 = adjust_volume_for_corporate_actions(records_1_1, ca_1_1)
        self.assertEqual(adj_vols_1_1[0], 20000)  # 10000 / 0.5
        self.assertEqual(adj_vols_1_1[1], 25000)  # ex-date unscaled

        # B. 1:2 Bonus Issue (e.g. TRENT, factor 0.6667 = 2/3)
        # Pre-event price scaled by 2/3, ex-date unscaled.
        records_1_2 = [
            {"trading_date": "2026-06-03", "open": 6000.0, "high": 6050.0, "low": 5950.0, "close": 6000.0, "volume": 50000},
            {"trading_date": "2026-06-04", "open": 4100.0, "high": 4150.0, "low": 4050.0, "close": 4100.0, "volume": 75000}  # ex-date
        ]
        ca_1_2 = [{"symbol": "TRENT", "action_type": "BONUS", "ex_date": "2026-06-04", "purpose": "Bonus 1:2", "adjustment_factor": 0.6667}]

        adj_prices_1_2 = calculate_split_bonus_adjustment_factors(records_1_2, ca_1_2)
        self.assertAlmostEqual(adj_prices_1_2[0]["adjusted_close"], 4000.20, places=1)
        self.assertAlmostEqual(adj_prices_1_2[1]["adjusted_close"], 4100.00, places=2)

        adj_vols_1_2 = adjust_volume_for_corporate_actions(records_1_2, ca_1_2)
        self.assertEqual(adj_vols_1_2[0], int(round(50000 / 0.6667)))  # 74996
        self.assertEqual(adj_vols_1_2[1], 75000)

        # C. 5:1 Stock Split (e.g. DRREDDY / SHRIRAMFIN, factor 0.2000 = 1/5)
        # Pre-event price scaled by 0.2, ex-date unscaled.
        records_5_1 = [
            {"trading_date": "2024-10-25", "open": 5000.0, "high": 5050.0, "low": 4980.0, "close": 5000.0, "volume": 10000},
            {"trading_date": "2024-10-28", "open": 1010.0, "high": 1030.0, "low": 1005.0, "close": 1020.0, "volume": 30000}  # ex-date
        ]
        ca_5_1 = [{"symbol": "DRREDDY", "action_type": "SPLIT", "ex_date": "2024-10-28", "purpose": "Split 5:1", "adjustment_factor": 0.2}]

        adj_prices_5_1 = calculate_split_bonus_adjustment_factors(records_5_1, ca_5_1)
        self.assertAlmostEqual(adj_prices_5_1[0]["adjusted_close"], 1000.0, places=2)
        self.assertAlmostEqual(adj_prices_5_1[1]["adjusted_close"], 1020.0, places=2)

        adj_vols_5_1 = adjust_volume_for_corporate_actions(records_5_1, ca_5_1)
        self.assertEqual(adj_vols_5_1[0], 50000)  # 10000 / 0.2
        self.assertEqual(adj_vols_5_1[1], 30000)

        # D. Compound Split + Bonus on Same Ex-Date (e.g. BAJFINANCE: 4:1 Bonus [0.2] + 2:1 Split [0.5])
        # Cumulative pre-event factor = 0.2 * 0.5 = 0.10.
        records_compound = [
            {"trading_date": "2025-06-13", "open": 8000.0, "high": 8050.0, "low": 7950.0, "close": 8000.0, "volume": 10000},
            {"trading_date": "2025-06-16", "open": 810.0, "high": 830.0, "low": 800.0, "close": 820.0, "volume": 95000}
        ]
        cas_compound = [
            {"symbol": "BAJFINANCE", "action_type": "BONUS", "ex_date": "2025-06-16", "purpose": "Bonus 4:1", "adjustment_factor": 0.2},
            {"symbol": "BAJFINANCE", "action_type": "SPLIT", "ex_date": "2025-06-16", "purpose": "Split 2:1", "adjustment_factor": 0.5}
        ]
        adj_prices_compound = calculate_split_bonus_adjustment_factors(records_compound, cas_compound)
        self.assertAlmostEqual(adj_prices_compound[0]["split_bonus_cum_factor"], 0.10, places=4)
        self.assertAlmostEqual(adj_prices_compound[0]["adjusted_close"], 800.0, places=2)
        self.assertAlmostEqual(adj_prices_compound[1]["adjusted_close"], 820.0, places=2)

    def test_live_database_corporate_actions_integrity(self):
        """10. Verify live production database (data/market_lab.db) contains complete, valid corporate actions."""
        live_db_path = "data/market_lab.db"
        if not os.path.exists(live_db_path):
            self.skipTest("Live database not found.")

        live_db = DatabaseManager(live_db_path)
        with live_db.get_connection() as conn:
            # PRAGMA integrity
            c = conn.execute("PRAGMA integrity_check;")
            self.assertEqual(c.fetchone()[0], "ok")

            # Check total corporate actions in window (169 rows post-NESTLEIND resolution)
            c = conn.execute("""
                SELECT COUNT(*), COUNT(DISTINCT symbol)
                FROM corporate_actions
                WHERE ex_date BETWEEN '2024-10-21' AND '2026-10-23';
            """)
            total_cas, unique_syms = c.fetchone()
            # In benchmark window: 169 baseline actions + 1 official ADANIENT Rights issue ingested directly from live NSE endpoint
            self.assertIn(total_cas, (169, 170), f"Expected 169 or 170 corporate actions, found {total_cas}")
            self.assertEqual(unique_syms, 49, f"Expected 49 unique symbols, found {unique_syms}")

            # Verify NESTLEIND contains BOTH distinct declarations on 2026-07-10
            c = conn.execute("""
                SELECT purpose, adjustment_factor
                FROM corporate_actions
                WHERE symbol = 'NESTLEIND' AND ex_date = '2026-07-10'
                ORDER BY purpose;
            """)
            nestle_events = c.fetchall()
            self.assertEqual(len(nestle_events), 2)
            self.assertEqual(nestle_events[0][0], "Dividend - Rs 5 Per Share")
            self.assertEqual(nestle_events[1][0], "Special Dividend - Rs 2 Per Share")

            # Check zero invalid adjustment factors
            c = conn.execute("SELECT COUNT(*) FROM corporate_actions WHERE adjustment_factor <= 0;")
            self.assertEqual(c.fetchone()[0], 0)

            # Check zero duplicate natural keys on (symbol, action_type, ex_date, purpose)
            c = conn.execute("""
                SELECT symbol, action_type, ex_date, purpose, COUNT(*)
                FROM corporate_actions
                GROUP BY symbol, action_type, ex_date, purpose
                HAVING COUNT(*) > 1;
            """)
            self.assertEqual(len(c.fetchall()), 0)

            # Check non-neutral adjustment factors
            c = conn.execute("""
                SELECT symbol, action_type, ex_date, adjustment_factor
                FROM corporate_actions
                WHERE symbol = 'RELIANCE' AND ex_date = '2024-10-28';
            """)
            reliance_bonus = c.fetchone()
            self.assertIsNotNone(reliance_bonus)
            self.assertEqual(reliance_bonus[1], "BONUS")
            self.assertEqual(reliance_bonus[3], 0.5)

            c = conn.execute("""
                SELECT symbol, action_type, ex_date, adjustment_factor
                FROM corporate_actions
                WHERE symbol = 'DRREDDY' AND ex_date = '2024-10-28';
            """)
            drreddy_split = c.fetchone()
            self.assertIsNotNone(drreddy_split)
            self.assertEqual(drreddy_split[1], "SPLIT")
            self.assertEqual(drreddy_split[3], 0.2)

    def test_directive_corporate_actions_upsert_on_duplicate_id(self):
        """Directive Test 1: Verify duplicate IDs trigger an UPSERT, not an error."""
        from src.quant.corporate_actions import CorporateActionsHandler
        handler = CorporateActionsHandler()
        
        mock_action = {
            "symbol": "INFY",
            "subject": "Interim Dividend - Rs 26 Per Share",
            "exDate": "03-Nov-2026",
            "recDate": "03-Nov-2026",
            "faceVal": "5"
        }
        parsed1 = handler.parse_action(mock_action, "INFY")
        self.assertIsNotNone(parsed1)
        self.db.upsert_corporate_actions([parsed1])

        # Second insert with updated purpose / face value on same ID
        parsed2 = dict(parsed1)
        parsed2["face_value"] = 10.0
        parsed2["record_date"] = "2026-11-04"
        
        # Must execute without error and update existing row
        self.db.upsert_corporate_actions([parsed2])

        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM corporate_actions WHERE id = ?", (parsed1["id"],))
            self.assertEqual(cursor.fetchone()[0], 1, "Duplicate ID must update existing row, not create duplicate")
            cursor = conn.execute("SELECT face_value, record_date FROM corporate_actions WHERE id = ?", (parsed1["id"],))
            row = cursor.fetchone()
            self.assertEqual(row[0], 10.0)
            self.assertEqual(row[1], "2026-11-04")

    def test_directive_unverified_disclosures_default_pending_verification(self):
        """Directive Test 2: Verify unverified disclosures default strictly to PENDING_VERIFICATION."""
        from src.quant.disclosures import CorporateDisclosuresHandler
        handler = CorporateDisclosuresHandler()

        mock_disclosure = {
            "symbol": "INFY",
            "desc": "Financial Results for Q2 FY27",
            "attchmntText": "Infosys announces second quarter financial results.",
            "attchmntFile": "https://nsearchives.nseindia.com/corporate/INFY_Q2_2026.pdf",
            "an_dt": "23-Oct-2026 16:30:00",
            "seq_id": "999888777"
        }
        parsed = handler.parse_disclosure(mock_disclosure, "INFY")
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed["verification_status"], "PENDING_VERIFICATION")
        self.assertEqual(parsed["source_url"], "https://nsearchives.nseindia.com/corporate/INFY_Q2_2026.pdf")
        self.assertEqual(parsed["category"], "EARNINGS")

        handler.ingest_disclosures(self.db, "INFY", [mock_disclosure], "test_path.json")

        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT verification_status, category, source_url FROM corporate_disclosures WHERE id = ?",
                (parsed["id"],)
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "PENDING_VERIFICATION")
            self.assertEqual(row[1], "EARNINGS")
            self.assertEqual(row[2], "https://nsearchives.nseindia.com/corporate/INFY_Q2_2026.pdf")

    def test_directive_zero_corporate_actions_handled_gracefully(self):
        """Directive Test 3: Verify a stock with zero corporate actions logs NO_ACTIONS_FOUND without error."""
        from src.quant.corporate_actions import CorporateActionsHandler
        handler = CorporateActionsHandler()

        result = handler.ingest_actions(self.db, "ADANIENT", [], "mock_empty_actions.json")
        self.assertEqual(result["status"], "NO_ACTIONS_FOUND")
        self.assertEqual(result["retrieved"], 0)
        self.assertEqual(result["accepted"], 0)

        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT status, records_retrieved, records_accepted, validation_summary FROM ingestion_audit_log WHERE symbol = 'ADANIENT' ORDER BY log_id DESC LIMIT 1;"
            )
            row = cursor.fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row[0], "NO_ACTIONS_FOUND")
            self.assertEqual(row[1], 0)
            self.assertEqual(row[2], 0)
            self.assertIn("No corporate actions found", row[3])

    def test_directive_disclosures_metadata_and_timestamp_accuracy(self):
        """Directive Test 4: Verify metadata tagging regex, PDF extraction, and exact exchange submission timestamp."""
        from src.quant.disclosures import CorporateDisclosuresHandler
        handler = CorporateDisclosuresHandler()

        items = [
            ({"desc": "Outcome of Board Meeting", "attchmntText": "Financial results for quarter ended Sept 30", "an_dt": "23-Oct-2026 16:30:00", "seq_id": "1"}, "EARNINGS"),
            ({"desc": "Board Meeting Intimation", "attchmntText": "Notice of meeting to consider accounts", "an_dt": "15-Oct-2026 10:00:00", "seq_id": "2"}, "BOARD_MEETING"),
            ({"desc": "Updates", "attchmntText": "Bagged contract worth Rs 450 Cr", "an_dt": "10-Oct-2026 12:00:00", "seq_id": "3"}, "CONTRACT_AWARD"),
            ({"desc": "Resignation", "attchmntText": "CFO resignation tendered", "an_dt": "05-Oct-2026 18:00:00", "seq_id": "4"}, "RESIGNATION"),
            ({"desc": "Appointment", "attchmntText": "Appointment of Director", "an_dt": "01-Oct-2026 14:00:00", "seq_id": "5"}, "APPOINTMENT"),
        ]

        for raw, expected_cat in items:
            raw["attchmntFile"] = f"https://nsearchives.nseindia.com/corporate/{expected_cat}.pdf"
            parsed = handler.parse_disclosure(raw, "TCS")
            self.assertEqual(parsed["category"], expected_cat)
            self.assertEqual(parsed["source_url"], raw["attchmntFile"])
            self.assertTrue(parsed["broadcast_timestamp"].endswith("+05:30"))

if __name__ == "__main__":
    unittest.main()
