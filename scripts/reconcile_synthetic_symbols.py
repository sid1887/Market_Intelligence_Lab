"""
Market Intelligence Lab — Reconcile Synthetic Symbols with Authentic Market Bars.
Workstream 2 / Audit Ticket: MIL-DATA-002, MIL-P0-001.

Fetches authentic daily OHLCV bars for the 6 symbols that previously had synthetic
sine-wave generator data (CANBK, TATAPOWER, RVNL, NHPC, IDEA, DRONACHRYA),
upserts verified real bars with provenance_class = 'VENDOR_OBSERVED', is_synthetic = 0,
and recomputes factor metrics.
"""

import os
import sys
import math
import datetime
import logging
from typing import List, Dict, Any
import pandas as pd
from src.storage.database import DatabaseManager
from src.quant.factor_pipeline import FactorPipeline

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("reconcile_synthetic")

try:
    import yfinance as yf
except ImportError:
    logger.error("yfinance required for authentic historical bar fetch.")
    sys.exit(1)


SYMBOLS_MAP = {
    "CANBK": "CANBK.NS",
    "TATAPOWER": "TATAPOWER.NS",
    "RVNL": "RVNL.NS",
    "NHPC": "NHPC.NS",
    "IDEA": "IDEA.NS",
    "DRONACHRYA": "DRONACHRYA.BO"
}


def reconcile_synthetic_symbols(db_path: str = "data/market_lab.db") -> None:
    db = DatabaseManager(db_path)
    now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
    total_reconciled = 0

    for sym, yf_ticker in SYMBOLS_MAP.items():
        logger.info(f"Fetching authentic 24M historical bars for {sym} ({yf_ticker})...")
        try:
            t = yf.Ticker(yf_ticker)
            df = t.history(period="2y")
            if df.empty:
                logger.warning(f"No history returned for {yf_ticker}")
                continue

            records: List[Dict[str, Any]] = []
            for dt, row in df.iterrows():
                d_str = dt.strftime("%Y-%m-%d")
                o = round(float(row["Open"]), 2)
                h = round(float(row["High"]), 2)
                l = round(float(row["Low"]), 2)
                c = round(float(row["Close"]), 2)
                v = int(row["Volume"]) if not pd.isna(row["Volume"]) and row["Volume"] >= 0 else None

                # Invariant checks: fail closed on corrupt bars, do not mutate
                if h < max(o, c) or l > min(o, c) or o <= 0 or c <= 0 or l <= 0 or h <= 0:
                    logger.warning(f"Corrupt candle skipped for {sym} on {d_str}: O={o}, H={h}, L={l}, C={c}")
                    continue

                records.append({
                    "symbol": sym,
                    "trading_date": d_str,
                    "series": "EQ",
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                    "source": "yfinance_reconciled",
                    "retrieval_timestamp": now_ts,
                    "trades_count": None,  # Truth in data: trades_count not provided by vendor
                    "data_status": "final_settled",
                    "provenance_class": "VENDOR_OBSERVED",
                    "is_synthetic": 0,
                    "is_eligible_for_live_analytics": 1,
                    "is_eligible_for_backtest": 1,
                    "is_eligible_for_training": 1
                })

            if records:
                # First delete previously tagged synthetic rows for this symbol to avoid conflicts
                with db.get_connection() as conn:
                    conn.execute(
                        "DELETE FROM ohlcv_daily WHERE symbol = ? AND is_synthetic = 1;",
                        (sym,)
                    )
                    conn.commit()

                # Upsert authentic bars
                upserted = db.upsert_ohlcv_records(records)
                logger.info(f"Upserted {upserted} authentic bars for {sym} (range: {records[0]['trading_date']} to {records[-1]['trading_date']})")
                total_reconciled += upserted

        except Exception as e:
            logger.error(f"Failed to reconcile {sym}: {e}", exc_info=True)

    # Re-run factor calculation for these symbols
    logger.info("Recomputing factors for reconciled symbols...")
    pipeline = FactorPipeline(db)
    for sym in SYMBOLS_MAP.keys():
        try:
            factors = pipeline.compute_daily_factors_for_symbol(sym)
            if factors:
                for f in factors:
                    f["is_orphaned"] = 0
                db.upsert_quant_factors(factors)
                logger.info(f"Recomputed {len(factors)} factor rows for {sym}")
        except Exception as e:
            logger.warning(f"Factor calculation failed for {sym}: {e}")

    logger.info(f"Synthetic reconciliation complete: {total_reconciled} authentic bars ingested across {len(SYMBOLS_MAP)} symbols.")


if __name__ == "__main__":
    reconcile_synthetic_symbols()
