"""
src/quant/factor_calculator.py
Vectorized Multi-Horizon Technical & Quantitative Factor Engine.
Task 2.2 / Phase 10: Computes 1D, 5D, 20D, 60D returns, SMAs (20, 50, 200), RSI-14,
and 20D annualized volatility, upserting into both factors_daily and quant_factors_daily.
"""

import os
import math
import time
import sqlite3
import logging
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, Tuple
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd

from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.FactorCalculator")


def compute_rsi_series(prices: pd.Series, period: int = 14) -> pd.Series:
    """Vectorized calculation of Relative Strength Index (RSI)."""
    delta = prices.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()

    rs = avg_gain / np.maximum(avg_loss, 1e-9)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi.fillna(50.0)


def _compute_symbol_factors_chunk(args: Tuple[str, List[str], Optional[int]]) -> Tuple[List[tuple], List[tuple], List[str]]:
    """Worker function executed inside ProcessPoolExecutor."""
    db_path, sym_chunk, recent_bars = args
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    records_factors = []
    records_quant = []
    processed_symbols = []
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        for symbol in sym_chunk:
            if recent_bars:
                cur = conn.execute("""
                    SELECT trading_date, open, high, low, close, volume
                    FROM (
                        SELECT trading_date, open, high, low, close, volume
                        FROM ohlcv_daily
                        WHERE symbol = ? AND is_synthetic = 0 AND series = 'EQ'
                        ORDER BY trading_date DESC
                        LIMIT ?
                    )
                    ORDER BY trading_date ASC
                """, (symbol, recent_bars))
            else:
                cur = conn.execute("""
                    SELECT trading_date, open, high, low, close, volume
                    FROM ohlcv_daily
                    WHERE symbol = ? AND is_synthetic = 0 AND series = 'EQ'
                    ORDER BY trading_date ASC
                """, (symbol,))
            rows = cur.fetchall()
            if len(rows) < 2:
                continue

            df = pd.DataFrame(rows, columns=["trading_date", "open", "high", "low", "close", "volume"])
            df["close"] = pd.to_numeric(df["close"], errors="coerce")
            df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
            df = df.dropna(subset=["close"]).reset_index(drop=True)
            if len(df) == 0:
                continue

            # Vectorized returns
            df["ret_1d"] = df["close"].pct_change().fillna(0.0)
            df["ret_5d"] = df["close"].pct_change(5)
            df["ret_20d"] = df["close"].pct_change(20)
            df["ret_60d"] = df["close"].pct_change(60)
            df["momentum_1y"] = df["close"].pct_change(252).fillna(0.10)

            # Vectorized Moving Averages
            df["sma_20"] = df["close"].rolling(20, min_periods=5).mean()
            df["sma_50"] = df["close"].rolling(50, min_periods=10).mean()
            df["sma_200"] = df["close"].rolling(200, min_periods=20).mean()

            # Vectorized 20-day Annualized Volatility
            df["volatility_20d"] = (df["ret_1d"].rolling(20, min_periods=5).std() * math.sqrt(252)).fillna(0.20)

            # Vectorized RSI-14
            df["rsi_14"] = compute_rsi_series(df["close"], 14)

            t_dates = df["trading_date"].tolist()
            closes = df["close"].tolist()
            volumes = df["volume"].tolist()
            ret_1ds = df["ret_1d"].tolist()
            ret_5ds = df["ret_5d"].tolist()
            ret_20ds = df["ret_20d"].tolist()
            sma_20s = df["sma_20"].tolist()
            sma_50s = df["sma_50"].tolist()
            sma_200s = df["sma_200"].tolist()
            vol_anns = df["volatility_20d"].tolist()
            rsi_14s = df["rsi_14"].tolist()
            mom_1ys = df["momentum_1y"].tolist()

            for i in range(len(df)):
                idx = i + 1
                t_date = str(t_dates[i])
                c_val = round(float(closes[i]), 2)
                vol_val = int(volumes[i])
                burn_in = 1 if idx >= 200 else 0
                s200 = sma_200s[i]
                sma_200_val = round(float(s200), 2) if (s200 is not None and not pd.isna(s200)) else None
                trend_regime = "BULLISH" if sma_200_val and c_val > sma_200_val else "BEARISH"
                vol_ann = round(float(vol_anns[i]), 4) if not pd.isna(vol_anns[i]) else 0.20

                r1 = ret_1ds[i]
                ret_1d = round(float(r1), 4) if (r1 is not None and not pd.isna(r1)) else None
                r5 = ret_5ds[i]
                ret_5d = round(float(r5), 4) if (r5 is not None and not pd.isna(r5)) else None
                r20 = ret_20ds[i]
                ret_20d = round(float(r20), 4) if (r20 is not None and not pd.isna(r20)) else None

                s20 = sma_20s[i]
                sma_20 = round(float(s20), 2) if (s20 is not None and not pd.isna(s20)) else None
                s50 = sma_50s[i]
                sma_50 = round(float(s50), 2) if (s50 is not None and not pd.isna(s50)) else None

                rsi_val = round(float(rsi_14s[i]), 2) if not pd.isna(rsi_14s[i]) else 50.0
                mom_val = round(float(mom_1ys[i]), 4) if not pd.isna(mom_1ys[i]) else 0.10

                records_factors.append((
                    symbol, t_date, c_val, c_val, vol_val, vol_val,
                    idx, burn_in, ret_1d, ret_5d, ret_20d, ret_20d,
                    sma_20, sma_50, sma_200_val, vol_ann, vol_ann,
                    rsi_val, mom_val,
                    trend_regime, now_iso
                ))

                records_quant.append((
                    symbol, t_date, ret_1d if ret_1d is not None else 0.0,
                    ret_5d, ret_20d, sma_20, sma_50, sma_200_val, vol_ann, now_iso
                ))
            processed_symbols.append(symbol)
    finally:
        conn.close()

    return records_factors, records_quant, processed_symbols


