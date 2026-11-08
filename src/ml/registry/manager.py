"""
Market Intelligence Lab — ML Model Registry (Stage A4).
Manages model lifecycle, artifact persistence, cryptographic integrity, and rollback.
"""

import os
import uuid
import pickle
import hashlib
import json
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class ModelRegistryManager:
    """Manages model metadata, promotions, demotions, and artifacts."""

    def __init__(self, db: DatabaseManager, artifact_dir: str = "models/registry"):
        self.db = db
        self.artifact_dir = artifact_dir
        os.makedirs(self.artifact_dir, exist_ok=True)

    def get_active_model_record(self) -> Optional[Dict[str, Any]]:
        """Returns the active (PROMOTED / CHAMPION) model metadata record from SQLite."""
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT * FROM model_registry
                WHERE status IN ('PROMOTED', 'CHAMPION')
                ORDER BY created_at DESC
                LIMIT 1
                """
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def load_active_model(self) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Loads and verifies the active model object from disk."""
        rec = self.get_active_model_record()
        if not rec:
            return None, None

        path = rec["artifact_path"]
        if not path or not os.path.exists(path):
            logger.error(f"Model artifact not found on disk at {path}")
            return None, rec

        # Check cryptographic checksum
        with open(path, "rb") as f:
            bytes_data = f.read()
            checksum = hashlib.sha256(bytes_data).hexdigest()

        if checksum != rec["artifact_hash"]:
            logger.error(f"Model artifact {path} checksum mismatch! Expected {rec['artifact_hash']}, got {checksum}")
            return None, rec

        model_obj = pickle.loads(bytes_data)
        return model_obj, rec

    def load_model_by_id(self, model_id: str) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Loads and cryptographically verifies a specific model artifact by model_id."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM model_registry WHERE model_id = ?", (model_id,))
            row = cur.fetchone()
            rec = dict(row) if row else None

        if not rec:
            logger.warning(f"Model ID '{model_id}' not found in registry.")
            return None, None

        path = rec.get("artifact_path")
        if not path or not os.path.exists(path):
            logger.error(f"Model artifact not found on disk at {path}")
            return None, rec

        with open(path, "rb") as f:
            bytes_data = f.read()
            checksum = hashlib.sha256(bytes_data).hexdigest()

        if checksum != rec.get("artifact_hash"):
            logger.error(f"Model artifact {path} checksum mismatch! Expected {rec.get('artifact_hash')}, got {checksum}")
            return None, rec

        try:
            model_obj = pickle.loads(bytes_data)
            return model_obj, rec
        except Exception as e:
            logger.error(f"Failed to unpickle model artifact {path}: {e}")
            return None, rec

    def register_model(
        self,
        model_name: str,
        model_version: str,
        task_type: str,
        artifact_pipeline: Any,
        metrics: Dict[str, Any],
        train_start: str = "2024-10-21",
        train_end: str = "2026-10-28",
        status: str = "CANDIDATE",
        approved_by: Optional[str] = None,
        target_horizon_days: int = 20
    ) -> str:
        """Serializes and registers a trained model in model_registry."""
        os.makedirs(self.artifact_dir, exist_ok=True)
        model_id = f"model_{model_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        artifact_path = os.path.join(self.artifact_dir, f"{model_id}.pkl")
        with open(artifact_path, "wb") as f:
            pickle.dump(artifact_pipeline, f)

        with open(artifact_path, "rb") as f:
            artifact_hash = hashlib.sha256(f.read()).hexdigest()

        val_ic = metrics.get("validation_ic") if "validation_ic" in metrics else metrics.get("aggregate_val_ic")
        val_sharpe = metrics.get("validation_sharpe", 0.0)
        metrics_payload = dict(metrics)
        if "validation_ic" not in metrics_payload and val_ic is not None:
            metrics_payload["validation_ic"] = val_ic
        if "validation_sharpe" not in metrics_payload:
            metrics_payload["validation_sharpe"] = val_sharpe

        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (
                    model_id, model_name, model_version, task_type,
                    status, artifact_path, artifact_hash,
                    train_start, train_end, metrics_json,
                    validation_ic, validation_sharpe,
                    approved_by, created_at, metric_validity, target_horizon_days
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'VALID', ?)
                """,
                (
                    model_id, model_name, model_version, task_type,
                    status, artifact_path, artifact_hash,
                    train_start, train_end, json.dumps(metrics_payload),
                    val_ic, val_sharpe,
                    approved_by, now_iso, target_horizon_days
                )
            )
            conn.commit()
        logger.info(f"Registered model '{model_id}' (horizon={target_horizon_days}d, status={status}, IC={val_ic}).")
        return model_id

    def promote_model(
        self,
        model_id: str,
        approved_by: str = "STAGE_4_WALK_FORWARD_TOURNAMENT",
        min_ic_hurdle: float = 0.02
    ) -> bool:
        """
        Promotes a candidate model to CHAMPION status after strictly validating:
        1. Model existence in registry
        2. Status is strictly 'CANDIDATE' (cannot promote BASELINE, RETIRED, DEMOTED, or non-candidate)
        3. Model architecture is not a baseline
        4. Artifact exists on disk, is a regular file within artifact_dir, and passes SHA-256 integrity verification
        5. Validation metrics are finite numbers and exceed minimum hurdles (IC > min_ic_hurdle, Sharpe > 0.0)
        """
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM model_registry WHERE model_id = ?", (model_id,))
            row = cur.fetchone()
            if not row:
                logger.warning(f"Promotion rejected: model_id '{model_id}' does not exist.")
                return False
            rec = dict(row)

            # Gate 1: Positively require CANDIDATE status
            if rec.get("status") != "CANDIDATE":
                logger.warning(f"Promotion rejected: model '{model_id}' has non-candidate status '{rec.get('status')}'.")
                return False

            if "Baseline" in rec.get("model_name", ""):
                logger.warning(f"Promotion rejected: baseline architecture '{rec.get('model_name')}' cannot be promoted.")
                return False

            # Gate 2: Artifact existence, path containment & SHA-256 verification
            path = rec.get("artifact_path")
            if not path or not os.path.isfile(path):
                logger.error(f"Promotion rejected: artifact file missing or invalid at '{path}'.")
                return False

            # Prevent directory traversal
            abs_artifact_dir = os.path.abspath(self.artifact_dir)
            abs_path = os.path.abspath(path)
            if not abs_path.startswith(abs_artifact_dir):
                logger.error(f"Promotion rejected: artifact path '{path}' escapes artifact directory '{self.artifact_dir}'.")
                return False

            with open(path, "rb") as f:
                checksum = hashlib.sha256(f.read()).hexdigest()

            if checksum != rec.get("artifact_hash"):
                logger.error(f"Promotion rejected: artifact checksum mismatch for '{model_id}'.")
                return False

            # Gate 3: Metric hurdles verification with finite number checking
            metrics_raw = rec.get("metrics_json") or "{}"
            try:
                metrics = json.loads(metrics_raw) if isinstance(metrics_raw, str) else metrics_raw
            except Exception:
                metrics = {}

            raw_ic = metrics.get("validation_ic") or rec.get("validation_ic") or metrics.get("aggregate_val_ic")
            raw_sharpe = metrics.get("validation_sharpe") or rec.get("validation_sharpe") or 0.0

            if raw_ic is None or raw_sharpe is None:
                logger.warning(f"Promotion rejected: model '{model_id}' missing validation_ic or validation_sharpe metrics.")
                return False

            try:
                val_ic = float(raw_ic)
                val_sharpe = float(raw_sharpe)
            except (ValueError, TypeError):
                logger.warning(f"Promotion rejected: non-numeric metrics in model '{model_id}'.")
                return False

            if not math.isfinite(val_ic) or not math.isfinite(val_sharpe):
                logger.warning(f"Promotion rejected: non-finite metrics in model '{model_id}' (IC={val_ic}, Sharpe={val_sharpe}).")
                return False

            if val_ic <= min_ic_hurdle or val_sharpe <= 0.0:
                logger.warning(
                    f"Promotion rejected: model '{model_id}' failed metric hurdles "
                    f"(IC={val_ic} <= {min_ic_hurdle} or Sharpe={val_sharpe} <= 0.0)."
                )
                return False

            # Promotion Approved: Demote previous active model for this horizon and promote candidate to CHAMPION
            horizon = rec.get("target_horizon_days") or 20
            conn.execute(
                """
                UPDATE model_registry
                SET status = 'RETIRED'
                WHERE status IN ('PROMOTED', 'CHAMPION') AND COALESCE(target_horizon_days, 20) = ?
                """,
                (horizon,)
            )
            res = conn.execute(
                """
                UPDATE model_registry
                SET status = 'CHAMPION',
                    approved_by = ?,
                    validation_ic = ?,
                    validation_sharpe = ?
                WHERE model_id = ?
                """,
                (approved_by, val_ic, val_sharpe, model_id)
            )

            # Update model_horizon_deployments
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                INSERT INTO model_horizon_deployments (horizon_days, active_model_id, promoted_at, promoted_by, validation_ic, validation_sharpe)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(horizon_days) DO UPDATE SET
                    active_model_id = excluded.active_model_id,
                    promoted_at = excluded.promoted_at,
                    promoted_by = excluded.promoted_by,
                    validation_ic = excluded.validation_ic,
                    validation_sharpe = excluded.validation_sharpe;
                """,
                (horizon, model_id, now_iso, approved_by, val_ic, val_sharpe)
            )

            # Synchronize supervisor_state atomically if primary 20D horizon
            if horizon == 20:
                conn.execute(
                    """
                    INSERT INTO supervisor_state (singleton_id, current_state, active_model_id, last_transition_at, transition_reason, updated_at)
                    VALUES (1, 'NORMAL', ?, ?, ?, ?)
                    ON CONFLICT(singleton_id) DO UPDATE SET
                        active_model_id = excluded.active_model_id,
                        current_state = 'NORMAL',
                        last_transition_at = excluded.last_transition_at,
                        transition_reason = excluded.transition_reason,
                        updated_at = excluded.updated_at;
                    """,
                    (model_id, now_iso, f"MODEL_PROMOTION: {model_id}", now_iso)
                )
            conn.commit()
            logger.info(f"Successfully promoted model '{model_id}' (horizon={horizon}d) to CHAMPION (IC={val_ic}, Sharpe={val_sharpe}).")
            return res.rowcount > 0

    def demote_model(self, model_id: str, reason: str = "PERFORMANCE_DEGRADATION") -> bool:
        """Demotes a model to DEMOTED status and clears active pointer if demoted was active."""
        with self.db.get_connection() as conn:
            res = conn.execute(
                """
                UPDATE model_registry
                SET status = 'DEMOTED'
                WHERE model_id = ?
                """,
                (model_id,)
            )
            now_iso = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE supervisor_state
                SET active_model_id = NULL, updated_at = ?
                WHERE singleton_id = 1 AND active_model_id = ?
                """,
                (now_iso, model_id)
            )
            conn.execute(
                """
                UPDATE model_horizon_deployments
                SET active_model_id = NULL, validation_ic = 0.0, validation_sharpe = 0.0
                WHERE active_model_id = ?
                """,
                (model_id,)
            )
            return res.rowcount > 0

    def get_horizon_deployments(self) -> Dict[int, Dict[str, Any]]:
        """Returns map of active champion models per horizon (5, 20, 60)."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM model_horizon_deployments ORDER BY horizon_days ASC")
            rows = [dict(r) for r in cur.fetchall()]
            return {r["horizon_days"]: r for r in rows}

    def load_model_for_horizon(self, horizon_days: int) -> Tuple[Optional[Any], Optional[Dict[str, Any]]]:
        """Loads and verifies the active champion model for a specific target horizon."""
        deployments = self.get_horizon_deployments()
        dep = deployments.get(horizon_days)
        if not dep:
            logger.warning(f"No active deployment found for horizon {horizon_days}d.")
            return None, None
        return self.load_model_by_id(dep["active_model_id"])

    def list_models(self) -> List[Dict[str, Any]]:
        """Lists all registered models in the ledger."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM model_registry ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]
