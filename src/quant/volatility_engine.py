"""
Market Intelligence Lab — Econometric Volatility & Tail-Risk GARCH Engine (Phase 15).

Provides institutional-grade risk and volatility analytics:
1. GARCH(1,1) conditional volatility estimation (MLE with variance targeting & RiskMetrics fallback)
2. Parkinson and Garman-Klass intraday range volatility estimators
3. Historical, Parametric, and Cornish-Fisher Value-at-Risk (VaR) and Expected Shortfall (CVaR)
4. Multi-horizon forward volatility price cones (80% and 95% confidence intervals)
"""

import math
import logging
from typing import Dict, Any, List, Optional, Tuple, Union

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import minimize

logger = logging.getLogger(__name__)

TRADING_DAYS_PER_YEAR = 252


def calculate_parkinson_volatility(
    high: np.ndarray,
    low: np.ndarray,
    trading_days: int = TRADING_DAYS_PER_YEAR
) -> Optional[float]:
    """
    Computes Parkinson (1980) extreme-value volatility estimator using High and Low prices.
    More efficient than close-to-close volatility as it captures intraday price dispersion.
    """
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)

    valid_mask = (h > 0) & (l > 0) & (h >= l)
    h_clean = h[valid_mask]
    l_clean = l[valid_mask]

    n = len(h_clean)
    if n < 5:
        return None

    log_hl = np.log(h_clean / l_clean)
    factor = 1.0 / (4.0 * math.log(2.0) * n)
    sum_sq = np.sum(log_hl ** 2)

    var = factor * sum_sq
    return float(math.sqrt(var * trading_days))


def calculate_garman_klass_volatility(
    open_: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    close: np.ndarray,
    trading_days: int = TRADING_DAYS_PER_YEAR
) -> Optional[float]:
    """
    Computes Garman-Klass (1980) volatility estimator extending Parkinson by incorporating
    Open and Close prices. ~7.4x more statistically efficient than standard close-to-close vol.
    """
    o = np.asarray(open_, dtype=float)
    h = np.asarray(high, dtype=float)
    l = np.asarray(low, dtype=float)
    c = np.asarray(close, dtype=float)

    valid_mask = (o > 0) & (h > 0) & (l > 0) & (c > 0) & (h >= l)
    o_c = o[valid_mask]
    h_c = h[valid_mask]
    l_c = l[valid_mask]
    c_c = c[valid_mask]

    n = len(o_c)
    if n < 5:
        return None

    log_hl = np.log(h_c / l_c)
    log_co = np.log(c_c / o_c)

    const = 2.0 * math.log(2.0) - 1.0
    term1 = 0.5 * (log_hl ** 2)
    term2 = const * (log_co ** 2)

    var = np.mean(term1 - term2)
    if var < 0:
        var = 0.0

    return float(math.sqrt(var * trading_days))


