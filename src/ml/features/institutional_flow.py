"""
src/ml/features/institutional_flow.py
NSE Delivery Flow & Microstructure Accumulation Feature Engine.
MIL 2.0 Phase 7 Deliverable 1 (Alpha Research Track 1).

Specifications:
1. Session-Date Integrity:
   - Validates trading session dates chronologically per symbol.
   - Cleanly deduplicates session dates and filters holiday/weekend carryover artifacts.
2. deliv_zscore_60d:
   - Rolling 60-session Z-score of deliverable volume percentage.
   - Winsorized strictly to [-4.0, +4.0].
3. clv_1d & deliv_clv_impulse:
   - Close Location Value CLV_t = (Close_t - Low_t) / max(High_t - Low_t, epsilon), clamped to [0.0, 1.0].
   - Centered impulse: deliv_zscore_60d * (2.0 * clv_1d - 1.0), bounded to [-8.0, +8.0].
4. atpt_zscore_60d:
   - Average Rupee Turnover per Reported Trade (ATPT = turnover / max(trades_count, 1)).
   - Rolling 60-session Z-score, winsorized to [-4.0, +4.0], resilient to zero/missing trades.
5. fii_dii_delta_qoq & promoter_pledge_delta:
   - Point-in-time QoQ institutional (FII + DII) and promoter pledge deltas gated strictly
     by eligible_from_date <= trading_date.
"""

import logging
from typing import Optional, List, Dict, Any
import numpy as np
import pandas as pd

from src.quant.calendar import is_trading_session

logger = logging.getLogger("MIL.Features.InstitutionalFlow")

FLOW_FEATURE_COLUMNS = [
    "deliv_zscore_60d",
    "clv_1d",
    "deliv_clv_impulse",
    "atpt_zscore_60d",
    "fii_dii_delta_qoq",
    "promoter_pledge_delta"
]


