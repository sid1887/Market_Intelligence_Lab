from typing import List, Dict, Any, Optional
from src.storage.database import DatabaseManager
from src.quant.benchmark import (
    calculate_split_bonus_adjustment_factors,
    calculate_excess_return,
    calculate_beta,
    validate_comparison_modes,
    BenchmarkMode,
    ReturnModeMismatchError
)
from src.quant.alignment import AlignedSeries

class RelativeStrengthEngine:
    """
    Computes multi-horizon relative strength rankings, excess returns,
    and rolling 60-day beta for universe stocks against Nifty 50.
    Enforces strict Mode 1 (PRI) and Mode 2 (TRI) separation.
    Mode 2 is ONLY computed when stock corporate actions pass completeness checks.
    """

    HORIZONS = {
        "1M": 21,
        "3M": 63,
        "6M": 126,
        "1Y": 252
    }

    def __init__(self, db: DatabaseManager):
        self.db = db

    def check_corporate_actions_completeness(self, symbol: str) -> bool:
        """
        Verifies if corporate actions for symbol have been audited and loaded.
        Returns True if records exist in corporate_actions; False otherwise.
        """
        cas = self.db.get_corporate_actions(symbol)
        return len(cas) > 0

    def compute_stock_relative_strength(
        self,
        symbol: str,
        as_of_date: str,
        benchmark_name: str = "NIFTY 50",
        mode: str = BenchmarkMode.PRI
    ) -> Dict[str, Any]:
        """
        Computes 1M, 3M, 6M, 1Y returns and 60-day rolling beta for a single stock.
        """
        # Corporate Action Completeness Check for Mode 2 (Mandatory Condition 2)
        if mode == BenchmarkMode.TRI:
            is_complete = self.check_corporate_actions_completeness(symbol)
            if not is_complete:
                return {
                    "symbol": symbol,
                    "as_of_date": as_of_date,
                    "mode": BenchmarkMode.TRI,
                    "status": "UNAVAILABLE",
                    "reason": f"Corporate action history incomplete or unverified for {symbol}. Mode 2 disallowed.",
                    "metrics": None
                }

        # 1. Fetch stock history up to as_of_date
        stock_raw = self.db.get_stock_history(symbol, start_date=None, end_date=as_of_date)
        if not stock_raw:
            return {
                "symbol": symbol,
                "as_of_date": as_of_date,
                "mode": mode,
                "status": "NO_DATA",
                "metrics": None
            }

        # Apply split/bonus adjustments
        cas = self.db.get_corporate_actions(symbol)
        stock_adj = calculate_split_bonus_adjustment_factors(stock_raw, cas)

        # 2. Fetch benchmark history up to as_of_date
        bench_raw = self.db.get_index_history(benchmark_name, mode, start_date=None, end_date=as_of_date)
        if not bench_raw:
            return {
                "symbol": symbol,
                "as_of_date": as_of_date,
                "mode": mode,
                "status": "NO_BENCHMARK_DATA",
                "metrics": None
            }

        # 3. Align series on exact trading dates (Mandatory Condition 4)
        aligned = AlignedSeries.align_stock_and_benchmark(
            stock_records=stock_adj,
            benchmark_records=bench_raw,
            stock_price_key="adjusted_close",
            benchmark_value_key="close"
        )

        n_aligned = len(aligned)
        if n_aligned < 2:
            return {
                "symbol": symbol,
                "as_of_date": as_of_date,
                "mode": mode,
                "status": "INSUFFICIENT_ALIGNED_DATA",
                "metrics": None
            }

        # Enforce that the latest aligned observation matches as_of_date
        if aligned[-1]["trading_date"] != as_of_date:
            return {
                "symbol": symbol,
                "as_of_date": as_of_date,
                "mode": mode,
                "status": "BENCHMARK_DATE_MISMATCH",
                "metrics": None
            }

        # 4. Compute Horizon Returns & Excess
        horizon_metrics = {}
        for h_label, window_len in self.HORIZONS.items():
            if n_aligned > window_len:
                p_start = aligned[-window_len - 1]["stock_price"]
                p_end = aligned[-1]["stock_price"]
                b_start = aligned[-window_len - 1]["benchmark_value"]
                b_end = aligned[-1]["benchmark_value"]

                s_ret = (p_end - p_start) / p_start if p_start > 0 else 0.0
                b_ret = (b_end - b_start) / b_start if b_start > 0 else 0.0
                excess = calculate_excess_return(s_ret, mode, b_ret, mode)

                horizon_metrics[h_label] = {
                    "stock_return_pct": round(s_ret * 100.0, 2),
                    "benchmark_return_pct": round(b_ret * 100.0, 2),
                    "excess_return_pct": round(excess["excess_return"] * 100.0, 2),
                    "is_outperforming": excess["is_outperforming"],
                    "window_days": window_len
                }
            else:
                horizon_metrics[h_label] = None  # Warm-up / insufficient history

        # 5. Compute Rolling 60-Day Beta vs Benchmark
        beta_60d = None
        if n_aligned >= 61:
            recent_aligned = aligned[-61:]
            _, s_rets, b_rets = AlignedSeries.compute_aligned_returns(recent_aligned, mode, mode)
            if len(s_rets) >= 60:
                beta_val = calculate_beta(s_rets, b_rets, mode, mode)
                beta_60d = round(beta_val, 3) if beta_val is not None else None

        return {
            "symbol": symbol,
            "as_of_date": as_of_date,
            "mode": mode,
            "status": "AVAILABLE",
            "aligned_days_count": n_aligned,
            "latest_close": aligned[-1]["stock_price"],
            "beta_60d": beta_60d,
            "horizons": horizon_metrics
        }

    def generate_universe_leaderboard(
        self,
        as_of_date: str,
        symbols: List[str],
        benchmark_name: str = "NIFTY 50",
        mode: str = BenchmarkMode.PRI,
        ranking_horizon: str = "1M"
    ) -> Dict[str, Any]:
        """
        Ranks universe constituents by excess return over the specified horizon.
        """
        results = []
        for sym in symbols:
            res = self.compute_stock_relative_strength(sym, as_of_date, benchmark_name, mode)
            if res["status"] == "AVAILABLE" and res["horizons"].get(ranking_horizon):
                metrics = res["horizons"][ranking_horizon]
                results.append({
                    "symbol": sym,
                    "latest_close": res["latest_close"],
                    "stock_return_pct": metrics["stock_return_pct"],
                    "benchmark_return_pct": metrics["benchmark_return_pct"],
                    "excess_return_pct": metrics["excess_return_pct"],
                    "beta_60d": res["beta_60d"],
                    "is_outperforming": metrics["is_outperforming"]
                })

        # Sort descending by excess return
        results.sort(key=lambda r: r["excess_return_pct"], reverse=True)

        return {
            "as_of_date": as_of_date,
            "ranking_horizon": ranking_horizon,
            "benchmark_name": benchmark_name,
            "mode": mode,
            "total_evaluated": len(symbols),
            "total_ranked": len(results),
            "leaderboard": results,
            "top_outperformers": results[:10],
            "top_underperformers": results[-10:][::-1]
        }
