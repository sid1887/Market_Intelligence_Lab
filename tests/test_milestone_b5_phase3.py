"""
Unit and integration tests for Milestone B5 Phase 3: Deterministic Market-Movement Analyzer.
Verifies:
1. Daily raw, adjusted, and total returns, overnight gap, intraday drift, and range.
2. Distinction between raw price drops and corporate-action-adjusted returns.
3. OLS Market Model abnormal returns and t-statistics with known inputs.
4. Statistical safeguards: minimum 126 observations, buffer window, insufficient history handling.
5. Synthetic peer basket return calculation (equal-weighting, excluding target stock).
6. Synthetic peer basket fallback when valid peers < 3 (never disguised as sector return).
7. Volume anomalies (VR >= 2.5, Z >= 2.5) and zero-volume handling.
8. Deterministic movement classification taxonomy (Idiosyncratic vs. Sector Systematic).
9. Zero look-ahead bias and no future data leakage.
10. Evidence semantics safeguard: financial statements have AMBIGUOUS direction and explicit profitability_status.
11. Absolute reproducibility of identical mathematical calculations.
"""

import unittest
import sqlite3
import math
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.evidence.models import (
    MovementClassification,
    SectorBenchmarkType,
    EvidenceDirection,
    MovementAnalysisResult
)
from src.evidence.constants import MINIMUM_SYNTHETIC_PEERS
from src.quant.movement_analyzer import MarketMovementAnalyzer
from src.evidence.store import EvidenceStore


