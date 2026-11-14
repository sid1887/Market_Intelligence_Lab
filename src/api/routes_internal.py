"""
src/api/routes_internal.py
Internal Sync & State Export Bridge for Decoupled Compute Workers (GitHub Actions / Kaggle).

Enables external 7GB runners to:
1. Export live portfolio/watchlist/OHLCV state (GET /api/v1/internal/export-state)
2. Batch sync finished news, causal catalysts, ML tournament summaries, and forecasts (POST /api/v1/internal/sync)
All requests are guarded with constant-time token verification via X-Internal-Token header.
"""

import os
import hmac
import json
import time
import logging
import sqlite3
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
from fastapi import APIRouter, Header, HTTPException, Depends
from pydantic import BaseModel, Field

from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH, get_db_connection, sanitize_for_json
from src.notifications.web_push import (
    broadcast_push,
    get_all_subscriptions,
    save_subscription,
    is_alert_dispatched,
    record_dispatched_alert,
)
from src.quant.ml_trainer import update_precomputed_forecasts

logger = logging.getLogger("MIL.InternalSync")

router = APIRouter(prefix="/internal", tags=["Internal Sync Bridge"])


def verify_internal_token(
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token")
) -> bool:
    """
    Constant-time token validation for internal bridge endpoints.
    Reads INTERNAL_SYNC_TOKEN from environment. Raises 401 if missing, empty, or mismatched.
    """
    expected_token = os.getenv("INTERNAL_SYNC_TOKEN", "").strip()
    if not expected_token:
        logger.warning("[INTERNAL-SYNC] Rejected: INTERNAL_SYNC_TOKEN is not configured on this server.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Server INTERNAL_SYNC_TOKEN is not configured."
        )

    if not x_internal_token:
        logger.warning("[INTERNAL-SYNC] Rejected: Missing X-Internal-Token header.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Missing X-Internal-Token header."
        )

    if not hmac.compare_digest(x_internal_token.strip(), expected_token):
        logger.warning("[INTERNAL-SYNC] Rejected: Invalid X-Internal-Token value.")
        raise HTTPException(
            status_code=401,
            detail="Unauthorized: Invalid internal sync token."
        )

    return True


# ─────────────────────────────────────────────────────────────────────────────
# 1. STATE EXPORT FOR STATELESS WORKERS
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/export-state")
def export_state_endpoint(
    conn: sqlite3.Connection = Depends(get_db_connection),
    _authorized: bool = Depends(verify_internal_token),
) -> Dict[str, Any]:
    """
    Exports state required by external compute workers to initialize and run offline tasks:
    - User watchlists
    - Active portfolio positions
    - Priority equity universe (NIFTY50 + top liquid)
    - Latest settled trading date
    - Recent 750 daily OHLCV bars (approx. 3 years) for target symbol group
    """
    cur = conn.cursor()

    # 1. Watchlist symbols
    cur.execute("""
        SELECT symbol, company_name, sector, target_price, stop_loss
        FROM user_watchlists
        ORDER BY symbol ASC
    """)
    watchlist = [
        {
            "symbol": r[0],
            "company_name": r[1],
            "sector": r[2],
            "target_price": r[3],
            "stop_loss": r[4],
        }
        for r in cur.fetchall()
    ]
    watchlist_symbols = [w["symbol"] for w in watchlist]

    # 2. Portfolio symbols with open positions
    cur.execute("""
        SELECT DISTINCT symbol
        FROM portfolio_positions
        WHERE quantity > 0
        ORDER BY symbol ASC
    """)
    portfolio_symbols = [r[0] for r in cur.fetchall() if r[0]]

    # 3. Priority universe (top 250 active symbols)
    cur.execute("""
        SELECT symbol
        FROM securities_master
        WHERE is_active = 1
        ORDER BY is_nifty50 DESC, symbol ASC
        LIMIT 250
    """)
    priority_symbols = [r[0] for r in cur.fetchall() if r[0]]

    # 4. Latest OHLCV trading date
    cur.execute("SELECT MAX(trading_date) FROM ohlcv_daily")
    latest_ohlcv_date_row = cur.fetchone()
    latest_ohlcv_date = latest_ohlcv_date_row[0] if latest_ohlcv_date_row else None

    # 5. Recent OHLCV bars (last 750 trading sessions, ~3 years) for Watchlist + Portfolio + Top 150
    target_symbols = list(dict.fromkeys(watchlist_symbols + portfolio_symbols + priority_symbols[:150]))
    recent_ohlcv: List[Dict[str, Any]] = []

    if target_symbols:
        placeholders = ",".join(["?"] * len(target_symbols))
        query = f"""
            SELECT symbol, trading_date, open, high, low, close, volume
            FROM ohlcv_daily
            WHERE symbol IN ({placeholders}) AND (series = 'EQ' OR series IS NULL)
            ORDER BY symbol ASC, trading_date ASC
        """
        df = pd.read_sql_query(query, conn, params=target_symbols)
        if not df.empty:
            for sym, group in df.groupby("symbol"):
                recent_sub = group.tail(750)
                for _, row in recent_sub.iterrows():
                    recent_ohlcv.append({
                        "symbol": row["symbol"],
                        "trading_date": str(row["trading_date"]),
                        "open": float(row["open"]),
                        "high": float(row["high"]),
                        "low": float(row["low"]),
                        "close": float(row["close"]),
                        "volume": int(row["volume"]) if pd.notnull(row["volume"]) else 0,
                    })

    return sanitize_for_json({
        "status": "success",
        "watchlist": watchlist,
        "portfolio_symbols": portfolio_symbols,
        "priority_symbols": priority_symbols,
        "latest_ohlcv_date": latest_ohlcv_date,
        "recent_ohlcv": recent_ohlcv,
        "push_subscriptions": get_all_subscriptions(),
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })


