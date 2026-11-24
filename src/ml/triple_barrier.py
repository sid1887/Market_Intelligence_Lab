"""
src/ml/triple_barrier.py
Conservative Daily Triple-Barrier Event Labeler & Path-Aware Net Cost Evaluator.
Phase 3 Deliverable — Replaces naive fixed-horizon labeling with path-dependent barrier exits.

Specifications:
1. Volatility-Scaled Barriers:
   - Upper Profit Barrier: U = P_0 * (1 + k_u * sigma_t)
   - Lower Stop-Loss Barrier: L = P_0 * (1 - k_l * sigma_t)
   - Vertical Time Barrier: T_max = t + H trading sessions (default k_u=2.0, k_l=1.5, H=20).
2. Daily-Bar Worst-Case Tie-Break Rule:
   - When a daily candle breaches BOTH barriers (High_s >= U and Low_s <= L):
     - If Open_s >= U: fill at Open_s (upper gap hit).
     - If Open_s <= L: fill at Open_s (lower gap hit).
     - Otherwise (Open_s in (L, U)): CONSERVATIVELY assign Stop-Loss hit first (label = -1, exit at L).
3. Net-of-Friction Realized Label Return:
   - Exact statutory + Angel One DP fees computed via src/portfolio/fee_engine.py at reference ticket size.
   - label = 1 strictly requires net_return > 0 after all costs.
"""

import math
import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager
from src.portfolio.fee_engine import (
    calculate_roundtrip_friction,
    ANGEL_ONE_DP_CHARGE,
    PROFILE_ZERO
)

logger = logging.getLogger("MIL.TripleBarrier")


@dataclass(frozen=True)
class TripleBarrierEvent:
    symbol: str
    signal_date: str
    entry_date: str
    entry_price: float
    volatility_20d: float
    upper_barrier: float
    lower_barrier: float
    vertical_barrier_date: str
    exit_date: str
    exit_price: float
    barrier_hit: str            # 'UPPER', 'LOWER', 'VERTICAL'
    gross_return: float         # decimal
    gross_return_pct: float     # percentage
    net_return: float           # decimal after statutory + DP fees
    net_return_pct: float       # percentage after statutory + DP fees
    fee_drag_pct: float         # drag percentage
    label: int                  # +1 (profitable winner), -1 (stop loss), 0 (vertical timeout/fee drag)
    holding_sessions: int


