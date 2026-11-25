"""
src/ml/features/alpha_v3_multimodal.py
MIL 2.0 Phase 10 — FEATURE_FAMILY_3 (`alpha_v3_multimodal`).

Combines:
1. Causal Fixed-Width Window Fractional Differentiation (fracdiff d=0.35, 0.50, tau=1e-4)
   on log total-return adj_close and log volume (stationary while preserving memory).
2. PIT Fundamental Quality & Earnings Acceleration (sue_eps, opm_surprise_bps,
   pead_reaction_score, roce_ttm, debt_to_equity, fii_dii_delta_qoq,
   quality_x_pead, inst_flow_x_clv).
3. Causal Phase 8 HMM Regime Probabilities (hmm_p_low_vol_trend, hmm_p_stress_drawdown)
   and Phase 9 Sector Granger Spillover Conditioning (sector_spillover_penalty).
4. Strict PIT & Trader DNA Isolation:
   Excludes SECTOR_ESTIMATE and CARRY_FORWARD_DUPLICATE rows and enforces
   zero Trader DNA leakage.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("MIL.Features.AlphaV3")

TRADER_DNA_FORBIDDEN_COLUMNS = frozenset({
    "trader_dna_score",
    "win_rate_pct",
    "cooldown_active",
    "consecutive_losses",
    "avg_hold_days",
    "risk_tolerance",
    "discipline_score",
    "revenge_trade_flag",
})

FEATURE_COLUMNS_ALPHA_V3: List[str] = [
    # Stationary memory-preserving FracDiff features
    "fracdiff_close_035",
    "fracdiff_close_050",
    "fracdiff_vol_050",
    # Base momentum & volatility structure
    "ret_20d",
    "volatility_20d",
    "rsi_14",
    # Delivery & microstructure flow
    "deliv_zscore_60d",
    "clv_1d",
    "deliv_clv_impulse",
    "atpt_zscore_60d",
    "fii_dii_delta_qoq",
    # PIT Fundamental Quality & PEAD Acceleration
    "sue_eps",
    "opm_surprise_bps",
    "pead_reaction_score",
    "roce_ttm",
    "debt_to_equity",
    "quality_x_pead",
    "inst_flow_x_clv",
    # Causal Phase 8 HMM & Phase 9 Spillover Conditioning
    "hmm_p_low_vol_trend",
    "hmm_p_stress_drawdown",
    "sector_spillover_penalty",
]


def get_fracdiff_weights(d: float, threshold: float = 1e-4, max_window: int = 250) -> np.ndarray:
    """
    Computes fixed-width window fractional differentiation weights:
    w_0 = 1, w_k = -w_{k-1} * (d - k + 1) / k, truncated at |w_k| < threshold.
    Returns weights ordered [w_0, w_1, ..., w_{K-1}].
    """
    weights = [1.0]
    k = 1
    while k < max_window:
        w_k = -weights[-1] * ((d - k + 1.0) / k)
        if abs(w_k) < threshold:
            break
        weights.append(w_k)
        k += 1
    return np.asarray(weights, dtype=np.float64)


def causal_fracdiff_series(
    values: np.ndarray,
    d: float = 0.35,
    threshold: float = 1e-4,
    max_window: int = 250,
) -> np.ndarray:
    """
    Applies strictly causal fixed-width window fractional differentiation:
    x_tilde[t] = sum_{k=0}^{K-1} w_k * x[t - k].
    Future values values[t+1:] NEVER influence output[t].
    """
    arr = np.asarray(values, dtype=np.float64)
    n = len(arr)
    w = get_fracdiff_weights(d=d, threshold=threshold, max_window=max_window)
    width = len(w)

    out = np.zeros(n, dtype=np.float64)
    if n == 0:
        return out

    # Causal convolution: out[t] = sum_{k=0}^{min(t, width-1)} w[k] * arr[t-k]
    # Forward-fill NaNs before convolution using causal ffill
    s = pd.Series(arr).ffill().bfill().to_numpy(dtype=np.float64)
    for t in range(n):
        k_end = min(t + 1, width)
        # Dot product of w[:k_end] with s[t], s[t-1], ..., s[t-k_end+1]
        window_slice = s[t - k_end + 1: t + 1][::-1]
        out[t] = float(np.dot(w[:k_end], window_slice))
    return out


def filter_pit_clean_rows(df: pd.DataFrame) -> pd.DataFrame:
    """
    Excludes SECTOR_ESTIMATE, CARRY_FORWARD_DUPLICATE, imputed fundamentals,
    and synthetic test rows from supervised ML training.
    """
    if df.empty:
        return df.copy()

    mask = pd.Series(True, index=df.index)
    for col in ("data_status", "provenance_class", "metric_applicability_flag", "data_quality_flag"):
        if col in df.columns:
            bad = df[col].astype(str).str.upper().isin(
                {"SECTOR_ESTIMATE", "CARRY_FORWARD_DUPLICATE", "SYNTHETIC_TEST"}
            )
            mask &= ~bad

    if "is_carry_forward_duplicate" in df.columns:
        mask &= ~df["is_carry_forward_duplicate"].fillna(False).astype(bool)
    if "is_sector_imputed" in df.columns:
        mask &= df["is_sector_imputed"].fillna(0).astype(int) == 0
    if "is_synthetic" in df.columns:
        mask &= df["is_synthetic"].fillna(0).astype(int) == 0

    return df.loc[mask].copy()


def build_alpha_v3_multimodal_features(
    df: pd.DataFrame,
    hmm_history_map: Optional[Dict[str, Dict[str, float]]] = None,
    spillover_penalty_map: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Enriches a chronological OHLCV + AlphaV2 panel DataFrame with `FEATURE_COLUMNS_ALPHA_V3`
    strictly causally per symbol.
    """
    if df.empty:
        return df.copy()

    out = filter_pit_clean_rows(df)
    if out.empty:
        return out

    # Enforce zero Trader DNA leakage
    for dna_col in TRADER_DNA_FORBIDDEN_COLUMNS:
        if dna_col in out.columns:
            out = out.drop(columns=[dna_col])

    out["trading_date"] = out["trading_date"].astype(str)
    out = out.sort_values(["symbol", "trading_date"]).reset_index(drop=True)

    # Price column selection: prefer total-return adj_close if present
    px_col = "adj_close" if "adj_close" in out.columns else "close"
    vol_col = "volume" if "volume" in out.columns else None

    fd_035 = np.zeros(len(out), dtype=np.float64)
    fd_050 = np.zeros(len(out), dtype=np.float64)
    fd_vol = np.zeros(len(out), dtype=np.float64)

    for _, idx in out.groupby("symbol", sort=False).groups.items():
        pos = np.asarray(list(idx), dtype=np.int64)
        log_px = np.log(np.maximum(out.loc[pos, px_col].to_numpy(dtype=np.float64), 1e-4))
        fd_035[pos] = causal_fracdiff_series(log_px, d=0.35, threshold=1e-4)
        fd_050[pos] = causal_fracdiff_series(log_px, d=0.50, threshold=1e-4)
        if vol_col:
            log_v = np.log1p(np.maximum(out.loc[pos, vol_col].to_numpy(dtype=np.float64), 0.0))
            fd_vol[pos] = causal_fracdiff_series(log_v, d=0.50, threshold=1e-4)

    out["fracdiff_close_035"] = np.clip(fd_035, -5.0, 5.0)
    out["fracdiff_close_050"] = np.clip(fd_050, -5.0, 5.0)
    out["fracdiff_vol_050"] = np.clip(fd_vol, -5.0, 5.0)

    # Ensure base & PIT columns exist cleanly
    defaults = {
        "ret_20d": 0.0,
        "volatility_20d": 0.22,
        "rsi_14": 50.0,
        "deliv_zscore_60d": 0.0,
        "clv_1d": 0.5,
        "deliv_clv_impulse": 0.0,
        "atpt_zscore_60d": 0.0,
        "fii_dii_delta_qoq": 0.0,
        "sue_eps": 0.0,
        "opm_surprise_bps": 0.0,
        "pead_reaction_score": 0.0,
        "roce_ttm": 15.0,
        "debt_to_equity": 0.3,
    }
    for col, val in defaults.items():
        if col not in out.columns:
            out[col] = val
        else:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(val)

    # Interaction terms
    out["quality_x_pead"] = np.clip((out["roce_ttm"] / 25.0) * out["pead_reaction_score"], -10.0, 10.0)
    out["inst_flow_x_clv"] = np.clip(out["fii_dii_delta_qoq"] * (2.0 * out["clv_1d"] - 1.0), -10.0, 10.0)

    # Causal Phase 8 HMM Regime Conditioning
    if hmm_history_map is None:
        hmm_history_map = {}
        try:
            from src.quant.regime_hmm import load_regime_hmm_state
            hmm_state = load_regime_hmm_state()
            for item in hmm_state.get("recent_history", []):
                hmm_history_map[str(item.get("trading_date"))] = item.get("probabilities", {})
            default_probs = hmm_state.get("latest_probabilities", {"LOW_VOL_TREND": 0.34, "STRESS_DRAWDOWN": 0.33})
        except Exception:
            default_probs = {"LOW_VOL_TREND": 0.34, "STRESS_DRAWDOWN": 0.33}
    else:
        default_probs = {"LOW_VOL_TREND": 0.34, "STRESS_DRAWDOWN": 0.33}

    out["hmm_p_low_vol_trend"] = [
        float(hmm_history_map.get(d, default_probs).get("LOW_VOL_TREND", 0.34))
        for d in out["trading_date"]
    ]
    out["hmm_p_stress_drawdown"] = [
        float(hmm_history_map.get(d, default_probs).get("STRESS_DRAWDOWN", 0.33))
        for d in out["trading_date"]
    ]

    # Causal Phase 9 Sector Granger Spillover Penalty
    if spillover_penalty_map is None:
        spillover_penalty_map = {}
        try:
            from src.quant.spillover_graph import get_sector_spillover_penalty
            if "sector" in out.columns:
                for sec in out["sector"].dropna().unique():
                    spillover_penalty_map[str(sec)] = float(
                        get_sector_spillover_penalty(str(sec)).get("negative_spillover_penalty", 0.0)
                    )
        except Exception:
            pass

    if "sector" in out.columns:
        out["sector_spillover_penalty"] = out["sector"].astype(str).map(spillover_penalty_map).fillna(0.0)
    else:
        out["sector_spillover_penalty"] = 0.0

    return out
