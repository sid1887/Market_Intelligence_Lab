"""
src/api/routes_stream.py
W3C-compliant Server-Sent Events (SSE) streaming router with replay support.
Zero-Lock Streaming Hub: connections are closed immediately before async sleep.
"""

import os
import asyncio
import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Request, Query
from fastapi.responses import StreamingResponse

from src.storage.database import DatabaseManager

router = APIRouter(prefix="/api/v1/events", tags=["Streaming"])
logger = logging.getLogger("MIL.Stream")

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


def fetch_events_slice(db: DatabaseManager, cursor: int, job_id: Optional[str]) -> List[Dict[str, Any]]:
    """
    Executes an instantaneous point-in-time read and immediately closes the connection.
    Guarantees no connection is held open across async sleep intervals.
    """
    with db.get_readonly_connection() as conn:
        conn.execute("PRAGMA busy_timeout = 2000;")
        cur = conn.cursor()
        if job_id:
            cur.execute("""
                SELECT event_id, job_id, sequence, event_type, stage, payload_json, created_at
                FROM job_events
                WHERE event_id > ? AND job_id = ?
                ORDER BY event_id ASC
                LIMIT 50
            """, (cursor, job_id))
        else:
            cur.execute("""
                SELECT event_id, job_id, sequence, event_type, stage, payload_json, created_at
                FROM job_events
                WHERE event_id > ?
                ORDER BY event_id ASC
                LIMIT 50
            """, (cursor,))

        rows = cur.fetchall()
        parsed = []
        for r in rows:
            raw_payload = r[5]
            if isinstance(raw_payload, str):
                try:
                    payload = json.loads(raw_payload)
                except Exception:
                    payload = {}
            elif isinstance(raw_payload, dict):
                payload = raw_payload
            else:
                payload = {}

            parsed.append({
                "event_id": r[0],
                "job_id": r[1],
                "sequence": r[2],
                "event_type": r[3],
                "stage": r[4],
                "payload": payload,
                "created_at": r[6]
            })
        return parsed


def fetch_macro_telemetry_snapshot(db: DatabaseManager) -> Dict[str, Any]:
    """Fetches latest macro tick and supervisor status instantly from cache and closes connection."""
    try:
        from src.client.macro_client import MacroClient
        from src.supervisor.state_machine import SupervisorStateMachine
        from src.api.utils import sanitize_for_json

        # read_cache_only=True guarantees zero blocking yfinance network calls inside the SSE async loop
        macro = MacroClient.get_macro_telemetry(force_refresh=False, read_cache_only=True)
        supervisor = SupervisorStateMachine(db).get_current_state()

        last_ingestion = None
        try:
            with db.get_readonly_connection() as conn:
                cur = conn.cursor()
                cur.execute("SELECT MAX(retrieval_timestamp) FROM ohlcv_daily WHERE series = 'EQ' AND is_synthetic = 0")
                r = cur.fetchone()
                last_ingestion = r[0] if r and r[0] else None
        except Exception:
            pass

        return sanitize_for_json({
            "macro": macro,
            "supervisor": supervisor.get("status", "NORMAL"),
            "supervisor_full": supervisor,
            "last_ingestion_timestamp": last_ingestion
        })
    except Exception as e:
        logger.error(f"Error fetching telemetry snapshot: {e}")
        return {}


@router.get("/stream")
async def stream_platform_events(
    request: Request,
    job_id: Optional[str] = Query(None, description="Optional job_id filter"),
    last_event_id: Optional[int] = Query(None, alias="Last-Event-ID")
):
    """
    Broadcasts real-time events.
    Supports reconnection replay from last_event_id.
    Guarantees zero database connection retention across async sleep intervals.
    """
    db = get_db()

    if last_event_id is None:
        header_val = request.headers.get("last-event-id")
        if header_val and header_val.isdigit():
            last_event_id = int(header_val)

    async def event_generator():
        current_cursor = last_event_id or 0
        tick_counter = 0

        while True:
            # 1. Connection check before doing any work
            try:
                if await request.is_disconnected():
                    break
            except Exception:
                pass

            # 2. Instantaneous query with scoped connection closure
            events = fetch_events_slice(db, current_cursor, job_id)

            if events:
                for ev in events:
                    current_cursor = ev["event_id"]
                    ev_type = ev["event_type"]
                    yield f"id: {current_cursor}\nevent: {ev_type}\ndata: {json.dumps(ev)}\n\n"

                # Zero open connection during sleep
                await asyncio.sleep(0.05)
            else:
                tick_counter += 1
                # Broadcast TELEMETRY_TICK every 30 seconds (30 * 1.0s sleep iterations)
                if tick_counter >= 30:
                    tick_counter = 0
                    if job_id is None:
                        telemetry = fetch_macro_telemetry_snapshot(db)
                        if telemetry:
                            yield f"event: TELEMETRY_TICK\ndata: {json.dumps(telemetry)}\n\n"

                yield ": keepalive-tick\n\n"
                # Zero open connection during sleep
                await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )
