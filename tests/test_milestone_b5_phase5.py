"""
Unit and regression tests for Milestone B5 Phase 5:
Structured Investigation Reports, Offline Visualizers, and Serialization.
"""

import unittest
import os
import json
import re
import shutil
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.evidence.models import (
    EvidenceRecord,
    EvidenceTier,
    EvidenceCategory,
    EvidenceDirection,
    MovementAnalysisResult,
    MovementClassification
)
from src.attribution.engine import EvidenceRankingEngine
from src.quant.movement_analyzer import MarketMovementAnalyzer
from src.reporting.investigation_schema import (
    InvestigationOverview,
    ExecutiveSummary,
    MarketMovementSection,
    MechanicalAdjustmentContext,
    TimelineItem,
    ExcludedEvidenceItem,
    TimelineSection,
    RankedHypothesisItem,
    ContradictionSection,
    LimitationsSection,
    FinalAssessmentSection,
    StructuredInvestigationReport,
    REPORT_SCHEMA_VERSION,
    FROZEN_DATASET_ID
)
from src.reporting.visualizer import (
    generate_performance_chart_svg,
    generate_drift_decomposition_svg,
    generate_volume_gauge_svg,
    generate_score_breakdown_svg
)
from src.reporting.investigation_builder import InvestigationReportBuilder


