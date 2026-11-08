"""
src/api/routes_backtest.py
Systematic Walk-Forward Portfolio Backtest REST API Router.
Workstream 9.0: Parameterized multi-horizon simulations, institutional tearsheet metrics,
and interactive visualization data feeds.
"""

import logging
from typing import Dict, Any, List, Optional
import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH, sanitize_for_json
from src.quant.portfolio_backtester import PortfolioBacktester

logger = logging.getLogger("MIL.BacktestAPI")

router = APIRouter(prefix="/api/v1/backtest", tags=["backtest"])


class PortfolioBacktestRequest(BaseModel):
    start_date: Optional[str] = Field(default=None, description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default=None, description="End date (YYYY-MM-DD)")
    initial_capital: float = Field(default=1000000.0, ge=10000.0, le=100000000.0, description="Virtual starting capital in INR")
    top_n: int = Field(default=15, ge=5, le=30, description="Portfolio basket size")
    rebalance_cadence: Optional[int] = Field(default=None, ge=5, le=60, description="Rebalance cadence in trading sessions")
    rebalance_every_n_days: Optional[int] = Field(default=20, ge=5, le=60, description="Rebalance cadence in trading sessions")
    strategy_mode: str = Field(default="BLENDED_20D_60D", description="BLENDED_20D_60D, TACTICAL_20D, or TREND_60D")
    hysteresis_buffer: float = Field(default=5.0, ge=0.0, le=20.0, description="Turnover hysteresis inertia bonus")
    enable_dynamic_cash: bool = Field(default=True, description="Market breadth dynamic cash modulation")
    cash_hurdle_rate: float = Field(default=0.065, ge=0.0, le=0.15, description="Annual risk-free cash hurdle yield")


class MultiStockCompareRequest(BaseModel):
    symbols: List[str] = Field(default=["TCS", "INFY", "HCLTECH"], min_length=1, max_length=10, description="Symbols to compare")
    start_date: Optional[str] = Field(default="2021-01-04", description="Start date (YYYY-MM-DD)")
    end_date: Optional[str] = Field(default="2026-11-06", description="End date (YYYY-MM-DD)")
    benchmark_symbol: Optional[str] = Field(default="^NSEI", description="Benchmark symbol")


@router.get("/presets")
def get_backtest_presets():
    """Returns available strategy regimes, default parameters, and historical date boundaries."""
    try:
        db = DatabaseManager(DATABASE_PATH)
        tester = PortfolioBacktester(db)
        bounds = tester.get_available_date_bounds()

        return sanitize_for_json({
            "strategy_modes": [
                {
                    "id": "BLENDED_20D_60D",
                    "name": "Institutional Blended (62.5% Tactical + 37.5% Trend)",
                    "description": "Combines 20D tactical excess return momentum with 60D structural trend filtering and dynamic hurdle gating."
                },
                {
                    "id": "TACTICAL_20D",
                    "name": "Tactical Swing (20D Momentum Champion)",
                    "description": "100% allocation driven by the 20-day walk-forward champion model (IC=0.0349, Sharpe=1.42)."
                },
                {
                    "id": "TREND_60D",
                    "name": "Structural Trend (60D Low-Beta Champion)",
                    "description": "100% allocation driven by the 60-day trend-following champion model (IC=0.0260)."
                }
            ],
            "top_n_options": [10, 15, 20],
            "frequency_options": [
                {"label": "10 Days (Bi-Weekly)", "value": 10},
                {"label": "20 Days (Monthly)", "value": 20},
                {"label": "60 Days (Quarterly)", "value": 60}
            ],
            "default_config": {
                "initial_capital": 1000000.0,
                "top_n": 15,
                "rebalance_every_n_days": 20,
                "strategy_mode": "BLENDED_20D_60D",
                "start_date": bounds["start_date"],
                "end_date": bounds["end_date"]
            },
            "date_bounds": bounds
        })
    except Exception as e:
        logger.error(f"Error fetching backtest presets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch backtest presets: {str(e)}")


