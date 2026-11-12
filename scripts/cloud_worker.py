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
    return os.getenv("RENDER_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


def get_default_sync_token() -> str:
    return os.getenv("INTERNAL_SYNC_TOKEN", "")


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
            resp = requests.get(
                export_url,
                headers={"X-Internal-Token": token},
                timeout=30
            )
            if resp.status_code == 200:
                payload = resp.json()
                state["watchlist"] = payload.get("watchlist", [])
                state["portfolio_symbols"] = payload.get("portfolio_symbols", [])
                state["priority_symbols"] = payload.get("priority_symbols", [])
                state["latest_ohlcv_date"] = payload.get("latest_ohlcv_date")
                recent_ohlcv = payload.get("recent_ohlcv", [])

                logger.info(
                    f"State successfully exported from backend: "
                    f"{len(state['watchlist'])} watchlist, "
                    f"{len(state['portfolio_symbols'])} portfolio, "
                    f"{len(state['priority_symbols'])} priority, "
                    f"{len(recent_ohlcv)} recent OHLCV bars."
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
                        bar_tuples = [
                            (
                                b["symbol"],
                                "EQ",
                                b["trading_date"],
                                b["open"],
                                b["high"],
                                b["low"],
                                b["close"],
                                b["close"],
                                b["volume"],
                                b["close"] * b["volume"],
                            )
                            for b in recent_ohlcv
                        ]
                        conn.executemany("""
                            INSERT OR REPLACE INTO ohlcv_daily (
                                symbol, series, trading_date, open, high, low, close, prev_close, volume, value
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, bar_tuples)

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

    # Compute target lists
    wl_syms = [w["symbol"] for w in state["watchlist"]]
    pf_syms = state["portfolio_symbols"]
    prio_syms = state["priority_symbols"]

    # Target news symbols: watchlist + portfolio + top 75 liquid equities (~85 total)
    state["target_news_symbols"] = list(dict.fromkeys(wl_syms + pf_syms + prio_syms[:75]))

    # Target ML symbols: watchlist + portfolio + top 300 active equities
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

    logger.info(f"Causal Radar identified {len(detected_catalysts)} active catalysts.")

    # Prepare sync payload (explicitly instruct Render backend to dispatch push for new catalysts)
    has_catalysts = len(detected_catalysts) > 0
    payload = {
        "news_articles": all_articles,
        "catalysts": detected_catalysts,
        "dispatch_push": True if has_catalysts else False
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
            resp = requests.post(
                sync_url,
                json=payload,
                headers={"X-Internal-Token": token},
                timeout=45
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
                WHERE symbol IN ({','.join(['?']*len(target_symbols))}) AND series = 'EQ'
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

    # 5. POST to Render Internal Sync Bridge
    if backend_url and token:
        sync_url = f"{backend_url}/api/v1/internal/sync"
        payload = {
            "tournament_summary": tournament_summary,
            "ml_forecasts": ml_forecasts,
            "factor_updates": factor_updates
        }
        logger.info(f"Syncing tournament & precomputed forecasts to backend: {sync_url}...")
        try:
            resp = requests.post(
                sync_url,
                json=payload,
                headers={"X-Internal-Token": token},
                timeout=60
            )
            if resp.status_code == 200:
                logger.info(f"Successfully synced ML forecasts to backend: {resp.json()}")
                result["synced"] = True
                result["backend_response"] = resp.json()
            else:
                logger.error(f"Backend ML sync failed with HTTP {resp.status_code}: {resp.text[:300]}")
        except Exception as e:
            logger.error(f"Failed to post ML sync to {sync_url}: {e}")
    else:
        logger.warning("No backend_url or token provided; skipping sync.")

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
        choices=["news", "ml", "all"],
        default="all",
        help="Pipeline mode to execute: 'news', 'ml', or 'all' (default: all)"
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
    if args.mode in ("news", "all"):
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
