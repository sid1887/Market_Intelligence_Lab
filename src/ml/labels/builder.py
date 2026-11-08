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
        """Returns sorted unique settled trading dates for eligible EQ series across the universe."""
        with self.db.get_connection() as conn:
            cur = conn.execute(
                """
                SELECT DISTINCT trading_date 
                FROM ohlcv_daily 
                WHERE series = 'EQ' 
                  AND COALESCE(is_synthetic, 0) = 0 
                  AND COALESCE(is_eligible_for_training, 1) = 1 
                ORDER BY trading_date ASC
                """
            )
            return [r["trading_date"] for r in cur.fetchall()]

    def build_labels(
        self,
        symbols: Optional[List[str]] = None,
        as_of_cutoff: Optional[str] = None,
        horizon_sessions: Optional[int] = None
    ) -> pd.DataFrame:
        """
        Builds matured forward returns for all observations.
        Supports arbitrary target horizons (e.g. 5, 20, 60 sessions).
        Observations whose T + horizon > max_settled_date are flagged matured=False.
        Strictly requires series = 'EQ', non-synthetic, and is_eligible_for_training = 1.
        """
        horizon = horizon_sessions if horizon_sessions is not None else self.horizon_sessions
        calendar = self.get_trading_calendar()
        if not calendar or len(calendar) <= horizon:
            return pd.DataFrame(columns=[
                "symbol", "trading_date", "target_date", "matured",
                "stock_fwd_ret", "bench_fwd_ret", "label_excess_ret_net", "label_up", "status",
                "horizon_sessions"
            ])

        date_to_idx = {d: i for i, d in enumerate(calendar)}
        max_idx = len(calendar) - 1
        max_evaluable_idx = max_idx - horizon

        # Fetch stock close prices strictly requiring EQ series & training eligibility
        where_clauses = [
            "series = 'EQ'",
            "COALESCE(is_synthetic, 0) = 0",
            "COALESCE(is_eligible_for_training, 1) = 1"
        ]
        params: List[Any] = []
        if symbols:
            placeholders = ",".join(["?"] * len(symbols))
            where_clauses.append(f"symbol IN ({placeholders})")
            params.extend(symbols)

        sql_stocks = f"""
        SELECT symbol, trading_date, close
        FROM ohlcv_daily
        WHERE {' AND '.join(where_clauses)}
        ORDER BY symbol, trading_date ASC
        """

        with self.db.get_connection() as conn:
            cur = conn.execute(sql_stocks, params)
            stock_rows = [dict(r) for r in cur.fetchall()]

            # Fetch NIFTY 50 TRI benchmark (primary: index_name='NIFTY 50' AND index_type='TRI')
            cur_b = conn.execute(
                """
                SELECT trading_date, close 
                FROM index_daily 
                WHERE (index_name = 'NIFTY 50' AND index_type = 'TRI')
                   OR index_name = 'NIFTY 50 TRI'
                ORDER BY trading_date ASC
                """
            )
            tri_map = {r["trading_date"]: r["close"] for r in cur_b.fetchall()}

            # Keep PRI separate: NEVER combine or mix TRI with PRI endpoints (P0-05)
            cur_pri = conn.execute(
                """
                SELECT trading_date, close 
                FROM index_daily 
                WHERE (index_name = 'NIFTY 50' AND index_type = 'PRI')
                   OR (index_name = 'NIFTY 50' AND index_type IS NULL)
                ORDER BY trading_date ASC
                """
            )
            pri_map = {r["trading_date"]: r["close"] for r in cur_pri.fetchall()}

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

            target_idx = idx + horizon
            if target_idx > max_idx:
                # Unsettled / in flight
                target_date = None
                matured = False
                fwd_ret = None
                bench_fwd_ret = None
                net_excess = None
                label_up = None
                status = "IN_FLIGHT"
            else:
                target_date = calendar[target_idx]
                future_price = price_lookup.get((sym, target_date))

                # Benchmark Consistency (P0-05): Endpoints must NOT mix TRI and PRI
                # 1. Both endpoints must have valid TRI
                if (
                    d in tri_map and target_date in tri_map
                    and tri_map[d] is not None and tri_map[target_date] is not None
                    and tri_map[d] > 0 and tri_map[target_date] > 0
                ):
                    bench_fwd_ret = (tri_map[target_date] / tri_map[d]) - 1.0
                # 2. Or both endpoints must have valid PRI
                elif (
                    d in pri_map and target_date in pri_map
                    and pri_map[d] is not None and pri_map[target_date] is not None
                    and pri_map[d] > 0 and pri_map[target_date] > 0
                ):
                    bench_fwd_ret = (pri_map[target_date] / pri_map[d]) - 1.0
                else:
                    bench_fwd_ret = None

                if future_price is None or not curr_price or curr_price <= 0:
                    matured = False
                    fwd_ret = None
                    bench_fwd_ret = None
                    net_excess = None
                    label_up = None
                    status = "MISSING_PRICE"
                elif bench_fwd_ret is None:
                    # ML Correctness (P0-05): Unobservable benchmark!
                    # Do NOT default to 0.0, and NEVER mix TRI with PRI across endpoints.
                    matured = False
                    fwd_ret = round((future_price / curr_price) - 1.0, 6)
                    bench_fwd_ret = None
                    net_excess = None
                    label_up = None
                    status = "UNOBSERVABLE_BENCHMARK"
                else:
                    matured = True
                    fwd_ret = (future_price / curr_price) - 1.0
                    gross_excess = fwd_ret - bench_fwd_ret
                    net_excess = round(gross_excess - self.friction_drag, 6)
                    label_up = 1 if net_excess > 0 else 0
                    status = "MATURED"

            records.append({
                "symbol": sym,
                "trading_date": d,
                "target_date": target_date,
                "matured": matured,
                "stock_fwd_ret": fwd_ret,
                "bench_fwd_ret": bench_fwd_ret,
                "label_excess_ret_net": net_excess,
                "label_up": label_up,
                "status": status,
                "horizon_sessions": horizon
            })

        return pd.DataFrame(records)
