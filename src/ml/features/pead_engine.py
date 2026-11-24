"""
src/ml/features/pead_engine.py
Point-in-Time Post-Earnings Announcement Drift (PEAD) Feature Engine.
MIL 2.0 Phase 7 Deliverable 2 (Alpha Research Track 1).

Specifications:
1. sue_eps:
   - Standardized Unexpected Earnings (Seasonal YoY EPS surprise):
     sue_eps = (EPS_q - EPS_{q-4}) / max(std(EPS_diff), 0.01), winsorized to [-5.0, +5.0].
2. opm_surprise_bps:
   - Operating margin YoY change in basis points:
     (OPM_q - OPM_{q-4}) * 10,000, bounded to [-5000.0, +5000.0] bps.
3. Strict Provenance Gating:
   - is_observed_pead = 1 strictly for filings with pit_provenance == 'OBSERVED_TIMESTAMP'.
   - Rows with STATUTORY_FALLBACK_LAG_* or imputed dates set is_observed_pead = 0 and
     pead_reaction_score = 0.0 to prevent artificial drift spikes on imputed dates.
4. pead_reaction_score:
   - Exponential decay: norm_sue * exp(-delta_t_sessions / 10.0) across 20 trading sessions [0, 20].
   - Strictly 0.0 outside [0, 20] sessions or when is_observed_pead == 0.
"""

import math
import logging
from typing import Optional, List, Dict, Any, Tuple
import numpy as np
import pandas as pd

from src.quant.disclosures import CorporateDisclosuresHandler
from src.quant.calendar import is_trading_session

logger = logging.getLogger("MIL.Features.PEAD")

PEAD_FEATURE_COLUMNS = [
    "sue_eps",
    "opm_surprise_bps",
    "is_observed_pead",
    "pead_reaction_score"
]


def resolve_effective_filing_session(
    pub_ts_str: Optional[str],
    provenance: str = "UNKNOWN"
) -> Tuple[Optional[str], int]:
    """
    Determines effective market reaction trading date (t=0) and whether it is an observed timestamp.
    Enforces:
    - If published > 15:30 IST or on weekend/holiday -> advances to next open trading session.
    - If pit_provenance is OBSERVED_TIMESTAMP -> is_observed = 1.
    - If STATUTORY_FALLBACK_LAG_* or unobserved -> is_observed = 0.
    """
    if not pub_ts_str or str(pub_ts_str).strip() in ("-", "", "None", "null"):
        return None, 0

    clean_ts = str(pub_ts_str).strip()
    is_observed = 1 if provenance == "OBSERVED_TIMESTAMP" else 0

    # Parse ISO timestamp or date
    iso_str, dt_ist = CorporateDisclosuresHandler.parse_broadcast_timestamp({"sort_date": clean_ts})
    if dt_ist is not None:
        eff_session = CorporateDisclosuresHandler.get_effective_session(dt_ist)
        return eff_session, is_observed

    # Date-only fallback: check if valid YYYY-MM-DD
    if len(clean_ts) >= 10 and clean_ts[:10].count("-") == 2:
        date_str = clean_ts[:10]
        # Check trading session
        is_open, _ = is_trading_session(date_str)
        if is_open:
            return date_str, is_observed
        # Advance to next open session
        next_d = pd.to_datetime(date_str) + pd.Timedelta(days=1)
        for _ in range(30):
            ns = next_d.strftime("%Y-%m-%d")
            is_open, _ = is_trading_session(ns)
            if is_open:
                return ns, is_observed
            next_d += pd.Timedelta(days=1)
        return date_str, is_observed

    return None, 0


