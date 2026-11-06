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
        LEFT JOIN ohlcv_daily o ON o.symbol = q.symbol AND o.trading_date = q.trading_date
        WHERE q.trading_date = ? {sym_clause}
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
        LEFT JOIN ohlcv_daily o ON o.symbol = q.symbol AND o.trading_date = q.trading_date
        WHERE q.trading_date >= ? AND q.trading_date <= ? {sym_clause}
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