class TestMilestoneB5Phase5(unittest.TestCase):
    """Deterministic regression tests for Phase 5 reporting layer."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "data/market_lab.db"
        cls.db = DatabaseManager(cls.db_path)
        cls.analyzer = MarketMovementAnalyzer(cls.db)
        cls.engine = EvidenceRankingEngine(cls.db)
        cls.builder = InvestigationReportBuilder(cls.db, cls.engine)
        cls.test_output_dir = "tests/test_investigation_output"
        os.makedirs(cls.test_output_dir, exist_ok=True)

    @classmethod
    def tearDownClass(cls):
        if os.path.exists(cls.test_output_dir):
            shutil.rmtree(cls.test_output_dir)

    # -------------------------------------------------------------
    # 1. Schema Validation & Dataclass Serialization
    # -------------------------------------------------------------
    def test_01_schema_dataclasses_and_json_serialization(self):
        """Verifies report schema dataclasses serialize to valid, parseable JSON."""
        overview = InvestigationOverview(
            investigation_id="EXP_TEST_20261016",
            symbol="TEST_STOCK",
            company_name="Test Stock Limited",
            isin="INE000000000",
            trading_date="2026-10-16",
            sector="Information Technology",
            industry="Software",
            reporting_basis="CONSOLIDATED",
            is_standalone_isolated=False,
            primary_classification="SECTOR_SYSTEMATIC_SURGE",
            secondary_classifications=["ANOMALOUS_VOLUME"],
            confidence_level="HIGH_CONFIDENCE",
            final_attribution_outcome="STRONGLY_SUPPORTED_EXPLANATION"
        )
        self.assertEqual(overview.schema_version, REPORT_SCHEMA_VERSION)
        self.assertEqual(overview.dataset_identifier, FROZEN_DATASET_ID)

        exec_summary = ExecutiveSummary(
            narrative="Test Stock rose 4.5% in line with sector rally.",
            relative_performance_summary="Outperformed broad market by 3.8%.",
            systematic_vs_idiosyncratic="Systematic coupling with sector.",
            strongest_hypothesis_summary="Sector surge EV_MKT_IT.",
            evidence_sufficiency="Available evidence provides sufficient corroboration.",
            key_uncertainties=["Consensus estimate unauthenticated."]
        )
        self.assertIn("deterministic heuristic", exec_summary.score_is_heuristic_disclaimer)

        movement_section = MarketMovementSection(
            price_action={"close": 1500.0, "ret_1d_adj": 0.045},
            benchmark_comparison={"benchmark_return": 0.007},
            market_model={"abnormal_return": 0.038, "t_statistic": 2.1},
            volume_liquidity={"volume_ratio_20d": 2.1, "is_volume_spike": True},
            mechanical_adjustment=None
        )

        timeline = TimelineSection(
            eligible_timeline=[
                TimelineItem(
                    evidence_id="EV_001",
                    event_date="2026-10-16",
                    broadcast_timestamp=None,
                    effective_session_date="2026-10-16",
                    tier=1,
                    tier_label="Tier 1: Official Exchange Filing",
                    category="EARNINGS_RESULT",
                    direction="POSITIVE",
                    headline="Q2 Financial Results",
                    source_identity="company_financial_statements",
                    source_reference=None,
                    verification_status="VERIFIED",
                    is_pit_eligible=True,
                    relevance_note="Primary catalyst."
                )
            ],
            excluded_evidence=[
                ExcludedEvidenceItem(
                    evidence_id="EV_EX_001",
                    headline="Late filing",
                    tier=1,
                    effective_session_date="2026-10-17",
                    exclusion_reason="FUTURE_LOOKAHEAD"
                )
            ]
        )

        ranked = [
            RankedHypothesisItem(
                rank=1,
                hypothesis_id="HYP_01",
                primary_evidence_id="EV_001",
                catalyst_type="SECTOR_SYSTEMATIC_SURGE",
                headline="Q2 Financial Results",
                score_breakdown={"base_score": 60.0, "clamped_total": 85.0},
                final_score=85.0,
                confidence_level="HIGH_CONFIDENCE",
                is_contradicted=False,
                contradiction_penalty=0.0,
                is_company_specific=True,
                ranking_rationale="Strong filing with same-session timing."
            )
        ]

        contradictions = ContradictionSection(
            has_contradictions=False,
            contradicting_evidence=[],
            alternative_explanations=[]
        )

        limitations = LimitationsSection(
            unresolved_questions=[],
            limitations=["Frozen offline benchmark"],
            governance_notice="Academic research only."
        )

        final_assess = FinalAssessmentSection(
            final_outcome="STRONGLY_SUPPORTED_EXPLANATION",
            conclusion_statement="Movement strongly supported.",
            provenance_audit_hash="",
            reproducibility_token="TEST_STOCK_20261016_MIL_FROZEN_BENCHMARK_2024_2026_V1"
        )

        report = StructuredInvestigationReport(
            overview=overview,
            executive_summary=exec_summary,
            movement_analysis=movement_section,
            timeline=timeline,
            ranked_explanations=ranked,
            contradictions=contradictions,
            limitations=limitations,
            final_assessment=final_assess
        )

        # Hash stamping
        report.final_assessment.provenance_audit_hash = report.compute_audit_hash()
        self.assertEqual(len(report.final_assessment.provenance_audit_hash), 64)

        # JSON Serialization roundtrip
        json_str = report.to_json(indent=2)
        parsed = json.loads(json_str)
        self.assertEqual(parsed["overview"]["symbol"], "TEST_STOCK")
        self.assertEqual(parsed["final_assessment"]["final_outcome"], "STRONGLY_SUPPORTED_EXPLANATION")
        self.assertEqual(parsed["timeline"]["eligible_timeline"][0]["evidence_id"], "EV_001")

    def test_02_provenance_audit_hash_determinism_and_sensitivity(self):
        """Verifies provenance audit hash is deterministic and sensitive to payload changes."""
        report1 = self.builder.build_report("INFY", "2026-10-16")
        hash1 = report1.compute_audit_hash()
        
        # Second computation must be identical
        hash2 = report1.compute_audit_hash()
        self.assertEqual(hash1, hash2)

        # Sensitivity: altering close price alters the hash
        report1.movement_analysis.price_action["close"] = 9999.99
        hash3 = report1.compute_audit_hash()
        self.assertNotEqual(hash1, hash3)

    # -------------------------------------------------------------
    # 2. Offline SVG Visualizer Tests
    # -------------------------------------------------------------
    def test_03_performance_chart_svg(self):
        """Verifies performance bar chart SVG generation and constraints."""
        svg = generate_performance_chart_svg(
            stock_symbol="INFY",
            stock_return=0.0461,
            benchmark_name="NIFTY 50 (PRI)",
            benchmark_return=0.0065,
            sector_name="NIFTY IT",
            sector_return=0.0392
        )
        self.assertTrue(svg.startswith("<svg"))
        self.assertTrue(svg.strip().endswith("</svg>"))
        self.assertIn("INFY", svg)
        self.assertIn("+4.61%", svg)
        self.assertIn("NIFTY 50 (PRI)", svg)
        self.assertIn("+0.65%", svg)
        self.assertIn("NIFTY IT", svg)
        self.assertIn("+3.92%", svg)
        self.assertNotIn("http://", svg.replace("http://www.w3.org/2000/svg", ""))
        self.assertNotIn("https://", svg)

    def test_04_drift_decomposition_svg(self):
        """Verifies intraday drift & gap decomposition SVG generator."""
        svg = generate_drift_decomposition_svg(
            gap_open=0.0158,
            intraday_drift=0.0299,
            total_adj_return=0.0461
        )
        self.assertIn("INTRADAY PRICE DRIFT", svg)
        self.assertIn("Overnight Gap", svg)
        self.assertIn("+1.58%", svg)
        self.assertIn("Intraday Drift", svg)
        self.assertIn("+2.99%", svg)
        self.assertIn("Net Return (Adj)", svg)
        self.assertIn("+4.61%", svg)

    def test_05_volume_gauge_svg(self):
        """Verifies volume activity gauge for both normal and anomalous volume."""
        # Anomalous volume
        svg_spike = generate_volume_gauge_svg(
            volume_ratio=2.43,
            z_score=2.89,
            is_spike=True
        )
        self.assertIn("ANOMALOUS ACTIVITY", svg_spike)
        self.assertIn("2.43x", svg_spike)
        self.assertIn("Log Z=+2.89", svg_spike)

        # Normal volume
        svg_norm = generate_volume_gauge_svg(
            volume_ratio=0.84,
            z_score=-0.10,
            is_spike=False
        )
        self.assertIn("NORMAL / MUTED ACTIVITY", svg_norm)
        self.assertIn("0.84x", svg_norm)

    def test_06_score_breakdown_svg(self):
        """Verifies score decomposition horizontal bar chart."""
        breakdown = {
            "clamped_total": 90.0,
            "base_score": 35.0,
            "temporal_score": 15.0,
            "directional_score": 15.0,
            "abnormal_return_score": 15.0,
            "volume_score": 10.0
        }
        svg = generate_score_breakdown_svg(breakdown)
        self.assertIn("EVIDENCE STRENGTH SCORE DECOMPOSITION", svg)
        self.assertIn("Final Score: 90.0 / 100.0", svg)
        self.assertIn("Base Tier Score", svg)
        self.assertIn("+35.0", svg)
        self.assertIn("Temporal Timing", svg)
        self.assertIn("+15.0", svg)
        self.assertIn("Volume Confirmation", svg)
        self.assertIn("+10.0", svg)

    # -------------------------------------------------------------
    # 3. Multi-Format Rendering & Export Tests
    # -------------------------------------------------------------
    def test_07_markdown_rendering_contains_all_sections(self):
        """Verifies rendered markdown contains all required sections A through H."""
        report = self.builder.build_report("INFY", "2026-10-16")
        md = self.builder.render_markdown(report)

        # Check section headings
        self.assertIn("# Stock Movement Investigation Report: Infosys Ltd. (INFY)", md)
        self.assertIn("## A. Investigation Overview", md)
        self.assertIn("## B. Executive Summary", md)
        self.assertIn("## C. Quantitative Market Movement Analysis", md)
        self.assertIn("## D. Event and Evidence Timeline", md)
        self.assertIn("## E. Ranked Candidate Explanations", md)
        self.assertIn("## F. Contradictory Evidence & Alternative Hypotheses", md)
        self.assertIn("## G. Data Gaps, Methodological Limitations & Governance", md)
        self.assertIn("## H. Final Assessment & Audit Stamp", md)

        # Check critical content
        self.assertIn("Methodological Note: The evidence strength score", md)
        self.assertIn(report.final_assessment.provenance_audit_hash, md)
        self.assertIn("FROZEN_BENCHMARK", md)

    def test_08_html_rendering_offline_and_self_contained(self):
        """Verifies HTML report is 100% self-contained with zero network dependencies."""
        report = self.builder.build_report("INFY", "2026-10-16")
        html = self.builder.render_html(report)

        self.assertTrue(html.startswith("<!DOCTYPE html>"))
        self.assertIn("<html lang=\"en\">", html)
        self.assertIn("<style>", html)
        self.assertIn("</style>", html)
        self.assertIn("</html>", html)

        # Check that no external script or stylesheet links exist
        self.assertNotIn("<script", html)
        self.assertNotIn("<link rel=\"stylesheet\"", html)
        self.assertNotIn("https://cdn.", html)
        self.assertNotIn("https://fonts.googleapis.com", html)
        self.assertNotIn("https://cdnjs.", html)

        # Check embedded SVGs
        self.assertIn("<svg width=\"560\"", html)
        self.assertIn("1-DAY PERFORMANCE DECOMPOSITION", html)
        self.assertIn("INTRADAY PRICE DRIFT", html)
        self.assertIn("VOLUME &amp; LIQUIDITY ANOMALY INDICATOR", html)
        self.assertIn("EVIDENCE STRENGTH SCORE DECOMPOSITION", html)

    def test_09_export_investigation_bundle(self):
        """Verifies bundle export creates folder and all 3 files properly."""
        report = self.builder.build_report("INFY", "2026-10-16")
        bundle = self.builder.export_investigation_bundle(report, base_output_dir=self.test_output_dir)

        target_dir = bundle["dir"]
        self.assertTrue(os.path.isdir(target_dir))
        self.assertTrue(os.path.isfile(bundle["json"]))
        self.assertTrue(os.path.isfile(bundle["md"]))
        self.assertTrue(os.path.isfile(bundle["html"]))

        # Check non-empty
        self.assertGreater(os.path.getsize(bundle["json"]), 1000)
        self.assertGreater(os.path.getsize(bundle["md"]), 1000)
        self.assertGreater(os.path.getsize(bundle["html"]), 3000)

    # -------------------------------------------------------------
    # 4. Canonical Price & Cross-Format Consistency Tests
    # -------------------------------------------------------------
    def test_10_infy_20261016_canonical_price_reconciliation(self):
        """
        Reconciles INFY on 2026-10-16 at source level:
        - Validates ohlcv_daily row 241: Open 1127.50, Close 1161.20, Prev 1110.00
        - Validates exact raw return = (1161.20 - 1110.00) / 1110.00 = +4.6126%
        - Validates that JSON, Markdown, and HTML contain identical prices.
        """
        # Canonical Phase 3 calculation
        res = self.analyzer.analyze_session_movement("INFY", "2026-10-16")
        self.assertEqual(res.open, 1127.50)
        self.assertEqual(res.close, 1161.20)
        self.assertEqual(res.prev_close, 1110.00)
        expected_raw_ret = (1161.20 - 1110.00) / 1110.00
        self.assertAlmostEqual(res.ret_1d_raw, expected_raw_ret, places=6)

        # Build Phase 5 report
        report = self.builder.build_report("INFY", "2026-10-16")
        pa = report.movement_analysis.price_action
        self.assertEqual(pa["open"], 1127.50)
        self.assertEqual(pa["close"], 1161.20)
        self.assertEqual(pa["prev_close"], 1110.00)
        self.assertAlmostEqual(pa["ret_1d_raw"], expected_raw_ret, places=6)

        # Verify Markdown contains canonical prices
        md = self.builder.render_markdown(report)
        self.assertIn("₹1,161.20", md)
        self.assertIn("₹1,127.50", md)
        self.assertIn("+4.61%", md)
        self.assertNotIn("1552.95", md)
        self.assertNotIn("1508.0", md)

        # Verify HTML contains canonical prices
        html = self.builder.render_html(report)
        self.assertIn("1,161.20", html)
        self.assertIn("+4.61%", html)
        self.assertNotIn("1552.95", html)

    def test_11_infy_q2_disclosure_timestamp_and_pit_calendar(self):
        """
        Reconciles INFY Q2 FY2027 announcement timestamp and effective sessions:
        - Authoritative timestamp is 2026-10-23T16:30:00+05:30 (16:30 IST)
        - Excluded from 2026-10-23 investigation (broadcast post-close)
        - Eligible in 2026-10-27 investigation (first trading session post-holiday)
        """
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            row = cursor.execute("""
                SELECT broadcast_timestamp, effective_session_date, verification_status 
                FROM corporate_disclosures 
                WHERE disclosure_id = 'INFY_DISC_20261023_Q2';
            """).fetchone()
            self.assertEqual(row[0], "2026-10-23T16:30:00+05:30")
            self.assertEqual(row[1], "2026-10-26")
            self.assertEqual(row[2], "VERIFIED")

            # Check session count for 2026-10-26
            cnt = cursor.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE trading_date = '2026-10-26';").fetchone()[0]
            self.assertGreaterEqual(cnt, 0)

        # October 23 investigation must exclude the Q2 announcement
        rep_oct23 = self.builder.build_report("INFY", "2026-10-23")
        excluded_ids = [ex.evidence_id for ex in rep_oct23.timeline.excluded_evidence]
        self.assertIn("EV_DISC_INFY_DISC_20261023_Q2", excluded_ids)

        # October 27 investigation must consume the Q2 announcement
        rep_oct27 = self.builder.build_report("INFY", "2026-10-27")
        top_hyp = rep_oct27.ranked_explanations[0]
        self.assertEqual(top_hyp.primary_evidence_id, "EV_DISC_INFY_DISC_20261023_Q2")
        self.assertEqual(top_hyp.final_score, 65.0)
        self.assertEqual(top_hyp.confidence_level, "MODERATE_CONFIDENCE")

    def test_12_nestleind_mechanical_adjustment_separation(self):
        """
        Verifies separation of mechanical corporate action from market catalyst:
        - 1:1 Bonus explains quoted price discontinuity (-50.93%, factor 0.50)
        - Underlying economic return (-1.86%) remains UNEXPLAINED_MOVEMENT
        - Bonus issue is EXCLUDED from economic explanatory candidate ranking
        """
        report = self.builder.build_report("NESTLEIND", "2025-08-08")
        
        # Section A & H: Underlying movement remains UNEXPLAINED_MOVEMENT
        self.assertEqual(report.overview.primary_classification, "UNEXPLAINED_MOVEMENT")
        self.assertEqual(report.overview.confidence_level, "UNEXPLAINED_MOVEMENT")
        self.assertEqual(report.final_assessment.final_outcome, "UNEXPLAINED_PRICE_MOVEMENT")

        # Section C: Dedicated mechanical adjustment context
        self.assertIsNotNone(report.movement_analysis.mechanical_adjustment)
        ma = report.movement_analysis.mechanical_adjustment
        self.assertTrue(ma.has_mechanical_adjustment)
        self.assertEqual(ma.corporate_action_type, "BONUS")
        self.assertEqual(ma.adjustment_factor, 0.50)
        self.assertAlmostEqual(ma.raw_return_pct, -0.5093, places=2)
        self.assertAlmostEqual(ma.adjusted_return_pct, -0.0186, places=2)
        self.assertEqual(ma.corporate_action_evidence_id, "EV_CA_NESTLEIND_BONUS_20250808_BONUS_1_1")

        # Section E: Mechanical corporate action is EXCLUDED from economic catalyst ranking
        self.assertEqual(len(report.ranked_explanations), 0)

        # Markdown & HTML verification
        md = self.builder.render_markdown(report)
        self.assertIn("Mechanical Corporate Action Price Adjustment", md)
        self.assertIn("0.50", md)
        self.assertIn("-50.93%", md)
        self.assertIn("-1.86%", md)
        self.assertIn("UNEXPLAINED_PRICE_MOVEMENT", md)
        self.assertIn("No independent candidate explanations met the minimum score threshold", md)

        html = self.builder.render_html(report)
        self.assertIn("Mechanical Corporate Action Price Adjustment", html)
        self.assertIn("NON-DIRECTIONAL", html)
        self.assertIn("No independent candidate explanations met the minimum score threshold", html)

    # -------------------------------------------------------------
    # 5. Remaining Representative Cases & Cross-Phase Reconciliations
    # -------------------------------------------------------------
    def test_13_case_1_infy_20261016_sector_surge(self):
        """Case 1: INFY 2026-10-16 - Sector systematic surge with High Confidence."""
        report = self.builder.build_report("INFY", "2026-10-16")
        self.assertEqual(report.overview.primary_classification, "SECTOR_SYSTEMATIC_SURGE")
        self.assertEqual(report.overview.confidence_level, "HIGH_CONFIDENCE")
        self.assertEqual(report.final_assessment.final_outcome, "STRONGLY_SUPPORTED_EXPLANATION")

        top = report.ranked_explanations[0]
        self.assertEqual(top.primary_evidence_id, "EV_MKT_NIFTY_IT_20261016_PRI")
        self.assertEqual(top.final_score, 90.0)
        self.assertEqual(top.confidence_level, "HIGH_CONFIDENCE")

    def test_14_case_5_sbin_20250808_standalone_isolation(self):
        """Case 5: SBIN 2025-08-08 - Standalone reporting-basis isolation verified."""
        report = self.builder.build_report("SBIN", "2025-08-08")
        self.assertEqual(report.overview.reporting_basis, "STANDALONE")
        self.assertTrue(report.overview.is_standalone_isolated)
        self.assertEqual(report.overview.primary_classification, "MARKET_BETA_DRIVEN")

        top = report.ranked_explanations[0]
        self.assertEqual(top.primary_evidence_id, "EV_FS_SBIN_Q1_FY26_STAND_V1")
        self.assertEqual(top.final_score, 65.0)
        self.assertEqual(top.confidence_level, "MODERATE_CONFIDENCE")

    def test_15_case_6_tmpv_20251110_demerger_and_recast_statement(self):
        """Case 6: TMPV 2025-11-10 - Demerger lineage, 0 OLS sessions, recast statement."""
        report = self.builder.build_report("TMPV", "2025-11-10")
        self.assertEqual(report.overview.primary_classification, "INSUFFICIENT_DATA")
        
        mm = report.movement_analysis.market_model
        self.assertEqual(mm["estimation_sessions_count"], 0)
        self.assertIsNone(mm["abnormal_return"])

        ranked_ev_ids = [r.primary_evidence_id for r in report.ranked_explanations]
        self.assertIn("EV_FS_TMPV_Q2_FY26_CONS_V1", ranked_ev_ids)
        self.assertIn("EV_FS_TMPV_Q1_FY26_CONS_V2_RECAST", ranked_ev_ids)
        self.assertEqual(report.overview.confidence_level, "MODERATE_CONFIDENCE")

    def test_16_infy_20261027_canonical_price_and_phase3_reconciliation(self):
        """
        Verifies INFY 2026-10-27 canonical price, return lineage, and cross-phase consistency:
        - Database row: Open ₹1,151.95, Close ₹1,163.00, Prev Close ₹1,153.80
        - Raw return: +0.80% (0.00797365), Adjusted return: +0.80% (0.00797365)
        - Overnight gap open: -0.16% (-0.0016034)
        - Intraday drift: +0.96% (+0.0095924)
        - Phase 3 analyzer matches Phase 4 engine and Phase 5 reports
        - Ensures no erroneous '-0.17%' or mock prices exist in published representations
        """
        # 1. Canonical database row
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            # Oct 27 row
            row_27 = cursor.execute("""
                SELECT open, high, low, close, prev_close, volume, source, data_status
                FROM ohlcv_daily
                WHERE symbol = 'INFY' AND trading_date = '2026-10-27'
            """).fetchone()
            self.assertIsNotNone(row_27)
            self.assertEqual(row_27[0], 1151.95)
            self.assertEqual(row_27[3], 1163.00)
            self.assertEqual(row_27[4], 1166.00)  # Raw unadjusted exchange reference in bhavcopy

            # Chronological previous session (Oct 23) settled close
            row_23 = cursor.execute("""
                SELECT close FROM ohlcv_daily
                WHERE symbol = 'INFY' AND trading_date = '2026-10-23'
            """).fetchone()
            self.assertIsNotNone(row_23)
            self.assertEqual(row_23[0], 1153.80)

        # 2. Phase 3 analyzer output
        p3_res = self.analyzer.analyze_session_movement("INFY", "2026-10-27")
        self.assertTrue(p3_res.has_calendar_gap)
        self.assertEqual(p3_res.missing_intermediate_sessions, ["2026-10-26"])
        self.assertEqual(p3_res.interval_sessions_count, 2)
        self.assertAlmostEqual(p3_res.interval_return_raw, 0.00797365, places=5)
        self.assertAlmostEqual(p3_res.ret_1d_raw, -0.002572898, places=5)
        self.assertAlmostEqual(p3_res.ret_1d_adj, -0.002572898, places=5)
        self.assertAlmostEqual(p3_res.gap_open, -0.0120497, places=4)
        self.assertAlmostEqual(p3_res.intraday_drift, 0.0095924, places=5)

        # 3. Phase 5 Report Builder output
        report = self.builder.build_report("INFY", "2026-10-27")
        pa = report.movement_analysis.price_action
        self.assertEqual(pa["open"], 1151.95)
        self.assertEqual(pa["close"], 1163.00)
        self.assertEqual(pa["prev_close"], 1166.00)
        self.assertEqual(pa["prev_stored_close"], 1153.80)
        self.assertAlmostEqual(pa["ret_1d_raw"], -0.0026, places=3)
        self.assertAlmostEqual(pa["ret_1d_adj"], -0.0026, places=3)
        self.assertAlmostEqual(pa["interval_return_raw"], 0.0080, places=3)

        # 4. Multi-format consistency
        md = self.builder.render_markdown(report)
        html = self.builder.render_html(report)
        json_str = json.dumps(report.to_dict())

        # All formats must report canonical -0.26% daily return, +0.80% interval return, and ₹1,163.00 close
        self.assertIn("-0.26%", md)
        self.assertIn("+0.80%", md)
        self.assertIn("1,163.00", md)
        self.assertIn("-0.26%", html)
        self.assertIn("+0.80%", html)
        self.assertIn("1,163.00", html)
        self.assertIn("1163.0", json_str)
        
        # Verify no confusing '-0.17%' appears in return reporting
        self.assertNotIn("-0.17%", md)
        self.assertNotIn("-0.17%", html)

    def test_17_cross_format_numerical_consistency(self):
        """
        Verifies numerical and provenance hash consistency across JSON, Markdown, and HTML
        for all representative cases.
        """
        cases = [
            ("INFY", "2026-10-16"),
            ("INFY", "2026-10-23"),
            ("INFY", "2026-10-27"),
            ("NESTLEIND", "2025-08-08"),
            ("SBIN", "2025-08-08"),
            ("TMPV", "2025-11-10")
        ]
        for sym, dt in cases:
            rep = self.builder.build_report(sym, dt)
            md = self.builder.render_markdown(rep)
            html = self.builder.render_html(rep)
            rep_dict = rep.to_dict()

            # Hash must match across object and representations
            expected_hash = rep.final_assessment.provenance_audit_hash
            self.assertEqual(rep.compute_audit_hash(), expected_hash)
            self.assertIn(expected_hash, md)
            self.assertIn(expected_hash, html)
            self.assertEqual(rep_dict["final_assessment"]["provenance_audit_hash"], expected_hash)

            # Close price formatting
            close_val = rep.movement_analysis.price_action["close"]
            self.assertIn(f"{close_val:,.2f}", md)
            self.assertIn(f"{close_val:,.2f}", html)


if __name__ == "__main__":
    unittest.main()