def calculate_pead_features(
    ohlcv_df: pd.DataFrame,
    quarterly_fin_df: Optional[pd.DataFrame] = None
) -> pd.DataFrame:
    """
    Extracts and merges PIT PEAD features against daily OHLCV bars.

    Parameters:
        ohlcv_df: Daily DataFrame with ['symbol', 'trading_date'] and optional ['close', 'volume'].
        quarterly_fin_df: Quarterly financial filings with:
            ['symbol', 'period_end_date', 'eps']
            and at least one of ['published_at_ist', 'filing_date', 'broadcast_timestamp']
            plus optional ['pit_provenance', 'ebitda', 'revenue', 'operating_margin_pct'].

    Returns:
        DataFrame containing ['symbol', 'trading_date'] + PEAD_FEATURE_COLUMNS.
    """
    if ohlcv_df.empty:
        return pd.DataFrame(columns=["symbol", "trading_date"] + PEAD_FEATURE_COLUMNS)

    clean_ohlcv = ohlcv_df.copy()
    clean_ohlcv["trading_date"] = clean_ohlcv["trading_date"].astype(str).str.strip()
    clean_ohlcv["symbol"] = clean_ohlcv["symbol"].astype(str).str.strip().str.upper()
    clean_ohlcv = clean_ohlcv.sort_values(["symbol", "trading_date"]).reset_index(drop=True)

    if quarterly_fin_df is None or quarterly_fin_df.empty:
        clean_ohlcv["sue_eps"] = 0.0
        clean_ohlcv["opm_surprise_bps"] = 0.0
        clean_ohlcv["is_observed_pead"] = 0
        clean_ohlcv["pead_reaction_score"] = 0.0
        return clean_ohlcv[["symbol", "trading_date"] + PEAD_FEATURE_COLUMNS].copy()

    fin = quarterly_fin_df.copy()
    fin["symbol"] = fin["symbol"].astype(str).str.strip().str.upper()

    # Filter out carry-forward duplicate filings (provenance / status tags)
    if "pit_provenance" in fin.columns:
        fin = fin[fin["pit_provenance"] != "CARRY_FORWARD_DUPLICATE"].copy()
    if "data_status" in fin.columns:
        fin = fin[fin["data_status"] != "CARRY_FORWARD_DUPLICATE"].copy()
    if "is_carry_forward_duplicate" in fin.columns:
        fin = fin[~fin["is_carry_forward_duplicate"].astype(bool)].copy()

    # Detect and exclude consecutive identical (revenue, pat, eps_diluted) filings per symbol
    rev_col = next((c for c in ["revenue", "total_revenue", "revenue_operations"] if c in fin.columns), None)
    pat_col = next((c for c in ["net_profit", "pat"] if c in fin.columns), None)
    eps_col = next((c for c in ["eps_diluted", "diluted_eps", "eps", "basic_eps"] if c in fin.columns), None)

    if rev_col and pat_col and eps_col and "period_end_date" in fin.columns:
        fin = fin.sort_values(["symbol", "period_end_date"]).reset_index(drop=True)
        same_sym = fin["symbol"] == fin["symbol"].shift(1)
        r_curr = pd.to_numeric(fin[rev_col], errors="coerce").fillna(0.0).round(2)
        r_prev = pd.to_numeric(fin[rev_col].shift(1), errors="coerce").fillna(0.0).round(2)
        p_curr = pd.to_numeric(fin[pat_col], errors="coerce").fillna(0.0).round(2)
        p_prev = pd.to_numeric(fin[pat_col].shift(1), errors="coerce").fillna(0.0).round(2)
        e_curr = pd.to_numeric(fin[eps_col], errors="coerce").fillna(0.0).round(4)
        e_prev = pd.to_numeric(fin[eps_col].shift(1), errors="coerce").fillna(0.0).round(4)
        is_carry = same_sym & (r_curr == r_prev) & (p_curr == p_prev) & (e_curr == e_prev) & (r_curr != 0.0)
        fin = fin[~is_carry].copy()

    # Identify filing timestamp column
    ts_col = None
    for cand in ["published_at_ist", "broadcast_timestamp", "filing_date", "publication_date"]:
        if cand in fin.columns:
            ts_col = cand
            break

    if ts_col is None and "period_end_date" in fin.columns:
        # Fallback to statutory lag
        fin["_ts"] = pd.to_datetime(fin["period_end_date"]) + pd.Timedelta(days=45)
        fin["_ts"] = fin["_ts"].dt.strftime("%Y-%m-%d")
        ts_col = "_ts"
        if "pit_provenance" not in fin.columns:
            fin["pit_provenance"] = "STATUTORY_FALLBACK_LAG_45D"

    if "pit_provenance" not in fin.columns:
        fin["pit_provenance"] = "UNKNOWN"

    # Compute effective reaction date and observation flag
    effective_dates = []
    observed_flags = []
    for _, row in fin.iterrows():
        ts_val = row[ts_col]
        prov = str(row.get("pit_provenance", "UNKNOWN")).strip()
        eff_date, is_obs = resolve_effective_filing_session(ts_val, provenance=prov)
        effective_dates.append(eff_date)
        observed_flags.append(is_obs)

    fin["effective_trading_date"] = effective_dates
    fin["is_observed_pead"] = observed_flags

    # Drop filings with unresolvable dates
    fin = fin.dropna(subset=["effective_trading_date"]).copy()
    if fin.empty:
        clean_ohlcv["sue_eps"] = 0.0
        clean_ohlcv["opm_surprise_bps"] = 0.0
        clean_ohlcv["is_observed_pead"] = 0
        clean_ohlcv["pead_reaction_score"] = 0.0
        return clean_ohlcv[["symbol", "trading_date"] + PEAD_FEATURE_COLUMNS].copy()

    # Sort filings chronologically per symbol
    fin = fin.sort_values(["symbol", "period_end_date"]).reset_index(drop=True)

    # Compute EPS and OPM
    fin["eps"] = pd.to_numeric(fin["eps"], errors="coerce").fillna(0.0)

    # Operating Margin
    if "operating_margin_pct" in fin.columns:
        fin["opm"] = pd.to_numeric(fin["operating_margin_pct"], errors="coerce").fillna(0.0) / 100.0
    elif "ebitda" in fin.columns and "revenue" in fin.columns:
        ebitda = pd.to_numeric(fin["ebitda"], errors="coerce").fillna(0.0)
        rev = pd.to_numeric(fin["revenue"], errors="coerce").fillna(0.0)
        safe_rev = np.where(rev > 0, rev, 1.0)
        fin["opm"] = np.where(rev > 0, ebitda / safe_rev, 0.0)
    elif "net_profit" in fin.columns and "revenue" in fin.columns:
        np_val = pd.to_numeric(fin["net_profit"], errors="coerce").fillna(0.0)
        rev = pd.to_numeric(fin["revenue"], errors="coerce").fillna(0.0)
        safe_rev = np.where(rev > 0, rev, 1.0)
        fin["opm"] = np.where(rev > 0, np_val / safe_rev, 0.0)
    else:
        fin["opm"] = 0.0

    # YoY Seasonal Surprise (comparing with 4 quarters ago, q-4)
    fin["eps_yoy_diff"] = fin.groupby("symbol")["eps"].diff(4).fillna(0.0)
    fin["opm_yoy_diff"] = fin.groupby("symbol")["opm"].diff(4).fillna(0.0)

    # SUE: EPS surprise scaled by rolling std of EPS diffs
    def _calc_sue(group: pd.Series) -> pd.Series:
        r_std = group.expanding(min_periods=2).std().fillna(0.0)
        safe_std = np.maximum(r_std.values, 0.01)
        sue = group.values / safe_std
        return pd.Series(np.clip(np.nan_to_num(sue, nan=0.0), -5.0, 5.0), index=group.index)

    fin["sue_eps"] = (
        fin.groupby("symbol")["eps_yoy_diff"]
        .transform(_calc_sue)
        .fillna(0.0)
        .astype(np.float32)
    )

    # OPM surprise in basis points
    fin["opm_surprise_bps"] = np.clip(fin["opm_yoy_diff"].values * 10000.0, -5000.0, 5000.0).astype(np.float32)

    # Merge onto daily OHLCV panel
    result_dfs = []
    fin_symbols = set(fin["symbol"].unique())

    for sym, sym_daily in clean_ohlcv.groupby("symbol"):
        if sym not in fin_symbols:
            sym_daily = sym_daily.copy()
            sym_daily["sue_eps"] = 0.0
            sym_daily["opm_surprise_bps"] = 0.0
            sym_daily["is_observed_pead"] = 0
            sym_daily["pead_reaction_score"] = 0.0
            result_dfs.append(sym_daily)
            continue

        sym_daily = sym_daily.sort_values("trading_date").reset_index(drop=True)
        sym_fin = fin[fin["symbol"] == sym].sort_values("effective_trading_date").reset_index(drop=True)

        trading_dates = sym_daily["trading_date"].tolist()
        date_to_idx = {d: i for i, d in enumerate(trading_dates)}

        # Arrays to hold daily features
        sue_arr = np.zeros(len(sym_daily), dtype=np.float32)
        opm_arr = np.zeros(len(sym_daily), dtype=np.float32)
        is_obs_arr = np.zeros(len(sym_daily), dtype=np.int32)
        pead_score_arr = np.zeros(len(sym_daily), dtype=np.float32)

        # Apply filings in chronological order
        for _, f_row in sym_fin.iterrows():
            eff_d = str(f_row["effective_trading_date"])
            sue_val = float(f_row["sue_eps"])
            opm_bps = float(f_row["opm_surprise_bps"])
            is_obs = int(f_row["is_observed_pead"])

            # Find starting session index in sym_daily
            # Find first date >= eff_d
            start_indices = [idx for d, idx in date_to_idx.items() if d >= eff_d]
            if not start_indices:
                continue
            start_idx = min(start_indices)

            # Window of 20 trading sessions [start_idx, start_idx + 20]
            end_idx = min(len(sym_daily), start_idx + 21)

            for session_idx in range(start_idx, end_idx):
                delta_t = session_idx - start_idx
                decay = math.exp(-delta_t / 10.0)

                sue_arr[session_idx] = sue_val
                opm_arr[session_idx] = opm_bps
                is_obs_arr[session_idx] = is_obs

                # STRICT INVARIANT: If not observed timestamp (e.g. statutory lag), pead_reaction_score MUST BE 0.0
                if is_obs == 1:
                    norm_sue = max(-3.0, min(3.0, sue_val))
                    pead_score_arr[session_idx] = float(norm_sue * decay)
                else:
                    pead_score_arr[session_idx] = 0.0

            # Forward fill sue and opm beyond session 20 until next filing, but score decays to 0
            tail_start = min(len(sym_daily), start_idx + 21)
            for session_idx in range(tail_start, len(sym_daily)):
                sue_arr[session_idx] = sue_val
                opm_arr[session_idx] = opm_bps
                is_obs_arr[session_idx] = is_obs
                pead_score_arr[session_idx] = 0.0

        sym_daily["sue_eps"] = sue_arr
        sym_daily["opm_surprise_bps"] = opm_arr
        sym_daily["is_observed_pead"] = is_obs_arr
        sym_daily["pead_reaction_score"] = pead_score_arr

        result_dfs.append(sym_daily)

    final_df = pd.concat(result_dfs, ignore_index=True)
    return final_df[["symbol", "trading_date"] + PEAD_FEATURE_COLUMNS].copy()
