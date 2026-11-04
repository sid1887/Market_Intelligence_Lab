#!/usr/bin/env python3
"""
Market Intelligence Lab — Universe Expansion & Factor Population.

Expands active research coverage from 50 to 180+ liquid NIFTY constituents:
1. Queries securities_master for liquid NIFTY 500 equities.
2. Activates them (is_active = 1).
3. Backfills 24 months of daily OHLCV history via BackfillManager.
4. Computes daily technical and fundamental factors via FactorPipeline in batches of 25.
5. Performs explicit garbage collection (gc.collect()) per batch.
"""

import os
import sys
import gc
import logging
import sqlite3
from typing import List

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.storage.database import DatabaseManager
from src.client.backfill_manager import BackfillManager
from src.quant.factor_pipeline import FactorPipeline

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [BATCH_INGEST] %(message)s"
)
logger = logging.getLogger("batch_ingest")


def run_batch_universe_expansion(target_total_symbols: int = 180):
    db = DatabaseManager()
    bm = BackfillManager(db)
    fp = FactorPipeline(db_manager=db)

    # Preload benchmark once
    logger.info("Preloading NIFTY 50 PRI benchmark returns...")
    fp.preload_benchmark_returns()

    with db.get_connection() as conn:
        # Check current active count
        cur = conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol ASC")
        already_active = [r["symbol"] for r in cur.fetchall()]
        logger.info(f"Currently active symbols: {len(already_active)}")

        # Fetch candidate symbols from securities_master to reach target_total_symbols
        needed = max(0, target_total_symbols - len(already_active))
        if needed > 0:
            cur = conn.execute(
                """
                SELECT symbol FROM securities_master
                WHERE is_active = 0
                ORDER BY ROWID ASC
                LIMIT ?
                """,
                (needed,)
            )
            to_activate = [r["symbol"] for r in cur.fetchall()]
            logger.info(f"Activating {len(to_activate)} additional symbols in securities_master...")
            for sym in to_activate:
                conn.execute("UPDATE securities_master SET is_active = 1 WHERE symbol = ?", (sym,))
            conn.commit()

        # Re-query all active symbols
        cur = conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol ASC")
        active_symbols = [r["symbol"] for r in cur.fetchall()]

    logger.info(f"Total active universe size: {len(active_symbols)} securities.")

    # 2. Ingest 2 years of daily OHLCV bars using BackfillManager
    logger.info("Starting OHLCV 24-month backfill for active universe...")
    for i, sym in enumerate(active_symbols, 1):
        try:
            res = bm.backfill_symbol(symbol=sym, total_months=24, end_date="2026-10-28")
            if i % 25 == 0 or i == len(active_symbols):
                logger.info(f"[{i}/{len(active_symbols)}] OHLCV backfill progress for {sym}: status={res.get('status')}")
        except Exception as e:
            logger.warning(f"Backfill warning for {sym}: {e}")

    # 3. Factor calculation in batches of 25
    batch_size = 25
    logger.info(f"Starting factor computation in batches of {batch_size}...")

    total_factors_upserted = 0
    for start_idx in range(0, len(active_symbols), batch_size):
        chunk = active_symbols[start_idx:start_idx + batch_size]
        batch_num = (start_idx // batch_size) + 1
        total_batches = (len(active_symbols) + batch_size - 1) // batch_size
        logger.info(f"Processing Factor Batch {batch_num}/{total_batches} ({len(chunk)} symbols: {chunk[0]}..{chunk[-1]})...")

        accumulated_factors = []
        for sym in chunk:
            try:
                sym_factors = fp.compute_factors_for_symbol(symbol=sym)
                accumulated_factors.extend(sym_factors)
            except Exception as e:
                logger.warning(f"Factor calculation error for {sym}: {e}")

        if accumulated_factors:
            upserted = db.upsert_quant_factors(accumulated_factors)
            total_factors_upserted += upserted
            logger.info(f"Batch {batch_num} complete: upserted {upserted} factor rows (Total so far: {total_factors_upserted})")

        del accumulated_factors
        gc.collect()

    # 4. Final verification query
    with db.get_connection() as conn:
        c1 = conn.execute("SELECT COUNT(DISTINCT symbol) FROM quant_factors_daily").fetchone()[0]
        c2 = conn.execute("SELECT COUNT(*) FROM securities_master WHERE is_active = 1").fetchone()[0]
        c3 = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily").fetchone()[0]

    logger.info("=======================================================")
    logger.info(f"UNIVERSE EXPANSION VERIFICATION:")
    logger.info(f"Distinct symbols in quant_factors_daily: {c1}")
    logger.info(f"Active symbols in securities_master: {c2}")
    logger.info(f"Latest factor session date: {c3}")
    logger.info("=======================================================")


if __name__ == "__main__":
    target = int(sys.argv[1]) if len(sys.argv) > 1 else 180
    run_batch_universe_expansion(target_total_symbols=target)
