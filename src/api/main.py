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
import re
import gc
import json
import sqlite3
import datetime
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks, Response
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.copilot.deliberation import MultiAgentDeliberationEngine

from src.storage.database import DatabaseManager
from src.storage.hydration import is_cloud_lightweight_mode, hydrate_initial_cloud_database
from src.quant.screener import FactorScreener
from src.quant.rebalance_engine import RebalanceEngine
from src.api.utils import (
    DATABASE_PATH,
    get_db_connection,
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

from contextlib import asynccontextmanager
import asyncio
import threading
from src.tasks.daemon import platform_daemon, run_autonomous_platform_daemon

logger = logging.getLogger(__name__)

# Thread-safe In-Memory Screener Materialized Snapshot View (Milestone B6 / P0)
_screener_cache_lock = threading.Lock()
_screener_snapshot_cache: Optional[Dict[str, Any]] = None
_screener_cached_bytes: Optional[bytes] = None
_screener_cached_1000_bytes: Optional[bytes] = None
_screener_cache_date: Optional[str] = None
_screener_cache_time: float = 0.0
SCREENER_CACHE_TTL_SECONDS: float = 300.0


def invalidate_screener_cache() -> None:
    """Explicitly invalidates the in-memory screener snapshot cache."""
    global _screener_snapshot_cache, _screener_cached_bytes, _screener_cached_1000_bytes, _screener_cache_date, _screener_cache_time
    with _screener_cache_lock:
        _screener_snapshot_cache = None
        _screener_cached_bytes = None
        _screener_cached_1000_bytes = None
        _screener_cache_date = None
        _screener_cache_time = 0.0
    logger.info("In-memory screener cache invalidated.")

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
    # 1. Automatic database hydration (fresh cloud container deploy)
    try:
        hydrate_initial_cloud_database(DATABASE_PATH)
    except Exception as e:
        logger.error(f"Cloud database hydration error: {e}", exc_info=True)

    # 2. Start autonomous platform daemon
    daemon_task = asyncio.create_task(run_autonomous_platform_daemon())

    # 3. Start embedded intraday catalyst & push loop if enabled (default True on Render)
    embedded_task = None
    enable_embedded = (
        os.getenv("ENABLE_EMBEDDED_SCHEDULER", "").lower() in ("true", "1") or
        os.getenv("RENDER", "").lower() in ("true", "1")
    )
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_origin_regex=r"https://.*\.(vercel\.app|ngrok-free\.app|onrender\.com)",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)

# Mount modular market routes (status, tearsheet, history)
app.include_router(market_router)
app.include_router(jobs_router)
app.include_router(stream_router)
app.include_router(portfolio_router)
app.include_router(backtest_router)
app.include_router(push_router, prefix="/api/v1")


