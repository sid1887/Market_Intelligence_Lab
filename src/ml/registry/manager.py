"""
Market Intelligence Lab — ML Model Registry (Stage A4).
Manages model lifecycle, artifact persistence, cryptographic integrity, and rollback.
"""

import os
import pickle
import hashlib
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

    def promote_model(self, model_id: str) -> bool:
        """Promotes a candidate model to PROMOTED status and demotes any existing active models."""
        with self.db.get_connection() as conn:
            # Demote current active models
            conn.execute(
                """
                UPDATE model_registry
                SET status = 'RETIRED'
                WHERE status IN ('PROMOTED', 'CHAMPION')
                """
            )
            # Promote new model
            res = conn.execute(
                """
                UPDATE model_registry
                SET status = 'PROMOTED'
                WHERE model_id = ?
                """,
                (model_id,)
            )
            return res.rowcount > 0

    def demote_model(self, model_id: str, reason: str = "PERFORMANCE_DEGRADATION") -> bool:
        """Demotes a model to DEMOTED status."""
        with self.db.get_connection() as conn:
            res = conn.execute(
                """
                UPDATE model_registry
                SET status = 'DEMOTED'
                WHERE model_id = ?
                """,
                (model_id,)
            )
            return res.rowcount > 0

    def list_models(self) -> List[Dict[str, Any]]:
        """Lists all registered models in the ledger."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT * FROM model_registry ORDER BY created_at DESC")
            return [dict(r) for r in cur.fetchall()]
