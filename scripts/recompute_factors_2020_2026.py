#!/usr/bin/env python3
"""
scripts/recompute_factors_2020_2026.py
Full-Horizon Factor Generation Engine (2020–2026).

Computes point-in-time quantitative and technical factors across the entire 181-equity universe:
- Corporate-action-adjusted prices (adj_close, adj_volume) via CorporateActionsManager.
- Technical indicators: sma_20, sma_50, sma_200, rsi_14, volatility_20d, volatility_annualized, momentum_1y, trend_regime.
- Enforces strict 252-session burn-in: long-term factors (sma_200, momentum_1y, volatility_annualized)
  are strictly NULL for sessions < 252.
- Persists into `factors_daily` and updates `quant_factors_daily`.
"""

import sys
import time
import logging
from datetime import datetime, timezone
import pandas as pd
import numpy as np

from src.storage.database import DatabaseManager
from src.data.corporate_actions import CorporateActionsManager
from src.data.historical_backfill import HistoricalBackfillCoordinator
from src.factors.engine import FactorEngine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("MIL.FactorRecompute")


def ensure_factors_table(db: DatabaseManager) -> None:
    """Ensures factors_daily table and indexes exist."""
    with db.get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS factors_daily (
                symbol TEXT NOT NULL,
                trading_date TEXT NOT NULL,
                close REAL NOT NULL,
                adj_close REAL NOT NULL,
                volume INTEGER NOT NULL,
                adj_volume INTEGER NOT NULL,
                sessions_available INTEGER NOT NULL,
                burn_in_complete INTEGER NOT NULL,
                ret_1d REAL,
                ret_5d REAL,
                ret_20d REAL,
                sma_20 REAL,
                sma_50 REAL,
                sma_200 REAL,
                volatility_20d REAL,
                volatility_annualized REAL,
                rsi_14 REAL,
                momentum_1y REAL,
                trend_regime TEXT,
                updated_at TEXT,
                PRIMARY KEY (symbol, trading_date)
            );
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_factors_daily_date ON factors_daily(trading_date);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_factors_daily_symbol_date ON factors_daily(symbol, trading_date);")
        conn.commit()