def validate_and_clean_session_dates(
    df: pd.DataFrame,
    drop_non_trading: bool = False
) -> pd.DataFrame:
    """
    Validates, deduplicates, and sorts trading dates per symbol.
    If drop_non_trading is True, removes weekend and holiday artifacts.
    """
    if df.empty:
        return df.copy()

    required_cols = ["symbol", "trading_date"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column '{col}' in input DataFrame.")

    clean_df = df.copy()
    clean_df["trading_date"] = clean_df["trading_date"].astype(str).str.strip()

    # Drop invalid or empty dates
    clean_df = clean_df[clean_df["trading_date"].str.match(r"^\d{4}-\d{2}-\d{2}$")].copy()

    # Optionally filter out exchange holidays and weekends
    if drop_non_trading:
        valid_dates = {}
        for d in clean_df["trading_date"].unique():
            is_open, _ = is_trading_session(d)
            valid_dates[d] = is_open
        clean_df = clean_df[clean_df["trading_date"].map(valid_dates)].copy()

    # Sort chronologically and drop duplicate symbol-date entries
    clean_df = clean_df.sort_values(["symbol", "trading_date"]).drop_duplicates(
        subset=["symbol", "trading_date"],
        keep="last"
    ).reset_index(drop=True)

    return clean_df


def compute_delivery_percentage_series(df: pd.DataFrame) -> pd.Series:
    """
    Extracts or computes deliverable percentage normalized to [0.0, 100.0].
    Handles raw delivery_pct, deliv_pct (basis points or decimals), or delivery_qty / volume.
    """
    if "delivery_pct" in df.columns:
        s = pd.to_numeric(df["delivery_pct"], errors="coerce").fillna(0.0)
        # If in [0, 1] range, convert to percentage
        if s.max() <= 1.0 and s.max() > 0.0:
            s = s * 100.0
        return s.clip(0.0, 100.0)

    if "deliv_pct" in df.columns:
        s = pd.to_numeric(df["deliv_pct"], errors="coerce").fillna(0.0)
        # MilzArchive stores in bps (e.g. 5000 bps = 50.0%)
        if s.max() > 100.0:
            s = s / 100.0
        elif s.max() <= 1.0 and s.max() > 0.0:
            s = s * 100.0
        return s.clip(0.0, 100.0)

    if "delivery_qty" in df.columns and "volume" in df.columns:
        deliv = pd.to_numeric(df["delivery_qty"], errors="coerce").fillna(0.0)
        vol = pd.to_numeric(df["volume"], errors="coerce").fillna(0.0)
        safe_vol = np.maximum(vol.values, 1.0)
        pct = (deliv.values / safe_vol) * 100.0
        return pd.Series(np.clip(pct, 0.0, 100.0), index=df.index)

    # Fallback neutral 50%
    return pd.Series(50.0, index=df.index)


def calculate_institutional_flow_features(
    df: pd.DataFrame,
    shareholding_df: Optional[pd.DataFrame] = None,
    drop_non_trading: bool = False
) -> pd.DataFrame:
    """
    Computes NSE institutional delivery flow, CLV impulse, turnover-per-trade,
    and point-in-time shareholding deltas.

    Parameters:
        df: Daily OHLCV DataFrame with columns:
            ['symbol', 'trading_date', 'close', 'high', 'low']
            and optionally ['turnover', 'trades_count', 'delivery_pct'/'deliv_pct'/'delivery_qty', 'volume'].
        shareholding_df: Optional PIT shareholding pattern DataFrame with:
            ['symbol', 'period_end_date', 'eligible_from_date', 'fii_pct', 'dii_pct', 'promoter_pledged_pct'].
        drop_non_trading: Whether to drop holidays and weekends.

    Returns:
        DataFrame with ['symbol', 'trading_date'] + FLOW_FEATURE_COLUMNS.
    """
    if df.empty:
        return pd.DataFrame(columns=["symbol", "trading_date"] + FLOW_FEATURE_COLUMNS)

    clean_df = validate_and_clean_session_dates(df, drop_non_trading=drop_non_trading)

    # Ensure required numeric columns
    for col in ["close", "high", "low"]:
        if col in clean_df.columns:
            clean_df[col] = pd.to_numeric(clean_df[col], errors="coerce").fillna(0.0)
        else:
            clean_df[col] = 0.0

    # 1. Delivery percentage & Rolling 60d Z-score
    clean_df["_deliv_pct"] = compute_delivery_percentage_series(clean_df)

    def _calc_deliv_z(group: pd.Series) -> pd.Series:
        r_mean = group.rolling(60, min_periods=5).mean()
        r_std = group.rolling(60, min_periods=5).std().fillna(0.0)
        safe_std = np.maximum(r_std.values, 1e-4)
        z = (group.values - r_mean.values) / safe_std
        # Zero out when std was effectively zero or unobserved
        z = np.where(r_std.values < 1e-4, 0.0, z)
        return pd.Series(np.clip(np.nan_to_num(z, nan=0.0), -4.0, 4.0), index=group.index)

    clean_df["deliv_zscore_60d"] = (
        clean_df.groupby("symbol")["_deliv_pct"]
        .transform(_calc_deliv_z)
        .fillna(0.0)
        .astype(np.float32)
    )

    # 2. Close Location Value (CLV) & Centered Impulse
    high = clean_df["high"].values
    low = clean_df["low"].values
    close = clean_df["close"].values
    candle_range = high - low

    # If range <= 1e-5 (circuit lock or flat candle), neutral CLV = 0.5
    valid_range = candle_range > 1e-5
    clv = np.where(valid_range, (close - low) / np.maximum(candle_range, 1e-5), 0.5)
    clv = np.clip(clv, 0.0, 1.0)
    clean_df["clv_1d"] = clv.astype(np.float32)

    # Impulse: deliv_zscore_60d * (2.0 * clv_1d - 1.0), bounded to [-8.0, 8.0]
    impulse = clean_df["deliv_zscore_60d"].values * (2.0 * clv - 1.0)
    clean_df["deliv_clv_impulse"] = np.clip(np.nan_to_num(impulse, nan=0.0), -8.0, 8.0).astype(np.float32)

    # 3. Average Rupee Turnover Per Trade (ATPT) Rolling 60d Z-score
    if "turnover" in clean_df.columns and "trades_count" in clean_df.columns:
        turnover = pd.to_numeric(clean_df["turnover"], errors="coerce").fillna(0.0).values
        trades = pd.to_numeric(clean_df["trades_count"], errors="coerce").fillna(0.0).values
        safe_trades = np.maximum(trades, 1.0)
        has_trades = trades > 0
        atpt = np.where(has_trades, turnover / safe_trades, 0.0)
    elif "turnover" in clean_df.columns:
        atpt = pd.to_numeric(clean_df["turnover"], errors="coerce").fillna(0.0).values
    else:
        atpt = np.zeros(len(clean_df), dtype=float)

    clean_df["_atpt"] = atpt

    def _calc_atpt_z(group: pd.Series) -> pd.Series:
        if (group > 0).sum() < 5:
            return pd.Series(0.0, index=group.index)
        r_mean = group.rolling(60, min_periods=5).mean()
        r_std = group.rolling(60, min_periods=5).std().fillna(0.0)
        safe_std = np.maximum(r_std.values, 1e-4)
        z = (group.values - r_mean.values) / safe_std
        z = np.where(r_std.values < 1e-4, 0.0, z)
        return pd.Series(np.clip(np.nan_to_num(z, nan=0.0), -4.0, 4.0), index=group.index)

    clean_df["atpt_zscore_60d"] = (
        clean_df.groupby("symbol")["_atpt"]
        .transform(_calc_atpt_z)
        .fillna(0.0)
        .astype(np.float32)
    )

    # 4. Point-in-Time Shareholding Deltas (FII+DII QoQ & Promoter Pledge QoQ)
    if shareholding_df is not None and not shareholding_df.empty:
        clean_df = _merge_pit_shareholding_features(clean_df, shareholding_df)
    else:
        clean_df["fii_dii_delta_qoq"] = 0.0
        clean_df["promoter_pledge_delta"] = 0.0

    output_cols = ["symbol", "trading_date"] + FLOW_FEATURE_COLUMNS
    return clean_df[output_cols].copy()


def _merge_pit_shareholding_features(
    daily_df: pd.DataFrame,
    sh_df: pd.DataFrame
) -> pd.DataFrame:
    """
    Strictly merges shareholding filings point-in-time where eligible_from_date <= trading_date.
    Computes QoQ delta of institutional holdings (FII + DII) and promoter pledge percentage.
    """
    df_out = daily_df.copy()
    sh = sh_df.copy()

    # Normalize column names
    col_map = {
        "period_end": "period_end_date",
        "filing_date": "eligible_from_date",
        "publication_date": "eligible_from_date",
        "fii": "fii_pct",
        "dii": "dii_pct",
        "promoter_pledge": "promoter_pledged_pct",
        "pledged_pct": "promoter_pledged_pct"
    }
    sh = sh.rename(columns=col_map)

    if "eligible_from_date" not in sh.columns:
        if "period_end_date" in sh.columns:
            # Fallback SEBI LODR 21-day shareholding submission window
            sh["eligible_from_date"] = pd.to_datetime(sh["period_end_date"]) + pd.Timedelta(days=21)
            sh["eligible_from_date"] = sh["eligible_from_date"].dt.strftime("%Y-%m-%d")
        else:
            df_out["fii_dii_delta_qoq"] = 0.0
            df_out["promoter_pledge_delta"] = 0.0
            return df_out

    sh["symbol"] = sh["symbol"].astype(str).str.strip().str.upper()
    sh["eligible_from_date"] = sh["eligible_from_date"].astype(str).str.strip()
    sh = sh.sort_values(["symbol", "eligible_from_date"]).reset_index(drop=True)

    # Standardize holding numbers
    for col in ["fii_pct", "dii_pct", "promoter_pledged_pct"]:
        if col in sh.columns:
            sh[col] = pd.to_numeric(sh[col], errors="coerce").fillna(0.0)
        else:
            sh[col] = 0.0

    sh["inst_holding"] = sh["fii_pct"] + sh["dii_pct"]
    sh["fii_dii_delta_qoq"] = sh.groupby("symbol")["inst_holding"].diff().fillna(0.0)
    sh["promoter_pledge_delta"] = sh.groupby("symbol")["promoter_pledged_pct"].diff().fillna(0.0)

    # Point-in-time merge_asof per symbol
    merged_chunks = []
    sh_symbols = set(sh["symbol"].unique())

    for sym, sym_daily in df_out.groupby("symbol"):
        if sym not in sh_symbols:
            sym_daily = sym_daily.copy()
            sym_daily["fii_dii_delta_qoq"] = 0.0
            sym_daily["promoter_pledge_delta"] = 0.0
            merged_chunks.append(sym_daily)
            continue

        sym_sh = sh[sh["symbol"] == sym].sort_values("eligible_from_date").copy()
        sym_daily = sym_daily.sort_values("trading_date").copy()

        sym_daily["_dt_trading"] = pd.to_datetime(sym_daily["trading_date"])
        sym_sh["_dt_eligible"] = pd.to_datetime(sym_sh["eligible_from_date"])

        # Merge as-of on trading_date >= eligible_from_date
        merged_sym = pd.merge_asof(
            sym_daily,
            sym_sh[["_dt_eligible", "fii_dii_delta_qoq", "promoter_pledge_delta"]],
            left_on="_dt_trading",
            right_on="_dt_eligible",
            direction="backward"
        )
        merged_sym = merged_sym.drop(columns=["_dt_trading", "_dt_eligible"], errors="ignore")
        merged_sym["fii_dii_delta_qoq"] = merged_sym["fii_dii_delta_qoq"].fillna(0.0).astype(np.float32)
        merged_sym["promoter_pledge_delta"] = merged_sym["promoter_pledge_delta"].fillna(0.0).astype(np.float32)
        merged_chunks.append(merged_sym)

    if merged_chunks:
        df_out = pd.concat(merged_chunks, ignore_index=True)
    else:
        df_out["fii_dii_delta_qoq"] = 0.0
        df_out["promoter_pledge_delta"] = 0.0

    return df_out
