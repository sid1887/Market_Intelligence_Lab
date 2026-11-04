"""
Market Intelligence Lab — Market & Stocks API Router (Milestones B6.4 & B6.4.1).

Exposes routes for individual stock tearsheets, dynamic status polling, and historical bars:
- GET /stocks/{symbol}/status & GET /api/v1/stocks/{symbol}/status
- GET /stocks/{symbol}/tearsheet & GET /api/v1/stocks/{symbol}/tearsheet
- GET /stocks/{symbol}/history & GET /api/v1/stocks/{symbol}/history
"""

import re
import gc
import sqlite3
import logging
from typing import Dict, Any, List, Optional
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query
from fastapi.responses import JSONResponse

from src.storage.database import DatabaseManager
from src.client.symbol_resolver import SymbolResolver
from src.pipeline.dynamic_ingestion import DynamicIngestionManager, _INGESTION_STATE
from src.api.utils import get_db_connection, sanitize_for_json, safe_float, safe_int, DATABASE_PATH

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stocks"])
market_router = router


def run_dynamic_ingestion(symbol: str) -> None:
    """Background worker for on-demand dynamic ingestion."""
    try:
        manager = DynamicIngestionManager()
        success = manager.ensure_symbol_data(symbol)
        if not success:
            logger.error(f"Background dynamic ingestion failed for {symbol}.")
    except Exception as e:
        logger.error(f"Background dynamic ingestion worker crashed for {symbol}: {e}", exc_info=True)
        DynamicIngestionManager.update_ingestion_status(
            symbol,
            status="FAILED",
            progress_pct=0,
            step="FAILED",
            detail=f"Worker error: {str(e)}"
        )
    finally:
        gc.collect()


