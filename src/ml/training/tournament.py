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
from typing import Dict, Any, List, Optional, Tuple, Callable
import pandas as pd
import numpy as np
from scipy.stats import spearmanr

from sklearn.linear_model import Ridge
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer

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
        symbols: Optional[List[str]] = None,
        horizon_sessions: Optional[int] = None
    ) -> pd.DataFrame:
        """Extracts aligned feature-label dataset with matured labels only."""
        feats = self.feature_extractor.extract_panel(start_date, end_date, symbols)
        if feats.empty:
            return pd.DataFrame()

        labels = self.label_builder.build_labels(symbols, as_of_cutoff=end_date, horizon_sessions=horizon_sessions)
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


def load_clean_training_panel(
    db_manager: DatabaseManager,
    start_date: str = "2024-10-21",
    end_date: str = "2026-10-28",
    horizon_days: int = 20
) -> pd.DataFrame:
    """
    Loads authentic point-in-time factor features aligned with forward relative return labels.
    Strict Invariants enforced:
    - series = 'EQ'
    - is_orphaned = 0
    - is_synthetic = 0
    - is_eligible_for_training = 1
    """
    tourney = ModelTournament(db_manager)
    df = tourney.prepare_dataset(start_date=start_date, end_date=end_date, horizon_sessions=horizon_days)
    if df.empty:
        return df

    # Prefix factor columns to match tournament convention
    for c in FEATURE_COLUMNS:
        if c in df.columns:
            df[f"factor_{c}"] = df[c]

    # Canonical target column
    target_col = f"forward_relative_return_{horizon_days}d"
    if "label_excess_ret_net" in df.columns:
        df[target_col] = df["label_excess_ret_net"]
        if target_col != "forward_relative_return_20d" and "forward_relative_return_20d" not in df.columns:
            df["forward_relative_return_20d"] = df["label_excess_ret_net"]

    return df


