"""
tests/test_durable_jobs_and_streaming.py
Hermetic verification of durable job lifecycle, worker lease expiration, and SSE event streaming.
"""

import os
import time
import json
import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from src.storage.database import DatabaseManager
from src.workers.runner import DurableJobWorker
from src.api.routes_jobs import enqueue_job, get_job_status, JobSubmissionRequest, set_default_db
from src.api.routes_stream import set_default_db as set_stream_default_db


@pytest.fixture
def isolated_db(tmp_path):
    db_file = tmp_path / "test_jobs.db"
    db = DatabaseManager(db_path=str(db_file))
    # Apply schema & migrations
    with db.get_connection() as conn:
        from src.storage.migrations import run_all_migrations
        run_all_migrations(conn)

    # Inject into API router singletons
    set_default_db(db)
    set_stream_default_db(db)
    os.environ["MIL_DATABASE_PATH"] = str(db_file)

    yield db

    set_default_db(None)
    set_stream_default_db(None)
    os.environ.pop("MIL_DATABASE_PATH", None)


def test_idempotent_job_submission(isolated_db):
    req = JobSubmissionRequest(
        job_type="UNIVERSE_EOD",
        payload={"target_date": "2026-11-09"},
        priority=50
    )

    # First submission
    res1 = enqueue_job(req)
    assert res1.status == "QUEUED"

    # Duplicate submission
    res2 = enqueue_job(req)
    assert res2.status == "QUEUED"
    assert res1.job_id == res2.job_id, "Idempotent submission must return existing job ID"
    assert res1.idempotency_key == res2.idempotency_key


def test_worker_lease_claiming_and_execution(isolated_db):
    # Enqueue a test factor job
    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="test-worker-1", lease_ttl=5)

    # Claim job
    claimed = worker._claim_next_job()
    assert claimed is not None
    assert claimed["job_id"] == job_info.job_id
    assert claimed["status"] == "RUNNING"
    assert claimed["lease_owner"] == "test-worker-1"


def test_zombie_lease_reaping_and_retry(isolated_db):
    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="dead-worker", lease_ttl=1)
    claimed = worker._claim_next_job()
    assert claimed is not None

    # Artificially expire lease in the past
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with isolated_db.get_connection() as conn:
        conn.execute("UPDATE job_runs SET lease_expires_at = ? WHERE job_id = ?", (past_iso, job_info.job_id))
        conn.commit()

    # Active worker reaps expired leases
    active_worker = DurableJobWorker(isolated_db, worker_id="active-worker", lease_ttl=10)
    active_worker._reap_expired_leases()

    with isolated_db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, attempt_count, error_code FROM job_runs WHERE job_id = ?", (job_info.job_id,))
        status, attempts, err = cur.fetchone()
        assert status == "QUEUED", "Zombie job under retry limit must return to QUEUED"
        assert attempts == 1
        assert err == "LEASE_TIMEOUT_RETRY"


def test_zombie_lease_exhaustion_marks_failed(isolated_db):
    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="dead-worker-2", lease_ttl=1)
    claimed = worker._claim_next_job()
    assert claimed is not None

    # Artificially set attempt_count = 3 (max_retries) and expire lease in the past
    past_iso = (datetime.now(timezone.utc) - timedelta(seconds=10)).isoformat()
    with isolated_db.get_connection() as conn:
        conn.execute(
            "UPDATE job_runs SET attempt_count = 3, lease_expires_at = ? WHERE job_id = ?",
            (past_iso, job_info.job_id)
        )
        conn.commit()

    active_worker = DurableJobWorker(isolated_db, worker_id="active-worker-2", lease_ttl=10)
    active_worker._reap_expired_leases()

    with isolated_db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT status, attempt_count, error_code FROM job_runs WHERE job_id = ?", (job_info.job_id,))
        status, attempts, err = cur.fetchone()
        assert status == "FAILED", "Zombie job exceeding retry limit must transition to FAILED"
        assert err == "LEASE_TIMEOUT_EXHAUSTED"


def test_event_ledger_monotonic_sequence(isolated_db):
    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="test-worker")
    worker.emit_progress(job_info.job_id, "STAGE_1", 10, 100)
    worker.emit_progress(job_info.job_id, "STAGE_2", 20, 100)

    with isolated_db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT sequence, stage FROM job_events WHERE job_id = ? ORDER BY sequence ASC", (job_info.job_id,))
        events = cur.fetchall()

        # Seq 1: Initial state change (QUEUED)
        # Seq 2: STAGE_1
        # Seq 3: STAGE_2
        assert len(events) == 3
        assert [e[0] for e in events] == [1, 2, 3]
        assert events[1][1] == "STAGE_1"
        assert events[2][1] == "STAGE_2"


def test_heartbeat_extends_lease(isolated_db):
    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="test-worker", lease_ttl=10)
    claimed = worker._claim_next_job()
    assert claimed is not None

    orig_expiry = claimed["lease_expires_at"]
    time.sleep(0.05)

    worker.heartbeat(job_info.job_id)

    with isolated_db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT lease_expires_at FROM job_runs WHERE job_id = ?", (job_info.job_id,))
        new_expiry = cur.fetchone()[0]
        assert new_expiry > orig_expiry


