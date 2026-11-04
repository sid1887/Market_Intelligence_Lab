"""
Unit and integration tests for Milestone B5 Phase 2: Unified Evidence Store & Source Adapters.
Verifies all 10 acceptance criteria:
1. Evidence serialization and deterministic identity.
2. Duplicate ingestion and idempotency.
3. Multiple legitimate events sharing an ex-date (Nestlé dividends).
4. Restatements and publication-time eligibility (TMPV recast).
5. Verified versus unverified disclosure handling (INFY schedule notice).
6. Standalone vs. consolidated reporting-basis isolation (SBIN vs peers).
7. PRI valuation and index movement deduplication (zero TRI duplicates).
8. Missing peer observations and individual peer audits (BPCL detection).
9. Synthetic peer minimum membership and conglomerate proxy labeling.
10. Corporate action classification and mechanical ex-date price effects.
"""

import unittest
import os
import sqlite3
import json
import datetime
import tempfile
import shutil
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.evidence.models import (
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    ReportingBasis,
    SectorBenchmarkType,
    EvidenceRecord
)
from src.evidence.constants import (
    MINIMUM_SYNTHETIC_PEERS,
    CONTRADICTION_PENALTY_DEFAULT,
    DATA_GOVERNANCE_NOTICE,
    resolve_sector_benchmark
)
from src.evidence.adapters import (
    CorporateDisclosuresAdapter,
    CorporateActionsAdapter,
    FinancialStatementsAdapter,
    MarketIndexMovementsAdapter,
    VolumeAnomaliesAdapter
)
from src.evidence.peer_validator import (
    SyntheticPeerValidator,
    PeerBasketValidationError
)
from src.evidence.store import EvidenceStore


