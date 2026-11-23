"""
src/quant/microstructure.py
Order Flow Dynamics, Delivery Accumulation, & Market Microstructure Anomalies.

Features:
1. Delivery Accumulation Index (DAI): Tracks institutional vs speculative flow using exchange settlement delivery shares.
2. Amihud Illiquidity Metric: Quantifies price impact per crore of turnover.
3. Corwin-Schultz Bid-Ask Spread Estimator: Vectorized spread proxy derived from daily high-low price ratios.
4. Microstructure Regime Classifier: Detects Institutional Accumulation, Aggressive Distribution, and Absorption Churn.
"""

import math
import numpy as np
import pandas as pd
from typing import Dict, Any, Optional, Tuple, List


def compute_delivery_accumulation_index(
    delivery_pct: pd.Series,
    volume_ratio: pd.Series,
    ret_1d: pd.Series
) -> pd.Series:
    """
    Computes Delivery Accumulation Index (DAI):
    Measures conviction order flow by weighting daily return by delivery percentage and relative volume.
    DAI_t = ret_1d * (delivery_pct / 50.0) * sqrt(max(volume_ratio, 0.1))
    """
    d_pct = delivery_pct.fillna(40.0)
    vr = volume_ratio.fillna(1.0).clip(lower=0.1)
    ret = ret_1d.fillna(0.0)

    conviction = ret * (d_pct / 50.0) * np.sqrt(vr)
    return conviction.rolling(window=10, min_periods=5).mean().round(4)


def compute_amihud_illiquidity(
    ret_1d: pd.Series,
    turnover_cr: pd.Series
) -> pd.Series:
    """
    Computes Amihud (2002) Illiquidity Ratio:
    Illiq_t = (|ret_1d| / Turnover_Cr) * 100
    Higher values signify lower liquidity and greater price impact.
    """
    abs_ret = ret_1d.abs().fillna(0.0)
    to = turnover_cr.clip(lower=0.1).fillna(1.0)
    raw_illiq = (abs_ret / to) * 100.0
    return raw_illiq.rolling(window=20, min_periods=5).mean().round(4)


def estimate_corwin_schultz_spread(
    high: pd.Series,
    low: pd.Series
) -> pd.Series:
    """
    Corwin & Schultz (2012) High-Low Bid-Ask Spread Estimator.
    Derives effective half-spreads from 2-day high/low price dynamics without intraday tick data.
    """
    h = high.astype(float)
    l = low.astype(float)

    # 1-day log range squared
    gamma = (np.log(np.maximum(h, 1e-4) / np.maximum(l, 1e-4))) ** 2
    gamma_2d = gamma + gamma.shift(1)

    # 2-day high/low range
    h_2d = pd.concat([h, h.shift(1)], axis=1).max(axis=1)
    l_2d = pd.concat([l, l.shift(1)], axis=1).min(axis=1)
    beta = (np.log(np.maximum(h_2d, 1e-4) / np.maximum(l_2d, 1e-4))) ** 2

    # Alpha estimation
    k2 = math.sqrt(8.0 / math.pi)
    alpha = (np.sqrt(2.0 * beta) - np.sqrt(beta)) / (3.0 - 2.0 * np.sqrt(2.0)) - np.sqrt(gamma_2d / (3.0 - 2.0 * np.sqrt(2.0)))

    # Spread: S = 2 * (exp(alpha) - 1) / (1 + exp(alpha))
    exp_alpha = np.exp(alpha.clip(lower=-2.0, upper=2.0))
    spread = 2.0 * (exp_alpha - 1.0) / (1.0 + exp_alpha)
    return spread.clip(lower=0.0, upper=0.10).rolling(window=10, min_periods=5).mean().round(4)


def classify_microstructure_regime(
    delivery_pct: Optional[float],
    volume_ratio: Optional[float],
    ret_1d: Optional[float],
    high: Optional[float] = None,
    low: Optional[float] = None,
    close: Optional[float] = None
) -> Dict[str, Any]:
    """
    Classifies daily order flow dynamics into institutional regimes:
    1. INSTITUTIONAL_ACCUMULATION: High delivery %, above-average volume, positive price absorption.
    2. AGGRESSIVE_DISTRIBUTION: High volume, sharp decline, delivery selling.
    3. ABSORPTION_CHURN: Enormous volume spike with tight price pin / consolidation.
    4. NORMAL_FLOW: Typical market balancing.
    """
    d_pct = delivery_pct if delivery_pct is not None else 40.0
    vr = volume_ratio if volume_ratio is not None else 1.0
    ret = ret_1d if ret_1d is not None else 0.0

    # Upper wick calculation if OHLC available
    upper_wick_pct = 0.0
    if high and low and close and (high > low):
        upper_wick_pct = (high - close) / (high - low)

    # 1. Institutional Accumulation
    if d_pct >= 55.0 and vr >= 1.4 and ret >= -0.005:
        return {
            "regime": "INSTITUTIONAL_ACCUMULATION",
            "confidence": 0.88,
            "description": "High delivery volume and firm pricing indicate institutional sponsorship."
        }

    # 2. Aggressive Distribution
    if vr >= 1.5 and ret <= -0.015:
        return {
            "regime": "AGGRESSIVE_DISTRIBUTION",
            "confidence": 0.85,
            "description": "Elevated selling volume driving downward expansion."
        }

    # 3. Absorption / Churn
    if vr >= 2.5 and abs(ret) <= 0.006:
        return {
            "regime": "ABSORPTION_CHURN",
            "confidence": 0.80,
            "description": "Abnormal turnover volume with negligible net price change (institutional transfer or pegging)."
        }

    # 4. Rejection at Highs
    if upper_wick_pct >= 0.60 and vr >= 1.3:
        return {
            "regime": "OVERHEAD_SUPPLY_REJECTION",
            "confidence": 0.75,
            "description": "Intraday buying absorbed by aggressive supply, leaving long upper shadow."
        }

    return {
        "regime": "NORMAL_FLOW",
        "confidence": 0.60,
        "description": "Balanced two-sided retail and market-maker participation."
    }
