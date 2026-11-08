"""
src/workers/runner.py
Durable background job runner implementing distributed lease claiming and heartbeat management.
"""

import os
import sys
import time
import json
import uuid
import signal
import logging
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from src.storage.database import DatabaseManager
from src.workers.dispatcher import TaskDispatcher

logger = logging.getLogger("MIL.Worker")


class DurableJobWorker:
    def __init__(
        self,
        db: DatabaseManager,
        worker_id: Optional[str] = None,
        poll_interval: float = 1.0,
        lease_ttl: int = 30
    ):
        self.db = db
        self.worker_id = worker_id or f"worker-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_interval = poll_interval
        self.lease_ttl = lease_ttl
        self.running = False
        self.dispatcher = TaskDispatcher(db, self)

    def start(self):
        self.running = True
        logger.info(f"Initialized DurableJobWorker [{self.worker_id}] with lease TTL={self.lease_ttl}s")
        try:
            signal.signal(signal.SIGINT, self._handle_shutdown)
            signal.signal(signal.SIGTERM, self._handle_shutdown)
        except (ValueError, AttributeError):
            # In non-main thread execution or testing environments
            pass

        while self.running:
            try:
                self._reap_expired_leases()
                claimed_job = self._claim_next_job()

                if claimed_job:
                    self._execute_job(claimed_job)
                else:
                    time.sleep(self.poll_interval)
            except Exception as e:
                logger.error(f"Unexpected worker loop exception: {e}\n{traceback.format_exc()}")
                time.sleep(self.poll_interval)

    def stop(self):
        """Stops the worker loop gracefully."""
        self.running = False

    def _handle_shutdown(self, signum, frame):
        logger.warning(f"Received termination signal ({signum}). Completing active step and shutting down...")
        self.running = False

    def _reap_expired_leases(self):
        """Transitions zombie jobs with expired leases to FAILED or queues for retry."""
        now_iso = datetime.now(timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT job_id, attempt_count, max_retries 
                FROM job_runs 
                WHERE status = 'RUNNING' AND lease_expires_at < ?
            """, (now_iso,))
            zombies = cur.fetchall()

            for job_id, attempts, max_retries in zombies:
                if attempts < max_retries:
                    logger.warning(f"Reaped zombie job {job_id} (lease expired). Rescheduling for attempt {attempts + 1}")
                    cur.execute("""
                        UPDATE job_runs 
                        SET status = 'QUEUED', 
                            lease_owner = NULL, 
                            lease_expires_at = NULL,
                            error_code = 'LEASE_TIMEOUT_RETRY'
                        WHERE job_id = ?
                    """, (job_id,))
                else:
                    logger.critical(f"Reaped zombie job {job_id} exceeded maximum retries ({max_retries}). Marking FAILED.")
                    cur.execute("""
                        UPDATE job_runs 
                        SET status = 'FAILED', 
                            lease_owner = NULL, 
                            lease_expires_at = NULL,
                            error_code = 'LEASE_TIMEOUT_EXHAUSTED',
                            completed_at = ?
                        WHERE job_id = ?
                    """, (now_iso, job_id))
            conn.commit()

    def _claim_next_job(self) -> Optional[Dict[str, Any]]:
        """Atomically locks the highest priority QUEUED job using SQLite conditional update."""
        now = datetime.now(timezone.utc)
        now_iso = now.isoformat()
        lease_expiry = (now + timedelta(seconds=self.lease_ttl)).isoformat()

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            # Select candidate
            cur.execute("""
                SELECT job_id FROM job_runs
                WHERE status = 'QUEUED'
                ORDER BY priority ASC, created_at ASC
                LIMIT 1
            """)
            row = cur.fetchone()
            if not row:
                return None

            job_id = row[0]

            # Atomic state change
            cur.execute("""
                UPDATE job_runs
                SET status = 'RUNNING',
                    lease_owner = ?,
                    lease_expires_at = ?,
                    last_heartbeat_at = ?,
                    started_at = COALESCE(started_at, ?),
                    attempt_count = attempt_count + 1
                WHERE job_id = ? AND status = 'QUEUED'
            """, (self.worker_id, lease_expiry, now_iso, now_iso, job_id))

            if cur.rowcount == 0:
                # Contention: Another worker claimed it first
                return None

            conn.commit()

            cur.execute("SELECT * FROM job_runs WHERE job_id = ?", (job_id,))
            return dict(cur.fetchone())

    def heartbeat(self, job_id: str):
        """Extends worker lease to prevent timeout during long-running sub-tasks."""
        now = datetime.now(timezone.utc)
        lease_expiry = (now + timedelta(seconds=self.lease_ttl)).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
                UPDATE job_runs
                SET lease_expires_at = ?, last_heartbeat_at = ?
                WHERE job_id = ? AND lease_owner = ?
            """, (lease_expiry, now.isoformat(), job_id, self.worker_id))
            conn.commit()

    def emit_progress(
        self,
        job_id: str,
        stage: str,
        records_processed: int,
        records_total: int,
        details: Optional[Dict[str, Any]] = None
    ):
        """Emits an event into the append-only ledger and updates parent job record."""
        now_iso = datetime.now(timezone.utc).isoformat()
        progress_pct = round((records_processed / max(1, records_total)) * 100, 2)
        payload = details or {}
        payload.update({
            "records_processed": records_processed,
            "records_total": records_total,
            "progress_pct": progress_pct
        })

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            # Get next sequence ID for job
            cur.execute("SELECT COALESCE(MAX(sequence), 0) + 1 FROM job_events WHERE job_id = ?", (job_id,))
            next_seq = cur.fetchone()[0]

            cur.execute("""
                INSERT INTO job_events (job_id, sequence, event_type, stage, payload_json, created_at)
                VALUES (?, ?, 'PROGRESS', ?, ?, ?)
            """, (job_id, next_seq, stage, json.dumps(payload), now_iso))

            cur.execute("""
                UPDATE job_runs
                SET records_processed = ?, records_total = ?, progress_pct = ?
                WHERE job_id = ?
            """, (records_processed, records_total, progress_pct, job_id))
            conn.commit()

        # Extend lease on progress
        self.heartbeat(job_id)

    def _execute_job(self, job: Dict[str, Any]):
        job_id = job["job_id"]
        job_type = job["job_type"]
        payload = json.loads(job["payload_json"])
        now_iso = datetime.now(timezone.utc).isoformat()

        logger.info(f"Executing job {job_id} ({job_type}) [Attempt {job['attempt_count']}]")

        try:
            result = self.dispatcher.dispatch(job_id, job_type, payload)

            with self.db.get_connection() as conn:
                conn.execute("""
                    UPDATE job_runs
                    SET status = 'SUCCEEDED',
                        progress_pct = 100.0,
                        result_json = ?,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        completed_at = ?
                    WHERE job_id = ?
                """, (json.dumps(result), datetime.now(timezone.utc).isoformat(), job_id))

                # Emit terminal event
                conn.execute("""
                    INSERT INTO job_events (job_id, sequence, event_type, stage, payload_json, created_at)
                    SELECT ?, COALESCE(MAX(sequence), 0) + 1, 'TERMINAL', 'COMPLETED', ?, ?
                    FROM job_events WHERE job_id = ?
                """, (job_id, json.dumps(result), now_iso, job_id))
                conn.commit()

            logger.info(f"Job {job_id} SUCCEEDED.")
        except Exception as e:
            error_msg = str(e)
            stack_trace = traceback.format_exc()
            logger.error(f"Job {job_id} execution failure: {error_msg}\n{stack_trace}")

            with self.db.get_connection() as conn:
                conn.execute("""
                    UPDATE job_runs
                    SET status = 'FAILED',
                        error_code = 'EXECUTION_EXCEPTION',
                        error_trace = ?,
                        result_json = ?,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        completed_at = ?
                    WHERE job_id = ?
                """, (stack_trace, json.dumps({"error": error_msg}), datetime.now(timezone.utc).isoformat(), job_id))

                conn.execute("""
                    INSERT INTO job_events (job_id, sequence, event_type, stage, payload_json, created_at)
                    SELECT ?, COALESCE(MAX(sequence), 0) + 1, 'TERMINAL', 'FAILED', ?, ?
                    FROM job_events WHERE job_id = ?
                """, (job_id, json.dumps({"error": error_msg}), now_iso, job_id))
                conn.commit()
