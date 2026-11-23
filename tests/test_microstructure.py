import numpy as np
import pandas as pd
import pytest

from src.quant.microstructure import (
    compute_delivery_accumulation_index,
    compute_amihud_illiquidity,
    estimate_corwin_schultz_spread,
    classify_microstructure_regime
)


def test_microstructure_regime_classification():
    # 1. Institutional Accumulation: 65% delivery, 2.0x volume, +1.5% return
    r1 = classify_microstructure_regime(delivery_pct=65.0, volume_ratio=2.0, ret_1d=0.015)
    assert r1["regime"] == "INSTITUTIONAL_ACCUMULATION"
    assert r1["confidence"] >= 0.85

    # 2. Aggressive Distribution: 2.2x volume, -3.0% return
    r2 = classify_microstructure_regime(delivery_pct=30.0, volume_ratio=2.2, ret_1d=-0.030)
    assert r2["regime"] == "AGGRESSIVE_DISTRIBUTION"
    assert r2["confidence"] >= 0.85

    # 3. Absorption / Churn: 3.5x volume, 0.1% return
    r3 = classify_microstructure_regime(delivery_pct=45.0, volume_ratio=3.5, ret_1d=0.001)
    assert r3["regime"] == "ABSORPTION_CHURN"

    # 4. Normal Flow: 42% delivery, 1.0x volume, +0.2% return
    r4 = classify_microstructure_regime(delivery_pct=42.0, volume_ratio=1.0, ret_1d=0.002)
    assert r4["regime"] == "NORMAL_FLOW"


def test_amihud_and_dai_vectorized():
    n = 30
    ret_1d = pd.Series([0.01 if i % 2 == 0 else -0.01 for i in range(n)])
    turnover_cr = pd.Series([50.0 + i for i in range(n)])
    delivery_pct = pd.Series([60.0 for _ in range(n)])
    volume_ratio = pd.Series([1.5 for _ in range(n)])

    # Delivery Accumulation Index
    dai = compute_delivery_accumulation_index(delivery_pct, volume_ratio, ret_1d)
    assert len(dai) == n
    assert pd.notna(dai.iloc[-1])

    # Amihud Illiquidity
    illiq = compute_amihud_illiquidity(ret_1d, turnover_cr)
    assert len(illiq) == n
    assert pd.notna(illiq.iloc[-1])
    assert (illiq.dropna() > 0).all()


def test_corwin_schultz_spread_bounds():
    n = 25
    high = pd.Series([102.0 + i * 0.5 for i in range(n)])
    low = pd.Series([99.0 + i * 0.5 for i in range(n)])

    spread = estimate_corwin_schultz_spread(high, low)
    assert len(spread) == n
    assert (spread.dropna() >= 0.0).all()
    assert (spread.dropna() <= 0.10).all()
