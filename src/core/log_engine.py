"""
Market Intelligence Lab — Unified Logging & Observability Engine
High-throughput, zero-external-dependency logging subsystem:
1. In-memory ring buffer (500 entries) for sub-millisecond retrieval.
2. Auto-pruned SQLite table (capped at 1,000 entries) for persistent WARNING/ERROR telemetry.
3. HealthCheckFilter to eliminate Render's 5s health check log spam.
4. Process RSS memory and request tracing telemetry.
"""

import os
import json
import queue
import logging
import sqlite3
import datetime
import threading
from collections import deque
from contextvars import ContextVar
from typing import List, Dict, Any, Optional, Tuple

# Context variable for correlation request IDs across async boundaries
request_id_ctx: ContextVar[Optional[str]] = ContextVar("request_id_ctx", default=None)


def get_current_rss_mb() -> float:
    """Returns current process Resident Set Size (RSS) in MB with zero external dependencies."""
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("VmRSS:"):
                    parts = line.split()
                    return round(float(parts[1]) / 1024.0, 2)
    except Exception:
        pass
    try:
        import resource
        return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0, 2)
    except Exception:
        return 0.0


class HealthCheckFilter(logging.Filter):
    """Suppresses repetitive 200 OK access logs from Render / uptime monitors on /health and /api/v1/health."""
    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        if ("GET /health" in msg or "GET /api/v1/health" in msg) and " 200 " in msg:
            return False
        return True


_LOG_SQLITE_QUEUE: "queue.SimpleQueue[Tuple[str, Tuple[Any, ...]]]" = queue.SimpleQueue()
_LOG_WORKER_STARTED = False
_LOG_WORKER_LOCK = threading.Lock()


