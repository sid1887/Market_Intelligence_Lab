"""
Market Intelligence Lab — Shadow Model Inference Runner (Stage A4).
Generates shadow model predictions in isolation with deterministic feature tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import numpy as np

from src.storage.database import DatabaseManager
from src.ml.features.builder import PITFeatureExtractor, FEATURE_COLUMNS
from src.ml.registry.manager import ModelRegistryManager

logger = logging.getLogger(__name__)


class ShadowInferenceRunner:
    """Executes shadow model predictions across active equities and records them for audit."""

    def __init__(self, db: DatabaseManager):
        self.db = db
        self.feature_extractor = PITFeatureExtractor(db)
        self.registry = ModelRegistryManager(db)

    def run_shadow_batch(
        self,
        as_of_date: str,
        symbols: Optional[List[str]] = None,
        model_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Executes a shadow inference batch for the specified session date.
        Uses active promoted model if model_id is None.
        """
        if model_id:
            # Query specific model
            with self.db.get_connection() as conn:
                cur = conn.execute("SELECT * FROM model_registry WHERE model_id = ?", (model_id,))
                rec = cur.fetchone()
                model_rec = dict(rec) if rec else None
            if not model_rec:
                return {"status": "MODEL_NOT_FOUND", "predictions_count": 0}
            model_obj, _ = self.registry.load_active_model() if model_rec.get("state") == "PROMOTED" else (None, None)
            if not model_obj:
                import pickle
                with open(model_rec["artifact_path"], "rb") as f:
                    model_obj = pickle.load(f)
        else:
            model_obj, model_rec = self.registry.load_active_model()

        if not model_obj or not model_rec:
            return {"status": "NO_ACTIVE_MODEL", "predictions_count": 0}

        # 1. Extract feature matrix
        feat_df = self.feature_extractor.extract_features_for_session(as_of_date, symbols)
        if feat_df.empty:
            return {"status": "NO_FEATURES_AVAILABLE", "predictions_count": 0}

        X_raw = feat_df[FEATURE_COLUMNS].values
        active_model_id = model_rec["model_id"]

        # 2. Predict excess returns
        try:
            preds = model_obj.predict(X_raw)
        except Exception:
            # Linear model needing imputation fallback
            from sklearn.impute import SimpleImputer
            X_imp = SimpleImputer(strategy="median").fit_transform(X_raw)
            preds = model_obj.predict(X_imp)

        # Compute pseudo probability using logistic sigmoid: 1 / (1 + exp(-50 * ret))
        probs_up = 1.0 / (1.0 + np.exp(-np.clip(preds * 50.0, -20.0, 20.0)))

        # 3. Persist to model_predictions_shadow
        records_to_insert = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for idx, row in feat_df.iterrows():
            pred_val = float(preds[idx])
            prob_val = float(probs_up[idx])
            f_hash = row["features_hash"]
            sym = row["symbol"]

            records_to_insert.append((
                active_model_id,
                sym,
                as_of_date,
                20,  # 20-day horizon
                round(pred_val, 6),
                round(prob_val, 4),
                round(pred_val - 0.04, 6),  # 80% CI rough spread
                round(pred_val + 0.04, 6),
                f_hash,
                now_iso
            ))

        with self.db.get_connection() as conn:
            conn.executemany(
                """
                INSERT INTO model_predictions_shadow (
                    model_id, symbol, as_of_date, horizon_days,
                    predicted_excess_return, predicted_prob_up,
                    confidence_interval_low, confidence_interval_high,
                    features_hash, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records_to_insert
            )

        return {
            "status": "COMPLETED",
            "model_id": active_model_id,
            "as_of_date": as_of_date,
            "predictions_count": len(records_to_insert),
            "mean_predicted_excess_return": round(float(np.mean(preds)), 6)
        }
