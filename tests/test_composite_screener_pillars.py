"""
Unit tests for FactorScreener Winsorization and 4-Pillar Sub-Scores (Phase 14).
"""

import pytest
import pandas as pd
import numpy as np

from src.quant.screener import FactorScreener


def test_winsorize_series():
    # Test series with extreme outliers and NaNs
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0, 1000.0, np.nan, -500.0])
    w = FactorScreener.winsorize_series(s, lower_pct=0.05, upper_pct=0.95)

    assert pd.isna(w.iloc[6])  # Preserves NaN
    assert w.iloc[5] < 1000.0   # Upper outlier clipped
    assert w.iloc[7] > -500.0   # Lower outlier clipped


def test_calculate_pillar_scores():
    screener = FactorScreener(db_manager=None)

    data = {
        "symbol": ["RELIANCE", "TCS", "INFY", "HDFCBANK"],
        "roe_pct": [14.5, 38.0, 29.0, np.nan],
        "opm_pct": [16.0, 25.0, 21.0, 35.0],
        "debt_to_equity": [0.4, 0.05, 0.08, 1.2],
        "excess_ret_20d": [0.05, -0.02, 0.08, 0.01],
        "ret_5d": [0.02, 0.01, 0.03, -0.01],
        "rsi_14": [55.0, 48.0, 62.0, 42.0],
        "ttm_pe": [25.0, 30.0, 22.0, 18.0],
        "volatility_annualized": [0.18, 0.16, 0.22, 0.20],
        "beta_60d_nifty": [0.95, 0.80, 1.10, 1.05],
    }
    df = pd.DataFrame(data)

    pillars = screener.calculate_pillar_scores(df)

    assert "quality_score" in pillars
    assert "momentum_score" in pillars
    assert "value_score" in pillars
    assert "safety_score" in pillars

    # TCS has very high ROE, low D/E, and high OPM, so its quality score should be high
    q = pillars["quality_score"]
    assert q.iloc[1] > q.iloc[0]

    # INFY has highest excess_ret_20d, ret_5d, rsi_14 -> highest momentum
    m = pillars["momentum_score"]
    assert m.iloc[2] == m.max()

    # HDFCBANK has lowest P/E -> highest earnings yield -> highest value score
    v = pillars["value_score"]
    assert v.iloc[3] == v.max()

    # TCS has lowest volatility and lowest beta -> highest safety score
    s = pillars["safety_score"]
    assert s.iloc[1] == s.max()


def test_pillar_scores_empty_df():
    screener = FactorScreener(db_manager=None)
    empty_df = pd.DataFrame()
    pillars = screener.calculate_pillar_scores(empty_df)
    assert len(pillars["quality_score"]) == 0
    assert len(pillars["momentum_score"]) == 0
