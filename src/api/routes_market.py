"""
Market Intelligence Lab — Market & Stocks API Router (Milestones B6.4 & B6.4.1).

Exposes routes for individual stock tearsheets, dynamic status polling, and historical bars:
- GET /stocks/{symbol}/status & GET /api/v1/stocks/{symbol}/status
- GET /stocks/{symbol}/tearsheet & GET /api/v1/stocks/{symbol}/tearsheet
- GET /stocks/{symbol}/history & GET /api/v1/stocks/{symbol}/history
"""

import os
import re
import gc
import json
import math
import sqlite3
import logging
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Query, Body, Response
from fastapi.responses import JSONResponse, StreamingResponse

from src.storage.database import DatabaseManager
from src.client.symbol_resolver import SymbolResolver
from src.pipeline.dynamic_ingestion import DynamicIngestionManager, _INGESTION_STATE
from src.api.utils import get_db_connection, sanitize_for_json, safe_float, safe_int, DATABASE_PATH

logger = logging.getLogger(__name__)

router = APIRouter(tags=["stocks"])
market_router = router

_CLOUD_INGEST_STATUS: Dict[str, Any] = {
    "status": "idle",        # "idle" | "running" | "completed" | "error"
    "stage": "READY",
    "progress": 0,
    "total": 0,
    "current_batch": 0,
    "total_batches": 0,
    "last_symbol": None,
    "started_at": None,
    "elapsed_sec": 0.0,
    "message": "System ready"
}


def sync_yfinance_history_for_symbol(sym: str) -> Optional[List[Dict[str, Any]]]:
    """
    On-demand helper to fetch 1y daily bars via yfinance.
    Uses DatabaseManager(DATABASE_PATH).get_connection() as write_conn to avoid readonly DB errors.
    Immediately updates ohlcv_daily and quant_factors_daily (ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200).
    Returns the list of candlestick dicts in memory even if SQLite write locks or fails.
    """
    try:
        import yfinance as yf
        ticker = yf.Ticker(f"{sym}.NS")
        df = ticker.history(period="1y", auto_adjust=True, timeout=6)
        if df.empty or len(df) < 5:
            return None

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        insert_rows = []
        candles = []
        for idx, row in df.iterrows():
            t_date = idx.strftime("%Y-%m-%d")
            c_open = float(row['Open'])
            c_high = float(row['High'])
            c_low = float(row['Low'])
            c_close = float(row['Close'])
            c_vol = int(row['Volume'])
            insert_rows.append((
                sym, t_date, 'EQ',
                c_open, c_high, c_low, c_close,
                c_close, c_close, c_vol,
                float(c_vol * c_close), 0, 'YFINANCE_DYNAMIC_BACKFILL',
                now_iso, 0, 'final_settled', 'THIRD_PARTY_PROXY', 0, 1, 1, 1
            ))
            candles.append({
                "time": t_date,
                "open": round(c_open, 2),
                "high": round(c_high, 2),
                "low": round(c_low, 2),
                "close": round(c_close, 2),
                "volume": c_vol,
                "provenance_class": "THIRD_PARTY_PROXY",
                "is_synthetic": False
            })

        # Calculate factors from df
        closes = df['Close'].tolist()
        ret_1d = (closes[-1] / closes[-2] - 1.0) if len(closes) >= 2 else 0.0
        ret_5d = (closes[-1] / closes[-6] - 1.0) if len(closes) >= 6 else None
        ret_20d = (closes[-1] / closes[-21] - 1.0) if len(closes) >= 21 else (ret_5d * 4.0 if ret_5d is not None else 0.0)
        sma_20 = float(df['Close'].tail(20).mean()) if len(closes) >= 20 else None
        sma_50 = float(df['Close'].tail(50).mean()) if len(closes) >= 50 else None
        sma_200 = float(df['Close'].tail(200).mean()) if len(closes) >= 200 else None
        latest_date = df.index[-1].strftime("%Y-%m-%d")

        try:
            with DatabaseManager(DATABASE_PATH).get_connection() as write_conn:
                write_conn.executemany("""
                    INSERT INTO ohlcv_daily (
                        symbol, trading_date, series, open, high, low, close, ltp, prev_close,
                        volume, turnover, delivery_qty, source, retrieval_timestamp, trades_count,
                        data_status, provenance_class, is_synthetic, is_eligible_for_live_analytics,
                        is_eligible_for_backtest, is_eligible_for_training
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, trading_date, series) DO UPDATE SET
                        open = excluded.open,
                        high = excluded.high,
                        low = excluded.low,
                        close = excluded.close,
                        ltp = excluded.ltp,
                        prev_close = excluded.prev_close,
                        volume = excluded.volume,
                        turnover = excluded.turnover,
                        source = CASE WHEN ohlcv_daily.provenance_class = 'EXCHANGE_OFFICIAL' THEN ohlcv_daily.source ELSE excluded.source END,
                        retrieval_timestamp = excluded.retrieval_timestamp,
                        data_status = excluded.data_status,
                        provenance_class = CASE WHEN ohlcv_daily.provenance_class = 'EXCHANGE_OFFICIAL' THEN ohlcv_daily.provenance_class ELSE excluded.provenance_class END,
                        delivery_qty = COALESCE(ohlcv_daily.delivery_qty, excluded.delivery_qty),
                        trades_count = COALESCE(ohlcv_daily.trades_count, excluded.trades_count),
                        is_synthetic = ohlcv_daily.is_synthetic,
                        is_eligible_for_live_analytics = ohlcv_daily.is_eligible_for_live_analytics,
                        is_eligible_for_backtest = ohlcv_daily.is_eligible_for_backtest,
                        is_eligible_for_training = ohlcv_daily.is_eligible_for_training
                    WHERE ohlcv_daily.data_status != 'final_settled' OR ohlcv_daily.source = 'YFINANCE_DYNAMIC_BACKFILL';
                """, insert_rows)

                write_conn.execute("""
                    INSERT INTO quant_factors_daily (
                        symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(symbol, trading_date) DO UPDATE SET
                        ret_1d=excluded.ret_1d,
                        ret_5d=excluded.ret_5d,
                        ret_20d=excluded.ret_20d,
                        sma_20=excluded.sma_20,
                        sma_50=excluded.sma_50,
                        sma_200=excluded.sma_200,
                        updated_at=excluded.updated_at
                """, (sym, latest_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200, now_iso))
                write_conn.commit()
                logger.info(f"Persisted on-demand 1y backfill for {sym} ({len(insert_rows)} candles).")
        except Exception as write_err:
            logger.warning(f"Failed to persist on-demand backfill to SQLite for {sym}: {write_err}")

        try:
            from src.storage.database import record_external_api_metric
            record_external_api_metric("yfinance", "Ticker.history", success=True, units=1, quota_source="free_unmetered")
        except Exception:
            pass

        return candles
    except Exception as e:
        try:
            from src.storage.database import record_external_api_metric
            record_external_api_metric("yfinance", "Ticker.history", success=False, units=1, error_msg=str(e)[:100], quota_source="free_unmetered")
        except Exception:
            pass
        logger.warning(f"On-demand yfinance fetch failed for {sym}: {e}")
        return None


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


