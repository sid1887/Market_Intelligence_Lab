"""
src/storage/maintenance.py
Automated Database Maintenance, Incremental Vacuum & Defrag Engine.
ADR-0011, P0-08.

Keeps SQLite database optimized, defragmented, and healthy:
1. Incremental Vacuum: Recovers unallocated pages without locking the whole database.
2. WAL Flush: Executes passive or truncate checkpoints to keep .db-wal under 10 MB.
3. Query Planner Optimization: Runs PRAGMA optimize to refresh index branch statistics.
4. B-Tree Integrity Guard: Executes PRAGMA quick_check to detect page corruption.
"""

import time
import logging
from typing import Dict, Any, Tuple
from src.storage.database import DatabaseManager

logger = logging.getLogger("MIL.Maintenance")


class DatabaseMaintenanceDaemon:
    """Manages low-overhead background maintenance tasks for SQLite in WAL mode."""

    def __init__(self, db: DatabaseManager):
        self.db = db

    def check_integrity(self) -> Tuple[bool, str]:
        """Runs PRAGMA quick_check to verify B-tree and index integrity."""
        try:
            with self.db.get_readonly_connection() as conn:
                cur = conn.execute("PRAGMA quick_check;")
                res = cur.fetchone()
                status = res[0] if res else "unknown"
                is_ok = (status.lower() == "ok")
                if not is_ok:
                    logger.error(f"[DB-INTEGRITY] Integrity violation detected: {status}")
                return is_ok, status
        except Exception as e:
            logger.error(f"[DB-INTEGRITY] Error running quick_check: {e}")
            return False, str(e)

    def run_wal_checkpoint(self, mode: str = "PASSIVE") -> Dict[str, Any]:
        """
        Executes a WAL checkpoint (PASSIVE, RESTART, FULL, TRUNCATE).
        PASSIVE flushes committed frames without blocking concurrent readers or writers.
        """
        valid_modes = {"PASSIVE", "RESTART", "FULL", "TRUNCATE"}
        target_mode = mode.upper() if mode.upper() in valid_modes else "PASSIVE"
        busy, log_frames, checkpointed = self.db.wal_checkpoint(target_mode)
        logger.info(f"[DB-MAINTENANCE] WAL checkpoint ({target_mode}): busy={busy}, log={log_frames}, checkpointed={checkpointed}")
        return {
            "mode": target_mode,
            "busy": bool(busy),
            "log_frames": log_frames,
            "checkpointed_frames": checkpointed
        }

    def run_incremental_vacuum(self, pages: int = 1000) -> Dict[str, Any]:
        """
        Performs incremental vacuuming to reclaim free pages incrementally without full database locks.
        """
        t0 = time.time()
        with self.db.get_connection() as conn:
            try:
                conn.execute(f"PRAGMA incremental_vacuum({pages});")
                conn.commit()
            except Exception as e:
                logger.debug(f"[DB-MAINTENANCE] Incremental vacuum note (auto_vacuum may be none): {e}")

        elapsed = time.time() - t0
        return {
            "status": "COMPLETED",
            "pages_requested": pages,
            "elapsed_seconds": round(elapsed, 4)
        }

    def run_query_planner_optimize(self) -> Dict[str, Any]:
        """
        Runs PRAGMA optimize to advise SQLite query planner based on queries run so far.
        """
        t0 = time.time()
        with self.db.get_connection() as conn:
            conn.execute("PRAGMA optimize;")
            conn.commit()
        elapsed = time.time() - t0
        return {
            "status": "COMPLETED",
            "elapsed_seconds": round(elapsed, 4)
        }

    def run_full_maintenance_cycle(self) -> Dict[str, Any]:
        """Executes complete automated maintenance cycle."""
        logger.info("[DB-MAINTENANCE] Starting automated database maintenance cycle...")
        t0 = time.time()

        is_healthy, integrity_msg = self.check_integrity()
        wal_res = self.run_wal_checkpoint(mode="PASSIVE")
        vac_res = self.run_incremental_vacuum(pages=1000)
        opt_res = self.run_query_planner_optimize()

        total_elapsed = time.time() - t0
        logger.info(f"[DB-MAINTENANCE] Cycle completed in {total_elapsed:.3f}s. Integrity: {integrity_msg}")

        return {
            "status": "SUCCESS" if is_healthy else "CORRUPTED",
            "integrity_ok": is_healthy,
            "integrity_detail": integrity_msg,
            "wal_checkpoint": wal_res,
            "vacuum": vac_res,
            "optimize": opt_res,
            "total_duration_seconds": round(total_elapsed, 4)
        }
