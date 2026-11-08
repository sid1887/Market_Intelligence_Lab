"""
src/ml/walk_forward_tournament.py
Expanding Walk-Forward Machine Learning Tournament Pipeline.

Trains, evaluates, and benchmarks multi-horizon alpha models across 4 expanding folds:
- Fold 1: Train 2020–2021 -> Test 2022
- Fold 2: Train 2020–2022 -> Test 2023
- Fold 3: Train 2020–2023 -> Test 2024
- Fold 4: Train 2020–2024 -> Test 2025–2026

Evaluates Candidate A (HistGradientBoostingRegressor) vs. Candidate B (Ridge L2) on
out-of-sample Spearman Information Coefficient (IC) for both Tactical (20D) and Trend (60D) targets.
Persists tournament summary to data/models/tournament_summary.json.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.linear_model import Ridge
from sklearn.preprocessing import RobustScaler

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.WalkForwardTournament")

FEATURE_COLUMNS = [
    "momentum_20d",
    "momentum_5d",
    "momentum_252d",
    "volatility_20d",
    "rsi_14",
    "sma_ratio_50_200",
    "operating_margin",
    "debt_to_equity",
]

FOLDS = [
    {"fold_id": 1, "train_end": "2021-12-31", "test_start": "2022-01-01", "test_end": "2022-12-31"},
    {"fold_id": 2, "train_end": "2022-12-31", "test_start": "2023-01-01", "test_end": "2023-12-31"},
    {"fold_id": 3, "train_end": "2023-12-31", "test_start": "2024-01-01", "test_end": "2024-12-31"},
    {"fold_id": 4, "train_end": "2024-12-31", "test_start": "2025-01-01", "test_end": "2026-11-30"},
]


class WalkForwardTournament:
    """
    Orchestrates expanding walk-forward tournaments across authentic historical factors.
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()
        self.output_dir = Path("data/models")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def load_feature_matrix(self) -> pd.DataFrame:
        """
        Loads aligned features and forward return targets across all active equities.
        """
        with self.db.get_connection() as conn:
            query = """
                SELECT 
                    f.symbol, f.trading_date, f.adj_close,
                    COALESCE(f.ret_20d, 0.0) as momentum_20d,
                    COALESCE(f.ret_5d, 0.0) as momentum_5d,
                    COALESCE(f.momentum_1y, 0.0) as momentum_252d,
                    COALESCE(f.volatility_20d, 25.0) as volatility_20d,
                    COALESCE(f.rsi_14, 50.0) as rsi_14,
                    f.sma_50, f.sma_200,
                    COALESCE(q.opm_pct, 15.0) as operating_margin,
                    COALESCE(q.debt_to_equity, 0.5) as debt_to_equity
                FROM factors_daily f
                LEFT JOIN quant_factors_daily q ON f.symbol = q.symbol AND f.trading_date = q.trading_date
                ORDER BY f.symbol, f.trading_date ASC
            """
            df = pd.read_sql_query(query, conn)

        # Log ratio of SMA 50 / SMA 200
        sma_ratio = np.where(
            (df["sma_50"] > 0) & (df["sma_200"] > 0),
            np.log(df["sma_50"] / df["sma_200"]),
            0.0
        )
        df["sma_ratio_50_200"] = np.nan_to_num(sma_ratio, nan=0.0)

        # Forward return targets per symbol
        df["target_20d"] = df.groupby("symbol")["adj_close"].shift(-20) / df["adj_close"] - 1.0
        df["target_60d"] = df.groupby("symbol")["adj_close"].shift(-60) / df["adj_close"] - 1.0

        return df

    def run_tournament(self) -> Dict[str, Any]:
        """
        Executes expanding walk-forward tournament across all 4 folds for 20D and 60D horizons.
        """
        logger.info("Loading feature matrix for walk-forward tournament...")
        df = self.load_feature_matrix()

        results: Dict[str, Any] = {
            "execution_timestamp": pd.Timestamp.now().isoformat(),
            "folds": [],
            "overall_summary": {}
        }

        horizons = [
            {"name": "TACTICAL_20D", "target_col": "target_20d", "horizon_days": 20},
            {"name": "TREND_60D", "target_col": "target_60d", "horizon_days": 60}
        ]

        hgb_ics_20, ridge_ics_20 = [], []
        hgb_ics_60, ridge_ics_60 = [], []
        feature_importances_accum = {f: 0.0 for f in FEATURE_COLUMNS}

        for fold in FOLDS:
            f_id = fold["fold_id"]
            train_mask = df["trading_date"] <= fold["train_end"]
            test_mask = (df["trading_date"] >= fold["test_start"]) & (df["trading_date"] <= fold["test_end"])

            df_train_raw = df[train_mask]
            df_test_raw = df[test_mask]

            fold_result: Dict[str, Any] = {
                "fold_id": f_id,
                "train_end": fold["train_end"],
                "test_window": f"{fold['test_start']} to {fold['test_end']}",
                "train_samples": len(df_train_raw),
                "test_samples": len(df_test_raw),
                "horizons": {}
            }

            for hz in horizons:
                hz_name = hz["name"]
                t_col = hz["target_col"]

                # Filter valid non-nan rows
                tr = df_train_raw.dropna(subset=[t_col] + FEATURE_COLUMNS).copy()
                te = df_test_raw.dropna(subset=[t_col] + FEATURE_COLUMNS).copy()

                if len(tr) < 100 or len(te) < 50:
                    continue

                X_tr = tr[FEATURE_COLUMNS].values
                y_tr = tr[t_col].values
                X_te = te[FEATURE_COLUMNS].values
                y_te = te[t_col].values

                # Cross-sectional RobustScaler
                scaler = RobustScaler()
                X_tr_scaled = scaler.fit_transform(X_tr)
                X_te_scaled = scaler.transform(X_te)

                # Candidate A: HistGradientBoostingRegressor
                hgb = HistGradientBoostingRegressor(
                    learning_rate=0.05,
                    max_depth=5,
                    min_samples_leaf=50,
                    random_state=42
                )
                hgb.fit(X_tr_scaled, y_tr)
                pred_hgb = hgb.predict(X_te_scaled)
                ic_hgb, _ = spearmanr(pred_hgb, y_te)

                # Candidate B: Ridge Regression (L2)
                ridge = Ridge(alpha=10.0)
                ridge.fit(X_tr_scaled, y_tr)
                pred_ridge = ridge.predict(X_te_scaled)
                ic_ridge, _ = spearmanr(pred_ridge, y_te)

                ic_hgb = float(np.nan_to_num(ic_hgb, nan=0.0))
                ic_ridge = float(np.nan_to_num(ic_ridge, nan=0.0))

                # Track metrics
                if hz_name == "TACTICAL_20D":
                    hgb_ics_20.append(ic_hgb)
                    ridge_ics_20.append(ic_ridge)
                    # Feature importance weights from Ridge coefficients as proxy
                    for idx, f in enumerate(FEATURE_COLUMNS):
                        feature_importances_accum[f] += abs(float(ridge.coef_[idx]))
                else:
                    hgb_ics_60.append(ic_hgb)
                    ridge_ics_60.append(ic_ridge)

                fold_result["horizons"][hz_name] = {
                    "hist_gradient_boosting_ic": round(ic_hgb, 4),
                    "ridge_ic": round(ic_ridge, 4),
                    "winner": "HistGradientBoosting" if ic_hgb >= ic_ridge else "Ridge"
                }

            results["folds"].append(fold_result)
            logger.info(f"Completed Fold {f_id}: {fold_result['horizons']}")

        # Overall summary
        mean_hgb_20 = float(np.mean(hgb_ics_20)) if hgb_ics_20 else 0.0
        mean_ridge_20 = float(np.mean(ridge_ics_20)) if ridge_ics_20 else 0.0
        mean_hgb_60 = float(np.mean(hgb_ics_60)) if hgb_ics_60 else 0.0
        mean_ridge_60 = float(np.mean(ridge_ics_60)) if ridge_ics_60 else 0.0

        # Normalize feature importances
        tot_imp = sum(feature_importances_accum.values()) or 1.0
        norm_importances = {k: round(v / tot_imp * 100.0, 2) for k, v in sorted(feature_importances_accum.items(), key=lambda x: x[1], reverse=True)}

        results["overall_summary"] = {
            "tactical_20d": {
                "hgb_mean_oos_ic": round(mean_hgb_20, 4),
                "ridge_mean_oos_ic": round(mean_ridge_20, 4),
                "champion": "HistGradientBoosting" if mean_hgb_20 >= mean_ridge_20 else "Ridge",
                "champion_ic": round(max(mean_hgb_20, mean_ridge_20), 4)
            },
            "trend_60d": {
                "hgb_mean_oos_ic": round(mean_hgb_60, 4),
                "ridge_mean_oos_ic": round(mean_ridge_60, 4),
                "champion": "HistGradientBoosting" if mean_hgb_60 >= mean_ridge_60 else "Ridge",
                "champion_ic": round(max(mean_hgb_60, mean_ridge_60), 4)
            },
            "feature_importance_pct": norm_importances
        }

        # Save to data/models/tournament_summary.json
        summary_path = self.output_dir / "tournament_summary.json"
        with open(summary_path, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)

        logger.info(f"Tournament summary written to {summary_path}")
        return results


if __name__ == "__main__":
    t = WalkForwardTournament()
    res = t.run_tournament()
    print(json.dumps(res, indent=2))
