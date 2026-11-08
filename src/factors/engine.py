"""
src/factors/engine.py
Hardened Factor Calculation Engine with Corporate Action Adjustments & 252-Session Burn-in.
Phase 10.1:
- Consumes retroactively adjusted prices (adj_close, adj_volume) from CorporateActionsManager.
- Enforces strict 252-trading-session burn-in warmup:
  Any date with fewer than 252 historical sessions available sets long-term metrics
  (sma_200, momentum_1y, volatility_annualized) strictly to None (NULL).
- Short-term metrics (sma_20, volatility_20d, rsi_14) require their respective minimum lookbacks.
"""

import math
import logging
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager
from src.data.corporate_actions import CorporateActionsManager

logger = logging.getLogger("MIL.FactorEngine")


def compute_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """Computes Wilder's Relative Strength Index (RSI). Requires >= period observations."""
    if len(prices) <= period:
        return pd.Series(index=prices.index, dtype=float)

    delta = prices.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)

    # First average
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    # Wilder's smoothing
    for i in range(period + 1, len(prices)):
        avg_gain.iloc[i] = (avg_gain.iloc[i - 1] * (period - 1) + gain.iloc[i]) / period
        avg_loss.iloc[i] = (avg_loss.iloc[i - 1] * (period - 1) + loss.iloc[i]) / period

    rs = avg_gain / np.where(avg_loss == 0, 1e-9, avg_loss)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.round(2)