# ─────────────────────────────────────────────────────────────────────────────
# 2. BATCH UPSERT / SYNC FROM EXTERNAL WORKER TO RENDER
# ─────────────────────────────────────────────────────────────────────────────

class InternalSyncPayload(BaseModel):
    news_articles: Optional[List[Dict[str, Any]]] = Field(None, description="Processed news articles for equity_news_feed")
    catalysts: Optional[List[Dict[str, Any]]] = Field(None, description="Detected causal catalysts for market_catalysts")
    dispatch_push: Optional[bool] = Field(True, description="Whether to broadcast push notifications for new catalysts")
    push_subscriptions: Optional[List[Dict[str, Any]]] = Field(None, description="Active Web Push client subscriptions to restore/persist")
    tournament_summary: Optional[Dict[str, Any]] = Field(None, description="ML tournament summary JSON payload")
    ml_forecasts: Optional[Dict[str, Dict[str, Any]]] = Field(None, description="Precomputed multi-horizon ML forecasts")
    ohlcv_bars: Optional[List[Dict[str, Any]]] = Field(None, description="Optional daily OHLCV candlestick rows")
    factor_updates: Optional[List[Dict[str, Any]]] = Field(None, description="Optional technical and quant factor rows")


@router.post("/sync")
def sync_internal_state_endpoint(
    payload: InternalSyncPayload,
    _authorized: bool = Depends(verify_internal_token),
) -> Dict[str, Any]:
    """
    Receives precomputed artifacts from external 7GB compute runners (GitHub Actions/Kaggle)
    and merges them into the local database, file models, and in-memory caches.
    """
    db = DatabaseManager(DATABASE_PATH)
    counts = {
        "push_subscriptions_restored": 0,
        "news_articles": 0,
        "catalysts": 0,
        "catalysts_push_sent": 0,
        "news_push_sent": 0,
        "tournament_summary": 0,
        "ml_forecasts": 0,
        "ohlcv_bars": 0,
        "factor_updates": 0,
    }

    # 0. Push Subscriptions Sync -> push_subscriptions (Restore if wiped by cold restart)
    if payload.push_subscriptions:
        restored = 0
        for sub in payload.push_subscriptions:
            ep = sub.get("endpoint")
            p256dh = sub.get("p256dh")
            auth = sub.get("auth")
            ua = sub.get("user_agent")
            if ep and p256dh and auth:
                if save_subscription(ep, p256dh, auth, ua):
                    restored += 1
        counts["push_subscriptions_restored"] = restored
        logger.info(f"[INTERNAL-SYNC] Restored/verified {restored} push subscriptions in SQLite.")

    # 1. News Articles Sync -> equity_news_feed
    if payload.news_articles:
        try:
            inserted_count = db.insert_news_articles(payload.news_articles)
            counts["news_articles"] = inserted_count
            logger.info(f"[INTERNAL-SYNC] Upserted {inserted_count} news articles into equity_news_feed.")
        except Exception as e:
            logger.error(f"[INTERNAL-SYNC] Error upserting news articles: {e}", exc_info=True)

    # 2. Causal Catalysts Sync -> market_catalysts (with deduplication)
    new_catalyst_records = []
    if payload.catalysts:
        try:
            with db.get_connection() as conn:
                existing_catalysts = set(
                    conn.execute("""
                        SELECT symbol, SUBSTR(triggered_at, 1, 10), causal_headline
                        FROM market_catalysts
                    """).fetchall()
                )

                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()

                for cat in payload.catalysts:
                    sym = cat.get("symbol", "").strip().upper()
                    trig_at = cat.get("triggered_at", now_iso)
                    trig_date = trig_at[:10]
                    headline = cat.get("causal_headline", "").strip()

                    dedup_key = (sym, trig_date, headline)
                    if dedup_key in existing_catalysts:
                        continue

                    bullets = cat.get("causal_bullets", [])
                    bullets_json = json.dumps(bullets) if isinstance(bullets, list) else str(bullets)
                    p1 = json.dumps(cat.get("pillar1", cat.get("pillar1_price", {})))
                    p2 = json.dumps(cat.get("pillar2", cat.get("pillar2_macro", {})))
                    p3 = json.dumps(cat.get("pillar3", cat.get("pillar3_corp", {})))
                    p4 = json.dumps(cat.get("pillar4", cat.get("pillar4_news", {})))

                    conn.execute("""
                        INSERT INTO market_catalysts (
                            symbol, company_name, sector, move_pct, rvol, classification,
                            pillar1_price, pillar2_macro, pillar3_corp, pillar4_news,
                            causal_headline, causal_bullets, triggered_at, push_sent
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        sym,
                        cat.get("company_name", sym),
                        cat.get("sector", "General"),
                        float(cat.get("move_pct", 0.0)),
                        float(cat.get("rvol", 1.0)),
                        cat.get("classification", "IDIOSYNCRATIC"),
                        p1,
                        p2,
                        p3,
                        p4,
                        headline,
                        bullets_json,
                        trig_at,
                        1 if payload.dispatch_push else 0,
                    ))
                    existing_catalysts.add(dedup_key)
                    new_catalyst_records.append(cat)

                conn.commit()
                counts["catalysts"] = len(new_catalyst_records)
                logger.info(f"[INTERNAL-SYNC] Inserted {len(new_catalyst_records)} new unique catalysts.")
        except Exception as e:
            logger.error(f"[INTERNAL-SYNC] Error syncing catalysts: {e}", exc_info=True)

    # 2.1 Multi-Source Smart Burst-Throttled Web Push Dispatch
    if payload.dispatch_push:
        try:
            # Load active watchlist and portfolio symbols to prioritize alerts
            watchlist_symbols_set = set()
            portfolio_symbols_set = set()
            try:
                with db.get_connection() as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT DISTINCT symbol FROM user_watchlists")
                    watchlist_symbols_set = {r[0].upper() for r in cur.fetchall() if r[0]}
                    cur.execute("SELECT DISTINCT symbol FROM portfolio_positions WHERE quantity > 0")
                    portfolio_symbols_set = {r[0].upper() for r in cur.fetchall() if r[0]}
            except Exception as e:
                logger.warning(f"[INTERNAL-SYNC] Could not fetch watchlist/portfolio symbols for push dispatch: {e}")

            raw_candidates = []

            # A. Catalysts (Highest priority)
            for c in new_catalyst_records:
                sym = c.get("symbol", "").strip().upper()
                headline = c.get("causal_headline", f"Catalyst Alert: {sym}").strip()
                bullets = c.get("causal_bullets", [])
                if isinstance(bullets, list) and bullets:
                    body_text = bullets[0][:140] + "..." if len(bullets[0]) > 140 else bullets[0]
                else:
                    body_text = headline
                trig_at = c.get("triggered_at", "")
                trig_date = trig_at[:10] if trig_at else datetime.date.today().isoformat()
                alert_key = f"catalyst:{sym}:{trig_date}:{headline[:40]}"
                raw_candidates.append({
                    "type": "catalyst",
                    "key": alert_key,
                    "sym": sym,
                    "title": headline,
                    "body": body_text,
                    "url": f"/stocks/{sym}" if sym else "/",
                    "priority": 100,
                })

            # B. News Articles & BSE Corporate Filings
            if payload.news_articles:
                for art in payload.news_articles:
                    sym = str(art.get("symbol", "")).strip().upper()
                    source = str(art.get("source", ""))
                    impact = str(art.get("impact", "NEUTRAL")).upper()
                    is_user_asset = bool(sym and (sym in watchlist_symbols_set or sym in portfolio_symbols_set))
                    is_bse_filing = "BSE Filing" in source and impact in ("BULLISH", "BEARISH")
                    is_high_impact = impact in ("BULLISH", "BEARISH")

                    if not (is_bse_filing or (is_user_asset and is_high_impact)):
                        continue

                    headline = str(art.get("headline", "")).strip()
                    summary = str(art.get("summary", "")).strip()
                    body_text = summary[:140] + "..." if len(summary) > 140 else (summary or headline)
                    art_id = art.get("article_id") or art.get("url") or f"{sym}:{headline[:40]}"
                    alert_key = f"news:{art_id}"

                    # Priority ranking: BSE filings first (90), then user asset news (80)
                    prio = 90 if is_bse_filing else 80

                    raw_candidates.append({
                        "type": "news",
                        "key": alert_key,
                        "sym": sym,
                        "title": headline,
                        "body": body_text,
                        "url": f"/stocks/{sym}" if sym else "/",
                        "priority": prio,
                    })

            # Deduplicate across candidates and filter through ledger
            push_candidates = []
            seen_keys = set()
            for cand in raw_candidates:
                k = cand["key"]
                if k in seen_keys or is_alert_dispatched(k):
                    continue
                seen_keys.add(k)
                push_candidates.append(cand)

            # Sort by priority descending
            push_candidates.sort(key=lambda x: x["priority"], reverse=True)

            if push_candidates:
                logger.info(f"[INTERNAL-SYNC] Dispatching push notifications for {len(push_candidates)} eligible alerts.")

                if len(push_candidates) <= 3:
                    for alert in push_candidates:
                        try:
                            push_stats = broadcast_push(
                                title=alert["title"],
                                body=alert["body"],
                                url=alert["url"],
                                tag=f"alert-{alert['sym']}-{int(time.time() * 1000)}",
                            )
                            record_dispatched_alert(alert["key"])
                            if isinstance(push_stats, dict) and push_stats.get("sent", 0) > 0:
                                if alert["type"] == "catalyst":
                                    counts["catalysts_push_sent"] += push_stats["sent"]
                                else:
                                    counts["news_push_sent"] += push_stats["sent"]
                            logger.info(f"[INTERNAL-SYNC] Web push dispatch for {alert['key']}: {push_stats}")
                        except Exception as pe:
                            logger.warning(f"[INTERNAL-SYNC] Push dispatch error for {alert['key']}: {pe}")
                        time.sleep(1.0)
                else:
                    # Smart Burst Throttling: Top 3 individual + 1 consolidated digest
                    top3 = push_candidates[:3]
                    overflow = push_candidates[3:]

                    for alert in top3:
                        try:
                            push_stats = broadcast_push(
                                title=alert["title"],
                                body=alert["body"],
                                url=alert["url"],
                                tag=f"alert-{alert['sym']}-{int(time.time() * 1000)}",
                            )
                            record_dispatched_alert(alert["key"])
                            if isinstance(push_stats, dict) and push_stats.get("sent", 0) > 0:
                                if alert["type"] == "catalyst":
                                    counts["catalysts_push_sent"] += push_stats["sent"]
                                else:
                                    counts["news_push_sent"] += push_stats["sent"]
                            logger.info(f"[INTERNAL-SYNC] Web push dispatch for {alert['key']}: {push_stats}")
                        except Exception as pe:
                            logger.warning(f"[INTERNAL-SYNC] Push dispatch error for {alert['key']}: {pe}")
                        time.sleep(1.0)

                    # Record all overflow alerts in ledger so they won't repeat
                    for alert in overflow:
                        record_dispatched_alert(alert["key"])

                    # Consolidated digest notification
                    overflow_symbols = list(dict.fromkeys([a["sym"] for a in overflow if a["sym"]]))
                    sym_str = ", ".join(overflow_symbols[:4])
                    if len(overflow_symbols) > 4:
                        sym_str += f" +{len(overflow_symbols) - 4} more"
                    digest_title = f"MIL Quant · +{len(overflow)} More Market Alerts"
                    digest_body = f"High-impact updates for {sym_str}" if sym_str else f"{len(overflow)} new regulatory filings & breaking news alerts."
                    try:
                        push_stats = broadcast_push(
                            title=digest_title,
                            body=digest_body,
                            url="/",
                            tag=f"digest-{int(time.time() * 1000)}",
                        )
                        if isinstance(push_stats, dict) and push_stats.get("sent", 0) > 0:
                            counts["news_push_sent"] += push_stats["sent"]
                        logger.info(f"[INTERNAL-SYNC] Consolidated digest push dispatch: {push_stats}")
                    except Exception as pe:
                        logger.warning(f"[INTERNAL-SYNC] Digest push dispatch warning: {pe}")

        except Exception as pe:
            logger.error(f"[INTERNAL-SYNC] Error during push notification dispatch: {pe}", exc_info=True)

    # 3. ML Tournament Summary -> data/models/tournament_summary.json
    if payload.tournament_summary:
        try:
            target_path = Path("data/models/tournament_summary.json")
            target_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = target_path.with_suffix(".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(payload.tournament_summary, f, indent=2)
            os.replace(tmp_path, target_path)
            counts["tournament_summary"] = 1
            logger.info("[INTERNAL-SYNC] Atomically updated data/models/tournament_summary.json.")
        except Exception as e:
            logger.error(f"[INTERNAL-SYNC] Error writing tournament summary: {e}", exc_info=True)

    # 4. ML Forecasts -> update_precomputed_forecasts & data/models/precomputed_forecasts.json
    if payload.ml_forecasts:
        try:
            synced_forecast_count = update_precomputed_forecasts(payload.ml_forecasts)
            counts["ml_forecasts"] = synced_forecast_count
            logger.info(f"[INTERNAL-SYNC] Synced {synced_forecast_count} precomputed ML forecasts to cache.")
        except Exception as e:
            logger.error(f"[INTERNAL-SYNC] Error updating precomputed forecasts: {e}", exc_info=True)

    # 5. OHLCV Bars Upsert
    if payload.ohlcv_bars:
        try:
            with db.get_connection() as conn:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                bar_tuples = []
                for b in payload.ohlcv_bars:
                    bar_tuples.append((
                        b["symbol"],
                        b["trading_date"],
                        b.get("series", "EQ"),
                        b.get("open"),
                        b.get("high"),
                        b.get("low"),
                        b["close"],
                        b.get("prev_close"),
                        b.get("volume", 0),
                        "INTERNAL_SYNC",
                        now_iso,
                    ))
                conn.executemany("""
                    INSERT OR REPLACE INTO ohlcv_daily (
                        symbol, trading_date, series, open, high, low, close, prev_close, volume, source, retrieval_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, bar_tuples)
                conn.commit()
                counts["ohlcv_bars"] = len(bar_tuples)
                logger.info(f"[INTERNAL-SYNC] Upserted {len(bar_tuples)} daily OHLCV bars.")
        except Exception as e:
            logger.error(f"[INTERNAL-SYNC] Error upserting OHLCV bars: {e}", exc_info=True)

    # 6. Factor Updates Upsert
    if payload.factor_updates:
        try:
            with db.get_connection() as conn:
                now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
                fact_tuples = []
                for f in payload.factor_updates:
                    fact_tuples.append((
                        f["symbol"],
                        f["trading_date"],
                        f.get("ret_1d", 0.0),
                        f.get("ret_5d"),
                        f.get("ret_20d"),
                        f.get("sma_20"),
                        f.get("sma_50"),
                        f.get("sma_200"),
                        now_iso,
                    ))
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
                """, fact_tuples)
                conn.commit()
                counts["factor_updates"] = len(fact_tuples)
                logger.info(f"[INTERNAL-SYNC] Upserted {len(fact_tuples)} quant factor rows.")
        except Exception as e:
            logger.error(f"[INTERNAL-SYNC] Error upserting factor updates: {e}", exc_info=True)

    # If prices or factors were updated, invalidate in-memory screener cache
    if payload.ohlcv_bars or payload.factor_updates:
        try:
            from src.api.main import invalidate_screener_cache
            invalidate_screener_cache()
            logger.info("[INTERNAL-SYNC] In-memory screener cache invalidated.")
        except Exception as e:
            logger.warning(f"[INTERNAL-SYNC] Failed to invalidate screener cache: {e}")

    return sanitize_for_json({
        "status": "synced",
        "counts": counts,
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    })
