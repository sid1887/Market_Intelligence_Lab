"""
Unit tests for Milestone B5 Phase 1: Schema Extensions & Unified Evidence Data Models.
Verifies:
1. Evidence dataclasses, serialization, and immutability.
2. ExpectationSurprise UNKNOWN default (never inferred from YoY growth alone).
3. Contradictory evidence flagging and configurable penalty heuristic.
4. Sector benchmark 4-tier hierarchy (Official -> Synthetic Basket -> NIFTY 50 PRI -> Unavailable).
5. Synthetic peer basket requirements (excludes symbol, >= 3 peers, flags survivorship proxy).
6. SQLite schema v3 migrations and CRUD operations.
7. Baseline row-count reconciliation invariants.
"""

import unittest
import sqlite3
import json
import datetime
from typing import Dict, Any, List

from src.evidence.models import (
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    ReportingBasis,
    MovementClassification,
    SectorBenchmarkType,
    EvidenceRecord,
    SectorBenchmarkContext,
    AttributionHypothesis
)
from src.evidence.constants import (
    SECTOR_TO_INDEX_MAP,
    SYNTHETIC_BASKET_DEFINITIONS,
    MINIMUM_SYNTHETIC_PEERS,
    CONTRADICTION_PENALTY_DEFAULT,
    DATA_GOVERNANCE_NOTICE,
    resolve_sector_benchmark
)
from src.storage.database import DatabaseManager