@router.get("/stocks/{symbol}/status")
@router.get("/api/v1/stocks/{symbol}/status")
def get_stock_status(
    symbol: str,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns real-time data readiness status for frontend polling during dynamic ingestion.
    Never returns 404 for unknown or unseeded stocks.
    """
    sym = symbol.upper().strip()

    # 1. Check if currently in active ingestion jobs
    active_jobs = getattr(DynamicIngestionManager, "_active_jobs", _INGESTION_STATE)
    if sym in active_jobs:
        job = active_jobs[sym]
        status = job.get("status")
        if status in ("INGESTING", "FAILED"):
            return sanitize_for_json(job)
        elif status == "READY":
            return sanitize_for_json(job)

    # 2. Check if the symbol already exists in securities_master with populated OHLCV
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM securities_master WHERE symbol = ?", (sym,))
    in_sec = cur.fetchone() is not None
    if not in_sec:
        cur.execute("SELECT 1 FROM user_watchlists WHERE symbol = ?", (sym,))
        in_sec = cur.fetchone() is not None

    cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'", (sym,))
    ohlcv_count = cur.fetchone()[0]
    if ohlcv_count == 0:
        cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ?", (sym,))
        ohlcv_count = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM quant_factors_daily WHERE symbol = ?", (sym,))
    factor_count = cur.fetchone()[0]

    if in_sec and ohlcv_count > 0:
        return sanitize_for_json({
            "status": "READY",
            "symbol": sym,
            "progress_pct": 100,
            "step": "READY",
            "detail": f"Data fully populated ({ohlcv_count} bars, {factor_count} factors)."
        })

    # 3. If symbol is unknown and not in active ingestion, return NOT_STARTED
    return sanitize_for_json({
        "status": "NOT_STARTED",
        "symbol": sym,
        "progress_pct": 0,
        "step": "NOT_STARTED",
        "detail": f"Symbol '{sym}' is not queued for ingestion."
    })


@router.get("/stocks/{symbol}/tearsheet")
@router.get("/api/v1/stocks/{symbol}/tearsheet")
def get_stock_tearsheet(
    symbol: str,
    background_tasks: BackgroundTasks,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns a unified JSON payload containing the stock's latest OHLCV,
    20/50/200 SMAs, fundamental ratios (ROE, D/E, TTM P/E), 5 most recent
    corporate disclosures, and historical candlestick bars for charting.
    If the symbol is unseeded on the NSE cash segment, returns HTTP 202 Accepted
    and triggers background dynamic ingestion.
    """
    sym = symbol.upper().strip()
    if not re.match(r"^[A-Z0-9&_\-]{1,20}$", sym):
        raise HTTPException(status_code=400, detail=f"Invalid symbol format: '{sym}'.")

    cur = conn.cursor()

    # 1. Fetch metadata
    cur.execute(
        "SELECT symbol, company_name, isin, industry, sector FROM securities_master WHERE symbol = ?",
        (sym,)
    )
    sec_row = cur.fetchone()

    cur.execute(
        "SELECT company_name, sector, target_price, stop_loss, notes FROM user_watchlists WHERE symbol = ?",
        (sym,)
    )
    wl_row = cur.fetchone()

    # Check OHLCV presence and bar count (reading only necessary columns)
    cur.execute(
        "SELECT trading_date, open, high, low, close, volume FROM ohlcv_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1",
        (sym,)
    )
    ohlcv_row = cur.fetchone()

    cur.execute(
        "SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'",
        (sym,)
    )
    ohlcv_count = cur.fetchone()[0]

    # Check Factor presence (reading only necessary columns)
    cur.execute(
        """
        SELECT symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200,
               volatility_annualized, beta_60d_nifty, volume_ratio_20d, volume_zscore_50d,
               roe_pct, debt_to_equity, ttm_pe, opm_pct
        FROM quant_factors_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1
        """,
        (sym,)
    )
    factors_row = cur.fetchone()

    # If NOT fully populated, resolve dynamically and trigger background ingestion
    if not (sec_row or wl_row) or not ohlcv_row or ohlcv_count < 240 or not factors_row:
        resolver = SymbolResolver()
        try:
            resolver.resolve_symbol(sym)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{sym}' not found or not actively traded on NSE cash segment (series 'EQ')."
            )

        status_info = DynamicIngestionManager.get_ingestion_status(sym)
        if status_info.get("status") != "INGESTING":
            DynamicIngestionManager.update_ingestion_status(
                sym,
                status="INGESTING",
                progress_pct=25,
                step="QUEUED",
                detail="Symbol discovered. Ingesting 24-month historical series, fundamentals, and factors..."
            )
            background_tasks.add_task(run_dynamic_ingestion, sym)

        current_status = DynamicIngestionManager.get_ingestion_status(sym)
        return JSONResponse(
            status_code=202,
            content=sanitize_for_json({
                "status": "INGESTING",
                "symbol": sym,
                "message": "Symbol discovered. Ingesting 24-month historical series, fundamentals, and factors...",
                "progress_pct": current_status.get("progress_pct", 25),
                "step": current_status.get("step", "QUEUED")
            })
        )

    company_name = (wl_row["company_name"] if wl_row else sec_row["company_name"]) or sym
    sector = (wl_row["sector"] if wl_row else sec_row["sector"]) or "General"
    industry = (sec_row["industry"] if sec_row else sector) or "General"
    isin = (sec_row["isin"] if sec_row else "N/A") or "N/A"
    is_watchlist = wl_row is not None
    target_price = safe_float(wl_row["target_price"]) if wl_row else None
    stop_loss = safe_float(wl_row["stop_loss"]) if wl_row else None
    notes = wl_row["notes"] if wl_row else None

    latest_close = safe_float(ohlcv_row["close"], 2)

    sma20 = safe_float(factors_row["sma_20"], 2) if factors_row else None
    sma50 = safe_float(factors_row["sma_50"], 2) if factors_row else None
    sma200 = safe_float(factors_row["sma_200"], 2) if factors_row else None
    ret1d = safe_float(factors_row["ret_1d"], 4) if factors_row else 0.0

    dist_sma200 = None
    if latest_close is not None and sma200 is not None and sma200 > 0:
        dist_sma200 = round(((latest_close / sma200) - 1.0) * 100.0, 2)

    # Fetch 5 Most Recent Corporate Disclosures
    cur.execute(
        """
        SELECT disclosure_id, broadcast_timestamp, effective_session_date,
               category, subject, details_summary, source_url, verification_status,
               audit_status, dividend_declared, operating_margin_pct
        FROM corporate_disclosures
        WHERE symbol = ?
        ORDER BY broadcast_timestamp DESC LIMIT 5
        """,
        (sym,)
    )
    disc_rows = cur.fetchall()
    disclosures = []
    for d in disc_rows:
        disclosures.append({
            "disclosure_id": d["disclosure_id"],
            "broadcast_timestamp": d["broadcast_timestamp"],
            "effective_session_date": d["effective_session_date"],
            "category": d["category"] or "GENERAL",
            "subject": d["subject"] or "Corporate Disclosure",
            "details_summary": d["details_summary"],
            "source_url": d["source_url"],
            "verification_status": d["verification_status"] or "PENDING_VERIFICATION",
            "audit_status": d["audit_status"],
            "dividend_declared": safe_float(d["dividend_declared"], 2),
            "operating_margin_pct": safe_float(d["operating_margin_pct"], 2)
        })

    # Fetch Historical Daily Candlesticks (for lightweight-charts)
    cur.execute(
        """
        SELECT trading_date as time, open, high, low, close, volume 
        FROM ohlcv_daily 
        WHERE symbol = ? 
        ORDER BY trading_date ASC
        """,
        (sym,)
    )
    chart_rows = cur.fetchall()
    history = [
        {
            "time": r["time"],
            "open": safe_float(r["open"], 2),
            "high": safe_float(r["high"], 2),
            "low": safe_float(r["low"], 2),
            "close": safe_float(r["close"], 2),
            "volume": safe_int(r["volume"]) or 0
        }
        for r in chart_rows
    ]

    payload = {
        "symbol": sym,
        "company_name": company_name,
        "isin": isin,
        "sector": sector,
        "industry": industry,
        "is_watchlist": is_watchlist,
        "target_price": target_price,
        "stop_loss": stop_loss,
        "notes": notes,
        "as_of_date": ohlcv_row["trading_date"],
        "latest_ohlcv": {
            "trading_date": ohlcv_row["trading_date"],
            "open": safe_float(ohlcv_row["open"], 2),
            "high": safe_float(ohlcv_row["high"], 2),
            "low": safe_float(ohlcv_row["low"], 2),
            "close": latest_close,
            "volume": safe_int(ohlcv_row["volume"]) or 0
        },
        "technicals": {
            "ret_1d": ret1d,
            "ret_1d_pct": round(ret1d * 100.0, 2) if ret1d is not None else 0.0,
            "ret_5d": safe_float(factors_row["ret_5d"], 4) if factors_row else None,
            "ret_20d": safe_float(factors_row["ret_20d"], 4) if factors_row else None,
            "sma_20": sma20,
            "sma_50": sma50,
            "sma_200": sma200,
            "dist_sma200_pct": dist_sma200,
            "price_above_sma200": (latest_close > sma200) if (latest_close is not None and sma200 is not None) else False,
            "volatility_annualized": safe_float(factors_row["volatility_annualized"], 4) if factors_row else None,
            "beta_60d_nifty": safe_float(factors_row["beta_60d_nifty"], 2) if factors_row else None,
            "volume_ratio_20d": safe_float(factors_row["volume_ratio_20d"], 2) if factors_row else None,
            "volume_zscore_50d": safe_float(factors_row["volume_zscore_50d"], 2) if factors_row else None
        },
        "fundamentals": {
            "roe_pct": safe_float(factors_row["roe_pct"], 2) if factors_row else None,
            "debt_to_equity": safe_float(factors_row["debt_to_equity"], 4) if factors_row else None,
            "ttm_pe": safe_float(factors_row["ttm_pe"], 2) if factors_row else None,
            "opm_pct": safe_float(factors_row["opm_pct"], 2) if factors_row else None
        },
        "recent_disclosures": disclosures,
        "history": history
    }

    return sanitize_for_json(payload)


