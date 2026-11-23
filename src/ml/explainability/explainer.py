"""
Market Intelligence Lab — Machine Learning Factor Attribution & Explainability Engine (Phase 19).

Decomposes ML excess return forecasts into factor-level contributions,
groups them into institutional pillars (Momentum/Trend, Quality, Risk/Volatility, Microstructure/Flow),
and synthesizes natural language executive memos for quantitative review.
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

PILLAR_MAPPING = {
    "ret_1d": "MOMENTUM_TREND",
    "ret_5d": "MOMENTUM_TREND",
    "ret_20d": "MOMENTUM_TREND",
    "dist_sma20": "MOMENTUM_TREND",
    "dist_sma50": "MOMENTUM_TREND",
    "dist_sma200": "MOMENTUM_TREND",
    "tactical_20d": "MOMENTUM_TREND",
    "trend_60d": "MOMENTUM_TREND",
    "structural_200d": "MOMENTUM_TREND",
    "relative_strength_nifty": "MOMENTUM_TREND",
    
    "roe_pct": "FUNDAMENTAL_QUALITY",
    "opm_pct": "FUNDAMENTAL_QUALITY",
    "debt_to_equity": "FUNDAMENTAL_QUALITY",
    "operating_margin": "FUNDAMENTAL_QUALITY",
    
    "vol_20d": "RISK_AND_VOLATILITY",
    "beta_60d": "RISK_AND_VOLATILITY",
    "low_vol_quality": "RISK_AND_VOLATILITY",
    "rsi_regime": "RISK_AND_VOLATILITY",
    
    "vol_ratio_20d": "FLOW_AND_MICROSTRUCTURE",
    "volume_accumulation": "FLOW_AND_MICROSTRUCTURE",
    "completeness_score": "FLOW_AND_MICROSTRUCTURE",
    "news_sentiment_7d": "FLOW_AND_MICROSTRUCTURE",
}

DEFAULT_FEATURE_MEANS = {
    "ret_1d": 0.0005,
    "ret_5d": 0.0025,
    "ret_20d": 0.0100,
    "vol_20d": 0.2200,
    "dist_sma20": 0.0050,
    "dist_sma50": 0.0120,
    "dist_sma200": 0.0400,
    "vol_ratio_20d": 1.0500,
    "beta_60d": 1.0000,
    "roe_pct": 14.0000,
    "debt_to_equity": 0.6500,
    "opm_pct": 16.5000,
    "completeness_score": 0.9500,
}

DEFAULT_FEATURE_WEIGHTS = {
    "ret_20d": 0.25,
    "ret_5d": 0.15,
    "ret_1d": 0.05,
    "dist_sma50": 0.10,
    "dist_sma200": 0.08,
    "dist_sma20": 0.07,
    "roe_pct": 0.18,
    "opm_pct": 0.12,
    "debt_to_equity": -0.15,
    "vol_20d": -0.12,
    "beta_60d": -0.08,
    "vol_ratio_20d": 0.10,
    "completeness_score": 0.05,
}


class ModelExplainer:
    """
    Decomposes model predictions into factor contributions and synthesizes explainable narratives.
    """

    def __init__(
        self,
        feature_weights: Optional[Dict[str, float]] = None,
        feature_means: Optional[Dict[str, float]] = None
    ):
        self.weights = feature_weights or DEFAULT_FEATURE_WEIGHTS
        self.means = feature_means or DEFAULT_FEATURE_MEANS

    def explain_prediction(
        self,
        features: Dict[str, Any],
        predicted_excess_return: float,
        horizon_days: int = 20,
        symbol: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Decomposes a single forecast into feature contributions and produces
        pillar aggregations and a human-readable memo.
        """
        contributions: Dict[str, float] = {}
        pillar_contributions: Dict[str, float] = {
            "MOMENTUM_TREND": 0.0,
            "FUNDAMENTAL_QUALITY": 0.0,
            "RISK_AND_VOLATILITY": 0.0,
            "FLOW_AND_MICROSTRUCTURE": 0.0,
        }

        # Compute raw linear contributions
        for feat, val in features.items():
            if feat in self.weights and val is not None and not (isinstance(val, float) and math.isnan(val)):
                mean_val = self.means.get(feat, 0.0)
                w = self.weights[feat]
                # Contribution = weight * (feature - baseline_mean)
                contrib = float(w * (float(val) - mean_val))
                contributions[feat] = round(contrib, 6)
                pillar = PILLAR_MAPPING.get(feat, "MOMENTUM_TREND")
                pillar_contributions[pillar] += contrib

        # Rescale sum of contributions to match predicted excess return if non-zero
        raw_sum = sum(contributions.values())
        if abs(raw_sum) > 1e-6 and abs(predicted_excess_return) > 1e-6:
            scale = predicted_excess_return / raw_sum
            for k in contributions:
                contributions[k] = round(contributions[k] * scale, 6)
            for p in pillar_contributions:
                pillar_contributions[p] = round(pillar_contributions[p] * scale, 6)

        # Sort feature contributions by magnitude
        sorted_feats = sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True)
        top_positive = [kv for kv in sorted_feats if kv[1] > 0][:3]
        top_negative = [kv for kv in sorted_feats if kv[1] < 0][:3]

        # Synthesize executive natural language memo
        sym_str = f" for {symbol}" if symbol else ""
        pred_pct = round(predicted_excess_return * 100.0, 2)
        direction = "Bullish" if predicted_excess_return > 0.01 else ("Bearish" if predicted_excess_return < -0.01 else "Neutral")

        # Identify dominant pillar
        dominant_pillar, dominant_impact = max(pillar_contributions.items(), key=lambda kv: abs(kv[1]))
        pillar_name_clean = dominant_pillar.replace("_", " ").title()

        drivers_text = []
        if top_positive:
            pos_names = ", ".join([f"{k} (+{round(v*100, 2)}%)" for k, v in top_positive])
            drivers_text.append(f"Primary tailwinds: {pos_names}.")
        if top_negative:
            neg_names = ", ".join([f"{k} ({round(v*100, 2)}%)" for k, v in top_negative])
            drivers_text.append(f"Headwinds: {neg_names}.")

        memo = (
            f"{direction} outlook{sym_str} over {horizon_days}D horizon ({pred_pct:+.2f}% expected excess vs NIFTY 50). "
            f"Largest driving pillar is {pillar_name_clean} ({round(dominant_impact*100, 2):+.2f}% contribution). "
            f"{' '.join(drivers_text)}"
        )

        return {
            "symbol": symbol,
            "horizon_days": horizon_days,
            "predicted_excess_return": round(predicted_excess_return, 6),
            "expected_excess_return_pct": pred_pct,
            "direction": direction,
            "feature_contributions": contributions,
            "pillar_contributions": {k: round(v, 6) for k, v in pillar_contributions.items()},
            "dominant_pillar": dominant_pillar,
            "top_positive_features": top_positive,
            "top_negative_features": top_negative,
            "executive_memo": memo
        }