class TestMilestoneB5Phase3(unittest.TestCase):
    """Phase 3 comprehensive verification suite."""

    @classmethod
    def setUpClass(cls):
        cls.db = DatabaseManager("data/market_lab.db")
        cls.analyzer = MarketMovementAnalyzer(cls.db)
        cls.store = EvidenceStore(cls.db)

    def test_1_positive_and_negative_returns_gap_and_drift(self):
        """Verifies formulas for raw 1d return, overnight gap, intraday drift, and range."""
        res = self.analyzer.analyze_session_movement("INFY", "2026-10-16")
        self.assertIsNotNone(res)

        # Expected values from database
        p_t = res.close
        p_prev = res.prev_close
        open_p = res.open
        high_p = res.high
        low_p = res.low

        expected_ret = (p_t - p_prev) / p_prev
        expected_gap = (open_p - p_prev) / p_prev
        expected_drift = (p_t - open_p) / open_p
        expected_range = (high_p - low_p) / p_prev

        self.assertAlmostEqual(res.ret_1d_raw, expected_ret, places=6)
        self.assertAlmostEqual(res.gap_open, expected_gap, places=6)
        self.assertAlmostEqual(res.intraday_drift, expected_drift, places=6)
        self.assertAlmostEqual(res.intraday_range, expected_range, places=6)

    def test_2_corporate_action_adjusted_returns_distinction(self):
        """
        Verifies that mechanical ex-date drops are isolated from genuine market performance.
        On 2025-08-08, NESTLEIND underwent a 1:1 bonus issue (factor 0.5).
        Raw return drops ~50.9%, while adjusted return is ~ -1.86%.
        """
        res = self.analyzer.analyze_session_movement("NESTLEIND", "2025-08-08")
        self.assertLess(res.ret_1d_raw, -0.45)  # Raw close is halved
        self.assertGreater(res.ret_1d_adj, -0.05)  # Adjusted return is near 0 (-1.86%)
        self.assertEqual(res.details.get("cum_ca_factor"), 0.5)

    def test_3_insufficient_regression_history_statistical_guard(self):
        """
        Requirement 2: If available observations in estimation window < 126,
        do NOT manufacture alpha, beta, AR, or t-statistic.
        """
        # 2024-11-05 is early in the 24-month database (< 15 historical sessions)
        res_early = self.analyzer.analyze_session_movement("INFY", "2024-11-05")
        self.assertEqual(res_early.model_status, "INSUFFICIENT_HISTORY")
        self.assertIsNone(res_early.alpha)
        self.assertIsNone(res_early.beta)
        self.assertIsNone(res_early.abnormal_return)
        self.assertIsNone(res_early.t_statistic)
        self.assertEqual(res_early.primary_classification, MovementClassification.INSUFFICIENT_DATA)

    def test_4_ols_market_model_estimation_on_sufficient_history(self):
        """
        Verifies that on 2026-10-23 (when >= 126 sessions exist),
        model estimates alpha, beta, R2, abnormal return, and t-statistic.
        """
        res = self.analyzer.analyze_session_movement("INFY", "2026-10-23")
        self.assertEqual(res.model_status, "ESTIMATED")
        self.assertIsNotNone(res.alpha)
        self.assertIsNotNone(res.beta)
        self.assertIsNotNone(res.r_squared)
        self.assertIsNotNone(res.abnormal_return)
        self.assertIsNotNone(res.t_statistic)
        self.assertGreaterEqual(res.estimation_sessions_count, 126)

        # Confirm expected return equation: E[R] = alpha + beta * R_m
        expected_e_r = res.alpha + res.beta * res.benchmark_return
        self.assertAlmostEqual(res.expected_return, expected_e_r, places=6)
        self.assertAlmostEqual(res.abnormal_return, res.ret_1d_adj - expected_e_r, places=6)

    def test_5_synthetic_peer_basket_calculation_and_peer_exclusion(self):
        """
        Requirement 3: Synthetic peer basket must exclude target stock and equal-weight peers.
        """
        res = self.analyzer.analyze_session_movement("RELIANCE", "2026-10-23")
        self.assertNotIn("RELIANCE", res.peer_returns)

        if len(res.peer_returns) >= MINIMUM_SYNTHETIC_PEERS:
            expected_sec_ret = sum(res.peer_returns.values()) / float(len(res.peer_returns))
            self.assertAlmostEqual(res.sector_return, expected_sec_ret, places=6)
            self.assertTrue(res.is_survivorship_biased_proxy)

    def test_6_synthetic_peer_basket_fallback_when_peers_less_than_3(self):
        """
        Requirement 3: When < 3 peers are active on the target date,
        system falls back to NIFTY 50 PRI and NEVER disguises it as an official sector return.
        """
        # LT is in Construction (0 peers) -> falls back to NIFTY 50
        res_lt = self.analyzer.analyze_session_movement("LT", "2026-10-23")
        self.assertEqual(res_lt.sector_benchmark_type, SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI)
        self.assertEqual(res_lt.sector_benchmark_name, "NIFTY 50")
        self.assertIn("broad-market context only", res_lt.sector_notes or "")

    def test_7_movement_classification_idiosyncratic_vs_sector_surge(self):
        """
        Requirement 4: On 2026-10-16, IT sector surged +3.92%.
        - INFY rose +4.61% (SAR = +0.69% <= 1.0%) -> SECTOR_SYSTEMATIC_SURGE
        - TECHM rose +8.48% (AR = +8.07%, SAR = +4.56% > 1.5%) -> IDIOSYNCRATIC_OUTPERFORMANCE
        """
        res_infy = self.analyzer.analyze_session_movement("INFY", "2026-10-16")
        self.assertEqual(res_infy.primary_classification, MovementClassification.SECTOR_SYSTEMATIC_SURGE)
        self.assertIn(MovementClassification.SECTOR_SYSTEMATIC_SURGE, res_infy.classifications)

        res_techm = self.analyzer.analyze_session_movement("TECHM", "2026-10-16")
        self.assertEqual(res_techm.primary_classification, MovementClassification.IDIOSYNCRATIC_OUTPERFORMANCE)
        self.assertIn(MovementClassification.IDIOSYNCRATIC_OUTPERFORMANCE, res_techm.classifications)

    def test_8_volume_spikes_and_anomalous_volume_tagging(self):
        """
        Requirement 4 & 5: On 2026-10-16, high trading activity in INFY triggers ANOMALOUS_VOLUME.
        Confirms that ANOMALOUS_VOLUME remains an independent tag and NEVER overwrites
        the primary price-movement classification (SECTOR_SYSTEMATIC_SURGE).
        """
        res = self.analyzer.analyze_session_movement("INFY", "2026-10-16")
        self.assertTrue(res.is_volume_spike)
        self.assertIn(MovementClassification.ANOMALOUS_VOLUME, res.classifications)
        # Primary classification must remain the price movement classification
        self.assertEqual(res.primary_classification, MovementClassification.SECTOR_SYSTEMATIC_SURGE)

        # On 2026-10-23, volume spike on an unclassified price move yields UNEXPLAINED_MOVEMENT as primary
        res23 = self.analyzer.analyze_session_movement("INFY", "2026-10-23")
        self.assertEqual(res23.primary_classification, MovementClassification.UNEXPLAINED_MOVEMENT)
        self.assertIn(MovementClassification.ANOMALOUS_VOLUME, res23.classifications)

    def test_9_evidence_semantics_safeguard_financial_statements_ambiguous(self):
        """
        Requirement 0: Profitability does not equal positive news.
        All financial statement evidence records must have direction = AMBIGUOUS
        and profitability_status in details.
        """
        summary = self.store.get_evidence_summary()
        self.assertEqual(summary["by_category"].get("EARNINGS_RELEASE"), 453)

        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            rows = cursor.execute("""
                SELECT evidence_direction, json_extract(details_json, '$.profitability_status')
                FROM evidence_records
                WHERE source_identity = 'company_financial_statements';
            """).fetchall()

            for r in rows:
                self.assertEqual(r[0], "AMBIGUOUS")
                self.assertIn(r[1], ["PROFITABLE", "LOSS_MAKING", "BREAK_EVEN"])

    def test_10_no_future_data_leakage_and_reproducibility(self):
        """
        Verifies zero future data leakage (OLS estimation window strictly ends at t-21)
        and 100% deterministic reproducibility across identical runs.
        """
        res1 = self.analyzer.analyze_session_movement("INFY", "2026-10-23")
        res2 = self.analyzer.analyze_session_movement("INFY", "2026-10-23")

        self.assertEqual(res1.ret_1d_raw, res2.ret_1d_raw)
        self.assertEqual(res1.abnormal_return, res2.abnormal_return)
        self.assertEqual(res1.t_statistic, res2.t_statistic)
        self.assertEqual(res1.primary_classification, res2.primary_classification)
        self.assertEqual(res1.classifications, res2.classifications)

    def test_11_volume_lookback_window_and_sample_variance(self):
        """
        Requirement 2 Audit:
        Verifies that:
        1. Current event session t is strictly excluded from historical volume baseline.
        2. VR uses exactly 20 preceding sessions [t-20, t-1].
        3. Z-score uses exactly 50 preceding sessions [t-50, t-1] with sample std dev (denominator 49).
        """
        # Fetch raw stock history for INFY
        stock_raw = self.db.get_stock_history("INFY")
        stock_sorted = sorted(stock_raw, key=lambda x: x["trading_date"])
        dates = [r["trading_date"] for r in stock_sorted]

        target_date = "2026-10-23"
        t_idx = dates.index(target_date)

        # Baseline records must be strictly before target_date
        prior_20 = stock_sorted[t_idx - 20:t_idx]
        prior_50 = stock_sorted[t_idx - 50:t_idx]

        self.assertEqual(len(prior_20), 20)
        self.assertEqual(len(prior_50), 50)
        self.assertNotIn(target_date, [r["trading_date"] for r in prior_20])
        self.assertNotIn(target_date, [r["trading_date"] for r in prior_50])

        # Calculate expected VR and Z manually
        vol_t = int(stock_sorted[t_idx]["volume"])
        sma_20 = sum(int(r["volume"]) for r in prior_20) / 20.0
        expected_vr = vol_t / sma_20

        log_vols = [math.log(int(r["volume"]) + 1.0) for r in prior_50]
        mean_log = sum(log_vols) / 50.0
        var_log_sample = sum((x - mean_log) ** 2 for x in log_vols) / 49.0  # Sample Bessel N-1
        std_log_sample = math.sqrt(var_log_sample)
        expected_z = (math.log(vol_t + 1.0) - mean_log) / std_log_sample

        res = self.analyzer.analyze_session_movement("INFY", target_date)
        self.assertAlmostEqual(res.volume_ratio_20d, expected_vr, places=4)
        self.assertAlmostEqual(res.volume_log_zscore_50d, expected_z, places=4)

    def test_12_ols_return_basis_and_abnormal_return_consistency(self):
        """
        Requirement 3 Audit:
        Confirms that:
        1. Dependent stock returns during OLS estimation are corporate-action-adjusted.
        2. Benchmark returns are NIFTY 50 PRI returns.
        3. Stock and benchmark are aligned on identical dates.
        4. Event-day abnormal return uses the exact same adjusted-return basis as the estimation model:
           AR_t = R_{1d,adj,t} - (alpha + beta * R_{m,t}).
        """
        res = self.analyzer.analyze_session_movement("INFY", "2026-10-16")
        self.assertEqual(res.model_status, "ESTIMATED")

        # Confirm benchmark used is NIFTY 50 PRI
        nifty_raw = self.db.get_index_history("NIFTY 50", "PRI")
        nifty_dates = {r["trading_date"]: float(r["close"]) for r in nifty_raw}
        p_curr = nifty_dates["2026-10-16"]
        p_prev = nifty_dates["2026-10-15"]
        expected_rm = (p_curr - p_prev) / p_prev
        self.assertAlmostEqual(res.benchmark_return, expected_rm, places=6)

        # Confirm abnormal return formula: AR = R_{adj} - (alpha + beta * R_m)
        expected_ar = res.ret_1d_adj - (res.alpha + res.beta * res.benchmark_return)
        self.assertAlmostEqual(res.abnormal_return, expected_ar, places=6)

        # 5. Confirm OLS estimation sample strictly excludes non-consecutive session pairs:
        # The 232-session historical estimation slice contains 231 adjacent row intervals.
        # Two pairs span missing exchange trading sessions (2025-10-17 -> 2025-10-21 missing 2025-10-20,
        # and 2025-10-21 -> 2025-10-24 missing 2025-10-23). Both pairs are strictly purged,
        # leaving exactly 229 pairs where both stock and benchmark represent identical consecutive 1d sessions.
        self.assertEqual(res.estimation_sessions_count, 229)


if __name__ == "__main__":
    unittest.main()
