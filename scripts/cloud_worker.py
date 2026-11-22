#!/usr/bin/env python3
"""
scripts/cloud_worker.py
Decoupled High-Capacity Cloud Compute Worker (GitHub Actions / Kaggle 7GB Runners).

Modes:
  --mode news : 8-thread parallel Google News RSS fetch + 4-pillar causal anomaly detection (~85 priority equities)
  --mode ml   : Universe refresh + walk-forward ML tournament (5D, 20D, 60D) + 300-stock forecast precomputation
  --mode all  : Executes both news and ML tournament pipelines

Flags:
  --dry-run   : Executes pipelines locally without making remote POST sync requests
  --backend-url: URL of Render backend (defaults to RENDER_BACKEND_URL or http://127.0.0.1:8000)
  --token     : Secret token for X-Internal-Token header (defaults to INTERNAL_SYNC_TOKEN)
"""

import os
import sys
import time
import json
import argparse
import logging
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from concurrent.futures import ThreadPoolExecutor, as_completed

# Set project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import requests
import pandas as pd

from src.storage.database import DatabaseManager
from src.storage.hydration import hydrate_initial_cloud_database
from src.client.news_client import NewsClient
from src.tasks.catalyst_engine import CausalCatalystEngine
from src.quant.ml_trainer import WalkForwardMLTrainer
from src.data.universe_expander import ingest_symbols_parallel

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
logger = logging.getLogger("MIL.CloudWorker")


def get_default_backend_url() -> str:
    url = os.getenv("RENDER_API_URL") or os.getenv("RENDER_BACKEND_URL") or "http://127.0.0.1:8000"
    return url.rstrip("/")


def get_default_sync_token() -> str:
    return os.getenv("MIL_INTERNAL_SYNC_SECRET") or os.getenv("INTERNAL_SYNC_TOKEN", "")


def ensure_backend_awake(backend_url: str, max_retries: int = 3, timeout: int = 95) -> bool:
    """
    Pings backend health endpoint with retries and backoff to ensure Render container is awake.
    Handles Render free-tier cold starts (up to 60-90s).
    """
    if not backend_url or "127.0.0.1" in backend_url or "localhost" in backend_url:
        return True
    health_url = f"{backend_url.rstrip('/')}/api/v1/health"
    logger.info(f"Pinging backend health at {health_url} (cold-start wake verification)...")
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.get(health_url, timeout=timeout)
            if resp.status_code == 200:
                logger.info(f"Backend is awake and healthy (attempt {attempt}).")
                return True
            logger.warning(f"Health check attempt {attempt} returned HTTP {resp.status_code}. Retrying in 10s...")
        except Exception as e:
            logger.warning(f"Health check attempt {attempt} failed ({e}). Retrying in 10s...")
        if attempt < max_retries:
            time.sleep(10.0)
    logger.warning("Backend did not respond to health checks within retry window; proceeding.")
    return False


def _request_with_wake(
    method: str,
    url: str,
    backend_url: Optional[str] = None,
    max_retries: int = 3,
    **kwargs
) -> requests.Response:
    """
    Guarantees backend is awake before executing HTTP request, and retries with backoff if network/timeout fails.
    """
    base = backend_url or url.split("/api/v1")[0]
    ensure_backend_awake(base)
    timeout = kwargs.pop("timeout", 90)
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
            if resp.status_code in (200, 201):
                return resp
            logger.warning(f"{method} {url} returned HTTP {resp.status_code} on attempt {attempt}: {resp.text[:200]}")
            if resp.status_code >= 500 and attempt < max_retries:
                time.sleep(10.0)
                continue
            return resp
        except Exception as e:
            last_exc = e
            logger.warning(f"{method} {url} attempt {attempt} raised: {e}")
            if attempt < max_retries:
                time.sleep(10.0)
    if last_exc:
        raise last_exc
    raise RuntimeError(f"Request {method} {url} failed after {max_retries} attempts.")


