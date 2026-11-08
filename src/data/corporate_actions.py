"""
src/data/corporate_actions.py
Corporate Actions Adjustment Service & Price Multiplier Engine.
Phase 10.1: Preserves unadjusted raw settlement exchange data in ohlcv_daily while
retroactively computing point-in-time compounding split/bonus adjustment multipliers
for downstream factor calculations and quantitative backtesting.
"""

import uuid
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union, Iterable
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.CorporateActions")

VERIFIED_HISTORICAL_CORPORATE_ACTIONS: List[Dict[str, Any]] = [
    {"symbol": "AARTIIND", "ex_date": "2021-06-22", "action_type": "BONUS", "ratio_from": 2.0, "ratio_to": 1.0, "record_date": "2021-06-23"},
    {"symbol": "IRCTC", "ex_date": "2021-10-28", "action_type": "SPLIT", "ratio_from": 5.0, "ratio_to": 1.0, "record_date": "2021-10-29"},
    {"symbol": "TATASTEEL", "ex_date": "2022-07-28", "action_type": "SPLIT", "ratio_from": 10.0, "ratio_to": 1.0, "record_date": "2022-07-29"},
    {"symbol": "NESTLEIND", "ex_date": "2024-01-05", "action_type": "SPLIT", "ratio_from": 10.0, "ratio_to": 1.0, "record_date": "2024-01-05"},
    {"symbol": "EICHERMOT", "ex_date": "2020-08-24", "action_type": "SPLIT", "ratio_from": 10.0, "ratio_to": 1.0, "record_date": "2020-08-25"},
    {"symbol": "BAJAJFINSV", "ex_date": "2022-09-13", "action_type": "SPLIT", "ratio_from": 5.0, "ratio_to": 1.0, "record_date": "2022-09-14"},
    {"symbol": "BAJAJFINSV", "ex_date": "2022-09-13", "action_type": "BONUS", "ratio_from": 2.0, "ratio_to": 1.0, "record_date": "2022-09-14"},
    {"symbol": "BEL", "ex_date": "2022-09-15", "action_type": "BONUS", "ratio_from": 3.0, "ratio_to": 1.0, "record_date": "2022-09-16"},
    {"symbol": "BSE", "ex_date": "2022-03-21", "action_type": "BONUS", "ratio_from": 3.0, "ratio_to": 1.0, "record_date": "2022-03-22"},
    {"symbol": "RELIANCE", "ex_date": "2024-10-28", "action_type": "BONUS", "ratio_from": 2.0, "ratio_to": 1.0, "record_date": "2024-10-28"},
    {"symbol": "DRREDDY", "ex_date": "2024-10-28", "action_type": "SPLIT", "ratio_from": 5.0, "ratio_to": 1.0, "record_date": "2024-10-28"},
    {"symbol": "BPCL", "ex_date": "2024-06-21", "action_type": "BONUS", "ratio_from": 2.0, "ratio_to": 1.0, "record_date": "2024-06-22"},
    {"symbol": "IOC", "ex_date": "2022-06-30", "action_type": "BONUS", "ratio_from": 3.0, "ratio_to": 2.0, "record_date": "2022-07-01"},
    {"symbol": "GAIL", "ex_date": "2022-09-06", "action_type": "BONUS", "ratio_from": 3.0, "ratio_to": 2.0, "record_date": "2022-09-07"},
    {"symbol": "POWERGRID", "ex_date": "2021-07-29", "action_type": "BONUS", "ratio_from": 4.0, "ratio_to": 3.0, "record_date": "2021-07-30"},
    {"symbol": "POWERGRID", "ex_date": "2023-09-12", "action_type": "BONUS", "ratio_from": 4.0, "ratio_to": 3.0, "record_date": "2023-09-12"},
    {"symbol": "APLAPOLLO", "ex_date": "2021-09-16", "action_type": "SPLIT", "ratio_from": 5.0, "ratio_to": 1.0, "record_date": "2021-09-17"},
    {"symbol": "TRIDENT", "ex_date": "2019-12-16", "action_type": "SPLIT", "ratio_from": 10.0, "ratio_to": 1.0, "record_date": "2019-12-17"},
]


