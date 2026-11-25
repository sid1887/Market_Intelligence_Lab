"""
Market Intelligence Lab — FastAPI REST API Bridge (Milestones B6.3, B6.4 & B6.4.1).

Exposes local SQLite quantitative database (`data/market_lab.db`) via high-performance,
concurrency-safe read-only WAL connection endpoints:
- GET /health & GET /api/v1/health: System status & latest market dates
- GET /api/v1/screener: Top ranked stocks based on composite Quality-Momentum score
- GET /api/v1/watchlist: Active user watchlist equities with real-time stats
- GET /stocks/{symbol}/status & GET /api/v1/stocks/{symbol}/status: Ingestion status
- GET /stocks/{symbol}/tearsheet & GET /api/v1/stocks/{symbol}/tearsheet: Complete tearsheet JSON payload
- GET /stocks/{symbol}/history & GET /api/v1/stocks/{symbol}/history: Daily OHLCV candlestick series
"""

import os
import sys
import re
import gc
import json
import sqlite3
import datetime
import logging
import gzip
import time
import uuid
from pathlib import Path
from typing import List, Dict, Any, Optional

from src.core.log_engine import log_engine, request_id_ctx, get_current_rss_mb
from src.storage.durable_state import mark_state_dirty
from src.storage.cache import enforce_rss_memory_guard, get_current_process_rss_mb

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
for _uvicorn_logger in ("uvicorn", "uvicorn.error", "uvicorn.access"):
    logging.getLogger(_uvicorn_logger).setLevel(logging.INFO)

# Silence noisy HTTP client loggers to prevent leaking external webhook tokens in request URLs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks, Response, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from pydantic import BaseModel

from src.copilot.deliberation import MultiAgentDeliberationEngine
from src.copilot.distiller import CopilotKnowledgeDistiller
from src.copilot.llm_client import MODEL_QUOTAS

from src.storage.database import DatabaseManager
from src.storage.hydration import is_cloud_lightweight_mode, hydrate_initial_cloud_database, get_hydration_status
from src.quant.screener import FactorScreener
from src.quant.rebalance_engine import RebalanceEngine
from src.api.utils import (
    DATABASE_PATH,
    get_db_connection,
    get_write_db_connection,
    sanitize_for_json,
    safe_float,
    safe_int
)
from src.api.routes_market import (
    market_router,
    get_stock_status,
    get_stock_tearsheet,
    get_stock_history,
    get_stock_forecast,
    get_stock_news,
    get_stock_bundle,
    run_backtest_endpoint,
    get_latest_backtest,
    get_investment_memo,
    get_system_accuracy,
    run_dynamic_ingestion,
    trigger_system_ingest
)
from src.api.routes_jobs import router as jobs_router
from src.api.routes_stream import router as stream_router
from src.api.routes_portfolio import router as portfolio_router
from src.api.routes_backtest import router as backtest_router
from src.api.routes_push import router as push_router
from src.api.routes_internal import router as internal_router
from src.api.routes_telegram import router as telegram_router
from src.notifications.telegram_bot import register_telegram_webhook

from contextlib import asynccontextmanager
import asyncio
import threading
from src.tasks.daemon import platform_daemon, run_autonomous_platform_daemon

logger = logging.getLogger(__name__)

# Thread-safe In-Memory Screener Materialized Snapshot View (Milestone B6 / P0)
SCREENER_CACHE_MAX_ITEMS: int = 1500
_screener_cache_lock = threading.Lock()
_screener_snapshot_cache: Optional[Dict[str, Any]] = None
_screener_cached_bytes: Optional[bytes] = None
_screener_cached_gzip: Optional[bytes] = None
_screener_cached_1000_bytes: Optional[bytes] = None
_screener_cached_1000_gzip: Optional[bytes] = None
_screener_cache_date: Optional[str] = None
_screener_cache_time: float = 0.0
SCREENER_CACHE_TTL_SECONDS: float = 300.0


def invalidate_screener_cache() -> None:
    """Explicitly invalidates the in-memory screener snapshot cache."""
    global _screener_snapshot_cache, _screener_cached_bytes, _screener_cached_gzip, _screener_cached_1000_bytes, _screener_cached_1000_gzip, _screener_cache_date, _screener_cache_time
    with _screener_cache_lock:
        _screener_snapshot_cache = None
        _screener_cached_bytes = None
        _screener_cached_gzip = None
        _screener_cached_1000_bytes = None
        _screener_cached_1000_gzip = None
        _screener_cache_date = None
        _screener_cache_time = 0.0
    logger.info("In-memory screener cache invalidated.")

def clear_all_api_caches() -> None:
    """Clears all in-memory API response caches (screener, macro, forecasts, LRU app_cache)."""
    invalidate_screener_cache()
    try:
        from src.storage.cache import app_cache
        app_cache.clear()
    except Exception:
        pass
    try:
        from src.client.macro_client import MacroClient
        MacroClient._cached_macro_data = None
        MacroClient._cache_timestamp = 0.0
    except Exception:
        pass
    logger.info("All in-memory API caches cleared.")

def is_nse_trading_hours() -> bool:
    """Returns True if current time is within NSE trading hours (09:15–15:35 IST, Mon–Fri)."""
    ist = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
    now = datetime.datetime.now(ist)
    if now.weekday() > 4:  # Saturday or Sunday
        return False
    market_open = now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=35, second=0, microsecond=0)
    return market_open <= now <= market_close


