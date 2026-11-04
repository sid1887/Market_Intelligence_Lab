"""
Market Intelligence Lab — FastAPI REST API Bridge.

Exposes local SQLite quantitative database (`data/market_lab.db`) via high-performance,
concurrency-safe read-only WAL connection endpoints:
- GET /api/v1/health: System status & latest market dates
- GET /api/v1/screener: Top ranked stocks based on composite Quality-Momentum score
- GET /api/v1/watchlist: Active user watchlist equities with real-time stats
- GET /api/v1/stocks/{symbol}/tearsheet: Complete tearsheet JSON payload
- GET /api/v1/stocks/{symbol}/history: Daily OHLCV candlestick series for lightweight-charts
"""

import os
import sqlite3
import datetime
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from src.storage.database import DatabaseManager
from src.quant.screener import FactorScreener

DATABASE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "market_lab.db")
)

app = FastAPI(
    title="Market Intelligence Lab API",
    version="1.0.0",
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


def get_db_connection():
    """
    Dependency that provides a safe read-only SQLite connection configured for concurrent WAL reads.
    Does not block concurrent writes or reader transactions.
    """
    db_uri = f"file:{DATABASE_PATH}?mode=ro"
    conn = sqlite3.connect(db_uri, uri=True, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


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
        return {
            "status": "healthy",
            "database": "connected (WAL mode)",
            "latest_ohlcv_date": latest_ohlcv,
            "latest_factors_date": latest_factors,
            "active_universe_count": active_count,
            "user_watchlist_count": watchlist_count,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
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
    """
    try:
        db = DatabaseManager(DATABASE_PATH)
        screener = FactorScreener(db)

        # 1. Determine latest trading date
        with db.get_connection() as conn:
            cur = conn.execute("SELECT MAX(trading_date) FROM quant_factors_daily")
            latest_date = cur.fetchone()[0]

        if not latest_date:
            return {"as_of_date": None, "total_count": 0, "results": []}

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

        results = []
        for rank, (_, row) in enumerate(df.head(limit).iterrows(), start=1):
            results.append({
                "rank": rank,
                "symbol": str(row["symbol"]),
                "company_name": str(row["company_name"]),
                "sector": str(row["sector"]),
                "close": round(float(row["close"]), 2) if row.get("close") is not None else None,
                "sma_200": round(float(row["sma_200"]), 2) if row.get("sma_200") is not None else None,
                "debt_to_equity": round(float(row["debt_to_equity"]), 4) if row.get("debt_to_equity") is not None else None,
                "roe_pct": round(float(row["roe_pct"]), 2) if row.get("roe_pct") is not None else None,
                "opm_pct": round(float(row["opm_pct"]), 2) if row.get("opm_pct") is not None else None,
                "excess_ret_20d": round(float(row["excess_ret_20d"]), 4) if row.get("excess_ret_20d") is not None else None,
                "composite_score": round(float(row["composite_score"]), 2) if row.get("composite_score") is not None else None,
                "price_above_sma200": bool(row.get("price_above_sma200", False)),
                "is_watchlist": bool(row.get("is_watchlist", 0))
            })

        return {
            "as_of_date": latest_date,
            "total_candidates": len(df),
            "returned_count": len(results),
            "results": results
        }
    except Exception as e:
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
            close_val = round(float(r["close"]), 2) if r["close"] is not None else None
            sma200_val = round(float(r["sma_200"]), 2) if r["sma_200"] is not None else None
            ret_1d_val = float(r["ret_1d"]) if r["ret_1d"] is not None else 0.0

            dist_sma200 = None
            if close_val is not None and sma200_val is not None and sma200_val > 0:
                dist_sma200 = round(((close_val / sma200_val) - 1.0) * 100.0, 2)

            watchlist.append({
                "symbol": r["symbol"],
                "company_name": r["company_name"],
                "sector": r["sector"],
                "target_price": r["target_price"],
                "stop_loss": r["stop_loss"],
                "notes": r["notes"],
                "added_date": r["added_date"],
                "trading_date": r["trading_date"],
                "close": close_val,
                "open": round(float(r["open"]), 2) if r["open"] is not None else None,
                "high": round(float(r["high"]), 2) if r["high"] is not None else None,
                "low": round(float(r["low"]), 2) if r["low"] is not None else None,
                "volume": int(r["volume"]) if r["volume"] is not None else None,
                "ret_1d": round(ret_1d_val, 4),
                "ret_1d_pct": round(ret_1d_val * 100.0, 2),
                "sma_20": round(float(r["sma_20"]), 2) if r["sma_20"] is not None else None,
                "sma_50": round(float(r["sma_50"]), 2) if r["sma_50"] is not None else None,
                "sma_200": sma200_val,
                "dist_sma200_pct": dist_sma200,
                "price_above_sma200": (close_val > sma200_val) if (close_val and sma200_val) else False,
                "volatility_annualized": round(float(r["volatility_annualized"]), 4) if r["volatility_annualized"] is not None else None,
                "beta_60d_nifty": round(float(r["beta_60d_nifty"]), 2) if r["beta_60d_nifty"] is not None else None,
                "ttm_pe": round(float(r["ttm_pe"]), 2) if r["ttm_pe"] is not None else None,
                "roe_pct": round(float(r["roe_pct"]), 2) if r["roe_pct"] is not None else None,
                "debt_to_equity": round(float(r["debt_to_equity"]), 4) if r["debt_to_equity"] is not None else None,
                "opm_pct": round(float(r["opm_pct"]), 2) if r["opm_pct"] is not None else None
            })

        return {
            "count": len(watchlist),
            "watchlist": watchlist
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Watchlist retrieval error: {str(e)}")


@app.get("/api/v1/stocks/{symbol}/tearsheet")
def get_stock_tearsheet(
    symbol: str,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns a unified JSON payload containing the stock's latest OHLCV,
    20/50/200 SMAs, fundamental ratios (ROE, D/E, TTM P/E), 5 most recent
    corporate disclosures, and historical candlestick bars for charting.
    """
    sym = symbol.upper().strip()
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

    if not sec_row and not wl_row:
        raise HTTPException(status_code=404, detail=f"Symbol '{sym}' not found in securities_master or user_watchlists.")

    company_name = (wl_row["company_name"] if wl_row else sec_row["company_name"]) or sym
    sector = (wl_row["sector"] if wl_row else sec_row["sector"]) or "General"
    industry = (sec_row["industry"] if sec_row else sector) or "General"
    isin = (sec_row["isin"] if sec_row else "N/A") or "N/A"
    is_watchlist = wl_row is not None
    target_price = wl_row["target_price"] if wl_row else None
    stop_loss = wl_row["stop_loss"] if wl_row else None
    notes = wl_row["notes"] if wl_row else None

    # 2. Fetch Latest OHLCV
    cur.execute(
        "SELECT * FROM ohlcv_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1",
        (sym,)
    )
    ohlcv_row = cur.fetchone()
    if not ohlcv_row:
        raise HTTPException(status_code=404, detail=f"No OHLCV trading bars found for '{sym}'.")

    latest_close = round(float(ohlcv_row["close"]), 2)

    # 3. Fetch Latest Quantitative Factors
    cur.execute(
        "SELECT * FROM quant_factors_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1",
        (sym,)
    )
    factors_row = cur.fetchone()

    sma20 = round(float(factors_row["sma_20"]), 2) if (factors_row and factors_row["sma_20"] is not None) else None
    sma50 = round(float(factors_row["sma_50"]), 2) if (factors_row and factors_row["sma_50"] is not None) else None
    sma200 = round(float(factors_row["sma_200"]), 2) if (factors_row and factors_row["sma_200"] is not None) else None
    ret1d = float(factors_row["ret_1d"]) if (factors_row and factors_row["ret_1d"] is not None) else 0.0

    dist_sma200 = None
    if sma200 and sma200 > 0:
        dist_sma200 = round(((latest_close / sma200) - 1.0) * 100.0, 2)

    # 4. Fetch 5 Most Recent Corporate Disclosures
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
            "dividend_declared": d["dividend_declared"],
            "operating_margin_pct": d["operating_margin_pct"]
        })

    # 5. Fetch Historical Daily Candlesticks (for lightweight-charts)
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
            "open": round(float(r["open"]), 2),
            "high": round(float(r["high"]), 2),
            "low": round(float(r["low"]), 2),
            "close": round(float(r["close"]), 2),
            "volume": int(r["volume"]) if r["volume"] is not None else 0
        }
        for r in chart_rows
    ]

    return {
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
            "open": round(float(ohlcv_row["open"]), 2),
            "high": round(float(ohlcv_row["high"]), 2),
            "low": round(float(ohlcv_row["low"]), 2),
            "close": latest_close,
            "volume": int(ohlcv_row["volume"]) if ohlcv_row["volume"] is not None else 0
        },
        "technicals": {
            "ret_1d": round(ret1d, 4),
            "ret_1d_pct": round(ret1d * 100.0, 2),
            "ret_5d": round(float(factors_row["ret_5d"]), 4) if (factors_row and factors_row["ret_5d"] is not None) else None,
            "ret_20d": round(float(factors_row["ret_20d"]), 4) if (factors_row and factors_row["ret_20d"] is not None) else None,
            "sma_20": sma20,
            "sma_50": sma50,
            "sma_200": sma200,
            "dist_sma200_pct": dist_sma200,
            "price_above_sma200": (latest_close > sma200) if sma200 else False,
            "volatility_annualized": round(float(factors_row["volatility_annualized"]), 4) if (factors_row and factors_row["volatility_annualized"] is not None) else None,
            "beta_60d_nifty": round(float(factors_row["beta_60d_nifty"]), 2) if (factors_row and factors_row["beta_60d_nifty"] is not None) else None,
            "volume_ratio_20d": round(float(factors_row["volume_ratio_20d"]), 2) if (factors_row and factors_row["volume_ratio_20d"] is not None) else None,
            "volume_zscore_50d": round(float(factors_row["volume_zscore_50d"]), 2) if (factors_row and factors_row["volume_zscore_50d"] is not None) else None
        },
        "fundamentals": {
            "roe_pct": round(float(factors_row["roe_pct"]), 2) if (factors_row and factors_row["roe_pct"] is not None) else None,
            "debt_to_equity": round(float(factors_row["debt_to_equity"]), 4) if (factors_row and factors_row["debt_to_equity"] is not None) else None,
            "ttm_pe": round(float(factors_row["ttm_pe"]), 2) if (factors_row and factors_row["ttm_pe"] is not None) else None,
            "opm_pct": round(float(factors_row["opm_pct"]), 2) if (factors_row and factors_row["opm_pct"] is not None) else None
        },
        "recent_disclosures": disclosures,
        "history": history
    }


@app.get("/api/v1/stocks/{symbol}/history")
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

    return [
        {
            "time": r["time"],
            "open": round(float(r["open"]), 2),
            "high": round(float(r["high"]), 2),
            "low": round(float(r["low"]), 2),
            "close": round(float(r["close"]), 2),
            "volume": int(r["volume"]) if r["volume"] is not None else 0
        }
        for r in rows
    ]