def run_factor_recompute():
    print("=" * 80)
    print("Market Intelligence Lab (MIL) — Full-Horizon Factor Calculation Pass (2020–2026)")
    print("Point-in-Time Corporate-Action-Adjusted Factor Engine")
    print("=" * 80)

    db = DatabaseManager("data/market_lab.db")
    ca_manager = CorporateActionsManager(db)
    coordinator = HistoricalBackfillCoordinator(db=db, ca_manager=ca_manager)
    factor_engine = FactorEngine(db=db, ca_manager=ca_manager)

    ensure_factors_table(db)

    symbols = coordinator.get_universe_symbols()
    total_symbols = len(symbols)
    print(f"[*] Universe initialized: {total_symbols} active instruments.")
    print("-" * 80)

    t_start = time.time()
    total_factor_rows = 0
    burn_in_achieved_count = 0
    now_iso = datetime.now(timezone.utc).isoformat()

    batch_factors_daily = []
    batch_quant_factors = []

    for idx, sym in enumerate(symbols, 1):
        s_t0 = time.time()
        df = factor_engine.compute_factors_for_symbol(sym)
        s_elapsed = time.time() - s_t0

        if df.empty:
            print(f"[{idx:03d}/{total_symbols}] {sym:<12}: 0 rows (no authentic settlement history)")
            continue

        n_rows = len(df)
        total_factor_rows += n_rows

        has_burn_in = (df["burn_in_complete"] == True).any()
        if has_burn_in:
            burn_in_achieved_count += 1
            burn_date = df[df["burn_in_complete"] == True].iloc[0]["trading_date"]
            burn_info = f"Burn-in on {burn_date}"
        else:
            burn_info = f"Burn-in pending ({n_rows}/252 sessions)"

        # Prepare records for factors_daily
        for r in df.to_dict(orient="records"):
            batch_factors_daily.append({
                "symbol": r["symbol"],
                "trading_date": r["trading_date"],
                "close": r["close"],
                "adj_close": r["adj_close"],
                "volume": r["volume"],
                "adj_volume": r["adj_volume"],
                "sessions_available": r["sessions_available"],
                "burn_in_complete": int(r["burn_in_complete"]),
                "ret_1d": r["ret_1d"],
                "ret_5d": r["ret_5d"],
                "ret_20d": r["ret_20d"],
                "sma_20": r["sma_20"],
                "sma_50": r["sma_50"],
                "sma_200": r["sma_200"],
                "volatility_20d": r["volatility_20d"],
                "volatility_annualized": r["volatility_annualized"],
                "rsi_14": r["rsi_14"],
                "momentum_1y": r["momentum_1y"],
                "trend_regime": r["trend_regime"],
                "updated_at": now_iso
            })

            batch_quant_factors.append({
                "symbol": r["symbol"],
                "trading_date": r["trading_date"],
                "ret_1d": r["ret_1d"] or 0.0,
                "ret_5d": r["ret_5d"],
                "ret_20d": r["ret_20d"],
                "vol_20d_annualized": r["volatility_20d"],
                "sma_20": r["sma_20"],
                "sma_50": r["sma_50"],
                "sma_200": r["sma_200"],
                "volatility_annualized": r["volatility_annualized"],
                "updated_at": now_iso,
                "is_orphaned": 0
            })

        # Batch insert every 10 symbols or at end
        if idx % 10 == 0 or idx == total_symbols:
            with db.get_connection() as conn:
                # 1. Insert into factors_daily
                conn.executemany("""
                    INSERT OR REPLACE INTO factors_daily (
                        symbol, trading_date, close, adj_close, volume, adj_volume,
                        sessions_available, burn_in_complete, ret_1d, ret_5d, ret_20d,
                        sma_20, sma_50, sma_200, volatility_20d, volatility_annualized,
                        rsi_14, momentum_1y, trend_regime, updated_at
                    ) VALUES (
                        :symbol, :trading_date, :close, :adj_close, :volume, :adj_volume,
                        :sessions_available, :burn_in_complete, :ret_1d, :ret_5d, :ret_20d,
                        :sma_20, :sma_50, :sma_200, :volatility_20d, :volatility_annualized,
                        :rsi_14, :momentum_1y, :trend_regime, :updated_at
                    )
                """, batch_factors_daily)

                # 2. Update quant_factors_daily
                conn.executemany("""
                    INSERT INTO quant_factors_daily (
                        symbol, trading_date, ret_1d, ret_5d, ret_20d, vol_20d_annualized,
                        sma_20, sma_50, sma_200, volatility_annualized, updated_at, is_orphaned
                    ) VALUES (
                        :symbol, :trading_date, :ret_1d, :ret_5d, :ret_20d, :vol_20d_annualized,
                        :sma_20, :sma_50, :sma_200, :volatility_annualized, :updated_at, :is_orphaned
                    )
                    ON CONFLICT(symbol, trading_date) DO UPDATE SET
                        ret_1d = excluded.ret_1d,
                        ret_5d = excluded.ret_5d,
                        ret_20d = excluded.ret_20d,
                        vol_20d_annualized = excluded.vol_20d_annualized,
                        sma_20 = excluded.sma_20,
                        sma_50 = excluded.sma_50,
                        sma_200 = excluded.sma_200,
                        volatility_annualized = excluded.volatility_annualized,
                        updated_at = excluded.updated_at,
                        is_orphaned = 0;
                """, batch_quant_factors)

                conn.commit()

            batch_factors_daily.clear()
            batch_quant_factors.clear()

        print(f"[{idx:03d}/{total_symbols}] {sym:<12}: {n_rows:,} rows in {s_elapsed:.2f}s | {burn_info}")

    total_time = time.time() - t_start

    print("\n" + "=" * 80)
    print("FULL-HORIZON FACTOR RECOMPUTATION SUMMARY")
    print("=" * 80)
    print(f"Total Computation Duration:  {total_time:.2f} seconds ({total_time / 60.0:.2f} minutes)")
    print(f"Total Universe Symbols:      {total_symbols}")
    print(f"Total Factor Rows Generated: {total_factor_rows:,}")
    print(f"Instruments Reaching Burn-In:{burn_in_achieved_count} / {total_symbols} ({round(burn_in_achieved_count / total_symbols * 100, 1)}%)")
    print(f"Calculation Throughput:      {round(total_factor_rows / total_time, 1):,} rows/second")
    print("=" * 80)


if __name__ == "__main__":
    run_factor_recompute()
