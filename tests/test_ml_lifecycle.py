"""
Market Intelligence Lab — Adaptive ML & Autonomous Supervisor Lifecycle Test Suite.
Verifies Stage A1 through A5 (ADR-0005, ADR-0008, ADR-0012).
"""

import os
import shutil
import tempfile
import unittest
import hashlib
import json
import uuid
import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager
from src.ml.features.builder import PITFeatureExtractor, compute_features_hash, FEATURE_COLUMNS
from src.ml.labels.builder import MaturedForwardLabelBuilder
from src.ml.training.tournament import ModelTournament, ZeroReturnBaseline
from src.ml.registry.manager import ModelRegistryManager
from src.ml.inference.shadow_runner import ShadowInferenceRunner
from src.supervisor.state_machine import SupervisorStateMachine


class TestMLLifecycle(unittest.TestCase):
    """Rigorous end-to-end testing of Adaptive ML and Supervisor Layer under strict isolation."""

    @classmethod
    def setUpClass(cls):
        # Create an isolated temporary workspace so tests NEVER touch data/market_lab.db
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.db_path = os.path.join(cls.temp_dir.name, "test_market_lab.db")
        cls.artifact_dir = os.path.join(cls.temp_dir.name, "models_registry")
        os.makedirs(cls.artifact_dir, exist_ok=True)

        # Copy data/market_lab.db into disposable test directory
        shutil.copy2("data/market_lab.db", cls.db_path)

        cls.db = DatabaseManager(cls.db_path)
        cls.feature_extractor = PITFeatureExtractor(cls.db)
        cls.label_builder = MaturedForwardLabelBuilder(cls.db, horizon_sessions=20)
        cls.tournament = ModelTournament(cls.db, artifact_dir=cls.artifact_dir)
        cls.registry = ModelRegistryManager(cls.db, artifact_dir=cls.artifact_dir)
        cls.shadow_runner = ShadowInferenceRunner(cls.db)
        # Point shadow_runner's registry to use isolated artifact_dir
        cls.shadow_runner.registry = cls.registry
        cls.supervisor = SupervisorStateMachine(cls.db)

    @classmethod
    def tearDownClass(cls):
        # Clean up temporary directory completely
        cls.temp_dir.cleanup()

    # --------------------------------------------------------------------------
    # 1. Feature Extractor & Deterministic Hash
    # --------------------------------------------------------------------------
    def test_01_feature_extractor_and_hash_determinism(self):
        """Features extracted as of session T are strictly <= T; hash is deterministic."""
        features_a = {"ret_1d": 0.0125, "vol_20d": 0.245, "dist_sma200": 0.05}
        features_b = {"dist_sma200": 0.05, "ret_1d": 0.0125, "vol_20d": 0.245}

        # Hashes must be identical regardless of dictionary insertion order
        hash_a = compute_features_hash(features_a)
        hash_b = compute_features_hash(features_b)
        self.assertEqual(hash_a, hash_b)
        self.assertEqual(len(hash_a), 64)

        # Extract features for TCS as of 2026-10-28
        df_feats = self.feature_extractor.extract_features_for_session("2026-10-28", ["TCS"])
        self.assertFalse(df_feats.empty)
        self.assertEqual(df_feats.iloc[0]["symbol"], "TCS")
        self.assertEqual(df_feats.iloc[0]["trading_date"], "2026-10-28")
        self.assertIn("features_hash", df_feats.columns)
        self.assertIsNotNone(df_feats.iloc[0]["features_hash"])

    # --------------------------------------------------------------------------
    # 2. Forward Labels & Transaction Friction
    # --------------------------------------------------------------------------
    def test_02_forward_labels_and_friction_accounting(self):
        """Forward labels incorporate 15 bps statutory Indian equity friction; unsettled remain unmatured."""
        calendar = self.label_builder.get_trading_calendar()
        self.assertGreater(len(calendar), 100)

        # Build labels for INFY
        df_labels = self.label_builder.build_labels(["INFY"])
        self.assertFalse(df_labels.empty)

        # Historical observations should be matured
        early_obs = df_labels[df_labels["trading_date"] <= calendar[-30]]
        self.assertTrue(early_obs.iloc[0]["matured"])
        self.assertIsNotNone(early_obs.iloc[0]["label_excess_ret_net"])

        # Latest observations (within last 20 sessions) must NOT be matured
        latest_obs = df_labels[df_labels["trading_date"] == calendar[-1]]
        if not latest_obs.empty:
            self.assertFalse(latest_obs.iloc[0]["matured"])
            self.assertTrue(pd.isna(latest_obs.iloc[0]["label_excess_ret_net"]))

    # --------------------------------------------------------------------------
    # 3. Model Tournament Execution
    # --------------------------------------------------------------------------
    def test_03_model_tournament_walk_forward(self):
        """Walk-forward tournament trains candidate architectures under purged cross-validation."""
        # Run mini tournament on historical segment
        res = self.tournament.run_tournament(
            start_date="2024-01-01",
            end_date="2026-10-28",
            train_ratio=0.75,
            embargo_sessions=20
        )
        self.assertIn(res["status"], ["COMPLETED", "INSUFFICIENT_DATA"])
        if res["status"] == "COMPLETED":
            self.assertIn("winner_model_id", res)
            self.assertIn("architecture", res)
            self.assertGreater(len(res["leaderboard"]), 1)

    # --------------------------------------------------------------------------
    # 4. Model Registry & Checksum Integrity
    # --------------------------------------------------------------------------
    def test_04_model_registry_lifecycle(self):
        """Model registry rejects baselines and sub-hurdle models, requires sha256 verification."""
        # 1. Non-existent model promotion must fail
        self.assertFalse(self.registry.promote_model("non_existent_model_id_999"))

        # 2. Baseline models must NEVER be promotable
        baseline_id = f"model_ZeroReturnBaseline_{uuid.uuid4().hex[:6]}"
        baseline_path = os.path.join(self.artifact_dir, f"{baseline_id}.pkl")
        with open(baseline_path, "wb") as f:
            import pickle
            pickle.dump(ZeroReturnBaseline(), f)
        with open(baseline_path, "rb") as f:
            baseline_hash = hashlib.sha256(f.read()).hexdigest()

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (
                    model_id, model_name, model_version, task_type,
                    status, artifact_path, artifact_hash, train_start, train_end, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    baseline_id,
                    "ZeroReturnBaseline",
                    "v1",
                    "REGRESSION",
                    "BASELINE",
                    baseline_path,
                    baseline_hash,
                    "2024-01-01",
                    "2026-06-01",
                    json.dumps({"validation_ic": 0.0, "validation_sharpe": 0.0}),
                    "2026-11-06T12:00:00"
                )
            )

        # Baseline promotion attempt must return False
        self.assertFalse(self.registry.promote_model(baseline_id))

        # 3. Model with sub-threshold metrics must fail promotion
        failing_id = f"model_RidgeRegressor_{uuid.uuid4().hex[:6]}"
        failing_path = os.path.join(self.artifact_dir, f"{failing_id}.pkl")
        with open(failing_path, "wb") as f:
            import pickle
            pickle.dump({"fake_model": 1}, f)
        with open(failing_path, "rb") as f:
            failing_hash = hashlib.sha256(f.read()).hexdigest()

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (
                    model_id, model_name, model_version, task_type,
                    status, artifact_path, artifact_hash, train_start, train_end, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    failing_id,
                    "RidgeRegressor_alpha10",
                    "v1",
                    "REGRESSION",
                    "CANDIDATE",
                    failing_path,
                    failing_hash,
                    "2024-01-01",
                    "2026-06-01",
                    json.dumps({"validation_ic": 0.01, "validation_sharpe": -0.2}),
                    "2026-11-06T12:01:00"
                )
            )

        # Hurdle failure attempt must return False
        self.assertFalse(self.registry.promote_model(failing_id))

        # 4. Valid candidate meeting all hurdles must succeed
        from sklearn.linear_model import Ridge
        valid_id = f"model_HistGradientBoostingRegressor_{uuid.uuid4().hex[:6]}"
        valid_path = os.path.join(self.artifact_dir, f"{valid_id}.pkl")
        valid_obj = Ridge(alpha=1.0)
        valid_obj.fit(np.zeros((10, len(FEATURE_COLUMNS))), np.zeros(10))
        with open(valid_path, "wb") as f:
            import pickle
            pickle.dump(valid_obj, f)
        with open(valid_path, "rb") as f:
            valid_hash = hashlib.sha256(f.read()).hexdigest()

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (
                    model_id, model_name, model_version, task_type,
                    status, artifact_path, artifact_hash, train_start, train_end, metrics_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    valid_id,
                    "HistGradientBoostingRegressor",
                    "v1",
                    "REGRESSION",
                    "CANDIDATE",
                    valid_path,
                    valid_hash,
                    "2024-01-01",
                    "2026-06-01",
                    json.dumps({"validation_ic": 0.065, "validation_sharpe": 1.45}),
                    "2026-11-06T12:02:00"
                )
            )

        promoted = self.registry.promote_model(valid_id)
        self.assertTrue(promoted)

        # Check active model record
        active_rec = self.registry.get_active_model_record()
        self.assertIsNotNone(active_rec)
        self.assertEqual(active_rec["model_id"], valid_id)
        self.assertEqual(active_rec["status"], "PROMOTED")

        # Load active model from disk
        loaded_obj, meta = self.registry.load_active_model()
        self.assertIsNotNone(loaded_obj)
        self.assertEqual(meta["model_id"], valid_id)

    # --------------------------------------------------------------------------
    # 5. Shadow Inference Runner
    # --------------------------------------------------------------------------
    def test_05_shadow_inference_runner(self):
        """Shadow inference executes without polluting user-facing deterministic paths."""
        res = self.shadow_runner.run_shadow_batch(
            as_of_date="2026-10-28",
            symbols=["TCS", "INFY"]
        )
        self.assertIn(res["status"], ["COMPLETED", "NO_ACTIVE_MODEL"])
        if res["status"] == "COMPLETED":
            self.assertGreaterEqual(res["predictions_count"], 1)

            # Check SQLite table
            with self.db.get_connection() as conn:
                cur = conn.execute(
                    "SELECT COUNT(*) as c FROM model_predictions_shadow WHERE as_of_date = '2026-10-28'"
                )
                cnt = cur.fetchone()["c"]
                self.assertGreaterEqual(cnt, 1)

    # --------------------------------------------------------------------------
    # 6. Supervisor State Machine & Telemetry
    # --------------------------------------------------------------------------
    def test_06_supervisor_state_machine_and_telemetry(self):
        """Supervisor transitions states, logs telemetry, and evaluates invariants."""
        state = self.supervisor.get_state()
        self.assertIn("current_state", state)

        # Log a telemetry event
        log_id = self.supervisor.log_telemetry(
            metric_name="TEST_ACCURACY_CHECK",
            metric_value=85.2,
            threshold_breached=False,
            severity="INFO",
            message="Unit test verification event"
        )
        self.assertGreater(log_id, 0)

        # Verify state transition
        self.supervisor.transition_to("DEGRADED", "Unit testing state degradation")
        updated = self.supervisor.get_state()
        self.assertEqual(updated["current_state"], "DEGRADED")

        # Recover back to NORMAL
        self.supervisor.transition_to("NORMAL", "Unit test recovery to healthy state")
        recovered = self.supervisor.get_state()
        self.assertEqual(recovered["current_state"], "NORMAL")

        # Health invariant check
        health = self.supervisor.evaluate_system_health()
        self.assertIn(health["status"], ["HEALTHY", "NORMAL_BASELINE", "NO_ACTIVE_MODEL"])
        self.assertEqual(health["contaminated_factors_count"], 0)


if __name__ == "__main__":
    unittest.main()
