"""
Market Intelligence Lab — Walk-Forward Model Tournament (Stage A3).
Trains and benchmarks multiple ML architectures under strict purged/embargoed walk-forward cross validation.
Includes Zero-Return Baseline, Ridge, Logistic, and HistGradientBoosting (native NaN handling).
"""

import os
import json
import uuid
import hashlib
import pickle
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from sklearn.linear_model import Ridge, LogisticRegression
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from src.storage.database import DatabaseManager
from src.ml.features.builder import PITFeatureExtractor, FEATURE_COLUMNS
from src.ml.labels.builder import MaturedForwardLabelBuilder

logger = logging.getLogger(__name__)


class ZeroReturnBaseline:
    """Deterministic zero-alpha baseline. Always predicts 0.0 excess return."""
    def fit(self, X, y):
        return self

    def predict(self, X):
        return np.zeros(len(X))


class ModelTournament:
    """Executes purged walk-forward model evaluation and tournament competition."""

    def __init__(self, db: DatabaseManager, artifact_dir: str = "models/registry"):
        self.db = db
        self.artifact_dir = artifact_dir
        os.makedirs(self.artifact_dir, exist_ok=True)
        self.feature_extractor = PITFeatureExtractor(db)
        self.label_builder = MaturedForwardLabelBuilder(db, horizon_sessions=20)

    def prepare_dataset(
        self,
        start_date: str,
        end_date: str,
        symbols: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Extracts aligned feature-label dataset with matured labels only."""
        feats = self.feature_extractor.extract_panel(start_date, end_date, symbols)
        if feats.empty:
            return pd.DataFrame()

        labels = self.label_builder.build_labels(symbols, as_of_cutoff=end_date)
        if labels.empty:
            return pd.DataFrame()

        # Merge on (symbol, trading_date)
        merged = pd.merge(feats, labels, on=["symbol", "trading_date"], how="inner")
        # Keep only matured records with valid continuous label
        matured = merged[merged["matured"] & merged["label_excess_ret_net"].notna()].copy()
        return matured.sort_values(by="trading_date").reset_index(drop=True)

    def evaluate_model(
        self,
        model_name: str,
        model,
        X_train: np.ndarray,
        y_train: np.ndarray,
        X_test: np.ndarray,
        y_test: np.ndarray
    ) -> Dict[str, Any]:
        """Fits model on training split and computes out-of-sample metrics."""
        model.fit(X_train, y_train)
        preds = model.predict(X_test)

        # 1. Information Coefficient (Spearman Rank Correlation)
        if np.all(preds == 0) or np.std(preds) == 0 or np.std(y_test) == 0:
            ic = 0.0
        else:
            res, _ = spearmanr(preds, y_test)
            ic = float(res) if not np.isnan(res) else 0.0

        # 2. Out-of-sample Sharpe Ratio of Top Quintile
        # Strategy: go long predictions in top 20%, evaluate mean return / volatility
        q80 = np.quantile(preds, 0.8)
        top_mask = preds >= q80
        if np.sum(top_mask) > 0:
            top_returns = y_test[top_mask]
            mean_ret = float(np.mean(top_returns))
            std_ret = float(np.std(top_returns))
            sharpe = (mean_ret / (std_ret + 1e-8)) * np.sqrt(252 / 20)
        else:
            sharpe = 0.0

        # 3. Directional Accuracy
        direction_pred = preds > 0
        direction_true = y_test > 0
        acc = float(np.mean(direction_pred == direction_true) * 100.0)

        # 4. Error metrics
        mae = float(np.mean(np.abs(preds - y_test)))
        rmse = float(np.sqrt(np.mean((preds - y_test) ** 2)))

        return {
            "model_name": model_name,
            "validation_ic": round(ic, 4),
            "validation_sharpe": round(sharpe, 4),
            "directional_accuracy_pct": round(acc, 2),
            "mae": round(mae, 6),
            "rmse": round(rmse, 6),
            "model_obj": model
        }

    def run_tournament(
        self,
        start_date: str = "2024-01-01",
        end_date: str = "2026-10-28",
        train_ratio: float = 0.75,
        embargo_sessions: int = 20
    ) -> Dict[str, Any]:
        """
        Executes purged walk-forward cross validation tournament.
        Candidates:
        1. Zero-Return Baseline
        2. Ridge Regressor (L2 regularized)
        3. HistGradientBoostingRegressor (native NaN handling)
        """
        df = self.prepare_dataset(start_date, end_date)
        if len(df) < 100:
            return {
                "status": "INSUFFICIENT_DATA",
                "message": f"Dataset contains {len(df)} samples, minimum 100 required.",
                "winner": None
            }

        dates = sorted(df["trading_date"].unique())
        split_idx = int(len(dates) * train_ratio)
        train_end_idx = max(0, split_idx - embargo_sessions)  # 20 session embargo purge

        train_cutoff = dates[train_end_idx]
        test_start = dates[split_idx]

        train_df = df[df["trading_date"] <= train_cutoff]
        test_df = df[df["trading_date"] >= test_start]

        if len(train_df) < 50 or len(test_df) < 20:
            return {
                "status": "INSUFFICIENT_SAMPLES_AFTER_SPLIT",
                "train_samples": len(train_df),
                "test_samples": len(test_df),
                "winner": None
            }

        X_train_raw = train_df[FEATURE_COLUMNS].values
        y_train = train_df["label_excess_ret_net"].values
        X_test_raw = test_df[FEATURE_COLUMNS].values
        y_test = test_df["label_excess_ret_net"].values

        # Imputed arrays for linear models
        imputer = SimpleImputer(strategy="median")
        X_train_imp = imputer.fit_transform(X_train_raw)
        X_test_imp = imputer.transform(X_test_raw)

        candidates = [
            ("ZeroReturnBaseline", ZeroReturnBaseline(), X_train_raw, X_test_raw),
            ("RidgeRegressor_alpha10", Ridge(alpha=10.0), X_train_imp, X_test_imp),
            (
                "HistGradientBoostingRegressor",
                HistGradientBoostingRegressor(
                    max_iter=100,
                    learning_rate=0.05,
                    max_leaf_nodes=15,
                    min_samples_leaf=20,
                    random_state=42
                ),
                X_train_raw,
                X_test_raw
            ),
        ]

        leaderboard = []
        for name, model, x_tr, x_te in candidates:
            try:
                res = self.evaluate_model(name, model, x_tr, y_train, x_te, y_test)
                leaderboard.append(res)
            except Exception as e:
                logger.warning(f"Model {name} failed evaluation: {e}")

        if not leaderboard:
            return {"status": "EVALUATION_FAILED", "winner": None}

        # Sort by Validation Sharpe then IC
        leaderboard.sort(key=lambda x: (x["validation_sharpe"], x["validation_ic"]), reverse=True)
        winner = leaderboard[0]

        # Check promotion hurdle: must beat baseline IC (> 0.0)
        promoted = winner["validation_ic"] > 0.02 and winner["validation_sharpe"] > 0.0
        model_id = f"model_{winner['model_name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Serialize model artifact
        artifact_filename = f"{model_id}.pkl"
        artifact_path = os.path.join(self.artifact_dir, artifact_filename)
        with open(artifact_path, "wb") as f:
            pickle.dump(winner["model_obj"], f)

        # Compute SHA-256
        with open(artifact_path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()

        # Save to model_registry in DB
        metrics_dict = {
            "validation_sharpe": winner["validation_sharpe"],
            "validation_ic": winner["validation_ic"],
            "directional_accuracy_pct": winner["directional_accuracy_pct"],
            "mae": winner["mae"],
            "rmse": winner["rmse"]
        }

        with self.db.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO model_registry (
                    model_id, model_name, model_version, task_type,
                    status, artifact_path, artifact_hash,
                    train_start, train_end, metrics_json,
                    approved_by, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    model_id,
                    winner["model_name"],
                    "v1_tournament",
                    "REGRESSION",
                    "PROMOTED" if promoted else "CANDIDATE",
                    artifact_path,
                    checksum,
                    str(dates[0]),
                    str(train_cutoff),
                    json.dumps(metrics_dict),
                    "AUTOMATED_SUPERVISOR_TOURNAMENT",
                    datetime.now(timezone.utc).isoformat()
                )
            )

        return {
            "status": "COMPLETED",
            "promoted": promoted,
            "winner_model_id": model_id,
            "architecture": winner["model_name"],
            "validation_sharpe": winner["validation_sharpe"],
            "validation_ic": winner["validation_ic"],
            "directional_accuracy_pct": winner["directional_accuracy_pct"],
            "n_train_samples": len(train_df),
            "n_test_samples": len(test_df),
            "leaderboard": [
                {k: v for k, v in m.items() if k != "model_obj"}
                for m in leaderboard
            ]
        }
