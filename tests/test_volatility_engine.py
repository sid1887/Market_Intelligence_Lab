"""
Unit tests for Econometric Volatility & Tail-Risk GARCH Engine (Phase 15).
"""

import math
import numpy as np
import pytest

from src.quant.volatility_engine import (
    calculate_parkinson_volatility,
    calculate_garman_klass_volatility,
    estimate_garch11,
    calculate_var_cvar,
    calculate_volatility_cones
)


def test_parkinson_and_garman_klass():
    np.random.seed(42)
    n = 100
    base = 100.0 + np.cumsum(np.random.normal(0, 1, n))
    high = base + np.abs(np.random.normal(1.0, 0.5, n))
    low = base - np.abs(np.random.normal(1.0, 0.5, n))
    open_ = base + np.random.normal(0, 0.2, n)
    close = base + np.random.normal(0, 0.2, n)

    p_vol = calculate_parkinson_volatility(high, low)
    gk_vol = calculate_garman_klass_volatility(open_, high, low, close)

    assert p_vol is not None
    assert gk_vol is not None
    assert p_vol > 0.0
    assert gk_vol > 0.0
    # Both annualized volatilities should be reasonably bounded
    assert 0.01 < p_vol < 2.0
    assert 0.01 < gk_vol < 2.0


def test_garch11_estimation():
    np.random.seed(42)
    # Simulate GARCH(1,1) series
    n = 250
    omega = 0.00001
    alpha = 0.10
    beta = 0.85
    returns = np.zeros(n)
    sigma2 = np.zeros(n)
    sigma2[0] = omega / (1 - alpha - beta)
    z = np.random.normal(0, 1, n)

    for t in range(1, n):
        sigma2[t] = omega + alpha * (returns[t - 1] ** 2) + beta * sigma2[t - 1]
        returns[t] = math.sqrt(sigma2[t]) * z[t]

    res = estimate_garch11(returns)
    assert res["model"] in ("GARCH(1,1)", "GARCH(1,1)_ROBUST")
    assert res["conditional_volatility"] is not None
    assert res["annualized_volatility"] > 0.0
    assert res["persistence"] < 1.0


def test_var_cvar_metrics():
    np.random.seed(42)
    returns = np.random.normal(0.0005, 0.015, 200)

    res = calculate_var_cvar(returns)
    assert res["sample_size"] == 200
    assert "95%" in res["levels"]
    assert "99%" in res["levels"]

    lvl95 = res["levels"]["95%"]
    lvl99 = res["levels"]["99%"]

    # 99% VaR should be greater than 95% VaR (losses are positive)
    assert lvl99["historical_var"] > lvl95["historical_var"]
    # CVaR (Expected Shortfall) should be >= VaR
    assert lvl95["historical_cvar"] >= lvl95["historical_var"]
    assert lvl99["historical_cvar"] >= lvl99["historical_var"]


def test_volatility_cones():
    np.random.seed(42)
    returns = np.random.normal(0.0002, 0.012, 120)
    current_price = 2500.0

    cones = calculate_volatility_cones(current_price, returns, horizons=[5, 20, 60], confidence_levels=[0.80, 0.95])
    assert "horizons" in cones
    assert "5d" in cones["horizons"]
    assert "20d" in cones["horizons"]
    assert "60d" in cones["horizons"]

    h20 = cones["horizons"]["20d"]
    assert "80%" in h20["intervals"]
    assert "95%" in h20["intervals"]

    int80 = h20["intervals"]["80%"]
    int95 = h20["intervals"]["95%"]

    # 95% interval should be wider than 80% interval
    assert int95["lower_bound"] < int80["lower_bound"]
    assert int95["upper_bound"] > int80["upper_bound"]
    assert int80["lower_bound"] < current_price < int80["upper_bound"]
