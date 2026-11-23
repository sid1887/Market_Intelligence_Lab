import math
import numpy as np
import pandas as pd
import pytest

from src.quant.factor_calculator import (
    compute_rsi_series,
    compute_atr_series,
    compute_macd_series,
    compute_bollinger_bands,
    compute_all_vectorized_factors
)


def test_rsi_series_bounds_and_warmup():
    # 30 bars of linearly increasing prices
    prices = pd.Series([100.0 + i for i in range(30)])
    rsi = compute_rsi_series(prices, period=14)

    # Initial 13 values must be NaN (warmup)
    assert pd.isna(rsi.iloc[0])
    assert pd.isna(rsi.iloc[13])

    # Since prices only increase, RSI must be 100
    assert rsi.iloc[14] == pytest.approx(100.0, rel=1e-3)
    assert (rsi.dropna() <= 100.0).all()
    assert (rsi.dropna() >= 0.0).all()


def test_bollinger_bands_and_atr_invariants():
    # Synthetic realistic price path
    np.random.seed(42)
    n = 100
    close = pd.Series(100.0 + np.cumsum(np.random.randn(n) * 1.5))
    high = close + np.random.uniform(0.5, 2.0, n)
    low = close - np.random.uniform(0.5, 2.0, n)

    upper, lower, pct_b, bw = compute_bollinger_bands(close, period=20, num_std=2.0)

    # First 19 values must be NaN
    assert pd.isna(upper.iloc[18])
    assert pd.isna(lower.iloc[18])

    # For valid index: upper > lower
    valid_mask = ~upper.isna()
    assert (upper[valid_mask] > lower[valid_mask]).all()
    assert (bw[valid_mask] > 0).all()

    # ATR
    atr = compute_atr_series(high, low, close, period=14)
    assert pd.isna(atr.iloc[12])
    assert (atr.dropna() > 0).all()


def test_macd_series_convergence():
    # 50 bars
    prices = pd.Series([100.0 + i * 0.5 for i in range(50)])
    macd_l, macd_s, macd_h = compute_macd_series(prices)

    # Monotonically increasing price gives positive MACD
    assert macd_l.iloc[-1] > 0
    assert (macd_h.iloc[-1] == pytest.approx(macd_l.iloc[-1] - macd_s.iloc[-1], rel=1e-5))


def test_all_vectorized_factors_24_matrix():
    # 300 bars to satisfy all warm-up periods (sma_200, ret_252d)
    np.random.seed(123)
    n = 300
    dates = pd.date_range("2023-01-01", periods=n, freq="D").strftime("%Y-%m-%d")
    close = 100.0 + np.cumsum(np.random.randn(n) * 1.0)
    high = close + 1.0
    low = close - 1.0
    volume = np.random.randint(100000, 5000000, n)

    df_raw = pd.DataFrame({
        "trading_date": dates,
        "open": close,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume
    })

    df_factors = compute_all_vectorized_factors(df_raw)

    # Verify all expected columns are present
    expected_cols = [
        "ret_1d", "ret_5d", "ret_20d", "ret_60d", "ret_120d", "ret_252d",
        "sma_20", "sma_50", "sma_100", "sma_200", "ema_9", "ema_21",
        "rsi_14", "macd_line", "macd_signal", "macd_hist",
        "bb_upper", "bb_lower", "bb_pct_b", "bb_bandwidth", "atr_14",
        "vol_20d_annualized", "vol_60d_annualized", "volume_ratio_20d", "volume_zscore_50d"
    ]
    for col in expected_cols:
        assert col in df_factors.columns, f"Missing factor {col}"

    # Verify warm-up strictness (zero fabrication)
    assert pd.isna(df_factors["ret_252d"].iloc[250])
    assert pd.notna(df_factors["ret_252d"].iloc[252])

    assert pd.isna(df_factors["sma_200"].iloc[198])
    assert pd.notna(df_factors["sma_200"].iloc[199])

    assert pd.isna(df_factors["vol_20d_annualized"].iloc[18])
    assert pd.notna(df_factors["vol_20d_annualized"].iloc[20])