def is_nse_market_hours() -> bool:
    """Checks whether current time is within NSE trading hours (Mon-Fri 09:15-15:30 IST)."""
    # IST is UTC+5:30
    ist_now = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=5, minutes=30)
    if ist_now.weekday() >= 5:  # Saturday or Sunday
        return False
    market_open = ist_now.replace(hour=9, minute=15, second=0, microsecond=0)
    market_close = ist_now.replace(hour=15, minute=30, second=0, microsecond=0)
    return market_open <= ist_now <= market_close


# ─────────────────────────────────────────────────────────────────────────────
# 1. DATABASE HYDRATION & STATE SYNC
# ─────────────────────────────────────────────────────────────────────────────

def bootstrap_worker_db(
    backend_url: str,
    token: str,
    db_path: str = "data/market_lab.db",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Initializes local SQLite DB, hydrates from cloud seed if needed,
    and pulls live watchlist/portfolio/OHLCV state from the backend.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    db = DatabaseManager(db_path)

    # Check if DB has baseline OHLCV records
    with db.get_connection() as conn:
        has_ohlcv = conn.execute("SELECT count(*) FROM sqlite_master WHERE type='table' AND name='ohlcv_daily'").fetchone()[0] > 0
        ohlcv_count = 0
        if has_ohlcv:
            ohlcv_count = conn.execute("SELECT count(*) FROM ohlcv_daily").fetchone()[0]

    if ohlcv_count == 0:
        seed_path = "data/cloud_seed_snapshot.json.gz"
        if os.path.exists(seed_path):
            logger.info(f"Hydrating empty worker database from {seed_path}...")
            hydrate_initial_cloud_database(db_path)
        else:
            logger.warning(f"No seed snapshot found at {seed_path}; proceeding with empty tables.")

    state: Dict[str, Any] = {
        "watchlist": [],
        "portfolio_symbols": [],
        "priority_symbols": [],
        "latest_ohlcv_date": None,
        "target_news_symbols": [],
        "target_ml_symbols": []
    }

    # Pull live state from Render Internal Bridge if credentials provided
    if backend_url and token:
        export_url = f"{backend_url}/api/v1/internal/export-state"
        logger.info(f"Pulling live state from backend: {export_url}...")
        try:
            resp = _request_with_wake(
                "GET",
                export_url,
                backend_url=backend_url,
                headers={
                    "X-Internal-Token": token,
                    "X-Internal-Sync-Secret": token,
                },
                timeout=95
            )
            if resp.status_code == 200:
                payload = resp.json()
                state["watchlist"] = payload.get("watchlist", [])
                state["portfolio_symbols"] = payload.get("portfolio_symbols", [])
                state["priority_symbols"] = payload.get("priority_symbols", [])
                state["latest_ohlcv_date"] = payload.get("latest_ohlcv_date")
                state["push_subscriptions"] = payload.get("push_subscriptions", [])
                recent_ohlcv = payload.get("recent_ohlcv", [])
                latest_funds = payload.get("latest_fundamentals", [])

                logger.info(
                    f"State successfully exported from backend: "
                    f"{len(state['watchlist'])} watchlist, "
                    f"{len(state['portfolio_symbols'])} portfolio, "
                    f"{len(state['priority_symbols'])} priority, "
                    f"{len(state.get('push_subscriptions', []))} push subscriptions, "
                    f"{len(recent_ohlcv)} recent OHLCV bars, "
                    f"{len(latest_funds)} fundamental records."
                )

                # Merge exported state into local DB
                with db.get_connection() as conn:
                    # 1. User watchlists
                    if state["watchlist"]:
                        wl_tuples = [
                            (
                                w["symbol"],
                                w.get("company_name", w["symbol"]),
                                w.get("sector", "General"),
                                datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                w.get("target_price"),
                                w.get("stop_loss"),
                            )
                            for w in state["watchlist"]
                        ]
                        conn.executemany("""
                            INSERT OR REPLACE INTO user_watchlists (
                                symbol, company_name, sector, added_date, target_price, stop_loss
                            ) VALUES (?, ?, ?, ?, ?, ?)
                        """, wl_tuples)

                    # 2. Recent OHLCV bars
                    if recent_ohlcv:
                        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        bar_tuples = [
                            (
                                b["symbol"],
                                b["trading_date"],
                                "EQ",
                                b["open"],
                                b["high"],
                                b["low"],
                                b["close"],
                                b.get("volume", 0),
                                "EXPORT_STATE",
                                now_iso,
                            )
                            for b in recent_ohlcv
                        ]
                        conn.executemany("""
                            INSERT OR IGNORE INTO ohlcv_daily (
                                symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, bar_tuples)

                    # 3. Latest fundamental metrics from Render (prevent overwriting fundamentals with NULL)
                    if latest_funds:
                        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                        for f in latest_funds:
                            conn.execute("""
                                UPDATE quant_factors_daily
                                SET roe_pct = COALESCE(?, roe_pct),
                                    opm_pct = COALESCE(?, opm_pct),
                                    debt_to_equity = COALESCE(?, debt_to_equity),
                                    ttm_pe = COALESCE(?, ttm_pe),
                                    eps_growth_yoy = COALESCE(?, eps_growth_yoy),
                                    updated_at = ?
                                WHERE symbol = ? AND trading_date = (SELECT MAX(trading_date) FROM quant_factors_daily WHERE symbol = ?)
                            """, (
                                f.get("roe_pct"),
                                f.get("opm_pct"),
                                f.get("debt_to_equity"),
                                f.get("ttm_pe"),
                                f.get("eps_growth_yoy"),
                                now_iso,
                                f["symbol"],
                                f["symbol"]
                            ))

                    conn.commit()
            else:
                logger.warning(f"Backend export-state returned HTTP {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            logger.warning(f"Failed to pull state from {export_url}: {e}")

    # Fallback / augment from local DB if empty
    with db.get_connection() as conn:
        if not state["watchlist"]:
            wl_rows = conn.execute("SELECT symbol, company_name, sector, target_price, stop_loss FROM user_watchlists").fetchall()
            state["watchlist"] = [
                {"symbol": r[0], "company_name": r[1], "sector": r[2], "target_price": r[3], "stop_loss": r[4]}
                for r in wl_rows
            ]

        if not state["portfolio_symbols"]:
            pf_rows = conn.execute("SELECT DISTINCT symbol FROM portfolio_positions WHERE quantity > 0").fetchall()
            state["portfolio_symbols"] = [r[0] for r in pf_rows if r[0]]

        if not state["priority_symbols"]:
            top_rows = conn.execute("""
                SELECT symbol FROM securities_master 
                WHERE is_active = 1 
                ORDER BY is_nifty50 DESC, symbol ASC 
                LIMIT 250
            """).fetchall()
            state["priority_symbols"] = [r[0] for r in top_rows if r[0]]

        # Fetch all active equities from securities_master for full-universe coverage
        all_active_rows = conn.execute("""
            SELECT symbol FROM securities_master 
            WHERE is_active = 1 
            ORDER BY is_nifty50 DESC, symbol ASC
        """).fetchall()
        all_active_symbols = [r[0] for r in all_active_rows if r[0]]

    # Compute target lists
    wl_syms = [w["symbol"] for w in state["watchlist"]]
    pf_syms = state["portfolio_symbols"]
    prio_syms = state["priority_symbols"]

    # Target news symbols: watchlist + portfolio + top 75 liquid equities (~85 total)
    state["target_news_symbols"] = list(dict.fromkeys(wl_syms + pf_syms + prio_syms[:75]))

    # Target ML symbols: full active universe (1,000+ equities) prioritized by watchlist + portfolio + active universe
    state["target_ml_symbols"] = list(dict.fromkeys(wl_syms + pf_syms + all_active_symbols))
    if not state["target_ml_symbols"]:
        state["target_ml_symbols"] = list(dict.fromkeys(wl_syms + pf_syms + prio_syms))

    logger.info(
        f"Worker Bootstrap Complete: {len(state['target_news_symbols'])} target news symbols, "
        f"{len(state['target_ml_symbols'])} target ML symbols."
    )
    return state


# ─────────────────────────────────────────────────────────────────────────────
# 2. 8-THREAD PARALLEL NEWS & CAUSAL RADAR
# ─────────────────────────────────────────────────────────────────────────────

def _fetch_single_symbol_news(
    symbol: str,
    idx: int,
    db: DatabaseManager
) -> List[Dict[str, Any]]:
    """Fetches news for a single symbol with rate-limit stagger."""
    time.sleep((idx % 8) * 0.2)  # Stagger concurrent requests
    try:
        client = NewsClient(db)
        articles = client.fetch_latest_news(symbol, limit=10, days=7, force_refresh=True)
        return articles
    except Exception as ex:
        logger.warning(f"Error fetching news for {symbol}: {ex}")
        return []


def run_parallel_news_pipeline(
    state: Dict[str, Any],
    backend_url: str,
    token: str,
    db_path: str = "data/market_lab.db",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Executes multi-source market-wide news & exchange filings aggregation
    (BSE Filings, NSE Filings, Direct Wire RSS, and Targeted Watchlist RSS)
    and runs the 4-pillar causal anomaly detection radar.
    """
    logger.info("=== STARTING MULTI-SOURCE NEWS & CAUSAL RADAR PIPELINE ===")
    t0 = time.time()
    db = DatabaseManager(db_path)

    # Priority watchlist + portfolio symbols for targeted deep coverage
    wl_syms = [w["symbol"] for w in state.get("watchlist", [])]
    pf_syms = state.get("portfolio_symbols", [])
    priority_symbols = list(dict.fromkeys(wl_syms + pf_syms))
    if not priority_symbols:
        priority_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "TATAMOTORS", "ITC", "BEL", "SBIN", "RVNL", "NHPC"]

    # 0. Fast 5d batch yfinance quote check on top 150 active equities to ensure fresh intraday price bars & RVOL
    quote_targets = list(dict.fromkeys(priority_symbols + state.get("priority_symbols", [])[:150]))[:150]
    if quote_targets:
        logger.info(f"Running fast 5d quote refresh for {len(quote_targets)} equities...")
        try:
            ingest_symbols_parallel(db, quote_targets, max_workers=6, chunk_size=25, period="5d")
        except Exception as e:
            logger.warning(f"Fast quote refresh error: {e}")

    logger.info(f"Triggering market-wide news & filings sweep (priority targets: {len(priority_symbols)})...")
    news_client = NewsClient(db)
    agg_result = news_client.fetch_market_wide_news_and_filings(priority_symbols=priority_symbols)

    counts = agg_result.get("counts", {})
    all_articles = agg_result.get("articles", [])

    logger.info(
        f"[NEWS-SYNC] BSE Filings: {counts.get('bse_filings', 0)} | "
        f"NSE Filings: {counts.get('nse_filings', 0)} | "
        f"Direct Wire (MC/ET/Mint): {counts.get('direct_wire', 0)} | "
        f"Watchlist RSS: {counts.get('watchlist_rss', 0)}"
    )

    # Run Causal Anomaly Detection across targets (worker never broadcasts push locally)
    logger.info("Running 4-Pillar Causal Catalyst Anomaly Radar...")
    catalyst_engine = CausalCatalystEngine(auto_push=False)
    detected_catalysts: List[Dict[str, Any]] = []

    target_symbols = state.get("target_news_symbols", priority_symbols)
    for sym in target_symbols:
        try:
            # Explicitly disable local push; push is dispatched remotely by Render on sync
            cat = catalyst_engine.investigate_symbol(sym, dispatch_push=False)
            if cat:
                detected_catalysts.append(cat)
        except Exception as e:
            logger.debug(f"Catalyst check error for {sym}: {e}")

    # During NSE Market Hours, run lightweight intraday price & volume anomaly scan
    if is_nse_market_hours():
        logger.info("[NEWS-RADAR] NSE Market Hours active (09:15-15:30 IST) -> Running intraday anomaly scan...")
        try:
            intraday_catalysts = catalyst_engine.run_intraday_scan(dispatch_push=False, max_push_alerts=2)
            for ic in intraday_catalysts:
                if not any(dc.get("symbol") == ic.get("symbol") for dc in detected_catalysts):
                    detected_catalysts.append(ic)
            logger.info(f"[NEWS-RADAR] Intraday scan detected {len(intraday_catalysts)} catalysts.")
        except Exception as ie:
            logger.warning(f"[NEWS-RADAR] Error running intraday catalyst scan: {ie}")

    logger.info(f"Causal Radar identified {len(detected_catalysts)} active catalysts.")

    # Extract any fresh OHLCV bars from 5d quote refresh
    fresh_news_bars = []
    try:
        with db.get_connection() as conn:
            max_d_row = conn.execute("SELECT MAX(trading_date) FROM ohlcv_daily").fetchone()
            if max_d_row and max_d_row[0]:
                max_d = max_d_row[0]
                cutoff_dt = datetime.datetime.strptime(max_d, "%Y-%m-%d") - datetime.timedelta(days=7)
                cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
                rows = conn.execute("""
                    SELECT symbol, trading_date, series, open, high, low, close, prev_close, volume
                    FROM ohlcv_daily
                    WHERE trading_date >= ? AND (series = 'EQ' OR series IS NULL)
                    ORDER BY symbol, trading_date
                """, (cutoff_str,)).fetchall()
                fresh_news_bars = [dict(r) for r in rows]
                logger.info(f"[NEWS-RADAR] Extracted {len(fresh_news_bars)} fresh OHLCV bars (>= {cutoff_str}) to sync to backend.")
    except Exception as bar_err:
        logger.warning(f"[NEWS-RADAR] Error extracting fresh OHLCV bars: {bar_err}")

    # Prepare sync payload (explicitly instruct Render backend to dispatch push for catalysts & breaking filings)
    has_catalysts = len(detected_catalysts) > 0
    has_articles = len(all_articles) > 0
    payload = {
        "news_articles": all_articles,
        "catalysts": detected_catalysts,
        "dispatch_push": True if (has_catalysts or has_articles) else False,
        "push_subscriptions": state.get("push_subscriptions", []),
        "ohlcv_bars": fresh_news_bars[:2500] if fresh_news_bars else None,
    }

    elapsed = round(time.time() - t0, 1)
    result = {
        "status": "completed",
        "elapsed_sec": elapsed,
        "symbols_processed": len(target_symbols),
        "articles_count": len(all_articles),
        "catalysts_count": len(detected_catalysts),
        "synced": False,
        "source_breakdown": counts
    }

    if dry_run:
        logger.info(f"[DRY-RUN] News pipeline finished in {elapsed}s. Skipping POST sync.")
        return result

    # POST to Render Internal Sync Bridge
    if backend_url and token:
        sync_url = f"{backend_url}/api/v1/internal/sync"
        logger.info(f"Syncing news & catalysts to backend: {sync_url}...")
        try:
            resp = _request_with_wake(
                "POST",
                sync_url,
                backend_url=backend_url,
                json=payload,
                headers={
                    "X-Internal-Token": token,
                    "X-Internal-Sync-Secret": token,
                    "Content-Type": "application/json",
                },
                timeout=95
            )
            if resp.status_code == 200:
                logger.info(f"Successfully synced news to backend: {resp.json()}")
                result["synced"] = True
                result["backend_response"] = resp.json()
            else:
                logger.error(f"Backend sync failed with HTTP {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            logger.error(f"Failed to post sync to {sync_url}: {e}")
    else:
        logger.warning("No backend_url or token provided; skipping sync.")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. WALK-FORWARD ML TOURNAMENT & 300-STOCK FORECAST PRECOMPUTATION
# ─────────────────────────────────────────────────────────────────────────────

def run_ml_tournament_pipeline(
    state: Dict[str, Any],
    backend_url: str,
    token: str,
    db_path: str = "data/market_lab.db",
    dry_run: bool = False
) -> Dict[str, Any]:
    """
    Refreshes latest daily bars, trains purged walk-forward ML models across
    5D, 20D, and 60D horizons, and precomputes multi-horizon alpha forecasts
    for up to 300 active equities.
    """
    logger.info("=== STARTING ML TOURNAMENT & FORECAST PRECOMPUTATION PIPELINE ===")
    t0 = time.time()
    db = DatabaseManager(db_path)
    target_symbols = state.get("target_ml_symbols", [])
    if not target_symbols:
        target_symbols = ["RELIANCE", "TCS", "HDFCBANK", "INFY", "TATAMOTORS", "ITC", "BEL", "SBIN", "RVNL", "NHPC"]

    # 0. Checkpoint-Driven 10-Year Bhavcopy Harvest & Full-Spectrum Enrichment
    logger.info("Executing incremental 10-year Bhavcopy harvest & .milz archive update...")
    try:
        from src.data.bhavcopy_harvester import Bhavcopy10YHarvester
        harvester = Bhavcopy10YHarvester(db)
        harvest_res = harvester.harvest_next_batch(max_sessions=60)
        logger.info(f"[ML-TOURNAMENT] Bhavcopy harvest batch completed: {harvest_res}")
        harvester.compute_intraday_microstructure_features(days=60)
    except Exception as harv_err:
        logger.warning(f"[ML-TOURNAMENT] Bhavcopy harvest non-fatal notice: {harv_err}")

    try:
        from src.data.full_spectrum_harvester import FullSpectrumHarvester
        fs_harvester = FullSpectrumHarvester(db)
        fs_res = fs_harvester.run_full_harvest(
            backfill_tickers=True,
            resolve_sectors=True,
            ingest_files=True,
            fetch_indices=False,
            enrich_fundamentals=True,
            pack_milz=False,
            export_snap=False,
            max_ticker_batch=20
        )
        logger.info(f"[ML-TOURNAMENT] Full-spectrum harvest incremental batch: {fs_res}")
    except Exception as fs_err:
        logger.warning(f"[ML-TOURNAMENT] Full-spectrum harvest non-fatal notice: {fs_err}")

    # 1. Refresh latest daily bars for priority equities
    logger.info(f"Updating latest price bars for {len(target_symbols)} equities via parallel ingestion...")
    try:
        ingest_symbols_parallel(db, target_symbols, max_workers=8, chunk_size=30, period="5d")
    except Exception as e:
        logger.warning(f"Error during parallel price ingestion: {e}")

    # 2. Vectorized factor updates
    logger.info("Calculating technical factors and 20D returns...")
    factor_updates = []
    try:
        with db.get_connection() as conn:
            df = pd.read_sql_query(f"""
                SELECT symbol, trading_date, close
                FROM ohlcv_daily
                WHERE symbol IN ({','.join(['?']*len(target_symbols))}) AND (series = 'EQ' OR series IS NULL)
                ORDER BY symbol, trading_date ASC
            """, conn, params=target_symbols)

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

            factor_updates.append({
                "symbol": sym,
                "trading_date": str(dates[-1]),
                "ret_1d": ret_1d,
                "ret_5d": ret_5d,
                "ret_20d": ret_20d,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
            })

        if factor_updates:
            with db.get_connection() as conn:
                conn.executemany("""
                    INSERT INTO quant_factors_daily (
                        symbol, trading_date, ret_1d, ret_5d, ret_20d, sma_20, sma_50, sma_200, updated_at
                    ) VALUES (:symbol, :trading_date, :ret_1d, :ret_5d, :ret_20d, :sma_20, :sma_50, :sma_200, :updated_at)
                    ON CONFLICT(symbol, trading_date) DO UPDATE SET
                        ret_1d=excluded.ret_1d,
                        ret_5d=excluded.ret_5d,
                        ret_20d=excluded.ret_20d,
                        sma_20=excluded.sma_20,
                        sma_50=excluded.sma_50,
                        sma_200=excluded.sma_200,
                        updated_at=excluded.updated_at
                """, [{**f, "updated_at": now_iso} for f in factor_updates])
                conn.commit()
            logger.info(f"Vectorized factors refreshed for {len(factor_updates)} equities.")
    except Exception as fe:
        logger.warning(f"Factor calculation error: {fe}")

    # 3. Execute walk-forward ML tournament
    logger.info("Training Walk-Forward ML Tournament (5D, 20D, 60D horizons)...")
    trainer = WalkForwardMLTrainer(db=db)
    tournament_results = trainer.run_training_tournament(horizons=[5, 20, 60])

    tournament_summary: Dict[str, Any] = {}
    summary_path = Path("data/models/tournament_summary.json")
    if summary_path.exists():
        try:
            with open(summary_path, "r", encoding="utf-8") as f:
                tournament_summary = json.load(f)
            logger.info(f"Tournament Summary loaded: Champion = {tournament_summary.get('overall_summary', {}).get('champion_model')}")
        except Exception as e:
            logger.warning(f"Error reading tournament summary: {e}")

    # 4. Precompute multi-horizon forecasts for target equities
    logger.info(f"Precomputing ML forecasts for {len(target_symbols)} equities...")
    ml_forecasts: Dict[str, Dict[str, Any]] = {}
    for sym in target_symbols:
        try:
            fc = trainer.predict_for_symbol(sym)
            if fc and "error" not in fc:
                ml_forecasts[sym] = fc
        except Exception as ex:
            logger.debug(f"Prediction skipped for {sym}: {ex}")

    logger.info(f"Successfully precomputed forecasts for {len(ml_forecasts)} equities.")

    elapsed = round(time.time() - t0, 1)
    result = {
        "status": "completed",
        "elapsed_sec": elapsed,
        "tournament_runs": len(tournament_results),
        "forecasts_count": len(ml_forecasts),
        "factors_updated": len(factor_updates),
        "synced": False
    }

    if dry_run:
        logger.info(f"[DRY-RUN] ML pipeline finished in {elapsed}s. Skipping POST sync.")
        return result

    # Extract fresh daily OHLCV bars ingested/updated during this run (last 5 sessions)
    fresh_ohlcv_bars = []
    try:
        with db.get_connection() as conn:
            max_d_row = conn.execute("SELECT MAX(trading_date) FROM ohlcv_daily").fetchone()
            if max_d_row and max_d_row[0]:
                max_d = max_d_row[0]
                cutoff_dt = datetime.datetime.strptime(max_d, "%Y-%m-%d") - datetime.timedelta(days=7)
                cutoff_str = cutoff_dt.strftime("%Y-%m-%d")
                rows = conn.execute("""
                    SELECT symbol, trading_date, series, open, high, low, close, prev_close, volume
                    FROM ohlcv_daily
                    WHERE trading_date >= ? AND (series = 'EQ' OR series IS NULL)
                    ORDER BY symbol, trading_date
                """, (cutoff_str,)).fetchall()
                fresh_ohlcv_bars = [dict(r) for r in rows]
                logger.info(f"[ML-TOURNAMENT] Extracted {len(fresh_ohlcv_bars)} fresh OHLCV bars (>= {cutoff_str}) to sync to backend.")
    except Exception as bar_err:
        logger.warning(f"[ML-TOURNAMENT] Error querying fresh OHLCV bars: {bar_err}")

    # 5. POST to Render Internal Sync Bridge (strictly capped to AT MOST 2 POST requests per run)
    if backend_url and token:
        sync_url = f"{backend_url}/api/v1/internal/sync"
        CHUNK_SIZE = 5000
        bar_chunks = [fresh_ohlcv_bars[i:i + CHUNK_SIZE] for i in range(0, max(1, len(fresh_ohlcv_bars)), CHUNK_SIZE)][:2] if fresh_ohlcv_bars else [[]]

        for chunk_idx, bar_chunk in enumerate(bar_chunks):
            is_first = (chunk_idx == 0)
            payload = {
                "tournament_summary": tournament_summary if is_first else None,
                "ml_forecasts": ml_forecasts if is_first else None,
                "factor_updates": factor_updates if is_first else None,
                "push_subscriptions": state.get("push_subscriptions", []) if is_first else [],
                "ohlcv_bars": bar_chunk if bar_chunk else None,
            }
            logger.info(f"Syncing tournament & bars (chunk {chunk_idx + 1}/{len(bar_chunks)}, {len(bar_chunk)} bars) to backend: {sync_url}...")
            try:
                resp = _request_with_wake(
                    "POST",
                    sync_url,
                    backend_url=backend_url,
                    json=payload,
                    headers={
                        "X-Internal-Token": token,
                        "X-Internal-Sync-Secret": token,
                        "Content-Type": "application/json",
                    },
                    timeout=95
                )
                if resp.status_code == 200:
                    logger.info(f"Successfully synced ML chunk {chunk_idx + 1} to backend: {resp.json().get('counts', {})}")
                    result["synced"] = True
                    result["backend_response"] = resp.json()
                else:
                    logger.error(f"Backend ML sync failed with HTTP {resp.status_code}: {resp.text[:300]}")
            except Exception as e:
                logger.error(f"Failed to post ML sync chunk {chunk_idx + 1} to {sync_url}: {e}")
    else:
        logger.warning("No backend_url or token provided; skipping sync.")

    # 6. Persist Refreshed data/cloud_seed_snapshot.json.gz (when not dry-run, hot 400-session window)
    try:
        from src.storage.cloud_snapshot import export_cloud_snapshot
        snap_path = export_cloud_snapshot(db, output_path="data/cloud_seed_snapshot.json.gz", max_ohlcv_days=400)
        logger.info(f"[SNAPSHOT] Refreshed cloud seed snapshot exported to {snap_path}")
    except Exception as snap_err:
        logger.warning(f"[SNAPSHOT] Error exporting refreshed cloud snapshot: {snap_err}")

    return result


# ─────────────────────────────────────────────────────────────────────────────
# MAIN CLI ENTRYPOINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Market Intelligence Lab: Decoupled 7GB Cloud Compute Worker"
    )
    parser.add_argument(
        "--mode",
        choices=["news", "news_radar", "ml", "backfill", "full_harvest", "all"],
        default="all",
        help="Pipeline mode to execute: 'news'/'news_radar', 'ml', 'backfill', 'full_harvest', or 'all' (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Execute pipelines locally without making remote POST sync requests"
    )
    parser.add_argument(
        "--backend-url",
        default=get_default_backend_url(),
        help="Base URL of Render backend (defaults to RENDER_BACKEND_URL or http://127.0.0.1:8000)"
    )
    parser.add_argument(
        "--token",
        default=get_default_sync_token(),
        help="Secret internal sync token (defaults to INTERNAL_SYNC_TOKEN)"
    )
    parser.add_argument(
        "--db-path",
        default="data/market_lab.db",
        help="Path to worker SQLite database (default: data/market_lab.db)"
    )

    args = parser.parse_args()

    logger.info("=====================================================")
    logger.info("   Market Intelligence Lab — Cloud Compute Worker   ")
    logger.info("=====================================================")
    logger.info(f"Execution Mode: {args.mode.upper()}")
    logger.info(f"Dry Run: {args.dry_run}")
    logger.info(f"Backend URL: {args.backend_url}")
    logger.info(f"Database Path: {args.db_path}")

    # 1. Bootstrap worker state
    state = bootstrap_worker_db(
        backend_url=args.backend_url,
        token=args.token,
        db_path=args.db_path,
        dry_run=args.dry_run
    )

    results: Dict[str, Any] = {}

    # 2. Execute selected pipeline
    if args.mode in ("backfill", "full_harvest"):
        from src.data.full_spectrum_harvester import FullSpectrumHarvester
        harvester = FullSpectrumHarvester(DatabaseManager(args.db_path))
        results["full_harvest"] = harvester.run_full_harvest()

    if args.mode in ("news", "news_radar", "all"):
        results["news"] = run_parallel_news_pipeline(
            state=state,
            backend_url=args.backend_url,
            token=args.token,
            db_path=args.db_path,
            dry_run=args.dry_run
        )

    if args.mode in ("ml", "all"):
        results["ml"] = run_ml_tournament_pipeline(
            state=state,
            backend_url=args.backend_url,
            token=args.token,
            db_path=args.db_path,
            dry_run=args.dry_run
        )

    logger.info("=====================================================")
    logger.info(f"Cloud Worker Execution Completed: {json.dumps(results, indent=2)}")
    logger.info("=====================================================")


if __name__ == "__main__":
    main()
