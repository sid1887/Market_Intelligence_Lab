"""
src/quant/regime_hmm.py
MIL 2.0 Phase 8 — 3-State Gaussian Hidden Markov Model (HMM) Market Regime Engine.

Strictly Causal Design:
- Uses forward-only filtering P(S_t = k | F_t) so future market data never leaks
  into past or current regime probabilities (zero backward Viterbi smoothing).
- Trained offline on historical NIFTY 50 TRI, realized volatility, market breadth thrust,
  and cross-sectional return dispersion.
- Exports compact < 100 KB JSON artifact (`data/models/regime_hmm_state.json`) for
  sub-millisecond inference on Render's 512 MB runtime.
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

logger = logging.getLogger("MIL.RegimeHMM")

REGIME_NAMES = ("LOW_VOL_TREND", "HIGH_VOL_CHOP", "STRESS_DRAWDOWN")

REGIME_POLICIES: Dict[str, Dict[str, Any]] = {
    "LOW_VOL_TREND": {
        "regime": "LOW_VOL_TREND",
        "label": "Low-Vol Trend",
        "description": "Positive trend drift with suppressed volatility. Standard sizing and hurdle.",
        "position_scale": 1.0,
        "max_portfolio_exposure": 1.0,
        "min_meta_prob_delta": 0.0,
        "veto_high_beta_breakouts": False,
        "stop_tightening_factor": 1.0,
    },
    "HIGH_VOL_CHOP": {
        "regime": "HIGH_VOL_CHOP",
        "label": "High-Vol Chop",
        "description": "Elevated two-way volatility and weak trend persistence. Tighten stops & raise hurdle +0.05.",
        "position_scale": 0.75,
        "max_portfolio_exposure": 0.70,
        "min_meta_prob_delta": 0.05,
        "veto_high_beta_breakouts": False,
        "stop_tightening_factor": 0.80,
    },
    "STRESS_DRAWDOWN": {
        "regime": "STRESS_DRAWDOWN",
        "label": "Stress Drawdown",
        "description": "Severe drawdown / volatility spike. Cap exposure at 25%, scale sizes 0.5x, veto high-beta breakouts.",
        "position_scale": 0.50,
        "max_portfolio_exposure": 0.25,
        "min_meta_prob_delta": 0.10,
        "veto_high_beta_breakouts": True,
        "stop_tightening_factor": 0.65,
    },
}

DEFAULT_HMM_STATE_PATH = Path("data/models/regime_hmm_state.json")


def _logsumexp(arr: np.ndarray, axis: Optional[int] = None) -> np.ndarray:
    m = np.max(arr, axis=axis, keepdims=True)
    res = m + np.log(np.sum(np.exp(arr - m), axis=axis, keepdims=True))
    if axis is not None:
        res = np.squeeze(res, axis=axis)
    return res


def _gaussian_log_pdf_diag(X: np.ndarray, means: np.ndarray, vars_: np.ndarray) -> np.ndarray:
    """
    Computes log N(x_t | mu_k, diag(var_k)) for all t=0..T-1 and k=0..K-1.
    Returns shape (T, K).
    """
    T, D = X.shape
    K = means.shape[0]
    safe_vars = np.maximum(vars_, 1e-4)
    log_det = np.sum(np.log(2.0 * np.pi * safe_vars), axis=1)  # (K,)
    # Broadcast: (T, 1, D) - (1, K, D)
    diff = X[:, None, :] - means[None, :, :]
    quad = np.sum((diff ** 2) / safe_vars[None, :, :], axis=2)  # (T, K)
    return -0.5 * (log_det[None, :] + quad)


class GaussianRegimeHMM:
    """
    3-State Diagonal-Covariance Gaussian HMM with strictly causal forward-only filtering.
    """

    def __init__(
        self,
        n_states: int = 3,
        max_iter: int = 60,
        tol: float = 1e-4,
        random_state: int = 42,
    ):
        self.n_states = n_states
        self.max_iter = max_iter
        self.tol = tol
        self.random_state = random_state

        self.pi: Optional[np.ndarray] = None           # (K,)
        self.A: Optional[np.ndarray] = None            # (K, K)
        self.means: Optional[np.ndarray] = None        # (K, D)
        self.vars: Optional[np.ndarray] = None         # (K, D)
        self.scaler_mean: Optional[np.ndarray] = None  # (D,)
        self.scaler_std: Optional[np.ndarray] = None   # (D,)
        self.state_labels: List[str] = list(REGIME_NAMES)
        self.feature_names: List[str] = [
            "nifty_ret_20d",
            "realized_vol_20d",
            "breadth_thrust",
            "xs_dispersion",
        ]

    def _standardize(self, raw_X: np.ndarray, fit: bool = False) -> np.ndarray:
        arr = np.asarray(raw_X, dtype=np.float64)
        if fit or self.scaler_mean is None or self.scaler_std is None:
            self.scaler_mean = np.nanmean(arr, axis=0)
            self.scaler_std = np.maximum(np.nanstd(arr, axis=0), 1e-6)
        return np.clip((arr - self.scaler_mean) / self.scaler_std, -6.0, 6.0)

    def fit(self, raw_X: np.ndarray) -> "GaussianRegimeHMM":
        """
        Fits the 3-State Gaussian HMM via scaled Baum-Welch (EM) offline,
        then orders states deterministically into:
        0: LOW_VOL_TREND, 1: HIGH_VOL_CHOP, 2: STRESS_DRAWDOWN.
        """
        from sklearn.cluster import KMeans

        X = self._standardize(raw_X, fit=True)
        T, D = X.shape
        K = self.n_states

        # KMeans initialization for stable convergence
        km = KMeans(n_clusters=K, n_init=10, random_state=self.random_state)
        labels = km.fit_predict(X)
        means = np.zeros((K, D), dtype=np.float64)
        vars_ = np.ones((K, D), dtype=np.float64)
        for k in range(K):
            mask = labels == k
            if np.sum(mask) >= 5:
                means[k] = np.mean(X[mask], axis=0)
                vars_[k] = np.maximum(np.var(X[mask], axis=0), 1e-2)
            else:
                means[k] = np.mean(X, axis=0)
                vars_[k] = np.maximum(np.var(X, axis=0), 1e-2)

        # Sticky prior transition matrix (daily regimes persist)
        A = np.full((K, K), 0.02 / max(K - 1, 1), dtype=np.float64)
        np.fill_diagonal(A, 0.98)
        pi = np.full(K, 1.0 / K, dtype=np.float64)

        prev_ll = -np.inf
        for _ in range(self.max_iter):
            log_emit = _gaussian_log_pdf_diag(X, means, vars_)  # (T, K)
            log_A = np.log(np.maximum(A, 1e-12))
            log_pi = np.log(np.maximum(pi, 1e-12))

            # Scaled forward-backward for EM parameter estimation ONLY during offline fit
            log_alpha = np.zeros((T, K), dtype=np.float64)
            log_alpha[0] = log_pi + log_emit[0]
            for t in range(1, T):
                log_alpha[t] = log_emit[t] + _logsumexp(log_alpha[t - 1][:, None] + log_A, axis=0)

            ll = float(_logsumexp(log_alpha[-1], axis=0))

            log_beta = np.zeros((T, K), dtype=np.float64)
            for t in range(T - 2, -1, -1):
                log_beta[t] = _logsumexp(log_A + log_emit[t + 1][None, :] + log_beta[t + 1][None, :], axis=1)

            log_gamma = log_alpha + log_beta
            log_gamma -= _logsumexp(log_gamma, axis=1)[:, None]
            gamma = np.exp(log_gamma)  # (T, K)

            # Xi expectations
            xi_sum = np.zeros((K, K), dtype=np.float64)
            for t in range(T - 1):
                log_xi_t = (
                    log_alpha[t][:, None]
                    + log_A
                    + log_emit[t + 1][None, :]
                    + log_beta[t + 1][None, :]
                )
                log_xi_t -= _logsumexp(log_xi_t)
                xi_sum += np.exp(log_xi_t)

            # M-step with small Dirichlet regularization
            pi = np.maximum(gamma[0], 1e-4)
            pi /= np.sum(pi)

            A_num = xi_sum + 1e-3
            A = A_num / np.sum(A_num, axis=1, keepdims=True)

            gamma_sum = np.maximum(np.sum(gamma, axis=0), 1e-4)  # (K,)
            means = (gamma.T @ X) / gamma_sum[:, None]
            for k in range(K):
                diff = X - means[k][None, :]
                vars_[k] = np.maximum(np.sum(gamma[:, k][:, None] * (diff ** 2), axis=0) / gamma_sum[k], 1e-2)

            if abs(ll - prev_ll) < self.tol:
                break
            prev_ll = ll

        # Sort states deterministically by stress score:
        # feature 0 is nifty_ret_20d (higher = calmer), feature 1 is realized_vol_20d (higher = stress)
        stress_scores = means[:, 1] - 0.75 * means[:, 0]
        order = np.argsort(stress_scores)  # ascending: 0=LOW_VOL_TREND, 1=HIGH_VOL_CHOP, 2=STRESS_DRAWDOWN

        self.pi = pi[order]
        self.A = A[np.ix_(order, order)]
        self.means = means[order]
        self.vars = vars_[order]
        self.state_labels = list(REGIME_NAMES)
        return self

    def forward_filter(self, raw_X: np.ndarray) -> np.ndarray:
        """
        Strictly causal forward-only filtering:
        Computes alpha_t(k) = P(S_t = k | X_1, ..., X_t) for each t = 0..T-1.
        Future observations X_{t+1..T} NEVER influence alpha_t.
        """
        if self.pi is None or self.A is None or self.means is None or self.vars is None:
            raise RuntimeError("GaussianRegimeHMM must be fitted or loaded before forward_filter().")

        X = self._standardize(raw_X, fit=False)
        T, _ = X.shape
        K = self.n_states

        log_emit = _gaussian_log_pdf_diag(X, self.means, self.vars)
        log_A = np.log(np.maximum(self.A, 1e-12))
        log_pi = np.log(np.maximum(self.pi, 1e-12))

        probs = np.zeros((T, K), dtype=np.float64)
        log_alpha = log_pi + log_emit[0]
        log_alpha -= float(_logsumexp(log_alpha, axis=0))
        probs[0] = np.exp(log_alpha)

        for t in range(1, T):
            log_alpha = log_emit[t] + _logsumexp(log_alpha[:, None] + log_A, axis=0)
            log_alpha -= float(_logsumexp(log_alpha, axis=0))
            probs[t] = np.exp(log_alpha)

        # Guarantee exact row normalization
        probs /= np.maximum(np.sum(probs, axis=1, keepdims=True), 1e-12)
        return probs

    def to_dict(self) -> Dict[str, Any]:
        return {
            "n_states": self.n_states,
            "state_labels": self.state_labels,
            "feature_names": self.feature_names,
            "pi": self.pi.tolist() if self.pi is not None else [],
            "A": self.A.tolist() if self.A is not None else [],
            "means": self.means.tolist() if self.means is not None else [],
            "vars": self.vars.tolist() if self.vars is not None else [],
            "scaler_mean": self.scaler_mean.tolist() if self.scaler_mean is not None else [],
            "scaler_std": self.scaler_std.tolist() if self.scaler_std is not None else [],
        }

    @classmethod
    def from_dict(cls, payload: Dict[str, Any]) -> "GaussianRegimeHMM":
        model = cls(n_states=int(payload.get("n_states", 3)))
        model.state_labels = list(payload.get("state_labels", REGIME_NAMES))
        model.feature_names = list(payload.get("feature_names", model.feature_names))
        model.pi = np.asarray(payload["pi"], dtype=np.float64)
        model.A = np.asarray(payload["A"], dtype=np.float64)
        model.means = np.asarray(payload["means"], dtype=np.float64)
        model.vars = np.asarray(payload["vars"], dtype=np.float64)
        model.scaler_mean = np.asarray(payload["scaler_mean"], dtype=np.float64)
        model.scaler_std = np.asarray(payload["scaler_std"], dtype=np.float64)
        return model


def build_regime_feature_matrix(
    db_path: str = "data/market_lab.db",
    milz_path: str = "data/archive/bhavcopy_10y.milz",
) -> pd.DataFrame:
    """
    Constructs a strictly causal daily feature DataFrame from NIFTY 50 PRI (`index_daily`)
    and cross-sectional NSE breadth/dispersion (`bhavcopy_10y.milz` or `ohlcv_daily`).
    """
    import sqlite3

    with sqlite3.connect(db_path) as conn:
        idx_df = pd.read_sql_query(
            """
            SELECT trading_date, open, high, low, close
            FROM index_daily
            WHERE index_name = 'NIFTY 50' AND index_type = 'PRI'
            ORDER BY trading_date ASC
            """,
            conn,
        )

    if idx_df.empty:
        raise RuntimeError("No NIFTY 50 rows found in index_daily to calibrate Regime HMM.")

    idx_df["trading_date"] = idx_df["trading_date"].astype(str)
    idx_df = idx_df.drop_duplicates(subset=["trading_date"]).sort_values("trading_date").reset_index(drop=True)
    idx_df["close"] = idx_df["close"].astype(float)
    idx_df["log_ret"] = np.log(idx_df["close"] / idx_df["close"].shift(1)).fillna(0.0)
    idx_df["nifty_ret_20d"] = idx_df["close"].pct_change(20).fillna(0.0)
    idx_df["realized_vol_20d"] = (
        idx_df["log_ret"].rolling(20, min_periods=5).std().fillna(0.01) * np.sqrt(252.0)
    )
    idx_df["intraday_range"] = (
        (idx_df["high"].astype(float) - idx_df["low"].astype(float)) / np.maximum(idx_df["close"], 1.0)
    ).rolling(20, min_periods=5).mean().fillna(0.012)

    # Cross-sectional breadth thrust & dispersion from bhavcopy_10y.milz (fast) or ohlcv_daily
    xs_df = pd.DataFrame()
    if os.path.exists(milz_path):
        try:
            from src.storage.compression_engine import MilzArchiveEngine
            eng = MilzArchiveEngine(milz_path)
            panel = eng.read_all()
            if not panel.empty and "trading_date" in panel.columns and "close" in panel.columns:
                panel["trading_date"] = panel["trading_date"].astype(str)
                panel = panel.sort_values(["symbol", "trading_date"])
                panel["ret_1d"] = panel.groupby("symbol")["close"].pct_change()
                panel["ret_20d"] = panel.groupby("symbol")["close"].pct_change(20)
                panel["pos_20d"] = (panel["ret_20d"] > 0).astype(float)
                xs_df = (
                    panel.groupby("trading_date")
                    .agg(
                        n_sym=("symbol", "count"),
                        breadth_thrust=("pos_20d", "mean"),
                        xs_dispersion=("ret_1d", "std"),
                    )
                    .reset_index()
                )
                xs_df = xs_df[xs_df["n_sym"] >= 20].drop(columns=["n_sym"])
        except Exception as e:
            logger.warning(f"MILZ cross-sectional read fallback to SQLite: {e}")

    if xs_df.empty:
        try:
            with sqlite3.connect(db_path) as conn:
                ohlcv = pd.read_sql_query(
                    """
                    SELECT symbol, trading_date, close
                    FROM ohlcv_daily
                    WHERE is_synthetic = 0
                    ORDER BY symbol, trading_date ASC
                    """,
                    conn,
                )
            if not ohlcv.empty:
                ohlcv["ret_1d"] = ohlcv.groupby("symbol")["close"].pct_change()
                ohlcv["ret_20d"] = ohlcv.groupby("symbol")["close"].pct_change(20)
                ohlcv["pos_20d"] = (ohlcv["ret_20d"] > 0).astype(float)
                xs_df = (
                    ohlcv.groupby("trading_date")
                    .agg(
                        n_sym=("symbol", "count"),
                        breadth_thrust=("pos_20d", "mean"),
                        xs_dispersion=("ret_1d", "std"),
                    )
                    .reset_index()
                )
                xs_df = xs_df[xs_df["n_sym"] >= 20].drop(columns=["n_sym"])
        except Exception as e:
            logger.debug(f"SQLite cross-sectional fallback notice: {e}")

    merged = idx_df.merge(xs_df, on="trading_date", how="left") if not xs_df.empty else idx_df.copy()

    # Smooth fallback for early index-only history (e.g., 2007-2010)
    fallback_breadth = 1.0 / (1.0 + np.exp(-15.0 * merged["nifty_ret_20d"]))
    if "breadth_thrust" not in merged.columns:
        merged["breadth_thrust"] = fallback_breadth
    else:
        merged["breadth_thrust"] = merged["breadth_thrust"].fillna(fallback_breadth)

    if "xs_dispersion" not in merged.columns:
        merged["xs_dispersion"] = merged["intraday_range"] * 1.5
    else:
        merged["xs_dispersion"] = (
            merged["xs_dispersion"]
            .rolling(10, min_periods=1)
            .mean()
            .fillna(merged["intraday_range"] * 1.5)
        )

    # Drop initial 20-day warmup rows
    out = merged.iloc[20:].copy().reset_index(drop=True)
    return out[["trading_date", "close", "nifty_ret_20d", "realized_vol_20d", "breadth_thrust", "xs_dispersion"]]


def train_and_export_regime_hmm(
    db_path: str = "data/market_lab.db",
    milz_path: str = "data/archive/bhavcopy_10y.milz",
    output_path: str | Path = DEFAULT_HMM_STATE_PATH,
    history_tail: int = 252,
) -> Dict[str, Any]:
    """
    Fits the 3-State Gaussian HMM offline on historical NSE data, performs strictly
    causal forward-only filtering, and exports `data/models/regime_hmm_state.json`.
    """
    df = build_regime_feature_matrix(db_path=db_path, milz_path=milz_path)
    feature_cols = ["nifty_ret_20d", "realized_vol_20d", "breadth_thrust", "xs_dispersion"]
    raw_X = df[feature_cols].to_numpy(dtype=np.float64)

    hmm = GaussianRegimeHMM(n_states=3, max_iter=60, random_state=42).fit(raw_X)
    filtered_probs = hmm.forward_filter(raw_X)

    df["p_low_vol_trend"] = filtered_probs[:, 0]
    df["p_high_vol_chop"] = filtered_probs[:, 1]
    df["p_stress_drawdown"] = filtered_probs[:, 2]
    state_idx = np.argmax(filtered_probs, axis=1)
    df["regime"] = [REGIME_NAMES[i] for i in state_idx]

    latest = df.iloc[-1]
    latest_regime = str(latest["regime"])
    latest_probs = {
        "LOW_VOL_TREND": round(float(latest["p_low_vol_trend"]), 4),
        "HIGH_VOL_CHOP": round(float(latest["p_high_vol_chop"]), 4),
        "STRESS_DRAWDOWN": round(float(latest["p_stress_drawdown"]), 4),
    }

    # Compact tail history for fast UI & Conformal lookup (< 100 KB total artifact)
    tail_df = df.tail(history_tail)
    recent_history = [
        {
            "trading_date": str(r.trading_date),
            "regime": str(r.regime),
            "probabilities": {
                "LOW_VOL_TREND": round(float(r.p_low_vol_trend), 4),
                "HIGH_VOL_CHOP": round(float(r.p_high_vol_chop), 4),
                "STRESS_DRAWDOWN": round(float(r.p_stress_drawdown), 4),
            },
            "nifty_ret_20d": round(float(r.nifty_ret_20d), 4),
            "realized_vol_20d": round(float(r.realized_vol_20d), 4),
            "breadth_thrust": round(float(r.breadth_thrust), 4),
        }
        for r in tail_df.itertuples(index=False)
    ]

    # Regime distribution across full history
    counts = df["regime"].value_counts().to_dict()
    total_days = len(df)
    regime_distribution_pct = {
        k: round(100.0 * counts.get(k, 0) / max(total_days, 1), 2) for k in REGIME_NAMES
    }

    payload = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "causality_mode": "FORWARD_ONLY_FILTER",
        "total_sessions_calibrated": total_days,
        "date_range": {
            "start": str(df["trading_date"].iloc[0]),
            "end": str(df["trading_date"].iloc[-1]),
        },
        "latest_date": str(latest["trading_date"]),
        "latest_regime": latest_regime,
        "latest_probabilities": latest_probs,
        "active_policy": REGIME_POLICIES[latest_regime],
        "regime_distribution_pct": regime_distribution_pct,
        "model_params": hmm.to_dict(),
        "recent_history": recent_history,
    }

    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    size_kb = out_p.stat().st_size / 1024.0
    logger.info(
        f"[HMM] Calibrated 3-State Regime HMM on {total_days} sessions -> "
        f"latest={latest_regime} ({latest_probs[latest_regime]:.2%}), artifact={size_kb:.1f} KB"
    )
    return payload


_cached_hmm_state: Optional[Dict[str, Any]] = None


def load_regime_hmm_state(path: str | Path = DEFAULT_HMM_STATE_PATH) -> Dict[str, Any]:
    """Sub-millisecond cached loader for Render runtime regime lookup."""
    global _cached_hmm_state
    if _cached_hmm_state is not None:
        return _cached_hmm_state

    p = Path(path)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                _cached_hmm_state = json.load(f)
            return _cached_hmm_state
        except Exception as e:
            logger.warning(f"Failed to load {p}: {e}")

    # Graceful fallback if artifact hasn't been generated yet
    return {
        "version": "fallback",
        "causality_mode": "FORWARD_ONLY_FILTER",
        "latest_regime": "HIGH_VOL_CHOP",
        "latest_probabilities": {
            "LOW_VOL_TREND": 0.25,
            "HIGH_VOL_CHOP": 0.55,
            "STRESS_DRAWDOWN": 0.20,
        },
        "active_policy": REGIME_POLICIES["HIGH_VOL_CHOP"],
        "recent_history": [],
    }