@router.get("/stocks/{symbol}/history")
@router.get("/api/v1/stocks/{symbol}/history")
def get_stock_history(
    symbol: str,
    limit: int = 500,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns time series OHLCV records for lightweight-charts candlestick rendering.
    """
    sym = symbol.upper().strip()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT trading_date as time, open, high, low, close, volume 
        FROM (
            SELECT trading_date, open, high, low, close, volume
            FROM ohlcv_daily 
            WHERE symbol = ? 
            ORDER BY trading_date DESC 
            LIMIT ?
        )
        ORDER BY trading_date ASC
        """,
        (sym, max(1, limit))
    )
    rows = cur.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail=f"No price history found for symbol '{sym}'.")

    history = [
        {
            "time": r["time"],
            "open": safe_float(r["open"], 2),
            "high": safe_float(r["high"], 2),
            "low": safe_float(r["low"], 2),
            "close": safe_float(r["close"], 2),
            "volume": safe_int(r["volume"]) or 0
        }
        for r in rows
    ]
    return sanitize_for_json(history)


@router.get("/stocks/{symbol}/forecast")
@router.get("/api/v1/stocks/{symbol}/forecast")
def get_stock_forecast(
    symbol: str,
    background_tasks: BackgroundTasks,
    horizon_days: int = Query(20, ge=1, le=60, description="Forecast horizon in trading days"),
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns walk-forward econometric price forecasts with GARCH(1,1) conditional volatility
    and Ornstein-Uhlenbeck mean-reverting drift projections (80% and 95% confidence fan cones).
    """
    sym = symbol.upper().strip()
    if not re.match(r"^[A-Z0-9&_\-]{1,20}$", sym):
        raise HTTPException(status_code=400, detail=f"Invalid symbol format: '{sym}'.")

    cur = conn.cursor()
    cur.execute("SELECT 1 FROM securities_master WHERE symbol = ?", (sym,))
    sec_row = cur.fetchone()

    cur.execute("SELECT 1 FROM user_watchlists WHERE symbol = ?", (sym,))
    wl_row = cur.fetchone()

    cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'", (sym,))
    ohlcv_count = cur.fetchone()[0]
    if ohlcv_count == 0:
        cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ?", (sym,))
        ohlcv_count = cur.fetchone()[0]

    # If unseeded or insufficient bars (< 126), trigger dynamic ingestion
    if not (sec_row or wl_row) or ohlcv_count < 126:
        resolver = SymbolResolver()
        try:
            resolver.resolve_symbol(sym)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{sym}' not found or not actively traded on NSE cash segment (series 'EQ')."
            )

        status_info = DynamicIngestionManager.get_ingestion_status(sym)
        if status_info.get("status") != "INGESTING":
            DynamicIngestionManager.update_ingestion_status(
                sym,
                status="INGESTING",
                progress_pct=25,
                step="QUEUED",
                detail="Symbol discovered. Ingesting historical series for econometric forecasting..."
            )
            background_tasks.add_task(run_dynamic_ingestion, sym)

        current_status = DynamicIngestionManager.get_ingestion_status(sym)
        return JSONResponse(
            status_code=202,
            content=sanitize_for_json({
                "status": "INGESTING",
                "symbol": sym,
                "message": "Symbol discovered. Ingesting historical series for econometric forecasting...",
                "progress_pct": current_status.get("progress_pct", 25),
                "step": current_status.get("step", "QUEUED")
            })
        )

    try:
        from src.quant.forecasting import EconometricForecaster
        forecaster = EconometricForecaster(DatabaseManager(DATABASE_PATH))
        forecast = forecaster.generate_forecast(sym, horizon_days=horizon_days)
        return sanitize_for_json(forecast)
    except Exception as e:
        logger.error(f"Econometric forecast error for {sym}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Econometric forecasting failed: {str(e)}")


@router.get("/stocks/{symbol}/news")
@router.get("/api/v1/stocks/{symbol}/news")
def get_stock_news(
    symbol: str,
    limit: int = Query(5, ge=1, le=20, description="Max news articles to return"),
    force_refresh: bool = Query(False, description="Bypass cache and fetch live RSS"),
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns real-time news articles with dual summary and directional impact assessment (Milestone B7.5).
    Cached up to 4 hours; automatically queries structured Google News RSS if stale or missing.
    """
    sym = symbol.upper().strip()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM securities_master WHERE symbol = ?", (sym,))
    sec_row = cur.fetchone()

    cur.execute("SELECT 1 FROM user_watchlists WHERE symbol = ?", (sym,))
    wl_row = cur.fetchone()

    if not (sec_row or wl_row):
        resolver = SymbolResolver()
        try:
            resolver.resolve_symbol(sym)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{sym}' not found in active universe or user watchlists."
            )

    try:
        from src.client.news_client import NewsClient
        client = NewsClient(DatabaseManager(DATABASE_PATH))
        raw_articles = client.fetch_latest_news(sym, limit=limit, force_refresh=force_refresh)

        articles = []
        for r in raw_articles:
            articles.append({
                "id": r["id"],
                "title": r["title"],
                "source": r.get("source", "Financial Media"),
                "published_at": r["published_at"],
                "article_url": r["article_url"],
                "summary": r.get("summary") or [],
                "impact": r.get("impact") or {
                    "direction": r.get("impact_direction", "NEUTRAL"),
                    "horizon": r.get("impact_horizon", "SHORT_TERM"),
                    "affected_drivers": r.get("impact_drivers", []),
                    "rationale": r.get("impact_rationale", ""),
                    "confidence_score": r.get("confidence_score", 1.0),
                }
            })

        return sanitize_for_json({
            "symbol": sym,
            "count": len(articles),
            "articles": articles
        })
    except Exception as e:
        logger.error(f"News retrieval error for {sym}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch news feed: {str(e)}")


__all__ = [
    "router",
    "market_router",
    "get_stock_status",
    "get_stock_tearsheet",
    "get_stock_history",
    "get_stock_forecast",
    "get_stock_news",
    "run_dynamic_ingestion",
]
