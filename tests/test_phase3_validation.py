"""
tests/test_phase3_validation.py
Comprehensive test suite verifying MIL 2.0 Phase 3 deliverables:
1. Triple-Barrier Event Labeler (volatility-scaled barriers, worst-case double-breach tie-break, statutory + DP cost deductions).
2. Combinatorial Purged Cross-Validation (CPCV 6,2 -> 15 splits, 5 OOS paths, zero temporal leakage, holdout isolation).
3. Bailey & López de Prado Deflated Sharpe Ratio (excess kurtosis formula, analytical normal variance invariant, multiple-testing deflation).
4. Two-Stage Tournament Engine (deterministic baseline, meta-labeling abstention gate, SECTOR_ESTIMATE exclusion, registry persistence).
"""

import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats

from src.ml.triple_barrier import TripleBarrierLabeler, TripleBarrierEvent
from src.quant.validation import CombinatorialPurgedCV, deflated_sharpe_ratio, EULER_MASCHERONI
from src.quant.ml_trainer import TwoStageTournamentRunner, FEATURE_COLUMNS_8
from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.portfolio.fee_engine import calculate_roundtrip_friction, PROFILE_ZERO


class TestTripleBarrierLabeler(unittest.TestCase):
    """Verifies path-aware, cost-adjusted Triple-Barrier event labeling."""

    def setUp(self):
        self.labeler = TripleBarrierLabeler(
            k_upper=2.0,
            k_lower=1.5,
            horizon_sessions=20,
            reference_ticket=5000.0,
            broker_profile=PROFILE_ZERO,
            min_volatility=0.01
        )

    def test_upper_barrier_hit_with_positive_net_return(self):
        """Tests clear upper profit take barrier breach."""
        # P0 = 100.0, vol = 0.02 -> U = 100 * (1 + 2 * 0.02) = 104.0, L = 100 * (1 - 1.5 * 0.02) = 97.0
        # Candle 1: Open 100, High 102, Low 99, Close 101
        # Candle 2: Open 101, High 105, Low 100.5, Close 104.5 (High >= 104.0 breaches U)
        forward_df = pd.DataFrame([
            {"trading_date": "2026-01-02", "open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0},
            {"trading_date": "2026-01-05", "open": 101.0, "high": 105.0, "low": 100.5, "close": 104.5},
            {"trading_date": "2026-01-06", "open": 104.0, "high": 106.0, "low": 103.0, "close": 105.0},
        ])

        ev = self.labeler.compute_event_label(
            symbol="INFY",
            signal_date="2026-01-01",
            entry_price=100.0,
            volatility_20d=0.02,
            forward_ohlc_df=forward_df
        )

        self.assertIsNotNone(ev)
        self.assertEqual(ev.barrier_hit, "UPPER")
        self.assertEqual(ev.exit_date, "2026-01-05")
        self.assertEqual(ev.exit_price, 104.0)
        self.assertGreater(ev.net_return, 0.0)
        self.assertEqual(ev.label, 1)
        self.assertEqual(ev.holding_sessions, 2)

    def test_lower_barrier_hit_triggers_stop_loss(self):
        """Tests lower stop loss barrier breach."""
        # P0 = 100.0, vol = 0.02 -> U = 104.0, L = 97.0
        # Candle 1: Open 100, High 101, Low 96.5, Close 97.0 (Low <= 97.0 breaches L)
        forward_df = pd.DataFrame([
            {"trading_date": "2026-01-02", "open": 100.0, "high": 101.0, "low": 96.5, "close": 97.0},
            {"trading_date": "2026-01-05", "open": 97.0, "high": 98.0, "low": 95.0, "close": 95.5},
        ])

        ev = self.labeler.compute_event_label(
            symbol="TCS",
            signal_date="2026-01-01",
            entry_price=100.0,
            volatility_20d=0.02,
            forward_ohlc_df=forward_df
        )

        self.assertIsNotNone(ev)
        self.assertEqual(ev.barrier_hit, "LOWER")
        self.assertEqual(ev.exit_date, "2026-01-02")
        self.assertEqual(ev.exit_price, 97.0)
        self.assertLess(ev.net_return, 0.0)
        self.assertEqual(ev.label, -1)
        self.assertEqual(ev.holding_sessions, 1)

    def test_vertical_timeout_barrier(self):
        """Tests price meandering within corridor until vertical horizon expiration."""
        # P0 = 100.0, vol = 0.02 -> U = 104.0, L = 97.0
        # 5 sessions where high < 104 and low > 97
        forward_df = pd.DataFrame([
            {"trading_date": f"2026-01-{i:02d}", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.2}
            for i in range(2, 7)
        ])

        labeler_5d = TripleBarrierLabeler(
            k_upper=2.0, k_lower=1.5, horizon_sessions=5, reference_ticket=5000.0
        )

        ev = labeler_5d.compute_event_label(
            symbol="HDFCBANK",
            signal_date="2026-01-01",
            entry_price=100.0,
            volatility_20d=0.02,
            forward_ohlc_df=forward_df
        )

        self.assertIsNotNone(ev)
        self.assertEqual(ev.barrier_hit, "VERTICAL")
        self.assertEqual(ev.exit_date, "2026-01-06")
        self.assertEqual(ev.exit_price, 100.2)
        self.assertEqual(ev.holding_sessions, 5)

    def test_daily_double_breach_worst_case_tie_break(self):
        """
        Crucial Invariant: When a single daily candle breaches BOTH upper and lower barriers:
        - If Open is inside corridor: CONSERVATIVELY assume stop-loss was touched first!
        - If Open gapped above U: fill at Open.
        - If Open gapped below L: fill at Open.
        """
        # P0 = 100.0, vol = 0.02 -> U = 104.0, L = 97.0

        # Case A: Open inside corridor (100.0), High=105.0 (>= U), Low=96.0 (<= L)
        df_inside = pd.DataFrame([
            {"trading_date": "2026-01-02", "open": 100.0, "high": 105.0, "low": 96.0, "close": 104.5}
        ])
        ev_inside = self.labeler.compute_event_label(
            symbol="RELIANCE", signal_date="2026-01-01", entry_price=100.0,
            volatility_20d=0.02, forward_ohlc_df=df_inside
        )
        self.assertEqual(ev_inside.barrier_hit, "LOWER", "Worst-case tie-break must assign LOWER when open is inside corridor!")
        self.assertEqual(ev_inside.exit_price, 97.0)
        self.assertEqual(ev_inside.label, -1)

        # Case B: Gapped up at open (Open = 105.0 >= U), High=106.0, Low=96.0
        df_gap_up = pd.DataFrame([
            {"trading_date": "2026-01-02", "open": 105.0, "high": 106.0, "low": 96.0, "close": 96.5}
        ])
        ev_gap_up = self.labeler.compute_event_label(
            symbol="RELIANCE", signal_date="2026-01-01", entry_price=100.0,
            volatility_20d=0.02, forward_ohlc_df=df_gap_up
        )
        self.assertEqual(ev_gap_up.barrier_hit, "UPPER", "Gap up at open fills UPPER at open price")
        self.assertEqual(ev_gap_up.exit_price, 105.0)

        # Case C: Gapped down at open (Open = 96.0 <= L), High=105.0, Low=95.0
        df_gap_down = pd.DataFrame([
            {"trading_date": "2026-01-02", "open": 96.0, "high": 105.0, "low": 95.0, "close": 104.0}
        ])
        ev_gap_down = self.labeler.compute_event_label(
            symbol="RELIANCE", signal_date="2026-01-01", entry_price=100.0,
            volatility_20d=0.02, forward_ohlc_df=df_gap_down
        )
        self.assertEqual(ev_gap_down.barrier_hit, "LOWER", "Gap down at open fills LOWER at open price")
        self.assertEqual(ev_gap_down.exit_price, 96.0)

    def test_fee_drag_nullifies_micro_gains(self):
        """
        Verifies that when a trade has a positive gross return that fails to clear
        statutory + Angel One DP fees (₹23.60), label is strictly NOT assigned 1.
        """
        # Set tight barrier: k_upper=0.1, vol=0.01 -> U = 100 * (1 + 0.001) = 100.1 (+0.1% gross gain)
        # On a ₹5,000 reference ticket, +0.1% gross = +₹5.00 gross gain.
        # But Angel One DP charge alone is ₹23.60, plus statutory turnover taxes (~₹5.50).
        # Total friction is ~₹29.10 -> Net return is negative (~ -₹24.10 or -0.48%)!
        tight_labeler = TripleBarrierLabeler(
            k_upper=0.1, k_lower=1.5, horizon_sessions=5, reference_ticket=5000.0, min_volatility=0.01
        )
        forward_df = pd.DataFrame([
            {"trading_date": "2026-01-02", "open": 100.0, "high": 100.2, "low": 99.5, "close": 100.15}
        ])

        ev = tight_labeler.compute_event_label(
            symbol="TCS", signal_date="2026-01-01", entry_price=100.0,
            volatility_20d=0.01, forward_ohlc_df=forward_df
        )

        self.assertIsNotNone(ev)
        self.assertEqual(ev.barrier_hit, "UPPER")
        self.assertGreater(ev.gross_return, 0.0)
        self.assertLess(ev.net_return, 0.0, "Net return must be negative after DP + statutory fees")
        self.assertNotEqual(ev.label, 1, "Label must not be 1 when net return after fees is negative!")
        self.assertEqual(ev.label, 0)


class TestCombinatorialPurgedCV(unittest.TestCase):
    """Verifies CPCV combinatorial properties, purging, embargoing, and holdout splits."""

    def test_cpcv_combinatorics_and_path_reconstruction(self):
        """CPCV(N=6, k=2) must yield exactly binom(6,2)=15 combinations and 5 complete OOS paths."""
        cpcv = CombinatorialPurgedCV(n_splits=6, n_test_splits=2, horizon_days=20, embargo_days=20)
        self.assertEqual(cpcv.total_combinations, 15)
        self.assertEqual(cpcv.n_oos_paths, 5)

        # Synthetic dataset of 600 samples
        X = np.arange(600)
        splits = list(cpcv.split(X))
        self.assertEqual(len(splits), 15)

    def test_cpcv_zero_temporal_leakage_and_purging(self):
        """
        Verifies that train and test indices have ZERO intersection across all splits,
        and that samples within the purge window (horizon H) and embargo window are strictly absent from train.
        """
        horizon = 15
        embargo = 10
        cpcv = CombinatorialPurgedCV(n_splits=6, n_test_splits=2, horizon_days=horizon, embargo_days=embargo)
        n_samples = 600
        X = np.arange(n_samples)

        block_bounds = np.linspace(0, n_samples, 7, dtype=int)

        for train_idx, test_idx in cpcv.split(X):
            # Invariant 1: No overlap
            overlap = np.intersect1d(train_idx, test_idx)
            self.assertEqual(len(overlap), 0, "Train and test sets must have zero overlapping indices!")

            # Invariant 2: Purge window before test blocks
            # Find start of each continuous test block
            for b in range(6):
                b_start = block_bounds[b]
                b_end = block_bounds[b + 1]
                if b_start in test_idx:
                    # Block b is in test.
                    # Samples in [b_start - horizon, b_start) must NOT be in train
                    purge_window = np.arange(max(0, b_start - horizon), b_start)
                    purge_in_train = np.intersect1d(train_idx, purge_window)
                    self.assertEqual(
                        len(purge_in_train), 0,
                        f"Purged indices {purge_in_train} leaked into training set!"
                    )

                    # Samples in [b_end, b_end + embargo) must NOT be in train
                    embargo_window = np.arange(b_end, min(n_samples, b_end + embargo))
                    embargo_in_train = np.intersect1d(train_idx, embargo_window)
                    self.assertEqual(
                        len(embargo_in_train), 0,
                        f"Embargoed indices {embargo_in_train} leaked into training set!"
                    )

    def test_split_train_holdout_untouched_slice(self):
        """Verifies reservation of final holdout sessions without chronological distortion."""
        df = pd.DataFrame({
            "trading_date": pd.date_range("2024-01-01", periods=500, freq="B").astype(str),
            "close": np.random.randn(500)
        })

        dev_df, holdout_df = CombinatorialPurgedCV.split_train_holdout(df, holdout_sessions=252)

        self.assertEqual(len(dev_df), 500 - 252)
        self.assertEqual(len(holdout_df), 252)
        self.assertLess(dev_df["trading_date"].max(), holdout_df["trading_date"].min())


class TestDeflatedSharpeRatio(unittest.TestCase):
    """Verifies Bailey & López de Prado DSR mathematical properties and excess kurtosis formulation."""

    def test_analytical_variance_invariant_under_normality(self):
        """
        Mathematical Invariant:
        When gamma_3 = 0 and gamma_4_ex = 0 (Normal distribution):
        V[SR_hat] = (1 + 0.5 * SR_hat^2) / (T - 1)
        """
        t_samples = 252
        sr_hat = 1.80

        # Under normality (gamma_3=0, gamma_4_ex=0):
        expected_variance = (1.0 + 0.5 * (sr_hat ** 2)) / (t_samples - 1)

        result = deflated_sharpe_ratio(
            sharpe_hat=sr_hat,
            skewness=0.0,
            excess_kurtosis=0.0,
            t_samples=t_samples,
            n_trials=1,
            annualized_factor=1.0
        )

        self.assertAlmostEqual(result["variance_sr"], expected_variance, places=5)

    def test_dsr_penalizes_multiple_trials(self):
        """
        Selection Bias Invariant:
        Increasing number of trials M increases the hurdle SR* and strictly deflates DSR.
        """
        sr_hat = 1.50
        t_samples = 252
        ann_factor = 252.0

        res_1 = deflated_sharpe_ratio(
            sharpe_hat=sr_hat, skewness=0.0, excess_kurtosis=0.0,
            t_samples=t_samples, n_trials=1, annualized_factor=ann_factor
        )
        res_10 = deflated_sharpe_ratio(
            sharpe_hat=sr_hat, skewness=0.0, excess_kurtosis=0.0,
            t_samples=t_samples, n_trials=10, annualized_factor=ann_factor
        )
        res_50 = deflated_sharpe_ratio(
            sharpe_hat=sr_hat, skewness=0.0, excess_kurtosis=0.0,
            t_samples=t_samples, n_trials=50, annualized_factor=ann_factor
        )

        # Hurdle increases with M
        self.assertLess(res_1["sharpe_star"], res_10["sharpe_star"])
        self.assertLess(res_10["sharpe_star"], res_50["sharpe_star"])

        # Deflated Sharpe decreases with M
        self.assertGreater(res_1["dsr"], res_10["dsr"])
        self.assertGreater(res_10["dsr"], res_50["dsr"])

    def test_dsr_from_sample_returns(self):
        """Tests end-to-end estimation directly from a return series."""
        np.random.seed(42)
        # Generate 500 sessions with positive drift
        rets = np.random.normal(loc=0.001, scale=0.015, size=500)

        res = deflated_sharpe_ratio(returns=rets, n_trials=5, annualized_factor=252.0)
        self.assertIn("dsr", res)
        self.assertIn("estimated_sharpe", res)
        self.assertGreater(res["dsr"], 0.0)
        self.assertLessEqual(res["dsr"], 1.0)


class TestTwoStageTournamentRunner(unittest.TestCase):
    """Verifies Phase 3 Tournament Runner, Data Integrity, Abstention Gating, and Registry Logging."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_tournament.db"
        self.db = DatabaseManager(db_path=self.db_path)
        with self.db.get_connection() as conn:
            run_all_migrations(conn)

        self.summary_json = Path(self.temp_dir.name) / "tournament_summary.json"
        self.runner = TwoStageTournamentRunner(
            db=self.db,
            horizon_days=10,
            n_splits=6,
            n_test_splits=2,
            min_meta_prob=0.55,
            reference_ticket=5000.0,
            holdout_sessions=50,
            summary_path=str(self.summary_json)
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_sector_estimate_and_synthetic_rows_excluded(self):
        """
        Data-Truth Invariant:
        prepare_dataset_from_df must strictly filter out rows flagged as SECTOR_ESTIMATE or is_sector_imputed=1.
        """
        raw_df = pd.DataFrame({
            "trading_date": [f"2026-01-{i:02d}" for i in range(1, 21)],
            "symbol": ["INFY"] * 20,
            "tactical_20d": [0.5] * 20,
            "data_status": ["OBSERVED"] * 15 + ["SECTOR_ESTIMATE"] * 5,
            "is_sector_imputed": [0] * 10 + [1] * 5 + [0] * 5
        })

        dev_df, _ = self.runner.prepare_dataset_from_df(raw_df)

        self.assertEqual(len(dev_df), 10, "Only rows with OBSERVED and is_sector_imputed!=1 should remain")
        if "data_status" in dev_df.columns:
            self.assertFalse((dev_df["data_status"] == "SECTOR_ESTIMATE").any())
        if "is_sector_imputed" in dev_df.columns:
            self.assertFalse((dev_df["is_sector_imputed"] == 1).any())

    def test_market_alpha_separation_from_trader_dna(self):
        """
        Architecture Invariant:
        FEATURE_COLUMNS_8 must contain ONLY market/instrument factors, NEVER Trader DNA features.
        """
        trader_dna_keys = {"loss_tolerance", "reaction_speed", "revenge_trade_bias", "max_drawdown_pain", "ticket_size"}
        for feat in FEATURE_COLUMNS_8:
            self.assertNotIn(feat, trader_dna_keys, f"Trader DNA key {feat} leaked into Market Alpha feature set!")

    def test_full_synthetic_tournament_execution(self):
        """
        Executes a complete tournament on synthetic multi-factor data:
        Verifies baseline benchmark, candidate evaluation, DSR calculation, and registry persistence.
        """
        np.random.seed(42)
        n_sessions = 300
        dates = pd.date_range("2024-01-01", periods=n_sessions, freq="B").astype(str)

        # Generate synthetic factor matrix
        data = {
            "trading_date": dates,
            "symbol": ["RELIANCE"] * n_sessions,
            "data_status": ["OBSERVED"] * n_sessions,
            "is_sector_imputed": [0] * n_sessions,
            "tactical_20d": np.random.uniform(0.1, 0.9, n_sessions),
            "low_vol_quality": np.random.uniform(0.1, 0.9, n_sessions),
            "structural_200d": np.random.uniform(0.1, 0.9, n_sessions),
            "fii_dii_flow": np.random.uniform(0.1, 0.9, n_sessions),
            "sector_relative_strength": np.random.uniform(0.1, 0.9, n_sessions),
            "earnings_acceleration": np.random.uniform(0.1, 0.9, n_sessions),
            "realized_volatility": np.random.uniform(0.01, 0.03, n_sessions),
            "margin_safety_spread": np.random.uniform(0.1, 0.9, n_sessions),
            "net_return": np.random.normal(0.005, 0.02, n_sessions),
            "label": np.random.choice([1, -1, 0], size=n_sessions, p=[0.4, 0.4, 0.2])
        }
        df = pd.DataFrame(data)

        summary = self.runner.run_full_tournament(df=df)

        self.assertIn("run_id", summary)
        self.assertEqual(summary["cpcv_combinations"], 15)
        self.assertIn("baseline", summary)
        self.assertIn("candidates", summary)
        self.assertIn("champion", summary)
        self.assertEqual(len(summary["candidates"]), 2)

        # Verify summary JSON created on disk
        self.assertTrue(self.summary_json.exists())

        # Verify model_registry table entry
        with self.db.get_connection() as conn:
            row = conn.execute("SELECT model_id, model_name, status, validation_sharpe FROM model_registry WHERE model_id = ?", (summary["run_id"],)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row["model_id"], summary["run_id"])


if __name__ == "__main__":
    unittest.main()
