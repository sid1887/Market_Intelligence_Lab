"""
Market Intelligence Lab — Market & Stocks API Router (Milestones B6.4 & B6.4.1).

Exposes routes for individual stock tearsheets, dynamic status polling, and historical bars:
- GET /stocks/{symbol}/status & GET /api/v1/stocks/{symbol}/status
- GET /stocks/{symbol}/tearsheet & GET /api/v1/stocks/{symbol}/tearsheet
- GET /stocks/{symbol}/history & GET /api/v1/stocks/{symbol}/history
"""

import re
import gc
import json
import sqlite3
import logging
import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Body
from fastapi.responses import JSONResponse

from src.storage.database import DatabaseManager
from src.client.symbol_resolver import SymbolResolver
from src.pipeline.dynamic_ingestion import DynamicIngestionManager, _INGESTION_STATE
from src.api.utils import get_db_connection, sanitize_for_json, safe_float, safe_int, DATABASE_PATH

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stocks"])
market_router = router

_CLOUD_INGEST_STATUS: Dict[str, Any] = {
    "status": "idle",
    "progress": 0,
    "total": 0,
    "message": "System ready"
}


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


@router.get("/rebalance/latest")
@router.get("/api/v1/rebalance/latest")
def get_latest_rebalance_proposal(
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns the latest multi-horizon portfolio rebalance proposal, trade deltas, and active horizon weights.
    """
    cur = conn.cursor()
    cur.execute("""
        SELECT proposal_id, session_date, model_composite_id, status, turnover_pct, projected_cost_bps,
               holdings_before_json, holdings_after_json, trade_deltas_json, created_at
        FROM rebalance_proposals
        ORDER BY session_date DESC, created_at DESC
        LIMIT 1
    """)
    row = cur.fetchone()
    if not row:
        return sanitize_for_json({
            "status": "NO_PROPOSAL",
            "message": "No rebalance proposal generated yet.",
            "proposal_id": None,
            "session_date": None,
            "trade_deltas": [],
            "effective_weights": {}
        })

    cur.execute("SELECT * FROM model_horizon_deployments ORDER BY horizon_days ASC")
    deployments = {r["horizon_days"]: dict(r) for r in cur.fetchall()}

    holdings_before = json.loads(row["holdings_before_json"]) if row["holdings_before_json"] else {}
    holdings_after = json.loads(row["holdings_after_json"]) if row["holdings_after_json"] else {}
    raw_trade_deltas = json.loads(row["trade_deltas_json"]) if row["trade_deltas_json"] else []

    # Map target_weight (decimal e.g. 0.0667) to target_allocation_pct (6.67) for frontend alignment
    trade_deltas = []
    for delta in raw_trade_deltas:
        d_dict = dict(delta)
        t_wt = safe_float(delta.get("target_weight"), 4) or 0.0
        c_wt = safe_float(delta.get("current_weight"), 4) or 0.0
        d_val = safe_float(delta.get("delta"), 4) or 0.0
        d_dict["target_allocation_pct"] = round(t_wt * 100.0, 2)
        d_dict["current_allocation_pct"] = round(c_wt * 100.0, 2)
        d_dict["delta_pct"] = round(d_val * 100.0, 2)
        trade_deltas.append(d_dict)

    active_horizons = [
        h for h, d in deployments.items() 
        if d.get("active_model_id") and float(d.get("validation_ic") or 0.0) >= 0.0150
    ]

    effective_weights = {
        "20D": 0.625 if 20 in active_horizons else 0.0,
        "60D": 0.375 if 60 in active_horizons else 0.0,
        "5D": 0.0
    }

    return sanitize_for_json({
        "proposal_id": row["proposal_id"],
        "session_date": row["session_date"],
        "model_composite_id": row["model_composite_id"],
        "status": row["status"],
        "turnover_pct": safe_float(row["turnover_pct"], 2),
        "projected_cost_bps": safe_float(row["projected_cost_bps"], 2),
        "holdings_before": holdings_before,
        "holdings_after": holdings_after,
        "holdings_after_pct": {k: round(v * 100.0, 2) for k, v in holdings_after.items()},
        "trade_deltas": trade_deltas,
        "active_horizons": active_horizons,
        "effective_weights": effective_weights,
        "created_at": row["created_at"]
    })


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
        "SELECT symbol, company_name, isin, industry, sector, COALESCE(is_nifty50, 0) as is_nifty50 FROM securities_master WHERE symbol = ?",
        (sym,)
    )
    sec_row = cur.fetchone()
    is_nifty50 = bool(sec_row["is_nifty50"]) if sec_row else False

    cur.execute(
        "SELECT company_name, sector, target_price, stop_loss, notes FROM user_watchlists WHERE symbol = ?",
        (sym,)
    )
    wl_row = cur.fetchone()

    # Check OHLCV presence and bar count (reading only necessary columns)
    cur.execute(
        "SELECT trading_date, open, high, low, close, volume FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ' ORDER BY trading_date DESC LIMIT 1",
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

    # If history is sparse (< 30 bars), attempt fast on-demand backfill via yfinance
    if ohlcv_count < 30:
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{sym}.NS")
            df = ticker.history(period="1y", auto_adjust=True, timeout=6)
            if not df.empty and len(df) >= 5:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                insert_rows = []
                for idx, row in df.iterrows():
                    t_date = idx.strftime("%Y-%m-%d")
                    insert_rows.append((
                        sym, t_date, 'EQ',
                        float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']),
                        float(row['Close']), float(row['Close']), int(row['Volume']),
                        float(row['Volume'] * row['Close']), 0, 'YFINANCE_DYNAMIC_BACKFILL',
                        now_iso, 0, 'final_settled', 'EXCHANGE_OFFICIAL', 0, 1, 1, 1
                    ))
                if insert_rows:
                    conn.executemany("""
                        INSERT OR REPLACE INTO ohlcv_daily (
                            symbol, trading_date, series, open, high, low, close, ltp, prev_close,
                            volume, turnover, delivery_qty, source, retrieval_timestamp, trades_count,
                            data_status, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                            is_eligible_for_backtest, is_eligible_for_training
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, insert_rows)
                    conn.commit()
                    cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'", (sym,))
                    ohlcv_count = cur.fetchone()[0]
                    cur.execute(
                        "SELECT trading_date, open, high, low, close, volume FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ' ORDER BY trading_date DESC LIMIT 1",
                        (sym,)
                    )
                    ohlcv_row = cur.fetchone()
        except Exception as e:
            logger.warning(f"On-demand tearsheet history fetch failed for {sym}: {e}")

    # Fallback to factors_daily if quant_factors_daily is missing
    if not factors_row:
        cur.execute(
            """
            SELECT symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200,
                   volatility_annualized, NULL as beta_60d_nifty, NULL as volume_ratio_20d, NULL as volume_zscore_50d,
                   NULL as roe_pct, NULL as debt_to_equity, NULL as ttm_pe, NULL as opm_pct
            FROM factors_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1
            """,
            (sym,)
        )
        factors_row = cur.fetchone()

    # Only trigger background ingestion if symbol has absolutely zero OHLCV records
    if not (sec_row or wl_row) or not ohlcv_row or ohlcv_count == 0:
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
        SELECT trading_date as time, open, high, low, close, volume,
               COALESCE(provenance_class, 'EXCHANGE_OFFICIAL') as provenance_class,
               COALESCE(is_synthetic, 0) as is_synthetic
        FROM ohlcv_daily 
        WHERE symbol = ? AND series = 'EQ'
          AND COALESCE(is_synthetic, 0) = 0
          AND COALESCE(is_eligible_for_live_analytics, 1) = 1
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
            "volume": safe_int(r["volume"]) or 0,
            "provenance_class": r["provenance_class"],
            "is_synthetic": bool(r["is_synthetic"])
        }
        for r in chart_rows
    ]

    payload = {
        "symbol": sym,
        "company_name": company_name,
        "isin": isin,
        "sector": sector,
        "industry": industry,
        "is_nifty50": is_nifty50,
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
    limit: int = 5000,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns time series OHLCV records for lightweight-charts candlestick rendering.
    """
    sym = symbol.upper().strip()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT trading_date as time, open, high, low, close, volume,
               COALESCE(provenance_class, 'EXCHANGE_OFFICIAL') as provenance_class,
               COALESCE(is_synthetic, 0) as is_synthetic
        FROM (
            SELECT trading_date, open, high, low, close, volume, provenance_class, is_synthetic
            FROM ohlcv_daily 
            WHERE symbol = ? AND series = 'EQ'
              AND COALESCE(is_synthetic, 0) = 0
              AND COALESCE(is_eligible_for_live_analytics, 1) = 1
            ORDER BY trading_date DESC 
            LIMIT ?
        )
        ORDER BY trading_date ASC
        """,
        (sym, max(1, limit))
    )
    rows = cur.fetchall()

    if len(rows) < 60:
        try:
            import yfinance as yf
            ticker = yf.Ticker(f"{sym}.NS")
            df = ticker.history(period="1y", auto_adjust=True, timeout=6)
            if not df.empty:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                insert_rows = []
                for idx, row in df.iterrows():
                    t_date = idx.strftime("%Y-%m-%d")
                    insert_rows.append((
                        sym, t_date, 'EQ',
                        float(row['Open']), float(row['High']), float(row['Low']), float(row['Close']),
                        float(row['Close']), float(row['Close']), int(row['Volume']),
                        float(row['Volume'] * row['Close']), 0, 'YFINANCE_DYNAMIC_BACKFILL',
                        now_iso, 0, 'final_settled', 'EXCHANGE_OFFICIAL', 0, 1, 1, 1
                    ))
                if insert_rows:
                    conn.executemany("""
                        INSERT OR REPLACE INTO ohlcv_daily (
                            symbol, trading_date, series, open, high, low, close, ltp, prev_close,
                            volume, turnover, delivery_qty, source, retrieval_timestamp, trades_count,
                            data_status, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                            is_eligible_for_backtest, is_eligible_for_training
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, insert_rows)
                    conn.commit()
                    cur.execute(
                        """
                        SELECT trading_date as time, open, high, low, close, volume,
                               COALESCE(provenance_class, 'EXCHANGE_OFFICIAL') as provenance_class,
                               COALESCE(is_synthetic, 0) as is_synthetic
                        FROM (
                            SELECT trading_date, open, high, low, close, volume, provenance_class, is_synthetic
                            FROM ohlcv_daily 
                            WHERE symbol = ? AND series = 'EQ'
                              AND COALESCE(is_synthetic, 0) = 0
                              AND COALESCE(is_eligible_for_live_analytics, 1) = 1
                            ORDER BY trading_date DESC 
                            LIMIT ?
                        )
                        ORDER BY trading_date ASC
                        """,
                        (sym, max(1, limit))
                    )
                    rows = cur.fetchall()
        except Exception as e:
            logger.warning(f"On-demand Yahoo Finance history fetch failed for {sym}: {e}")

    if not rows:
        raise HTTPException(status_code=404, detail=f"No price history found for symbol '{sym}'.")

    history = [
        {
            "time": r["time"],
            "open": safe_float(r["open"], 2),
            "high": safe_float(r["high"], 2),
            "low": safe_float(r["low"], 2),
            "close": safe_float(r["close"], 2),
            "volume": safe_int(r["volume"]) or 0,
            "provenance_class": r["provenance_class"],
            "is_synthetic": bool(r["is_synthetic"])
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

        # GET request is strictly read-only (CQRS). No audit ledger mutations on read.
        return sanitize_for_json(forecast)
    except Exception as e:
        logger.error(f"Econometric forecast error for {sym}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Econometric forecasting failed: {str(e)}")


@router.get("/stocks/{symbol}/news")
@router.get("/api/v1/stocks/{symbol}/news")
@router.get("/news/{symbol}")
@router.get("/api/v1/news/{symbol}")
def get_stock_news(
    symbol: str,
    limit: int = Query(5, ge=1, le=20, description="Max news articles to return"),
    force_refresh: bool = Query(True, description="Bypass cache and fetch live RSS"),
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


# ====================================================================
# Milestone B8.0: Multi-Factor Strategy Backtest Endpoints
# ====================================================================

class BacktestRequest(BaseModel):
    strategy_name: str = Field("Quality_Momentum_Top10", description="Strategy identifier")
    start_date: str = Field("2024-01-01", description="Simulation start date (YYYY-MM-DD)")
    end_date: str = Field("2026-10-28", description="Simulation end date (YYYY-MM-DD)")
    initial_capital: float = Field(500000.0, ge=10000.0, description="Initial capital in INR")
    rebalance_frequency: str = Field("MONTHLY", description="'MONTHLY' or 'QUARTERLY'")
    top_n: int = Field(10, ge=5, le=20, description="Number of top securities to hold")
    weighting: str = Field("EQUAL_WEIGHT", description="'EQUAL_WEIGHT' or 'INVERSE_VOLATILITY'")
    slippage_bps: float = Field(5.0, ge=0.0, le=100.0, description="Slippage in basis points")


@router.post("/backtest/run")
@router.post("/api/v1/backtest/run")
def run_backtest_endpoint(raw_body: Dict[str, Any] = Body(...)):
    """
    Executes backtest:
    - If payload specifies 'strategy_mode' or 'rebalance_cadence', routes to Phase 9.0 systematic PortfolioBacktester.
    - Otherwise, routes to legacy single-strategy BacktestEngine.
    """
    if "strategy_mode" in raw_body or "rebalance_cadence" in raw_body:
        from src.api.routes_backtest import run_portfolio_backtest, PortfolioBacktestRequest
        return run_portfolio_backtest(PortfolioBacktestRequest(**raw_body))

    request = BacktestRequest(**raw_body)
    try:
        from src.quant.backtest_engine import BacktestEngine
        engine = BacktestEngine(DatabaseManager(DATABASE_PATH))
        result = engine.run_backtest(
            strategy_name=request.strategy_name,
            start_date=request.start_date,
            end_date=request.end_date,
            initial_capital=request.initial_capital,
            rebalance_frequency=request.rebalance_frequency,
            top_n=request.top_n,
            weighting=request.weighting,
            slippage_bps=request.slippage_bps,
            save_to_db=True
        )
        return sanitize_for_json(result)
    except Exception as e:
        logger.error(f"Backtest execution error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Backtest execution failed: {str(e)}")


@router.get("/backtest/latest")
@router.get("/api/v1/backtest/latest")
def get_latest_backtest():
    """
    Returns the most recent backtest run and equity curve from the ledger.
    Strictly read-only: does not trigger on-the-fly execution.
    """
    try:
        db = DatabaseManager(DATABASE_PATH)
        latest = db.get_latest_backtest_run()
        if latest:
            return sanitize_for_json(latest)

        return sanitize_for_json({
            "status": "NOT_RUN",
            "run": None,
            "message": "No backtest runs found. Execute backtest pipeline via POST /api/v1/backtest/run."
        })
    except Exception as e:
        logger.error(f"Latest backtest retrieval error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve latest backtest: {str(e)}")


@router.get("/stocks/{symbol}/memo")
@router.get("/api/v1/stocks/{symbol}/memo")
def get_investment_memo(symbol: str):
    """
    Returns the synthesized institutional Investment Decision Memo for the specified symbol.
    Integrates technical trend structure, point-in-time fundamentals, news sentiment,
    and walk-forward GARCH econometric cones into a definitive one-page tearsheet memo.
    """
    try:
        from src.explanation.decision_engine import InvestmentDecisionEngine
        engine = InvestmentDecisionEngine(DatabaseManager(DATABASE_PATH))
        memo = engine.generate_memo(symbol)
        return sanitize_for_json(memo)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        logger.error(f"Investment memo generation error for {symbol}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Memo generation failed: {str(e)}")


@router.get("/system/accuracy")
@router.get("/api/v1/system/accuracy")
def get_system_accuracy():
    """
    Returns compounding ML self-evaluation accuracy metrics across historical econometric
    confidence cone containment (80% & 95%) and post-catalyst return realizations.
    """
    try:
        from src.quant.feedback_evaluator import FeedbackEvaluator
        evaluator = FeedbackEvaluator(DatabaseManager(DATABASE_PATH))
        metrics = evaluator.get_accuracy_metrics()
        return sanitize_for_json(metrics)
    except Exception as e:
        logger.error(f"System accuracy metrics retrieval error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to retrieve accuracy metrics: {str(e)}")



def run_cloud_safe_ingestion() -> None:
    """
    Background worker for asynchronous market ingestion.
    In cloud lightweight mode, processes symbols in small batches (batch_size=25, max_workers=1)
    with garbage collection to maintain memory strictly under 300 MB on 512 MB containers.
    """
    global _CLOUD_INGEST_STATUS
    import gc
    from src.storage.hydration import is_cloud_lightweight_mode
    from src.pipeline.universe_ingestion import UniverseIngestionManager
    from src.tasks.catalyst_engine import catalyst_engine
    
    logger.info("Starting background cloud-safe market ingestion...")
    _CLOUD_INGEST_STATUS = {
        "status": "running",
        "progress": 0,
        "total": 0,
        "message": "Initializing cloud market ingestion..."
    }
    manager = UniverseIngestionManager(DATABASE_PATH)
    
    try:
        if is_cloud_lightweight_mode():
            # In cloud lightweight mode: prioritize Watchlist + Portfolio + Top-200 liquid equities
            with manager.db.get_connection() as conn:
                wl_rows = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM user_watchlists").fetchall()]
                pf_rows = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM portfolio_positions WHERE quantity > 0").fetchall()]
                top_rows = [r[0] for r in conn.execute("SELECT symbol FROM securities_master WHERE is_active = 1 AND (is_nifty50 = 1 OR tier = 'LARGE' OR tier = 'MID') LIMIT 200").fetchall()]
            
            priority_symbols = list(dict.fromkeys(wl_rows + pf_rows + top_rows))
            if not priority_symbols:
                priority_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "SUZLON", "TRIDENT"]
                
            total_symbols = len(priority_symbols)
            _CLOUD_INGEST_STATUS["total"] = total_symbols
            _CLOUD_INGEST_STATUS["message"] = f"Ingesting {total_symbols} priority equities in batches of 25..."
            logger.info(f"Cloud Lightweight Ingest: processing {total_symbols} priority symbols in batches of 25...")
            
            from src.data.universe_expander import ingest_symbols_parallel
            for i in range(0, total_symbols, 25):
                chunk = priority_symbols[i:i + 25]
                try:
                    ingest_symbols_parallel(manager.db, chunk, max_workers=1, chunk_size=25, period="5d")
                except Exception as e:
                    logger.warning(f"Batch {i//25 + 1} ingest partial: {e}")
                _CLOUD_INGEST_STATUS["progress"] = min(i + len(chunk), total_symbols)
                _CLOUD_INGEST_STATUS["message"] = f"Processed {min(i + len(chunk), total_symbols)}/{total_symbols} equities..."
                gc.collect()
                
            try:
                manager.pipeline.calculate_daily_factors(symbols=priority_symbols)
            except Exception as e:
                logger.warning(f"Priority factor calculation error: {e}")
        else:
            _CLOUD_INGEST_STATUS["message"] = "Executing full universe ingestion..."
            manager.execute_universe_ingestion()
            
        # Invalidate in-memory screener cache
        try:
            from src.api.main import invalidate_screener_cache
            invalidate_screener_cache()
        except Exception:
            pass
            
        # Scan for real-time catalysts and dispatch push
        try:
            catalyst_engine.run_intraday_scan()
        except Exception as e:
            logger.warning(f"Catalyst scan post-ingest error: {e}")
            
        _CLOUD_INGEST_STATUS = {
            "status": "completed",
            "progress": _CLOUD_INGEST_STATUS.get("total", 100),
            "total": _CLOUD_INGEST_STATUS.get("total", 100),
            "message": "Market ingestion completed successfully."
        }
        logger.info("Background market ingestion completed successfully.")
    except Exception as e:
        logger.error(f"Error in background market ingestion: {e}", exc_info=True)
        _CLOUD_INGEST_STATUS = {
            "status": "error",
            "progress": 0,
            "total": 0,
            "message": f"Ingestion error: {str(e)}"
        }
    finally:
        gc.collect()


@router.get("/ingest/status")
@router.get("/api/v1/ingest/status")
def get_ingest_status():
    """Returns dynamic market ingestion progress and status."""
    return sanitize_for_json(_CLOUD_INGEST_STATUS)


@router.post("/system/ingest", status_code=202)
@router.post("/api/v1/system/ingest", status_code=202)
@router.post("/ingest", status_code=202)
@router.post("/api/v1/ingest", status_code=202)
def trigger_system_ingest(
    background_tasks: BackgroundTasks,
    background: bool = Query(True, description="Run ingestion in background asynchronously"),
):
    """
    Executes non-blocking dynamic market ingestion.
    Returns 202 Accepted in < 100ms and executes sync asynchronously to prevent Render 502 timeouts.
    """
    from src.storage.hydration import is_cloud_lightweight_mode
    background_tasks.add_task(run_cloud_safe_ingestion)
    return sanitize_for_json({
        "status": "running",
        "job_id": "cloud-sync",
        "message": "Incremental market sync started in background.",
        "mode": "CLOUD_LIGHTWEIGHT_MODE" if is_cloud_lightweight_mode() else "FULL_UNIVERSE"
    })


__all__ = [
    "router",
    "market_router",
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
    "get_ingest_status",
]
