"""
Market Intelligence Lab — Point-In-Time Feature Extractor (Stage A1).
Builds strictly point-in-time features with deterministic hashing and zero lookahead bias.
"""

import hashlib
import json
import logging
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "ret_1d",
    "ret_5d",
    "ret_20d",
    "vol_20d",
    "dist_sma20",
    "dist_sma50",
    "dist_sma200",
    "vol_ratio_20d",
    "beta_60d",
    "roe_pct",
    "debt_to_equity",
    "opm_pct",
    "completeness_score",
]


def compute_features_hash(features_dict: Dict[str, Any]) -> str:
    """Computes a deterministic SHA-256 hash across sorted feature key-value pairs."""
    clean_dict = {}
    for k, v in sorted(features_dict.items()):
        if isinstance(v, (float, np.floating)):
            clean_dict[k] = None if np.isnan(v) else round(float(v), 6)
        else:
            clean_dict[k] = v
    payload = json.dumps(clean_dict, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def purge_and_embargo(
    df: pd.DataFrame,
    test_start_date: str,
    test_end_date: str,
    calendar: Optional[List[str]] = None,
    horizon_sessions: int = 20,
    embargo_sessions: int = 5
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Purges overlapping forward return labels from training sets and embargos post-test observations
    to eliminate cross-contamination and autocorrelation leakage (Advances in Financial Machine Learning).
    
    1. Purge: Drops train samples whose forward evaluation window [t, t + horizon] extends into test_start_date.
    2. Embargo: Prevents samples within embargo_sessions immediately following test_end_date from entering train.
    """
    if df.empty or "trading_date" not in df.columns:
        return df.copy(), pd.DataFrame()

    # Split into test and non-test
    test_mask = (df["trading_date"] >= test_start_date) & (df["trading_date"] <= test_end_date)
    test_df = df[test_mask].copy()

    # Training candidates: strictly before test_start_date (expanding window)
    train_candidate_mask = df["trading_date"] < test_start_date
    train_df = df[train_candidate_mask].copy()

    if calendar and horizon_sessions > 0:
        date_to_idx = {d: i for i, d in enumerate(calendar)}
        if test_start_date in date_to_idx:
            test_start_idx = date_to_idx[test_start_date]
            # Drop any train date where idx + horizon_sessions >= test_start_idx
            valid_train_dates = set()
            for d in train_df["trading_date"].unique():
                if d in date_to_idx:
                    d_idx = date_to_idx[d]
                    if (d_idx + horizon_sessions) < test_start_idx:
                        valid_train_dates.add(d)
            train_df = train_df[train_df["trading_date"].isin(valid_train_dates)].copy()

    return train_df, test_df


class PITFeatureExtractor:
    """Extracts strictly point-in-time technical and fundamental features as of session T."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def extract_features_for_session(
        self,
        trading_date: str,
        symbols: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Extracts feature matrix for all active symbols as of trading_date.
        All inputs are guaranteed <= trading_date.
        """
        sym_clause = ""
        params: List[Any] = [trading_date]
        if symbols:
            placeholders = ",".join(["?"] * len(symbols))
            sym_clause = f"AND q.symbol IN ({placeholders})"
            params.extend(symbols)

        sql = f"""
        SELECT 
            q.symbol,
            q.trading_date,
            o.close,
            q.ret_1d,
            q.ret_5d,
            q.ret_20d,
            COALESCE(q.vol_20d_annualized, q.volatility_annualized) as vol_20d,
            q.sma_20,
            q.sma_50,
            q.sma_200,
            q.volume_ratio_20d as vol_ratio_20d,
            q.beta_60d_nifty as beta_60d,
            q.roe_pct,
            q.debt_to_equity,
            q.opm_pct
        FROM quant_factors_daily q
        JOIN ohlcv_daily o ON o.symbol = q.symbol AND o.trading_date = q.trading_date
        WHERE q.trading_date = ? 
          AND o.series = 'EQ'
          AND COALESCE(q.is_orphaned, 0) = 0
          AND COALESCE(o.is_synthetic, 0) = 0
          AND o.is_eligible_for_training = 1
          {sym_clause}
        """

        with self.db.get_connection() as conn:
            cur = conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            return pd.DataFrame(columns=["symbol", "trading_date"] + FEATURE_COLUMNS + ["features_hash"])

        df = pd.DataFrame(rows)

        # Distance to moving averages
        df["dist_sma20"] = np.where(df["sma_20"].notna() & (df["sma_20"] > 0), (df["close"] - df["sma_20"]) / df["sma_20"], np.nan)
        df["dist_sma50"] = np.where(df["sma_50"].notna() & (df["sma_50"] > 0), (df["close"] - df["sma_50"]) / df["sma_50"], np.nan)
        df["dist_sma200"] = np.where(df["sma_200"].notna() & (df["sma_200"] > 0), (df["close"] - df["sma_200"]) / df["sma_200"], np.nan)

        # Completeness score (fraction of non-null core features)
        check_cols = ["ret_20d", "vol_20d", "dist_sma200", "roe_pct", "debt_to_equity", "opm_pct"]
        df["completeness_score"] = df[check_cols].notna().mean(axis=1)

        # Generate feature hashes
        hashes = []
        for _, row in df.iterrows():
            feat_subset = {c: row[c] for c in FEATURE_COLUMNS if c in row}
            hashes.append(compute_features_hash(feat_subset))
        df["features_hash"] = hashes

        return df[["symbol", "trading_date"] + FEATURE_COLUMNS + ["features_hash"]]

    def extract_panel(
        self,
        start_date: str,
        end_date: str,
        symbols: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """Extracts multi-session feature panel strictly across trading sessions in [start_date, end_date]."""
        sym_clause = ""
        params: List[Any] = [start_date, end_date]
        if symbols:
            placeholders = ",".join(["?"] * len(symbols))
            sym_clause = f"AND q.symbol IN ({placeholders})"
            params.extend(symbols)

        sql = f"""
        SELECT 
            q.symbol,
            q.trading_date,
            o.close,
            q.ret_1d,
            q.ret_5d,
            q.ret_20d,
            COALESCE(q.vol_20d_annualized, q.volatility_annualized) as vol_20d,
            q.sma_20,
            q.sma_50,
            q.sma_200,
            q.volume_ratio_20d as vol_ratio_20d,
            q.beta_60d_nifty as beta_60d,
            q.roe_pct,
            q.debt_to_equity,
            q.opm_pct
        FROM quant_factors_daily q
        JOIN ohlcv_daily o ON o.symbol = q.symbol AND o.trading_date = q.trading_date
        WHERE q.trading_date >= ? AND q.trading_date <= ?
          AND o.series = 'EQ'
          AND COALESCE(q.is_orphaned, 0) = 0
          AND COALESCE(o.is_synthetic, 0) = 0
          AND o.is_eligible_for_training = 1
          {sym_clause}
        ORDER BY q.trading_date ASC, q.symbol ASC
        """

        with self.db.get_connection() as conn:
            cur = conn.execute(sql, params)
            rows = [dict(r) for r in cur.fetchall()]

        if not rows:
            return pd.DataFrame(columns=["symbol", "trading_date"] + FEATURE_COLUMNS + ["features_hash"])

        df = pd.DataFrame(rows)
        df["dist_sma20"] = np.where(df["sma_20"].notna() & (df["sma_20"] > 0), (df["close"] - df["sma_20"]) / df["sma_20"], np.nan)
        df["dist_sma50"] = np.where(df["sma_50"].notna() & (df["sma_50"] > 0), (df["close"] - df["sma_50"]) / df["sma_50"], np.nan)
        df["dist_sma200"] = np.where(df["sma_200"].notna() & (df["sma_200"] > 0), (df["close"] - df["sma_200"]) / df["sma_200"], np.nan)

        check_cols = ["ret_20d", "vol_20d", "dist_sma200", "roe_pct", "debt_to_equity", "opm_pct"]
        df["completeness_score"] = df[check_cols].notna().mean(axis=1)

        hashes = []
        for _, row in df.iterrows():
            feat_subset = {c: row[c] for c in FEATURE_COLUMNS if c in row}
            hashes.append(compute_features_hash(feat_subset))
        df["features_hash"] = hashes

        return df[["symbol", "trading_date"] + FEATURE_COLUMNS + ["features_hash"]]