@router.post("/run")
@router.post("/portfolio")
def run_portfolio_backtest(req: PortfolioBacktestRequest = Body(...)):
    """
    Executes walk-forward systematic portfolio simulation and returns
    full tearsheet risk metrics, dual equity curves, underwater drawdown series,
    and historical rebalance logs.
    """
    try:
        db = DatabaseManager(DATABASE_PATH)
        tester = PortfolioBacktester(db)
        cadence = req.rebalance_cadence or req.rebalance_every_n_days or 20
        result = tester.run_backtest(
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            top_n=req.top_n,
            rebalance_cadence=cadence,
            rebalance_every_n_days=cadence,
            strategy_mode=req.strategy_mode,
            apply_friction=True,
            hysteresis_buffer=req.hysteresis_buffer,
            enable_dynamic_cash=req.enable_dynamic_cash,
            cash_hurdle_rate=req.cash_hurdle_rate
        )
        return sanitize_for_json(result)
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        logger.error(f"Backtest simulation failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest failed: {str(e)}")


@router.post("/compare")
def compare_multi_stock(req: MultiStockCompareRequest = Body(...)):
    """
    Executes cross-sectional comparison across multiple equities:
    - Base-100 normalized equity curves vs NIFTY 50 benchmark
    - Comparative risk and return metrics (CAGR, Volatility, Sharpe, Drawdown, Beta)
    - Pairwise daily return correlation matrix
    - Radar factor percentile profile (Quality, Momentum, Trend, Volatility)
    """
    try:
        symbols = [s.strip().upper() for s in req.symbols if s.strip()]
        if not symbols:
            raise HTTPException(status_code=400, detail="At least one valid symbol must be provided.")

        start_d = req.start_date or "2021-01-04"
        end_d = req.end_date or "2026-11-06"
        bench_sym = req.benchmark_symbol or "^NSEI"

        db = DatabaseManager(DATABASE_PATH)
        tester = PortfolioBacktester(db)

        # 1. Fetch benchmark price series
        trading_dates = tester._get_trading_calendar(start_d, end_d)
        if len(trading_dates) < 5:
            raise HTTPException(status_code=400, detail=f"Insufficient trading sessions between {start_d} and {end_d}.")

        bench_curve_raw = tester._build_benchmark_curve(trading_dates, initial_capital=100.0)

        # 2. Fetch prices for requested symbols
        placeholders = ",".join("?" for _ in symbols)
        with db.get_connection() as conn:
            cur = conn.execute(f"""
                SELECT symbol, trading_date, adj_close
                FROM factors_daily
                WHERE symbol IN ({placeholders})
                  AND trading_date >= ? AND trading_date <= ?
                ORDER BY trading_date ASC
            """, (*symbols, start_d, end_d))
            rows = cur.fetchall()

        # Fallback to ohlcv_daily if factors_daily empty for any symbols
        sym_price_map: Dict[str, Dict[str, float]] = {s: {} for s in symbols}
        for r in rows:
            sym_price_map[str(r[0])][str(r[1])] = float(r[2])

        missing_symbols = [s for s in symbols if not sym_price_map[s]]
        if missing_symbols:
            with db.get_connection() as conn:
                cur = conn.execute(f"""
                    SELECT symbol, trading_date, close
                    FROM ohlcv_daily
                    WHERE symbol IN ({",".join("?" for _ in missing_symbols)})
                      AND trading_date >= ? AND trading_date <= ?
                      AND series = 'EQ' AND COALESCE(is_synthetic, 0) = 0
                    ORDER BY trading_date ASC
                """, (*missing_symbols, start_d, end_d))
                for r in cur.fetchall():
                    sym_price_map[str(r[0])][str(r[1])] = float(r[2])

        # 3. Construct Base-100 Normalized Series
        normalized_series: List[Dict[str, Any]] = []
        base_prices: Dict[str, Optional[float]] = {s: None for s in symbols}
        base_bench = bench_curve_raw.get(trading_dates[0], 100.0)

        # Keep running prices for metric calculation
        running_prices: Dict[str, List[float]] = {s: [] for s in symbols}
        bench_prices_list: List[float] = []

        for d in trading_dates:
            entry: Dict[str, Any] = {"date": d, "trading_date": d}

            # Benchmark base 100
            b_val = bench_curve_raw.get(d, base_bench)
            entry["BENCHMARK"] = round((b_val / base_bench) * 100.0, 2) if base_bench > 0 else 100.0
            bench_prices_list.append(b_val)

            for s in symbols:
                p = sym_price_map[s].get(d)
                if p is not None and p > 0:
                    if base_prices[s] is None:
                        base_prices[s] = p
                    norm_val = round((p / base_prices[s]) * 100.0, 2)
                    entry[s] = norm_val
                    running_prices[s].append(p)
                else:
                    # Carry forward previous normalized value if already started
                    if base_prices[s] is not None and running_prices[s]:
                        last_p = running_prices[s][-1]
                        entry[s] = round((last_p / base_prices[s]) * 100.0, 2)
                    else:
                        entry[s] = None

            normalized_series.append(entry)

        # 4. Compute Performance & Risk Metrics
        comparison_metrics: Dict[str, Any] = {}
        rf_annual = 0.065
        years = len(trading_dates) / 252.0 if len(trading_dates) > 0 else 1.0

        # Benchmark metrics
        b_ret_series = pd.Series(bench_prices_list).pct_change().dropna()
        b_total_ret = ((bench_prices_list[-1] / bench_prices_list[0]) - 1.0) * 100.0 if bench_prices_list else 0.0
        b_cagr = (((bench_prices_list[-1] / bench_prices_list[0]) ** (1.0 / max(years, 0.1))) - 1.0) * 100.0 if bench_prices_list else 0.0
        b_vol = float(b_ret_series.std() * np.sqrt(252.0) * 100.0) if len(b_ret_series) > 1 else 0.0
        b_sharpe = float((b_cagr / 100.0 - rf_annual) / (b_vol / 100.0)) if b_vol > 0 else 0.0

        b_peaks = pd.Series(bench_prices_list).cummax()
        b_dds = (pd.Series(bench_prices_list) - b_peaks) / b_peaks * 100.0
        b_mdd = float(abs(b_dds.min())) if len(b_dds) > 0 else 0.0

        comparison_metrics["BENCHMARK"] = {
            "symbol": "NIFTY 50",
            "total_return_pct": round(b_total_ret, 2),
            "cagr_pct": round(b_cagr, 2),
            "annualized_volatility_pct": round(b_vol, 2),
            "sharpe_ratio": round(b_sharpe, 2),
            "max_drawdown_pct": round(b_mdd, 2),
            "beta_to_bench": 1.0
        }

        # Per symbol metrics
        daily_returns_dict: Dict[str, pd.Series] = {}

        for s in symbols:
            p_list = running_prices[s]
            if len(p_list) < 5:
                comparison_metrics[s] = {
                    "symbol": s,
                    "total_return_pct": 0.0,
                    "cagr_pct": 0.0,
                    "annualized_volatility_pct": 0.0,
                    "sharpe_ratio": 0.0,
                    "max_drawdown_pct": 0.0,
                    "beta_to_bench": 1.0
                }
                daily_returns_dict[s] = pd.Series(dtype=float)
                continue

            p_s = pd.Series(p_list)
            r_s = p_s.pct_change().dropna()
            daily_returns_dict[s] = r_s

            tot_ret = ((p_list[-1] / p_list[0]) - 1.0) * 100.0
            cagr = (((p_list[-1] / p_list[0]) ** (1.0 / max(years, 0.1))) - 1.0) * 100.0
            vol = float(r_s.std() * np.sqrt(252.0) * 100.0) if len(r_s) > 1 else 0.0
            sharpe = float((cagr / 100.0 - rf_annual) / (vol / 100.0)) if vol > 0 else 0.0

            peaks = p_s.cummax()
            dds = (p_s - peaks) / peaks * 100.0
            mdd = float(abs(dds.min())) if len(dds) > 0 else 0.0

            # Beta vs benchmark
            if len(r_s) == len(b_ret_series) and b_ret_series.var() > 1e-8:
                cov = float(np.cov(r_s, b_ret_series)[0, 1])
                beta = float(cov / b_ret_series.var())
            else:
                beta = 1.0

            comparison_metrics[s] = {
                "symbol": s,
                "total_return_pct": round(tot_ret, 2),
                "cagr_pct": round(cagr, 2),
                "annualized_volatility_pct": round(vol, 2),
                "sharpe_ratio": round(sharpe, 2),
                "max_drawdown_pct": round(mdd, 2),
                "beta_to_bench": round(beta, 2)
            }

        # 5. Pairwise Correlation Matrix
        corr_matrix: Dict[str, Dict[str, float]] = {}
        for s1 in symbols:
            corr_matrix[s1] = {}
            for s2 in symbols:
                if s1 == s2:
                    corr_matrix[s1][s2] = 1.00
                else:
                    r1 = daily_returns_dict.get(s1)
                    r2 = daily_returns_dict.get(s2)
                    if r1 is not None and r2 is not None and len(r1) > 10 and len(r2) > 10:
                        min_l = min(len(r1), len(r2))
                        val = float(r1.iloc[-min_l:].corr(r2.iloc[-min_l:]))
                        corr_matrix[s1][s2] = round(val if not np.isnan(val) else 0.0, 2)
                    else:
                        corr_matrix[s1][s2] = 0.50

        # 6. Radar Factor Percentiles
        radar_scores: Dict[str, Dict[str, float]] = {}
        with db.get_connection() as conn:
            cur = conn.execute(f"""
                SELECT f.symbol, COALESCE(q.roe_pct, 15.0), f.momentum_1y, f.volatility_20d, f.trend_regime
                FROM factors_daily f
                LEFT JOIN quant_factors_daily q ON f.symbol = q.symbol AND f.trading_date = q.trading_date
                WHERE f.symbol IN ({placeholders})
                ORDER BY f.trading_date DESC
            """, (*symbols,))
            seen_syms = set()
            for r in cur.fetchall():
                sym = str(r[0])
                if sym in seen_syms:
                    continue
                seen_syms.add(sym)
                roe = float(r[1]) if r[1] is not None else 15.0
                mom = float(r[2]) if r[2] is not None else 10.0
                vol = float(r[3]) if r[3] is not None else 25.0
                reg = str(r[4]) if r[4] is not None else "NEUTRAL"

                # Map to 0-100 scores
                q_score = min(100.0, max(10.0, roe * 3.5))
                m_score = min(100.0, max(10.0, 50.0 + mom * 0.8))
                t_score = 90.0 if "BULL" in reg else (30.0 if "BEAR" in reg else 55.0)
                v_score = min(100.0, max(10.0, 100.0 - vol * 1.8))

                radar_scores[sym] = {
                    "quality": round(q_score, 1),
                    "momentum": round(m_score, 1),
                    "trend": round(t_score, 1),
                    "volatility": round(v_score, 1)
                }

        # Fill any missing
        for s in symbols:
            if s not in radar_scores:
                radar_scores[s] = {"quality": 60.0, "momentum": 55.0, "trend": 65.0, "volatility": 50.0}

        return sanitize_for_json({
            "start_date": start_d,
            "end_date": end_d,
            "benchmark_symbol": bench_sym,
            "symbols": symbols,
            "normalized_series": normalized_series,
            "comparison_metrics": comparison_metrics,
            "correlation_matrix": corr_matrix,
            "radar_scores": radar_scores
        })

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in multi-stock comparison API: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Comparison failed: {str(e)}")
