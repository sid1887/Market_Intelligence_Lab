"""
Market Intelligence Lab — Milestone B4.2 Structured Multi-Factor Screener & Ranking Engine.

Executes deterministic multi-factor screening across the expanded equity universe
(NIFTY 50 active constituents + user trading watchlists).
Integrates technical moving averages, volatility, beta, and volume anomalies with
point-in-time fundamental ratios (TTM P/E, ROE %, Debt-to-Equity, OPM %).
Computes a normalized Composite Quality-Momentum score (0-100).
"""

import math
import datetime
import logging
from typing import Dict, Any, List, Optional, Union, Tuple

import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)


class FactorScreener:
    """
    Programmatic multi-factor screening and ranking engine.
    Queries quant_factors_daily and point-in-time fundamental and technical state
    as of any given trading session.
    """

    DEFAULT_QUALITY_MOMENTUM_WEIGHTS = {
        "roe": 0.30,
        "low_de": 0.25,
        "excess_ret_20d": 0.25,
        "opm": 0.20
    }

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    def get_benchmark_20d_return(
        self,
        as_of_date: str,
        index_name: str = "NIFTY 50",
        index_type: str = "PRI"
    ) -> Optional[float]:
        """
        Retrieves the trailing 20-session benchmark return as of as_of_date.
        Returns None if sufficient history is unavailable (P0-03, ADR-0004).
        """
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT trading_date, close
                FROM index_daily
                WHERE index_name = ? AND index_type = ? AND trading_date <= ?
                ORDER BY trading_date DESC
                LIMIT 21
                """,
                (index_name, index_type, as_of_date)
            )
            rows = cursor.fetchall()

        if len(rows) < 21:
            return None

        c_today = float(rows[0]["close"])
        c_20_ago = float(rows[20]["close"])
        return (c_today - c_20_ago) / c_20_ago if c_20_ago > 0 else None

    @staticmethod
    def _percentile_rank_series(series: pd.Series, ascending: bool = True) -> pd.Series:
        """
        Computes exact normalized percentile rank between 0.0 and 100.0 strictly over valid non-null rows.
        Missing values remain NaN — NEVER filled with 0.0 (P0-06, ADR-0007).
        """
        valid = series.dropna()
        if len(valid) == 0:
            return pd.Series(np.nan, index=series.index)
        if len(valid) == 1:
            return pd.Series(100.0, index=series.index).where(series.notna(), np.nan)

        ranks = valid.rank(ascending=ascending, method="average")
        n = len(valid)
        if n > 1:
            pct = ((ranks - 1.0) / (n - 1.0)) * 100.0
        else:
            pct = pd.Series(100.0, index=valid.index)

        # Preserve NaN for unobserved rows
        return pct.reindex(series.index)

    def calculate_composite_score(
        self,
        df: pd.DataFrame,
        weights: Optional[Dict[str, float]] = None,
        return_metadata: bool = False
    ) -> Union[pd.Series, Tuple[pd.Series, pd.Series, pd.Series]]:
        """
        Computes composite Quality-Momentum score normalized strictly between 0.0 and 100.0.
        Renormalizes valid weights if data_completeness >= 60%; sets score to NaN if completeness < 60%.
        """
        if df.empty:
            if return_metadata:
                return pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=object)
            return pd.Series(dtype=float)

        w = weights or self.DEFAULT_QUALITY_MOMENTUM_WEIGHTS
        w_roe = w.get("roe", 0.30)
        w_de = w.get("low_de", 0.25)
        w_excess = w.get("excess_ret_20d", 0.25)
        w_opm = w.get("opm", 0.20)
        nominal_total = w_roe + w_de + w_excess + w_opm

        # Percentile rank components across the universe strictly over non-nulls
        score_roe = self._percentile_rank_series(df["roe_pct"], ascending=True)
        score_de = self._percentile_rank_series(df["debt_to_equity"], ascending=False)
        score_excess = self._percentile_rank_series(df["excess_ret_20d"], ascending=True)
        score_opm = self._percentile_rank_series(df["opm_pct"], ascending=True)

        composites = []
        completeness_list = []
        status_list = []

        for idx in df.index:
            valid_w = 0.0
            weighted_sum = 0.0

            if pd.notna(score_roe.loc[idx]):
                valid_w += w_roe
                weighted_sum += w_roe * score_roe.loc[idx]

            if pd.notna(score_de.loc[idx]):
                valid_w += w_de
                weighted_sum += w_de * score_de.loc[idx]

            if pd.notna(score_excess.loc[idx]):
                valid_w += w_excess
                weighted_sum += w_excess * score_excess.loc[idx]

            if pd.notna(score_opm.loc[idx]):
                valid_w += w_opm
                weighted_sum += w_opm * score_opm.loc[idx]

            comp_pct = round((valid_w / nominal_total) * 100.0, 1)
            completeness_list.append(comp_pct)

            if comp_pct >= 60.0 and valid_w > 0:
                renorm_score = round(weighted_sum / valid_w, 2)
                composites.append(renorm_score)
                status_list.append("FULL_SCORE" if comp_pct == 100.0 else "PARTIAL_SCORE")
            else:
                composites.append(np.nan)
                status_list.append("INSUFFICIENT_DATA")

        comp_series = pd.Series(composites, index=df.index)
        if return_metadata:
            return (
                comp_series,
                pd.Series(completeness_list, index=df.index),
                pd.Series(status_list, index=df.index)
            )
        return comp_series

    def screen(
        self,
        as_of_date: str,
        criteria: Optional[Dict[str, Any]] = None,
        universe: Optional[List[str]] = None,
        include_watchlists: bool = True
    ) -> pd.DataFrame:
        """
        Performs point-in-time multi-factor screen on `as_of_date`.
        Returns a sorted pandas DataFrame ranked by composite Quality-Momentum score.

        Supported criteria filters:
        - Technical:
            - price_above_sma20: bool
            - price_above_sma50: bool
            - price_above_sma200: bool
            - max_volatility: float
            - max_beta: float
            - volume_spike_flag: bool
        - Fundamental:
            - max_debt_to_equity: float
            - min_roe_pct: float
            - max_ttm_pe: float
            - min_opm_pct: float
        - Universe / Sector:
            - exclude_sectors: List[str] or str
            - include_sectors: List[str] or str
            - is_watchlist_only: bool
            - min_price: float
            - max_price: float
        """
        # 1. Fetch universe factors as of as_of_date
        with self.db.get_connection() as conn:
            # Partitioned query: takes the latest available trading_date for each active instrument on or before as_of_date
            sql = """
            WITH latest_factors AS (
                SELECT *,
                       ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
                FROM quant_factors_daily
                WHERE (? IS NULL OR trading_date <= ?)
                  AND COALESCE(is_orphaned, 0) = 0
            )
            SELECT 
                q.symbol,
                q.trading_date,
                COALESCE(w.company_name, s.company_name, q.symbol) AS company_name,
                COALESCE(w.sector, s.sector, 'Unclassified') AS sector,
                o.close,
                q.sma_20,
                q.sma_50,
                q.sma_200,
                q.ret_1d,
                q.ret_5d,
                q.ret_20d,
                q.volatility_annualized,
                q.beta_60d_nifty,
                q.volume_ratio_20d,
                q.volume_zscore_50d,
                q.is_volume_spike_ratio,
                q.is_volume_spike_zscore,
                q.ttm_pe,
                q.roe_pct,
                q.debt_to_equity,
                q.opm_pct,
                CASE WHEN w.symbol IS NOT NULL THEN 1 ELSE 0 END AS is_watchlist
            FROM latest_factors q
            JOIN ohlcv_daily o 
              ON q.symbol = o.symbol AND q.trading_date = o.trading_date
            LEFT JOIN securities_master s 
              ON q.symbol = s.symbol
            LEFT JOIN user_watchlists w 
              ON q.symbol = w.symbol
            WHERE q.rn = 1
              AND o.series = 'EQ'
              AND COALESCE(o.is_synthetic, 0) = 0
              AND o.is_eligible_for_live_analytics = 1
            """
            params: List[Any] = [as_of_date, as_of_date]

            if not include_watchlists:
                sql += " AND (s.is_active = 1)"

            if universe:
                placeholders = ",".join("?" for _ in universe)
                sql += f" AND q.symbol IN ({placeholders})"
                params.extend(universe)

            sql += " ORDER BY q.symbol ASC;"
            df = pd.read_sql_query(sql, conn, params=params)

        if df.empty:
            return pd.DataFrame()

        # Coerce numeric columns from SQLite to float to safely handle NULLs/None
        numeric_cols = [
            "close", "sma_20", "sma_50", "sma_200", "ret_1d", "ret_5d", "ret_20d",
            "volatility_annualized", "beta_60d_nifty", "volume_ratio_20d",
            "volume_zscore_50d", "ttm_pe", "roe_pct", "debt_to_equity", "opm_pct"
        ]
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        # 2. Compute 20-day Excess Return vs Nifty 50 (P0-06: No fillna(0.0) on missing returns)
        nifty_ret_20d = self.get_benchmark_20d_return(as_of_date)
        if nifty_ret_20d is not None:
            df["excess_ret_20d"] = np.where(
                df["ret_20d"].notna(),
                (df["ret_20d"] - nifty_ret_20d).round(4),
                np.nan
            )
        else:
            df["excess_ret_20d"] = np.nan

        # 3. Compute Composite Quality-Momentum Score & Completeness across the universe
        comp_scores, completeness, statuses = self.calculate_composite_score(df, return_metadata=True)
        df["composite_score"] = comp_scores
        df["data_completeness_score"] = completeness
        df["score_status"] = statuses

        # 4. Helper boolean column for SMA comparison
        df["price_above_sma200"] = df["sma_200"].notna() & (df["close"] > df["sma_200"])
        df["price_above_sma50"] = df["sma_50"].notna() & (df["close"] > df["sma_50"])
        df["price_above_sma20"] = df["sma_20"].notna() & (df["close"] > df["sma_20"])

        # 5. Apply Filter Criteria
        if not criteria:
            return df.sort_values(by="composite_score", ascending=False).reset_index(drop=True)

        mask = pd.Series(True, index=df.index)

        # Technical Filters
        if criteria.get("price_above_sma20") is True:
            mask &= df["price_above_sma20"]

        if criteria.get("price_above_sma50") is True:
            mask &= df["price_above_sma50"]

        if criteria.get("price_above_sma200") is True:
            mask &= df["price_above_sma200"]

        if criteria.get("max_volatility") is not None:
            max_vol = float(criteria["max_volatility"])
            mask &= df["volatility_annualized"].notna() & (df["volatility_annualized"] <= max_vol)

        if criteria.get("max_beta") is not None:
            max_beta = float(criteria["max_beta"])
            mask &= df["beta_60d_nifty"].notna() & (df["beta_60d_nifty"] <= max_beta)

        if criteria.get("volume_spike_flag") is True:
            mask &= (df["is_volume_spike_ratio"] == 1) | (df["is_volume_spike_zscore"] == 1)

        # Fundamental Filters
        if criteria.get("max_debt_to_equity") is not None:
            max_de = float(criteria["max_debt_to_equity"])
            mask &= df["debt_to_equity"].notna() & (df["debt_to_equity"] <= max_de)

        if criteria.get("min_roe_pct") is not None:
            min_roe = float(criteria["min_roe_pct"])
            mask &= df["roe_pct"].notna() & (df["roe_pct"] >= min_roe)

        if criteria.get("max_ttm_pe") is not None:
            max_pe = float(criteria["max_ttm_pe"])
            mask &= df["ttm_pe"].notna() & (df["ttm_pe"] > 0) & (df["ttm_pe"] <= max_pe)

        if criteria.get("min_opm_pct") is not None:
            min_opm = float(criteria["min_opm_pct"])
            mask &= df["opm_pct"].notna() & (df["opm_pct"] >= min_opm)

        # Sector Exclusions & Inclusions
        exclude_sectors = criteria.get("exclude_sectors")
        if exclude_sectors:
            if isinstance(exclude_sectors, str):
                exclude_sectors = [exclude_sectors]
            for exc in exclude_sectors:
                exc_clean = exc.strip().lower()
                if "financial" in exc_clean or "bank" in exc_clean:
                    mask &= ~df["sector"].str.lower().str.contains(r"financial|bank", regex=True, na=False)
                else:
                    mask &= ~df["sector"].str.lower().str.contains(exc_clean, na=False)

        include_sectors = criteria.get("include_sectors")
        if include_sectors:
            if isinstance(include_sectors, str):
                include_sectors = [include_sectors]
            inc_mask = pd.Series(False, index=df.index)
            for inc in include_sectors:
                inc_clean = inc.strip().lower()
                inc_mask |= df["sector"].str.lower().str.contains(inc_clean, na=False)
            mask &= inc_mask

        # Watchlist restriction
        if criteria.get("is_watchlist_only") is True:
            mask &= (df["is_watchlist"] == 1)

        # Price boundaries
        if criteria.get("min_price") is not None:
            mask &= (df["close"] >= float(criteria["min_price"]))
        if criteria.get("max_price") is not None:
            mask &= (df["close"] <= float(criteria["max_price"]))

        filtered_df = df[mask].sort_values(by="composite_score", ascending=False).reset_index(drop=True)
        return filtered_df
