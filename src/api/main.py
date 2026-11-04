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
import sqlite3
import datetime
import logging
from typing import List, Dict, Any, Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Depends, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.storage.database import DatabaseManager
from src.quant.screener import FactorScreener
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
    run_dynamic_ingestion
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Market Intelligence Lab API",
    version="1.1.0",
    description="Local-first quantitative analytics & market terminal REST API."
)

# CORS Configuration
# Allow local Next.js frontend (localhost:3000) and any Vercel deployment preview/production URL
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
        "http://127.0.0.1:8000"
    ],
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount modular market routes (status, tearsheet, history)
app.include_router(market_router)


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


@app.get("/api/v1/screener")
def get_screener(
    min_roe: Optional[float] = Query(None, description="Minimum Return on Equity (%)"),
    max_de: Optional[float] = Query(None, description="Maximum Debt-to-Equity ratio"),
    price_above_sma200: Optional[bool] = Query(None, description="Filter for Price > 200-day SMA"),
    exclude_financials: bool = Query(False, description="Exclude Financial Services sector"),
    include_watchlists: bool = Query(True, description="Include onboarded user watchlists"),
    limit: int = Query(50, ge=1, le=100, description="Max results to return")
):
    """
    Returns top-ranked stocks from the latest trading session in quant_factors_daily
    sorted descending by composite Quality-Momentum score.
    Safely sanitizes all NaN / Infinity values to prevent serialization crashes.
    """
    try:
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
        df = screener.screen(
            as_of_date=latest_date,
            criteria=criteria if criteria else None,
            include_watchlists=include_watchlists
        )

        # Sanitize DataFrame replacing NaNs with None as specified in directive
        df_clean = df.where(pd.notnull(df), None)

        results = []
        for rank, (_, row) in enumerate(df_clean.head(limit).iterrows(), start=1):
            results.append({
                "rank": rank,
                "symbol": str(row["symbol"]),
                "company_name": str(row["company_name"]),
                "sector": str(row["sector"]),
                "close": safe_float(row.get("close"), 2),
                "sma_200": safe_float(row.get("sma_200"), 2),
                "debt_to_equity": safe_float(row.get("debt_to_equity"), 4),
                "roe_pct": safe_float(row.get("roe_pct"), 2),
                "opm_pct": safe_float(row.get("opm_pct"), 2),
                "excess_ret_20d": safe_float(row.get("excess_ret_20d"), 4),
                "composite_score": safe_float(row.get("composite_score"), 2),
                "price_above_sma200": bool(row.get("price_above_sma200", False)),
                "is_watchlist": bool(row.get("is_watchlist", 0))
            })

        return sanitize_for_json({
            "as_of_date": latest_date,
            "total_candidates": len(df),
            "returned_count": len(results),
            "results": results
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
    "run_dynamic_ingestion",
]
