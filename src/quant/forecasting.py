"""
Market Intelligence Lab — Econometric Forecasting Engine (Milestone B7.0).

Provides walk-forward econometric forecasting with conditional volatility modeling
(GARCH 1,1 / EWMA) and Ornstein-Uhlenbeck mean-reverting drift projections.
Generates multi-horizon probabilistic confidence fan cones (80% and 95% envelopes)
without black-box ML or look-ahead data leakage.
"""

import math
import logging
import datetime
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.storage.database import DatabaseManager
from src.api.utils import sanitize_for_json

logger = logging.getLogger(__name__)


class EconometricForecaster:
    """
    Multi-horizon econometric forecasting engine based on GARCH(1,1) conditional volatility
    and Ornstein-Uhlenbeck mean-reversion drift dynamics.
    Strictly adheres to walk-forward data partitioning (t <= T_cutoff).
    """

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()

    @staticmethod
    def get_forward_trading_dates(start_date_str: str, num_days: int) -> List[str]:
        """
        Generates forward trading session dates starting after start_date_str,
        skipping weekends (Saturdays and Sundays).
        """
        start_date = datetime.date.fromisoformat(start_date_str)
        trading_dates = []
        curr = start_date

        while len(trading_dates) < num_days:
            curr += datetime.timedelta(days=1)
            # Skip weekends (5=Sat, 6=Sun)
            if curr.weekday() < 5:
                trading_dates.append(curr.isoformat())

        return trading_dates

    @staticmethod
    def fit_garch11(returns: np.ndarray) -> Tuple[float, float, float]:
        """
        Calibrates GARCH(1,1) variance parameters (omega, alpha, beta):
        sigma_{t+1}^2 = omega + alpha * eps_t^2 + beta * sigma_t^2
        
        Enforces strict constraints:
        - omega > 0
        - alpha >= 0
        - beta >= 0
        - alpha + beta < 1.0 (strict covariance stationarity)
        
        Uses variance targeting reparameterization with L-BFGS-B,
        falling back to analytical EWMA (RiskMetrics lambda=0.94) if optimization fails.
        """
        n = len(returns)
        if n < 30:
            var_sample = float(np.var(returns, ddof=1)) if n > 1 else 0.0004
            return var_sample * 0.06, 0.06, 0.88

        mu = float(np.mean(returns))
        eps = returns - mu
        var_sample = float(np.var(returns, ddof=1))
        if var_sample <= 1e-12:
            var_sample = 1e-6

        # Variance targeting objective:
        # gamma = alpha + beta in [0.50, 0.995]
        # phi = alpha / (alpha + beta) in [0.01, 0.40]
        # omega = var_sample * (1 - gamma)
        def nll(params):
            gamma, phi = params
            alpha = gamma * phi
            beta = gamma * (1.0 - phi)
            omega = var_sample * (1.0 - gamma)

            sigma2 = np.empty(n)
            sigma2[0] = var_sample
            for t in range(1, n):
                s2 = omega + alpha * (eps[t - 1] ** 2) + beta * sigma2[t - 1]
                if s2 <= 1e-12:
                    return 1e10
                sigma2[t] = s2

            # Negative log likelihood (Gaussian)
            return 0.5 * np.sum(np.log(sigma2) + (eps ** 2) / sigma2)

        try:
            init_guess = [0.94, 0.08]
            bounds = [(0.50, 0.995), (0.01, 0.40)]
            res = minimize(nll, init_guess, method="L-BFGS-B", bounds=bounds)

            if res.success and not np.isnan(res.x[0]):
                gamma, phi = res.x
                alpha = float(gamma * phi)
                beta = float(gamma * (1.0 - phi))
                omega = float(var_sample * (1.0 - gamma))
                return max(1e-12, omega), max(0.001, alpha), max(0.001, beta)
        except Exception as e:
            logger.debug(f"GARCH optimization fallback to EWMA: {e}")

        # Analytical EWMA fallback (RiskMetrics lambda=0.94)
        alpha = 0.06
        beta = 0.92
        omega = var_sample * (1.0 - (alpha + beta))
        return max(1e-12, omega), alpha, beta

    def generate_forecast(
        self,
        symbol: str,
        horizon_days: int = 20,
        cutoff_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Produces multi-horizon econometric forecast:
        - Filters historical bars strictly to t <= cutoff_date (Zero Look-ahead Bias).
        - Computes GARCH conditional volatility forward term structure.
        - Computes Ornstein-Uhlenbeck drift trajectory toward long-term moving averages.
        - Calculates 80% and 95% probabilistic confidence cones.
        """
        sym = symbol.strip().upper()
        h_days = min(max(1, int(horizon_days)), 60)

        # 1. Fetch historical OHLCV bars strictly up to cutoff_date
        query = """
            SELECT trading_date, close, open, high, low, volume
            FROM ohlcv_daily
            WHERE symbol = ?
        """
        params: List[Any] = [sym]

        if cutoff_date:
            query += " AND trading_date <= ?"
            params.append(cutoff_date)

        query += " ORDER BY trading_date ASC"

        with self.db.get_connection() as conn:
            cursor = conn.execute(query, tuple(params))
            rows = cursor.fetchall()

        if len(rows) < 126:
            raise ValueError(
                f"Insufficient historical data for symbol '{sym}': "
                f"found {len(rows)} bars, minimum 126 required for econometric calibration."
            )

        trading_dates = [r["trading_date"] for r in rows]
        closes = np.array([float(r["close"]) for r in rows], dtype=float)

        as_of_date = trading_dates[-1]
        current_close = float(closes[-1])

        # 2. Compute log returns strictly within window
        log_returns = np.diff(np.log(closes))
        n_returns = len(log_returns)

        # Sample variance & volatility
        var_sample = float(np.var(log_returns, ddof=1))
        annualized_vol = float(np.sqrt(var_sample * 252.0))

        # 3. Fit GARCH(1,1) model
        omega, alpha, beta = self.fit_garch11(log_returns)
        persistence = alpha + beta

        # Long-term unconditional variance
        sigma_L2 = omega / max(1e-5, (1.0 - persistence))

        # Step 1 conditional variance
        mu_ret = float(np.mean(log_returns))
        last_eps = log_returns[-1] - mu_ret
        sigma_prev2 = var_sample  # Baseline prior variance
        sigma_T1_2 = omega + alpha * (last_eps ** 2) + beta * sigma_prev2
        sigma_T1_2 = max(1e-10, sigma_T1_2)

        # 4. Volatility Regime Classification
        if annualized_vol < 0.15:
            vol_regime = "LOW"
        elif annualized_vol <= 0.32:
            vol_regime = "NORMAL"
        else:
            vol_regime = "ELEVATED"

        # 5. Drift & Ornstein-Uhlenbeck Mean Reversion Setup
        # Short-term 20-day momentum drift
        recent_window = min(20, n_returns)
        mu_20d = float(np.mean(log_returns[-recent_window:]))

        # Anchor price target: blend of 50-day and 200-day SMAs
        sma_50 = float(np.mean(closes[-min(50, len(closes)):]))
        sma_200 = float(np.mean(closes[-min(200, len(closes)):])) if len(closes) >= 200 else sma_50
        anchor_price = 0.60 * sma_50 + 0.40 * sma_200

        # Mean reversion decay constant (kappa ~ 0.05, half-life of 14 sessions)
        kappa = 0.045

        # 6. Generate Projections over Horizon
        target_dates = self.get_forward_trading_dates(as_of_date, h_days)
        projections: List[Dict[str, Any]] = []

        cum_variance = 0.0
        for step in range(1, h_days + 1):
            t_date = target_dates[step - 1]

            # GARCH conditional variance term structure: sigma_{T+h}^2
            if step == 1:
                sig2_h = sigma_T1_2
            else:
                sig2_h = sigma_L2 + (persistence ** (step - 1)) * (sigma_T1_2 - sigma_L2)

            sig2_h = max(1e-10, sig2_h)
            cum_variance += sig2_h
            cum_std = math.sqrt(cum_variance)

            # Expected path via OU process in log-space
            weight_curr = math.exp(-kappa * step)
            drift_term = mu_20d * ((1.0 - weight_curr) / kappa) if kappa > 0 else mu_20d * step
            expected_log_p = (
                weight_curr * math.log(current_close) +
                (1.0 - weight_curr) * math.log(anchor_price) +
                drift_term
            )
            expected_price = math.exp(expected_log_p)

            # Probabilistic Fan Cones (80% CI: z=1.282, 95% CI: z=1.960)
            spread_80 = 1.282 * expected_price * cum_std
            spread_95 = 1.960 * expected_price * cum_std

            upper_80 = round(expected_price + spread_80, 2)
            lower_80 = round(max(0.01, expected_price - spread_80), 2)
            upper_95 = round(expected_price + spread_95, 2)
            lower_95 = round(max(0.01, expected_price - spread_95), 2)
            exp_rounded = round(expected_price, 2)

            # Invariant check: upper_95 >= upper_80 >= expected >= lower_80 >= lower_95 > 0
            if upper_80 > upper_95:
                upper_95 = upper_80
            if lower_80 < lower_95:
                lower_95 = lower_80

            projections.append({
                "step": step,
                "target_date": t_date,
                "expected": exp_rounded,
                "upper_80": upper_80,
                "lower_80": lower_80,
                "upper_95": upper_95,
                "lower_95": lower_95
            })

        payload = {
            "symbol": sym,
            "as_of_date": as_of_date,
            "current_close": round(current_close, 2),
            "annualized_volatility": round(annualized_vol, 4),
            "volatility_regime": vol_regime,
            "forecast_horizon_days": h_days,
            "garch_parameters": {
                "omega": round(omega, 8),
                "alpha": round(alpha, 4),
                "beta": round(beta, 4),
                "persistence": round(persistence, 4)
            },
            "mean_reversion_anchor": round(anchor_price, 2),
            "projections": projections
        }

        return sanitize_for_json(payload)