def generate_walk_forward_folds(
    df: pd.DataFrame,
    n_folds: int = 5,
    horizon_days: int = 20,
    embargo_days: int = 5
) -> List[Tuple[np.ndarray, np.ndarray]]:
    """
    Constructs expanding-window walk-forward folds with strict purge of overlapping
    forward return periods and embargo buffers.
    Returns list of (train_idx, val_idx) numpy integer row indices for df.iloc[...].
    """
    if "trading_date" not in df.columns or len(df) == 0:
        return []

    dates = sorted(df["trading_date"].unique())
    if len(dates) < 30:
        return []

    min_train_dates = int(len(dates) * 0.4)
    eval_dates = dates[min_train_dates:]
    fold_size = max(10, len(eval_dates) // n_folds)

    folds: List[Tuple[np.ndarray, np.ndarray]] = []
    for fold_idx in range(n_folds):
        start_i = fold_idx * fold_size
        end_i = (fold_idx + 1) * fold_size if fold_idx < n_folds - 1 else len(eval_dates)
        fold_test_dates = eval_dates[start_i:end_i]
        if not fold_test_dates:
            continue

        test_start = fold_test_dates[0]
        test_start_idx = dates.index(test_start)
        train_cutoff_idx = max(0, test_start_idx - embargo_days)
        train_cutoff = dates[train_cutoff_idx]

        if "target_date" in df.columns:
            train_mask = (df["trading_date"] <= train_cutoff) & (df["target_date"] < test_start)
        else:
            purge_cutoff_idx = max(0, test_start_idx - horizon_days - embargo_days)
            train_mask = df["trading_date"] <= dates[purge_cutoff_idx]

        test_mask = df["trading_date"].isin(fold_test_dates)

        train_indices = np.where(train_mask.values)[0]
        val_indices = np.where(test_mask.values)[0]

        if len(train_indices) >= 50 and len(val_indices) >= 10:
            folds.append((train_indices, val_indices))

    return folds


def run_purged_walk_forward_tournament(
    db_manager: DatabaseManager,
    registry_manager: Optional[ModelRegistryManager] = None,
    progress_callback: Optional[Callable[[int, int, Dict[str, Any]], None]] = None
) -> Optional[str]:
    """
    Executes a 5-fold purged walk-forward cross-validation tournament.
    Enforces out-of-sample IC > 0.02 and Sharpe > 0 hurdles before promoting to CHAMPION.
    """
    logger.info("Executing Stage 4 Model Tournament with Purged Walk-Forward CV...")

    # 1. Fetch training data (Strict Invariants: is_orphaned = 0, is_synthetic = 0, series = 'EQ')
    df = load_clean_training_panel(db_manager)
    if len(df) < 5000:
        logger.error(f"Insufficient training observations: {len(df)} rows.")
        return None

    features = [c for c in df.columns if c.startswith("factor_")]
    target_col = "forward_relative_return_20d"
    if not features or target_col not in df.columns:
        logger.error("Required features or target column missing from clean panel.")
        return None

    # 2. Build 5 Expanding Window Folds with 20-Day Target Purge & Embargo
    folds = generate_walk_forward_folds(df, n_folds=5, horizon_days=20, embargo_days=5)
    if not folds:
        logger.error("Failed to construct walk-forward cross validation folds.")
        return None

    # Feature selection: Select roe_pct and debt_to_equity
    idx1 = features.index("factor_roe_pct") if "factor_roe_pct" in features else FEATURE_COLUMNS.index("roe_pct")
    idx2 = features.index("factor_debt_to_equity") if "factor_debt_to_equity" in features else FEATURE_COLUMNS.index("debt_to_equity")
    selector = ColumnTransformer(
        transformers=[("select", "passthrough", [idx1, idx2])],
        remainder="drop"
    )

    candidate_pipeline = Pipeline([
        ("selector", selector),
        ("imputer", SimpleImputer(strategy="median")),
        ("regressor", HistGradientBoostingRegressor(
            max_iter=80,
            learning_rate=0.03,
            max_depth=3,
            min_samples_leaf=100,
            l2_regularization=10.0,
            random_state=42
        ))
    ])

    fold_ics = []
    fold_sharpes = []

    for fold_idx, (train_idx, val_idx) in enumerate(folds):
        X_train, y_train = df.iloc[train_idx][features], df.iloc[train_idx][target_col]
        X_val, y_val = df.iloc[val_idx][features], df.iloc[val_idx][target_col]

        # Fit pipeline hermetically on training fold only
        candidate_pipeline.fit(X_train, y_train)

        # Predict on out-of-sample validation fold
        val_preds = candidate_pipeline.predict(X_val)

        # Calculate cross-sectional Spearman Rank IC and top quintile Sharpe
        val_df = df.iloc[val_idx].copy()
        val_df["pred"] = val_preds

        daily_ics = []
        top_returns = []
        for date, group in val_df.groupby("trading_date"):
            if len(group) >= 10 and group["pred"].std() > 1e-8:
                ic, _ = spearmanr(group["pred"], group[target_col])
                if not np.isnan(ic):
                    daily_ics.append(ic)
                q80 = group["pred"].quantile(0.8)
                top = group[group["pred"] >= q80]
                if len(top) > 0:
                    top_returns.append(float(top[target_col].mean()))

        mean_fold_ic = float(np.mean(daily_ics)) if daily_ics else 0.0
        fold_ics.append(mean_fold_ic)
        fold_sh = (np.mean(top_returns) / np.std(top_returns)) * np.sqrt(252 / 20) if len(top_returns) > 1 and np.std(top_returns) > 1e-8 else 0.0
        fold_sharpes.append(float(fold_sh))
        logger.info(f"Fold {fold_idx + 1}/5 Out-of-Sample IC: {mean_fold_ic:.4f}, Sharpe: {fold_sh:.4f}")

        if progress_callback:
            try:
                progress_callback(fold_idx + 1, len(folds), {
                    "fold": fold_idx + 1,
                    "validation_ic": round(mean_fold_ic, 4),
                    "validation_sharpe": round(fold_sh, 4)
                })
            except Exception as cb_err:
                logger.warning(f"Progress callback error in fold {fold_idx + 1}: {cb_err}")

    aggregate_ic = float(np.mean(fold_ics))
    aggregate_sharpe = float(np.mean(fold_sharpes))
    logger.info(f"Aggregate Walk-Forward Out-of-Sample IC: {aggregate_ic:.4f}, Sharpe: {aggregate_sharpe:.4f}")

    # 3. Governance Gate Evaluation
    if aggregate_ic <= 0.02 or aggregate_sharpe <= 0.0:
        logger.warning(
            f"Candidate rejected: Aggregate IC ({aggregate_ic:.4f}) or Sharpe ({aggregate_sharpe:.4f}) "
            f"did not clear hurdle (IC > 0.02, Sharpe > 0.0)."
        )
        return None

    # Fit final champion model on full history up to evaluation cutoff
    final_pipeline = candidate_pipeline.fit(df[features], df[target_col])

    metrics = {
        "walk_forward_folds": len(folds),
        "validation_ic": round(aggregate_ic, 4),
        "validation_sharpe": round(aggregate_sharpe, 4),
        "aggregate_val_ic": round(aggregate_ic, 4),
        "aggregate_val_sharpe": round(aggregate_sharpe, 4),
        "fold_ics": [round(x, 4) for x in fold_ics],
        "fold_sharpes": [round(x, 4) for x in fold_sharpes],
        "algorithm": "HistGradientBoostingRegressor",
        "pipeline": "ColumnTransformer+SimpleImputer+HistGradientBoostingRegressor"
    }

    if registry_manager is None:
        registry_manager = ModelRegistryManager(db_manager)

    # 4. Register and Atomically Promote
    model_id = registry_manager.register_model(
        model_name="HistGradientBoosting_Alpha5D",
        model_version="3.0.0",
        task_type="REGRESSION",
        artifact_pipeline=final_pipeline,
        metrics=metrics,
        status="CANDIDATE"
    )

    promotion_success = registry_manager.promote_model(
        model_id=model_id,
        approved_by="STAGE_4_WALK_FORWARD_TOURNAMENT",
        min_ic_hurdle=0.02
    )

    if promotion_success:
        logger.info(f"Successfully promoted model '{model_id}' to active CHAMPION.")
        return model_id
    else:
        logger.error(f"Promotion failed at registry manager for '{model_id}'.")
        return None


def run_multi_horizon_tournament(
    db_manager: DatabaseManager,
    registry_manager: Optional[ModelRegistryManager] = None,
    horizon_days: int = 20,
    progress_callback: Optional[Callable[[int, int, Dict[str, Any]], None]] = None
) -> Optional[str]:
    """
    Executes a 5-fold purged walk-forward cross-validation tournament for arbitrary horizon H in {5, 20, 60}.
    - For H=5: Purge window = 5 days, Embargo = 2 days
    - For H=20: Purge window = 20 days, Embargo = 5 days
    - For H=60: Purge window = 60 days, Embargo = 10 days
    """
    if horizon_days == 20:
        return run_purged_walk_forward_tournament(
            db_manager=db_manager,
            registry_manager=registry_manager,
            progress_callback=progress_callback
        )

    logger.info(f"Executing Multi-Horizon ({horizon_days}D) Walk-Forward Tournament...")

    df = load_clean_training_panel(db_manager, horizon_days=horizon_days)
    if len(df) < 5000:
        logger.error(f"Insufficient training observations for {horizon_days}D: {len(df)} rows.")
        return None

    features = [c for c in df.columns if c.startswith("factor_")]
    target_col = f"forward_relative_return_{horizon_days}d"
    if not features or target_col not in df.columns:
        logger.error(f"Required features or target column {target_col} missing from clean panel.")
        return None

    embargo_days = 2 if horizon_days == 5 else (10 if horizon_days == 60 else 5)
    folds = generate_walk_forward_folds(df, n_folds=5, horizon_days=horizon_days, embargo_days=embargo_days)
    if not folds:
        logger.error(f"Failed to construct walk-forward folds for {horizon_days}D.")
        return None

    annualization = np.sqrt(252 / horizon_days)

    # Candidate pipelines
    if horizon_days == 5:
        # Swing: short-term signals with L2 regularization
        candidate_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("regressor", Ridge(alpha=100.0))
        ])
        candidate_name = "Ridge_Alpha5D_5D"
        min_ic_hurdle = 0.015
        min_sharpe_hurdle = 0.70
    elif horizon_days == 60:
        # Long-horizon trend & drift
        candidate_pipeline = Pipeline([
            ("imputer", SimpleImputer(strategy="median")),
            ("regressor", HistGradientBoostingRegressor(
                max_iter=80,
                learning_rate=0.03,
                max_depth=3,
                min_samples_leaf=100,
                l2_regularization=10.0,
                random_state=42
            ))
        ])
        candidate_name = "HistGradientBoosting_Alpha5D_60D"
        min_ic_hurdle = 0.010
        min_sharpe_hurdle = 0.70
    else:
        raise ValueError(f"Unsupported horizon: {horizon_days}")

    fold_ics = []
    fold_sharpes = []

    for fold_idx, (train_idx, val_idx) in enumerate(folds):
        X_train, y_train = df.iloc[train_idx][features], df.iloc[train_idx][target_col]
        X_val, y_val = df.iloc[val_idx][features], df.iloc[val_idx][target_col]

        candidate_pipeline.fit(X_train, y_train)
        val_preds = candidate_pipeline.predict(X_val)

        val_df = df.iloc[val_idx].copy()
        val_df["pred"] = val_preds

        daily_ics = []
        top_returns = []
        for date, group in val_df.groupby("trading_date"):
            if len(group) >= 10 and group["pred"].std() > 1e-8:
                ic, _ = spearmanr(group["pred"], group[target_col])
                if not np.isnan(ic):
                    daily_ics.append(ic)
                q80 = group["pred"].quantile(0.8)
                top = group[group["pred"] >= q80]
                if len(top) > 0:
                    top_returns.append(float(top[target_col].mean()))

        mean_fold_ic = float(np.mean(daily_ics)) if daily_ics else 0.0
        fold_ics.append(mean_fold_ic)
        fold_sh = (np.mean(top_returns) / np.std(top_returns)) * annualization if len(top_returns) > 1 and np.std(top_returns) > 1e-8 else 0.0
        fold_sharpes.append(float(fold_sh))
        logger.info(f"Horizon {horizon_days}D Fold {fold_idx + 1}/5: IC={mean_fold_ic:.4f}, Sharpe={fold_sh:.4f}")

        if progress_callback:
            try:
                progress_callback(fold_idx + 1, len(folds), {
                    "horizon_days": horizon_days,
                    "fold": fold_idx + 1,
                    "validation_ic": round(mean_fold_ic, 4),
                    "validation_sharpe": round(fold_sh, 4)
                })
            except Exception as cb_err:
                logger.warning(f"Progress callback error: {cb_err}")

    aggregate_ic = float(np.mean(fold_ics))
    aggregate_sharpe = float(np.mean(fold_sharpes))
    logger.info(f"Horizon {horizon_days}D Aggregate Out-of-Sample IC: {aggregate_ic:.4f}, Sharpe: {aggregate_sharpe:.4f}")

    if aggregate_ic < min_ic_hurdle or aggregate_sharpe < min_sharpe_hurdle:
        logger.warning(
            f"{horizon_days}D Candidate rejected: Aggregate IC ({aggregate_ic:.4f}) or Sharpe ({aggregate_sharpe:.4f}) "
            f"below hurdle (IC > {min_ic_hurdle}, Sharpe > {min_sharpe_hurdle})."
        )
        return None

    # Fit final champion on full panel
    final_pipeline = candidate_pipeline.fit(df[features], df[target_col])

    metrics = {
        "target_horizon_days": horizon_days,
        "walk_forward_folds": len(folds),
        "validation_ic": round(aggregate_ic, 4),
        "validation_sharpe": round(aggregate_sharpe, 4),
        "aggregate_val_ic": round(aggregate_ic, 4),
        "aggregate_val_sharpe": round(aggregate_sharpe, 4),
        "fold_ics": [round(x, 4) for x in fold_ics],
        "fold_sharpes": [round(x, 4) for x in fold_sharpes],
        "algorithm": candidate_name,
        "pipeline": str(candidate_pipeline)
    }

    if registry_manager is None:
        registry_manager = ModelRegistryManager(db_manager)

    model_id = registry_manager.register_model(
        model_name=candidate_name,
        model_version="1.0.0",
        task_type="REGRESSION",
        artifact_pipeline=final_pipeline,
        metrics=metrics,
        status="CANDIDATE",
        target_horizon_days=horizon_days
    )

    promotion_success = registry_manager.promote_model(
        model_id=model_id,
        approved_by=f"MULTI_HORIZON_TOURNAMENT_{horizon_days}D",
        min_ic_hurdle=min_ic_hurdle
    )

    if promotion_success:
        logger.info(f"Successfully promoted {horizon_days}D champion model '{model_id}'.")
        return model_id
    else:
        logger.error(f"Promotion failed for {horizon_days}D model '{model_id}'.")
        return None