@pytest.mark.asyncio
async def test_sse_event_streaming_framing(isolated_db):
    """Verifies that SSE stream emits standard W3C 'id:', 'event:', 'data:' frames and supports last-event-id."""
    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="stream-worker")
    worker.emit_progress(job_info.job_id, "FETCHING", 5, 10, {"detail": "fetch_in_progress"})
    worker.emit_progress(job_info.job_id, "COMPUTING", 10, 10, {"detail": "computing_complete"})

    from starlette.requests import Request
    from src.api.routes_stream import stream_platform_events

    # Mock Request
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/events/stream",
        "headers": [(b"last-event-id", b"1")]  # Replay starting after event 1
    }

    async def mock_receive():
        return {"type": "http.request"}

    mock_request = Request(scope, receive=mock_receive)

    # Call the endpoint generator
    response = await stream_platform_events(mock_request, job_id=job_info.job_id, last_event_id=1)
    gen = response.body_iterator

    # Read first event (should be event 2, stage FETCHING)
    frame1 = await gen.__anext__()
    assert "id: 2" in frame1
    assert "event: PROGRESS" in frame1
    assert "data: " in frame1
    assert "FETCHING" in frame1

    # Read second event (should be event 3, stage COMPUTING)
    frame2 = await gen.__anext__()
    assert "id: 3" in frame2
    assert "event: PROGRESS" in frame2
    assert "COMPUTING" in frame2


def test_worker_cli_once_execution(isolated_db):
    import sys
    import subprocess

    req = JobSubmissionRequest(job_type="FACTOR_RECOMPUTE", payload={"trading_date": "2026-11-06"})
    job_info = enqueue_job(req)

    # Run scripts/run_worker.py --once
    res = subprocess.run(
        [
            sys.executable,
            "scripts/run_worker.py",
            "--db-path",
            isolated_db.db_path,
            "--once",
            "--worker-id",
            "cli-test-worker"
        ],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0
    output = res.stdout + res.stderr
    assert "Single-execution mode enabled" in output
    assert f"Job {job_info.job_id} execution finished." in output

    # Check job status in isolated DB
    with isolated_db.get_connection() as conn:
        row = conn.execute(
            "SELECT status, lease_owner, progress_pct FROM job_runs WHERE job_id = ?",
            (job_info.job_id,)
        ).fetchone()
        assert row[0] == "SUCCEEDED"
        assert row[1] is None  # Lease cleared on completion
        assert row[2] == 100


def test_intermediate_checkpoint_persistence_and_resumption(isolated_db, monkeypatch):
    from src.workers.dispatcher import TaskDispatcher
    from src.pipeline.universe_ingestion import UniverseIngestionManager
    from src.quant.factor_pipeline import FactorPipeline

    fake_symbols = [f"SYM_{i:03d}" for i in range(25)]
    processed_symbols = []

    def mock_get_universe(self):
        return fake_symbols

    def mock_fetch_symbol(self, sym, target_date=None):
        processed_symbols.append(sym)
        return [{"symbol": sym, "close": 100.0}]

    def mock_compute_factors(self, target_date=None):
        return len(fake_symbols)

    monkeypatch.setattr(UniverseIngestionManager, "get_active_universe", mock_get_universe)
    monkeypatch.setattr(UniverseIngestionManager, "fetch_and_persist_symbol", mock_fetch_symbol)
    monkeypatch.setattr(FactorPipeline, "compute_universe_factors", mock_compute_factors)

    # 1. Enqueue UNIVERSE_EOD job
    req = JobSubmissionRequest(job_type="UNIVERSE_EOD", payload={"target_date": "2026-11-06"})
    job_info = enqueue_job(req)

    worker = DurableJobWorker(isolated_db, worker_id="chk-worker", lease_ttl=30)
    dispatcher = TaskDispatcher(isolated_db, worker)

    # 2. Simulate failure after 12 symbols
    fail_after = 12
    call_count = 0

    def mock_fetch_with_crash(self, sym, target_date=None):
        nonlocal call_count
        call_count += 1
        if call_count > fail_after:
            raise RuntimeError("Simulated worker crash after symbol 12")
        processed_symbols.append(sym)
        return [{"symbol": sym, "close": 100.0}]

    monkeypatch.setattr(UniverseIngestionManager, "fetch_and_persist_symbol", mock_fetch_with_crash)

    # Run dispatcher - should fail at symbol 13
    with pytest.raises(RuntimeError, match="Simulated worker crash"):
        dispatcher._run_universe_eod(job_info.job_id, {"target_date": "2026-11-06"})

    # Verify checkpoint exists at symbol 10 (idx 9)
    with isolated_db.get_connection() as conn:
        chk_row = conn.execute(
            "SELECT cursor_json, stage FROM job_checkpoints WHERE job_id = ? AND checkpoint_key = 'RESUME_INDEX'",
            (job_info.job_id,)
        ).fetchone()
        assert chk_row is not None
        chk_data = json.loads(chk_row[0])
        assert chk_data["last_index"] == 9
        assert chk_data["last_symbol"] == "SYM_009"
        assert chk_data["processed_count"] == 10

    # 3. Resume execution with working mock
    processed_symbols.clear()
    monkeypatch.setattr(UniverseIngestionManager, "fetch_and_persist_symbol", mock_fetch_symbol)

    result = dispatcher._run_universe_eod(job_info.job_id, {"target_date": "2026-11-06"})
    assert result["symbols_processed"] == 25
    # Since it resumed from index 10 (SYM_010), processed_symbols should only have SYM_010 through SYM_024 (15 symbols)
    assert len(processed_symbols) == 15
    assert processed_symbols[0] == "SYM_010"
    assert processed_symbols[-1] == "SYM_024"

    # Verify final checkpoint
    with isolated_db.get_connection() as conn:
        final_chk = conn.execute(
            "SELECT cursor_json, stage FROM job_checkpoints WHERE job_id = ? AND checkpoint_key = 'SUMMARY'",
            (job_info.job_id,)
        ).fetchone()
        assert final_chk is not None
        final_data = json.loads(final_chk[0])
        assert final_data["status"] == "COMPLETED"
        assert final_data["symbols_processed"] == 25


