"""
Unit and end-to-end system verification tests for Milestone B5 Phase 6:
Comparative Evaluation, System Verification & Milestone Closeout.
"""

import unittest
import os
import json
import hashlib
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
from src.evidence.store import EvidenceStore
from src.quant.movement_analyzer import MarketMovementAnalyzer
from src.attribution.engine import EvidenceRankingEngine
from src.reporting.investigation_builder import InvestigationReportBuilder
from src.reporting.investigation_schema import StructuredInvestigationReport


class TestMilestoneB5Phase6SystemVerification(unittest.TestCase):
    """
    Comprehensive Phase 6 verification suite evaluating end-to-end pipeline consistency,
    reproducibility, numerical integrity, and governance compliance across all milestones (B3-B5).
    """

    @classmethod
    def setUpClass(cls):
        cls.db_path = "data/market_lab.db"
        cls.db = DatabaseManager(cls.db_path)
        cls.evidence_store = EvidenceStore(cls.db)
        cls.analyzer = MarketMovementAnalyzer(cls.db)
        cls.engine = EvidenceRankingEngine(cls.db, cls.evidence_store, cls.analyzer)
        cls.builder = InvestigationReportBuilder(cls.db, cls.engine)

        cls.cases = [
            ("INFY", "2026-10-16"),
            ("INFY", "2026-10-23"),
            ("INFY", "2026-10-27"),
            ("NESTLEIND", "2025-08-08"),
            ("SBIN", "2025-08-08"),
            ("TMPV", "2025-11-10")
        ]

    # -------------------------------------------------------------
    # 1. Database Integrity & Baseline Inventory
    # -------------------------------------------------------------
    def test_01_database_integrity_and_foreign_keys(self):
        """Verifies zero SQLite corruption and zero foreign key violations."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            integrity = cursor.execute("PRAGMA integrity_check;").fetchall()
            self.assertEqual([r[0] for r in integrity], ["ok"])

            fk_violations = cursor.execute("PRAGMA foreign_key_check;").fetchall()
            self.assertEqual(len(fk_violations), 0)

    def test_02_database_inventory_and_milestone_coverage(self):
        """Verifies row counts across foundational tables matches frozen benchmark."""
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            
            # Securities Master: 50 active + 8 benchmark/indices = 58
            sec_count = cursor.execute("SELECT count(*) FROM securities_master;").fetchone()[0]
            self.assertGreaterEqual(sec_count, 50)

            # Daily OHLCV: at least 25,106 rows (25,106 frozen Nifty baseline, plus expanded universe)
            ohlcv_count = cursor.execute("SELECT count(*) FROM ohlcv_daily;").fetchone()[0]
            self.assertGreaterEqual(ohlcv_count, 25106)
            nifty_ohlcv = cursor.execute("SELECT count(*) FROM ohlcv_daily WHERE symbol IN (SELECT symbol FROM securities_master WHERE is_active = 1);").fetchone()[0]
            self.assertGreaterEqual(nifty_ohlcv, 25106)

            # Index Daily: 8,964 rows
            idx_count = cursor.execute("SELECT count(*) FROM index_daily;").fetchone()[0]
            self.assertEqual(idx_count, 8964)

            # Corporate Actions: at least 169 rows (169 frozen B5 baseline, 911 post-B3.2 universe)
            ca_count = cursor.execute("SELECT count(*) FROM corporate_actions;").fetchone()[0]
            self.assertGreaterEqual(ca_count, 169)

            # Corporate Disclosures: at least 3 rows (3 frozen B5 baseline, 95k+ post-B3.2 universe)
            disc_count = cursor.execute("SELECT count(*) FROM corporate_disclosures;").fetchone()[0]
            self.assertGreaterEqual(disc_count, 3)

            # Financial Statements: 453 verified statements
            fs_count = cursor.execute("SELECT count(*) FROM company_financial_statements;").fetchone()[0]
            self.assertEqual(fs_count, 453)

            # Evidence Store: exactly 1,418 ingested evidence records
            ev_count = cursor.execute("SELECT count(*) FROM evidence_records;").fetchone()[0]
            self.assertEqual(ev_count, 1418)

    # -------------------------------------------------------------
    # 2. End-to-End Pipeline Contract & Provenance Preservation
    # -------------------------------------------------------------
    def test_03_end_to_end_pipeline_contract(self):
        """
        Verifies contract flow:
        DB -> MarketMovementAnalyzer -> EvidenceRankingEngine -> InvestigationReportBuilder
        Ensures downstream report consumes upstream outputs without mutation.
        """
        symbol = "INFY"
        date = "2026-10-16"

        # Step 1: Upstream analyzer
        mv = self.analyzer.analyze_session_movement(symbol, date)
        self.assertEqual(mv.symbol, symbol)
        self.assertEqual(mv.trading_date, date)
        self.assertAlmostEqual(mv.ret_1d_raw, 0.046126, places=4)
        self.assertAlmostEqual(mv.ret_1d_adj, 0.046126, places=4)

        # Step 2: Attribution engine
        exp = self.engine.explain_movement(symbol, date, persist_to_db=False)
        self.assertEqual(exp.movement_result.ret_1d_raw, mv.ret_1d_raw)
        self.assertEqual(exp.movement_result.ret_1d_adj, mv.ret_1d_adj)
        self.assertEqual(exp.primary_hypothesis.evidence_strength_score, 90.0)

        # Step 3: Report builder
        rep = self.builder.build_report(symbol, date)
        self.assertEqual(rep.movement_analysis.price_action["ret_1d_raw"], mv.ret_1d_raw)
        self.assertEqual(rep.movement_analysis.price_action["ret_1d_adj"], mv.ret_1d_adj)
        self.assertEqual(rep.ranked_explanations[0].final_score, 90.0)
        self.assertEqual(rep.overview.confidence_level, "HIGH_CONFIDENCE")
        self.assertEqual(rep.final_assessment.final_outcome, "STRONGLY_SUPPORTED_EXPLANATION")

    def test_04_repeat_build_determinism_and_hash_identity(self):
        """Verifies that repeat builds produce byte-for-byte identical SHA-256 hashes."""
        for sym, dt in self.cases:
            rep1 = self.builder.build_report(sym, dt)
            hash1 = rep1.final_assessment.provenance_audit_hash

            rep2 = self.builder.build_report(sym, dt)
            hash2 = rep2.final_assessment.provenance_audit_hash

            self.assertEqual(hash1, hash2, f"Hash mismatch on repeat build for {sym} {dt}")
            self.assertEqual(len(hash1), 64)

    def test_05_provenance_hash_sensitivity(self):
        """Verifies that altering core analytical fields alters the cryptographic hash."""
        rep = self.builder.build_report("INFY", "2026-10-16")
        original_hash = rep.compute_audit_hash()

        # Modify close price in price action
        rep.movement_analysis.price_action["close"] = 1200.0
        hash_price_changed = rep.compute_audit_hash()
        self.assertNotEqual(original_hash, hash_price_changed)

        # Restore price, modify score of top explanation
        rep.movement_analysis.price_action["close"] = 1161.20
        rep.ranked_explanations[0].final_score = 85.0
        hash_score_changed = rep.compute_audit_hash()
        self.assertNotEqual(original_hash, hash_score_changed)

    # -------------------------------------------------------------
    # 3. Cross-Case Numerical & Semantic Consistency
    # -------------------------------------------------------------
    def test_06_case_1_infy_20261016_sector_surge(self):
        """Case 1: INFY 2026-10-16 - Sector Systematic Surge (+4.61%, Score 90.0)."""
        rep = self.builder.build_report("INFY", "2026-10-16")
        pa = rep.movement_analysis.price_action
        self.assertEqual(pa["open"], 1127.50)
        self.assertEqual(pa["close"], 1161.20)
        self.assertEqual(pa["prev_close"], 1110.00)
        self.assertAlmostEqual(pa["ret_1d_raw"], 0.046126, places=4)
        self.assertAlmostEqual(pa["ret_1d_adj"], 0.046126, places=4)

        self.assertEqual(rep.overview.primary_classification, "SECTOR_SYSTEMATIC_SURGE")
        self.assertEqual(rep.overview.confidence_level, "HIGH_CONFIDENCE")
        self.assertEqual(rep.final_assessment.final_outcome, "STRONGLY_SUPPORTED_EXPLANATION")

        top = rep.ranked_explanations[0]
        self.assertEqual(top.primary_evidence_id, "EV_MKT_NIFTY_IT_20261016_PRI")
        self.assertEqual(top.final_score, 90.0)

    def test_07_case_2_infy_20261023_anomalous_volume_activity_separation(self):
        """Case 2: INFY 2026-10-23 - Volume activity separated from causal explanation."""
        rep = self.builder.build_report("INFY", "2026-10-23")
        self.assertEqual(rep.overview.primary_classification, "UNEXPLAINED_MOVEMENT")
        self.assertEqual(rep.overview.confidence_level, "UNEXPLAINED_MOVEMENT")
        self.assertEqual(rep.final_assessment.final_outcome, "UNEXPLAINED_PRICE_MOVEMENT")

        # Volume activity observation is tagged as ACTIVITY_OBSERVATION, capped at 49.9
        top = rep.ranked_explanations[0]
        self.assertEqual(top.primary_evidence_id, "EV_VOL_INFY_20261023")
        self.assertEqual(top.catalyst_type, "ACTIVITY_OBSERVATION")
        self.assertEqual(top.final_score, 49.9)
        self.assertEqual(top.confidence_level, "LOW_CONFIDENCE")

        # PIT post-market announcement must be excluded
        excluded_ids = [ex.evidence_id for ex in rep.timeline.excluded_evidence]
        self.assertIn("EV_DISC_INFY_DISC_20261023_Q2", excluded_ids)

    def test_08_case_3_infy_20261027_q2_disclosure_unknown_consensus(self):
        """Case 3: INFY 2026-10-27 - Canonical price, -0.26% 1d return, +0.80% interval return, 65.0 score."""
        rep = self.builder.build_report("INFY", "2026-10-27")
        pa = rep.movement_analysis.price_action
        self.assertEqual(pa["open"], 1151.95)
        self.assertEqual(pa["close"], 1163.00)
        self.assertEqual(pa["prev_close"], 1166.00)
        self.assertEqual(pa["prev_stored_close"], 1153.80)
        self.assertTrue(pa["has_calendar_gap"])
        self.assertEqual(pa["missing_intermediate_sessions"], ["2026-10-26"])
        self.assertEqual(pa["interval_sessions_count"], 2)
        self.assertAlmostEqual(pa["interval_return_raw"], 0.00797365, places=4)
        self.assertAlmostEqual(pa["ret_1d_raw"], -0.002572898, places=4)
        self.assertAlmostEqual(pa["ret_1d_adj"], -0.002572898, places=4)
        self.assertAlmostEqual(pa["gap_open"], -0.0120497, places=4)
        self.assertAlmostEqual(pa["intraday_drift"], 0.0095924, places=4)

        # Benchmark return None and AR None
        self.assertIsNone(rep.movement_analysis.benchmark_comparison["benchmark_return"])
        self.assertIsNone(rep.movement_analysis.market_model["abnormal_return"])

        # MODERATE_CONFIDENCE (65.0): Tier 1 (60) + 1-day lag from Oct 26 (5)
        self.assertEqual(rep.overview.confidence_level, "MODERATE_CONFIDENCE")
        self.assertEqual(rep.final_assessment.final_outcome, "MODERATELY_SUPPORTED_EXPLANATION")
        top = rep.ranked_explanations[0]
        self.assertEqual(top.primary_evidence_id, "EV_DISC_INFY_DISC_20261023_Q2")
        self.assertEqual(top.final_score, 65.0)

    def test_09_case_4_nestleind_20250808_mechanical_bonus_isolation(self):
        """Case 4: NESTLEIND 2025-08-08 - Bonus excluded from economic catalyst ranking."""
        rep = self.builder.build_report("NESTLEIND", "2025-08-08")
        
        # Mechanical context preserved under movement_analysis
        self.assertIsNotNone(rep.movement_analysis.mechanical_adjustment)
        ma = rep.movement_analysis.mechanical_adjustment
        self.assertTrue(ma.has_mechanical_adjustment)
        self.assertEqual(ma.corporate_action_type, "BONUS")
        self.assertEqual(ma.adjustment_factor, 0.50)
        self.assertAlmostEqual(ma.raw_return_pct, -0.509308, places=4)
        self.assertAlmostEqual(ma.adjusted_return_pct, -0.018616, places=4)

        # Bonus corporate action is EXCLUDED from economic explanatory hypotheses
        self.assertEqual(len(rep.ranked_explanations), 0)
        self.assertEqual(rep.overview.confidence_level, "UNEXPLAINED_MOVEMENT")
        self.assertEqual(rep.final_assessment.final_outcome, "UNEXPLAINED_PRICE_MOVEMENT")

    def test_10_case_5_sbin_20250808_standalone_isolation(self):
        """Case 5: SBIN 2025-08-08 - Standalone reporting basis isolated from consolidated peers."""
        rep = self.builder.build_report("SBIN", "2025-08-08")
        self.assertEqual(rep.overview.reporting_basis, "STANDALONE")
        self.assertTrue(rep.overview.is_standalone_isolated)
        self.assertEqual(rep.overview.primary_classification, "MARKET_BETA_DRIVEN")

        top = rep.ranked_explanations[0]
        self.assertEqual(top.primary_evidence_id, "EV_FS_SBIN_Q1_FY26_STAND_V1")
        self.assertEqual(top.final_score, 65.0)
        self.assertEqual(top.confidence_level, "MODERATE_CONFIDENCE")

    def test_11_case_6_tmpv_20251110_demerger_lineage_and_recast_handling(self):
        """Case 6: TMPV 2025-11-10 - Demerger 0-session OLS and recast statement ranking."""
        rep = self.builder.build_report("TMPV", "2025-11-10")
        self.assertEqual(rep.overview.primary_classification, "INSUFFICIENT_DATA")

        # Market model gracefully reflects 0 sessions
        mm = rep.movement_analysis.market_model
        self.assertEqual(mm["estimation_sessions_count"], 0)
        self.assertIsNone(mm["abnormal_return"])

        # Both Q2 and Q1 recast statements present
        ev_ids = [r.primary_evidence_id for r in rep.ranked_explanations]
        self.assertIn("EV_FS_TMPV_Q2_FY26_CONS_V1", ev_ids)
        self.assertIn("EV_FS_TMPV_Q1_FY26_CONS_V2_RECAST", ev_ids)

    # -------------------------------------------------------------
    # 4. Multi-Format Presentation & Provenance Consistency
    # -------------------------------------------------------------
    def test_12_multi_format_representation_consistency(self):
        """Verifies that JSON, Markdown, and HTML report identical analytical figures."""
        for sym, dt in self.cases:
            rep = self.builder.build_report(sym, dt)
            md = self.builder.render_markdown(rep)
            html = self.builder.render_html(rep)
            json_dict = rep.to_dict()

            audit_hash = rep.final_assessment.provenance_audit_hash

            # 1. Audit hash match across representations
            self.assertIn(audit_hash, md)
            self.assertIn(audit_hash, html)
            self.assertEqual(json_dict["final_assessment"]["provenance_audit_hash"], audit_hash)

            # 2. Benchmark ID in all representations
            self.assertIn("MIL_FROZEN_BENCHMARK_2024_2026_V1", md)
            self.assertIn("MIL_FROZEN_BENCHMARK_2024_2026_V1", html)

            # 3. Close price formatted consistently
            close_str = f"{rep.movement_analysis.price_action['close']:,.2f}"
            self.assertIn(close_str, md)
            self.assertIn(close_str, html)


if __name__ == "__main__":
    unittest.main()