async def embedded_intraday_catalyst_loop():
    """Background loop executing intraday anomaly scan & push delivery every 10 minutes during NSE hours."""
    from src.tasks.catalyst_engine import catalyst_engine
    logger.info("Embedded Intraday Catalyst & Push Loop initialized.")
    while True:
        try:
            # Check market hours
            if is_nse_trading_hours():
                logger.info("NSE session active: running 10-minute intraday catalyst scan...")
                loop = asyncio.get_running_loop()
                await loop.run_in_executor(None, catalyst_engine.run_intraday_scan)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Error in embedded catalyst loop: {e}", exc_info=True)

        try:
            await asyncio.sleep(600)  # 10 minutes
        except asyncio.CancelledError:
            break


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize Unified Observability Subsystem & Silence Healthcheck Spam
    try:
        log_engine.initialize_db(DATABASE_PATH)
        log_engine.setup_logging()
    except Exception as log_init_err:
        logger.warning(f"Could not initialize unified log engine: {log_init_err}")

    # Startup Environment Invariant Checks
    startup_notices = []
    if not (os.getenv("MIL_INTERNAL_SYNC_SECRET") or os.getenv("INTERNAL_SYNC_TOKEN")):
        startup_notices.append("MIL_INTERNAL_SYNC_SECRET not set: /api/v1/internal/* sync will reject external workers.")
    if not os.getenv("VAPID_PRIVATE_KEY") and not os.path.exists("data/vapid.json"):
        startup_notices.append("VAPID_PRIVATE_KEY not configured: Push notifications will generate an ephemeral session key.")
    if not (os.getenv("GROQ_API_KEY") or os.getenv("GEMINI_API_KEY")):
        startup_notices.append("No live LLM key (GROQ_API_KEY / GEMINI_API_KEY): Copilot will use local deterministic quant synthesis.")

    for notice in startup_notices:
        logger.info(f"[STARTUP-NOTICE] {notice}")

    # 1. Asynchronous non-blocking cloud database hydration & supervisor state recovery
    def _run_background_hydration_and_recovery():
        try:
            hydrate_initial_cloud_database(DATABASE_PATH)
            try:
                from src.supervisor.state_machine import SupervisorStateMachine
                from src.storage.database import DatabaseManager
                sup_mgr = SupervisorStateMachine(DatabaseManager(DATABASE_PATH))
                recovered_state = sup_mgr.evaluate_and_recover()
                logger.info(f"Supervisor post-hydration status: {recovered_state.get('status')} (Active: {recovered_state.get('active_model_id')})")
            except Exception as sup_err:
                logger.warning(f"Supervisor post-hydration recovery notice: {sup_err}")
        except Exception as hyd_err:
            logger.error(f"Cloud database hydration error: {hyd_err}", exc_info=True)

    hydration_thread = threading.Thread(
        target=_run_background_hydration_and_recovery,
        daemon=True,
        name="MIL-CloudHydration"
    )
    hydration_thread.start()

    daemon_task = None
    embedded_task = None

    # Check if running in lightweight cloud container (e.g. Render 512MB RAM)
    is_cloud = is_cloud_lightweight_mode() or (os.getenv("RENDER", "").lower() in ("true", "1"))

    if is_cloud:
        logger.info("CLOUD_LIGHTWEIGHT_MODE active: Autonomous EOD & Catalyst daemons delegated to GitHub Actions 7GB worker.")
        if os.getenv("TELEGRAM_BOT_TOKEN"):
            try:
                backend_url = os.getenv("RENDER_BACKEND_URL", "https://mil-quant-backend.onrender.com").rstrip("/")
                asyncio.create_task(register_telegram_webhook(f"{backend_url}/api/v1/telegram/webhook"))
            except Exception as tg_err:
                logger.warning(f"Failed to schedule Telegram webhook registration: {tg_err}")
    else:
        # 2. Start autonomous platform daemon (Local / dedicated server only)
        daemon_task = asyncio.create_task(run_autonomous_platform_daemon())

        # 3. Start embedded intraday catalyst & push loop if explicitly enabled
        enable_embedded = os.getenv("ENABLE_EMBEDDED_SCHEDULER", "").lower() in ("true", "1")
        if enable_embedded:
            embedded_task = asyncio.create_task(embedded_intraday_catalyst_loop())

    try:
        yield
    finally:
        if embedded_task:
            embedded_task.cancel()
            try:
                await embedded_task
            except asyncio.CancelledError:
                pass
        if daemon_task:
            platform_daemon.stop()
            daemon_task.cancel()
            try:
                await daemon_task
            except asyncio.CancelledError:
                pass

app = FastAPI(
    title="Market Intelligence Lab API",
    version="2.4.0",
    description="Local-first quantitative analytics & autonomous market terminal REST API.",
    lifespan=lifespan
)

# CORS Configuration (ADR-0001: Explicit trusted local origins + Vercel & Cloud Regex)
extra_origins = []
for env_var in ("ALLOWED_ORIGINS", "MIL_CORS_ORIGINS"):
    val = os.getenv(env_var, "")
    if val:
        extra_origins.extend([o.strip() for o in val.split(",") if o.strip()])

allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://market-intelligence-lab-vert.vercel.app",
]
for o in extra_origins:
    if o not in allowed_origins:
        allowed_origins.append(o)

cors_origin_regex = os.getenv(
    "MIL_CORS_ORIGIN_REGEX",
    r"^https://market-intelligence-lab[-\w]*\.vercel\.app$|^https://mil-quant-backend[-\w]*\.onrender\.com$"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=cors_origin_regex,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD", "PATCH"],
    allow_headers=["*"],
    expose_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=10000)

@app.middleware("http")
async def observability_tracing_middleware(request: Request, call_next):
    req_id = request.headers.get("x-request-id") or f"req-{uuid.uuid4().hex[:8]}"
    token = request_id_ctx.set(req_id)
    start_time = time.perf_counter()
    rss_before = get_current_rss_mb()

    response = await call_next(request)

    duration_ms = round((time.perf_counter() - start_time) * 1000.0, 2)
    response.headers["X-Request-ID"] = req_id
    response.headers["X-Response-Time-Ms"] = str(duration_ms)
    response.headers["X-Process-RSS-MB"] = str(rss_before)

    path = request.url.path
    if not (path.endswith("/health") and response.status_code == 200):
        if duration_ms > 1500 or response.status_code >= 400:
            logger.warning(
                f"{request.method} {path} status={response.status_code} latency={duration_ms}ms rss={rss_before}MB req_id={req_id}"
            )
        else:
            logger.debug(
                f"{request.method} {path} status={response.status_code} latency={duration_ms}ms rss={rss_before}MB req_id={req_id}"
            )

    request_id_ctx.reset(token)
    return response

# Mount modular market routes (status, tearsheet, history)
app.include_router(market_router)
app.include_router(jobs_router)
app.include_router(stream_router)
app.include_router(portfolio_router)
app.include_router(backtest_router)
app.include_router(push_router, prefix="/api/v1")
app.include_router(internal_router, prefix="/api/v1")
app.include_router(telegram_router, prefix="/api/v1")


@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
def root_probe():
    """Lightweight root probe for Render load balancer and ingress health checks."""
    return {"status": "ok", "service": "mil-quant-backend"}


_health_db_cache: Dict[str, Any] = {
    "latest_ohlcv": None,
    "latest_factors": None,
    "active_count": 0,
    "watchlist_count": 0,
}
_health_db_cache_time: float = 0.0

