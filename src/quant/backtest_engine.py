"""
Market Intelligence Lab: Multi-Factor Strategy Backtesting & Portfolio Rebalancing Engine
Milestone: B8.0 (Multi-Factor Strategy Backtesting & Portfolio Rebalancing Engine)

Executes point-in-time systematic portfolio simulation driven by the Quality-Momentum screener.
Models realistic exchange friction:
- Delivery STT: 0.1% on buy and 0.1% on sell
- Exchange Turnover Fees: 0.0035% on total traded turnover
- Depository Participant (DP) Charges: Flat ₹15.34 per liquidated equity symbol
- Slippage Drag: Configurable penalty (default: 5 bps / 0.05%)
- Cash Drag: Strict integer share quantities (no fractional shares) with unallocated cash reserves.
"""

import math
import uuid
import datetime
import logging
from typing import Dict, List, Any, Optional, Tuple, Set

import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager
from src.quant.screener import FactorScreener
from src.quant.performance import PerformanceMetricsCalculator

logger = logging.getLogger(__name__)


class BacktestEngine:
    """
    Simulates multi-factor systematic equity strategies with realistic friction modeling.
    """

    STT_BUY_RATE = 0.001       # 0.1% on equity delivery buy
    STT_SELL_RATE = 0.001      # 0.1% on equity delivery sell
    EXCHANGE_TURNOVER_RATE = 0.000035  # 0.0035% exchange charges & stamp duty
    DP_CHARGE_PER_SELL = 15.34 # Flat CDSL DP charge per liquidated equity symbol (incl. GST)

    def __init__(self, db_manager: Optional[DatabaseManager] = None):
        self.db = db_manager or DatabaseManager()
        self.screener = FactorScreener(self.db)

    def _get_trading_calendar(self, start_date: str, end_date: str) -> List[str]:
        """
        Retrieves all active trading sessions between start_date and end_date in ascending order.
        Strictly excludes official NSE exchange holidays (P0-02, P0-07, ADR-0009).
        """
        from src.quant.calendar import is_trading_session
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT DISTINCT trading_date
                FROM ohlcv_daily
                WHERE trading_date >= ? AND trading_date <= ? AND series = 'EQ'
                ORDER BY trading_date ASC;
                """,
                (start_date, end_date)
            )
            raw_dates = [row[0] for row in cursor.fetchall()]

        valid_dates = [d for d in raw_dates if is_trading_session(d)[0]]
        return valid_dates

    def _build_benchmark_series(
        self,
        trading_dates: List[str],
        initial_capital: float
    ) -> Dict[str, float]:
        """
        Builds a continuous NIFTY 50 TRI benchmark curve normalized to initial_capital strictly
        using official TRI records from index_daily (P0-03, ADR-0004).
        Synthetic cross-sectional stock return chaining is prohibited.
        """
        if not trading_dates:
            return {}

        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT trading_date, close
                FROM index_daily
                WHERE index_name = 'NIFTY 50' AND index_type = 'TRI'
                ORDER BY trading_date ASC;
                """
            )
            official_tri = dict(cur.fetchall())

        tri_dates = sorted([d for d in trading_dates if d in official_tri])
        if not tri_dates:
            # Fallback to official PRI if TRI not present in date range
            with self.db.get_connection() as conn:
                cur_pri = conn.execute(
                    """
                    SELECT trading_date, close
                    FROM index_daily
                    WHERE index_name = 'NIFTY 50' AND index_type = 'PRI'
                    ORDER BY trading_date ASC;
                    """
                )
                official_tri = dict(cur_pri.fetchall())
                tri_dates = sorted([d for d in trading_dates if d in official_tri])

        if not tri_dates:
            logger.warning("Official NIFTY 50 TRI/PRI records completely missing. Returning un-levered benchmark.")
            return {d: round(initial_capital, 2) for d in trading_dates}

        anchor_date = tri_dates[0]
        base_val = float(official_tri[anchor_date])
        norm_series: Dict[str, float] = {}
        curr_norm = initial_capital

        for d in trading_dates:
            if d in official_tri and official_tri[d] is not None:
                curr_norm = round((float(official_tri[d]) / base_val) * initial_capital, 2)
            norm_series[d] = curr_norm

        return norm_series

    def _get_rebalance_dates(
        self,
        trading_dates: List[str],
        frequency: str
    ) -> List[str]:
        """
        Determines the list of rebalance decision dates according to the chosen frequency.
        - MONTHLY: First trading session of each calendar month.
        - QUARTERLY: First trading session of each calendar quarter (months 1, 4, 7, 10).
        """
        if not trading_dates:
            return []

        rebalance_dates = [trading_dates[0]]  # Day 0 initial allocation
        prev_month = trading_dates[0][:7]

        for i in range(1, len(trading_dates)):
            curr_date = trading_dates[i]
            curr_month = curr_date[:7]
            month_num = int(curr_date[5:7])

            if curr_month != prev_month:
                if frequency.upper() == "QUARTERLY":
                    if month_num in [1, 4, 7, 10]:
                        rebalance_dates.append(curr_date)
                else:  # MONTHLY
                    rebalance_dates.append(curr_date)
                prev_month = curr_month

        return rebalance_dates

    def run_backtest(
        self,
        strategy_name: str = "Quality_Momentum_Top10",
        start_date: str = "2024-01-01",
        end_date: str = "2026-10-28",
        initial_capital: float = 500000.0,
        rebalance_frequency: str = "MONTHLY",
        top_n: int = 10,
        weighting: str = "EQUAL_WEIGHT",
        slippage_bps: float = 5.0,
        save_to_db: bool = True
    ) -> Dict[str, Any]:
        """
        Executes systematic portfolio simulation and calculates institutional metrics.
        """
        # Validate inputs
        top_n = max(5, min(top_n, 20))
        slippage_pct = max(0.0, slippage_bps) / 10000.0
        rebalance_freq = rebalance_frequency.upper()
        weighting_mode = weighting.upper()

        # 1. Trading Calendar & Benchmarks
        trading_dates = self._get_trading_calendar(start_date, end_date)
        if len(trading_dates) < 5:
            raise ValueError(f"Insufficient trading dates ({len(trading_dates)}) between {start_date} and {end_date}.")

        benchmark_curve = self._build_benchmark_series(trading_dates, initial_capital)
        rebalance_dates = set(self._get_rebalance_dates(trading_dates, rebalance_freq))

        # 2. Pre-load daily prices for fast lookup: (symbol, date) -> (open, close)
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT symbol, trading_date, open, close
                FROM ohlcv_daily
                WHERE trading_date >= ? AND trading_date <= ? AND series = 'EQ';
                """,
                (trading_dates[0], trading_dates[-1])
            )
            price_map: Dict[Tuple[str, str], Dict[str, float]] = {}
            for r in cur.fetchall():
                price_map[(r[0], r[1])] = {
                    "open": float(r[2]) if r[2] is not None else float(r[3]),
                    "close": float(r[3])
                }

        # 3. Portfolio State
        cash = float(initial_capital)
        holdings: Dict[str, int] = {}  # symbol -> share count
        last_known_close: Dict[str, float] = {}  # symbol -> last valid closing price (P0-02)
        rebalance_records: List[Dict[str, Any]] = []
        equity_curve: List[Dict[str, Any]] = []

        total_stt_paid = 0.0
        total_dp_paid = 0.0
        total_turnover_fees = 0.0
        total_slippage_cost = 0.0

        prev_rebalance_value = initial_capital

        # 4. Simulation Day-by-Day Loop
        for idx, date in enumerate(trading_dates):
            is_rebalance_day = (date in rebalance_dates)

            # Rebalance execution on decision day
            if is_rebalance_day:
                # 4a. Point-in-time screener selection as of `date`
                screen_criteria = {
                    "max_debt_to_equity": 0.5,
                    "min_roe_pct": 15.0,
                    "price_above_sma200": True,
                    "exclude_sectors": ["Financial Services"]
                }
                screen_df = self.screener.screen(
                    as_of_date=date,
                    criteria=screen_criteria,
                    include_watchlists=True
                )

                # Filter top_n securities by composite score
                if not screen_df.empty:
                    top_candidates = screen_df.head(top_n).copy()
                    target_symbols = top_candidates["symbol"].tolist()
                else:
                    top_candidates = pd.DataFrame()
                    target_symbols = []

                # Compute target weights
                target_weights: Dict[str, float] = {}
                if not top_candidates.empty:
                    k = len(top_candidates)
                    if weighting_mode == "INVERSE_VOLATILITY":
                        inv_vols = []
                        for _, row in top_candidates.iterrows():
                            vol = row.get("volatility_annualized")
                            vol_val = float(vol) if (vol is not None and not np.isnan(vol)) else 0.30
                            inv_vols.append(1.0 / max(vol_val, 0.05))
                        total_inv = sum(inv_vols)
                        for sym, iv in zip(target_symbols, inv_vols):
                            target_weights[sym] = iv / total_inv if total_inv > 0 else (1.0 / k)
                    else:  # EQUAL_WEIGHT
                        for sym in target_symbols:
                            target_weights[sym] = 1.0 / k

                # Determine execution price point: Next session open (P0-02, ADR-0009)
                if idx + 1 >= len(trading_dates):
                    continue  # Last session of backtest, rebalance order cannot execute forward

                exec_date = trading_dates[idx + 1]

                # Current portfolio valuation at next-session execution prices
                current_stock_value = 0.0
                current_prices: Dict[str, float] = {}
                for sym, qty in holdings.items():
                    price_info = price_map.get((sym, exec_date))
                    if price_info and price_info.get("open") is not None and float(price_info["open"]) > 0:
                        p = float(price_info["open"])
                    elif price_info and price_info.get("close") is not None and float(price_info["close"]) > 0:
                        p = float(price_info["close"])
                    else:
                        p = last_known_close.get(sym, 0.0)
                    current_prices[sym] = p
                    current_stock_value += qty * p

                total_nav = cash + current_stock_value

                # 4b. Execute SELLS first to generate cash
                sells_log: List[Dict[str, Any]] = []
                buys_log: List[Dict[str, Any]] = []
                reb_friction = 0.0
                reb_turnover = 0.0

                for sym in list(holdings.keys()):
                    qty = holdings[sym]
                    p = current_prices.get(sym, 0.0)
                    if p <= 0:
                        continue

                    # If not in target universe or needs reduction
                    target_alloc = total_nav * target_weights.get(sym, 0.0)
                    target_qty = math.floor(target_alloc / p) if p > 0 else 0

                    if target_qty < qty:
                        shares_to_sell = qty - target_qty
                        gross_sell_val = shares_to_sell * p
                        exec_sell_price = p * (1.0 - slippage_pct)
                        net_sell_val = shares_to_sell * exec_sell_price

                        # Friction
                        stt = gross_sell_val * self.STT_SELL_RATE
                        turnover_chg = gross_sell_val * self.EXCHANGE_TURNOVER_RATE
                        dp = self.DP_CHARGE_PER_SELL  # Flat CDSL DP charge on liquidated stock
                        slip = gross_sell_val * slippage_pct

                        friction_total = stt + turnover_chg + dp + slip
                        reb_friction += friction_total
                        reb_turnover += gross_sell_val
                        total_stt_paid += stt
                        total_dp_paid += dp
                        total_turnover_fees += turnover_chg
                        total_slippage_cost += slip

                        # Cash credit
                        cash += (net_sell_val - stt - turnover_chg - dp)
                        if target_qty == 0:
                            del holdings[sym]
                        else:
                            holdings[sym] = target_qty

                        sells_log.append({
                            "symbol": sym,
                            "shares": shares_to_sell,
                            "exec_price": round(exec_sell_price, 2),
                            "gross_value": round(gross_sell_val, 2),
                            "stt": round(stt, 2),
                            "dp_charge": round(dp, 2)
                        })

                # 4c. Execute BUYS with available cash at next session open
                for sym in target_symbols:
                    price_info = price_map.get((sym, exec_date))
                    if price_info and price_info.get("open") is not None and float(price_info["open"]) > 0:
                        p = float(price_info["open"])
                    elif price_info and price_info.get("close") is not None and float(price_info["close"]) > 0:
                        p = float(price_info["close"])
                    else:
                        p = last_known_close.get(sym, 0.0)
                    if p <= 0:
                        continue

                    curr_qty = holdings.get(sym, 0)
                    target_alloc = total_nav * target_weights[sym]
                    curr_val = curr_qty * p

                    if target_alloc > curr_val:
                        alloc_diff = target_alloc - curr_val
                        exec_buy_price = p * (1.0 + slippage_pct)
                        cost_per_share = exec_buy_price * (1.0 + self.STT_BUY_RATE + self.EXCHANGE_TURNOVER_RATE)
                        shares_to_buy = math.floor(alloc_diff / cost_per_share) if cost_per_share > 0 else 0

                        # Ensure cash covers
                        while shares_to_buy > 0 and (shares_to_buy * cost_per_share) > cash:
                            shares_to_buy -= 1

                        if shares_to_buy > 0:
                            gross_buy_val = shares_to_buy * p
                            exec_total = shares_to_buy * exec_buy_price
                            stt = gross_buy_val * self.STT_BUY_RATE
                            turnover_chg = gross_buy_val * self.EXCHANGE_TURNOVER_RATE
                            slip = gross_buy_val * slippage_pct

                            total_buy_cost = exec_total + stt + turnover_chg
                            cash -= total_buy_cost
                            holdings[sym] = curr_qty + shares_to_buy

                            friction_total = stt + turnover_chg + slip
                            reb_friction += friction_total
                            reb_turnover += gross_buy_val
                            total_stt_paid += stt
                            total_turnover_fees += turnover_chg
                            total_slippage_cost += slip

                            buys_log.append({
                                "symbol": sym,
                                "shares": shares_to_buy,
                                "exec_price": round(exec_buy_price, 2),
                                "gross_value": round(gross_buy_val, 2),
                                "stt": round(stt, 2)
                            })

                # Log rebalance audit
                period_ret = ((total_nav / prev_rebalance_value) - 1.0) * 100.0 if prev_rebalance_value > 0 else 0.0
                prev_rebalance_value = total_nav

                stocks_held_summary = []
                for s, q in holdings.items():
                    c_price = (price_map.get((s, date)) or {}).get("close", 0.0)
                    pos_val = q * c_price
                    stocks_held_summary.append({
                        "symbol": s,
                        "shares": q,
                        "price": round(c_price, 2),
                        "position_value": round(pos_val, 2),
                        "weight_pct": round((pos_val / total_nav) * 100.0, 2) if total_nav > 0 else 0.0
                    })

                rebalance_records.append({
                    "rebalance_date": date,
                    "execution_date": exec_date,
                    "portfolio_value": round(total_nav, 2),
                    "cash_balance": round(cash, 2),
                    "friction_inr": round(reb_friction, 2),
                    "stt_inr": round(total_stt_paid, 2),
                    "dp_charges_inr": round(total_dp_paid, 2),
                    "turnover_charges_inr": round(total_turnover_fees, 2),
                    "slippage_drag_inr": round(total_slippage_cost, 2),
                    "turnover_traded_inr": round(reb_turnover, 2),
                    "period_net_return_pct": round(period_ret, 2),
                    "stocks_held": stocks_held_summary,
                    "buys": buys_log,
                    "sells": sells_log
                })

            # 4d. End-of-Day Valuation (P0-02: Never value held stock at 0.0 on missing bar)
            daily_stock_val = 0.0
            for sym, qty in holdings.items():
                p_info = price_map.get((sym, date))
                if p_info and p_info.get("close") is not None and float(p_info["close"]) > 0:
                    c_price = float(p_info["close"])
                    last_known_close[sym] = c_price
                else:
                    c_price = last_known_close.get(sym, 0.0)
                daily_stock_val += qty * c_price

            portfolio_val = round(cash + daily_stock_val, 2)
            bench_val = benchmark_curve.get(date, initial_capital)

            equity_curve.append({
                "trading_date": date,
                "portfolio_value": portfolio_val,
                "benchmark_value": bench_val,
                "cash": round(cash, 2),
                "invested_value": round(daily_stock_val, 2)
            })

        # 5. Compute Drawdowns
        max_p = initial_capital
        max_b = initial_capital
        for pt in equity_curve:
            if pt["portfolio_value"] > max_p:
                max_p = pt["portfolio_value"]
            if pt["benchmark_value"] > max_b:
                max_b = pt["benchmark_value"]
            pt["drawdown_pct"] = round(((pt["portfolio_value"] - max_p) / max_p) * 100.0, 2) if max_p > 0 else 0.0
            pt["benchmark_drawdown_pct"] = round(((pt["benchmark_value"] - max_b) / max_b) * 100.0, 2) if max_b > 0 else 0.0

        # 6. Performance Attribution
        metrics = PerformanceMetricsCalculator.calculate_metrics(
            equity_curve=equity_curve,
            rebalance_records=rebalance_records
        )

        run_id = f"BT_{strategy_name}_{datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        params_dict = {
            "strategy_name": strategy_name,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital,
            "rebalance_frequency": rebalance_freq,
            "top_n": top_n,
            "weighting": weighting_mode,
            "slippage_bps": slippage_bps
        }

        # 7. Persistence
        if save_to_db:
            run_data = {
                "run_id": run_id,
                "strategy_name": strategy_name,
                "parameters": params_dict,
                "cagr_pct": metrics["portfolio"]["cagr_pct"],
                "sharpe_ratio": metrics["portfolio"]["sharpe_ratio"],
                "max_drawdown_pct": metrics["portfolio"]["max_drawdown_pct"],
                "win_rate_pct": metrics["portfolio"]["win_rate_pct"],
                "created_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            }
            self.db.save_backtest_run(run_data, equity_curve)

        return {
            "run_id": run_id,
            "strategy_name": strategy_name,
            "parameters": params_dict,
            "metrics": metrics["portfolio"],
            "benchmark_metrics": metrics["benchmark"],
            "simulation": metrics["simulation"],
            "equity_curve": equity_curve,
            "rebalance_events": rebalance_records
        }