@app.get("/health")
@app.get("/api/v1/health")
def health_check(conn: sqlite3.Connection = Depends(get_db_connection)):
    """Health check endpoint confirming database connectivity and latest settled date."""
    try:
        cur = conn.cursor()
        cur.execute("SELECT MAX(trading_date) FROM ohlcv_daily")
        latest_ohlcv = cur.fetchone()[0]
        cur.execute("SELECT MAX(trading_date) FROM quant_factors_daily")
        latest_factors = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM securities_master WHERE is_active = 1")
        active_count = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM user_watchlists")
        watchlist_count = cur.fetchone()[0]
        return sanitize_for_json({
            "status": "healthy",
            "database": "connected (WAL mode)",
            "latest_ohlcv_date": latest_ohlcv,
            "latest_factors_date": latest_factors,
            "active_universe_count": active_count,
            "user_watchlist_count": watchlist_count,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Database health check failed: {str(e)}")


@app.get("/supervisor/status")
@app.get("/api/v1/supervisor/status")
def get_supervisor_status():
    """Returns real-time status of the autonomous supervisor, EOD daemon, and universe health."""
    return platform_daemon.get_status()


@app.get("/screener")
@app.get("/api/v1/screener")
def get_screener(
    min_roe: Optional[float] = Query(None, description="Minimum Return on Equity (%)"),
    max_de: Optional[float] = Query(None, description="Maximum Debt-to-Equity ratio"),
    price_above_sma200: Optional[bool] = Query(None, description="Filter for Price > 200-day SMA"),
    exclude_financials: bool = Query(False, description="Exclude Financial Services sector"),
    include_watchlists: bool = Query(True, description="Include onboarded user watchlists"),
    limit: int = Query(1000, ge=1, le=2000, description="Max results to return"),
    offset: int = Query(0, ge=0, description="Pagination offset")
):
    """
    Returns top-ranked stocks from the latest trading session in quant_factors_daily
    sorted descending by composite Quality-Momentum score.
    Safely sanitizes all NaN / Infinity values to prevent serialization crashes.
    """
    global _screener_snapshot_cache, _screener_cached_bytes, _screener_cached_1000_bytes, _screener_cache_date, _screener_cache_time
    try:
        is_default_query = (
            min_roe is None and
            max_de is None and
            price_above_sma200 is None and
            not exclude_financials and
            include_watchlists
        )

        # Fast In-Memory Materialized View Serve (< 5ms)
        now_time = datetime.datetime.now().timestamp()
        if is_default_query:
            with _screener_cache_lock:
                if (
                    _screener_snapshot_cache is not None and
                    (now_time - _screener_cache_time < SCREENER_CACHE_TTL_SECONDS)
                ):
                    cached_items = _screener_snapshot_cache["items"]
                    cached_date = _screener_cache_date
                    if offset == 0 and limit == 1000 and _screener_cached_1000_bytes is not None:
                        return Response(content=_screener_cached_1000_bytes, media_type="application/json")
                    if offset == 0 and limit >= len(cached_items) and _screener_cached_bytes is not None:
                        return Response(content=_screener_cached_bytes, media_type="application/json")

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

        db = DatabaseManager(DATABASE_PATH)
        screener = FactorScreener(db)

        # 1. Determine latest trading date
        with db.get_connection() as conn:
            cur = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily")
            latest_date = cur.fetchone()[0]

        if not latest_date:
            return sanitize_for_json({"as_of_date": None, "total_count": 0, "results": []})

        # 2. Build Criteria
        criteria: Dict[str, Any] = {}
        if min_roe is not None:
            criteria["min_roe_pct"] = min_roe
        if max_de is not None:
            criteria["max_debt_to_equity"] = max_de
        if price_above_sma200 is True:
            criteria["price_above_sma200"] = True
        if exclude_financials:
            criteria["exclude_sectors"] = ["Financial Services"]

        # 3. Execute deterministic screen
        # If default query, fetch all candidates to populate the in-memory cache
        fetch_limit = 2500 if is_default_query else limit
        fetch_offset = 0 if is_default_query else offset

        df = screener.screen(
            trading_date=latest_date,
            criteria=criteria if criteria else None,
            include_watchlists=include_watchlists,
            limit=fetch_limit,
            offset=fetch_offset
        )

        # Sanitize DataFrame replacing NaNs with None as specified in directive
        df_clean = df.where(pd.notnull(df), None)

        results = []
        for rank, (_, row) in enumerate(df_clean.iterrows(), start=fetch_offset + 1):
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
                "excess_ret_20d": safe_float(row.get("excess_ret_20d"), 4),
                "ret_20d": safe_float(row.get("ret_20d"), 4),
                "return_20d": safe_float(row.get("ret_20d"), 4),
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
                "volatility_20d": safe_float(row.get("volatility_20d"), 4)
            })

        # Populate cache on default queries
        if is_default_query:
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
            with _screener_cache_lock:
                _screener_snapshot_cache = {
                    "trading_date": latest_date,
                    "as_of_date": latest_date,
                    "total_candidates": len(results),
                    "items": results
                }
                _screener_cached_bytes = raw_bytes
                _screener_cached_1000_bytes = raw_1000_bytes
                _screener_cache_date = latest_date
                _screener_cache_time = now_time

            if offset == 0 and limit == 1000:
                return Response(content=raw_1000_bytes, media_type="application/json")
            if offset == 0 and limit >= len(results):
                return Response(content=raw_bytes, media_type="application/json")

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
                "cached": False
            }
            return Response(content=json.dumps(sliced_payload).encode("utf-8"), media_type="application/json")
        else:
            sliced_results = results

        return sanitize_for_json({
            "trading_date": latest_date,
            "as_of_date": latest_date,
            "total_candidates": len(results) if is_default_query else len(df),
            "returned_count": len(sliced_results),
            "offset": offset,
            "limit": limit,
            "candidates": sliced_results,
            "results": sliced_results,
            "items": sliced_results
        })
    except Exception as e:
        logger.error(f"Screener execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Screener execution error: {str(e)}")


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
        ) o ON w.symbol = o.symbol AND o.rn = 1
        LEFT JOIN (
            SELECT symbol, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200,
                   volatility_annualized, beta_60d_nifty, ttm_pe, roe_pct, debt_to_equity, opm_pct,
                   ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
            FROM quant_factors_daily
        ) q ON w.symbol = q.symbol AND q.rn = 1
        ORDER BY w.symbol ASC;
        """
        cur.execute(sql)
        rows = cur.fetchall()

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
                "opm_pct": safe_float(r["opm_pct"], 2)
            })

        return sanitize_for_json({
            "count": len(watchlist),
            "watchlist": watchlist
        })
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Watchlist retrieval error: {str(e)}")


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


copilot_engine = MultiAgentDeliberationEngine()


@app.post("/copilot/stream")
@app.post("/api/v1/copilot/stream")
async def stream_copilot_deliberation(request: CopilotStreamRequest):
    """
    Server-Sent Events (SSE) endpoint for multi-agent deliberation:
    Bull Analyst -> Bear Analyst -> Portfolio Manager Judge.
    """
    sym = request.symbol.strip().upper()
    user_prompt = request.prompt or "Debate Bull vs Bear Thesis"

    async def event_generator():
        try:
            async for chunk in copilot_engine.run_deliberation_stream(
                symbol=sym,
                user_prompt=user_prompt,
                context_override=request.context_override
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
