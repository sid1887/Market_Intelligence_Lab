"""
Market Intelligence Lab — Matured Forward Label Builder (Stage A2).
Builds forward excess returns net of Indian delivery friction with strict settlement guards.
"""

import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager

logger = logging.getLogger(__name__)

INDIAN_EQUITY_FRICTION_BPS = 15.0  # 15 bps round-trip delivery costs (STT + Stamp + Exch + GST + SEBI)


class MaturedForwardLabelBuilder:
    """Builds matured 20-session forward labels with zero premature evaluation."""

    def __init__(self, db: DatabaseManager, horizon_sessions: int = 20, friction_bps: float = INDIAN_EQUITY_FRICTION_BPS):
        self.db = db
        self.horizon_sessions = horizon_sessions
        self.friction_drag = friction_bps / 10000.0

    def get_trading_calendar(self) -> List[str]:
        """Returns sorted unique settled trading dates across the universe."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT DISTINCT trading_date FROM ohlcv_daily ORDER BY trading_date ASC")
            return [r["trading_date"] for r in cur.fetchall()]

    def build_labels(
        self,
        symbols: Optional[List[str]] = None,
        as_of_cutoff: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Builds matured forward returns for all observations.
        Observations whose T + horizon_sessions > max_settled_date are flagged matured=False.
        """
        calendar = self.get_trading_calendar()
        if not calendar or len(calendar) <= self.horizon_sessions:
            return pd.DataFrame(columns=[
                "symbol", "trading_date", "target_date", "matured",
                "stock_fwd_ret", "bench_fwd_ret", "label_excess_ret_net", "label_up"
            ])

        date_to_idx = {d: i for i, d in enumerate(calendar)}
        max_idx = len(calendar) - 1
        max_evaluable_idx = max_idx - self.horizon_sessions

        # Fetch stock close prices
        sym_clause = ""
        params: List[Any] = []
        if symbols:
            placeholders = ",".join(["?"] * len(symbols))
            sym_clause = f"WHERE symbol IN ({placeholders})"
            params.extend(symbols)

        sql_stocks = f"""
        SELECT symbol, trading_date, close
        FROM ohlcv_daily
        {sym_clause}
        ORDER BY symbol, trading_date ASC
        """

        with self.db.get_connection() as conn:
            cur = conn.execute(sql_stocks, params)
            stock_rows = [dict(r) for r in cur.fetchall()]

            # Fetch NIFTY 50 TRI benchmark
            cur_b = conn.execute(
                """
                SELECT trading_date, close 
                FROM index_daily 
                WHERE index_name = 'NIFTY 50 TRI'
                ORDER BY trading_date ASC
                """
            )
            bench_map = {r["trading_date"]: r["close"] for r in cur_b.fetchall()}

        if not stock_rows:
            return pd.DataFrame()

        df_stocks = pd.DataFrame(stock_rows)

        # Pivot to lookup prices easily: symbol -> date -> close
        price_lookup = {}
        for row in stock_rows:
            price_lookup[(row["symbol"], row["trading_date"])] = row["close"]

        records = []
        for _, row in df_stocks.iterrows():
            sym = row["symbol"]
            d = row["trading_date"]
            if as_of_cutoff and d > as_of_cutoff:
                continue

            curr_price = row["close"]
            idx = date_to_idx.get(d)
            if idx is None:
                continue

            target_idx = idx + self.horizon_sessions
            if target_idx > max_idx:
                # Unsettled / in flight
                target_date = None
                matured = False
                fwd_ret = None
                bench_fwd_ret = None
                net_excess = None
                label_up = None
            else:
                target_date = calendar[target_idx]
                future_price = price_lookup.get((sym, target_date))
                if future_price is not None and curr_price and curr_price > 0:
                    matured = True
                    fwd_ret = (future_price / curr_price) - 1.0

                    # Benchmark return
                    bench_curr = bench_map.get(d)
                    bench_target = bench_map.get(target_date)
                    if bench_curr and bench_target and bench_curr > 0:
                        bench_fwd_ret = (bench_target / bench_curr) - 1.0
                    else:
                        bench_fwd_ret = 0.0

                    gross_excess = fwd_ret - bench_fwd_ret
                    net_excess = round(gross_excess - self.friction_drag, 6)
                    label_up = 1 if net_excess > 0 else 0
                else:
                    matured = False
                    fwd_ret = None
                    bench_fwd_ret = None
                    net_excess = None
                    label_up = None

            records.append({
                "symbol": sym,
                "trading_date": d,
                "target_date": target_date,
                "matured": matured,
                "stock_fwd_ret": fwd_ret,
                "bench_fwd_ret": bench_fwd_ret,
                "label_excess_ret_net": net_excess,
                "label_up": label_up
            })

        return pd.DataFrame(records)
