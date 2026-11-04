"""
Market Intelligence Lab: Portfolio Performance & Risk Attribution Engine
Milestone: B8.0 (Multi-Factor Strategy Backtesting & Portfolio Rebalancing Engine)

Computes institutional risk-adjusted return analytics against NIFTY 50 TRI benchmark:
- CAGR %, Annualized Volatility %, Sharpe Ratio (Rf = 6.5%), Sortino Ratio
- Maximum Drawdown (MDD %) and Peak-to-Trough Drawdown Duration
- Jensen's Alpha % and Market Beta via OLS regression
- Portfolio Turnover % and Win Rate %
- Transaction Friction Breakdown (STT, DP charges, turnover fees, slippage drag)
"""

import math
from typing import Dict, List, Any, Optional
import numpy as np
import pandas as pd


class PerformanceMetricsCalculator:
    """
    Computes portfolio and benchmark performance metrics from daily equity curves
    and rebalance event audit logs.
    """

    DEFAULT_RF = 0.065  # 6.5% annual risk-free proxy (RBI repo rate)

    @classmethod
    def calculate_metrics(
        cls,
        equity_curve: List[Dict[str, Any]],
        rebalance_records: Optional[List[Dict[str, Any]]] = None,
        rf: float = DEFAULT_RF
    ) -> Dict[str, Any]:
        """
        Calculates all institutional performance metrics for the portfolio and benchmark.
        """
        if not equity_curve or len(equity_curve) < 2:
            return cls._empty_metrics()

        df = pd.DataFrame(equity_curve)
        df["trading_date"] = pd.to_datetime(df["trading_date"])
        df = df.sort_values("trading_date").reset_index(drop=True)

        v_series = df["portfolio_value"].astype(float)
        b_series = df["benchmark_value"].astype(float)

        n_days = len(df)
        start_date = df["trading_date"].iloc[0]
        end_date = df["trading_date"].iloc[-1]
        calendar_days = max((end_date - start_date).days, 1)
        years = calendar_days / 365.25

        # 1. Daily Returns
        p_returns = v_series.pct_change().dropna()
        b_returns = b_series.pct_change().dropna()

        # 2. CAGR
        v_initial = v_series.iloc[0]
        v_final = v_series.iloc[-1]
        cagr = ((v_final / v_initial) ** (1.0 / years) - 1.0) if (years > 0 and v_initial > 0) else 0.0

        b_initial = b_series.iloc[0]
        b_final = b_series.iloc[-1]
        b_cagr = ((b_final / b_initial) ** (1.0 / years) - 1.0) if (years > 0 and b_initial > 0) else 0.0

        # 3. Annualized Volatility
        p_vol = float(p_returns.std() * math.sqrt(252)) if len(p_returns) > 1 else 0.0
        b_vol = float(b_returns.std() * math.sqrt(252)) if len(b_returns) > 1 else 0.0

        # 4. Sharpe Ratio
        p_sharpe = ((cagr - rf) / p_vol) if p_vol > 0 else 0.0
        b_sharpe = ((b_cagr - rf) / b_vol) if b_vol > 0 else 0.0

        # 5. Sortino Ratio
        daily_rf = rf / 252.0
        p_downside = p_returns[p_returns < daily_rf] - daily_rf
        p_downside_dev = float(math.sqrt((p_downside ** 2).mean() * 252)) if len(p_downside) > 0 else 0.0
        p_sortino = ((cagr - rf) / p_downside_dev) if p_downside_dev > 0 else 0.0

        b_downside = b_returns[b_returns < daily_rf] - daily_rf
        b_downside_dev = float(math.sqrt((b_downside ** 2).mean() * 252)) if len(b_downside) > 0 else 0.0
        b_sortino = ((b_cagr - rf) / b_downside_dev) if b_downside_dev > 0 else 0.0

        # 6. Drawdown & Duration
        cummax = v_series.cummax()
        drawdowns = (v_series - cummax) / cummax
        max_drawdown = float(drawdowns.min())

        b_cummax = b_series.cummax()
        b_drawdowns = (b_series - b_cummax) / b_cummax
        b_max_drawdown = float(b_drawdowns.min())

        # Drawdown duration (max calendar days in continuous underwater state)
        mdd_duration_days = 0
        current_dd_start = None
        for idx, dd in enumerate(drawdowns):
            if dd < 0:
                if current_dd_start is None:
                    current_dd_start = df["trading_date"].iloc[idx]
                dur = (df["trading_date"].iloc[idx] - current_dd_start).days
                if dur > mdd_duration_days:
                    mdd_duration_days = dur
            else:
                current_dd_start = None

        # 7. Alpha & Beta via OLS vs NIFTY 50
        beta = 1.0
        alpha_ann = 0.0
        if len(p_returns) > 10 and len(b_returns) > 10 and b_returns.var() > 1e-8:
            covariance = np.cov(p_returns, b_returns)[0, 1]
            b_var = b_returns.var()
            beta = float(covariance / b_var) if b_var > 0 else 1.0
            daily_alpha = float(p_returns.mean() - beta * b_returns.mean())
            alpha_ann = float(daily_alpha * 252)

        # 8. Win Rate & Rebalance Friction
        win_rate_pct = 50.0
        total_friction = 0.0
        total_stt = 0.0
        total_dp = 0.0
        total_turnover_charges = 0.0
        total_slippage = 0.0
        turnover_annualized = 0.0

        if rebalance_records:
            profitable_periods = 0
            total_turnover_traded = 0.0
            rebalance_count = len(rebalance_records)

            for reb in rebalance_records:
                total_friction += float(reb.get("friction_inr", 0.0))
                total_stt += float(reb.get("stt_inr", 0.0))
                total_dp += float(reb.get("dp_charges_inr", 0.0))
                total_turnover_charges += float(reb.get("turnover_charges_inr", 0.0))
                total_slippage += float(reb.get("slippage_drag_inr", 0.0))
                total_turnover_traded += float(reb.get("turnover_traded_inr", 0.0))
                if float(reb.get("period_net_return_pct", 0.0)) > 0:
                    profitable_periods += 1

            if rebalance_count > 0:
                win_rate_pct = (profitable_periods / rebalance_count) * 100.0
                avg_portfolio_value = v_series.mean() if len(v_series) > 0 else v_initial
                if years > 0 and avg_portfolio_value > 0:
                    turnover_annualized = (total_turnover_traded / (2.0 * avg_portfolio_value)) / years * 100.0
        else:
            # Fallback win rate from daily positive returns
            pos_days = (p_returns > 0).sum()
            win_rate_pct = float(pos_days / len(p_returns) * 100.0) if len(p_returns) > 0 else 50.0

        return {
            "portfolio": {
                "initial_value": round(v_initial, 2),
                "final_value": round(v_final, 2),
                "total_return_pct": round(((v_final / v_initial) - 1.0) * 100.0, 2),
                "cagr_pct": round(cagr * 100.0, 2),
                "annualized_volatility_pct": round(p_vol * 100.0, 2),
                "sharpe_ratio": round(p_sharpe, 2),
                "sortino_ratio": round(p_sortino, 2),
                "max_drawdown_pct": round(abs(max_drawdown) * 100.0, 2),
                "mdd_duration_days": int(mdd_duration_days),
                "alpha_pct": round(alpha_ann * 100.0, 2),
                "beta": round(beta, 2),
                "win_rate_pct": round(win_rate_pct, 2),
                "turnover_pct": round(turnover_annualized, 2),
                "total_friction_inr": round(total_friction, 2),
                "stt_paid_inr": round(total_stt, 2),
                "dp_charges_paid_inr": round(total_dp, 2),
                "turnover_charges_paid_inr": round(total_turnover_charges, 2),
                "slippage_cost_inr": round(total_slippage, 2),
            },
            "benchmark": {
                "initial_value": round(b_initial, 2),
                "final_value": round(b_final, 2),
                "total_return_pct": round(((b_final / b_initial) - 1.0) * 100.0, 2),
                "cagr_pct": round(b_cagr * 100.0, 2),
                "annualized_volatility_pct": round(b_vol * 100.0, 2),
                "sharpe_ratio": round(b_sharpe, 2),
                "sortino_ratio": round(b_sortino, 2),
                "max_drawdown_pct": round(abs(b_max_drawdown) * 100.0, 2),
            },
            "simulation": {
                "start_date": str(start_date)[:10],
                "end_date": str(end_date)[:10],
                "total_trading_days": n_days,
                "calendar_years": round(years, 2),
                "risk_free_rate_pct": round(rf * 100.0, 2)
            }
        }

    @staticmethod
    def _empty_metrics() -> Dict[str, Any]:
        return {
            "portfolio": {
                "initial_value": 0.0,
                "final_value": 0.0,
                "total_return_pct": 0.0,
                "cagr_pct": 0.0,
                "annualized_volatility_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "mdd_duration_days": 0,
                "alpha_pct": 0.0,
                "beta": 1.0,
                "win_rate_pct": 0.0,
                "turnover_pct": 0.0,
                "total_friction_inr": 0.0,
                "stt_paid_inr": 0.0,
                "dp_charges_paid_inr": 0.0,
                "turnover_charges_paid_inr": 0.0,
                "slippage_cost_inr": 0.0,
            },
            "benchmark": {
                "initial_value": 0.0,
                "final_value": 0.0,
                "total_return_pct": 0.0,
                "cagr_pct": 0.0,
                "annualized_volatility_pct": 0.0,
                "sharpe_ratio": 0.0,
                "sortino_ratio": 0.0,
                "max_drawdown_pct": 0.0,
            },
            "simulation": {
                "start_date": "",
                "end_date": "",
                "total_trading_days": 0,
                "calendar_years": 0.0,
                "risk_free_rate_pct": 6.5
            }
        }