class CorporateActionsManager:
    """
    Manages corporate action adjustments (splits, bonuses, rights).
    Computes retroactive compounding multipliers:
        M(t) = Product_{ex_date > t} (split_multiplier)
    Scales prices by M(t) and volume by 1.0 / M(t), strictly preserving raw settlement prints.
    """

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager()

    def seed_verified_corporate_actions(self) -> int:
        """
        Populates corporate_action_adjustments with verified historical splits and bonuses (2020-2026).
        Returns number of seeded actions.
        """
        seeded = 0
        for act in VERIFIED_HISTORICAL_CORPORATE_ACTIONS:
            self.record_action(
                symbol=act["symbol"],
                ex_date=act["ex_date"],
                action_type=act["action_type"],
                ratio_from=act["ratio_from"],
                ratio_to=act["ratio_to"],
                record_date=act.get("record_date"),
                source="NSE_EXCHANGE_DISCLOSURES"
            )
            seeded += 1
        logger.info(f"Seeded {seeded} verified corporate actions into corporate_action_adjustments.")
        return seeded

    def record_action(
        self,
        symbol: str,
        ex_date: str,
        action_type: str,
        ratio_from: float,
        ratio_to: float,
        record_date: Optional[str] = None,
        source: str = "NSE_EXCHANGE_DISCLOSURES",
        is_applied: int = 1
    ) -> str:
        """
        Calculates split_multiplier = ratio_to / ratio_from and persists
        the event into corporate_action_adjustments.
        Returns the generated action_id.
        """
        sym = symbol.strip().upper()
        act_type = action_type.strip().upper()
        r_from = float(ratio_from)
        r_to = float(ratio_to)

        if r_from <= 0:
            raise ValueError(f"ratio_from must be strictly positive, got {ratio_from}")
        if r_to <= 0:
            raise ValueError(f"ratio_to must be strictly positive, got {ratio_to}")

        split_multiplier = r_to / r_from
        action_id = f"ca_{sym}_{ex_date.replace('-', '')}_{act_type.lower()}_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO corporate_action_adjustments (
                    action_id, symbol, ex_date, record_date, action_type,
                    ratio_from, ratio_to, split_multiplier, is_applied,
                    source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                action_id, sym, ex_date, record_date, act_type,
                r_from, r_to, split_multiplier, is_applied,
                source, now_iso
            ))
            conn.commit()

        logger.info(
            f"Recorded corporate action for {sym}: {act_type} {ratio_from}:{ratio_to} "
            f"on ex_date {ex_date} (multiplier={split_multiplier:.6f})"
        )
        return action_id

    def get_actions_for_symbol(self, symbol: str, active_only: bool = True) -> List[Dict[str, Any]]:
        """Retrieves corporate actions for a symbol sorted chronologically by ex_date."""
        sym = symbol.strip().upper()
        sql = """
            SELECT action_id, symbol, ex_date, record_date, action_type,
                   ratio_from, ratio_to, split_multiplier, is_applied, source, created_at
            FROM corporate_action_adjustments
            WHERE symbol = ?
        """
        if active_only:
            sql += " AND is_applied = 1"
        sql += " ORDER BY ex_date ASC"

        with self.db.get_connection() as conn:
            cur = conn.execute(sql, (sym,))
            rows = cur.fetchall()

        actions = []
        for r in rows:
            if isinstance(r, sqlite3_row_or_dict := dict):
                actions.append(dict(r))
            else:
                actions.append({
                    "action_id": r[0],
                    "symbol": r[1],
                    "ex_date": r[2],
                    "record_date": r[3],
                    "action_type": r[4],
                    "ratio_from": float(r[5]),
                    "ratio_to": float(r[6]),
                    "split_multiplier": float(r[7]),
                    "is_applied": int(r[8]),
                    "source": r[9],
                    "created_at": r[10]
                })
        return actions

    def get_adjustment_factors_series(
        self,
        symbol: str,
        dates: Optional[Iterable[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> pd.Series:
        """
        Computes cumulative backward adjustment multiplier series M(t) for symbol:
            M(t) = Product_{ex_date > t} (split_multiplier)
        Returns pd.Series indexed by date string ('YYYY-MM-DD').
        """
        sym = symbol.strip().upper()
        actions = self.get_actions_for_symbol(sym, active_only=True)

        # Determine target dates
        date_list: List[str] = []
        if dates is not None:
            date_list = [str(d) for d in dates]
        else:
            with self.db.get_connection() as conn:
                query = "SELECT DISTINCT trading_date FROM ohlcv_daily WHERE symbol = ?"
                params = [sym]
                if start_date:
                    query += " AND trading_date >= ?"
                    params.append(start_date)
                if end_date:
                    query += " AND trading_date <= ?"
                    params.append(end_date)
                query += " ORDER BY trading_date ASC"
                cur = conn.execute(query, params)
                date_list = [r[0] for r in cur.fetchall()]

        if not date_list:
            return pd.Series(dtype=float, name="adj_multiplier")

        # Sort actions by ex_date
        split_events = [(a["ex_date"], float(a["split_multiplier"])) for a in actions]

        multipliers = []
        for d in date_list:
            m = 1.0
            for ex_d, mult in split_events:
                # Compound all splits strictly occurring after date d
                if ex_d > d:
                    m *= mult
            multipliers.append(m)

        return pd.Series(multipliers, index=date_list, name="adj_multiplier")

    def apply_adjustments_to_ohlcv(self, df_raw: pd.DataFrame) -> pd.DataFrame:
        """
        Applies point-in-time corporate action multipliers to raw OHLCV DataFrame:
        - Scales open, high, low, close by M(t)
        - Scales volume by 1.0 / M(t)
        - Strictly preserves original raw columns (open, high, low, close, volume)
        - Adds adj_open, adj_high, adj_low, adj_close, adj_volume, adj_multiplier
        """
        if df_raw.empty:
            df_out = df_raw.copy()
            for col in ["adj_open", "adj_high", "adj_low", "adj_close", "adj_volume", "adj_multiplier"]:
                if col not in df_out.columns:
                    df_out[col] = pd.Series(dtype=float)
            return df_out

        df_out = df_raw.copy()
        date_col = "trading_date" if "trading_date" in df_out.columns else ("date" if "date" in df_out.columns else None)
        if not date_col:
            raise ValueError("DataFrame must contain 'trading_date' or 'date' column.")

        # If symbol is present, process symbol by symbol
        if "symbol" in df_out.columns:
            symbols = df_out["symbol"].unique()
            adj_open_list = []
            adj_high_list = []
            adj_low_list = []
            adj_close_list = []
            adj_volume_list = []
            adj_mult_list = []

            for sym in symbols:
                sym_mask = df_out["symbol"] == sym
                sym_df = df_out[sym_mask]
                dates = sym_df[date_col].tolist()
                mult_series = self.get_adjustment_factors_series(str(sym), dates=dates)
                mults = mult_series.values

                df_out.loc[sym_mask, "adj_multiplier"] = mults
                df_out.loc[sym_mask, "adj_open"] = (sym_df["open"] * mults).round(2)
                df_out.loc[sym_mask, "adj_high"] = (sym_df["high"] * mults).round(2)
                df_out.loc[sym_mask, "adj_low"] = (sym_df["low"] * mults).round(2)
                df_out.loc[sym_mask, "adj_close"] = (sym_df["close"] * mults).round(2)
                
                # Volume scaled inversely by multiplier (e.g. 10:1 split scales volume up by 10x)
                v_scaled = sym_df["volume"] / np.where(mults > 0, mults, 1.0)
                df_out.loc[sym_mask, "adj_volume"] = v_scaled.round().astype(int)
        else:
            # Single unknown symbol series - fallback to 1.0 multiplier
            df_out["adj_multiplier"] = 1.0
            df_out["adj_open"] = df_out["open"]
            df_out["adj_high"] = df_out["high"]
            df_out["adj_low"] = df_out["low"]
            df_out["adj_close"] = df_out["close"]
            df_out["adj_volume"] = df_out["volume"]

        return df_out
