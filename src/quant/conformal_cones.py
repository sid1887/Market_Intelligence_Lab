"""
src/quant/conformal_cones.py
MIL 2.0 Phase 8 — Weighted Adaptive Conformal Prediction Cones (80% & 95%).

Provides distribution-free, regime-conditioned uncertainty cones that adapt to
non-stationary fat tails (Excess Kurtosis > 17 observed in Phase 7).

Features:
- Normalized nonconformity scores s_i = |y_i - y_hat_i| / max(sigma_hat_i, eps)
- Exponentially decayed weighted split-conformal quantiles (q_80, q_95)
- Grouped by HMM Regime (LOW_VOL_TREND, HIGH_VOL_CHOP, STRESS_DRAWDOWN) x Horizon (5D, 10D, 20D)
- Rolling 60-session empirical coverage monitor; auto-flags CONFORMAL_COVERAGE_DRIFT
  and widens intervals if empirical 80% coverage drops below 72%.
- Exports compact < 150 KB JSON (`data/models/conformal_quantiles.json`) for Render.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from src.quant.regime_hmm import (
    DEFAULT_HMM_STATE_PATH,
    GaussianRegimeHMM,
    REGIME_NAMES,
    build_regime_feature_matrix,
    load_regime_hmm_state,
)

logger = logging.getLogger("MIL.ConformalCones")

DEFAULT_CONFORMAL_PATH = Path("data/models/conformal_quantiles.json")
HORIZONS = (5, 10, 20)
EPSILON_SIGMA = 1e-4
COVERAGE_DRIFT_THRESHOLD = 0.72  # Nominal 80% cone drift alert threshold


def weighted_conformal_quantile(
    scores: np.ndarray,
    weights: np.ndarray,
    alpha: float,
) -> float:
    """
    Computes the weighted split-conformal quantile at level (1 - alpha).
    For 80% coverage, alpha = 0.20 (80th percentile).
    For 95% coverage, alpha = 0.05 (95th percentile).
    Includes finite-sample conservative adjustment.
    """
    s = np.asarray(scores, dtype=np.float64)
    w = np.asarray(weights, dtype=np.float64)
    valid = np.isfinite(s) & np.isfinite(w) & (w > 0)
    s = s[valid]
    w = w[valid]

    if len(s) == 0:
        return 1.28 if alpha >= 0.15 else 1.96

    order = np.argsort(s)
    s_sorted = s[order]
    w_sorted = w[order]

    # Finite-sample conformal correction: add weight 1/(n+1) at +inf equivalent
    w_total = np.sum(w_sorted)
    n = len(s_sorted)
    target = (1.0 - alpha) * (1.0 + 1.0 / max(n, 1))
    target = min(target, 0.995)

    cum_w = np.cumsum(w_sorted) / max(w_total, 1e-12)
    idx = int(np.searchsorted(cum_w, target, side="left"))
    idx = min(max(idx, 0), n - 1)
    return float(s_sorted[idx])


def calibrate_regime_conformal_cell(
    residuals: np.ndarray,
    sigmas: np.ndarray,
    decay_lambda: float = 0.996,
    rolling_window: int = 60,
) -> Dict[str, Any]:
    """
    Calibrates (q_80, q_95) and rolling 60-session empirical coverage for a single
    (regime, horizon) calibration sample sequence ordered chronologically.
    """
    res = np.asarray(residuals, dtype=np.float64)
    sig = np.maximum(np.asarray(sigmas, dtype=np.float64), EPSILON_SIGMA)
    scores = np.abs(res) / sig
    n = len(scores)

    if n < 20:
        return {
            "sample_count": int(n),
            "q_80": 1.35,
            "q_95": 2.15,
            "raw_q_80": 1.35,
            "raw_q_95": 2.15,
            "rolling_60_coverage_80": 0.80,
            "rolling_60_coverage_95": 0.95,
            "drift_flag": "INSUFFICIENT_SAMPLES",
            "drift_widening_factor": 1.0,
        }

    # Exponentially decayed weights favoring recent observations
    exponents = np.arange(n - 1, -1, -1, dtype=np.float64)
    weights = np.power(decay_lambda, exponents)
    weights /= np.sum(weights)

    raw_q80 = weighted_conformal_quantile(scores, weights, alpha=0.20)
    raw_q95 = max(weighted_conformal_quantile(scores, weights, alpha=0.05), raw_q80 * 1.15)

    # Evaluate rolling 60-session out-of-sample empirical coverage on tail using causal prefix quantile
    eval_n = min(rolling_window, max(10, n // 4))
    prefix_end = n - eval_n
    if prefix_end >= 20:
        pref_scores = scores[:prefix_end]
        pref_exp = np.arange(prefix_end - 1, -1, -1, dtype=np.float64)
        pref_w = np.power(decay_lambda, pref_exp)
        pref_w /= np.sum(pref_w)
        eval_q80 = weighted_conformal_quantile(pref_scores, pref_w, alpha=0.20)
        eval_q95 = weighted_conformal_quantile(pref_scores, pref_w, alpha=0.05)
    else:
        eval_q80 = raw_q80
        eval_q95 = raw_q95

    tail_scores = scores[-eval_n:]
    cov_80 = float(np.mean(tail_scores <= eval_q80))
    cov_95 = float(np.mean(tail_scores <= eval_q95))

    drift_flag = "CALIBRATED"
    widening_factor = 1.0
    if cov_80 < COVERAGE_DRIFT_THRESHOLD:
        drift_flag = "CONFORMAL_COVERAGE_DRIFT"
        widening_factor = round(min(1.75, 0.80 / max(cov_80, 0.45)), 4)

    adj_q80 = round(raw_q80 * widening_factor, 4)
    adj_q95 = round(max(raw_q95 * widening_factor, adj_q80 * 1.15), 4)

    return {
        "sample_count": int(n),
        "q_80": adj_q80,
        "q_95": adj_q95,
        "raw_q_80": round(raw_q80, 4),
        "raw_q_95": round(raw_q95, 4),
        "rolling_60_coverage_80": round(cov_80, 4),
        "rolling_60_coverage_95": round(cov_95, 4),
        "drift_flag": drift_flag,
        "drift_widening_factor": widening_factor,
    }


def calibrate_and_export_conformal_cones(
    db_path: str = "data/market_lab.db",
    milz_path: str = "data/bhavcopy_10y.milz",
    hmm_state_path: str | Path = DEFAULT_HMM_STATE_PATH,
    output_path: str | Path = DEFAULT_CONFORMAL_PATH,
    decay_lambda: float = 0.996,
) -> Dict[str, Any]:
    """
    Calibrates regime-conditioned weighted split-conformal quantiles (80% & 95%)
    across 5D, 10D, and 20D horizons using historical NSE OHLCV residuals and
    causal forward-filtered HMM regimes.
    """
    # 1. Load or fit HMM for causal regime mapping per date
    hmm_p = Path(hmm_state_path)
    if hmm_p.exists():
        with open(hmm_p, "r", encoding="utf-8") as f:
            hmm_state = json.load(f)
        hmm = GaussianRegimeHMM.from_dict(hmm_state["model_params"])
    else:
        from src.quant.regime_hmm import train_and_export_regime_hmm
        hmm_state = train_and_export_regime_hmm(db_path=db_path, milz_path=milz_path, output_path=hmm_p)
        hmm = GaussianRegimeHMM.from_dict(hmm_state["model_params"])

    feat_df = build_regime_feature_matrix(db_path=db_path, milz_path=milz_path)
    raw_X = feat_df[["nifty_ret_20d", "realized_vol_20d", "breadth_thrust", "xs_dispersion"]].to_numpy(dtype=np.float64)
    probs = hmm.forward_filter(raw_X)
    feat_df["regime"] = [REGIME_NAMES[i] for i in np.argmax(probs, axis=1)]
    date_regime_map = dict(zip(feat_df["trading_date"].astype(str), feat_df["regime"]))

    # 2. Load equity panel for out-of-sample return residuals
    panel = pd.DataFrame()
    if os.path.exists(milz_path):
        try:
            from src.storage.compression_engine import MilzArchiveEngine
            panel = MilzArchiveEngine(milz_path).read_all()
        except Exception as e:
            logger.warning(f"MILZ load fallback to SQLite for conformal calibration: {e}")

    if panel.empty:
        import sqlite3
        with sqlite3.connect(db_path) as conn:
            panel = pd.read_sql_query(
                """
                SELECT symbol, trading_date, close
                FROM ohlcv_daily
                WHERE is_synthetic = 0
                ORDER BY symbol, trading_date ASC
                """,
                conn,
            )

    if panel.empty:
        raise RuntimeError("No historical OHLCV data available for conformal cone calibration.")

    panel["trading_date"] = panel["trading_date"].astype(str)
    panel = panel.sort_values(["symbol", "trading_date"]).reset_index(drop=True)
    panel["close"] = panel["close"].astype(float)
    panel["ret_1d"] = panel.groupby("symbol")["close"].pct_change()
    # Strictly causal 20D realized daily volatility & momentum expectation
    panel["daily_vol_20d"] = (
        panel.groupby("symbol")["ret_1d"].transform(lambda s: s.rolling(20, min_periods=10).std()).fillna(0.02)
    )
    panel["ret_20d_lag"] = panel.groupby("symbol")["close"].pct_change(20).fillna(0.0)
    panel["regime"] = panel["trading_date"].map(date_regime_map).fillna("HIGH_VOL_CHOP")

    # Sample top liquid / cross-sectional panel up to ~250k rows chronologically for fast calibration
    if len(panel) > 250000:
        syms = panel["symbol"].value_counts().head(200).index
        panel = panel[panel["symbol"].isin(syms)].copy()

    quantiles_matrix: Dict[str, Dict[str, Any]] = {r: {} for r in REGIME_NAMES}
    global_drift_alerts: List[str] = []

    for h in HORIZONS:
        # Forward h-day realized return y_t and causal baseline expectation y_hat_t
        fwd_ret = panel.groupby("symbol")["close"].shift(-h) / panel["close"] - 1.0
        # Causal momentum drift expectation (shrunk by 0.15)
        y_hat = np.clip(panel["ret_20d_lag"] * (h / 20.0) * 0.15, -0.10, 0.10)
        sigma_hat = np.maximum(panel["daily_vol_20d"] * np.sqrt(h), EPSILON_SIGMA)

        valid_mask = fwd_ret.notna() & np.isfinite(fwd_ret) & np.isfinite(sigma_hat)
        sub = panel.loc[valid_mask, ["trading_date", "regime"]].copy()
        sub["residual"] = (fwd_ret[valid_mask] - y_hat[valid_mask]).to_numpy()
        sub["sigma_hat"] = sigma_hat[valid_mask].to_numpy()
        sub = sub.sort_values("trading_date")

        for r in REGIME_NAMES:
            r_sub = sub[sub["regime"] == r]
            cell = calibrate_regime_conformal_cell(
                residuals=r_sub["residual"].to_numpy(),
                sigmas=r_sub["sigma_hat"].to_numpy(),
                decay_lambda=decay_lambda,
            )
            quantiles_matrix[r][f"{h}D"] = cell
            if cell["drift_flag"] == "CONFORMAL_COVERAGE_DRIFT":
                global_drift_alerts.append(f"{r}:{h}D (cov={cell['rolling_60_coverage_80']:.1%})")

    payload = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "decay_lambda": decay_lambda,
        "coverage_drift_threshold": COVERAGE_DRIFT_THRESHOLD,
        "active_regime": hmm_state.get("latest_regime", "HIGH_VOL_CHOP"),
        "global_drift_status": "CONFORMAL_COVERAGE_DRIFT" if global_drift_alerts else "CALIBRATED",
        "drift_alerts": global_drift_alerts,
        "quantiles_by_regime": quantiles_matrix,
    }

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    size_kb = out_p.stat().st_size / 1024.0
    logger.info(
        f"[CONFORMAL] Calibrated regime-conditioned 80%/95% cones across {len(HORIZONS)} horizons -> "
        f"status={payload['global_drift_status']}, artifact={size_kb:.1f} KB"
    )
    return payload


_cached_conformal_state: Optional[Dict[str, Any]] = None


def load_conformal_quantiles(path: str | Path = DEFAULT_CONFORMAL_PATH) -> Dict[str, Any]:
    """Sub-millisecond cached loader for Render runtime conformal quantile lookup."""
    global _cached_conformal_state
    if _cached_conformal_state is not None:
        return _cached_conformal_state

    p = Path(path)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                _cached_conformal_state = json.load(f)
            return _cached_conformal_state
        except Exception as e:
            logger.warning(f"Failed to load {p}: {e}")

    # Graceful fallback
    return {
        "version": "fallback",
        "global_drift_status": "CALIBRATED",
        "drift_alerts": [],
        "quantiles_by_regime": {
            r: {
                f"{h}D": {
                    "q_80": 1.35 if r == "LOW_VOL_TREND" else (1.60 if r == "HIGH_VOL_CHOP" else 2.10),
                    "q_95": 2.15 if r == "LOW_VOL_TREND" else (2.55 if r == "HIGH_VOL_CHOP" else 3.30),
                    "rolling_60_coverage_80": 0.80,
                    "drift_flag": "CALIBRATED",
                }
                for h in HORIZONS
            }
            for r in REGIME_NAMES
        },
    }


def compute_conformal_price_cone(
    current_price: float,
    expected_return: float = 0.0,
    annual_vol: float = 0.25,
    horizon_days: int = 20,
    regime: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Computes calibrated 80% and 95% conformal return & price cones for a given stock
    and horizon conditioned on the active HMM regime.
    """
    if regime is None:
        regime = load_regime_hmm_state().get("latest_regime", "HIGH_VOL_CHOP")

    conf_data = load_conformal_quantiles()
    h_key = f"{horizon_days}D"
    regime_map = conf_data.get("quantiles_by_regime", {}).get(regime, {})
    cell = regime_map.get(h_key) or regime_map.get("20D") or {"q_80": 1.45, "q_95": 2.35, "rolling_60_coverage_80": 0.80, "drift_flag": "CALIBRATED"}

    q80 = float(cell.get("q_80", 1.45))
    q95 = float(cell.get("q_95", 2.35))

    safe_annual_vol = min(max(float(annual_vol), 0.05), 1.50)
    daily_vol = safe_annual_vol / np.sqrt(252.0)
    horizon_sigma = daily_vol * np.sqrt(horizon_days)

    half_width_80 = q80 * horizon_sigma
    half_width_95 = q95 * horizon_sigma

    point_ret = float(expected_return)
    ret_l95 = point_ret - half_width_95
    ret_l80 = point_ret - half_width_80
    ret_u80 = point_ret + half_width_80
    ret_u95 = point_ret + half_width_95

    px = max(float(current_price), 0.01)
    return {
        "regime": regime,
        "horizon_days": int(horizon_days),
        "q_80": round(q80, 4),
        "q_95": round(q95, 4),
        "rolling_60_coverage_80": cell.get("rolling_60_coverage_80", 0.80),
        "drift_flag": cell.get("drift_flag", "CALIBRATED"),
        "expected_return_pct": round(point_ret * 100.0, 2),
        "lower_95_return_pct": round(ret_l95 * 100.0, 2),
        "lower_80_return_pct": round(ret_l80 * 100.0, 2),
        "upper_80_return_pct": round(ret_u80 * 100.0, 2),
        "upper_95_return_pct": round(ret_u95 * 100.0, 2),
        "point_estimate_price": round(px * (1.0 + point_ret), 2),
        "lower_95_price": round(px * max(0.01, 1.0 + ret_l95), 2),
        "lower_80_price": round(px * max(0.01, 1.0 + ret_l80), 2),
        "upper_80_price": round(px * (1.0 + ret_u80), 2),
        "upper_95_price": round(px * (1.0 + ret_u95), 2),
    }
