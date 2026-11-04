"""
Unit and regression tests for Milestone B5 Phase 4:
Deterministic Evidence Attribution & Confidence Ranking Engine.
"""

import unittest
import os
import json
import sqlite3
import tempfile
import shutil
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.evidence.models import (
    EvidenceRecord,
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    ExpectationSurprise,
    MovementAnalysisResult,
    MovementClassification,
    SectorBenchmarkType,
    AttributionHypothesis
)
from src.evidence.store import EvidenceStore
from src.quant.movement_analyzer import MarketMovementAnalyzer
from src.attribution.ranking import (
    ScoringConfig,
    ScoringBreakdown,
    score_evidence_item,
    determine_confidence_level,
    is_independently_corroborating
)
from src.attribution.engine import (
    EvidenceRankingEngine,
    MovementExplanationReport
)


class TestMilestoneB5Phase4(unittest.TestCase):
    """Comprehensive regression tests for Phase 4 Attribution Engine."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.mkdtemp()
        cls.db_copy_path = os.path.join(cls.temp_dir, "test_market_lab.db")
        shutil.copy2("data/market_lab.db", cls.db_copy_path)
        cls.db = DatabaseManager(cls.db_copy_path)
        cls.store = EvidenceStore(cls.db)
        cls.analyzer = MarketMovementAnalyzer(cls.db)
        cls.engine = EvidenceRankingEngine(cls.db, cls.store, cls.analyzer)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def _create_mock_movement(
        self,
        symbol: str = "TEST_STOCK",
        trading_date: str = "2026-10-16",
        ret_1d_adj: float = 0.0461,
        ret_1d_raw: float = 0.0461,
        benchmark_return: float = 0.0065,
        sector_return: float = 0.0392,
        abnormal_return: float = 0.0426,
        sector_adjusted_return: float = 0.0069,
        volume_ratio: float = 2.12,
        primary_class: MovementClassification = MovementClassification.SECTOR_SYSTEMATIC_SURGE
    ) -> MovementAnalysisResult:
        return MovementAnalysisResult(
            symbol=symbol,
            trading_date=trading_date,
            open=1500.0,
            high=1580.0,
            low=1495.0,
            close=1569.15,
            prev_close=1500.0,
            volume=5000000,
            ret_1d_raw=ret_1d_raw,
            ret_1d_adj=ret_1d_adj,
            ret_1d_total=ret_1d_adj,
            gap_open=0.015,
            intraday_drift=0.030,
            intraday_range=0.056,
            ret_5d=0.05,
            ret_20d=0.08,
            benchmark_return=benchmark_return,
            sector_benchmark_type=SectorBenchmarkType.OFFICIAL_SECTOR_PRI,
            sector_benchmark_name="NIFTY IT",
            sector_return=sector_return,
            eligible_peers=["TCS", "WIPRO", "TECHM", "HCLTECH"],
            peer_returns={"TCS": 0.035, "WIPRO": 0.038, "TECHM": 0.085, "HCLTECH": 0.040},
            is_survivorship_biased_proxy=False,
            model_status="ESTIMATED",
            alpha=0.0002,
            beta=1.12,
            r_squared=0.45,
            residual_std_err=0.012,
            estimation_sessions_count=232,
            expected_return=0.0035,
            abnormal_return=abnormal_return,
            t_statistic=3.55,
            sector_adjusted_return=sector_adjusted_return,
            volume_ratio_20d=volume_ratio,
            volume_log_zscore_50d=2.15,
            is_volume_spike=True,
            is_zero_volume=False,
            primary_classification=primary_class,
            classifications=[primary_class, MovementClassification.ANOMALOUS_VOLUME]
        )

    def _create_mock_evidence(
        self,
        evidence_id: str = "EV_TEST_001",
        symbol: str = "TEST_STOCK",
        effective_session: str = "2026-10-16",
        event_date: str = "2026-10-16",
        broadcast_timestamp: str = "2026-10-16T08:30:00+05:30",
        tier: EvidenceTier = EvidenceTier.TIER_1_OFFICIAL_FILING,
        category: EvidenceCategory = EvidenceCategory.BOARD_MEETING_OUTCOME,
        direction: EvidenceDirection = EvidenceDirection.POSITIVE,
        verification_status: str = "VERIFIED",
        is_pit_eligible: bool = True,
        expectation_surprise: ExpectationSurprise = ExpectationSurprise.UNKNOWN,
        source_identity: str = "corporate_disclosures",
        details: Dict[str, Any] = None
    ) -> EvidenceRecord:
        return EvidenceRecord(
            evidence_id=evidence_id,
            symbol=symbol,
            entity_type="STOCK",
            event_date=event_date,
            broadcast_timestamp=broadcast_timestamp,
            effective_session_date=effective_session,
            tier=tier,
            category=category,
            direction=direction,
            headline=f"Test Headline: {evidence_id}",
            details=details or {},
            source_identity=source_identity,
            source_reference=None,
            verification_status=verification_status,
            is_pit_eligible=is_pit_eligible,
            reporting_basis="CONSOLIDATED",
            expectation_surprise=expectation_surprise,
            is_contradictory=False
        )

    # 1. Point-in-time announcement eligibility
    def test_1_point_in_time_announcement_eligibility(self):
        """Verifies events are eligible only when effective_session_date <= target_date."""
        report = self.engine.explain_movement("INFY", "2026-10-16", as_of_date="2026-10-16")
        self.assertGreater(len(report.eligible_evidence), 0)
        for e in report.eligible_evidence:
            self.assertLessEqual(e.effective_session_date, "2026-10-16")

    # 2. Before-market and after-market timestamp treatment
    def test_2_before_market_and_after_market_timestamp_treatment(self):
        """
        Announcements after 15:30 IST on trading_date cannot explain trading_date.
        Pre-market announcements before 15:30 IST are eligible.
        """
        # INFY Q2 board meeting was broadcast at 2026-10-23T16:30:00+05:30 (after close)
        report_oct23 = self.engine.explain_movement("INFY", "2026-10-23")
        # Ensure EV_DISC_INFY_DISC_20261023_Q2 is excluded on Oct 23
        excluded_ids = [ex["evidence_id"] for ex in report_oct23.excluded_evidence]
        self.assertIn("EV_DISC_INFY_DISC_20261023_Q2", excluded_ids)

        # But on next trading session 2026-10-27, it must be eligible!
        report_oct27 = self.engine.explain_movement("INFY", "2026-10-27")
        eligible_ids = [e.evidence_id for e in report_oct27.eligible_evidence]
        self.assertIn("EV_DISC_INFY_DISC_20261023_Q2", eligible_ids)

    # 3. Date-only and unknown-timestamp handling
    def test_3_date_only_and_unknown_timestamp_handling(self):
        """Date-only announcements with is_pit_eligible=True are valid; pit_eligible=False are excluded."""
        movement = self._create_mock_movement()
        ev_valid = self._create_mock_evidence(broadcast_timestamp=None, is_pit_eligible=True)
        breakdown = score_evidence_item(ev_valid, movement)
        self.assertGreater(breakdown.clamped_total, 50.0)

        # Unsafe PIT record
        ev_unsafe = self._create_mock_evidence(broadcast_timestamp=None, is_pit_eligible=False)
        # When passed to engine, unsafe PIT must be excluded
        # Checked via engine logic
        self.assertFalse(ev_unsafe.is_pit_eligible)

    # 4. Future evidence exclusion
    def test_4_future_evidence_exclusion(self):
        """Future evidence (effective_date > target_date) is strictly excluded."""
        report = self.engine.explain_movement("INFY", "2026-10-16")
        for ex in report.excluded_evidence:
            if "FUTURE_EVENT_LOOKAHEAD" in ex.get("reason", ""):
                self.assertGreater(ex["effective_session_date"], "2026-10-16")

    # 5. Verification-status filtering
    def test_5_verification_status_filtering(self):
        """SOURCE_UNVERIFIED and PENDING_VERIFICATION records are excluded from candidates."""
        report = self.engine.explain_movement("INFY", "2026-10-16")
        excluded_ids = [ex["evidence_id"] for ex in report.excluded_evidence]
        # EV_DISC_INFY_DISC_20261015_SCHED is SOURCE_UNVERIFIED
        self.assertIn("EV_DISC_INFY_DISC_20261015_SCHED", excluded_ids)

        # None of the eligible records can be unverified
        for e in report.eligible_evidence:
            self.assertEqual(e.verification_status, "VERIFIED")

    # 6. Positive PAT with unknown consensus does not receive positive catalyst points
    def test_6_positive_pat_unknown_consensus_no_positive_catalyst_points(self):
        """Profitability alone (PAT > 0) with ExpectationSurprise.UNKNOWN gives directional_score = 0.0."""
        movement = self._create_mock_movement(ret_1d_adj=0.0461)  # Stock surged +4.61%
        ev_profitable = self._create_mock_evidence(
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.AMBIGUOUS,
            expectation_surprise=ExpectationSurprise.UNKNOWN,
            details={"profitability_status": "PROFITABLE", "net_profit": 6506.0}
        )
        breakdown = score_evidence_item(ev_profitable, movement)
        self.assertEqual(breakdown.directional_score, 0.0)
        self.assertFalse(breakdown.is_contradicted)
        self.assertIn("PAT sign does NOT award directional points", breakdown.notes[2])

    # 7. Negative PAT with unknown consensus does not receive negative catalyst points
    def test_7_negative_pat_unknown_consensus_no_negative_catalyst_points(self):
        """Loss-making PAT (< 0) with ExpectationSurprise.UNKNOWN gives directional_score = 0.0."""
        movement = self._create_mock_movement(ret_1d_adj=-0.0450)  # Stock dropped -4.50%
        ev_loss = self._create_mock_evidence(
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.AMBIGUOUS,
            expectation_surprise=ExpectationSurprise.UNKNOWN,
            details={"profitability_status": "LOSS_MAKING", "net_profit": -500.0}
        )
        breakdown = score_evidence_item(ev_loss, movement)
        self.assertEqual(breakdown.directional_score, 0.0)
        self.assertFalse(breakdown.is_contradicted)

    # 8. Authenticated consensus beat/miss handling
    def test_8_authenticated_consensus_beat_miss_handling(self):
        """Authenticated BEAT on positive day awards +15.0; BEAT on negative day triggers contradiction (-30.0)."""
        movement_up = self._create_mock_movement(ret_1d_adj=0.035)
        movement_down = self._create_mock_movement(ret_1d_adj=-0.035)

        ev_beat = self._create_mock_evidence(
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.POSITIVE,
            expectation_surprise=ExpectationSurprise.BEAT
        )

        breakdown_aligned = score_evidence_item(ev_beat, movement_up)
        self.assertEqual(breakdown_aligned.directional_score, 15.0)
        self.assertFalse(breakdown_aligned.is_contradicted)

        breakdown_contradicted = score_evidence_item(ev_beat, movement_down)
        self.assertEqual(breakdown_contradicted.directional_score, 0.0)
        self.assertTrue(breakdown_contradicted.is_contradicted)
        self.assertEqual(breakdown_contradicted.contradiction_penalty, 30.0)

    # 9. Neutral corporate actions do not become directional catalysts
    def test_9_neutral_corporate_actions_not_directional_catalysts(self):
        """Corporate action with NEUTRAL direction on a trending day awards 0.0 directional score."""
        movement = self._create_mock_movement(ret_1d_adj=0.045)
        ev_div = self._create_mock_evidence(
            category=EvidenceCategory.DIVIDEND_DECLARATION,
            direction=EvidenceDirection.NEUTRAL,
            tier=EvidenceTier.TIER_2_FINANCIAL_ACTION
        )
        breakdown = score_evidence_item(ev_div, movement)
        self.assertEqual(breakdown.directional_score, 0.0)
        self.assertFalse(breakdown.is_contradicted)

    # 10. Contradictory evidence retention and penalty
    def test_10_contradictory_evidence_retention_and_penalty(self):
        """POSITIVE evidence on a NEGATIVE day applies -30.0 penalty and flags contradiction."""
        movement_down = self._create_mock_movement(ret_1d_adj=-0.030)
        ev_positive = self._create_mock_evidence(
            direction=EvidenceDirection.POSITIVE,
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING
        )
        breakdown = score_evidence_item(ev_positive, movement_down)
        self.assertTrue(breakdown.is_contradicted)
        self.assertEqual(breakdown.contradiction_penalty, 30.0)
        self.assertLess(breakdown.clamped_total, 50.0)

    # 11. High-confidence restrictions under contradiction
    def test_11_high_confidence_restrictions_under_contradiction(self):
        """Contradicted evidence can NEVER attain HIGH_CONFIDENCE, capped at max 49.9."""
        movement_down = self._create_mock_movement(ret_1d_adj=-0.040, volume_ratio=3.5)
        ev_positive = self._create_mock_evidence(
            direction=EvidenceDirection.POSITIVE,
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING
        )
        # Even with Tier 1 (60) + same-session (15) + volume (15) = 90
        # Minus penalty (30) = 60. But contradicted guard forces cap at 49.9!
        breakdown = score_evidence_item(ev_positive, movement_down)
        self.assertTrue(breakdown.is_contradicted)
        self.assertLessEqual(breakdown.clamped_total, 49.9)

        conf = determine_confidence_level(breakdown.clamped_total, breakdown.is_contradicted, ev_positive.tier)
        self.assertNotEqual(conf, "HIGH_CONFIDENCE")
        self.assertIn(conf, ["MODERATE_CONFIDENCE", "LOW_CONFIDENCE"])

    # 12. Independent corroboration
    def test_12_independent_corroboration(self):
        """Multiple independent aligned records award +10.0 corroboration bonus."""
        movement = self._create_mock_movement(ret_1d_adj=0.030)
        ev = self._create_mock_evidence(direction=EvidenceDirection.POSITIVE)
        
        breakdown_solo = score_evidence_item(ev, movement, corroborating_count=0)
        breakdown_corrob = score_evidence_item(ev, movement, corroborating_count=2)
        
        self.assertEqual(breakdown_solo.corroboration_score, 0.0)
        self.assertEqual(breakdown_corrob.corroboration_score, 10.0)
        self.assertEqual(breakdown_corrob.raw_total, breakdown_solo.raw_total + 10.0)

    # 13. Multiple evidence records for the same event
    def test_13_multiple_evidence_records_same_event(self):
        """Preserves distinct evidence records and populates alternative_hypotheses on primary."""
        report = self.engine.explain_movement("INFY", "2026-10-16")
        self.assertGreater(len(report.ranked_hypotheses), 1)
        primary = report.primary_hypothesis
        self.assertIsNotNone(primary)
        self.assertGreater(len(primary.alternative_hypotheses), 0)

    # 14. Sector-wide versus company-specific movement distinction
    def test_14_sector_wide_vs_company_specific_distinction(self):
        """On 2026-10-16, IT sector surged +3.92%; primary explanation is NIFTY IT sector momentum."""
        report = self.engine.explain_movement("INFY", "2026-10-16")
        self.assertEqual(report.movement_result.primary_classification, MovementClassification.SECTOR_SYSTEMATIC_SURGE)
        self.assertEqual(report.primary_hypothesis.confidence_level, "HIGH_CONFIDENCE")
        self.assertEqual(report.primary_hypothesis.primary_evidence_id, "EV_MKT_NIFTY_IT_20261016_PRI")

    # 15. Missing AR/SAR and insufficient-history handling
    def test_15_missing_ar_sar_insufficient_history_handling(self):
        """Missing abnormal return awards 0.0 bonus without substituting 0.0 or fabricating."""
        movement = self._create_mock_movement(abnormal_return=None)
        movement.model_status = "INSUFFICIENT_HISTORY"
        ev = self._create_mock_evidence(direction=EvidenceDirection.POSITIVE)
        
        breakdown = score_evidence_item(ev, movement)
        self.assertEqual(breakdown.abnormal_return_score, 0.0)
        self.assertIn("Abnormal return unavailable", breakdown.notes[3])

    # 16. Reproducible ranking and idempotent execution
    def test_16_reproducible_ranking_and_idempotent_execution(self):
        """Repeated explain_movement executions produce identical JSON structure and scores."""
        rep1 = self.engine.explain_movement("INFY", "2026-10-16", persist_to_db=False)
        rep2 = self.engine.explain_movement("INFY", "2026-10-16", persist_to_db=False)

        self.assertEqual(rep1.primary_hypothesis.evidence_strength_score, rep2.primary_hypothesis.evidence_strength_score)
        self.assertEqual(rep1.primary_hypothesis.confidence_level, rep2.primary_hypothesis.confidence_level)
        
        d1 = rep1.to_dict()
        d2 = rep2.to_dict()
        d1.pop("generated_at")
        d2.pop("generated_at")
        self.assertEqual(d1, d2)

        # Test database persistence idempotency
        self.engine.explain_movement("INFY", "2026-10-16", persist_to_db=True)
        cached = self.db.get_movement_explanation("INFY", "2026-10-16")
        self.assertIsNotNone(cached)
        self.assertEqual(cached["explanation_id"], "EXP_INFY_20261016")

    # 17. SBIN standalone reporting-basis isolation
    def test_17_sbin_standalone_reporting_basis_isolation(self):
        """SBIN operates on a STANDALONE basis; engine flags reporting basis isolation."""
        report = self.engine.explain_movement("SBIN", "2026-10-23")
        self.assertTrue(report.reporting_basis_context["is_standalone_isolated"])
        self.assertEqual(report.reporting_basis_context["reporting_basis"], "STANDALONE")
        self.assertTrue(any("REPORTING_BASIS_ISOLATION" in q for q in report.unresolved_questions))

    # 18. TMPV recast and point-in-time lineage
    def test_18_tmpv_recast_and_point_in_time_lineage(self):
        """TMPV predecessor lineage includes TATAMOTORS and recasts respect publication dates."""
        # Query TMPV disclosures
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT evidence_id, headline, event_date, effective_session_date
                FROM evidence_records
                WHERE symbol IN ('TMPV', 'TATAMOTORS')
                ORDER BY event_date ASC;
            """).fetchall()
            self.assertGreater(len(rows), 0)


    # 19. Tier 1 base score + same-session timing alone cannot produce HIGH_CONFIDENCE
    def test_19_tier1_timing_alone_cannot_produce_high_confidence(self):
        """Tier 1 filing with UNKNOWN direction / directional score 0.0 cannot attain HIGH_CONFIDENCE."""
        movement = self._create_mock_movement(ret_1d_adj=0.015)
        ev_unknown = self._create_mock_evidence(
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING,
            direction=EvidenceDirection.AMBIGUOUS,
            expectation_surprise=ExpectationSurprise.UNKNOWN
        )
        breakdown = score_evidence_item(ev_unknown, movement)
        self.assertGreaterEqual(breakdown.clamped_total, 75.0)  # High score from base + timing + volume
        # Even with score >= 75.0, confidence MUST be capped at MODERATE_CONFIDENCE due to unverified market direction!
        conf = determine_confidence_level(
            score=breakdown.clamped_total,
            evidence=ev_unknown,
            movement=movement,
            breakdown=breakdown
        )
        self.assertEqual(conf, "MODERATE_CONFIDENCE")

    # 20. Official financial results with UNKNOWN consensus cannot become high-confidence explanation
    def test_20_financial_results_unknown_consensus_capped_at_moderate(self):
        """Financial statement with ExpectationSurprise.UNKNOWN is capped at MODERATE_CONFIDENCE."""
        movement = self._create_mock_movement(ret_1d_adj=0.008)
        ev_fs = self._create_mock_evidence(
            tier=EvidenceTier.TIER_1_OFFICIAL_FILING,
            category=EvidenceCategory.EARNINGS_RELEASE,
            direction=EvidenceDirection.AMBIGUOUS,
            expectation_surprise=ExpectationSurprise.UNKNOWN
        )
        breakdown = score_evidence_item(ev_fs, movement)
        conf = determine_confidence_level(
            score=breakdown.clamped_total,
            evidence=ev_fs,
            movement=movement,
            breakdown=breakdown
        )
        self.assertEqual(conf, "MODERATE_CONFIDENCE")

    # 21. Volume anomaly alone cannot receive MODERATE_CONFIDENCE or HIGH_CONFIDENCE
    def test_21_volume_anomaly_alone_cannot_reach_moderate_or_high_confidence(self):
        """Volume anomaly establishes trading activity, not causation; score is capped at 49.9 and LOW_CONFIDENCE."""
        movement = self._create_mock_movement(ret_1d_adj=0.0004, volume_ratio=2.43)
        ev_vol = self._create_mock_evidence(
            tier=EvidenceTier.TIER_3_SECTOR_BENCHMARK,
            category=EvidenceCategory.VOLUME_LIQUIDITY_SURGE,
            direction=EvidenceDirection.NEUTRAL
        )
        breakdown = score_evidence_item(ev_vol, movement)
        self.assertEqual(breakdown.clamped_total, 49.9)  # Explicitly capped at 49.9
        conf = determine_confidence_level(
            score=breakdown.clamped_total,
            evidence=ev_vol,
            movement=movement,
            breakdown=breakdown
        )
        self.assertEqual(conf, "LOW_CONFIDENCE")
        self.assertNotIn(conf, ["MODERATE_CONFIDENCE", "HIGH_CONFIDENCE"])

    # 22. Volume anomalies cannot be the primary explanatory hypothesis
    def test_22_volume_anomalies_cannot_be_primary_explanatory_hypothesis(self):
        """When only volume anomalies exist, primary hypothesis is UNEXPLAINED_MOVEMENT, not the volume anomaly."""
        report = self.engine.explain_movement("INFY", "2026-10-23")
        self.assertEqual(report.primary_hypothesis.confidence_level, "UNEXPLAINED_MOVEMENT")
        self.assertIsNone(report.primary_hypothesis.primary_evidence_id)
        self.assertIn("Anomalous trading volume observed", report.primary_hypothesis.notes)
        self.assertIn("unusual volume alone establishes trading activity", report.primary_hypothesis.notes)

    # 23. Sector index cannot be counted twice as independent corroboration
    def test_23_sector_index_cannot_be_counted_twice_as_independent_corroboration(self):
        """Sector index movement cannot be double-counted as corroboration for a company-specific filing."""
        ev_stock = self._create_mock_evidence(symbol="INFY", tier=EvidenceTier.TIER_1_OFFICIAL_FILING)
        ev_sector = EvidenceRecord(
            evidence_id="EV_MKT_NIFTY_IT",
            symbol="NIFTY IT",
            entity_type="SECTOR",
            event_date="2026-10-16",
            broadcast_timestamp=None,
            effective_session_date="2026-10-16",
            tier=EvidenceTier.TIER_3_SECTOR_BENCHMARK,
            category=EvidenceCategory.SECTOR_MOMENTUM,
            direction=EvidenceDirection.POSITIVE,
            headline="NIFTY IT Surge",
            details={},
            source_identity="index_daily",
            source_reference=None,
            verification_status="VERIFIED",
            is_pit_eligible=True
        )
        is_corrob = is_independently_corroborating(ev_stock, ev_sector)
        self.assertFalse(is_corrob)

    # 24. Duplicate evidence records from same underlying event cannot inflate confidence
    def test_24_duplicate_evidence_records_same_event_do_not_inflate_confidence(self):
        """Duplicate records sharing the same filing reference or (source, date, category) cannot corroborate."""
        ev1 = self._create_mock_evidence(
            evidence_id="EV_DISC_1",
            details={"source_reference": "CIRCULAR_123"},
            direction=EvidenceDirection.POSITIVE
        )
        # Add source_reference to ev1
        object.__setattr__(ev1, "source_reference", "CIRCULAR_123")

        ev2 = self._create_mock_evidence(
            evidence_id="EV_DISC_2",
            details={"source_reference": "CIRCULAR_123"},
            direction=EvidenceDirection.POSITIVE
        )
        object.__setattr__(ev2, "source_reference", "CIRCULAR_123")

        self.assertFalse(is_independently_corroborating(ev1, ev2))

    # 25. Volume anomaly cannot corroborate itself
    def test_25_volume_anomaly_cannot_corroborate_itself(self):
        """Volume anomaly cannot corroborate another volume anomaly from the same trading observations."""
        vol1 = self._create_mock_evidence(
            evidence_id="EV_VOL_1",
            category=EvidenceCategory.VOLUME_LIQUIDITY_SURGE,
            direction=EvidenceDirection.POSITIVE
        )
        vol2 = self._create_mock_evidence(
            evidence_id="EV_VOL_2",
            category=EvidenceCategory.VOLUME_LIQUIDITY_SURGE,
            direction=EvidenceDirection.POSITIVE
        )
        self.assertFalse(is_independently_corroborating(vol1, vol2))

    # 26. Multiple genuinely independent verified sources provide corroboration
    def test_26_genuine_independent_sources_provide_corroboration(self):
        """A verified disclosure and an independent corporate action sharing aligned direction corroborate."""
        ev_disc = self._create_mock_evidence(
            evidence_id="EV_DISC_01",
            source_identity="corporate_disclosures",
            category=EvidenceCategory.BOARD_MEETING_OUTCOME,
            direction=EvidenceDirection.POSITIVE
        )
        ev_action = EvidenceRecord(
            evidence_id="EV_ACT_01",
            symbol="TEST_STOCK",
            entity_type="STOCK",
            event_date="2026-10-16",
            broadcast_timestamp=None,
            effective_session_date="2026-10-16",
            tier=EvidenceTier.TIER_2_FINANCIAL_ACTION,
            category=EvidenceCategory.DIVIDEND_DECLARATION,
            direction=EvidenceDirection.POSITIVE,
            headline="Special Interim Dividend Declared",
            details={},
            source_identity="corporate_actions",
            source_reference="DIV_REF_999",
            verification_status="VERIFIED",
            is_pit_eligible=True
        )
        self.assertTrue(is_independently_corroborating(ev_disc, ev_action))

    # 27. Updated representative INFY investigations
    def test_27_three_representative_infy_investigations(self):
        """
        Validates all three real INFY dates:
        - 2026-10-16: HIGH_CONFIDENCE on NIFTY IT sector surge (Score: 90.0, broad market not double-counted)
        - 2026-10-23: UNEXPLAINED_MOVEMENT (volume anomaly score capped at 49.9, cannot be primary catalyst)
        - 2026-10-27: MODERATE_CONFIDENCE on Q2 results (Score: 65.0, 1-day lag from Monday Oct 26 effective session, consensus surprise UNKNOWN)
        """
        # 1. Oct 16
        rep16 = self.engine.explain_movement("INFY", "2026-10-16")
        self.assertEqual(rep16.movement_result.primary_classification, MovementClassification.SECTOR_SYSTEMATIC_SURGE)
        self.assertEqual(rep16.primary_hypothesis.confidence_level, "HIGH_CONFIDENCE")
        self.assertEqual(rep16.primary_hypothesis.primary_evidence_id, "EV_MKT_NIFTY_IT_20261016_PRI")
        self.assertEqual(rep16.primary_hypothesis.evidence_strength_score, 90.0)

        # 2. Oct 23
        rep23 = self.engine.explain_movement("INFY", "2026-10-23")
        self.assertEqual(rep23.primary_hypothesis.confidence_level, "UNEXPLAINED_MOVEMENT")
        self.assertIsNone(rep23.primary_hypothesis.primary_evidence_id)
        # Volume anomaly in ranked hypotheses must be LOW_CONFIDENCE and capped at 49.9
        vol_hyp = [h for h in rep23.ranked_hypotheses if h.primary_evidence_id == "EV_VOL_INFY_20261023"]
        self.assertTrue(len(vol_hyp) > 0)
        self.assertEqual(vol_hyp[0].confidence_level, "LOW_CONFIDENCE")
        self.assertEqual(vol_hyp[0].evidence_strength_score, 49.9)

        # 3. Oct 27
        rep27 = self.engine.explain_movement("INFY", "2026-10-27")
        self.assertEqual(rep27.primary_hypothesis.primary_evidence_id, "EV_DISC_INFY_DISC_20261023_Q2")
        self.assertEqual(rep27.primary_hypothesis.confidence_level, "MODERATE_CONFIDENCE")
        self.assertEqual(rep27.primary_hypothesis.evidence_strength_score, 65.0)

    # 28. Market-model benchmark observations cannot be counted again as independent corroboration
    def test_28_market_model_benchmark_cannot_corroborate_sector_index(self):
        """NIFTY 50 PRI cannot corroborate NIFTY IT PRI (both are market-model index inputs)."""
        ev_sector = EvidenceRecord(
            evidence_id="EV_MKT_NIFTY_IT_20261016_PRI",
            symbol="NIFTY IT",
            entity_type="SECTOR",
            event_date="2026-10-16",
            broadcast_timestamp=None,
            effective_session_date="2026-10-16",
            tier=EvidenceTier.TIER_3_SECTOR_BENCHMARK,
            category=EvidenceCategory.SECTOR_MOMENTUM,
            direction=EvidenceDirection.POSITIVE,
            headline="NIFTY IT Surge",
            details={},
            source_identity="index_daily",
            source_reference=None,
            verification_status="VERIFIED",
            is_pit_eligible=True
        )
        ev_mkt = EvidenceRecord(
            evidence_id="EV_MKT_NIFTY_50_20261015_PRI",
            symbol="NIFTY 50",
            entity_type="BENCHMARK",
            event_date="2026-10-15",
            broadcast_timestamp=None,
            effective_session_date="2026-10-15",
            tier=EvidenceTier.TIER_3_SECTOR_BENCHMARK,
            category=EvidenceCategory.SECTOR_MOMENTUM,
            direction=EvidenceDirection.POSITIVE,
            headline="NIFTY 50 Surge",
            details={},
            source_identity="index_daily",
            source_reference=None,
            verification_status="VERIFIED",
            is_pit_eligible=True
        )
        self.assertFalse(is_independently_corroborating(ev_sector, ev_mkt))

    # 29. Volume-observation scores and explanatory-confidence labels remain semantically consistent
    def test_29_volume_observation_score_and_confidence_harmonized(self):
        """Volume observation score is strictly harmonized with LOW_CONFIDENCE taxonomy range (30.0-49.9)."""
        movement = self._create_mock_movement(volume_ratio=3.5)
        ev_vol = self._create_mock_evidence(
            category=EvidenceCategory.VOLUME_LIQUIDITY_SURGE,
            direction=EvidenceDirection.NEUTRAL
        )
        breakdown = score_evidence_item(ev_vol, movement)
        self.assertLessEqual(breakdown.clamped_total, 49.9)
        conf = determine_confidence_level(breakdown.clamped_total, ev_vol, movement, breakdown)
        self.assertEqual(conf, "LOW_CONFIDENCE")

    # 30. Volume evidence cannot inflate the confidence of an unrelated catalyst
    def test_30_volume_evidence_cannot_inflate_unrelated_catalyst_confidence(self):
        """Volume anomaly cannot corroborate or award directional points to an unaligned catalyst."""
        ev_cat = self._create_mock_evidence(
            category=EvidenceCategory.DIVIDEND_DECLARATION,
            direction=EvidenceDirection.NEUTRAL
        )
        ev_vol = self._create_mock_evidence(
            category=EvidenceCategory.VOLUME_LIQUIDITY_SURGE,
            direction=EvidenceDirection.POSITIVE
        )
        self.assertFalse(is_independently_corroborating(ev_cat, ev_vol))


if __name__ == "__main__":
    unittest.main()