class VectorizedFactorCalculator:
    """Computes and upserts vectorized time-series factors across all NSE instruments."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def compute_for_symbol(self, symbol: str) -> int:
        """Computes technical factors for a single symbol and upserts to database."""
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT trading_date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE symbol = ? AND is_synthetic = 0 AND series = 'EQ'
                ORDER BY trading_date ASC
            """, (symbol,))
            rows = cur.fetchall()

        if len(rows) < 2:
            return 0

        df = pd.DataFrame([dict(r) for r in rows])
        df["close"] = pd.to_numeric(df["close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)
        df = df.dropna(subset=["close"]).reset_index(drop=True)

        if len(df) == 0:
            return 0

        # Vectorized returns
        df["ret_1d"] = df["close"].pct_change().fillna(0.0)
        df["ret_5d"] = df["close"].pct_change(5)
        df["ret_20d"] = df["close"].pct_change(20)
        df["ret_60d"] = df["close"].pct_change(60)
        df["momentum_1y"] = df["close"].pct_change(252).fillna(0.10)

        # Vectorized Moving Averages
        df["sma_20"] = df["close"].rolling(20, min_periods=5).mean()
        df["sma_50"] = df["close"].rolling(50, min_periods=10).mean()
        df["sma_200"] = df["close"].rolling(200, min_periods=20).mean()

        # Vectorized 20-day Annualized Volatility
        df["volatility_20d"] = (df["ret_1d"].rolling(20, min_periods=5).std() * math.sqrt(252)).fillna(0.20)

        # Vectorized RSI-14
        df["rsi_14"] = compute_rsi_series(df["close"], 14)

        now_iso = datetime.now(timezone.utc).isoformat()
        records_factors = []
        records_quant = []

        total_sessions = len(df)
        for i, (_, r) in enumerate(df.iterrows(), start=1):
            t_date = str(r["trading_date"])
            c_val = round(float(r["close"]), 2)
            vol_val = int(r["volume"])
            burn_in = 1 if i >= 200 else 0
            sma_200_val = round(float(r["sma_200"]), 2) if pd.notna(r["sma_200"]) else None
            trend_regime = "BULLISH" if sma_200_val and c_val > sma_200_val else "BEARISH"
            vol_ann = round(float(r["volatility_20d"]), 4)

            ret_1d = round(float(r["ret_1d"]), 4) if pd.notna(r["ret_1d"]) else None
            ret_5d = round(float(r["ret_5d"]), 4) if pd.notna(r["ret_5d"]) else None
            ret_20d = round(float(r["ret_20d"]), 4) if pd.notna(r["ret_20d"]) else None
            sma_20 = round(float(r["sma_20"]), 2) if pd.notna(r["sma_20"]) else None
            sma_50 = round(float(r["sma_50"]), 2) if pd.notna(r["sma_50"]) else None

            # factors_daily record
            records_factors.append((
                symbol,
                t_date,
                c_val,
                c_val,
                vol_val,
                vol_val,
                i,
                burn_in,
                ret_1d,
                ret_5d,
                ret_20d,
                ret_20d,  # return_20d alias
                sma_20,
                sma_50,
                sma_200_val,
                vol_ann,
                vol_ann,
                round(float(r["rsi_14"]), 2),
                round(float(r["momentum_1y"]), 4),
                trend_regime,
                now_iso
            ))

            # quant_factors_daily record
            records_quant.append((
                symbol,
                t_date,
                ret_1d if ret_1d is not None else 0.0,
                ret_5d,
                ret_20d,
                sma_20,
                sma_50,
                sma_200_val,
                vol_ann,
                now_iso
            ))

        with self.db.get_connection() as conn:
            conn.executemany("""
                INSERT INTO factors_daily (
                    symbol, trading_date, close, adj_close, volume, adj_volume,
                    sessions_available, burn_in_complete,
                    ret_1d, ret_5d, ret_20d, return_20d, sma_20, sma_50, sma_200,
                    volatility_20d, volatility_annualized, rsi_14, momentum_1y,
                    trend_regime, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol, trading_date) DO UPDATE SET
                    close = excluded.close,
                    sessions_available = excluded.sessions_available,
                    burn_in_complete = excluded.burn_in_complete,
                    ret_1d = excluded.ret_1d,
                    ret_5d = excluded.ret_5d,
                    ret_20d = excluded.ret_20d,
                    return_20d = excluded.return_20d,
                    sma_20 = excluded.sma_20,
                    sma_50 = excluded.sma_50,
                    sma_200 = excluded.sma_200,
                    volatility_20d = excluded.volatility_20d,
                    volatility_annualized = excluded.volatility_annualized,
                    rsi_14 = excluded.rsi_14,
                    momentum_1y = excluded.momentum_1y,
                    trend_regime = excluded.trend_regime,
                    updated_at = excluded.updated_at
            """, records_factors)

            conn.executemany("""
                INSERT INTO quant_factors_daily (
                    symbol, trading_date, ret_1d, ret_5d, ret_20d,
                    sma_20, sma_50, sma_200, volatility_annualized, is_orphaned, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                ON CONFLICT(symbol, trading_date) DO UPDATE SET
                    ret_1d = excluded.ret_1d,
                    ret_5d = excluded.ret_5d,
                    ret_20d = excluded.ret_20d,
                    sma_20 = excluded.sma_20,
                    sma_50 = excluded.sma_50,
                    sma_200 = excluded.sma_200,
                    volatility_annualized = excluded.volatility_annualized,
                    is_orphaned = 0,
                    updated_at = excluded.updated_at
            """, records_quant)

        return len(records_factors)

    def compute_for_all_parallel(
        self,
        symbols: Optional[List[str]] = None,
        max_workers: Optional[int] = None,
        recent_bars: Optional[int] = None
    ) -> Dict[str, Any]:
        """Multi-process factor engine partitioning symbols across CPU cores via ProcessPoolExecutor."""
        t0 = time.time()
        with self.db.get_connection() as conn:
            if symbols:
                target_symbols = symbols
            else:
                cur = conn.execute("SELECT DISTINCT symbol FROM ohlcv_daily WHERE is_synthetic = 0 AND series = 'EQ'")
                target_symbols = [r[0] for r in cur.fetchall()]

        if not target_symbols:
            return {"processed_symbols": 0, "total_bars_factored": 0, "duration_seconds": 0.0}

        n_workers = max_workers or min(os.cpu_count() or 4, 6)
        if os.getenv("RENDER", "").lower() in ("true", "1") or os.getenv("CLOUD_LIGHTWEIGHT_MODE", "").lower() in ("true", "1"):
            n_workers = min(n_workers, 2)
        n_workers = max(1, min(n_workers, len(target_symbols)))
        chunk_size = math.ceil(len(target_symbols) / n_workers)
        chunks = [target_symbols[i:i + chunk_size] for i in range(0, len(target_symbols), chunk_size)]

        db_path = getattr(self.db, "db_path", "data/market_lab.db")
        tasks = [(db_path, ch, recent_bars) for ch in chunks]

        all_factors = []
        all_quant = []
        all_processed = []

        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            for fac_recs, quant_recs, syms in executor.map(_compute_symbol_factors_chunk, tasks):
                all_factors.extend(fac_recs)
                all_quant.extend(quant_recs)
                all_processed.extend(syms)

        # Single bulk-upsert in parent process under WAL mode
        if all_factors:
            with self.db.get_connection() as conn:
                conn.execute("PRAGMA journal_mode = WAL;")
                conn.execute("PRAGMA synchronous = NORMAL;")
                conn.executemany("""
                    INSERT INTO factors_daily (
                        symbol, trading_date, close, adj_close, volume, adj_volume,
                        sessions_available, burn_in_complete,
                        ret_1d, ret_5d, ret_20d, return_20d, sma_20, sma_50, sma_200,
                        volatility_20d, volatility_annualized, rsi_14, momentum_1y,
                        trend_regime, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, trading_date) DO UPDATE SET
                        close = excluded.close,
                        sessions_available = excluded.sessions_available,
                        burn_in_complete = excluded.burn_in_complete,
                        ret_1d = excluded.ret_1d,
                        ret_5d = excluded.ret_5d,
                        ret_20d = excluded.ret_20d,
                        return_20d = excluded.return_20d,
                        sma_20 = excluded.sma_20,
                        sma_50 = excluded.sma_50,
                        sma_200 = excluded.sma_200,
                        volatility_20d = excluded.volatility_20d,
                        volatility_annualized = excluded.volatility_annualized,
                        rsi_14 = excluded.rsi_14,
                        momentum_1y = excluded.momentum_1y,
                        trend_regime = excluded.trend_regime,
                        updated_at = excluded.updated_at
                """, all_factors)

                conn.executemany("""
                    INSERT INTO quant_factors_daily (
                        symbol, trading_date, ret_1d, ret_5d, ret_20d,
                        sma_20, sma_50, sma_200, volatility_annualized, is_orphaned, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?)
                    ON CONFLICT(symbol, trading_date) DO UPDATE SET
                        ret_1d = excluded.ret_1d,
                        ret_5d = excluded.ret_5d,
                        ret_20d = excluded.ret_20d,
                        sma_20 = excluded.sma_20,
                        sma_50 = excluded.sma_50,
                        sma_200 = excluded.sma_200,
                        volatility_annualized = excluded.volatility_annualized,
                        is_orphaned = 0,
                        updated_at = excluded.updated_at
                """, all_quant)
                conn.commit()

        duration = round(time.time() - t0, 3)
        logger.info(f"Parallel factor calculation completed: {len(all_processed)} symbols ({len(all_factors)} bars) in {duration}s across {n_workers} cores.")
        return {
            "processed_symbols": len(all_processed),
            "total_bars_factored": len(all_factors),
            "total_targets": len(target_symbols),
            "duration_seconds": duration,
            "workers_used": n_workers
        }

    def compute_for_all(self, symbols: Optional[List[str]] = None) -> Dict[str, Any]:
        """Computes factors for all or filtered symbols using multi-core parallelism."""
        return self.compute_for_all_parallel(symbols=symbols)