class TestMilestoneB5Phase1(unittest.TestCase):
    """Phase 1 verification suite."""

    def test_evidence_model_serialization_and_immutability(self):
        """Verifies EvidenceRecord dataclass integrity, immutability, and JSON serialization."""
        rec = EvidenceRecord(
            evidence_id="INFY_DISC_20261023_Q2",
            symbol="INFY",
            entity_type="STOCK",
            event_date="2026-10-23",
            broadcast_timestamp="2026-10-23T16:30:00+05:30",
            effective_session_date="2026-10-26",
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING,
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.POSITIVE,
            headline="Q2 FY2027 Audited Results: Constant Currency Revenue +2.2% QoQ",
            details={
                "revenue_growth_qoq_cc": 2.2,
                "operating_margin_pct": 21.1,
                "dividend_declared": 21.0
            },
            source_identity="nse_circular",
            source_reference="INFY_BM_OUTCOME_20261023.pdf",
            verification_status="VERIFIED",
            is_pit_eligible=True,
            reporting_basis="CONSOLIDATED",
            expectation_surprise=ExpectationSurprise.UNKNOWN,
            is_contradictory=False,
            retrieval_timestamp="2026-10-23T17:00:00Z",
            created_at="2026-10-31T18:00:00Z"
        )

        # 1. Immutability
        with self.assertRaises(Exception):
            rec.headline = "Modified headline"  # type: ignore

        # 2. to_dict serialization
        d = rec.to_dict()
        self.assertEqual(d["tier"], 1)
        self.assertEqual(d["category"], "EARNINGS_RELEASE")
        self.assertEqual(d["direction"], "POSITIVE")
        self.assertEqual(d["expectation_surprise"], "UNKNOWN")
        self.assertEqual(d["details"]["operating_margin_pct"], 21.1)

        # 3. from_dict deserialization
        rec2 = EvidenceRecord.from_dict(d)
        self.assertEqual(rec, rec2)
        self.assertEqual(rec2.tier, EvidenceTier.TIER_1_OFFICIAL_FILING)
        self.assertEqual(rec2.expectation_surprise, ExpectationSurprise.UNKNOWN)

        # 4. JSON roundtrip
        json_str = rec.to_json()
        parsed = json.loads(json_str)
        self.assertEqual(parsed["evidence_id"], "INFY_DISC_20261023_Q2")

    def test_expectation_surprise_unknown_by_default(self):
        """
        Decision 1 Requirement: If analyst expectations/consensus estimates are absent,
        expectation-relative surprise MUST be marked UNKNOWN.
        Never inferred from YoY growth alone.
        """
        rec = EvidenceRecord(
            evidence_id="TCS_Q2_FY27",
            symbol="TCS",
            entity_type="STOCK",
            event_date="2026-10-15",
            broadcast_timestamp="2026-10-15T16:00:00+05:30",
            effective_session_date="2026-10-16",
            tier=EvidenceTier.TIER_2_FINANCIAL_ACTION,
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.POSITIVE,
            headline="TCS Q2 PAT grew 8.5% YoY",
            details={"pat_growth_yoy": 8.5},
            source_identity="cfs_table",
            source_reference=None,
            verification_status="VERIFIED",
            is_pit_eligible=True
        )
        # Default must be UNKNOWN
        self.assertEqual(rec.expectation_surprise, ExpectationSurprise.UNKNOWN)
        # Explicitly ensure enum members are complete
        self.assertIn(ExpectationSurprise.BEAT, ExpectationSurprise)
        self.assertIn(ExpectationSurprise.MISS, ExpectationSurprise)
        self.assertIn(ExpectationSurprise.IN_LINE, ExpectationSurprise)
        self.assertIn(ExpectationSurprise.UNKNOWN, ExpectationSurprise)

    def test_contradiction_flag_and_penalty_constant(self):
        """
        Decision 1 Requirement: Contradictory evidence is retained, flagged,
        and receives a configurable penalty (default 30.0), but is not invalidated.
        """
        self.assertEqual(CONTRADICTION_PENALTY_DEFAULT, 30.0)

        # Contradicted evidence record (e.g. positive news on falling stock)
        rec = EvidenceRecord(
            evidence_id="CONTRADICTED_EVENT_001",
            symbol="INFY",
            entity_type="STOCK",
            event_date="2026-10-23",
            broadcast_timestamp=None,
            effective_session_date="2026-10-26",
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING,
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.POSITIVE,
            headline="Revenue beat but stock dropped 3%",
            details={},
            source_identity="nse_circular",
            source_reference=None,
            verification_status="VERIFIED",
            is_pit_eligible=True,
            is_contradictory=True
        )
        self.assertTrue(rec.is_contradictory)

        # Hypothesis captures penalty heuristic
        hyp = AttributionHypothesis(
            hypothesis_id="HYP_INFY_20261026",
            symbol="INFY",
            target_date="2026-10-26",
            movement_classification=MovementClassification.IDIOSYNCRATIC_UNDERPERFORMANCE,
            primary_evidence_id="CONTRADICTED_EVENT_001",
            supporting_evidence_ids=[],
            contradicting_evidence_ids=["CONTRADICTED_EVENT_001"],
            evidence_strength_score=30.0,  # 60 base - 30 penalty = 30
            confidence_level="LOW_CONFIDENCE",
            is_contradicted=True,
            contradiction_penalty_applied=CONTRADICTION_PENALTY_DEFAULT,
            notes="Earnings was positive but stock declined; contradiction penalty applied."
        )
        self.assertTrue(hyp.is_contradicted)
        self.assertEqual(hyp.contradiction_penalty_applied, 30.0)
        self.assertEqual(hyp.confidence_level, "LOW_CONFIDENCE")

    def test_reporting_basis_enum(self):
        """Verifies ReportingBasis enum covers CONSOLIDATED and STANDALONE."""
        self.assertEqual(ReportingBasis.CONSOLIDATED.value, "CONSOLIDATED")
        self.assertEqual(ReportingBasis.STANDALONE.value, "STANDALONE")

    def test_sector_benchmark_resolution_official_indices(self):
        """
        Decision 2 Requirement (Tier 1): Official sector PRI index resolution.
        """
        # Bank -> NIFTY BANK
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark("HDFCBANK", "Financial Services", "Private Sector Bank")
        self.assertEqual(b_type, SectorBenchmarkType.OFFICIAL_SECTOR_PRI)
        self.assertEqual(b_name, "NIFTY BANK")
        self.assertFalse(is_proxy)

        # PSU Bank -> NIFTY BANK
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark("SBIN", "Financial Services", "Public Sector Bank")
        self.assertEqual(b_type, SectorBenchmarkType.OFFICIAL_SECTOR_PRI)
        self.assertEqual(b_name, "NIFTY BANK")

        # Non-Bank Financial -> NIFTY FINANCIAL SERVICES
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark("BAJFINANCE", "Financial Services", "Non-Banking Financial Company")
        self.assertEqual(b_type, SectorBenchmarkType.OFFICIAL_SECTOR_PRI)
        self.assertEqual(b_name, "NIFTY FINANCIAL SERVICES")

        # IT -> NIFTY IT
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark("INFY", "Information Technology", "IT Services & Consulting")
        self.assertEqual(b_type, SectorBenchmarkType.OFFICIAL_SECTOR_PRI)
        self.assertEqual(b_name, "NIFTY IT")

        # Auto -> NIFTY AUTO
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark("TMPV", "Automobile and Auto Components", "Passenger Cars & Utility Vehicles")
        self.assertEqual(b_type, SectorBenchmarkType.OFFICIAL_SECTOR_PRI)
        self.assertEqual(b_name, "NIFTY AUTO")

        # Pharma -> NIFTY PHARMA
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark("SUNPHARMA", "Healthcare", "Pharmaceuticals")
        self.assertEqual(b_type, SectorBenchmarkType.OFFICIAL_SECTOR_PRI)
        self.assertEqual(b_name, "NIFTY PHARMA")

    def test_sector_benchmark_resolution_synthetic_peer_basket(self):
        """
        Decision 2 Requirement (Tier 2): Synthetic peer basket when no official index exists.
        - Must exclude investigated stock
        - Must require >= 3 eligible peers
        - Must flag as survivorship-biased proxy
        - Must never describe as official sector index
        """
        active_universe = ["RELIANCE", "ONGC", "BPCL", "COALINDIA", "TCS", "INFY"]
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark(
            symbol="RELIANCE",
            sector="Oil Gas & Consumable Fuels",
            industry="Integrated Oil & Gas",
            active_universe_symbols=active_universe
        )
        self.assertEqual(b_type, SectorBenchmarkType.SYNTHETIC_PEER_BASKET)
        self.assertEqual(b_name, "SYNTHETIC_ENERGY_BASKET")
        self.assertNotIn("RELIANCE", peers)  # Excludes investigated stock
        self.assertGreaterEqual(len(peers), 3)  # At least 3 peers
        self.assertTrue(is_proxy)  # Flagged as survivorship-biased proxy
        self.assertIn("Never presented as an official index", notes)

    def test_sector_benchmark_resolution_fallback_to_nifty50(self):
        """
        Decision 2 Requirement (Tier 3): When < 3 peers exist for a sector without an official index,
        falls back to broad-market NIFTY 50 PRI as broad-market context only.
        """
        # LT in Construction (only 1 constituent in universe)
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark(
            symbol="LT",
            sector="Construction",
            industry="Civil Construction"
        )
        self.assertEqual(b_type, SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI)
        self.assertEqual(b_name, "NIFTY 50")
        self.assertIn("broad-market context only", notes)

        # ASIANPAINT in Consumer Durables (TITAN is only other peer -> 1 peer < 3)
        b_type, b_name, peers, is_proxy, notes = resolve_sector_benchmark(
            symbol="ASIANPAINT",
            sector="Consumer Durables",
            industry="Paints"
        )
        self.assertEqual(b_type, SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI)
        self.assertEqual(b_name, "NIFTY 50")
        self.assertIn("only 1 eligible peers", notes)

    def test_sqlite_schema_v3_and_crud(self):
        """Verifies schema v3 tables and DatabaseManager CRUD operations on in-memory DB."""
        db = DatabaseManager(":memory:")
        db.init_schema()

        # 1. Upsert Evidence Records
        rec = {
            "evidence_id": "TEST_EV_001",
            "symbol": "INFY",
            "entity_type": "STOCK",
            "event_date": "2026-10-23",
            "broadcast_timestamp": "2026-10-23T16:30:00+05:30",
            "effective_session_date": "2026-10-26",
            "evidence_tier": 1,
            "evidence_category": "EARNINGS_RELEASE",
            "evidence_direction": "POSITIVE",
            "headline": "INFY Q2 FY27 Results",
            "details_json": {"qoq": 2.2},
            "source_identity": "bse_filing",
            "source_reference": "doc_ref_123",
            "verification_status": "VERIFIED",
            "is_pit_eligible": 1,
            "reporting_basis": "CONSOLIDATED",
            "expectation_surprise": "UNKNOWN",
            "is_contradictory": 0,
            "retrieval_timestamp": "2026-10-23T17:00:00Z",
            "created_at": "2026-10-31T18:00:00Z"
        }
        cnt = db.upsert_evidence_records([rec])
        self.assertEqual(cnt, 1)

        # 2. Query Evidence Records
        rows = db.get_evidence_records(symbol="INFY", effective_session_date="2026-10-26")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["evidence_id"], "TEST_EV_001")
        self.assertEqual(rows[0]["details"]["qoq"], 2.2)

        # 3. Record Movement Explanation
        exp = {
            "explanation_id": "EXP_INFY_20261026",
            "symbol": "INFY",
            "trading_date": "2026-10-26",
            "movement_classification": "IDIOSYNCRATIC_OUTPERFORMANCE",
            "stock_return_1d": 0.035,
            "benchmark_return_1d": 0.005,
            "sector_return_1d": 0.012,
            "sector_benchmark_type": "OFFICIAL_SECTOR_PRI",
            "sector_benchmark_name": "NIFTY IT",
            "abnormal_return": 0.028,
            "sector_adjusted_return": 0.023,
            "volume_ratio": 2.8,
            "primary_evidence_id": "TEST_EV_001",
            "evidence_strength_score": 85.0,
            "confidence_level": "HIGH_CONFIDENCE",
            "is_contradicted": 0,
            "contradiction_penalty": 0.0,
            "unexplained_residual_pct": 0.007,
            "full_report_json": {"summary": "Strong Q2 beat drove idiosyncratic outperformance"},
            "generated_at": "2026-10-31T18:00:00Z"
        }
        db.record_movement_explanation(exp)

        # 4. Fetch Movement Explanation
        res = db.get_movement_explanation(symbol="INFY", trading_date="2026-10-26")
        self.assertIsNotNone(res)
        self.assertEqual(res["confidence_level"], "HIGH_CONFIDENCE")
        self.assertEqual(res["full_report"]["summary"], "Strong Q2 beat drove idiosyncratic outperformance")

    def test_baseline_row_counts_reconciliation(self):
        """
        Preflight Check Invariant:
        Reconciles the exact database baseline:
        - ohlcv_daily: 25,106 rows (25,056 post-phase 3 + 50 rows for 2026-10-28 via cm_udiff)
        - fundamental_factors_daily: 210 rows (204 post-phase 3 + 6 rows on 2024-10-23 pilot evaluation)
        """
        con = sqlite3.connect("data/market_lab.db")
        cur = con.cursor()

        ohlcv_count = cur.execute("SELECT count(*) FROM ohlcv_daily").fetchone()[0]
        self.assertGreaterEqual(ohlcv_count, 25106)
        nifty_ohlcv_count = cur.execute("SELECT count(*) FROM ohlcv_daily WHERE symbol IN (SELECT symbol FROM securities_master WHERE is_active = 1)").fetchone()[0]
        self.assertEqual(nifty_ohlcv_count, 25106)

        ff_count = cur.execute("SELECT count(*) FROM fundamental_factors_daily").fetchone()[0]
        self.assertEqual(ff_count, 210)

        # Confirm the 50 rows on 2026-10-28
        rows_20261028 = cur.execute("SELECT count(*) FROM ohlcv_daily WHERE trading_date='2026-10-28'").fetchone()[0]
        self.assertGreaterEqual(rows_20261028, 50)
        nifty_20261028 = cur.execute("SELECT count(*) FROM ohlcv_daily WHERE trading_date='2026-10-28' AND symbol IN (SELECT symbol FROM securities_master WHERE is_active = 1)").fetchone()[0]
        self.assertEqual(nifty_20261028, 50)

        # Confirm date breakdown:
        # 2024-10-23: 49 rows (43 universe constituents + 6 pilot companies reconciled)
        # 2025-05-15: 49 rows
        # 2025-10-23: 6 rows (pilot audit date)
        # 2026-05-15: 50 rows (all 50 active constituents post-demerger)
        # 2026-10-23: 6 rows (pilot audit date)
        # 2026-10-27: 50 rows (all 50 active constituents)
        # Total = 49 + 49 + 6 + 50 + 6 + 50 = 210 rows
        date_counts = dict(cur.execute("SELECT trading_date, count(*) FROM fundamental_factors_daily GROUP BY trading_date").fetchall())
        self.assertEqual(date_counts.get("2024-10-23"), 49)
        self.assertEqual(date_counts.get("2025-05-15"), 49)
        self.assertEqual(date_counts.get("2025-10-23"), 6)
        self.assertEqual(date_counts.get("2026-05-15"), 50)
        self.assertEqual(date_counts.get("2026-10-23"), 6)
        self.assertEqual(date_counts.get("2026-10-27"), 50)
        self.assertEqual(sum(date_counts.values()), 210)


if __name__ == "__main__":
    unittest.main()