class FactorEngine:
    """
    Hardened Factor Generation Engine enforcing corporate action adjustments
    and institutional 252-session burn-in period.
    """

    BURN_IN_SESSIONS = 252

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        ca_manager: Optional[CorporateActionsManager] = None
    ):
        self.db = db or DatabaseManager()
        self.ca_manager = ca_manager or CorporateActionsManager(self.db)

    def compute_factors_for_symbol(
        self,
        symbol: str,
        df_ohlcv: Optional[pd.DataFrame] = None
    ) -> pd.DataFrame:
        """
        Computes point-in-time factors for symbol across all historical sessions:
        - Adjusts raw OHLCV for splits/bonuses using CorporateActionsManager
        - Evaluates SMA_20, SMA_200, volatility_20d, volatility_annualized, RSI_14, momentum_1y
        - Enforces 252-session burn-in: sma_200, momentum_1y, volatility_annualized are NULL
          if available trading sessions < 252.
        """
        sym = symbol.strip().upper()

        if df_ohlcv is not None and not df_ohlcv.empty:
            df_raw = df_ohlcv.copy()
        else:
            with self.db.get_connection() as conn:
                cur = conn.execute("""
                    SELECT symbol, trading_date, open, high, low, close, volume
                    FROM ohlcv_daily
                    WHERE symbol = ? AND series = 'EQ' AND COALESCE(is_synthetic, 0) = 0
                    ORDER BY trading_date ASC
                """, (sym,))
                rows = cur.fetchall()

            if not rows:
                return pd.DataFrame()

            df_raw = pd.DataFrame(rows, columns=["symbol", "trading_date", "open", "high", "low", "close", "volume"])

        # 1. Apply Corporate Actions Adjustments (retroactive split scaling)
        df_adj = self.ca_manager.apply_adjustments_to_ohlcv(df_raw)

        n = len(df_adj)
        if n == 0:
            return pd.DataFrame()

        adj_closes = df_adj["adj_close"].values
        adj_volumes = df_adj["adj_volume"].values
        trading_dates = df_adj["trading_date"].values

        # Daily returns on adjusted close
        daily_returns = np.zeros(n)
        for i in range(1, n):
            prev_c = adj_closes[i - 1]
            curr_c = adj_closes[i]
            daily_returns[i] = (curr_c - prev_c) / prev_c if prev_c > 0 else 0.0

        # RSI Series
        rsi_series = compute_rsi(pd.Series(adj_closes), period=14).values

        factor_records: List[Dict[str, Any]] = []

        for i in range(n):
            sessions_available = i + 1  # 1-based count of sessions up to current date
            d = str(trading_dates[i])
            c_raw = float(df_adj["close"].iloc[i])
            c_adj = float(adj_closes[i])
            v_raw = int(df_adj["volume"].iloc[i])
            v_adj = int(adj_volumes[i])

            # -------------------------------------------------------------
            # Short-Term Factors (Minimum Lookbacks)
            # -------------------------------------------------------------
            # 1-day return
            ret_1d = round(float(daily_returns[i]), 4) if i > 0 else 0.0

            # 5-day return
            ret_5d = round(float((c_adj - adj_closes[i - 5]) / adj_closes[i - 5]), 4) if i >= 5 and adj_closes[i - 5] > 0 else None

            # 20-day return
            ret_20d = round(float((c_adj - adj_closes[i - 20]) / adj_closes[i - 20]), 4) if i >= 20 and adj_closes[i - 20] > 0 else None

            # 20-day SMA
            sma_20 = round(float(np.mean(adj_closes[i - 19:i + 1])), 2) if i >= 19 else None

            # 50-day SMA
            sma_50 = round(float(np.mean(adj_closes[i - 49:i + 1])), 2) if i >= 49 else None

            # 20-day Volatility (annualized)
            if i >= 20:
                ret_slice = daily_returns[i - 19:i + 1]
                vol_20d = round(float(np.std(ret_slice, ddof=1) * math.sqrt(252.0) * 100.0), 2)
            else:
                vol_20d = None

            # 14-day RSI
            rsi_14 = float(rsi_series[i]) if (not np.isnan(rsi_series[i])) and i >= 14 else None

            # -------------------------------------------------------------
            # Long-Term Factors (Strict 252-Session Burn-in Enforcement)
            # -------------------------------------------------------------
            burn_in_complete = bool(sessions_available >= self.BURN_IN_SESSIONS)

            if not burn_in_complete:
                # Strictly NULL during the 252-session burn-in period
                sma_200 = None
                momentum_1y = None
                volatility_annualized = None
                trend_regime = None
            else:
                # 200-day SMA on adjusted close
                sma_200 = round(float(np.mean(adj_closes[i - 199:i + 1])), 2)

                # 1-year (252 sessions) momentum
                base_252 = adj_closes[i - 251]
                momentum_1y = round(float((c_adj - base_252) / base_252 * 100.0), 2) if base_252 > 0 else None

                # Annualized Volatility over 252 sessions
                ret_252_slice = daily_returns[i - 251:i + 1]
                volatility_annualized = round(float(np.std(ret_252_slice, ddof=1) * math.sqrt(252.0) * 100.0), 2)

                # Trend Regime Classification
                if sma_20 is not None and sma_50 is not None and sma_200 is not None:
                    if c_adj > sma_20 > sma_50 > sma_200:
                        trend_regime = "STRONG_BULL"
                    elif c_adj > sma_200:
                        trend_regime = "BULL"
                    elif c_adj < sma_20 < sma_50 < sma_200:
                        trend_regime = "STRONG_BEAR"
                    elif c_adj < sma_200:
                        trend_regime = "BEAR"
                    else:
                        trend_regime = "NEUTRAL"
                else:
                    trend_regime = "NEUTRAL"

            factor_records.append({
                "symbol": sym,
                "trading_date": d,
                "close": c_raw,
                "adj_close": c_adj,
                "volume": v_raw,
                "adj_volume": v_adj,
                "sessions_available": sessions_available,
                "burn_in_complete": burn_in_complete,
                "ret_1d": ret_1d,
                "ret_5d": ret_5d,
                "ret_20d": ret_20d,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
                "volatility_20d": vol_20d,
                "volatility_annualized": volatility_annualized,
                "rsi_14": rsi_14,
                "momentum_1y": momentum_1y,
                "trend_regime": trend_regime
            })

        return pd.DataFrame(factor_records)
