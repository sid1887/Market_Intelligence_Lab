"""
Unit tests for ML Purging, Embargoing, and Model Explainability (Phases 16–20).
"""

import pytest
import pandas as pd
import numpy as np

from src.ml.features.builder import purge_and_embargo
from src.ml.explainability.explainer import ModelExplainer


def test_purge_and_embargo():
    # Calendar of 100 consecutive dates
    calendar = [f"2024-01-{i:02d}" for i in range(1, 32)] + [f"2024-02-{i:02d}" for i in range(1, 30)]

    df = pd.DataFrame({
        "trading_date": calendar[:50],
        "symbol": ["INFY"] * 50,
        "feature_1": np.random.randn(50)
    })

    test_start = "2024-01-25"
    test_end = "2024-02-05"

    train_df, test_df = purge_and_embargo(
        df=df,
        test_start_date=test_start,
        test_end_date=test_end,
        calendar=calendar,
        horizon_sessions=10,
        embargo_sessions=5
    )

    # Test set must only contain dates in [test_start, test_end]
    assert test_df["trading_date"].min() >= test_start
    assert test_df["trading_date"].max() <= test_end

    # Train set must not overlap test set
    assert train_df["trading_date"].max() < test_start

    # The latest training date must be purged by at least horizon_sessions (10 sessions) before test_start
    train_dates = sorted(train_df["trading_date"].unique())
    last_train_idx = calendar.index(train_dates[-1])
    test_start_idx = calendar.index(test_start)
    assert test_start_idx - last_train_idx > 10


def test_model_explainer():
    explainer = ModelExplainer()

    features = {
        "ret_20d": 0.08,
        "ret_5d": 0.03,
        "dist_sma50": 0.04,
        "roe_pct": 28.0,
        "opm_pct": 22.0,
        "debt_to_equity": 0.1,
        "vol_20d": 0.15,
        "beta_60d": 0.9,
    }

    res = explainer.explain_prediction(
        features=features,
        predicted_excess_return=0.035,
        horizon_days=20,
        symbol="TCS"
    )

    assert res["symbol"] == "TCS"
    assert res["direction"] == "Bullish"
    assert res["predicted_excess_return"] == 0.035
    assert "MOMENTUM_TREND" in res["pillar_contributions"]
    assert "FUNDAMENTAL_QUALITY" in res["pillar_contributions"]
    assert len(res["top_positive_features"]) > 0
    assert "executive_memo" in res
    assert "TCS" in res["executive_memo"]
    assert "expected excess" in res["executive_memo"]