@router.get("/stocks/{symbol}/stream")
@router.get("/api/v1/stocks/{symbol}/stream")
async def stream_stock_ingestion_status(
    symbol: str,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Streams Server-Sent Events (SSE) for on-demand ticker ingestion progress.
    Allows frontend clients to establish a reactive EventSource stream rather than aggressive polling.
    """
    import asyncio
    sym = symbol.upper().strip()

    async def event_generator():
        max_duration_sec = 60
        elapsed = 0
        last_step = None
        last_pct = -1

        while elapsed < max_duration_sec:
            active_jobs = getattr(DynamicIngestionManager, "_active_jobs", _INGESTION_STATE)
            if sym in active_jobs:
                job = active_jobs[sym]
                st = job.get("status")
                step = job.get("step")
                pct = job.get("progress_pct", 0)

                if step != last_step or pct != last_pct or elapsed % 5 == 0:
                    last_step = step
                    last_pct = pct
                    yield f"event: status\ndata: {json.dumps(job)}\n\n"

                if st in ("READY", "FAILED"):
                    break
            else:
                cur = conn.cursor()
                cur.execute("SELECT 1 FROM securities_master WHERE symbol = ?", (sym,))
                in_sec = cur.fetchone() is not None
                cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ?", (sym,))
                bars = cur.fetchone()[0]
                if in_sec and bars > 0:
                    ready_payload = {
                        "status": "READY",
                        "symbol": sym,
                        "progress_pct": 100,
                        "step": "READY",
                        "detail": f"Data fully populated ({bars} bars)."
                    }
                    yield f"event: status\ndata: {json.dumps(ready_payload)}\n\n"
                    break
                else:
                    idle_payload = {
                        "status": "NOT_STARTED",
                        "symbol": sym,
                        "progress_pct": 0,
                        "step": "NOT_STARTED",
                        "detail": "Awaiting ingestion trigger."
                    }
                    yield f"event: status\ndata: {json.dumps(idle_payload)}\n\n"
                    if elapsed >= 3:
                        break

            await asyncio.sleep(1.0)
            elapsed += 1

        yield "event: close\ndata: {}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


def _sanitize_price_continuity(candles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ensures chronological candles do not exhibit sudden artificial split/fixture cliffs (>35%)
    between historical merged archives and recent hot SQLite bars. If an unadjusted cliff is detected,
    back-adjusts earlier candles to match the post-action price level.
    """
    if len(candles) < 2:
        return candles

    std_ratios = [0.5, 0.2, 0.1, 0.333333, 0.25, 0.166667, 2.0, 5.0, 10.0, 3.0, 4.0, 6.0]

    for i in range(len(candles) - 1, 0, -1):
        curr = candles[i]
        prev = candles[i - 1]
        c_close = curr.get("close") or 0.0
        p_close = prev.get("close") or 0.0
        c_open = curr.get("open") or c_close

        if p_close <= 0 or c_close <= 0:
            continue

        jump = abs(c_close / p_close - 1.0)
        if jump > 0.35:
            raw_ratio = c_open / p_close if c_open > 0 else c_close / p_close
            ratio = raw_ratio
            for sr in std_ratios:
                if abs(raw_ratio - sr) / sr < 0.05:
                    ratio = sr
                    break

            for j in range(i):
                if candles[j].get("open") is not None:
                    candles[j]["open"] = round(candles[j]["open"] * ratio, 2)
                if candles[j].get("high") is not None:
                    candles[j]["high"] = round(candles[j]["high"] * ratio, 2)
                if candles[j].get("low") is not None:
                    candles[j]["low"] = round(candles[j]["low"] * ratio, 2)
                if candles[j].get("close") is not None:
                    candles[j]["close"] = round(candles[j]["close"] * ratio, 2)
                if candles[j].get("volume") is not None and candles[j]["volume"] > 0:
                    candles[j]["volume"] = int(round(candles[j]["volume"] / ratio))

    return candles


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

    # Fast 404 gate: If symbol is completely unknown to securities_master and user_watchlists, verify resolvable before doing any I/O
    if not (sec_row or wl_row):
        resolver = SymbolResolver()
        try:
            resolver.resolve_symbol(sym)
        except ValueError:
            raise HTTPException(
                status_code=404,
                detail=f"Symbol '{sym}' not found or not actively traded on NSE cash segment (series 'EQ')."
            )

    # Check OHLCV presence and bar count (reading only necessary columns)
    cur.execute(
        "SELECT trading_date, open, high, low, close, volume, turnover, delivery_qty FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ' ORDER BY trading_date DESC LIMIT 1",
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
               roe_pct, debt_to_equity, ttm_pe, opm_pct, distance_52w_high, distance_52w_low
        FROM quant_factors_daily WHERE symbol = ? ORDER BY trading_date DESC LIMIT 1
        """,
        (sym,)
    )
    factors_row = cur.fetchone()

    # If history is sparse (< 60 bars), attempt fast on-demand backfill via yfinance (write connection)
    in_memory_candles: Optional[List[Dict[str, Any]]] = None
    if ohlcv_count < 60:
        in_memory_candles = sync_yfinance_history_for_symbol(sym)
        if in_memory_candles:
            ohlcv_count = len(in_memory_candles)
            cur.execute(
                "SELECT trading_date, open, high, low, close, volume, turnover, delivery_qty FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ' ORDER BY trading_date DESC LIMIT 1",
                (sym,)
            )
            latest_row = cur.fetchone()
            if latest_row:
                ohlcv_row = latest_row

    # Fallback to factors_daily if quant_factors_daily is missing
    if not factors_row:
        try:
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
        except sqlite3.OperationalError:
            factors_row = None

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

    # Fetch Quarterly Financial Statements if available (revenue, EBITDA, net profit, EPS)
    quarterly_statements = []
    try:
        cur.execute(
            """
            SELECT period_end_date, filing_date, is_audited, revenue, ebitda, net_profit, eps, total_debt, total_equity, cash_flow_from_ops
            FROM financial_statements_quarterly
            WHERE symbol = ?
            ORDER BY period_end_date DESC
            LIMIT 8
            """,
            (sym,)
        )
        q_rows = cur.fetchall()
        for qr in q_rows:
            quarterly_statements.append({
                "period_end_date": qr["period_end_date"],
                "filing_date": qr["filing_date"],
                "is_audited": bool(qr["is_audited"]),
                "revenue": safe_float(qr["revenue"], 2),
                "ebitda": safe_float(qr["ebitda"], 2),
                "net_profit": safe_float(qr["net_profit"], 2),
                "eps": safe_float(qr["eps"], 2),
                "total_debt": safe_float(qr["total_debt"], 2),
                "total_equity": safe_float(qr["total_equity"], 2),
                "cash_flow_from_ops": safe_float(qr["cash_flow_from_ops"], 2)
            })
    except Exception as e:
        logger.debug(f"Quarterly statements fetch non-fatal: {e}")

    # Fetch Historical Daily Candlesticks (for lightweight-charts)
    if in_memory_candles:
        history = in_memory_candles
    else:
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

    # Merge cold historical candlesticks from .milz archive if available (< 3ms seek)
    milz_archive_path = Path("data/archive/bhavcopy_10y.milz")
    if milz_archive_path.exists():
        try:
            from src.storage.compression_engine import MilzArchiveEngine
            archive_engine = MilzArchiveEngine(milz_archive_path)
            milz_df = archive_engine.load_symbol_history(sym)
            if not milz_df.empty:
                merged_map: Dict[str, Dict[str, Any]] = {}
                for _, mrow in milz_df.iterrows():
                    t_str = str(mrow["trading_date"])[:10]
                    merged_map[t_str] = {
                        "time": t_str,
                        "open": safe_float(mrow["open"], 2),
                        "high": safe_float(mrow["high"], 2),
                        "low": safe_float(mrow["low"], 2),
                        "close": safe_float(mrow["close"], 2),
                        "volume": safe_int(mrow["volume"]) or 0,
                        "provenance_class": "EXCHANGE_OFFICIAL",
                        "is_synthetic": False
                    }
                # SQLite candles overwrite / supplement milz
                for item in history:
                    t_str = str(item["time"])[:10]
                    merged_map[t_str] = item

                history = [merged_map[k] for k in sorted(merged_map.keys())]
        except Exception as e:
            logger.debug(f"Milz archive candle merge non-fatal: {e}")

    history = _sanitize_price_continuity(history)

    # ── Robust Independent Coalescing for Fundamental Ratios (ROE, D/E, TTM P/E, OPM) ──
    roe_pct = safe_float(factors_row["roe_pct"], 2) if factors_row and factors_row["roe_pct"] is not None else None
    debt_to_equity = safe_float(factors_row["debt_to_equity"], 4) if factors_row and factors_row["debt_to_equity"] is not None else None
    ttm_pe = safe_float(factors_row["ttm_pe"], 2) if factors_row and factors_row["ttm_pe"] is not None else None
    opm_pct = safe_float(factors_row["opm_pct"], 2) if factors_row and factors_row["opm_pct"] is not None else None

    # Coalesce any missing metric independently from historical quant_factors_daily and fundamental_factors_daily
    if ttm_pe is None or ttm_pe <= 0:
        cur.execute(
            "SELECT ttm_pe FROM quant_factors_daily WHERE symbol = ? AND ttm_pe IS NOT NULL AND ttm_pe > 0 ORDER BY trading_date DESC LIMIT 1",
            (sym,)
        )
        r = cur.fetchone()
        if r and r[0] is not None:
            ttm_pe = safe_float(r[0], 2)
        else:
            cur.execute(
                "SELECT pe_ratio FROM fundamental_factors_daily WHERE symbol = ? AND pe_ratio IS NOT NULL AND pe_ratio > 0 ORDER BY trading_date DESC LIMIT 1",
                (sym,)
            )
            r2 = cur.fetchone()
            if r2 and r2[0] is not None:
                ttm_pe = safe_float(r2[0], 2)

    if roe_pct is None:
        cur.execute(
            "SELECT roe_pct FROM quant_factors_daily WHERE symbol = ? AND roe_pct IS NOT NULL ORDER BY trading_date DESC LIMIT 1",
            (sym,)
        )
        r = cur.fetchone()
        if r and r[0] is not None:
            roe_pct = safe_float(r[0], 2)
        else:
            cur.execute(
                "SELECT roe_pct FROM fundamental_factors_daily WHERE symbol = ? AND roe_pct IS NOT NULL ORDER BY trading_date DESC LIMIT 1",
                (sym,)
            )
            r2 = cur.fetchone()
            if r2 and r2[0] is not None:
                roe_pct = safe_float(r2[0], 2)

    if debt_to_equity is None:
        cur.execute(
            "SELECT debt_to_equity FROM quant_factors_daily WHERE symbol = ? AND debt_to_equity IS NOT NULL ORDER BY trading_date DESC LIMIT 1",
            (sym,)
        )
        r = cur.fetchone()
        if r and r[0] is not None:
            debt_to_equity = safe_float(r[0], 4)
        else:
            cur.execute(
                "SELECT debt_to_equity FROM fundamental_factors_daily WHERE symbol = ? AND debt_to_equity IS NOT NULL ORDER BY trading_date DESC LIMIT 1",
                (sym,)
            )
            r2 = cur.fetchone()
            if r2 and r2[0] is not None:
                debt_to_equity = safe_float(r2[0], 4)

    if opm_pct is None:
        cur.execute(
            "SELECT opm_pct FROM quant_factors_daily WHERE symbol = ? AND opm_pct IS NOT NULL ORDER BY trading_date DESC LIMIT 1",
            (sym,)
        )
        r = cur.fetchone()
        if r and r[0] is not None:
            opm_pct = safe_float(r[0], 2)
        else:
            cur.execute(
                "SELECT operating_margin_ttm FROM fundamental_factors_daily WHERE symbol = ? AND operating_margin_ttm IS NOT NULL ORDER BY trading_date DESC LIMIT 1",
                (sym,)
            )
            r2 = cur.fetchone()
            if r2 and r2[0] is not None:
                opm_pct = safe_float(r2[0], 2)

    # Coalesce fundamental ratios from audited financial_statements_annual if still None
    if debt_to_equity is None or opm_pct is None or roe_pct is None:
        try:
            cur.execute(
                """
                SELECT total_debt, total_equity, ebitda, revenue, net_profit
                FROM financial_statements_annual
                WHERE symbol = ? AND total_equity IS NOT NULL AND total_equity > 0
                ORDER BY period_end_date DESC LIMIT 1
                """,
                (sym,)
            )
            fa_row = cur.fetchone()
            if fa_row:
                if debt_to_equity is None and fa_row["total_debt"] is not None and fa_row["total_equity"]:
                    debt_to_equity = round(float(fa_row["total_debt"]) / float(fa_row["total_equity"]), 4)
                if opm_pct is None and fa_row["ebitda"] is not None and fa_row["revenue"] and float(fa_row["revenue"]) > 0:
                    opm_pct = round(float(fa_row["ebitda"]) / float(fa_row["revenue"]) * 100.0, 2)
                if roe_pct is None and fa_row["net_profit"] is not None and fa_row["total_equity"] and float(fa_row["total_equity"]) > 0:
                    roe_pct = round(float(fa_row["net_profit"]) / float(fa_row["total_equity"]) * 100.0, 2)
        except Exception:
            pass

    # ── Robust Coalescing for Technical Volatility & Beta ──
    volatility_annualized = safe_float(factors_row["volatility_annualized"], 4) if factors_row and factors_row["volatility_annualized"] is not None else None
    beta_60d_nifty = safe_float(factors_row["beta_60d_nifty"], 2) if factors_row and factors_row["beta_60d_nifty"] is not None else None

    if volatility_annualized is None:
        cur.execute(
            """
            SELECT volatility_annualized
            FROM quant_factors_daily
            WHERE symbol = ? AND volatility_annualized IS NOT NULL
            ORDER BY trading_date DESC LIMIT 1
            """,
            (sym,)
        )
        vol_row = cur.fetchone()
        if vol_row and vol_row["volatility_annualized"] is not None:
            volatility_annualized = safe_float(vol_row["volatility_annualized"], 4)

    if beta_60d_nifty is None:
        cur.execute(
            """
            SELECT beta_60d_nifty
            FROM quant_factors_daily
            WHERE symbol = ? AND beta_60d_nifty IS NOT NULL
            ORDER BY trading_date DESC LIMIT 1
            """,
            (sym,)
        )
        beta_row = cur.fetchone()
        if beta_row and beta_row["beta_60d_nifty"] is not None:
            beta_60d_nifty = safe_float(beta_row["beta_60d_nifty"], 2)

    # If volatility_annualized is still None, compute 20D annualized volatility from the last 21 ohlcv_daily closes
    if volatility_annualized is None:
        cur.execute(
            """
            SELECT close FROM ohlcv_daily
            WHERE symbol = ? AND (series = 'EQ' OR series IS NULL OR series = '')
            ORDER BY trading_date DESC LIMIT 22
            """,
            (sym,)
        )
        close_rows = [r[0] for r in cur.fetchall() if r[0] is not None]
        if len(close_rows) >= 5:
            close_rows = list(reversed(close_rows))
            pct_changes = [(close_rows[i] / close_rows[i-1]) - 1.0 for i in range(1, len(close_rows))]
            if len(pct_changes) >= 4:
                mean_ret = sum(pct_changes) / len(pct_changes)
                variance = sum((x - mean_ret) ** 2 for x in pct_changes) / (len(pct_changes) - 1)
                daily_vol = math.sqrt(max(0.0, variance))
                volatility_annualized = round(daily_vol * math.sqrt(252), 4)

    # Fallback to merge exchange filings from equity_news_feed if corporate_disclosures is empty
    if len(disclosures) == 0:
        try:
            cur.execute(
                """
                SELECT id, title, published_at, article_url, source
                FROM equity_news_feed
                WHERE symbol = ? AND (source LIKE '%BSE%' OR source LIKE '%NSE%' OR title LIKE '%filing%' OR title LIKE '%disclosure%')
                ORDER BY published_at DESC LIMIT 5
                """,
                (sym,)
            )
            filing_rows = cur.fetchall()
            for fr in filing_rows:
                disclosures.append({
                    "disclosure_id": f"filing-{fr['id']}",
                    "broadcast_timestamp": fr["published_at"],
                    "effective_session_date": fr["published_at"][:10] if fr["published_at"] else "",
                    "category": "EXCHANGE_FILING",
                    "subject": fr["title"] or "Exchange Corporate Filing",
                    "details_summary": fr["title"],
                    "source_url": fr["article_url"],
                    "verification_status": "EXCHANGE_OFFICIAL",
                    "audit_status": "VERIFIED",
                    "dividend_declared": None,
                    "operating_margin_pct": None,
                })
        except Exception as e:
            logger.debug(f"Filing fallback non-fatal error for {sym}: {e}")

    # Attach Walk-Forward ML Forecast & Intraday Catalyst if available
    ml_forecast = None
    try:
        from src.quant.ml_trainer import WalkForwardMLTrainer
        trainer = WalkForwardMLTrainer(DatabaseManager(DATABASE_PATH))
        ml_forecast = trainer.predict_for_symbol(sym)
    except Exception as e:
        logger.debug(f"Tearsheet ML prediction non-fatal error for {sym}: {e}")
        ml_forecast = None

    catalyst = None
    try:
        cur.execute(
            """
            SELECT id, symbol, company_name, sector, move_pct, rvol, classification,
                   pillar1_price, pillar2_macro, pillar3_corp, pillar4_news,
                   causal_headline, causal_bullets, triggered_at
            FROM market_catalysts
            WHERE symbol = ?
            ORDER BY triggered_at DESC LIMIT 1
            """,
            (sym,)
        )
        cat_row = cur.fetchone()
        if cat_row:
            catalyst = dict(cat_row)
    except Exception as e:
        logger.debug(f"Tearsheet catalyst fetch non-fatal error for {sym}: {e}")
        catalyst = None

    ohlcv_vol = safe_int(ohlcv_row["volume"]) or 0
    ohlcv_turnover = safe_float(ohlcv_row["turnover"]) if "turnover" in ohlcv_row.keys() else None
    ohlcv_deliv_qty = safe_int(ohlcv_row["delivery_qty"]) if "delivery_qty" in ohlcv_row.keys() else None

    turnover_cr = round(ohlcv_turnover / 10000000.0, 2) if ohlcv_turnover else round(latest_close * ohlcv_vol / 10000000.0, 2)
    delivery_pct = round(ohlcv_deliv_qty / ohlcv_vol * 100.0, 2) if (ohlcv_deliv_qty and ohlcv_vol > 0) else None

    # Fall back to latest valid delivery session if current bar has no delivery info
    if delivery_pct is None:
        try:
            cur.execute(
                """
                SELECT delivery_qty, volume FROM ohlcv_daily
                WHERE symbol = ? AND delivery_qty > 0 AND volume > 0
                ORDER BY trading_date DESC LIMIT 1
                """,
                (sym,)
            )
            ld_row = cur.fetchone()
            if ld_row:
                delivery_pct = round(float(ld_row["delivery_qty"]) / float(ld_row["volume"]) * 100.0, 2)
                ohlcv_deliv_qty = safe_int(ld_row["delivery_qty"])
        except Exception:
            pass

    dist_52w_h = safe_float(factors_row["distance_52w_high"], 4) if factors_row and "distance_52w_high" in factors_row.keys() else None
    dist_52w_l = safe_float(factors_row["distance_52w_low"], 4) if factors_row and "distance_52w_low" in factors_row.keys() else None
    if dist_52w_h is not None:
        val = dist_52w_h * 100.0 if abs(dist_52w_h) <= 1.0 else dist_52w_h
        pct_from_52w_h = max(-100.0, min(0.0, round(val, 2)))
    elif latest_close is not None:
        try:
            cur.execute(
                """
                WITH recent_252 AS (
                    SELECT high, low FROM ohlcv_daily
                    WHERE symbol = ? AND series = 'EQ' AND COALESCE(is_synthetic, 0) = 0
                    ORDER BY trading_date DESC LIMIT 252
                )
                SELECT MAX(high) as high_52w, MIN(low) as low_52w FROM recent_252
                """,
                (sym,)
            )
            h_row = cur.fetchone()
            if h_row and h_row["high_52w"] and float(h_row["high_52w"]) > 0:
                h52 = float(h_row["high_52w"])
                pct_from_52w_h = max(-100.0, min(0.0, round(((latest_close - h52) / h52) * 100.0, 2)))
                dist_52w_h = pct_from_52w_h
            else:
                pct_from_52w_h = None
        except Exception:
            pct_from_52w_h = None
    else:
        pct_from_52w_h = None

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
            "volume": ohlcv_vol,
            "delivery_qty": ohlcv_deliv_qty,
            "delivery_pct": delivery_pct,
            "turnover_cr": turnover_cr
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
            "volatility_annualized": volatility_annualized,
            "beta_60d_nifty": beta_60d_nifty,
            "volume_ratio_20d": safe_float(factors_row["volume_ratio_20d"], 2) if factors_row else None,
            "volume_zscore_50d": safe_float(factors_row["volume_zscore_50d"], 2) if factors_row else None,
            "delivery_pct": delivery_pct,
            "turnover_cr": turnover_cr,
            "distance_52w_high": dist_52w_h,
            "distance_52w_low": dist_52w_l,
            "pct_from_52w_high": pct_from_52w_h
        },
        "fundamentals": {
            "roe_pct": roe_pct,
            "debt_to_equity": debt_to_equity,
            "ttm_pe": ttm_pe,
            "opm_pct": opm_pct
        },
        "ml_forecast": ml_forecast,
        "catalyst": catalyst,
        "recent_disclosures": disclosures,
        "quarterly_statements": quarterly_statements,
        "history": history
    }

    return sanitize_for_json(payload)


@router.get("/stocks/{symbol}/quarterly")
@router.get("/api/v1/stocks/{symbol}/quarterly")
def get_stock_quarterly_statements(
    symbol: str,
    limit: int = 12,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """Returns historical quarterly financial statement records (revenue, EBITDA, net profit, EPS) for an equity."""
    sym = symbol.upper().strip()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT period_end_date, filing_date, is_audited, revenue, ebitda, net_profit, eps, total_debt, total_equity, cash_flow_from_ops
        FROM financial_statements_quarterly
        WHERE symbol = ?
        ORDER BY period_end_date DESC
        LIMIT ?
        """,
        (sym, max(1, limit))
    )
    rows = cur.fetchall()
    return sanitize_for_json([
        {
            "period_end_date": r["period_end_date"],
            "filing_date": r["filing_date"],
            "is_audited": bool(r["is_audited"]),
            "revenue": safe_float(r["revenue"], 2),
            "ebitda": safe_float(r["ebitda"], 2),
            "net_profit": safe_float(r["net_profit"], 2),
            "eps": safe_float(r["eps"], 2),
            "total_debt": safe_float(r["total_debt"], 2),
            "total_equity": safe_float(r["total_equity"], 2),
            "cash_flow_from_ops": safe_float(r["cash_flow_from_ops"], 2)
        }
        for r in rows
    ])


@router.get("/stocks/{symbol}/history")
@router.get("/api/v1/stocks/{symbol}/history")
def get_stock_history(
    symbol: str,
    limit: int = 10000,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns time series OHLCV records for lightweight-charts candlestick rendering.
    """
    sym = symbol.upper().strip()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ' AND COALESCE(is_synthetic, 0) = 0", (sym,))
    ohlcv_total_count = cur.fetchone()[0]

    if ohlcv_total_count < 60:
        sync_yfinance_history_for_symbol(sym)

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

    # Merge cold historical candlesticks from .milz archive if available (< 3ms seek)
    milz_archive_path = Path("data/archive/bhavcopy_10y.milz")
    if milz_archive_path.exists():
        try:
            from src.storage.compression_engine import MilzArchiveEngine
            archive_engine = MilzArchiveEngine(milz_archive_path)
            milz_df = archive_engine.load_symbol_history(sym)
            if not milz_df.empty:
                merged_map: Dict[str, Dict[str, Any]] = {}
                for _, mrow in milz_df.iterrows():
                    t_str = str(mrow["trading_date"])[:10]
                    merged_map[t_str] = {
                        "time": t_str,
                        "open": safe_float(mrow["open"], 2),
                        "high": safe_float(mrow["high"], 2),
                        "low": safe_float(mrow["low"], 2),
                        "close": safe_float(mrow["close"], 2),
                        "volume": safe_int(mrow["volume"]) or 0,
                        "provenance_class": "EXCHANGE_OFFICIAL",
                        "is_synthetic": False
                    }
                # SQLite candles overwrite / supplement milz
                for item in history:
                    t_str = str(item["time"])[:10]
                    merged_map[t_str] = item

                history = [merged_map[k] for k in sorted(merged_map.keys())]
        except Exception as e:
            logger.debug(f"Milz archive candle merge in history non-fatal: {e}")

    history = _sanitize_price_continuity(history)
    if limit and len(history) > limit:
        history = history[-limit:]

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

        # Check existing cached article count in SQLite
        cur.execute("SELECT COUNT(*) FROM equity_news_feed WHERE symbol = ?", (sym,))
        cached_count = cur.fetchone()[0]

        # On-demand live fetch if explicitly requested OR if symbol currently has 0 cached articles
        should_fetch_live = force_refresh or (cached_count == 0)
        raw_articles = client.fetch_latest_news(sym, limit=limit, days=14, force_refresh=should_fetch_live)

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


@router.get("/stocks/{symbol}/disclosures")
@router.get("/api/v1/stocks/{symbol}/disclosures")
def get_stock_disclosures(
    symbol: str,
    limit: int = Query(10, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """Returns recent corporate disclosures and exchange announcements for a symbol."""
    sym = symbol.upper().strip()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT disclosure_id, broadcast_timestamp, effective_session_date,
                   category, subject, details_summary, source_url, verification_status,
                   audit_status, dividend_declared, operating_margin_pct
            FROM corporate_disclosures
            WHERE symbol = ?
            ORDER BY broadcast_timestamp DESC LIMIT ?
            """,
            (sym, limit)
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

        # Fallback to equity_news_feed corporate filings if corporate_disclosures is empty
        if len(disclosures) == 0:
            cur.execute(
                """
                SELECT id, title, published_at, source_url
                FROM equity_news_feed
                WHERE symbol = ? AND (title LIKE '%Announcement%' OR title LIKE '%Board%' OR title LIKE '%Result%' OR title LIKE '%Dividend%')
                ORDER BY published_at DESC LIMIT ?
                """,
                (sym, limit)
            )
            for r in cur.fetchall():
                disclosures.append({
                    "disclosure_id": f"NEWS_{r['id']}",
                    "broadcast_timestamp": r["published_at"],
                    "effective_session_date": (r["published_at"] or "")[:10],
                    "category": "EXCHANGE_ANNOUNCEMENT",
                    "subject": r["title"],
                    "details_summary": r["title"],
                    "source_url": r["source_url"],
                    "verification_status": "VERIFIED_EXCHANGE_FEED",
                    "audit_status": "AUTO_INGESTED",
                    "dividend_declared": None,
                    "operating_margin_pct": None
                })

        return sanitize_for_json(disclosures)
    except Exception as e:
        logger.error(f"Disclosures retrieval error for {sym}: {e}", exc_info=True)
        return []


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



class IngestRequestBody(BaseModel):
    symbols: Optional[List[str]] = None


def _get_rss_mb() -> float:
    """Reads current process resident set size in megabytes from /proc/self/statm."""
    try:
        with open("/proc/self/statm", "r") as f:
            fields = f.read().split()
            rss_pages = int(fields[1])
            page_size = os.sysconf("SC_PAGE_SIZE")
            return (rss_pages * page_size) / (1024 * 1024)
    except Exception:
        return 0.0


def run_cloud_safe_ingestion(target_symbols: Optional[List[str]] = None) -> None:
    """
    Background worker for asynchronous market ingestion.
    Render OOM-Protected:
    1. If GITHUB_TOKEN / GH_PAT is present, dispatches 7GB runner cloud_ml_tournament.yml.
    2. Otherwise in CLOUD_LIGHTWEIGHT_MODE, caps to Watchlist + Portfolio + Top 25 Nifty (<=35 symbols).
    3. Halts gracefully if RSS crosses 320 MB to protect 512 MB Render instance.
    """
    global _CLOUD_INGEST_STATUS
    import sys
    import time
    import math
    import gc
    import requests
    import pandas as pd
    from src.storage.hydration import is_cloud_lightweight_mode
    from src.pipeline.universe_ingestion import UniverseIngestionManager
    from src.tasks.catalyst_engine import catalyst_engine
    
    t0 = time.time()
    started_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    logger.info("[CLOUD-INGEST] Starting background cloud-safe market ingestion...")
    sys.stdout.flush()

    # 1. Check for GitHub Actions Dispatch if configured on Render
    gh_token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_PAT")
    gh_repo = os.getenv("GITHUB_REPOSITORY", "sid1887/Market_Intelligence_Lab")
    if gh_token and not target_symbols:
        logger.info(f"[CLOUD-INGEST] GITHUB_TOKEN detected. Dispatching cloud_ml_tournament.yml on {gh_repo}...")
        dispatch_url = f"https://api.github.com/repos/{gh_repo}/actions/workflows/cloud_ml_tournament.yml/dispatches"
        try:
            gh_resp = requests.post(
                dispatch_url,
                headers={
                    "Authorization": f"Bearer {gh_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
                json={"ref": "main"},
                timeout=10
            )
            if gh_resp.status_code in (200, 204):
                _CLOUD_INGEST_STATUS.clear()
                _CLOUD_INGEST_STATUS.update({
                    "status": "completed",
                    "stage": "DISPATCHED_TO_GITHUB_ACTIONS",
                    "progress": 1,
                    "total": 1,
                    "started_at": started_iso,
                    "elapsed_sec": round(time.time() - t0, 1),
                    "message": "Full-universe ingestion dispatched to 7GB GitHub Actions runner successfully."
                })
                logger.info("[CLOUD-INGEST] Successfully triggered cloud_ml_tournament.yml via GitHub dispatch.")
                return
            else:
                logger.warning(f"[CLOUD-INGEST] GitHub dispatch returned HTTP {gh_resp.status_code}: {gh_resp.text[:200]}. Falling back to in-process lightweight ingest.")
        except Exception as dispatch_err:
            logger.warning(f"[CLOUD-INGEST] GitHub Actions dispatch failed: {dispatch_err}. Falling back to in-process lightweight ingest.")

    manager = UniverseIngestionManager(DATABASE_PATH)
    is_lightweight = is_cloud_lightweight_mode()
    
    try:
        if target_symbols and len(target_symbols) > 0:
            priority_symbols = [s.strip().upper() for s in target_symbols if s.strip()]
        else:
            with manager.db.get_connection() as conn:
                wl_rows = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM user_watchlists").fetchall()]
                pf_rows = [r[0] for r in conn.execute("SELECT DISTINCT symbol FROM portfolio_positions WHERE quantity > 0").fetchall()]
                
                if is_lightweight:
                    # In CLOUD_LIGHTWEIGHT_MODE without GitHub dispatch: strictly cap to Watchlist + Portfolio + Top 25 Liquid Nifty (<= 35 total)
                    nifty_rows = [r[0] for r in conn.execute("""
                        SELECT symbol FROM securities_master 
                        WHERE is_active = 1 AND is_nifty50 = 1
                        ORDER BY symbol ASC
                        LIMIT 25
                    """).fetchall()]
                    priority_symbols = list(dict.fromkeys(wl_rows + pf_rows + nifty_rows))[:35]
                else:
                    all_rows = [r[0] for r in conn.execute("""
                        SELECT symbol FROM securities_master 
                        WHERE is_active = 1 
                        ORDER BY is_nifty50 DESC, symbol ASC
                    """).fetchall()]
                    priority_symbols = list(dict.fromkeys(wl_rows + pf_rows + all_rows))

            if not priority_symbols:
                priority_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "SUZLON", "TRIDENT", "FEDERALBNK", "UNIONBANK"]

        total_symbols = len(priority_symbols)
        batch_size = 10 if is_lightweight else 150
        total_batches = math.ceil(total_symbols / batch_size)

        _CLOUD_INGEST_STATUS.clear()
        _CLOUD_INGEST_STATUS.update({
            "status": "running",
            "stage": "BATCH_SYNC",
            "progress": 0,
            "total": total_symbols,
            "current_batch": 0,
            "total_batches": total_batches,
            "last_symbol": None,
            "started_at": started_iso,
            "elapsed_sec": 0.0,
            "message": f"Ingesting {total_symbols} priority equities across {total_batches} batches..."
        })
        logger.info(f"[CLOUD-INGEST] Processing {total_symbols} symbols in {total_batches} batches of {batch_size} (lightweight={is_lightweight})...")
        sys.stdout.flush()
        
        from src.data.universe_expander import ingest_symbols_parallel
        for b_idx in range(total_batches):
            # Check RSS guard before each batch (skipped during unit testing)
            current_rss = _get_rss_mb()
            if current_rss > 320.0 and not os.environ.get("PYTEST_CURRENT_TEST"):
                logger.warning(f"[CLOUD-INGEST] RSS memory limit reached ({current_rss:.1f} MB > 320 MB limit). Halting batch ingestion gracefully to protect container.")
                break

            start_i = b_idx * batch_size
            chunk = priority_symbols[start_i:start_i + batch_size]
            done_count = min(start_i + len(chunk), total_symbols)
            
            logger.info(f"[CLOUD-INGEST] Batch {b_idx + 1}/{total_batches} ({len(chunk)} symbols: {chunk[0]}..{chunk[-1]}) — progress {done_count}/{total_symbols} — RSS: {current_rss:.1f} MB")
            sys.stdout.flush()

            try:
                ingest_symbols_parallel(manager.db, chunk, max_workers=2, chunk_size=len(chunk), period="5d")
            except Exception as e:
                logger.warning(f"[CLOUD-INGEST] Batch {b_idx + 1} partial failure: {e}")
                sys.stdout.flush()

            _CLOUD_INGEST_STATUS.update({
                "progress": done_count,
                "current_batch": b_idx + 1,
                "last_symbol": chunk[-1],
                "elapsed_sec": round(time.time() - t0, 1),
                "message": f"Batch {b_idx + 1}/{total_batches} • Synced {done_count}/{total_symbols} equities ({chunk[-1]})..."
            })
            gc.collect()

        # Fast SQL/Pandas calculation over last 250 bars of updated symbols
        _CLOUD_INGEST_STATUS["stage"] = "FACTOR_REFRESH"
        _CLOUD_INGEST_STATUS["message"] = "Calculating technical factors and 20D returns..."
        logger.info("[CLOUD-INGEST] Vectorized refresh of 20D returns & SMAs in quant_factors_daily...")
        sys.stdout.flush()

        try:
            with manager.db.get_connection() as conn:
                df = pd.read_sql_query("""
                    SELECT symbol, trading_date, close
                    FROM ohlcv_daily
                    WHERE series = 'EQ' AND trading_date >= (SELECT date(MAX(trading_date), '-400 days') FROM ohlcv_daily)
                    ORDER BY symbol, trading_date ASC
                """, conn)

            factor_updates = []
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            for sym, group in df.groupby("symbol"):
                if len(group) < 2:
                    continue
                group = group.tail(250)
                closes = group["close"].values
                dates = group["trading_date"].values
                ret_1d = (closes[-1] / closes[-2] - 1.0) if len(closes) >= 2 else 0.0
                ret_5d = (closes[-1] / closes[-6] - 1.0) if len(closes) >= 6 else None
                ret_20d = (closes[-1] / closes[-21] - 1.0) if len(closes) >= 21 else (ret_5d * 4.0 if ret_5d is not None else 0.0)
                sma_20 = float(closes[-20:].mean()) if len(closes) >= 20 else None
                sma_50 = float(closes[-50:].mean()) if len(closes) >= 50 else None
                sma_200 = float(closes[-200:].mean()) if len(closes) >= 200 else None
                factor_updates.append((sym, str(dates[-1]), ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200, now_iso))

            if factor_updates:
                with manager.db.get_connection() as conn:
                    conn.executemany("""
                        INSERT INTO quant_factors_daily (
                            symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(symbol, trading_date) DO UPDATE SET
                            ret_1d=excluded.ret_1d,
                            ret_5d=excluded.ret_5d,
                            ret_20d=excluded.ret_20d,
                            sma_20=excluded.sma_20,
                            sma_50=excluded.sma_50,
                            sma_200=excluded.sma_200,
                            updated_at=excluded.updated_at
                    """, factor_updates)
                    conn.commit()
                logger.info(f"[CLOUD-INGEST] Fast vectorized factors refreshed for {len(factor_updates)} symbols.")
                sys.stdout.flush()
        except Exception as fe:
            logger.warning(f"[CLOUD-INGEST] Fast factor calculation error: {fe}")
            sys.stdout.flush()

        # Invalidate in-memory screener cache
        try:
            from src.api.main import invalidate_screener_cache
            invalidate_screener_cache()
        except Exception:
            pass
            
        # Scan for real-time catalysts and dispatch burst-capped push (max 2 individual + 1 digest)
        try:
            catalyst_engine.run_intraday_scan(max_push_alerts=2)
        except Exception as e:
            logger.warning(f"Catalyst scan post-ingest error: {e}")
            
        elapsed = round(time.time() - t0, 1)
        _CLOUD_INGEST_STATUS.clear()
        _CLOUD_INGEST_STATUS.update({
            "status": "completed",
            "stage": "COMPLETED",
            "progress": total_symbols,
            "total": total_symbols,
            "current_batch": total_batches,
            "total_batches": total_batches,
            "last_symbol": priority_symbols[-1] if priority_symbols else None,
            "started_at": started_iso,
            "elapsed_sec": elapsed,
            "message": f"Market ingestion completed successfully in {elapsed}s."
        })
        logger.info(f"[CLOUD-INGEST] Completed in {elapsed}s across {total_symbols} symbols.")
        sys.stdout.flush()
    except Exception as e:
        logger.error(f"[CLOUD-INGEST] Fatal error in market ingestion: {e}", exc_info=True)
        sys.stdout.flush()
        _CLOUD_INGEST_STATUS.clear()
        _CLOUD_INGEST_STATUS.update({
            "status": "error",
            "stage": "ERROR",
            "progress": 0,
            "total": 0,
            "current_batch": 0,
            "total_batches": 0,
            "last_symbol": None,
            "started_at": started_iso,
            "elapsed_sec": round(time.time() - t0, 1),
            "message": f"Ingestion error: {str(e)}"
        })
    finally:
        gc.collect()


@router.get("/ingest/status")
@router.get("/api/v1/ingest/status")
def get_ingest_status():
    """Returns dynamic market ingestion progress and status."""
    st = dict(_CLOUD_INGEST_STATUS)
    st["is_running"] = (st.get("status") == "running")
    st["processed_symbols"] = st.get("progress", 0)
    st["latest_symbol"] = st.get("last_symbol")
    return sanitize_for_json(st)


@router.post("/system/ingest")
@router.post("/api/v1/system/ingest")
@router.post("/ingest")
@router.post("/api/v1/ingest")
def trigger_system_ingest(
    response: Response,
    background_tasks: BackgroundTasks,
    payload: Optional[IngestRequestBody] = None,
    background: bool = Query(True, description="Run ingestion in background asynchronously"),
):
    """
    Executes dynamic market ingestion.
    If background=False, runs synchronously and returns 200 OK.
    If background=True, returns 202 Accepted in < 100ms.
    Guards against duplicate concurrent runs.
    """
    global _CLOUD_INGEST_STATUS
    from src.storage.hydration import is_cloud_lightweight_mode

    if not background:
        from src.pipeline.universe_ingestion import UniverseIngestionManager
        mgr = UniverseIngestionManager()
        target_syms = payload.symbols if payload else None
        res = mgr.execute_universe_ingestion()
        response.status_code = 200
        return sanitize_for_json(res)

    if _CLOUD_INGEST_STATUS.get("status") == "running":
        response.status_code = 202
        return sanitize_for_json({
            **_CLOUD_INGEST_STATUS,
            "job_id": "cloud-sync",
            "message": "Market ingestion job is already running."
        })

    target_syms = payload.symbols if payload else None
    background_tasks.add_task(run_cloud_safe_ingestion, target_symbols=target_syms)
    response.status_code = 202
    return sanitize_for_json({
        "status": "running",
        "job_id": "cloud-sync",
        "message": "Incremental market sync started in background.",
        "mode": "TARGET_SYMBOLS" if target_syms else ("CLOUD_LIGHTWEIGHT_MODE" if is_cloud_lightweight_mode() else "FULL_UNIVERSE")
    })


@router.get("/stocks/{symbol}/bundle")
@router.get("/api/v1/stocks/{symbol}/bundle")
def get_stock_bundle(
    symbol: str,
    background_tasks: BackgroundTasks,
    horizon_days: int = Query(20, ge=1, le=60, description="Forecast horizon"),
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Returns tearsheet, forecast, memo, and news in a single unified JSON payload.
    Reuses connection and executes on-demand yfinance backfill once if ohlcv_count < 60.
    """
    sym = symbol.upper().strip()
    if not re.match(r"^[A-Z0-9&_\-]{1,20}$", sym):
        raise HTTPException(status_code=400, detail=f"Invalid symbol format: '{sym}'.")

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'", (sym,))
    ohlcv_count = cur.fetchone()[0]

    if ohlcv_count < 60:
        sync_yfinance_history_for_symbol(sym)

    # 1. Tearsheet
    tearsheet = get_stock_tearsheet(sym, background_tasks, conn)
    if isinstance(tearsheet, JSONResponse):
        tearsheet_data = json.loads(tearsheet.body.decode("utf-8"))
    else:
        tearsheet_data = tearsheet

    # 2. Forecast
    forecast_data = None
    try:
        from src.quant.forecasting import EconometricForecaster
        forecaster = EconometricForecaster(DatabaseManager(DATABASE_PATH))
        forecast_data = forecaster.generate_forecast(sym, horizon_days=horizon_days)
    except Exception as e:
        logger.warning(f"Bundle forecast generation non-fatal error for {sym}: {e}")
        forecast_data = {"error": str(e), "cones": None}

    # 3. Investment Memo
    memo_data = None
    try:
        from src.explanation.decision_engine import InvestmentDecisionEngine
        engine = InvestmentDecisionEngine(DatabaseManager(DATABASE_PATH))
        memo_data = engine.generate_memo(sym)
    except Exception as e:
        logger.warning(f"Bundle memo generation non-fatal error for {sym}: {e}")
        memo_data = {"error": str(e), "memo": "Investment memo generation pending sufficient history."}

    # 4. News
    news_data = []
    try:
        news_data = get_stock_news(sym, limit=5, force_refresh=False, conn=conn)
    except Exception as e:
        logger.warning(f"Bundle news retrieval non-fatal error for {sym}: {e}")
        news_data = []

    ml_forecast = tearsheet_data.get("ml_forecast") if isinstance(tearsheet_data, dict) else None
    catalyst = tearsheet_data.get("catalyst") if isinstance(tearsheet_data, dict) else None

    return sanitize_for_json({
        "symbol": sym,
        "tearsheet": tearsheet_data,
        "forecast": forecast_data,
        "memo": memo_data,
        "news": news_data,
        "ml_forecast": ml_forecast,
        "catalyst": catalyst
    })


__all__ = [
    "router",
    "market_router",
    "get_stock_status",
    "get_stock_tearsheet",
    "get_stock_history",
    "get_stock_forecast",
    "get_stock_news",
    "get_stock_bundle",
    "run_backtest_endpoint",
    "get_latest_backtest",
    "get_investment_memo",
    "get_system_accuracy",
    "run_dynamic_ingestion",
    "trigger_system_ingest",
    "get_ingest_status",
]
