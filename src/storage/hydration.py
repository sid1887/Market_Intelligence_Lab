"""
src/storage/hydration.py

Market Intelligence Lab — Cloud Database Auto-Hydration Engine (Render 512MB Guard).
Automatically hydrates SQLite tables, securities master, initial watchlists, and
pre-computes initial causal catalysts on fresh cloud deployments.
"""

import os
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.notifications.web_push import init_push_tables
from src.tasks.catalyst_engine import init_catalyst_tables, catalyst_engine
from src.data.universe_expander import UniverseExpander

logger = logging.getLogger("storage.hydration")

DEFAULT_WATCHLIST_SEED = [
    {"symbol": "SUZLON", "company_name": "Suzlon Energy Ltd", "sector": "Renewable Energy"},
    {"symbol": "TRIDENT", "company_name": "Trident Ltd", "sector": "Textiles / Paper"},
    {"symbol": "DRONACHRYA", "company_name": "Droneacharya Aerial Innovations Ltd", "sector": "Aerospace / Defense"},
    {"symbol": "MOREPENLAB", "company_name": "Morepen Laboratories Ltd", "sector": "Pharmaceuticals"},
    {"symbol": "RELIANCE", "company_name": "Reliance Industries Ltd.", "sector": "Energy"},
    {"symbol": "TCS", "company_name": "Tata Consultancy Services Ltd.", "sector": "Information Technology"},
    {"symbol": "HDFCBANK", "company_name": "HDFC Bank Ltd.", "sector": "Financial Services"},
]


def is_cloud_lightweight_mode() -> bool:
    """Returns True if running on Render or CLOUD_LIGHTWEIGHT_MODE is set."""
    return (
        os.getenv("RENDER", "").lower() in ("true", "1") or
        os.getenv("CLOUD_LIGHTWEIGHT_MODE", "").lower() in ("true", "1")
    )


def hydrate_initial_cloud_database(db_path: str = "data/market_lab.db") -> Dict[str, Any]:
    """
    Checks if the local SQLite database is uninitialized or missing core data.
    If empty or fresh, automatically migrates schema, seeds securities_master,
    seeds default user_watchlists, and synthesizes initial intraday catalysts.
    """
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    db = DatabaseManager(db_path)

    # 1. Ensure migrations and auxiliary tables are created
    with db.get_connection() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        run_all_migrations(conn)

    init_push_tables()
    init_catalyst_tables()

    stats = {
        "securities_seeded": 0,
        "watchlists_seeded": 0,
        "catalysts_seeded": 0
    }

    # 2. Check and hydrate securities_master
    with db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM securities_master")
        sec_count = cur.fetchone()[0]

    if sec_count == 0:
        logger.info("Fresh database detected. Hydrating securities_master from curated universe...")
        expander = UniverseExpander(db)
        # In cloud lightweight mode, seed up to 500 top liquid equities
        max_seed = 500 if is_cloud_lightweight_mode() else 1000
        res = expander.seed_master_universe(max_symbols=max_seed)
        stats["securities_seeded"] = res.get("master_records_inserted", 0)

    # 3. Check and hydrate user_watchlists
    now_iso = datetime.now(timezone.utc).isoformat()
    with db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM user_watchlists")
        wl_count = cur.fetchone()[0]
        if wl_count == 0:
            logger.info("Seeding default user watchlists...")
            for w in DEFAULT_WATCHLIST_SEED:
                conn.execute("""
                    INSERT OR IGNORE INTO user_watchlists (
                        symbol, company_name, sector, notes, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                """, (w["symbol"], w["company_name"], w["sector"], "Initial institutional seed", now_iso, now_iso))
            conn.commit()
            stats["watchlists_seeded"] = len(DEFAULT_WATCHLIST_SEED)

    # 4. Check and synthesize initial market catalysts
    with db.get_connection() as conn:
        cur = conn.execute("SELECT COUNT(*) FROM market_catalysts")
        cat_count = cur.fetchone()[0]

    if cat_count == 0:
        logger.info("Synthesizing initial intraday causal catalysts...")
        try:
            catalysts = catalyst_engine.run_intraday_scan()
            stats["catalysts_seeded"] = len(catalysts)
        except Exception as e:
            logger.warning(f"Initial catalyst scan partial: {e}")

    logger.info(f"Database hydration check complete: {stats}")
    return stats
