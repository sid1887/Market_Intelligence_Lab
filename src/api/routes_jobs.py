"""
src/api/routes_jobs.py
Asynchronous job management endpoints returning immediate 202 Accepted responses.
"""

import os
import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field

from src.storage.database import DatabaseManager

router = APIRouter(prefix="/api/v1/jobs", tags=["Job Engine"])

_DEFAULT_DB: Optional[DatabaseManager] = None


def set_default_db(db: Optional[DatabaseManager]):
    global _DEFAULT_DB
    _DEFAULT_DB = db


def get_db() -> DatabaseManager:
    global _DEFAULT_DB
    if _DEFAULT_DB is not None:
        return _DEFAULT_DB
    db_path = os.getenv("MIL_DATABASE_PATH", "data/market_lab.db")
    return DatabaseManager(db_path)


class JobSubmissionRequest(BaseModel):
    job_type: str = Field(..., description="UNIVERSE_EOD, MODEL_TOURNAMENT, or FACTOR_RECOMPUTE")
    payload: Dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=1, le=1000)


class JobSubmissionResponse(BaseModel):
    job_id: str
    job_type: str
    status: str
    idempotency_key: str
    status_url: str
    stream_url: str
    created_at: str


@router.post("", status_code=status.HTTP_202_ACCEPTED, response_model=JobSubmissionResponse)
def enqueue_job(req: JobSubmissionRequest, db: Optional[DatabaseManager] = Depends(get_db)):
    if not isinstance(db, DatabaseManager):
        db = get_db()

    # 1. Deterministic Idempotency Key calculation
    serialized_payload = json.dumps(req.payload, sort_keys=True)
    raw_hash = f"{req.job_type}:{serialized_payload}"
    idempotency_key = hashlib.sha256(raw_hash.encode()).hexdigest()

    now_iso = datetime.now(timezone.utc).isoformat()

    with db.get_connection() as conn:
        cur = conn.cursor()

        # Check if identical job is already queued, running, or previously executed
        cur.execute("""
            SELECT job_id, status, created_at FROM job_runs 
            WHERE idempotency_key = ?
        """, (idempotency_key,))
        existing = cur.fetchone()

        if existing:
            job_id, current_status, created_at = existing[0], existing[1], existing[2]
            return JobSubmissionResponse(
                job_id=job_id,
                job_type=req.job_type,
                status=current_status,
                idempotency_key=idempotency_key,
                status_url=f"/api/v1/jobs/{job_id}",
                stream_url=f"/api/v1/events/stream?job_id={job_id}",
                created_at=created_at
            )

        new_job_id = f"job_{uuid.uuid4().hex[:12]}"
        cur.execute("""
            INSERT INTO job_runs (
                job_id, job_type, idempotency_key, status, priority, 
                payload_json, created_at
            ) VALUES (?, ?, ?, 'QUEUED', ?, ?, ?)
        """, (new_job_id, req.job_type, idempotency_key, req.priority, serialized_payload, now_iso))

        # Emit initial ENQUEUED event
        cur.execute("""
            INSERT INTO job_events (job_id, sequence, event_type, stage, payload_json, created_at)
            VALUES (?, 1, 'STATE_CHANGE', 'QUEUED', ?, ?)
        """, (new_job_id, json.dumps({"message": "Job queued for execution"}), now_iso))

        conn.commit()

    return JobSubmissionResponse(
        job_id=new_job_id,
        job_type=req.job_type,
        status="QUEUED",
        idempotency_key=idempotency_key,
        status_url=f"/api/v1/jobs/{new_job_id}",
        stream_url=f"/api/v1/events/stream?job_id={new_job_id}",
        created_at=now_iso
    )


@router.get("/{job_id}")
def get_job_status(job_id: str, db: Optional[DatabaseManager] = Depends(get_db)):
    if not isinstance(db, DatabaseManager):
        db = get_db()
    with db.get_connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM job_runs WHERE job_id = ?", (job_id,))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Job not found")

        data = dict(row)
        if data.get("payload_json"):
            try:
                data["payload"] = json.loads(data["payload_json"])
            except Exception:
                data["payload"] = {}
        if data.get("result_json"):
            try:
                data["result"] = json.loads(data["result_json"])
            except Exception:
                data["result"] = {}

        return data
