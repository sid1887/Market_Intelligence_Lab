"""
Unit tests for src/core/log_engine.py
Verifies ring buffer, SQLite persistence, HealthCheckFilter, and RSS metrics.
"""

import os
import logging
import tempfile
import pytest
from src.core.log_engine import (
    HealthCheckFilter,
    RingBufferLogHandler,
    UnifiedLogEngine,
    get_current_rss_mb,
    request_id_ctx
)


def test_health_check_filter():
    f = HealthCheckFilter()
    
    # 200 OK on /health should be filtered out
    rec1 = logging.LogRecord("uvicorn.access", logging.INFO, "access.py", 10, '127.0.0.1 - "GET /health HTTP/1.1" 200 OK', (), None)
    assert f.filter(rec1) is False

    # 200 OK on /api/v1/health should be filtered out
    rec2 = logging.LogRecord("uvicorn.access", logging.INFO, "access.py", 10, '127.0.0.1 - "GET /api/v1/health HTTP/1.1" 200 OK', (), None)
    assert f.filter(rec2) is False

    # 500 error on /health should NOT be filtered out
    rec3 = logging.LogRecord("uvicorn.access", logging.ERROR, "access.py", 10, '127.0.0.1 - "GET /health HTTP/1.1" 500 Internal Error', (), None)
    assert f.filter(rec3) is True

    # Screener request should NOT be filtered out
    rec4 = logging.LogRecord("uvicorn.access", logging.INFO, "access.py", 10, '127.0.0.1 - "GET /api/v1/screener HTTP/1.1" 200 OK', (), None)
    assert f.filter(rec4) is True


def test_rss_metric():
    rss = get_current_rss_mb()
    assert isinstance(rss, float)
    assert rss >= 0.0


def test_unified_log_engine():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        engine = UnifiedLogEngine(db_path=db_path, max_buffer_size=10)
        engine.initialize_db(db_path)

        test_logger = logging.getLogger("test_mil_engine")
        test_logger.setLevel(logging.DEBUG)
        test_logger.addHandler(engine.ring_handler)

        # Emit some logs
        test_logger.info("Informational message 1")
        test_logger.warning("Warning message 2")
        test_logger.error("Error message 3")

        logs = engine.get_logs(limit=10, min_level="INFO")
        assert len(logs) == 3
        assert logs[0]["message"] == "Error message 3"  # reverse chronological

        # Test level filtering
        warn_logs = engine.get_logs(limit=10, min_level="WARNING")
        assert len(warn_logs) == 2

        # Test search
        found = engine.get_logs(search="Warning")
        assert len(found) == 1
        assert found[0]["message"] == "Warning message 2"

        # Test client event logging
        engine.log_client_event("ERROR", "Frontend render exception", meta={"url": "/stocks/RELIANCE"})
        cli_logs = engine.get_logs(source="client")
        assert len(cli_logs) == 1
        assert cli_logs[0]["message"] == "Frontend render exception"
        assert cli_logs[0]["source"] == "client"

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
