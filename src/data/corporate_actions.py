"""
src/data/corporate_actions.py
Corporate Actions Adjustment Service & Price Multiplier Engine.
Phase 10.1: Preserves unadjusted raw settlement exchange data in ohlcv_daily while
retroactively computing point-in-time compounding split/bonus adjustment multipliers
for downstream factor calculations and quantitative backtesting.
"""

import uuid
import re
import hashlib
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Union, Iterable
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.CorporateActions")

# Standard regex extractors for cash dividend declarations
DIVIDEND_AMOUNT_REGEX = re.compile(r'(?:Rs\.?|Re\.?|INR)\s*[-:]?\s*(\d+(?:\.\d+)?)', re.IGNORECASE)
DIVIDEND_ALT_REGEX = re.compile(r'(?:Dividend|Special\s*Dividend|Interim\s*Dividend)\s*[-:]?\s*(\d+(?:\.\d+)?)(?!\s*%)\s*(?:/-|/)?', re.IGNORECASE)
DIVIDEND_PERCENT_REGEX = re.compile(r'(\d+(?:\.\d+)?)\s*%', re.IGNORECASE)


def extract_cash_dividend_amount(purpose: str, face_val: Optional[float] = None) -> float:
    """
    Extracts total cash dividend per share in INR from corporate announcement purpose text.
    Handles multiple components (e.g. Interim + Special Dividend) and percentage dividends.
    """
    p = str(purpose or "").strip()
    if not p:
        return 0.0

    # 1. If explicit percentage of face value is declared (e.g. "Agm/Dividend - 100%", "Dividend - 250%")
    if "%" in p and face_val and face_val > 0:
        pct_matches = DIVIDEND_PERCENT_REGEX.findall(p)
        if pct_matches:
            amounts = [(float(x) / 100.0) * face_val for x in pct_matches]
            return round(sum(amounts), 4)

    # 2. Match rupee amounts (Rs, Re, INR)
    amounts = [float(x) for x in DIVIDEND_AMOUNT_REGEX.findall(p)]
    if not amounts and "%" not in p:
        amounts = [float(x) for x in DIVIDEND_ALT_REGEX.findall(p)]

    return round(sum(amounts), 4) if amounts else 0.0

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
        Also syncs from corporate_actions table if populated.
        Returns total number of processed actions.
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
        
        synced = self.sync_from_corporate_actions_table()
        logger.info(f"Seeded {seeded} verified corporate actions and synced {synced} table actions into corporate_action_adjustments.")
        return seeded + synced

    def sync_from_corporate_actions_table(self, include_dividends: bool = True) -> int:
        """
        Synchronizes raw exchange actions from corporate_actions table into corporate_action_adjustments ledger.
        Extracts SPLIT, BONUS, RIGHTS, and cash DIVIDEND ratios, computes backward compounding multipliers,
        and persists them idempotently.
        """
        synced = 0
        try:
            with self.db.get_connection() as conn:
                cur = conn.execute("""
                    SELECT symbol, ex_date, record_date, action_type, adjustment_factor, adjustment_ratio, purpose, source, face_value
                    FROM corporate_actions
                    WHERE action_type IN ('SPLIT', 'BONUS', 'RIGHTS', 'DIVIDEND')
                      AND ex_date IS NOT NULL AND ex_date != ''
                    ORDER BY ex_date ASC
                """)
                rows = cur.fetchall()
                for r in rows:
                    sym = r["symbol"].strip().upper()
                    ex_dt = r["ex_date"].strip()
                    rec_dt = r["record_date"].strip() if r["record_date"] else None
                    act_type = r["action_type"].strip().upper()
                    adj_factor = float(r["adjustment_factor"] or r["adjustment_ratio"] or 1.0)
                    purpose = str(r["purpose"] or "")
                    source = r["source"] or "NSE_EXCHANGE_DISCLOSURES"
                    face_val = float(r["face_value"]) if r["face_value"] is not None else None

                    purpose_hash = hashlib.md5(purpose.encode("utf-8")).hexdigest()[:6]

                    if act_type in ("SPLIT", "BONUS", "RIGHTS"):
                        if 0 < adj_factor < 1.0:
                            det_action_id = f"ca_{sym}_{ex_dt.replace('-', '')}_{act_type.lower()}_{purpose_hash}"
                            self.record_action(
                                symbol=sym,
                                ex_date=ex_dt,
                                action_type=act_type,
                                ratio_from=1.0,
                                ratio_to=round(adj_factor, 6),
                                record_date=rec_dt,
                                source=source,
                                action_id=det_action_id
                            )
                            synced += 1

                    elif act_type == "DIVIDEND" and include_dividends:
                        d_s = extract_cash_dividend_amount(purpose, face_val)
                        if d_s <= 0:
                            continue

                        # Look up unadjusted close price P_{s-1} on session immediately preceding ex_date
                        cur_p = conn.execute("""
                            SELECT close FROM ohlcv_daily
                            WHERE symbol = ? AND trading_date < ?
                            ORDER BY trading_date DESC LIMIT 1
                        """, (sym, ex_dt)).fetchone()

                        if not cur_p or cur_p[0] is None or float(cur_p[0]) <= 0:
                            # If no preceding price found in ohlcv_daily, skip recording dividend factor
                            continue

                        p_prev = float(cur_p[0])

                        # Guard against corrupt dividend records where D_s >= 0.5 * P_{s-1} without special dividend
                        if d_s >= 0.5 * p_prev:
                            is_special = "SPECIAL" in purpose.upper()
                            if not is_special:
                                logger.warning(
                                    f"[CORP-ACTIONS] Flagged suspicious dividend for {sym} on {ex_dt}: "
                                    f"D_s=₹{d_s} >= 50% of P_{{s-1}}=₹{p_prev:.2f} without special dividend declaration. Skipping."
                                )
                                continue

                        # Dividend adjustment factor: 1 - (D_s / P_{s-1})
                        div_multiplier = max(0.0001, round(1.0 - (d_s / p_prev), 6))
                        ratio_from = round(p_prev, 4)
                        ratio_to = round(max(0.01, p_prev - d_s), 4)
                        det_action_id = f"ca_{sym}_{ex_dt.replace('-', '')}_div_{purpose_hash}"

                        self.record_action(
                            symbol=sym,
                            ex_date=ex_dt,
                            action_type="DIVIDEND",
                            ratio_from=ratio_from,
                            ratio_to=ratio_to,
                            record_date=rec_dt,
                            source=source,
                            action_id=det_action_id
                        )
                        synced += 1

            logger.info(f"Synchronized {synced} corporate actions from corporate_actions table into adjustments ledger.")
        except Exception as e:
            logger.warning(f"Error syncing from corporate_actions table: {e}")
        return synced

    def record_action(
        self,
        symbol: str,
        ex_date: str,
        action_type: str,
        ratio_from: float,
        ratio_to: float,
        record_date: Optional[str] = None,
        source: str = "NSE_EXCHANGE_DISCLOSURES",
        is_applied: int = 1,
        action_id: Optional[str] = None
    ) -> str:
        """
        Calculates split_multiplier = ratio_to / ratio_from and persists
        the event into corporate_action_adjustments.
        Returns the action_id.
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
        act_id = action_id or f"ca_{sym}_{ex_date.replace('-', '')}_{act_type.lower()}_{uuid.uuid4().hex[:6]}"
        now_iso = datetime.now(timezone.utc).isoformat()

        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO corporate_action_adjustments (
                    action_id, symbol, ex_date, record_date, action_type,
                    ratio_from, ratio_to, split_multiplier, is_applied,
                    source, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                act_id, sym, ex_date, record_date, act_type,
                r_from, r_to, split_multiplier, is_applied,
                source, now_iso
            ))
            conn.commit()

        logger.debug(
            f"Recorded corporate action for {sym}: {act_type} {ratio_from}:{ratio_to} "
            f"on ex_date {ex_date} (multiplier={split_multiplier:.6f})"
        )
        return act_id

    def record_dividend_action(
        self,
        symbol: str,
        ex_date: str,
        dividend_amount: float,
        cum_close_price: float,
        record_date: Optional[str] = None,
        purpose: str = "",
        source: str = "NSE_EXCHANGE_DISCLOSURES",
        is_applied: int = 1
    ) -> Optional[str]:
        """
        Calculates total-return dividend adjustment multiplier:
            F_s = 1 - (D_s / P_{s-1})
        and records the event into corporate_action_adjustments.
        """
        d_s = float(dividend_amount)
        p_prev = float(cum_close_price)

        if d_s <= 0 or p_prev <= 0:
            return None

        # Guard against corrupt entries
        if d_s >= 0.5 * p_prev and "SPECIAL" not in purpose.upper():
            logger.warning(
                f"[CORP-ACTIONS] Flagged suspicious dividend for {symbol} on {ex_date}: "
                f"D_s=₹{d_s} >= 50% of P_{{s-1}}=₹{p_prev:.2f} without special dividend declaration. Skipping."
            )
            return None

        sym = symbol.strip().upper()
        ratio_from = round(p_prev, 4)
        ratio_to = round(max(0.01, p_prev - d_s), 4)
        purpose_hash = hashlib.md5((purpose or str(d_s)).encode("utf-8")).hexdigest()[:6]
        act_id = f"ca_{sym}_{ex_date.replace('-', '')}_div_{purpose_hash}"

        return self.record_action(
            symbol=sym,
            ex_date=ex_date,
            action_type="DIVIDEND",
            ratio_from=ratio_from,
            ratio_to=ratio_to,
            record_date=record_date,
            source=source,
            is_applied=is_applied,
            action_id=act_id
        )

    def get_actions_for_symbol(
        self,
        symbol: str,
        active_only: bool = True,
        action_types: Optional[List[str]] = None
    ) -> List[Dict[str, Any]]:
        """Retrieves corporate actions for a symbol sorted chronologically by ex_date."""
        sym = symbol.strip().upper()
        sql = """
            SELECT action_id, symbol, ex_date, record_date, action_type,
                   ratio_from, ratio_to, split_multiplier, is_applied, source, created_at
            FROM corporate_action_adjustments
            WHERE symbol = ?
        """
        params: List[Any] = [sym]
        if active_only:
            sql += " AND is_applied = 1"
        if action_types:
            placeholders = ",".join("?" for _ in action_types)
            sql += f" AND action_type IN ({placeholders})"
            params.extend([at.upper() for at in action_types])

        sql += " ORDER BY ex_date ASC"

        with self.db.get_connection() as conn:
            cur = conn.execute(sql, params)
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
        end_date: Optional[str] = None,
        include_dividends: bool = True
    ) -> pd.Series:
        """
        Computes cumulative backward adjustment multiplier series M(t) for symbol:
            M(t) = Product_{ex_date > t} (split_multiplier)
        incorporating SPLIT, BONUS, RIGHTS, and cash DIVIDEND actions.
        Returns pd.Series indexed by date string ('YYYY-MM-DD').
        """
        sym = symbol.strip().upper()
        actions = self.get_actions_for_symbol(sym, active_only=True)
        if not include_dividends:
            actions = [a for a in actions if a["action_type"] in ("SPLIT", "BONUS", "RIGHTS")]

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
        action_events = [(a["ex_date"], float(a["split_multiplier"])) for a in actions]

        multipliers = []
        for d in date_list:
            m = 1.0
            for ex_d, mult in action_events:
                # Compound all adjustments strictly occurring after date d
                if ex_d > d:
                    m *= mult
            multipliers.append(round(m, 6))

        return pd.Series(multipliers, index=date_list, name="adj_multiplier")

    def apply_adjustments_to_ohlcv(
        self,
        df_raw: pd.DataFrame,
        include_dividends: bool = True
    ) -> pd.DataFrame:
        """
        Applies point-in-time corporate action multipliers to raw OHLCV DataFrame:
        - Scales open, high, low, close by total-return multiplier M(t)
        - Scales volume by share-count multiplier (splits/bonuses/rights only, excluding cash dividends)
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

            for sym in symbols:
                sym_mask = df_out["symbol"] == sym
                sym_df = df_out[sym_mask]
                dates = sym_df[date_col].tolist()

                # Total-return multipliers for prices (splits + bonuses + dividends)
                total_mult_series = self.get_adjustment_factors_series(
                    str(sym), dates=dates, include_dividends=include_dividends
                )
                mults = total_mult_series.values

                # Share-count multipliers for volume (splits + bonuses + rights only)
                split_mult_series = self.get_adjustment_factors_series(
                    str(sym), dates=dates, include_dividends=False
                )
                split_mults = split_mult_series.values

                df_out.loc[sym_mask, "adj_multiplier"] = mults
                df_out.loc[sym_mask, "adj_open"] = (sym_df["open"] * mults).round(2)
                df_out.loc[sym_mask, "adj_high"] = (sym_df["high"] * mults).round(2)
                df_out.loc[sym_mask, "adj_low"] = (sym_df["low"] * mults).round(2)
                df_out.loc[sym_mask, "adj_close"] = (sym_df["close"] * mults).round(2)

                # Volume scaled inversely by share count multiplier (excluding cash dividends)
                v_scaled = sym_df["volume"] / np.where(split_mults > 0, split_mults, 1.0)
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

    def recompute_symbol_adjustments(self, symbol: str) -> int:
        """
        Idempotently recomputes adjustment multipliers and updates factors_daily for symbol.
        Returns count of updated factors_daily rows.
        """
        sym = symbol.strip().upper()
        self.sync_from_corporate_actions_table()

        with self.db.get_connection() as conn:
            cur = conn.execute(
                "SELECT trading_date, close FROM factors_daily WHERE symbol = ? ORDER BY trading_date ASC",
                (sym,)
            )
            rows = cur.fetchall()
            if not rows:
                return 0

            dates = [r[0] for r in rows]
            mult_series = self.get_adjustment_factors_series(sym, dates=dates, include_dividends=True)

            updates = []
            for r in rows:
                dt = r[0]
                close = float(r[1])
                m = float(mult_series.get(dt, 1.0))
                adj_close = round(close * m, 2)
                updates.append((adj_close, sym, dt))

            conn.executemany(
                "UPDATE factors_daily SET adj_close = ? WHERE symbol = ? AND trading_date = ?",
                updates
            )
            conn.commit()
            return len(updates)
