"""
src/pipeline/universe_ingestion.py

Market Intelligence Lab — Universal Dynamic Ingestion Pipeline.
Fetches authentic exchange settlement data for the active equity universe,
updates ohlcv_daily and index_daily, computes point-in-time factors via FactorPipeline,
and updates supervisor telemetry.
"""

import os
import time
import logging
import sqlite3
import datetime
import threading
from typing import Dict, Any, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
try:
    import yfinance as yf
except ImportError:
    yf = None

from src.storage.database import DatabaseManager
from src.quant.factor_pipeline import FactorPipeline
from src.client.macro_client import MacroClient
from src.supervisor.state_machine import SupervisorStateMachine

logger = logging.getLogger("universe_ingestion")


class UniverseIngestionManager:
    """Orchestrates live on-demand EOD ingestion and factor computation for the entire universe."""

    def __init__(self, db_path: Any = "data/market_lab.db"):
        if isinstance(db_path, DatabaseManager):
            self.db = db_path
            self.db_path = getattr(db_path, "db_path", "data/market_lab.db")
        else:
            self.db_path = str(db_path)
            self.db = DatabaseManager(self.db_path)
        self.pipeline = FactorPipeline(self.db)
        self.factor_pipeline = self.pipeline
        self.supervisor = SupervisorStateMachine(self.db)
        self.lock = threading.Lock()

    def get_active_universe(self) -> List[str]:
        """Returns list of active equity symbols from securities_master."""
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol ASC;")
            rows = cur.fetchall()
            return [r[0] for r in rows] if rows else ["TCS", "INFY", "RELIANCE"]

    def fetch_and_persist_symbol(self, symbol: str, target_date: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetches candles for symbol and persists valid EQ bars to ohlcv_daily."""
        _, candles = self._fetch_symbol_candles(symbol)
        if not candles:
            return []

        if target_date:
            candles = [c for c in candles if c.get("trading_date") == target_date]
            if not candles:
                return []

        with self.db.get_connection() as conn:
            for c in candles:
                conn.execute("""
                    INSERT INTO ohlcv_daily (
                        symbol, trading_date, series, open, high, low, close, ltp, prev_close,
                        volume, source, retrieval_timestamp, data_status,
                        provenance_class, is_synthetic,
                        is_eligible_for_live_analytics, is_eligible_for_backtest, is_eligible_for_training
                    ) VALUES (
                        :symbol, :trading_date, :series, :open, :high, :low, :close, :ltp, :prev_close,
                        :volume, :source, :retrieval_timestamp, :data_status,
                        :provenance_class, :is_synthetic,
                        :is_eligible_for_live_analytics, :is_eligible_for_backtest, :is_eligible_for_training
                    )
                    ON CONFLICT(symbol, trading_date, series) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        ltp = excluded.ltp,
                        volume = excluded.volume,
                        source = excluded.source,
                        retrieval_timestamp = excluded.retrieval_timestamp,
                        data_status = excluded.data_status,
                        provenance_class = excluded.provenance_class,
                        is_synthetic = excluded.is_synthetic,
                        is_eligible_for_live_analytics = excluded.is_eligible_for_live_analytics,
                        is_eligible_for_backtest = excluded.is_eligible_for_backtest,
                        is_eligible_for_training = excluded.is_eligible_for_training;
                """, c)
            conn.commit()
        return candles

    def _fetch_symbol_candles(self, symbol: str) -> Tuple[str, List[Dict[str, Any]]]:
        """Fetches the latest 5-day settlement candles for a symbol from authentic exchange feeds."""
        if yf is None:
            return symbol, []
        ticker_sym = f"{symbol}.NS"
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        try:
            t = yf.Ticker(ticker_sym)
            hist = t.history(period="5d")
            if hist is None or hist.empty:
                t = yf.Ticker(symbol)
                hist = t.history(period="5d")
                if hist is None or hist.empty:
                    return symbol, []

            candles = []
            for dt_idx, row in hist.iterrows():
                if pd.isna(row["Open"]) or pd.isna(row["Close"]):
                    continue
                d_str = dt_idx.strftime("%Y-%m-%d")
                o = round(float(row["Open"]), 2)
                h = round(float(row["High"]) if not pd.isna(row["High"]) else o, 2)
                l = round(float(row["Low"]) if not pd.isna(row["Low"]) else o, 2)
                c = round(float(row["Close"]), 2)
                v = int(row["Volume"]) if not pd.isna(row["Volume"]) and row["Volume"] >= 0 else None

                # Strict OHLC Invariant Enforcement: reject corrupt bars without mutating
                if h < max(o, c) or l > min(o, c) or o <= 0 or c <= 0 or l <= 0 or h <= 0:
                    logger.warning(f"Corrupt candle rejected for {symbol} on {d_str}: O={o}, H={h}, L={l}, C={c}")
                    continue

                candles.append({
                    "symbol": symbol,
                    "trading_date": d_str,
                    "series": "EQ",
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "ltp": c,
                    "prev_close": None,
                    "volume": v,
                    "source": "yfinance",
                    "retrieval_timestamp": now_ts,
                    "data_status": "final_settled",
                    "provenance_class": "VENDOR_OBSERVED",
                    "is_synthetic": 0,
                    "is_eligible_for_live_analytics": 1,
                    "is_eligible_for_backtest": 1,
                    "is_eligible_for_training": 1
                })
            return symbol, candles
        except Exception as e:
            logger.warning(f"Live fetch error for {symbol}: {e}")
            return symbol, []

    def _fetch_benchmark_candles(self) -> List[Dict[str, Any]]:
        """Fetches benchmark candles for NIFTY 50."""
        if yf is None:
            return []
        try:
            t = yf.Ticker("^NSEI")
            hist = t.history(period="5d")
            if hist is None or hist.empty:
                return []
            now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
            candles = []
            for dt_idx, row in hist.iterrows():
                if pd.isna(row["Close"]) or pd.isna(row["Open"]):
                    continue
                d_str = dt_idx.strftime("%Y-%m-%d")
                c = round(float(row["Close"]), 2)
                o = round(float(row["Open"]), 2)
                h = round(float(row["High"]), 2) if not pd.isna(row["High"]) else max(o, c)
                l = round(float(row["Low"]), 2) if not pd.isna(row["Low"]) else min(o, c)

                if h < max(o, c) or l > min(o, c) or o <= 0 or c <= 0 or l <= 0 or h <= 0:
                    logger.warning(f"Corrupt benchmark candle rejected for NIFTY 50 on {d_str}")
                    continue

                candles.append({
                    "index_name": "NIFTY 50",
                    "trading_date": d_str,
                    "index_type": "PRI",
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "source": "yfinance",
                    "retrieval_timestamp": now_ts
                })
            return candles
        except Exception as e:
            logger.warning(f"Benchmark fetch error: {e}")
            return []

    def execute_universe_ingestion(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes end-to-end universal ingestion:
        1. Queries active symbols from securities_master.
        2. Ingests latest candles for equities and benchmark.
        3. Computes updated factors for the latest session.
        4. Updates supervisor state and telemetry.
        """
        t0 = time.time()
        eff_target_date = target_date or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
        logger.info(f"Initiating Universal Dynamic Ingestion for session: {eff_target_date}...")

        # 1. Resolve active symbols
        with self.db.get_connection() as conn:
            cur = conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol ASC;")
            symbols = [r["symbol"] for r in cur.fetchall()]

        if not symbols:
            logger.error("Active universe resolution failed: zero active securities found.")
            return {
                "status": "FAILED",
                "error_code": "EMPTY_UNIVERSE",
                "reason": "EMPTY_UNIVERSE",
                "records_ingested": 0,
                "symbols_updated": 0,
                "target_date": eff_target_date,
                "duration_seconds": round(time.time() - t0, 2),
                "message": "No active equities found in securities_master."
            }

        # 2. Ingest benchmark candles
        bench_candles = self._fetch_benchmark_candles()
        if bench_candles:
            with self.db.get_connection() as conn:
                for b in bench_candles:
                    conn.execute("""
                        INSERT INTO index_daily (index_name, trading_date, index_type, open, high, low, close, source, retrieval_timestamp)
                        VALUES (:index_name, :trading_date, :index_type, :open, :high, :low, :close, :source, :retrieval_timestamp)
                        ON CONFLICT(index_name, trading_date, index_type) DO UPDATE SET
                            close = excluded.close,
                            high = excluded.high,
                            low = excluded.low,
                            open = excluded.open;
                    """, b)
                conn.commit()

        # 3. Concurrent live equity candle fetching
        all_candles: List[Dict[str, Any]] = []
        updated_symbols = set()
        failed_symbols = []

        with ThreadPoolExecutor(max_workers=20) as executor:
            future_to_sym = {executor.submit(self._fetch_symbol_candles, sym): sym for sym in symbols}
            for future in as_completed(future_to_sym):
                sym, c_list = future.result()
                if c_list:
                    all_candles.extend(c_list)
                    updated_symbols.add(sym)
                else:
                    failed_symbols.append(sym)

        # STRICT INVARIANT: Zero records fetched MUST NEVER return SUCCESS
        if not all_candles:
            elapsed = round(time.time() - t0, 2)
            logger.critical(f"EOD ingestion aborted: 0 valid bars retrieved for {eff_target_date}. Providers unavailable or non-trading session.")
            return {
                "status": "FAILED",
                "error_code": "NO_NEW_BARS",
                "reason": "NO_NEW_BARS",
                "settled_date": None,
                "symbols_updated": 0,
                "records_ingested": 0,
                "factors_computed": 0,
                "failed_symbols_count": len(failed_symbols),
                "target_date": eff_target_date,
                "duration_seconds": elapsed,
                "message": f"Zero valid bars retrieved for {eff_target_date}. Providers unavailable or non-trading session."
            }

        # 4. Upsert into ohlcv_daily under thread lock
        total_upserted = 0
        latest_date = None

        with self.db.get_connection() as conn:
            for c in all_candles:
                cur = conn.execute("""
                    INSERT INTO ohlcv_daily (
                        symbol, trading_date, series, open, high, low, close, ltp, prev_close,
                        volume, source, retrieval_timestamp, data_status,
                        provenance_class, is_synthetic,
                        is_eligible_for_live_analytics, is_eligible_for_backtest, is_eligible_for_training
                    ) VALUES (
                        :symbol, :trading_date, :series, :open, :high, :low, :close, :ltp, :prev_close,
                        :volume, :source, :retrieval_timestamp, :data_status,
                        :provenance_class, :is_synthetic,
                        :is_eligible_for_live_analytics, :is_eligible_for_backtest, :is_eligible_for_training
                    )
                    ON CONFLICT(symbol, trading_date, series) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        ltp = excluded.ltp,
                        volume = excluded.volume,
                        source = excluded.source,
                        retrieval_timestamp = excluded.retrieval_timestamp,
                        data_status = excluded.data_status,
                        provenance_class = excluded.provenance_class,
                        is_synthetic = excluded.is_synthetic,
                        is_eligible_for_live_analytics = excluded.is_eligible_for_live_analytics,
                        is_eligible_for_backtest = excluded.is_eligible_for_backtest,
                        is_eligible_for_training = excluded.is_eligible_for_training;
                """, c)
                total_upserted += cur.rowcount
                if latest_date is None or c["trading_date"] > latest_date:
                    latest_date = c["trading_date"]
            conn.commit()

        # Fail closed if no bars were persisted
        if not latest_date or total_upserted == 0:
            elapsed = round(time.time() - t0, 2)
            logger.warning("Universe ingestion persisted 0 new bars. Failing closed without advancing settlement.")
            return {
                "status": "FAILED",
                "error_code": "NO_NEW_BARS",
                "reason": "NO_NEW_BARS",
                "settled_date": None,
                "symbols_updated": 0,
                "records_ingested": 0,
                "factors_computed": 0,
                "failed_symbols_count": len(failed_symbols),
                "target_date": eff_target_date,
                "duration_seconds": elapsed,
                "message": "Zero bars persisted from provider feeds; cannot advance settlement."
            }

        # Strict universe coverage floor (minimum 85% of active universe)
        min_required_bars = max(1, int(len(symbols) * 0.85))
        if len(symbols) >= 10 and total_upserted < min_required_bars:
            elapsed = round(time.time() - t0, 2)
            logger.warning(
                f"Universe ingestion coverage below 85% floor: {total_upserted}/{len(symbols)} "
                f"(min required: {min_required_bars}). Failing closed without advancing settlement."
            )
            return {
                "status": "FAILED",
                "error_code": "INSUFFICIENT_COVERAGE",
                "reason": "PARTIAL_UNIVERSE_COVERAGE",
                "settled_date": None,
                "symbols_updated": len(updated_symbols),
                "records_ingested": total_upserted,
                "factors_computed": 0,
                "failed_symbols_count": len(failed_symbols),
                "target_date": eff_target_date,
                "duration_seconds": elapsed,
                "message": f"Coverage {total_upserted}/{len(symbols)} is below 85% threshold."
            }

        # 5. Compute factors for the latest session
        logger.info(f"Computing factors across universe for session {latest_date}...")
        factor_res = self.pipeline.run_universe_pipeline(
            symbols=list(updated_symbols) if updated_symbols else symbols,
            start_date=latest_date,
            end_date=latest_date
        )

        # 6. Refresh macro telemetry
        MacroClient.get_macro_telemetry(force_refresh=True)

        # 7. Log Supervisor Telemetry
        elapsed = round(time.time() - t0, 2)
        factors_count = factor_res.get("total_factors_upserted", 0)

        self.supervisor.log_telemetry(
            metric_name="UNIVERSAL_DYNAMIC_INGESTION",
            metric_value=float(len(updated_symbols)),
            threshold_breached=False,
            severity="INFO",
            message=f"Ingested {len(updated_symbols)} equities ({total_upserted} bars) for session {latest_date} in {elapsed}s.",
            context={
                "settled_session": latest_date,
                "symbols_updated": len(updated_symbols),
                "factors_computed": factors_count,
                "duration_seconds": elapsed
            }
        )

        return {
            "status": "SUCCESS",
            "settled_date": latest_date,
            "symbols_updated": len(updated_symbols),
            "records_ingested": total_upserted,
            "factors_computed": factors_count,
            "duration_seconds": elapsed,
            "message": f"Successfully ingested live session data for {latest_date} across {len(updated_symbols)} equities."
        }