class TripleBarrierLabeler:
    """
    Constructs path-aware, cost-adjusted Triple-Barrier event labels for quantitative research.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        k_upper: float = 2.0,
        k_lower: float = 1.5,
        horizon_sessions: int = 20,
        reference_ticket: float = 5000.0,
        broker_profile: str = PROFILE_ZERO,
        min_volatility: float = 0.005
    ):
        self.db = db or DatabaseManager()
        self.k_upper = float(k_upper)
        self.k_lower = float(k_lower)
        self.horizon_sessions = int(horizon_sessions)
        self.reference_ticket = float(reference_ticket)
        self.broker_profile = broker_profile
        self.min_volatility = float(min_volatility)

    def compute_event_label(
        self,
        symbol: str,
        signal_date: str,
        entry_price: float,
        volatility_20d: float,
        forward_ohlc_df: pd.DataFrame
    ) -> Optional[TripleBarrierEvent]:
        """
        Computes the triple-barrier resolution for a single observation using forward daily OHLC candles.

        Parameters:
            symbol: Ticker symbol.
            signal_date: Session t date string ('YYYY-MM-DD').
            entry_price: Session t+1 Open price (P_0).
            volatility_20d: Trailing 20-day realized daily volatility as of session t.
            forward_ohlc_df: DataFrame of subsequent sessions [t+1, t+H] containing:
                             ['trading_date', 'open', 'high', 'low', 'close'].
        """
        p0 = float(entry_price)
        if p0 <= 0 or forward_ohlc_df.empty:
            return None

        # Effective volatility floor
        vol = max(float(volatility_20d), self.min_volatility)

        # 1. Volatility-Scaled Barrier Thresholds
        u = round(p0 * (1.0 + self.k_upper * vol), 4)
        l = round(p0 * (1.0 - self.k_lower * vol), 4)

        candles = forward_ohlc_df.head(self.horizon_sessions).reset_index(drop=True)
        if candles.empty:
            return None

        entry_date = str(candles.iloc[0]["trading_date"])
        vertical_date = str(candles.iloc[-1]["trading_date"])

        barrier_hit = "VERTICAL"
        exit_date = vertical_date
        exit_price = float(candles.iloc[-1]["close"])
        holding_sessions = len(candles)

        # 2. Iterate through forward candles and enforce Worst-Case Tie-Break Rule
        for idx, row in candles.iterrows():
            session_date = str(row["trading_date"])
            o = float(row["open"])
            h = float(row["high"])
            lo = float(row["low"])
            c = float(row["close"])

            breach_upper = h >= u
            breach_lower = lo <= l

            # Double breach: candle hit BOTH upper and lower barriers on the same day
            if breach_upper and breach_lower:
                if o >= u:
                    # Gapped up above upper barrier at open
                    barrier_hit = "UPPER"
                    exit_price = o
                elif o <= l:
                    # Gapped down below lower barrier at open
                    barrier_hit = "LOWER"
                    exit_price = o
                else:
                    # Open was inside the corridor -> CONSERVATIVE WORST-CASE: Stop-loss touched first!
                    barrier_hit = "LOWER"
                    exit_price = l

                exit_date = session_date
                holding_sessions = idx + 1
                break

            elif breach_upper:
                barrier_hit = "UPPER"
                exit_price = o if o >= u else u
                exit_date = session_date
                holding_sessions = idx + 1
                break

            elif breach_lower:
                barrier_hit = "LOWER"
                exit_price = o if o <= l else l
                exit_date = session_date
                holding_sessions = idx + 1
                break

        # 3. Calculate gross and net realized returns using canonical fee engine
        gross_return = (exit_price / p0) - 1.0
        gross_return_pct = round(gross_return * 100.0, 4)

        # Net return after exact statutory fees + Angel One DP charges
        sell_turnover = round(self.reference_ticket * (1.0 + gross_return), 2)
        rt = calculate_roundtrip_friction(
            buy_turnover=self.reference_ticket,
            sell_turnover=sell_turnover,
            profile=self.broker_profile
        )

        net_return_pct = rt.net_return_pct
        net_return = round(net_return_pct / 100.0, 6)
        fee_drag_pct = rt.fee_drag_pct

        # 4. Mandatory Net-of-Cost Label Assignment
        # label = 1 iff upper barrier hit AND net return is strictly positive
        if barrier_hit == "UPPER":
            label = 1 if net_return > 0.0 else 0
        elif barrier_hit == "LOWER":
            label = -1
        else:  # VERTICAL timeout
            if net_return > 0.0025:
                label = 1
            elif net_return < -0.0025:
                label = -1
            else:
                label = 0

        return TripleBarrierEvent(
            symbol=symbol,
            signal_date=signal_date,
            entry_date=entry_date,
            entry_price=round(p0, 2),
            volatility_20d=round(vol, 6),
            upper_barrier=round(u, 2),
            lower_barrier=round(l, 2),
            vertical_barrier_date=vertical_date,
            exit_date=exit_date,
            exit_price=round(exit_price, 2),
            barrier_hit=barrier_hit,
            gross_return=round(gross_return, 6),
            gross_return_pct=gross_return_pct,
            net_return=net_return,
            net_return_pct=net_return_pct,
            fee_drag_pct=fee_drag_pct,
            label=label,
            holding_sessions=holding_sessions
        )

    def generate_labels_for_series(
        self,
        symbol: str,
        df_ohlcv: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Generates full triple-barrier event series for an equity from its OHLCV history.
        DataFrame must contain ['trading_date', 'open', 'high', 'low', 'close', 'volume'].
        """
        if df_ohlcv.empty or len(df_ohlcv) < self.horizon_sessions + 25:
            return pd.DataFrame()

        df = df_ohlcv.sort_values(by="trading_date").reset_index(drop=True).copy()

        # Calculate 20-day realized volatility: std of daily returns
        df["ret_1d"] = df["close"].pct_change().fillna(0.0)
        df["vol_20d"] = df["ret_1d"].rolling(20).std().fillna(0.015)

        events: List[Dict[str, Any]] = []
        n = len(df)

        for i in range(20, n - self.horizon_sessions):
            sig_date = str(df.loc[i, "trading_date"])
            entry_p = float(df.loc[i + 1, "open"])
            vol = float(df.loc[i, "vol_20d"])

            # Forward window [i+1, i+H]
            fwd_df = df.iloc[i + 1: i + 1 + self.horizon_sessions]

            ev = self.compute_event_label(
                symbol=symbol,
                signal_date=sig_date,
                entry_price=entry_p,
                volatility_20d=vol,
                forward_ohlc_df=fwd_df
            )
            if ev:
                events.append({
                    "symbol": ev.symbol,
                    "signal_date": ev.signal_date,
                    "entry_date": ev.entry_date,
                    "entry_price": ev.entry_price,
                    "upper_barrier": ev.upper_barrier,
                    "lower_barrier": ev.lower_barrier,
                    "exit_date": ev.exit_date,
                    "exit_price": ev.exit_price,
                    "barrier_hit": ev.barrier_hit,
                    "gross_return_pct": ev.gross_return_pct,
                    "net_return_pct": ev.net_return_pct,
                    "fee_drag_pct": ev.fee_drag_pct,
                    "label": ev.label,
                    "holding_sessions": ev.holding_sessions
                })

        return pd.DataFrame(events)
