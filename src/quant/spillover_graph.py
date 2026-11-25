"""
src/quant/spillover_graph.py
MIL 2.0 Phase 9 — Cross-Asset & Sector Spillover Graph (Graphical Lasso + Lead-Lag).

Detects institutional sector rotation and macro tail-shock contagion:
1. Sparse Inverse Covariance (GraphicalLassoCV with LedoitWolf fallback) over
   trailing 60-session standardized returns of NSE sector indices.
2. Exact partial correlations rho_{ij|-ij} = -Theta_ij / sqrt(Theta_ii * Theta_jj).
3. 1-to-3 session Granger / cross-lagged Lead -> Follower spillover edges.
4. Systemic Contagion Index (0-100) from leading eigenvalue share (Absorption Ratio).
5. Strict causal PIT window (zero future look-ahead leakage).
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("MIL.SpilloverGraph")

SECTOR_INDICES = [
    "NIFTY BANK",
    "NIFTY IT",
    "NIFTY AUTO",
    "NIFTY PHARMA",
    "NIFTY METAL",
    "NIFTY FMCG",
    "NIFTY ENERGY",
    "NIFTY REALTY",
]

SECTOR_TO_INDEX_MAP: Dict[str, str] = {
    "BANKING": "NIFTY BANK",
    "FINANCIAL SERVICES": "NIFTY BANK",
    "FINANCE": "NIFTY BANK",
    "IT": "NIFTY IT",
    "INFORMATION TECHNOLOGY": "NIFTY IT",
    "TECHNOLOGY": "NIFTY IT",
    "AUTO": "NIFTY AUTO",
    "AUTOMOBILE": "NIFTY AUTO",
    "PHARMA": "NIFTY PHARMA",
    "HEALTHCARE": "NIFTY PHARMA",
    "METAL": "NIFTY METAL",
    "METALS": "NIFTY METAL",
    "FMCG": "NIFTY FMCG",
    "CONSUMER": "NIFTY FMCG",
    "ENERGY": "NIFTY ENERGY",
    "OIL & GAS": "NIFTY ENERGY",
    "POWER": "NIFTY ENERGY",
    "REALTY": "NIFTY REALTY",
    "REAL ESTATE": "NIFTY REALTY",
}

DEFAULT_SPILLOVER_PATH = Path("data/models/spillover_graph.json")


def compute_partial_correlations_from_returns(
    returns_df: pd.DataFrame,
    window: int = 60,
) -> Tuple[np.ndarray, List[str], str]:
    """
    Estimates sparse precision matrix Theta = Sigma^{-1} on the trailing `window`
    standardized returns and extracts symmetric partial correlations in [-1, 1].
    Returns (partial_corr_matrix, column_names, estimator_used).
    """
    from sklearn.covariance import GraphicalLasso, GraphicalLassoCV, LedoitWolf

    tail_df = returns_df.tail(window).dropna(axis=1, how="all").fillna(0.0)
    cols = list(tail_df.columns)
    X = tail_df.to_numpy(dtype=np.float64)

    # Standardize columns safely
    means = np.mean(X, axis=0)
    stds = np.std(X, axis=0)
    valid_cols = [i for i, s in enumerate(stds) if s > 1e-8]
    X = X[:, valid_cols]
    cols = [cols[i] for i in valid_cols]
    stds = stds[valid_cols]
    means = means[valid_cols]
    X_std = np.clip((X - means) / stds, -5.0, 5.0)

    n_nodes = X_std.shape[1]
    if n_nodes < 2 or X_std.shape[0] < 15:
        return np.eye(max(n_nodes, 1)), cols, "IDENTITY_FALLBACK"

    estimator_used = "GraphicalLassoCV"
    precision = None
    try:
        model = GraphicalLassoCV(cv=3, max_iter=200, assume_centered=True)
        model.fit(X_std)
        precision = model.precision_
    except Exception:
        try:
            model = GraphicalLasso(alpha=0.15, max_iter=200, assume_centered=True)
            model.fit(X_std)
            precision = model.precision_
            estimator_used = "GraphicalLasso"
        except Exception:
            lw = LedoitWolf(assume_centered=True).fit(X_std)
            precision = lw.precision_
            estimator_used = "LedoitWolf"

    diag = np.sqrt(np.maximum(np.diag(precision), 1e-10))
    pcorr = -precision / np.outer(diag, diag)
    np.fill_diagonal(pcorr, 1.0)
    pcorr = 0.5 * (pcorr + pcorr.T)  # enforce exact symmetry
    pcorr = np.clip(pcorr, -1.0, 1.0)
    return pcorr, cols, estimator_used


def compute_systemic_contagion_index(returns_df: pd.DataFrame, window: int = 60) -> float:
    """
    Computes Systemic Contagion Index (0-100) from the leading eigenvalue share
    (Absorption Ratio) of the trailing `window`-session return correlation matrix.
    """
    tail = returns_df.tail(window).dropna(axis=1, how="any")
    if tail.shape[1] < 2 or tail.shape[0] < 15:
        return 35.0
    corr = tail.corr().fillna(0.0).to_numpy(dtype=np.float64)
    corr = 0.5 * (corr + corr.T)
    eigvals = np.linalg.eigvalsh(corr)
    eigvals = np.maximum(eigvals, 0.0)
    total = float(np.sum(eigvals))
    if total <= 1e-12:
        return 0.0
    n = len(eigvals)
    lead_share = float(np.max(eigvals)) / total
    # Normalize from [1/n, 1.0] to [0, 100]
    norm = (lead_share - (1.0 / n)) / max(1.0 - (1.0 / n), 1e-6)
    return round(float(np.clip(norm * 100.0, 0.0, 100.0)), 2)


def _granger_f_score(leader: np.ndarray, follower: np.ndarray, max_lag: int = 2) -> Tuple[float, float, int]:
    """
    Computes Granger-style F-statistic for `leader` -> `follower` with `max_lag` lags
    and returns (f_score, best_lag_corr, best_lag).
    """
    T = len(follower)
    if T <= 2 * max_lag + 5:
        return 0.0, 0.0, 1

    best_corr = 0.0
    best_lag = 1
    for lag in (1, 2, 3):
        if T > lag + 5:
            c = np.corrcoef(leader[:-lag], follower[lag:])[0, 1]
            if np.isfinite(c) and abs(c) > abs(best_corr):
                best_corr = float(c)
                best_lag = lag

    y = follower[max_lag:]
    n_obs = len(y)
    # Restricted: own lags + intercept
    X_r = np.column_stack([np.ones(n_obs)] + [follower[max_lag - k: T - k] for k in range(1, max_lag + 1)])
    # Unrestricted: own lags + leader lags + intercept
    X_u = np.column_stack([X_r] + [leader[max_lag - k: T - k] for k in range(1, max_lag + 1)])

    try:
        beta_r, *_ = np.linalg.lstsq(X_r, y, rcond=None)
        rss_r = float(np.sum((y - X_r @ beta_r) ** 2))
        beta_u, *_ = np.linalg.lstsq(X_u, y, rcond=None)
        rss_u = float(np.sum((y - X_u @ beta_u) ** 2))
        df_num = max_lag
        df_den = max(n_obs - X_u.shape[1], 1)
        f_stat = ((rss_r - rss_u) / df_num) / max(rss_u / df_den, 1e-12)
        return round(float(max(f_stat, 0.0)), 3), round(best_corr, 4), best_lag
    except Exception:
        return 0.0, round(best_corr, 4), best_lag


def build_spillover_graph(
    db_path: str = "data/market_lab.db",
    macro_path: str = "data/macro_telemetry.json",
    output_path: str | Path = DEFAULT_SPILLOVER_PATH,
    as_of_date: Optional[str] = None,
    window: int = 60,
) -> Dict[str, Any]:
    """
    Builds the causal Cross-Asset & Sector Spillover Graph up to `as_of_date`
    and exports `data/models/spillover_graph.json` (< 150 KB).
    """
    date_filter = "AND trading_date <= ?" if as_of_date else ""
    params: Tuple[Any, ...] = tuple(SECTOR_INDICES) + ((as_of_date,) if as_of_date else ())
    placeholders = ",".join("?" for _ in SECTOR_INDICES)

    with sqlite3.connect(db_path) as conn:
        df = pd.read_sql_query(
            f"""
            SELECT index_name, trading_date, close
            FROM index_daily
            WHERE index_name IN ({placeholders}) {date_filter}
            ORDER BY trading_date ASC
            """,
            conn,
            params=params,
        )

    if df.empty:
        raise RuntimeError("No sector index data found in index_daily to build spillover graph.")

    df["trading_date"] = df["trading_date"].astype(str)
    pivot = df.pivot_table(index="trading_date", columns="index_name", values="close", aggfunc="last").sort_index()
    pivot = pivot.ffill().dropna(how="all")
    returns_df = np.log(pivot / pivot.shift(1)).iloc[1:].fillna(0.0)

    latest_date = str(returns_df.index[-1])
    pcorr, cols, estimator_used = compute_partial_correlations_from_returns(returns_df, window=window)
    contagion_index = compute_systemic_contagion_index(returns_df, window=window)

    # Trailing 5-session cumulative return per sector
    ret_5d_map = {}
    tail_5 = returns_df.tail(5)
    for c in cols:
        ret_5d_map[c] = round(float(np.expm1(tail_5[c].sum()) * 100.0), 2)

    # Sparse partial correlation edges (|rho| >= 0.08)
    sparse_edges: List[Dict[str, Any]] = []
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            rho = float(pcorr[i, j])
            if abs(rho) >= 0.08:
                sparse_edges.append({
                    "source": cols[i],
                    "target": cols[j],
                    "partial_corr": round(rho, 4),
                    "abs_strength": round(abs(rho), 4),
                })
    sparse_edges.sort(key=lambda x: x["abs_strength"], reverse=True)

    # Directed Leader -> Follower Granger spillover edges (trailing 60 sessions)
    tail_ret = returns_df[cols].tail(window)
    directed_edges: List[Dict[str, Any]] = []
    sector_penalty_map: Dict[str, Dict[str, Any]] = {
        c: {"ret_5d_pct": ret_5d_map.get(c, 0.0), "negative_spillover_penalty": 0.0, "leaders": []}
        for c in cols
    }

    for i, leader in enumerate(cols):
        l_arr = tail_ret[leader].to_numpy(dtype=np.float64)
        for j, follower in enumerate(cols):
            if i == j:
                continue
            f_arr = tail_ret[follower].to_numpy(dtype=np.float64)
            f_score, lag_corr, best_lag = _granger_f_score(l_arr, f_arr, max_lag=2)
            if f_score >= 2.0 or abs(lag_corr) >= 0.22:
                leader_ret5 = ret_5d_map.get(leader, 0.0)
                is_neg_shock = (leader_ret5 < -1.0 and lag_corr > 0.15) or (leader_ret5 > 1.5 and lag_corr < -0.15)
                signal_type = "NEGATIVE_SPILLOVER" if is_neg_shock else "POSITIVE_ROTATION"
                edge = {
                    "leader": leader,
                    "follower": follower,
                    "granger_f": f_score,
                    "lag_corr": lag_corr,
                    "best_lag_days": best_lag,
                    "leader_5d_ret_pct": leader_ret5,
                    "signal_type": signal_type,
                }
                directed_edges.append(edge)
                if is_neg_shock:
                    sector_penalty_map[follower]["negative_spillover_penalty"] = round(
                        min(0.25, sector_penalty_map[follower]["negative_spillover_penalty"] + 0.05), 3
                    )
                    sector_penalty_map[follower]["leaders"].append(leader)

    directed_edges.sort(key=lambda x: (x["granger_f"], abs(x["lag_corr"])), reverse=True)

    # Include live macro telemetry context if present
    macro_signals: List[Dict[str, Any]] = []
    if os.path.exists(macro_path):
        try:
            with open(macro_path, "r", encoding="utf-8") as mf:
                m_data = json.load(mf)
            for ind in m_data.get("indicators", []):
                macro_signals.append({
                    "symbol": ind.get("symbol"),
                    "label": ind.get("label"),
                    "value": ind.get("value"),
                    "change_pct": ind.get("change_pct"),
                })
        except Exception:
            pass

    payload = {
        "version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": latest_date,
        "window_sessions": window,
        "estimator": estimator_used,
        "systemic_contagion_index": contagion_index,
        "contagion_regime": (
            "SYSTEMIC_STRESS" if contagion_index >= 70.0
            else ("ELEVATED_COUPLING" if contagion_index >= 50.0 else "NORMAL_DISPERSION")
        ),
        "nodes": cols,
        "sector_5d_returns_pct": ret_5d_map,
        "sparse_partial_corr_edges": sparse_edges[:30],
        "directed_lead_lag_edges": directed_edges[:25],
        "top_spillover_alert": directed_edges[0] if directed_edges else None,
        "sector_risk_penalties": sector_penalty_map,
        "macro_indicators": macro_signals,
    }

    if output_path:
        out_p = Path(output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        size_kb = out_p.stat().st_size / 1024.0
        logger.info(
            f"[SPILLOVER] Built {len(cols)}-sector graph ({estimator_used}) -> "
            f"contagion={contagion_index}/100, edges={len(sparse_edges)}, artifact={size_kb:.1f} KB"
        )

    return payload


_cached_spillover: Optional[Dict[str, Any]] = None


def load_spillover_graph(path: str | Path = DEFAULT_SPILLOVER_PATH) -> Dict[str, Any]:
    """Sub-millisecond cached loader for Render runtime spillover lookup."""
    global _cached_spillover
    if _cached_spillover is not None:
        return _cached_spillover

    p = Path(path)
    if p.exists():
        try:
            with open(p, "r", encoding="utf-8") as f:
                _cached_spillover = json.load(f)
            return _cached_spillover
        except Exception as e:
            logger.warning(f"Failed to load {p}: {e}")

    return {
        "version": "fallback",
        "systemic_contagion_index": 40.0,
        "contagion_regime": "NORMAL_DISPERSION",
        "directed_lead_lag_edges": [],
        "top_spillover_alert": None,
        "sector_risk_penalties": {},
    }


def get_sector_spillover_penalty(sector: Optional[str]) -> Dict[str, Any]:
    """
    Returns negative spillover penalty and leader attribution for a stock's sector.
    Used by MultiAgentDeliberationEngine during risk deliberation.
    """
    graph = load_spillover_graph()
    idx_name = None
    if sector:
        s_up = sector.strip().upper()
        if s_up in graph.get("sector_risk_penalties", {}):
            idx_name = s_up
        else:
            for key, mapped in SECTOR_TO_INDEX_MAP.items():
                if key in s_up:
                    idx_name = mapped
                    break

    pen_info = graph.get("sector_risk_penalties", {}).get(idx_name or "", {})
    return {
        "sector_index": idx_name,
        "systemic_contagion_index": graph.get("systemic_contagion_index", 40.0),
        "contagion_regime": graph.get("contagion_regime", "NORMAL_DISPERSION"),
        "negative_spillover_penalty": float(pen_info.get("negative_spillover_penalty", 0.0)),
        "negative_leaders": pen_info.get("leaders", []),
        "sector_5d_return_pct": pen_info.get("ret_5d_pct", 0.0),
    }