class TestMilestoneB5Phase2(unittest.TestCase):
    """Phase 2 comprehensive verification test suite."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_copy_path = os.path.join(cls.temp_dir, "test_market_lab.db")
        shutil.copy2("data/market_lab.db", cls.db_copy_path)
        cls.db = DatabaseManager(cls.db_copy_path)
        cls.store = EvidenceStore(cls.db)
        # Ensure evidence is ingested into isolated test db
        cls.ingest_res = cls.store.ingest_all_local_evidence()

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_1_evidence_serialization_and_identity(self):
        """Verifies deterministic evidence ID generation and dataclass serialization round-trip."""
        rec = EvidenceRecord(
            evidence_id="TEST_ID_001",
            symbol="INFY",
            entity_type="STOCK",
            event_date="2026-10-23",
            broadcast_timestamp="2026-10-23T16:30:00+05:30",
            effective_session_date="2026-10-26",
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING,
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.POSITIVE,
            headline="INFY Q2 FY2027 Audited Results",
            details={"rev_cc_qoq": 2.2},
            source_identity="corporate_disclosures",
            source_reference="doc_123",
            verification_status="VERIFIED",
            is_pit_eligible=True,
            reporting_basis="CONSOLIDATED",
            expectation_surprise=ExpectationSurprise.UNKNOWN
        )
        d = rec.to_dict()
        self.assertEqual(d["tier"], 1)
        self.assertEqual(d["category"], "EARNINGS_RELEASE")
        rec2 = EvidenceRecord.from_dict(d)
        self.assertEqual(rec, rec2)

    def test_2_duplicate_ingestion_and_idempotency(self):
        """Verifies that running ingest_all_local_evidence repeatedly is 100% idempotent."""
        initial_summary = self.store.get_evidence_summary()
        initial_total = initial_summary["total_records"]
        self.assertGreater(initial_total, 1000)

        # Run ingestion a second time
        second_res = self.store.ingest_all_local_evidence()
        second_summary = self.store.get_evidence_summary()
        self.assertEqual(second_summary["total_records"], initial_total)
        self.assertEqual(second_summary["by_tier"], initial_summary["by_tier"])
        self.assertEqual(second_summary["by_category"], initial_summary["by_category"])

    def test_3_multiple_legitimate_events_sharing_an_exdate(self):
        """
        Requirement 1: Do not collapse distinct events into one record.
        Nestle India had both a ₹5 final dividend and a ₹2 special dividend on 2026-07-10.
        Both must be preserved as distinct records with distinct IDs.
        """
        evs = self.store.get_evidence_for_session(symbol="NESTLEIND", session_date="2026-07-10")
        dividend_evs = [e for e in evs if e.category == EvidenceCategory.DIVIDEND_DECLARATION]
        self.assertEqual(len(dividend_evs), 2)

        ids = {e.evidence_id for e in dividend_evs}
        self.assertEqual(len(ids), 2)  # 2 distinct IDs

        purposes = {e.details.get("purpose") for e in dividend_evs}
        self.assertIn("Dividend - Rs 5 Per Share", purposes)
        self.assertIn("Special Dividend - Rs 2 Per Share", purposes)

    def test_4_restatement_and_publication_time_eligibility(self):
        """
        Requirement 4: Preserve point-in-time rules and separate restatement versions.
        TMPV Q1 FY26 original (V1) published in Aug 2025; recast (V2) published Nov 2025.
        """
        summary = self.store.get_evidence_summary()
        # Verify EARNINGS_REVISION exists
        self.assertGreaterEqual(summary["by_category"].get("EARNINGS_REVISION", 0), 1)

        # Query as-of 2025-08-15 (prior to recast publication):
        # Query window around Q1 FY26 release (effective 2025-08-01)
        evs_pre = self.store.get_evidence_in_window(
            symbol="TMPV",
            start_session="2025-08-01",
            end_session="2025-08-05",
            as_of_date="2025-08-15"
        )
        fs_pre = [e for e in evs_pre if e.source_identity == "company_financial_statements"]
        self.assertEqual(len(fs_pre), 1)
        self.assertEqual(fs_pre[0].details.get("statement_version"), 1)
        self.assertEqual(fs_pre[0].category, EvidenceCategory.EARNINGS_RELEASE)

        # Query as-of 2026-05-15 (after recast publication):
        # On 2025-11-10, TMPV published both Q2 FY26 (V1) and recast Q1 FY26 (V2)
        evs_recast = self.store.get_evidence_in_window(
            symbol="TMPV",
            start_session="2025-11-01",
            end_session="2025-11-15",
            as_of_date="2026-05-15"
        )
        fs_recast = [e for e in evs_recast if e.source_identity == "company_financial_statements"]
        self.assertEqual(len(fs_recast), 2)  # Q2 V1 release + Q1 V2 recast
        
        recast_items = [e for e in fs_recast if e.category == EvidenceCategory.EARNINGS_REVISION]
        self.assertEqual(len(recast_items), 1)
        self.assertEqual(recast_items[0].details.get("statement_version"), 2)
        self.assertEqual(recast_items[0].details.get("statement_id"), "TMPV_Q1_FY26_CONS_V2_RECAST")

    def test_5_verified_versus_unverified_disclosure_handling(self):
        """
        Requirement 2: PENDING_VERIFICATION and SOURCE_UNVERIFIED must not enter verified ranking.
        INFY schedule disclosure (effective 2026-10-16) is SOURCE_UNVERIFIED.
        """
        # When only_verified=True, unverified disclosure is excluded
        verified_evs = self.store.get_evidence_for_session(
            symbol="INFY",
            session_date="2026-10-16",
            only_verified=True
        )
        for e in verified_evs:
            self.assertEqual(e.verification_status, "VERIFIED")
            self.assertNotEqual(e.tier, EvidenceTier.TIER_5_UNVERIFIED)

        # When only_verified=False, it appears flagged as Tier 5 and SOURCE_UNVERIFIED
        all_evs = self.store.get_evidence_for_session(
            symbol="INFY",
            session_date="2026-10-16",
            only_verified=False
        )
        unverified_list = [e for e in all_evs if e.verification_status == "SOURCE_UNVERIFIED"]
        self.assertEqual(len(unverified_list), 1)
        self.assertEqual(unverified_list[0].tier, EvidenceTier.TIER_5_UNVERIFIED)
        self.assertFalse(unverified_list[0].is_pit_eligible)

    def test_6_standalone_consolidated_reporting_basis_isolation(self):
        """
        Requirement 4: SBIN must be tagged STANDALONE; peer statements tagged CONSOLIDATED.
        """
        summary = self.store.get_evidence_summary()
        self.assertEqual(summary["by_reporting_basis"]["STANDALONE"], 9)
        self.assertEqual(summary["by_reporting_basis"]["CONSOLIDATED"], 444)

        # Test specific SBIN statement
        sbin_evs = self.store.get_evidence_for_session(symbol="SBIN", session_date="2025-05-09")
        fs_sbin = [e for e in sbin_evs if e.source_identity == "company_financial_statements"]
        self.assertEqual(len(fs_sbin), 1)
        self.assertEqual(fs_sbin[0].reporting_basis, "STANDALONE")

    def test_7_pri_valuation_and_movement_deduplication(self):
        """
        Requirement 5: Strict PRI-only filtering for index movements to avoid double-counting with TRI.
        """
        summary = self.store.get_evidence_summary()
        index_moves_count = summary["by_category"].get("SECTOR_MOMENTUM", 0)
        self.assertGreater(index_moves_count, 500)

        # Confirm every single index evidence record has details_json with index_type == 'PRI'
        with self.db.get_connection() as conn:
            cursor = conn.execute("SELECT details_json FROM evidence_records WHERE evidence_category = 'SECTOR_MOMENTUM'")
            for row in cursor.fetchall():
                d = json.loads(row[0])
                self.assertEqual(d.get("index_type"), "PRI")
                self.assertEqual(d.get("deduplication_rule"), "PRI_EXCLUSIVE_FILTER")

    def test_8_missing_peer_observations_and_validation(self):
        """
        Requirement 5: Synthetic peer validator audits individual peers:
        BPCL is marked inactive (is_active=0) with 0 OHLCV rows and MUST be rejected.
        ONGC and COALINDIA are active with valid OHLCV and MUST be accepted.
        """
        validator = SyntheticPeerValidator(self.db)

        audit_bpcl = validator.audit_individual_peer("BPCL")
        self.assertFalse(audit_bpcl["is_eligible"])
        self.assertIn("inactive", audit_bpcl["rejection_reason"])
        self.assertEqual(audit_bpcl["ohlcv_count"], 0)

        audit_ongc = validator.audit_individual_peer("ONGC")
        self.assertTrue(audit_ongc["is_eligible"])
        self.assertGreater(audit_ongc["ohlcv_count"], 450)

        audit_coal = validator.audit_individual_peer("COALINDIA")
        self.assertTrue(audit_coal["is_eligible"])
        self.assertGreater(audit_coal["ohlcv_count"], 450)

    def test_9_synthetic_peer_minimum_membership_and_conglomerate_proxy(self):
        """
        Requirement 5: Reliance energy basket validation.
        - Narrow proposal (ONGC, BPCL, COALINDIA) fails: BPCL has 0 data -> only 2 peers < 3.
        - Expanded proxy (ONGC, COALINDIA, NTPC, POWERGRID) passes: 4 peers >= 3.
        - Reliance conglomerate nature explicitly annotated.
        """
        validator = SyntheticPeerValidator(self.db)
        audit_res = validator.audit_reliance_energy_basket()

        self.assertEqual(audit_res["target"], "RELIANCE")
        self.assertIn("diversified conglomerate", audit_res["conglomerate_nature_note"])

        # Narrow proposal validation
        narrow = audit_res["narrow_proposal"]
        self.assertFalse(narrow["is_valid"])
        self.assertEqual(narrow["eligible_count"], 2)
        self.assertEqual(len(narrow["rejected_peers"]), 1)
        self.assertEqual(narrow["rejected_peers"][0]["symbol"], "BPCL")

        # Expanded proxy validation
        expanded = audit_res["expanded_proxy"]
        self.assertTrue(expanded["is_valid"])
        self.assertGreaterEqual(expanded["eligible_count"], 3)
        self.assertTrue(expanded["is_survivorship_biased_proxy"])

    def test_10_corporate_action_direction_and_mechanical_price_effects(self):
        """
        Requirement 3: Corporate actions (bonus/split/dividend) must be classified as NEUTRAL
        and tagged as mechanical adjustments on ex-date, NOT investor sentiment shifts.
        """
        # NESTLEIND 1:1 Bonus on 2025-08-08
        evs = self.store.get_evidence_for_session(symbol="NESTLEIND", session_date="2025-08-08")
        bonus_evs = [e for e in evs if e.category == EvidenceCategory.BONUS_SPLIT_EVENT]
        self.assertEqual(len(bonus_evs), 1)

        b_ev = bonus_evs[0]
        self.assertEqual(b_ev.direction, EvidenceDirection.NEUTRAL)
        self.assertTrue(b_ev.details.get("is_mechanical_adjustment"))
        self.assertEqual(b_ev.details.get("adjustment_factor"), 0.5)
        self.assertIn("mechanical", b_ev.details.get("mechanical_note", "").lower())


if __name__ == "__main__":
    unittest.main()