def _sqlite_log_worker() -> None:
    while True:
        item = _LOG_SQLITE_QUEUE.get()
        db_path, row_tuple = item
        try:
            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(db_path, timeout=5.0)
                with conn:
                    conn.execute(
                        """
                        INSERT INTO system_telemetry_logs (timestamp, level, source, logger_name, message, request_id, meta_json)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                        row_tuple,
                    )
                conn.close()
        except Exception:
            pass


def _enqueue_sqlite_log(db_path: Optional[str], row_tuple: Tuple[Any, ...]) -> None:
    global _LOG_WORKER_STARTED
    if not db_path or not os.path.exists(db_path):
        return
    if not _LOG_WORKER_STARTED:
        with _LOG_WORKER_LOCK:
            if not _LOG_WORKER_STARTED:
                t = threading.Thread(target=_sqlite_log_worker, name="mil-log-sqlite-writer", daemon=True)
                t.start()
                _LOG_WORKER_STARTED = True
    _LOG_SQLITE_QUEUE.put((db_path, row_tuple))


class RingBufferLogHandler(logging.Handler):
    """
    In-memory FIFO buffer for live telemetry inspection with optional non-blocking
    SQLite write for warnings and errors.
    """
    def __init__(self, buffer: deque, db_path: Optional[str] = None):
        super().__init__()
        self.buffer = buffer
        self.db_path = db_path

    def emit(self, record: logging.LogRecord) -> None:
        try:
            req_id = getattr(record, "request_id", None) or request_id_ctx.get()
            ts = datetime.datetime.fromtimestamp(record.created, datetime.timezone.utc).isoformat()
            
            entry = {
                "id": f"{int(record.created * 1000)}-{record.levelno}",
                "timestamp": ts,
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "funcName": record.funcName,
                "lineNo": record.lineno,
                "source": "server",
                "request_id": req_id
            }
            self.buffer.append(entry)

            # Persist WARNING, ERROR, CRITICAL to SQLite capped table asynchronously
            if record.levelno >= logging.WARNING and self.db_path and os.path.exists(self.db_path):
                self._persist_to_sqlite(entry)
        except Exception:
            self.handleError(record)

    def _persist_to_sqlite(self, entry: Dict[str, Any]) -> None:
        _enqueue_sqlite_log(
            self.db_path,
            (
                entry["timestamp"],
                entry["level"],
                entry["source"],
                entry["logger"],
                entry["message"],
                entry["request_id"],
                json.dumps({
                    "module": entry["module"],
                    "funcName": entry["funcName"],
                    "lineNo": entry["lineNo"]
                }),
            ),
        )


class UnifiedLogEngine:
    _instance: Optional["UnifiedLogEngine"] = None

    def __init__(self, db_path: Optional[str] = None, max_buffer_size: int = 500):
        self.db_path = db_path
        self.buffer: deque = deque(maxlen=max_buffer_size)
        self.ring_handler = RingBufferLogHandler(self.buffer, db_path)
        self.health_filter = HealthCheckFilter()
        self._is_configured = False

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> "UnifiedLogEngine":
        if cls._instance is None:
            cls._instance = UnifiedLogEngine(db_path=db_path)
        elif db_path and not cls._instance.db_path:
            cls._instance.db_path = db_path
            cls._instance.ring_handler.db_path = db_path
        return cls._instance

    def initialize_db(self, db_path: str) -> None:
        self.db_path = db_path
        self.ring_handler.db_path = db_path
        try:
            conn = sqlite3.connect(db_path, timeout=10.0)
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS system_telemetry_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        level TEXT NOT NULL,
                        source TEXT NOT NULL,
                        logger_name TEXT,
                        message TEXT NOT NULL,
                        request_id TEXT,
                        meta_json TEXT
                    );
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_logs_ts ON system_telemetry_logs(timestamp DESC);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_telemetry_logs_level ON system_telemetry_logs(level);")
                conn.execute("""
                    CREATE TRIGGER IF NOT EXISTS prune_system_telemetry_logs
                    AFTER INSERT ON system_telemetry_logs
                    WHEN (SELECT COUNT(*) FROM system_telemetry_logs) > 1000
                    BEGIN
                        DELETE FROM system_telemetry_logs WHERE id IN (
                            SELECT id FROM system_telemetry_logs ORDER BY id ASC LIMIT 100
                        );
                    END;
                """)
            conn.close()
        except Exception as e:
            logging.getLogger("mil.log_engine").warning(f"Could not initialize system_telemetry_logs table: {e}")

    def setup_logging(self) -> None:
        if self._is_configured:
            return
        
        # Attach ring buffer to root logger
        root = logging.getLogger()
        self.ring_handler.setLevel(logging.INFO)
        root.addHandler(self.ring_handler)

        # Silence repetitive 200 OK health check logs on uvicorn.access
        uvicorn_access = logging.getLogger("uvicorn.access")
        uvicorn_access.addFilter(self.health_filter)

        self._is_configured = True

    def get_logs(
        self,
        limit: int = 150,
        min_level: str = "INFO",
        source: Optional[str] = None,
        search: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        level_order = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}
        min_level_no = level_order.get(min_level.upper(), 20)

        logs = list(self.buffer)
        filtered = []

        for log in reversed(logs):
            lvl_no = level_order.get(log["level"], 20)
            if lvl_no < min_level_no:
                continue
            if source and source.lower() != "all" and log.get("source", "").lower() != source.lower():
                continue
            if search:
                s_lower = search.lower()
                msg = log.get("message", "").lower()
                logger_name = log.get("logger", "").lower()
                req = (log.get("request_id") or "").lower()
                if s_lower not in msg and s_lower not in logger_name and s_lower not in req:
                    continue
            filtered.append(log)
            if len(filtered) >= limit:
                break

        return filtered

    def log_client_event(
        self,
        level: str,
        message: str,
        client_ip: Optional[str] = None,
        meta: Optional[Dict[str, Any]] = None
    ) -> None:
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        lvl = level.upper() if level else "INFO"
        
        entry = {
            "id": f"cli-{int(datetime.datetime.now().timestamp() * 1000)}",
            "timestamp": now_iso,
            "level": lvl,
            "logger": "client.frontend",
            "message": message,
            "module": "client",
            "funcName": "browser",
            "lineNo": 0,
            "source": "client",
            "request_id": meta.get("request_id") if meta else None
        }
        self.buffer.append(entry)

        if lvl in ("WARNING", "ERROR", "CRITICAL") and self.db_path and os.path.exists(self.db_path):
            _enqueue_sqlite_log(
                self.db_path,
                (
                    now_iso,
                    lvl,
                    "client",
                    "client.frontend",
                    message,
                    entry["request_id"],
                    json.dumps(meta or {}),
                ),
            )


log_engine = UnifiedLogEngine.get_instance()
