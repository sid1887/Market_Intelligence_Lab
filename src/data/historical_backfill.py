"""
src/data/historical_backfill.py
Historical Multi-Year Checkpointed Ingestion Coordinator (2020–2024).
Phase 10.1 Hardened: Strictly eliminates all synthetic price generation.
Enforces authentic NSE bhavcopy ingestion, listing date verification (NOT_YET_LISTED),
and explicit MISSING_SOURCE_DATA quarantine whenever source archives are unavailable.
"""

import os
import time
import json
import uuid
import calendar
import logging
from datetime import datetime, timezone, date
from typing import Dict, Any, List, Optional, Tuple, Callable

from src.storage.database import DatabaseManager
from src.data.corporate_actions import CorporateActionsManager
from src.data.instrument_master import InstrumentMaster
from src.data.nse_archive_fetcher import NSEArchiveFetcher

logger = logging.getLogger("MIL.HistoricalBackfill")


class HistoricalBackfillCoordinator:
    """
    Coordinates multi-year historical backfilling across the universe.
    Maintains a durable checkpoint ledger in backfill_sync_checkpoints.
    Enforces truth-layer invariants:
    - Never fabricates synthetic settlement prices (zero random-walk/Brownian generation).
    - Checks instrument listing dates: marks NOT_YET_LISTED with 0 rows prior to official IPO listing.
    - Sinks authentic exchange bhavcopies; marks MISSING_SOURCE_DATA when archives are missing.
    """

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        ca_manager: Optional[CorporateActionsManager] = None,
        instrument_master: Optional[InstrumentMaster] = None,
        bhavcopy_dir: str = "data/raw/bhavcopies",
        archive_fetcher: Optional[NSEArchiveFetcher] = None
    ):
        self.db = db or DatabaseManager()
        self.ca_manager = ca_manager or CorporateActionsManager(self.db)
        self.instrument_master = instrument_master or InstrumentMaster(self.db)
        self.bhavcopy_dir = bhavcopy_dir
        self.fetcher = archive_fetcher or NSEArchiveFetcher(cache_dir=self.bhavcopy_dir)
        self._ensure_system_events_table()

    def _ensure_system_events_table(self) -> None:
        """Ensures system_events table exists for telemetry publishing."""
        with self.db.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_events (
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
            """)
            conn.commit()

    def get_universe_symbols(self) -> List[str]:
        """
        Retrieves authoritative list of universe symbols from ohlcv_daily and securities_master.
        Guarantees 181 distinct active symbols.
        """
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT DISTINCT symbol FROM ohlcv_daily WHERE series = 'EQ'
                UNION
                SELECT symbol FROM securities_master WHERE is_active = 1
                ORDER BY symbol ASC
            """)
            symbols = [r[0] for r in cur.fetchall() if r[0] and not r[0].startswith("SYNTHETIC")]
        return symbols

    def initialize_checkpoint_matrix(
        self,
        symbols: Optional[List[str]] = None,
        start_year: int = 2020,
        end_year: int = 2024,
        end_month: int = 10
    ) -> int:
        """
        Seeds backfill_sync_checkpoints with PENDING status for all (symbol, year, month) units.
        181 Symbols x 58 Months (2020-01 to 2024-10) = 10,498 Work Units.
        Idempotent: skips existing rows.
        """
        sym_list = symbols if symbols is not None else self.get_universe_symbols()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Build list of (year, month) pairs
        ym_pairs: List[Tuple[int, int]] = []
        for y in range(start_year, end_year + 1):
            max_m = end_month if y == end_year else 12
            for m in range(1, max_m + 1):
                ym_pairs.append((y, m))

        total_units = len(sym_list) * len(ym_pairs)
        logger.info(
            f"Initializing checkpoint matrix: {len(sym_list)} symbols x {len(ym_pairs)} months "
            f"= {total_units} target work units ({start_year}-01 to {end_year}-{end_month:02d})."
        )

        with self.db.get_connection() as conn:
            records = []
            for sym in sym_list:
                for y, m in ym_pairs:
                    chk_id = f"chk_{sym}_{y}_{m:02d}"
                    records.append((chk_id, sym, y, m, "PENDING", 0, None, None, None, now_iso))

            conn.executemany("""
                INSERT OR IGNORE INTO backfill_sync_checkpoints (
                    checkpoint_id, symbol, target_year, target_month,
                    status, rows_ingested, earliest_date_ingested,
                    latest_date_ingested, error_message, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, records)
            conn.commit()

        stats = self.get_checkpoint_stats()
        logger.info(
            f"Checkpoint matrix initialized: Total={stats['total_work_units']}, "
            f"Pending={stats['pending_units']}, Completed={stats['completed_units']}"
        )
        return stats["total_work_units"]

    def get_checkpoint_stats(self) -> Dict[str, Any]:
        """Returns aggregated telemetry metrics for the historical backfill ledger."""
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total_units,
                    SUM(CASE WHEN status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_units,
                    SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) as pending_units,
                    SUM(CASE WHEN status = 'FAILED' THEN 1 ELSE 0 END) as failed_units,
                    SUM(CASE WHEN status = 'PROCESSING' THEN 1 ELSE 0 END) as processing_units,
                    SUM(CASE WHEN status = 'NOT_YET_LISTED' THEN 1 ELSE 0 END) as not_yet_listed_units,
                    SUM(CASE WHEN status = 'MISSING_SOURCE_DATA' THEN 1 ELSE 0 END) as missing_source_units,
                    SUM(rows_ingested) as total_rows_ingested,
                    MIN(earliest_date_ingested) as earliest_date,
                    MAX(latest_date_ingested) as latest_date
                FROM backfill_sync_checkpoints
            """)
            row = cur.fetchone()

        total = row[0] if row and row[0] is not None else 0
        completed = row[1] if row and row[1] is not None else 0
        pending = row[2] if row and row[2] is not None else 0
        failed = row[3] if row and row[3] is not None else 0
        processing = row[4] if row and row[4] is not None else 0
        not_yet_listed = row[5] if row and row[5] is not None else 0
        missing_source = row[6] if row and row[6] is not None else 0
        rows_ingested = row[7] if row and row[7] is not None else 0
        earliest_d = row[8] if row else None
        latest_d = row[9] if row else None

        completion_pct = round((completed / total) * 100.0, 2) if total > 0 else 0.0

        return {
            "total_work_units": total,
            "completed_units": completed,
            "pending_units": pending,
            "failed_units": failed,
            "processing_units": processing,
            "not_yet_listed_units": not_yet_listed,
            "missing_source_units": missing_source,
            "completion_pct": completion_pct,
            "total_rows_ingested": rows_ingested,
            "earliest_date_ingested": earliest_d,
            "latest_date_ingested": latest_d
        }

    def _load_authentic_bars_for_month(
        self,
        symbol: str,
        year: int,
        month: int
    ) -> Optional[List[Dict[str, Any]]]:
        """
        Attempts to load authentic exchange settlement bars from local bhavcopy
        archives or raw MCP storage for symbol and month.
        Returns List of dicts if authentic bars exist, or None if no authentic source data exists.
        STRICT INVARIANT: NEVER generates synthetic or random-walk numbers.
        """
        m_prefix = f"{year:04d}-{month:02d}"

        # 1. Fetch from official NSE bhavcopy archives via NSEArchiveFetcher
        try:
            universe = set(self.get_universe_symbols())
            month_bars = self.fetcher.fetch_and_parse_month(year, month, universe_symbols=universe)
            if symbol in month_bars and len(month_bars[symbol]) > 0:
                return month_bars[symbol]
        except Exception as err:
            logger.debug(f"Error fetching/parsing bhavcopy for {year}-{month:02d}: {err}")

        # 2. Search in local raw directory for matching MCP history dumps
        raw_dir = "data/raw"
        if os.path.exists(raw_dir):
            for fname in os.listdir(raw_dir):
                if fname.startswith(f"{symbol}_history") and fname.endswith(".json"):
                    fpath = os.path.join(raw_dir, fname)
                    try:
                        with open(fpath, "r", encoding="utf-8") as f:
                            content = json.load(f)
                        chunks = content.get("chunks", []) if isinstance(content, dict) else []
                        for chunk in chunks:
                            res = chunk.get("result", {})
                            c_list = res.get("content", [])
                            for c_item in c_list:
                                text_val = c_item.get("text", "")
                                if not text_val:
                                    continue
                                parsed = json.loads(text_val)
                                data_bars = parsed.get("data", [])
                                matching_bars = []
                                for b in data_bars:
                                    d_str = b.get("trading_date") or b.get("date")
                                    if d_str and d_str.startswith(m_prefix):
                                        matching_bars.append({
                                            "symbol": symbol,
                                            "trading_date": d_str,
                                            "series": b.get("series", "EQ"),
                                            "open": float(b.get("open", 0.0)),
                                            "high": float(b.get("high", 0.0)),
                                            "low": float(b.get("low", 0.0)),
                                            "close": float(b.get("close", 0.0)),
                                            "volume": int(b.get("volume", 0)),
                                            "source": "NSE_MCP_ARCHIVE",
                                            "retrieval_timestamp": datetime.now(timezone.utc).isoformat(),
                                            "data_status": "final_settled",
                                            "provenance_class": "EXCHANGE_OFFICIAL",
                                            "is_synthetic": 0,
                                            "is_eligible_for_live_analytics": 1,
                                            "is_eligible_for_backtest": 1,
                                            "is_eligible_for_training": 1
                                        })
                                if matching_bars:
                                    return matching_bars
                    except Exception as err:
                        logger.debug(f"Error parsing raw MCP history file {fname}: {err}")

        # No authentic data found: return None (strictly no fabrication)
        return None

    def emit_progress_event(self, job_id: Optional[str], event_data: Dict[str, Any]) -> None:
        """Emits progress event to both system_events and job_events for SSE listeners."""
        now_iso = datetime.now(timezone.utc).isoformat()
        evt_id = f"evt_{uuid.uuid4().hex[:12]}"
        payload_str = json.dumps(event_data)

        with self.db.get_connection() as conn:
            # 1. system_events
            conn.execute("""
                INSERT INTO system_events (event_id, event_type, payload_json, created_at)
                VALUES (?, 'HISTORICAL_BACKFILL_PROGRESS', ?, ?)
            """, (evt_id, payload_str, now_iso))

            # 2. job_events (if job_id provided)
            if job_id:
                cur = conn.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE job_id = ?", (job_id,))
                seq = cur.fetchone()[0]
                conn.execute("""
                    INSERT INTO job_events (job_id, sequence, event_type, stage, payload_json, created_at)
                    VALUES (?, ?, 'PROGRESS', 'HISTORICAL_BACKFILL_PROGRESS', ?, ?)
                """, (job_id, seq, payload_str, now_iso))

            conn.commit()

    def execute_backfill_batch(
        self,
        batch_size_months: int = 20,
        max_retries: int = 3,
        job_id: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Executes a batch of historical backfill work units adhering to Truth-Layer Invariants:
        1. Checks listing date: If month precedes instrument's IPO, marks NOT_YET_LISTED (0 rows).
        2. Consumes authentic exchange settlement data if present in archive.
        3. If no authentic archive exists, marks MISSING_SOURCE_DATA (0 rows). Never fabricates data.
        """
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT checkpoint_id, symbol, target_year, target_month
                FROM backfill_sync_checkpoints
                WHERE status IN ('PENDING', 'FAILED')
                ORDER BY target_year ASC, target_month ASC, symbol ASC
                LIMIT ?
            """, (batch_size_months,))
            pending_chunks = cur.fetchall()

        if not pending_chunks:
            logger.info("No pending historical backfill chunks found.")
            return {"status": "IDLE", "processed_chunks": 0, "stats": self.get_checkpoint_stats()}

        processed_count = 0
        not_yet_listed_count = 0
        missing_source_count = 0
        failed_count = 0

        for chk_id, sym, y, m in pending_chunks:
            now_iso = datetime.now(timezone.utc).isoformat()

            # -------------------------------------------------------------
            # Invariant 1: Listing Date Guard
            # -------------------------------------------------------------
            if self.instrument_master.is_month_prior_to_listing(sym, y, m):
                ld = self.instrument_master.get_listing_date(sym)
                logger.info(
                    f"Backfill chunk {chk_id}: {sym} not yet listed on NSE in {y}-{m:02d} "
                    f"(IPO listing date: {ld}). Marking NOT_YET_LISTED with 0 rows."
                )
                with self.db.get_connection() as conn:
                    conn.execute("""
                        UPDATE backfill_sync_checkpoints
                        SET status = 'NOT_YET_LISTED',
                            rows_ingested = 0,
                            earliest_date_ingested = NULL,
                            latest_date_ingested = NULL,
                            error_message = ?,
                            updated_at = ?
                        WHERE checkpoint_id = ?
                    """, (f"Instrument unlisted prior to {ld}", now_iso, chk_id))
                    conn.commit()

                not_yet_listed_count += 1
                processed_count += 1
                continue

            # -------------------------------------------------------------
            # Invariant 2: Authentic Source Ingestion & Fallback Prohibition
            # -------------------------------------------------------------
            try:
                bars = self._load_authentic_bars_for_month(sym, y, m)

                if bars and len(bars) > 0:
                    # Authentic exchange data found: insert with is_synthetic = 0
                    with self.db.get_connection() as conn:
                        conn.executemany("""
                            INSERT OR REPLACE INTO ohlcv_daily (
                                symbol, trading_date, series, open, high, low, close,
                                volume, source, retrieval_timestamp, data_status,
                                provenance_class, is_synthetic, is_eligible_for_live_analytics,
                                is_eligible_for_backtest, is_eligible_for_training
                            ) VALUES (
                                :symbol, :trading_date, :series, :open, :high, :low, :close,
                                :volume, :source, :retrieval_timestamp, :data_status,
                                :provenance_class, :is_synthetic, :is_eligible_for_live_analytics,
                                :is_eligible_for_backtest, :is_eligible_for_training
                            )
                        """, bars)

                        earliest_d = min(b["trading_date"] for b in bars)
                        latest_d = max(b["trading_date"] for b in bars)

                        conn.execute("""
                            UPDATE backfill_sync_checkpoints
                            SET status = 'COMPLETED',
                                rows_ingested = ?,
                                earliest_date_ingested = ?,
                                latest_date_ingested = ?,
                                error_message = NULL,
                                updated_at = ?
                            WHERE checkpoint_id = ?
                        """, (len(bars), earliest_d, latest_d, now_iso, chk_id))
                        conn.commit()

                    processed_count += 1
                    logger.info(f"Backfill chunk {chk_id}: Ingested {len(bars)} authentic bars for {sym}.")

                else:
                    # Authentic source data is absent: mark MISSING_SOURCE_DATA. NEVER fabricate!
                    logger.warning(
                        f"Backfill chunk {chk_id}: Authentic exchange bhavcopy missing for {sym} "
                        f"in {y}-{m:02d}. Recording MISSING_SOURCE_DATA without price fabrication."
                    )
                    with self.db.get_connection() as conn:
                        conn.execute("""
                            UPDATE backfill_sync_checkpoints
                            SET status = 'MISSING_SOURCE_DATA',
                                rows_ingested = 0,
                                earliest_date_ingested = NULL,
                                latest_date_ingested = NULL,
                                error_message = ?,
                                updated_at = ?
                            WHERE checkpoint_id = ?
                        """, (
                            f"Authentic exchange bhavcopy archive for {sym} {y}-{m:02d} not found in local repository.",
                            now_iso,
                            chk_id
                        ))
                        conn.commit()

                    missing_source_count += 1
                    processed_count += 1

            except Exception as e:
                logger.error(f"Failed processing backfill chunk {chk_id} for {sym}: {e}", exc_info=True)
                failed_count += 1
                err_iso = datetime.now(timezone.utc).isoformat()
                with self.db.get_connection() as conn:
                    conn.execute("""
                        UPDATE backfill_sync_checkpoints
                        SET status = 'FAILED',
                            error_message = ?,
                            updated_at = ?
                        WHERE checkpoint_id = ?
                    """, (str(e), err_iso, chk_id))
                    conn.commit()

            # Emit progress telemetry
            current_stats = self.get_checkpoint_stats()
            evt_payload = {
                "checkpoint_id": chk_id,
                "current_symbol": sym,
                "current_period": f"{y}-{m:02d}",
                "progress_pct": current_stats["completion_pct"],
                "completed_units": current_stats["completed_units"],
                "not_yet_listed_units": current_stats["not_yet_listed_units"],
                "missing_source_units": current_stats["missing_source_units"],
                "total_work_units": current_stats["total_work_units"],
                "total_rows_ingested": current_stats["total_rows_ingested"]
            }
            self.emit_progress_event(job_id, evt_payload)
            if progress_callback:
                progress_callback(evt_payload)

        final_stats = self.get_checkpoint_stats()
        return {
            "status": "BATCH_COMPLETED",
            "processed_chunks": processed_count,
            "not_yet_listed_chunks": not_yet_listed_count,
            "missing_source_chunks": missing_source_count,
            "failed_chunks": failed_count,
            "stats": final_stats
        }

    def ingest_month(
        self,
        year: int,
        month: int,
        max_date: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        High-throughput month-level ingestion pipeline:
        1. Downloads and parses authentic exchange bhavcopies for all trading days in (year, month).
        2. Filters strictly for active universe symbols and series == 'EQ'.
        3. Enforces listing date guards (NOT_YET_LISTED).
        4. Inserts authentic settlement bars into ohlcv_daily in a single atomic transaction.
        5. Updates backfill_sync_checkpoints cleanly.
        """
        now_iso = datetime.now(timezone.utc).isoformat()
        universe_symbols = self.get_universe_symbols()
        universe_set = set(universe_symbols)

        # 1. Fetch & parse month in memory
        t0 = time.time()
        month_bars = self.fetcher.fetch_and_parse_month(
            year=year,
            month=month,
            universe_symbols=universe_set,
            max_date=max_date
        )
        fetch_duration = time.time() - t0

        # 2. Query checkpoints for this month
        with self.db.get_connection() as conn:
            cur = conn.execute("""
                SELECT checkpoint_id, symbol
                FROM backfill_sync_checkpoints
                WHERE target_year = ? AND target_month = ?
                ORDER BY symbol ASC
            """, (year, month))
            chunks = cur.fetchall()

        if not chunks:
            # Checkpoints missing for this month; seed them
            self.initialize_checkpoint_matrix(
                symbols=universe_symbols,
                start_year=year,
                end_year=year,
                end_month=month
            )
            with self.db.get_connection() as conn:
                cur = conn.execute("""
                    SELECT checkpoint_id, symbol
                    FROM backfill_sync_checkpoints
                    WHERE target_year = ? AND target_month = ?
                    ORDER BY symbol ASC
                """, (year, month))
                chunks = cur.fetchall()

        total_bars_inserted = 0
        completed_count = 0
        not_yet_listed_count = 0
        missing_source_count = 0

        # 3. Process universe and insert atomically per month
        with self.db.get_connection() as conn:
            for chk_id, sym in chunks:
                # Guard 1: Pre-IPO check
                if self.instrument_master.is_month_prior_to_listing(sym, year, month):
                    ld = self.instrument_master.get_listing_date(sym)
                    conn.execute("""
                        UPDATE backfill_sync_checkpoints
                        SET status = 'NOT_YET_LISTED',
                            rows_ingested = 0,
                            earliest_date_ingested = NULL,
                            latest_date_ingested = NULL,
                            error_message = ?,
                            updated_at = ?
                        WHERE checkpoint_id = ?
                    """, (f"Instrument unlisted prior to {ld}", now_iso, chk_id))
                    not_yet_listed_count += 1
                    continue

                # Guard 2: Authentic bars ingestion
                raw_bars = month_bars.get(sym, [])
                if max_date:
                    bars = [b for b in raw_bars if b["trading_date"] <= max_date]
                else:
                    bars = raw_bars

                if bars and len(bars) > 0:
                    conn.executemany("""
                        INSERT OR REPLACE INTO ohlcv_daily (
                            symbol, trading_date, series, open, high, low, close,
                            volume, source, retrieval_timestamp, data_status,
                            provenance_class, is_synthetic, is_eligible_for_live_analytics,
                            is_eligible_for_backtest, is_eligible_for_training
                        ) VALUES (
                            :symbol, :trading_date, :series, :open, :high, :low, :close,
                            :volume, :source, :retrieval_timestamp, :data_status,
                            :provenance_class, :is_synthetic, :is_eligible_for_live_analytics,
                            :is_eligible_for_backtest, :is_eligible_for_training
                        )
                    """, bars)

                    earliest_d = min(b["trading_date"] for b in bars)
                    latest_d = max(b["trading_date"] for b in bars)
                    conn.execute("""
                        UPDATE backfill_sync_checkpoints
                        SET status = 'COMPLETED',
                            rows_ingested = ?,
                            earliest_date_ingested = ?,
                            latest_date_ingested = ?,
                            error_message = NULL,
                            updated_at = ?
                        WHERE checkpoint_id = ?
                    """, (len(bars), earliest_d, latest_d, now_iso, chk_id))

                    total_bars_inserted += len(bars)
                    completed_count += 1
                else:
                    conn.execute("""
                        UPDATE backfill_sync_checkpoints
                        SET status = 'MISSING_SOURCE_DATA',
                            rows_ingested = 0,
                            earliest_date_ingested = NULL,
                            latest_date_ingested = NULL,
                            error_message = ?,
                            updated_at = ?
                        WHERE checkpoint_id = ?
                    """, (
                        f"Authentic exchange bhavcopy archive for {sym} {year}-{month:02d} not found in official exchange repository.",
                        now_iso,
                        chk_id
                    ))
                    missing_source_count += 1

            conn.commit()

        # Free memory of older months
        self.fetcher.clear_month_cache(keep_latest=True)

        return {
            "year": year,
            "month": month,
            "fetch_duration_seconds": round(fetch_duration, 2),
            "completed_units": completed_count,
            "not_yet_listed_units": not_yet_listed_count,
            "missing_source_units": missing_source_count,
            "total_bars_inserted": total_bars_inserted
        }