@app.get("/health")
@app.get("/api/v1/health")
def health_check():
    """Ultra-fast non-blocking health check endpoint confirming database connectivity, memory headroom, and champion model."""
    global _health_db_cache, _health_db_cache_time
    try:
        hydration_status = get_hydration_status()
        now_ts = time.time()

        # Phase 5 Live Health & Memory Headroom Telemetry
        guard = enforce_rss_memory_guard(threshold_mb=375.0)
        rss_mb = guard["rss_mb"]
        memory_headroom_mb = guard["memory_headroom_mb"]

        # If database is ready, safely refresh cached DB telemetry every 15 seconds
        if hydration_status == "READY" and (now_ts - _health_db_cache_time > 15.0 or not _health_db_cache.get("latest_ohlcv")):
            try:
                with sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True, timeout=1.0) as quick_conn:
                    cur = quick_conn.cursor()
                    cur.execute("SELECT MAX(trading_date) FROM ohlcv_daily")
                    ohlcv_row = cur.fetchone()
                    cur.execute("SELECT MAX(trading_date) FROM quant_factors_daily")
                    factors_row = cur.fetchone()
                    cur.execute("SELECT COUNT(*) FROM securities_master WHERE is_active = 1")
                    sec_row = cur.fetchone()
                    cur.execute("SELECT COUNT(*) FROM user_watchlists")
                    wl_row = cur.fetchone()

                    _health_db_cache["latest_ohlcv"] = ohlcv_row[0] if ohlcv_row else None
                    _health_db_cache["latest_factors"] = factors_row[0] if factors_row else None
                    _health_db_cache["active_count"] = sec_row[0] if sec_row else 0
                    _health_db_cache["watchlist_count"] = wl_row[0] if wl_row else 0
                    _health_db_cache_time = now_ts
            except Exception as db_query_err:
                logger.debug(f"Health DB query non-fatal fallback: {db_query_err}")

        # Active champion model lookup (derived authoritatively from tournament_summary.json)
        active_champion = "Deterministic Baseline (Momentum+LowVol+PIT)"
        try:
            summary_file = Path("data/models/tournament_summary.json")
            if summary_file.exists():
                with open(summary_file, "r", encoding="utf-8") as sf:
                    s_data = json.load(sf)
                    champ = s_data.get("champion", {})
                    p_verdict = s_data.get("promotion_verdict", champ.get("promotion_status"))
                    if p_verdict in ("CHAMPION", "PROMOTED"):
                        active_champion = champ.get("candidate_name", active_champion)
                    else:
                        active_champion = s_data.get("baseline", {}).get("name", active_champion)
        except Exception:
            pass

        # Durable state status & active dual-cloud backends
        durable_state_status = "LOCAL_ONLY"
        durable_backends_active: List[str] = []
        try:
            from src.storage.durable_state import DurableStateManager
            summary = DurableStateManager.get_instance().get_status_summary()
            durable_state_status = summary.get("durable_state_status", "LOCAL_ONLY")
            durable_backends_active = summary.get("durable_backends_active", [])
        except Exception:
            pass

        return sanitize_for_json({
            "status": "healthy",
            "hydration_status": hydration_status,
            "database": "connected (WAL mode)" if hydration_status == "READY" else "hydrating_background",
            "latest_ohlcv_date": _health_db_cache.get("latest_ohlcv"),
            "latest_factors_date": _health_db_cache.get("latest_factors"),
            "active_universe_count": _health_db_cache.get("active_count", 0),
            "user_watchlist_count": _health_db_cache.get("watchlist_count", 0),
            "rss_mb": rss_mb,
            "memory_headroom_mb": memory_headroom_mb,
            "cgroup_memory_limit_mb": 512.0,
            "durable_state_status": durable_state_status,
            "durable_backends_active": durable_backends_active,
            "active_champion_model": active_champion,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database health check failed: {str(e)}")


_supervisor_status_cache: Dict[str, Any] = {}
_supervisor_status_cache_time: float = 0.0
_SUPERVISOR_STATUS_TTL_SECONDS: float = 30.0

@app.get("/supervisor/status")
@app.get("/api/v1/supervisor/status")
def get_supervisor_status(force_refresh: bool = False):
    """Returns real-time status of the autonomous supervisor, EOD daemon, and universe health (cached with 30s TTL)."""
    global _supervisor_status_cache, _supervisor_status_cache_time
    now = time.monotonic()
    if not force_refresh and _supervisor_status_cache and (now - _supervisor_status_cache_time) < _SUPERVISOR_STATUS_TTL_SECONDS:
        return _supervisor_status_cache

    status = platform_daemon.get_status()
    _supervisor_status_cache = status
    _supervisor_status_cache_time = now
    return status


@app.get("/screener")
@app.get("/api/v1/screener")
def get_screener(
    request: Request,
    min_roe: Optional[float] = Query(None, description="Minimum Return on Equity (%)"),
    max_de: Optional[float] = Query(None, description="Maximum Debt-to-Equity ratio"),
    price_above_sma200: Optional[bool] = Query(None, description="Filter for Price > 200-day SMA"),
    exclude_financials: bool = Query(False, description="Exclude Financial Services sector"),
    include_watchlists: bool = Query(True, description="Include onboarded user watchlists"),
    sort_by: Optional[str] = Query(None, description="Sort column (e.g. composite_score or blended_score)"),
    limit: int = Query(1500, ge=1, le=2500, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Returns top-ranked stocks from the latest trading session in quant_factors_daily
    sorted descending by composite Quality-Momentum score.
    Safely sanitizes all NaN / Infinity values to prevent serialization crashes.
    """
    global _screener_snapshot_cache, _screener_cached_bytes, _screener_cached_gzip, _screener_cached_1000_bytes, _screener_cached_1000_gzip, _screener_cache_date, _screener_cache_time
    enforce_rss_memory_guard(threshold_mb=375.0)
    try:
        is_default_query = (
            min_roe is None and
            max_de is None and
            price_above_sma200 is None and
            not exclude_financials and
            include_watchlists and
            (sort_by is None or sort_by == "composite_score")
        )

        accepts_gzip = "gzip" in request.headers.get("accept-encoding", "").lower()

        # Fast In-Memory Materialized View Serve (< 5ms) with Double-Checked Single-Flight Lock
        if is_default_query:
            with _screener_cache_lock:
                now_time = datetime.datetime.now().timestamp()
                if (
                    _screener_snapshot_cache is not None and
                    (now_time - _screener_cache_time < SCREENER_CACHE_TTL_SECONDS)
                ):
                    cached_items = _screener_snapshot_cache["items"]
                    cached_date = _screener_cache_date
                    if offset == 0 and limit == 1000:
                        if accepts_gzip and _screener_cached_1000_gzip is not None:
                            return Response(content=_screener_cached_1000_gzip, media_type="application/json", headers={"Content-Encoding": "gzip"})
                        if _screener_cached_1000_gzip is not None:
                            return Response(content=gzip.decompress(_screener_cached_1000_gzip), media_type="application/json")
                    if offset == 0 and limit >= len(cached_items):
                        if accepts_gzip and _screener_cached_gzip is not None:
                            return Response(content=_screener_cached_gzip, media_type="application/json", headers={"Content-Encoding": "gzip"})
                        if _screener_cached_gzip is not None:
                            return Response(content=gzip.decompress(_screener_cached_gzip), media_type="application/json")

                    sliced_items = cached_items[offset: offset + limit]
                    payload = {
                        "trading_date": cached_date,
                        "as_of_date": cached_date,
                        "total_candidates": len(cached_items),
                        "returned_count": len(sliced_items),
                        "offset": offset,
                        "limit": limit,
                        "candidates": sliced_items,
                        "results": sliced_items,
                        "items": sliced_items,
                        "cached": True
                    }
                    return Response(content=json.dumps(payload).encode("utf-8"), media_type="application/json")

                # Cache miss or expired: Generate inside lock to prevent thundering-herd memory ballooning
                db = DatabaseManager(DATABASE_PATH)
                screener = FactorScreener(db)
                with db.get_connection() as conn:
                    cur = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily")
                    latest_date = cur.fetchone()[0]

                if not latest_date:
                    return sanitize_for_json({"as_of_date": None, "total_count": 0, "results": []})

                df = screener.screen(
                    trading_date=latest_date,
                    criteria={"sort_by": "composite_score"},
                    include_watchlists=include_watchlists,
                    limit=2500,
                    offset=0
                )
                df_clean = df.where(pd.notnull(df), None)

                results = []
                for rank, (_, row) in enumerate(df_clean.iterrows(), start=1):
                    sym = str(row["symbol"])
                    b_score = safe_float(row.get("blended_score"), 2)
                    if b_score is None:
                        b_score = safe_float(row.get("composite_score"), 2)

                    target_alloc = safe_float(row.get("target_allocation_pct"), 2) or 0.0
                    drivers = row.get("horizon_drivers")
                    if not isinstance(drivers, list):
                        drivers = []
                    is_target = bool(row.get("is_rebalance_target", False))

                    results.append({
                        "rank": rank,
                        "symbol": sym,
                        "company_name": str(row.get("company_name", sym)),
                        "sector": str(row.get("sector", "Unclassified")),
                        "close": safe_float(row.get("close"), 2),
                        "sma_200": safe_float(row.get("sma_200"), 2),
                        "debt_to_equity": safe_float(row.get("debt_to_equity"), 4),
                        "roe_pct": safe_float(row.get("roe_pct"), 2),
                        "opm_pct": safe_float(row.get("opm_pct"), 2),
                        "excess_ret_20d": (
                            safe_float(row.get("excess_ret_20d"), 4)
                            if row.get("excess_ret_20d") is not None
                            else (safe_float(row.get("ret_20d"), 4) or 0.0)
                        ),
                        "ret_20d": (
                            safe_float(row.get("ret_20d"), 4)
                            if row.get("ret_20d") is not None
                            else (safe_float(row.get("excess_ret_20d"), 4) or 0.0)
                        ),
                        "return_20d": (
                            safe_float(row.get("ret_20d"), 4)
                            if row.get("ret_20d") is not None
                            else (safe_float(row.get("excess_ret_20d"), 4) or 0.0)
                        ),
                        "composite_score": safe_float(row.get("composite_score"), 2),
                        "blended_score": b_score,
                        "target_allocation_pct": target_alloc,
                        "horizon_drivers": drivers,
                        "is_rebalance_target": is_target,
                        "score_20d": safe_float(row.get("score_20d"), 1),
                        "score_60d": safe_float(row.get("score_60d"), 1),
                        "price_above_sma200": bool(row.get("price_above_sma200", False)),
                        "is_watchlist": bool(row.get("is_watchlist", 0)),
                        "rsi_14": safe_float(row.get("rsi_14"), 2),
                        "volatility_20d": safe_float(row.get("volatility_20d"), 4),
                        "delivery_pct": safe_float(row.get("delivery_pct"), 2),
                        "turnover_cr": safe_float(row.get("turnover_cr"), 2),
                        "distance_52w_high": safe_float(row.get("distance_52w_high"), 4),
                        "distance_52w_low": safe_float(row.get("distance_52w_low"), 4),
                        "pct_from_52w_high": (
                            max(-100.0, min(0.0, round(float(row.get("distance_52w_high")), 2)))
                            if row.get("distance_52w_high") is not None and not pd.isna(row.get("distance_52w_high"))
                            else None
                        )
                    })

                payload = {
                    "trading_date": latest_date,
                    "as_of_date": latest_date,
                    "total_candidates": len(results),
                    "returned_count": len(results),
                    "offset": 0,
                    "limit": len(results),
                    "candidates": results,
                    "results": results,
                    "items": results,
                    "cached": True
                }
                raw_bytes = json.dumps(payload).encode("utf-8")
                raw_gzip = gzip.compress(raw_bytes, compresslevel=6)
                sliced_1000 = results[:1000]
                raw_1000_bytes = json.dumps({
                    "trading_date": latest_date,
                    "as_of_date": latest_date,
                    "total_candidates": len(results),
                    "returned_count": len(sliced_1000),
                    "offset": 0,
                    "limit": 1000,
                    "candidates": sliced_1000,
                    "results": sliced_1000,
                    "items": sliced_1000,
                    "cached": True
                }).encode("utf-8")
                raw_1000_gzip = gzip.compress(raw_1000_bytes, compresslevel=6)

                _screener_snapshot_cache = {
                    "trading_date": latest_date,
                    "as_of_date": latest_date,
                    "total_candidates": len(results),
                    "items": results
                }
                _screener_cached_bytes = None
                _screener_cached_gzip = raw_gzip
                _screener_cached_1000_bytes = None
                _screener_cached_1000_gzip = raw_1000_gzip
                _screener_cache_date = latest_date
                _screener_cache_time = now_time

                del df, df_clean, raw_bytes, raw_1000_bytes
                gc.collect()
                enforce_rss_memory_guard(threshold_mb=375.0)

                if offset == 0 and limit == 1000:
                    if accepts_gzip:
                        return Response(content=raw_1000_gzip, media_type="application/json", headers={"Content-Encoding": "gzip"})
                    return Response(content=gzip.decompress(raw_1000_gzip), media_type="application/json")
                if offset == 0 and limit >= len(results):
                    if accepts_gzip:
                        return Response(content=raw_gzip, media_type="application/json", headers={"Content-Encoding": "gzip"})
                    return Response(content=gzip.decompress(raw_gzip), media_type="application/json")

                sliced_results = results[offset: offset + limit]
                sliced_payload = {
                    "trading_date": latest_date,
                    "as_of_date": latest_date,
                    "total_candidates": len(results),
                    "returned_count": len(sliced_results),
                    "offset": offset,
                    "limit": limit,
                    "candidates": sliced_results,
                    "results": sliced_results,
                    "items": sliced_results,
                    "cached": True
                }
                return Response(content=json.dumps(sliced_payload).encode("utf-8"), media_type="application/json")

        # Non-default query with explicit filters: execute dynamic screen
        db = DatabaseManager(DATABASE_PATH)
        screener = FactorScreener(db)
        with db.get_connection() as conn:
            cur = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily")
            latest_date = cur.fetchone()[0]

        if not latest_date:
            return sanitize_for_json({"as_of_date": None, "total_count": 0, "results": []})

        criteria: Dict[str, Any] = {}
        if min_roe is not None:
            criteria["min_roe_pct"] = min_roe
        if max_de is not None:
            criteria["max_debt_to_equity"] = max_de
        if price_above_sma200 is True:
            criteria["price_above_sma200"] = True
        if exclude_financials:
            criteria["exclude_sectors"] = ["Financial Services"]
        criteria["sort_by"] = sort_by if sort_by else "composite_score"

        df = screener.screen(
            trading_date=latest_date,
            criteria=criteria,
            include_watchlists=include_watchlists,
            limit=limit,
            offset=offset
        )
        df_clean = df.where(pd.notnull(df), None)
        results = []
        for rank, (_, row) in enumerate(df_clean.iterrows(), start=offset + 1):
            sym = str(row["symbol"])
            b_score = safe_float(row.get("blended_score"), 2) or safe_float(row.get("composite_score"), 2)
            results.append({
                "rank": rank,
                "symbol": sym,
                "company_name": str(row.get("company_name", sym)),
                "sector": str(row.get("sector", "Unclassified")),
                "close": safe_float(row.get("close"), 2),
                "sma_200": safe_float(row.get("sma_200"), 2),
                "debt_to_equity": safe_float(row.get("debt_to_equity"), 4),
                "roe_pct": safe_float(row.get("roe_pct"), 2),
                "opm_pct": safe_float(row.get("opm_pct"), 2),
                "composite_score": safe_float(row.get("composite_score"), 2),
                "blended_score": b_score,
                "is_watchlist": bool(row.get("is_watchlist", 0)),
            })

        return sanitize_for_json({
            "trading_date": latest_date,
            "as_of_date": latest_date,
            "total_candidates": len(df),
            "returned_count": len(results),
            "offset": offset,
            "limit": limit,
            "candidates": results,
            "results": results,
            "items": results,
            "cached": False
        })
    except Exception as e:
        logger.error(f"Screener execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Screener execution error: {str(e)}")


@app.get("/watchlist")
@app.get("/api/v1/watchlist")
def get_watchlist(conn: sqlite3.Connection = Depends(get_db_connection)):
    """
    Returns data for symbols in user_watchlists joined with latest OHLCV
    and quantitative factors.
    """
    try:
        cur = conn.cursor()
        sql = """
        SELECT 
            w.symbol,
            w.company_name,
            w.sector,
            w.target_price,
            w.stop_loss,
            w.notes,
            w.added_date,
            o.trading_date,
            o.open,
            o.high,
            o.low,
            o.close,
            o.volume,
            q.ret_1d,
            q.ret_5d,
            q.ret_20d,
            q.sma_20,
            q.sma_50,
            q.sma_200,
            q.volatility_annualized,
            q.beta_60d_nifty,
            q.ttm_pe,
            q.roe_pct,
            q.debt_to_equity,
            q.opm_pct
        FROM user_watchlists w
        LEFT JOIN (
            SELECT symbol, open, high, low, close, volume, trading_date,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
            FROM ohlcv_daily
            WHERE symbol IN (SELECT symbol FROM user_watchlists)
        ) o ON w.symbol = o.symbol AND o.rn = 1
        LEFT JOIN (
            SELECT symbol, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200,
                   volatility_annualized, beta_60d_nifty, ttm_pe, roe_pct, debt_to_equity, opm_pct,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
            FROM quant_factors_daily
            WHERE symbol IN (SELECT symbol FROM user_watchlists)
        ) q ON w.symbol = q.symbol AND q.rn = 1
        ORDER BY w.symbol ASC;
        """
        cur.execute(sql)
        rows = cur.fetchall()

        # Fetch real 10-day price history for sparkline visualization
        sparklines = {}
        if rows:
            symbols = [r["symbol"] for r in rows]
            placeholders = ",".join(["?"] * len(symbols))
            cur.execute(f"""
                SELECT symbol, close FROM (
                    SELECT symbol, close, trading_date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
                    FROM ohlcv_daily
                    WHERE symbol IN ({placeholders})
                ) WHERE rn <= 10 ORDER BY symbol, trading_date ASC
            """, symbols)
            for s_row in cur.fetchall():
                sym = s_row["symbol"]
                c_val = safe_float(s_row["close"], 2)
                if c_val is not None:
                    sparklines.setdefault(sym, []).append(c_val)

        watchlist = []
        for r in rows:
            close_val = safe_float(r["close"], 2)
            sma200_val = safe_float(r["sma_200"], 2)
            ret_1d_val = safe_float(r["ret_1d"], 4) or 0.0

            dist_sma200 = None
            if close_val is not None and sma200_val is not None and sma200_val > 0:
                dist_sma200 = round(((close_val / sma200_val) - 1.0) * 100.0, 2)

            watchlist.append({
                "symbol": r["symbol"],
                "company_name": r["company_name"],
                "sector": r["sector"],
                "target_price": safe_float(r["target_price"], 2),
                "stop_loss": safe_float(r["stop_loss"], 2),
                "notes": r["notes"],
                "added_date": r["added_date"],
                "trading_date": r["trading_date"],
                "close": close_val,
                "open": safe_float(r["open"], 2),
                "high": safe_float(r["high"], 2),
                "low": safe_float(r["low"], 2),
                "volume": safe_int(r["volume"]),
                "ret_1d": round(ret_1d_val, 4),
                "ret_1d_pct": round(ret_1d_val * 100.0, 2),
                "sma_20": safe_float(r["sma_20"], 2),
                "sma_50": safe_float(r["sma_50"], 2),
                "sma_200": sma200_val,
                "dist_sma200_pct": dist_sma200,
                "price_above_sma200": (close_val > sma200_val) if (close_val and sma200_val) else False,
                "volatility_annualized": safe_float(r["volatility_annualized"], 4),
                "beta_60d_nifty": safe_float(r["beta_60d_nifty"], 2),
                "ttm_pe": safe_float(r["ttm_pe"], 2),
                "roe_pct": safe_float(r["roe_pct"], 2),
                "debt_to_equity": safe_float(r["debt_to_equity"], 4),
                "opm_pct": safe_float(r["opm_pct"], 2),
                "sparkline": sparklines.get(r["symbol"], [])
            })

        return sanitize_for_json({
            "count": len(watchlist),
            "watchlist": watchlist
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Watchlist retrieval error: {str(e)}")


class WatchlistAddRequest(BaseModel):
    symbol: str
    action: Optional[str] = None  # 'add' or 'remove'
    target_price: Optional[float] = None
    stop_loss: Optional[float] = None
    notes: Optional[str] = None


@app.post("/watchlist")
@app.post("/api/v1/watchlist")
def add_to_watchlist(
    payload: WatchlistAddRequest,
    conn: sqlite3.Connection = Depends(get_write_db_connection)
):
    """Adds, updates, or removes an equity symbol in user_watchlists with automated securities_master metadata."""
    sym = payload.symbol.strip().upper()
    try:
        if payload.action and payload.action.lower() == "remove":
            conn.execute("DELETE FROM user_watchlists WHERE symbol = ?", (sym,))
            conn.commit()
            return {
                "status": "ok",
                "message": f"{sym} removed from active user watchlist.",
                "symbol": sym,
                "is_watchlist": False
            }

        # Lookup company_name & sector from securities_master
        sec = conn.execute(
            "SELECT company_name, sector FROM securities_master WHERE symbol = ?", (sym,)
        ).fetchone()
        comp_name = sec["company_name"] if sec and sec["company_name"] else sym
        sector = sec["sector"] if sec and sec["sector"] else "Equity"
        today_str = datetime.date.today().isoformat()

        conn.execute("""
            INSERT INTO user_watchlists (symbol, company_name, sector, added_date, target_price, stop_loss, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                target_price = COALESCE(excluded.target_price, user_watchlists.target_price),
                stop_loss = COALESCE(excluded.stop_loss, user_watchlists.stop_loss),
                notes = COALESCE(excluded.notes, user_watchlists.notes)
        """, (sym, comp_name, sector, today_str, payload.target_price, payload.stop_loss, payload.notes))
        conn.commit()
        mark_state_dirty()

        return {
            "status": "ok",
            "message": f"{sym} added to active user watchlist.",
            "symbol": sym,
            "is_watchlist": True
        }
    except Exception as e:
        logger.error(f"Error adding {sym} to watchlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to add to watchlist: {str(e)}")


@app.delete("/watchlist/{symbol}")
@app.delete("/api/v1/watchlist/{symbol}")
def remove_from_watchlist(
    symbol: str,
    conn: sqlite3.Connection = Depends(get_write_db_connection)
):
    """Removes an equity symbol from user_watchlists."""
    sym = symbol.strip().upper()
    try:
        conn.execute("DELETE FROM user_watchlists WHERE symbol = ?", (sym,))
        conn.commit()
        mark_state_dirty()
        return {
            "status": "ok",
            "message": f"{sym} removed from active user watchlist.",
            "symbol": sym,
            "is_watchlist": False
        }
    except Exception as e:
        logger.error(f"Error removing {sym} from watchlist: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to remove from watchlist: {str(e)}")


@app.get("/macro")
@app.get("/api/v1/macro")
def get_macro_telemetry():
    """
    Returns verified macro telemetry with real observed timestamps (P0-05, ADR-0002).
    """
    from src.client.macro_client import MacroClient
    data = MacroClient.get_macro_telemetry()
    return sanitize_for_json(data)


# =====================================================================
# V8 Engine / Phase 10: Universe Expansion & Walk-Forward ML Endpoints
# =====================================================================

class UniverseExpandRequest(BaseModel):
    batch_size: Optional[int] = 15
    target_start_date: Optional[str] = "2011-01-01"
    run_seed_only: Optional[bool] = False


class MLTrainRequest(BaseModel):
    horizons: Optional[List[int]] = [5, 20, 60]


@app.post("/system/universe/expand")
@app.post("/api/v1/system/universe/expand")
def expand_universe_endpoint(req: Optional[UniverseExpandRequest] = None):
    """Seeds the 1,000+ master universe and optionally triggers a 15-year backfill batch."""
    try:
        from src.data.universe_expander import UniverseExpander
        db = DatabaseManager(DATABASE_PATH)
        expander = UniverseExpander(db=db)
        status = expander.seed_master_universe()
        if req and not req.run_seed_only:
            batch_res = expander.run_backfill_batch(
                batch_size=req.batch_size or 15,
                target_start_date=req.target_start_date or "2011-01-01"
            )
            return sanitize_for_json(batch_res)
        return sanitize_for_json(status)
    except Exception as e:
        logger.error(f"Error expanding universe: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Universe expansion failed: {str(e)}")


@app.get("/system/universe/status")
@app.get("/api/v1/system/universe/status")
def get_universe_status_endpoint():
    """Returns tracking status of the 1,000+ universe and 15-year historical backfill."""
    try:
        from src.data.universe_expander import UniverseExpander
        db = DatabaseManager(DATABASE_PATH)
        expander = UniverseExpander(db=db)
        return sanitize_for_json(expander.get_universe_status())
    except Exception as e:
        logger.error(f"Error getting universe status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get universe status: {str(e)}")


@app.post("/ml/train")
@app.post("/api/v1/ml/train")
def train_ml_tournament_endpoint(req: Optional[MLTrainRequest] = None):
    """Executes purged walk-forward ML training tournament across 5D, 20D, and 60D horizons."""
    if is_cloud_lightweight_mode():
        logger.info("CLOUD_LIGHTWEIGHT_MODE active: Serving cached tournament summary and models without retraining.")
        summary_path = Path("data/models/tournament_summary.json")
        if not summary_path.is_absolute():
            summary_path = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "tournament_summary.json"
        summary_data = {}
        if summary_path.exists():
            with open(summary_path, "r", encoding="utf-8") as f:
                summary_data = json.load(f)
        else:
            try:
                from src.quant.ml_trainer import WalkForwardMLTrainer
                db = DatabaseManager(DATABASE_PATH)
                trainer = WalkForwardMLTrainer(db=db)
                summary_data = trainer.get_ml_telemetry(limit=10)
            except Exception:
                summary_data = {}
        return sanitize_for_json({
            "message": "Cloud Lightweight Mode active: Serving pre-trained champion models from registry.",
            "mode": "CLOUD_LIGHTWEIGHT_MODE",
            "results": [summary_data.get("overall_summary", summary_data)],
            "telemetry": summary_data
        })
    try:
        from src.quant.ml_trainer import WalkForwardMLTrainer
        db = DatabaseManager(DATABASE_PATH)
        trainer = WalkForwardMLTrainer(db=db)
        horizons = req.horizons if req and req.horizons else [5, 20, 60]
        results = trainer.run_training_tournament(horizons=horizons)
        return sanitize_for_json({
            "message": "ML walk-forward tournament completed successfully.",
            "results": results,
            "telemetry": trainer.get_ml_telemetry(limit=10)
        })
    except Exception as e:
        logger.error(f"Error training ML models: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"ML training failed: {str(e)}")


@app.get("/ml/telemetry")
@app.get("/api/v1/ml/telemetry")
def get_ml_telemetry_endpoint(limit: int = Query(25, ge=1, le=100)):
    """Returns chronological ledger of ML training runs and current out-of-sample champions."""
    try:
        from src.quant.ml_trainer import WalkForwardMLTrainer
        db = DatabaseManager(DATABASE_PATH)
        trainer = WalkForwardMLTrainer(db=db)
        return sanitize_for_json(trainer.get_ml_telemetry(limit=limit))
    except Exception as e:
        logger.error(f"Error fetching ML telemetry: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch ML telemetry: {str(e)}")


@app.get("/models/tournament")
@app.get("/api/v1/models/tournament")
def get_ml_tournament_summary():
    """
    Returns latest CPCV(6, 2) walk-forward ML tournament summary, candidate metrics,
    Deflated Sharpe Ratio (DSR) stats, and active production champion model status.
    """
    try:
        summary_path = Path("data/models/tournament_summary.json")
        if not summary_path.exists():
            summary_path = Path(__file__).resolve().parent.parent.parent / "data" / "models" / "tournament_summary.json"

        if summary_path.exists():
            with open(summary_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            # Determine active production champion
            champ = data.get("champion", {})
            if champ.get("promotion_status") == "CHAMPION":
                active_champion = champ.get("candidate_name", "ML Champion")
            else:
                active_champion = data.get("baseline", {}).get("name", "Deterministic Baseline (Momentum+LowVol+PIT)")

            data["active_champion"] = active_champion
            data["status"] = "SUCCESS"
            return sanitize_for_json(data)
        else:
            return sanitize_for_json({
                "status": "NO_TOURNAMENT_RECORD",
                "active_champion": "Deterministic Baseline (Momentum+LowVol+PIT)",
                "baseline": {
                    "name": "Deterministic Baseline (Momentum+LowVol+PIT)",
                    "mean_net_sharpe": 0.4322,
                },
                "candidates": [],
                "champion": {
                    "promotion_status": "REJECTED_BELOW_BASELINE",
                    "candidate_name": "None"
                },
                "promotion_verdict": "REJECTED_BELOW_BASELINE",
                "message": "No tournament run summary found on disk. Deterministic baseline active."
            })
    except Exception as e:
        logger.error(f"Error reading tournament summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load tournament summary: {str(e)}")


@app.get("/regime/status")
@app.get("/api/v1/regime/status")
def get_regime_status(symbol: Optional[str] = Query(None), horizon_days: int = Query(20, ge=5, le=60)):
    """
    Returns active 3-State Gaussian HMM market regime, causal forward-only probabilities,
    execution policy rules, and calibrated 80% / 95% Weighted Adaptive Conformal Cones.
    """
    try:
        from src.quant.regime_hmm import load_regime_hmm_state, REGIME_POLICIES
        from src.quant.conformal_cones import load_conformal_quantiles, compute_conformal_price_cone

        hmm_state = load_regime_hmm_state()
        conf_state = load_conformal_quantiles()

        latest_regime = hmm_state.get("latest_regime", "HIGH_VOL_CHOP")
        policy = hmm_state.get("active_policy") or REGIME_POLICIES.get(latest_regime, {})

        payload: Dict[str, Any] = {
            "status": "ok",
            "causality_mode": hmm_state.get("causality_mode", "FORWARD_ONLY_FILTER"),
            "latest_date": hmm_state.get("latest_date"),
            "active_regime": latest_regime,
            "probabilities": hmm_state.get("latest_probabilities", {}),
            "policy": policy,
            "regime_distribution_pct": hmm_state.get("regime_distribution_pct", {}),
            "recent_history": (hmm_state.get("recent_history") or [])[-30:],
            "conformal": {
                "global_drift_status": conf_state.get("global_drift_status", "CALIBRATED"),
                "drift_alerts": conf_state.get("drift_alerts", []),
                "quantiles_active_regime": conf_state.get("quantiles_by_regime", {}).get(latest_regime, {}),
            },
            "symbol_cones": None,
        }

        if symbol:
            sym = symbol.strip().upper()
            try:
                with sqlite3.connect(f"file:{DATABASE_PATH}?mode=ro", uri=True, timeout=1.0) as conn:
                    closes_rows = conn.execute(
                        "SELECT close FROM ohlcv_daily WHERE symbol = ? AND is_synthetic = 0 ORDER BY trading_date DESC LIMIT 25",
                        (sym,),
                    ).fetchall()
                    closes = [float(r[0]) for r in reversed(closes_rows) if r[0] is not None and float(r[0]) > 0]
                    px = closes[-1] if closes else 100.0
                    if len(closes) >= 10:
                        import math
                        log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
                        mean_r = sum(log_rets) / len(log_rets)
                        var_r = sum((r - mean_r) ** 2 for r in log_rets) / max(len(log_rets) - 1, 1)
                        vol_20d = min(max(math.sqrt(var_r * 252.0), 0.08), 1.20)
                        ret_20d = (closes[-1] / closes[0]) - 1.0
                    else:
                        vol_20d = 0.25
                        ret_20d = 0.0

                    cones_by_horizon = {}
                    for h in (5, 10, 20):
                        exp_ret = max(-0.10, min(0.10, ret_20d * (h / 20.0) * 0.15))
                        cones_by_horizon[f"{h}D"] = compute_conformal_price_cone(
                            current_price=px,
                            expected_return=exp_ret,
                            annual_vol=vol_20d,
                            horizon_days=h,
                            regime=latest_regime,
                        )
                    payload["symbol_cones"] = {
                        "symbol": sym,
                        "current_price": px,
                        "annual_vol": round(vol_20d, 4),
                        "requested_horizon": f"{horizon_days}D",
                        "horizons": cones_by_horizon,
                    }
            except Exception as sym_err:
                logger.debug(f"Symbol conformal cone lookup notice for {sym}: {sym_err}")

        return sanitize_for_json(payload)
    except Exception as e:
        logger.error(f"Error computing regime status: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to compute regime status: {str(e)}")


@app.get("/regime/spillover")
@app.get("/api/v1/regime/spillover")
def get_regime_spillover():
    """
    Returns Cross-Asset & Sector Spillover Graph (Graphical Lasso partial correlations,
    Granger Lead -> Follower edges, and Systemic Contagion Index 0-100).
    """
    try:
        from src.quant.spillover_graph import load_spillover_graph
        data = load_spillover_graph()
        return sanitize_for_json({"status": "ok", **data})
    except Exception as e:
        logger.error(f"Error loading spillover graph: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to load spillover graph: {str(e)}")


@app.post("/news/ingest")
@app.post("/api/v1/news/ingest")
def trigger_news_ingestion(symbols: Optional[List[str]] = Query(None)):
    """Triggers live financial news ingestion and sentiment scoring for active portfolio and top stocks."""
    try:
        from src.tasks.news_daemon import NewsSentimentDaemon
        db = DatabaseManager(DATABASE_PATH)
        daemon = NewsSentimentDaemon(db=db)
        result = daemon.ingest_portfolio_and_top_candidates(top_symbols=symbols)
        return sanitize_for_json(result)
    except Exception as e:
        logger.error(f"Error ingesting news: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"News ingestion failed: {str(e)}")


def _format_catalyst_row(row_dict: dict) -> dict:
    item = dict(row_dict)
    for json_field, alias in [
        ("causal_bullets", "causal_bullets"),
        ("pillar1_price", "pillar1"),
        ("pillar2_macro", "pillar2"),
        ("pillar3_corp", "pillar3"),
        ("pillar4_news", "pillar4"),
    ]:
        val = item.get(json_field)
        if isinstance(val, str):
            try:
                parsed = json.loads(val)
                item[json_field] = parsed
                if alias:
                    item[alias] = parsed
            except Exception:
                pass
        elif val and alias:
            item[alias] = val
    return item


@app.post("/catalysts/scan")
@app.post("/api/v1/catalysts/scan")
def scan_catalysts_endpoint():
    """Trigger intraday causal anomaly scan and push alerts."""
    try:
        from src.tasks.catalyst_engine import catalyst_engine
        results = catalyst_engine.run_intraday_scan(max_push_alerts=2)
        return {"status": "ok", "count": len(results) if isinstance(results, list) else 0, "results": results}
    except Exception as e:
        logger.error(f"Error scanning catalysts: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/catalysts")
@app.get("/api/v1/catalysts")
@app.get("/catalysts/live")
@app.get("/api/v1/catalysts/live")
def get_live_catalysts_endpoint(
    limit: int = Query(20, ge=1, le=100),
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """Fetch recent market-wide causal catalysts."""
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, symbol, company_name, sector, move_pct, rvol, classification,
                   pillar1_price, pillar2_macro, pillar3_corp, pillar4_news,
                   causal_headline, causal_bullets, triggered_at
            FROM market_catalysts
            ORDER BY triggered_at DESC
            LIMIT ?
            """,
            (limit,)
        )
        rows = [_format_catalyst_row(dict(r)) for r in cur.fetchall()]
        return {"status": "ok", "count": len(rows), "catalysts": sanitize_for_json(rows)}
    except Exception as e:
        logger.error(f"Error fetching live catalysts: {e}", exc_info=True)
        return {"status": "error", "count": 0, "catalysts": []}


@app.get("/catalysts/symbol/{symbol}")
@app.get("/api/v1/catalysts/symbol/{symbol}")
def get_symbol_catalysts_endpoint(
    symbol: str,
    fallback: bool = Query(True),
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """Fetch catalysts for a specific symbol, optionally falling back to latest."""
    sym = symbol.strip().upper()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, symbol, company_name, sector, move_pct, rvol, classification,
                   pillar1_price, pillar2_macro, pillar3_corp, pillar4_news,
                   causal_headline, causal_bullets, triggered_at
            FROM market_catalysts
            WHERE symbol = ?
            ORDER BY triggered_at DESC
            LIMIT 10
            """,
            (sym,)
        )
        rows = [_format_catalyst_row(dict(r)) for r in cur.fetchall()]
        latest = rows[0] if rows else None
        return {
            "status": "ok",
            "symbol": sym,
            "catalysts": sanitize_for_json(rows),
            "latest": sanitize_for_json(latest)
        }
    except Exception as e:
        logger.error(f"Error fetching catalyst for {sym}: {e}", exc_info=True)
        return {"status": "error", "symbol": sym, "catalysts": [], "latest": None}


@app.get("/api/v1/ml/forecast/{symbol}")
def get_ml_forecast_endpoint(symbol: str):
    """
    Sub-millisecond multi-horizon walk-forward ML alpha inference.
    Returns 5D, 20D, and 60D forward return expectations with feature attributions.
    """
    sym = symbol.strip().upper()
    try:
        from src.quant.ml_trainer import WalkForwardMLTrainer
        db = DatabaseManager(DATABASE_PATH)
        trainer = WalkForwardMLTrainer(db=db)
        fc = trainer.predict_for_symbol(sym)
        return sanitize_for_json(fc)
    except Exception as e:
        logger.error(f"Error predicting ML for {sym}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/v1/ml/train_async")
def trigger_ml_training_endpoint(background_tasks: BackgroundTasks):
    """
    Triggers walk-forward ML tournament training across 5D, 20D, and 60D horizons
    in the background.
    """
    if is_cloud_lightweight_mode():
        return {
            "status": "skipped",
            "mode": "CLOUD_LIGHTWEIGHT_MODE",
            "message": "Cloud Lightweight Mode active: Serving pre-trained champion models without container retraining."
        }
    def _train():
        try:
            from src.quant.ml_trainer import WalkForwardMLTrainer
            db = DatabaseManager(DATABASE_PATH)
            trainer = WalkForwardMLTrainer(db=db)
            trainer.run_training_tournament()
        except Exception as err:
            logger.error(f"Background ML training error: {err}", exc_info=True)

    background_tasks.add_task(_train)
    return {
        "status": "accepted",
        "message": "Walk-forward ML tournament training scheduled asynchronously across 5D, 20D, and 60D horizons."
    }


class CopilotStreamRequest(BaseModel):
    symbol: str
    prompt: Optional[str] = "Debate Bull vs Bear Thesis"
    context_override: Optional[Dict[str, Any]] = None
    history: Optional[List[Dict[str, str]]] = None


copilot_engine = MultiAgentDeliberationEngine()


@app.post("/copilot/stream")
@app.post("/api/v1/copilot/stream")
async def stream_copilot_deliberation(request: CopilotStreamRequest):
    """
    Server-Sent Events (SSE) endpoint for multi-agent deliberation:
    Bull Analyst -> Bear Analyst -> Portfolio Manager Judge.
    """
    enforce_rss_memory_guard(threshold_mb=375.0)
    sym = request.symbol.strip().upper()
    user_prompt = request.prompt or "Debate Bull vs Bear Thesis"

    async def event_generator():
        try:
            async for chunk in copilot_engine.run_deliberation_stream(
                symbol=sym,
                user_prompt=user_prompt,
                context_override=request.context_override,
                history=request.history,
            ):
                yield chunk
        except Exception as stream_err:
            logger.error(f"Copilot streaming exception: {stream_err}", exc_info=True)
            err_payload = {"stage": "error", "message": f"Deliberation recovered: {str(stream_err)}", "progress": 100}
            yield f"data: {json.dumps(err_payload)}\n\n"
        finally:
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/copilot/deliberate")
@app.post("/api/v1/copilot/deliberate")
async def deliberate_copilot_json(request: CopilotStreamRequest):
    """
    Direct non-streaming JSON endpoint fallback for Copilot deliberation.
    Guarantees reliable turn completion when network proxies or edge limits sever SSE streams.
    """
    enforce_rss_memory_guard(threshold_mb=375.0)
    sym = request.symbol.strip().upper()
    user_prompt = request.prompt or "Debate Bull vs Bear Thesis"
    res = await copilot_engine.deliberate_json(
        symbol=sym,
        user_prompt=user_prompt,
        context_override=request.context_override,
        history=request.history
    )
    from src.api.utils import sanitize_for_json
    return sanitize_for_json(res)


@app.get("/copilot/usage")
@app.get("/api/v1/copilot/usage")
async def get_copilot_usage_telemetry():
    """Returns today's token & request usage per model, quota headroom, and distillation statistics."""
    from datetime import datetime, timezone
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    db = DatabaseManager(DATABASE_PATH)
    models_status = []

    with db.get_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM llm_usage_telemetry WHERE usage_date = ?",
            (today_utc,)
        ).fetchall()
        usage_by_model = {r["model_id"]: dict(r) for r in rows}

        ext_rows = conn.execute(
            "SELECT * FROM external_api_telemetry WHERE usage_date = ? ORDER BY service_name, endpoint_or_model",
            (today_utc,)
        ).fetchall()
        external_apis = [dict(r) for r in ext_rows]

    for model_id, quota in MODEL_QUOTAS.items():
        used_row = usage_by_model.get(model_id, {})
        reqs_used = used_row.get("requests_used", 0)
        toks_used = used_row.get("total_tokens", 0)
        daily_req_limit = quota.get("daily_request_limit", 1000)
        daily_tok_limit = quota.get("daily_token_limit", 200000)
        provider = "groq" if "gpt" in model_id else "gemini"

        models_status.append({
            "model_id": model_id,
            "provider": provider,
            "requests_used": reqs_used,
            "daily_request_limit": daily_req_limit,
            "requests_remaining": max(0, daily_req_limit - reqs_used),
            "requests_pct_used": round((reqs_used / daily_req_limit) * 100, 1) if daily_req_limit else 0,
            "prompt_tokens": used_row.get("prompt_tokens", 0),
            "completion_tokens": used_row.get("completion_tokens", 0),
            "total_tokens": toks_used,
            "daily_token_limit": daily_tok_limit,
            "tokens_remaining": max(0, daily_tok_limit - toks_used),
            "tokens_pct_used": round((toks_used / daily_tok_limit) * 100, 1) if daily_tok_limit else 0,
            "remaining_requests_header": used_row.get("remaining_requests_header"),
            "remaining_tokens_header": used_row.get("remaining_tokens_header"),
            "last_used_at": used_row.get("last_used_at")
        })

    distiller = CopilotKnowledgeDistiller(db)
    distill_stats = distiller.get_distillation_stats()

    return JSONResponse(sanitize_for_json({
        "status": "success",
        "date_utc": today_utc,
        "models": models_status,
        "distillation": distill_stats,
        "external_apis": external_apis
    }))


@app.post("/copilot/distill")
@app.post("/api/v1/copilot/distill")
async def trigger_copilot_distillation():
    """Triggers TF-IDF and Ridge parameter training on the collected teacher distillation corpus."""
    db = DatabaseManager(DATABASE_PATH)
    distiller = CopilotKnowledgeDistiller(db)
    train_results = distiller.train()
    stats = distiller.get_distillation_stats()
    return JSONResponse(sanitize_for_json({
        "status": "success",
        "message": "Distillation tournament trained successfully",
        "train_results": train_results,
        "distillation_stats": stats
    }))


class ClientLogRequest(BaseModel):
    level: str = "INFO"
    message: str
    meta: Optional[Dict[str, Any]] = None


@app.get("/system/logs")
@app.get("/api/v1/system/logs")
async def get_system_logs(
    limit: int = Query(150, ge=1, le=500),
    level: str = Query("INFO"),
    source: Optional[str] = Query(None),
    search: Optional[str] = Query(None)
):
    """Retrieves live in-memory and persistent system telemetry logs with process RSS memory stats."""
    logs = log_engine.get_logs(limit=limit, min_level=level, source=source, search=search)
    return sanitize_for_json({
        "rss_mb": get_current_rss_mb(),
        "total_buffered": len(log_engine.buffer),
        "count": len(logs),
        "logs": logs
    })


@app.post("/system/client-logs")
@app.post("/api/v1/system/client-logs")
async def receive_client_log(req: ClientLogRequest, request: Request):
    """Receives frontend warnings, errors, and unhandled rejections for unified log aggregation."""
    client_ip = request.client.host if request.client else "unknown"
    log_engine.log_client_event(
        level=req.level,
        message=req.message,
        client_ip=client_ip,
        meta=req.meta
    )
    return {"status": "recorded"}


__all__ = [
    "app",
    "market_router",
    "get_db_connection",
    "sanitize_for_json",
    "get_stock_status",
    "get_stock_tearsheet",
    "get_stock_history",
    "get_stock_forecast",
    "get_stock_news",
    "run_backtest_endpoint",
    "get_latest_backtest",
    "get_investment_memo",
    "get_system_accuracy",
    "run_dynamic_ingestion",
    "trigger_system_ingest",
]
