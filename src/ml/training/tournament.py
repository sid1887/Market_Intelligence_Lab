"""
Market Intelligence Lab — Walk-Forward Model Tournament (Stage A3).
Trains and benchmarks multiple ML architectures under strict purged/embargoed walk-forward cross validation.
Includes Zero-Return Baseline, Ridge, and HistGradientBoosting (native NaN handling).
"""

import os
import json
import uuid
import hashlib
import pickle
import math
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

from src.storage.database import DatabaseManager
from src.ml.features.builder import PITFeatureExtractor, FEATURE_COLUMNS
from src.ml.labels.builder import MaturedForwardLabelBuilder
from src.ml.registry.manager import ModelRegistryManager

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
        self.registry = ModelRegistryManager(db, artifact_dir=self.artifact_dir)

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
        y_test: np.ndarray,
        test_dates: Optional[np.ndarray] = None
    ) -> Dict[str, Any]:
        """Fits model on training split and computes out-of-sample metrics."""
        model.fit(X_train, y_train)
        preds = model.predict(X_test)

        # 1. Information Coefficient (Spearman Rank Correlation)
        is_constant_prediction = bool(np.all(preds == 0) or np.std(preds) == 0)
        if is_constant_prediction or np.std(y_test) == 0:
            ic = 0.0
            sharpe = 0.0
        else:
            res, _ = spearmanr(preds, y_test)
            ic = float(res) if (not np.isnan(res) and math.isfinite(res)) else 0.0

            # 2. Out-of-sample Sharpe Ratio of Top Quintile (Signal-based)
            if test_dates is not None and len(test_dates) == len(preds):
                unique_dates = np.unique(test_dates)
                period_returns = []
                for td in unique_dates:
                    mask_td = (test_dates == td)
                    preds_td = preds[mask_td]
                    y_td = y_test[mask_td]
                    if len(preds_td) >= 5 and np.std(preds_td) > 1e-8:
                        q80 = np.quantile(preds_td, 0.8)
                        top_m = preds_td >= q80
                        if np.sum(top_m) > 0:
                            period_returns.append(float(np.mean(y_td[top_m])))
                    elif len(preds_td) > 0 and np.std(preds_td) > 1e-8:
                        period_returns.append(float(np.mean(y_td)))

                if len(period_returns) > 1 and np.std(period_returns) > 1e-8:
                    mean_ret = float(np.mean(period_returns))
                    std_ret = float(np.std(period_returns))
                    calc_sharpe = (mean_ret / std_ret) * np.sqrt(252 / 20)
                    sharpe = float(calc_sharpe) if math.isfinite(calc_sharpe) else 0.0
                else:
                    sharpe = 0.0
            else:
                q80 = np.quantile(preds, 0.8)
                top_mask = preds >= q80
                if np.sum(top_mask) > 0:
                    top_returns = y_test[top_mask]
                    mean_ret = float(np.mean(top_returns))
                    std_ret = float(np.std(top_returns))
                    if std_ret > 1e-8:
                        calc_sharpe = (mean_ret / std_ret) * np.sqrt(252 / 20)
                        sharpe = float(calc_sharpe) if math.isfinite(calc_sharpe) else 0.0
                    else:
                        sharpe = 0.0
                else:
                    sharpe = 0.0

        # 3. Directional Accuracy
        direction_pred = preds > 0
        direction_true = y_test > 0
        acc = float(np.mean(direction_pred == direction_true) * 100.0)
        if not math.isfinite(acc):
            acc = 0.0

        # 4. Error metrics
        mae = float(np.mean(np.abs(preds - y_test)))
        rmse = float(np.sqrt(np.mean((preds - y_test) ** 2)))
        if not math.isfinite(mae):
            mae = 0.0
        if not math.isfinite(rmse):
            rmse = 0.0

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
        embargo_sessions: int = 20,
        n_splits: int = 3
    ) -> Dict[str, Any]:
        """
        Executes purged walk-forward cross-validation tournament.
        Candidates:
        1. ZeroReturnBaseline
        2. RidgeRegressor_alpha10 (fold-isolated median imputer + Ridge)
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
        if len(dates) < 40:
            return {
                "status": "INSUFFICIENT_DATA",
                "message": f"Only {len(dates)} unique dates available, minimum 40 required.",
                "winner": None
            }

        def build_candidates():
            return [
                ("ZeroReturnBaseline", ZeroReturnBaseline()),
                (
                    "RidgeRegressor_alpha10",
                    Pipeline([
                        ("imputer", SimpleImputer(strategy="median")),
                        ("regressor", Ridge(alpha=10.0))
                    ])
                ),
                (
                    "HistGradientBoostingRegressor",
                    HistGradientBoostingRegressor(
                        max_iter=100,
                        learning_rate=0.05,
                        max_leaf_nodes=15,
                        min_samples_leaf=20,
                        random_state=42
                    )
                ),
            ]

        # Multi-fold walk-forward purged cross-validation splits
        folds: List[Tuple[pd.DataFrame, pd.DataFrame]] = []
        if len(dates) >= 90 and n_splits > 1:
            min_train_dates = int(len(dates) * 0.5)
            eval_dates = dates[min_train_dates:]
            fold_size = max(10, len(eval_dates) // n_splits)
            for i in range(n_splits):
                start_i = i * fold_size
                end_i = (i + 1) * fold_size if i < n_splits - 1 else len(eval_dates)
                fold_test_dates = eval_dates[start_i:end_i]
                if not fold_test_dates:
                    continue
                test_start = fold_test_dates[0]
                test_start_idx = dates.index(test_start)
                train_cutoff_idx = max(0, test_start_idx - embargo_sessions)
                train_cutoff = dates[train_cutoff_idx]
                f_train = df[(df["trading_date"] <= train_cutoff) & (df["target_date"] < test_start)].copy()
                f_test = df[df["trading_date"].isin(fold_test_dates)].copy()
                if len(f_train) >= 30 and len(f_test) >= 10:
                    folds.append((f_train, f_test))

        if not folds:
            # Fallback to single purged/embargoed split
            split_idx = int(len(dates) * train_ratio)
            test_start = dates[split_idx]
            train_end_idx = max(0, split_idx - embargo_sessions)
            train_cutoff = dates[train_end_idx]
            train_df = df[(df["trading_date"] <= train_cutoff) & (df["target_date"] < test_start)].copy()
            test_df = df[df["trading_date"] >= test_start].copy()
            if len(train_df) < 50 or len(test_df) < 20:
                return {
                    "status": "INSUFFICIENT_SAMPLES_AFTER_SPLIT",
                    "train_samples": len(train_df),
                    "test_samples": len(test_df),
                    "winner": None
                }
            folds.append((train_df, test_df))

        # Evaluate candidate architectures across folds
        candidate_specs = build_candidates()
        model_fold_metrics: Dict[str, List[Dict[str, Any]]] = {name: [] for name, _ in candidate_specs}

        for fold_idx, (f_train, f_test) in enumerate(folds):
            X_tr = f_train[FEATURE_COLUMNS].values
            y_tr = f_train["label_excess_ret_net"].values
            X_te = f_test[FEATURE_COLUMNS].values
            y_te = f_test["label_excess_ret_net"].values
            t_dates = f_test["trading_date"].values

            for name, model_template in build_candidates():
                try:
                    res = self.evaluate_model(name, model_template, X_tr, y_tr, X_te, y_te, test_dates=t_dates)
                    model_fold_metrics[name].append(res)
                except Exception as e:
                    logger.warning(f"Model {name} failed fold {fold_idx}: {e}")

        leaderboard = []
        for name, _ in candidate_specs:
            f_results = model_fold_metrics.get(name, [])
            if not f_results:
                continue
            avg_sharpe = float(np.mean([r["validation_sharpe"] for r in f_results]))
            avg_ic = float(np.mean([r["validation_ic"] for r in f_results]))
            avg_acc = float(np.mean([r["directional_accuracy_pct"] for r in f_results]))
            avg_mae = float(np.mean([r["mae"] for r in f_results]))
            avg_rmse = float(np.mean([r["rmse"] for r in f_results]))

            leaderboard.append({
                "model_name": name,
                "validation_sharpe": round(avg_sharpe, 4),
                "validation_ic": round(avg_ic, 4),
                "directional_accuracy_pct": round(avg_acc, 2),
                "mae": round(avg_mae, 6),
                "rmse": round(avg_rmse, 6),
                "n_folds_evaluated": len(f_results)
            })

        if not leaderboard:
            return {"status": "EVALUATION_FAILED", "winner": None}

        # Sort by Validation Sharpe then IC descending
        leaderboard.sort(key=lambda x: (x["validation_sharpe"], x["validation_ic"]), reverse=True)
        winner = leaderboard[0]

        # Train winning model on full training set up to final train cutoff
        last_train_df = folds[-1][0]
        X_final_train = last_train_df[FEATURE_COLUMNS].values
        y_final_train = last_train_df["label_excess_ret_net"].values

        winner_candidates = dict(build_candidates())
        winner_model_obj = winner_candidates[winner["model_name"]]
        winner_model_obj.fit(X_final_train, y_final_train)

        is_baseline = "Baseline" in winner["model_name"]
        model_id = f"model_{winner['model_name']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"

        # Serialize model artifact
        artifact_filename = f"{model_id}.pkl"
        artifact_path = os.path.join(self.artifact_dir, artifact_filename)
        with open(artifact_path, "wb") as f:
            pickle.dump(winner_model_obj, f)

        with open(artifact_path, "rb") as f:
            checksum = hashlib.sha256(f.read()).hexdigest()

        metrics_dict = {
            "validation_sharpe": winner["validation_sharpe"],
            "validation_ic": winner["validation_ic"],
            "directional_accuracy_pct": winner["directional_accuracy_pct"],
            "mae": winner["mae"],
            "rmse": winner["rmse"],
            "n_folds_evaluated": winner["n_folds_evaluated"]
        }

        # Status: Baseline models are saved as BASELINE; Candidates are saved as CANDIDATE
        initial_status = "BASELINE" if is_baseline else "CANDIDATE"

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
                    initial_status,
                    artifact_path,
                    checksum,
                    str(dates[0]),
                    str(last_train_df["trading_date"].max()),
                    json.dumps(metrics_dict),
                    "AUTOMATED_SUPERVISOR_TOURNAMENT",
                    datetime.now(timezone.utc).isoformat()
                )
            )

        # Unified promotion routing: NEVER directly promote via SQL; route through ModelRegistryManager gate
        promoted = False
        if not is_baseline and winner["validation_ic"] > 0.02 and winner["validation_sharpe"] > 0.0:
            promoted = self.registry.promote_model(model_id)

        total_train_samples = sum(len(f[0]) for f in folds)
        total_test_samples = sum(len(f[1]) for f in folds)

        return {
            "status": "COMPLETED",
            "promoted": promoted,
            "winner_model_id": model_id,
            "architecture": winner["model_name"],
            "validation_sharpe": winner["validation_sharpe"],
            "validation_ic": winner["validation_ic"],
            "directional_accuracy_pct": winner["directional_accuracy_pct"],
            "n_train_samples": total_train_samples,
            "n_test_samples": total_test_samples,
            "n_folds": len(folds),
            "leaderboard": leaderboard
        }