def estimate_garch11(
    returns: np.ndarray,
    annualized: bool = True,
    trading_days: int = TRADING_DAYS_PER_YEAR
) -> Dict[str, Any]:
    """
    Fits a GARCH(1,1) model using Quasi-Maximum Likelihood Estimation (QMLE) with variance targeting:
        sigma_t^2 = omega + alpha * epsilon_{t-1}^2 + beta * sigma_{t-1}^2
    where omega = unconditional_variance * (1 - alpha - beta).

    Falls back cleanly to EWMA (RiskMetrics lambda=0.94) if sample is small (N < 30)
    or optimization does not reach convergence.
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)

    if n < 10:
        return {
            "model": "INSUFFICIENT_DATA",
            "sample_size": n,
            "conditional_volatility": None,
            "annualized_volatility": None,
            "long_run_volatility": None,
            "alpha": None,
            "beta": None,
            "omega": None,
            "persistence": None
        }

    demeaned = r - np.mean(r)
    uncond_var = np.var(demeaned, ddof=1)
    if uncond_var <= 1e-12:
        uncond_var = 1e-6

    # If sample is small, apply EWMA directly
    if n < 30:
        lam = 0.94
        variances = np.zeros(n)
        variances[0] = uncond_var
        for t in range(1, n):
            variances[t] = lam * variances[t - 1] + (1 - lam) * (demeaned[t - 1] ** 2)
        curr_vol = math.sqrt(variances[-1])
        ann_vol = curr_vol * math.sqrt(trading_days) if annualized else curr_vol
        return {
            "model": "EWMA_FALLBACK",
            "sample_size": n,
            "conditional_volatility": float(curr_vol),
            "annualized_volatility": float(ann_vol),
            "long_run_volatility": float(math.sqrt(uncond_var * trading_days)),
            "alpha": 1.0 - lam,
            "beta": lam,
            "omega": float(uncond_var * (1.0 - lam)),
            "persistence": 1.0
        }

    # Variance targeting parameter optimization for (alpha, beta)
    def negative_log_likelihood(params):
        alpha, beta = params
        if alpha < 0 or beta < 0 or (alpha + beta) >= 0.999:
            return 1e10
        omega = uncond_var * (1.0 - alpha - beta)
        sigma2 = np.zeros(n)
        sigma2[0] = uncond_var
        for t in range(1, n):
            sigma2[t] = omega + alpha * (demeaned[t - 1] ** 2) + beta * sigma2[t - 1]
            if sigma2[t] <= 1e-12:
                sigma2[t] = 1e-12

        ll = -0.5 * np.sum(np.log(2 * np.pi) + np.log(sigma2) + (demeaned ** 2) / sigma2)
        return -ll

    init_params = [0.08, 0.90]
    bounds = [(1e-4, 0.35), (0.50, 0.99)]

    res = minimize(
        negative_log_likelihood,
        init_params,
        method="L-BFGS-B",
        bounds=bounds,
        options={"maxiter": 200, "ftol": 1e-6}
    )

    if res.success and (res.x[0] + res.x[1]) < 1.0:
        alpha, beta = float(res.x[0]), float(res.x[1])
        model_name = "GARCH(1,1)"
    else:
        # Fall back to standard empirical parameters
        alpha, beta = 0.06, 0.92
        model_name = "GARCH(1,1)_ROBUST"

    persistence = alpha + beta
    omega = float(uncond_var * (1.0 - persistence))

    # Compute filtered conditional variances
    sigma2 = np.zeros(n)
    sigma2[0] = uncond_var
    for t in range(1, n):
        sigma2[t] = omega + alpha * (demeaned[t - 1] ** 2) + beta * sigma2[t - 1]

    current_cond_var = float(sigma2[-1])
    current_cond_vol = math.sqrt(max(current_cond_var, 1e-12))
    long_run_var = omega / (1.0 - persistence) if persistence < 1.0 else uncond_var
    long_run_vol = math.sqrt(max(long_run_var, 1e-12))

    ann_cond_vol = current_cond_vol * math.sqrt(trading_days) if annualized else current_cond_vol
    ann_long_run_vol = long_run_vol * math.sqrt(trading_days) if annualized else long_run_vol

    return {
        "model": model_name,
        "sample_size": n,
        "conditional_volatility": float(current_cond_vol),
        "annualized_volatility": float(ann_cond_vol),
        "long_run_volatility": float(ann_long_run_vol),
        "alpha": round(alpha, 4),
        "beta": round(beta, 4),
        "omega": round(omega, 8),
        "persistence": round(persistence, 4),
        "current_variance": float(current_cond_var)
    }


def calculate_var_cvar(
    returns: np.ndarray,
    confidence_levels: Tuple[float, ...] = (0.95, 0.99)
) -> Dict[str, Any]:
    """
    Computes Historical VaR/CVaR, Parametric Gaussian VaR/CVaR, and Cornish-Fisher VaR
    which adjusts for empirical third (skewness) and fourth (excess kurtosis) moments.
    Returns percentages representing maximum expected loss over a 1-day holding period.
    """
    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)

    if n < 10:
        return {"error": "Insufficient data (minimum 10 returns required)", "sample_size": n}

    mu = float(np.mean(r))
    sigma = float(np.std(r, ddof=1))
    skew = float(stats.skew(r)) if n >= 20 else 0.0
    kurt = float(stats.kurtosis(r)) if n >= 20 else 0.0  # Excess kurtosis

    results: Dict[str, Any] = {
        "sample_size": n,
        "mean_daily_return": round(mu, 6),
        "daily_volatility": round(sigma, 6),
        "skewness": round(skew, 4),
        "excess_kurtosis": round(kurt, 4),
        "levels": {}
    }

    sorted_r = np.sort(r)

    for cl in confidence_levels:
        alpha = 1.0 - cl
        # 1. Historical VaR & CVaR
        idx = int(math.floor(alpha * n))
        idx = max(0, min(idx, n - 1))
        hist_var = -float(sorted_r[idx])  # Loss is positive
        tail_losses = -sorted_r[:idx + 1]
        hist_cvar = float(np.mean(tail_losses)) if len(tail_losses) > 0 else hist_var

        # 2. Parametric Gaussian VaR & CVaR
        z = float(stats.norm.ppf(cl))
        param_var = -(mu - z * sigma)
        pdf_z = float(stats.norm.pdf(z))
        param_cvar = -(mu - sigma * (pdf_z / alpha))

        # 3. Cornish-Fisher expansion VaR
        # z_cf = z + (z^2 - 1)*skew/6 + (z^3 - 3z)*kurt/24 - (2z^3 - 5z)*skew^2/36
        z_cf = z + ((z**2 - 1.0) * skew / 6.0) + \
               ((z**3 - 3.0 * z) * kurt / 24.0) - \
               ((2.0 * z**3 - 5.0 * z) * (skew**2) / 36.0)
        cf_var = -(mu - z_cf * sigma)

        results["levels"][f"{int(cl * 100)}%"] = {
            "historical_var": round(hist_var, 6),
            "historical_cvar": round(hist_cvar, 6),
            "parametric_var": round(param_var, 6),
            "parametric_cvar": round(param_cvar, 6),
            "cornish_fisher_var": round(cf_var, 6)
        }

    return results


def calculate_volatility_cones(
    current_price: float,
    returns: np.ndarray,
    horizons: List[int] = [5, 20, 60],
    confidence_levels: List[float] = [0.80, 0.95],
    trading_days: int = TRADING_DAYS_PER_YEAR
) -> Dict[str, Any]:
    """
    Computes dynamic forward price cones / confidence intervals using GARCH(1,1)
    conditional volatility and lognormal diffusion over horizons T (in trading sessions).

    Cone intervals:
        Price_t = S_0 * exp( (mu - 0.5*sigma^2)*dt +/- Z * sigma * sqrt(dt) )
    """
    if current_price <= 0:
        return {"error": "Invalid current price"}

    r = np.asarray(returns, dtype=float)
    r = r[~np.isnan(r)]
    n = len(r)

    if n < 10:
        return {"error": "Insufficient returns for volatility cone projection"}

    garch = estimate_garch11(r, annualized=True, trading_days=trading_days)
    ann_vol = garch.get("annualized_volatility")
    if not ann_vol or ann_vol <= 0:
        ann_vol = float(np.std(r, ddof=1) * math.sqrt(trading_days))

    daily_mu = float(np.mean(r))
    ann_drift = daily_mu * trading_days

    cones = {}
    for h in horizons:
        dt = h / float(trading_days)
        expected_price = current_price * math.exp(ann_drift * dt)
        h_dict = {
            "trading_days": h,
            "expected_price": round(expected_price, 2),
            "intervals": {}
        }
        for cl in confidence_levels:
            z = float(stats.norm.ppf(0.5 + cl / 2.0))
            diffusion_scale = ann_vol * math.sqrt(dt)
            drift_term = (ann_drift - 0.5 * (ann_vol ** 2)) * dt

            lower = current_price * math.exp(drift_term - z * diffusion_scale)
            upper = current_price * math.exp(drift_term + z * diffusion_scale)

            h_dict["intervals"][f"{int(cl * 100)}%"] = {
                "lower_bound": round(lower, 2),
                "upper_bound": round(upper, 2),
                "lower_pct_change": round((lower - current_price) / current_price * 100.0, 2),
                "upper_pct_change": round((upper - current_price) / current_price * 100.0, 2)
            }
        cones[f"{h}d"] = h_dict

    return {
        "current_price": round(current_price, 2),
        "annualized_volatility": round(ann_vol, 4),
        "annualized_drift": round(ann_drift, 4),
        "garch_model": garch.get("model"),
        "horizons": cones
    }
