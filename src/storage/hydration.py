"""
src/storage/hydration.py

Market Intelligence Lab — Cloud Database Auto-Hydration Engine (Render 512MB Guard).
Automatically hydrates SQLite tables, securities master, initial watchlists, and
pre-computes initial causal catalysts on fresh cloud deployments.
Unpacks pre-packaged data/cloud_seed_snapshot.json.gz in < 1 second on cold boot.
"""

import os
import gc
import json
import gzip
import time
import threading
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

# Thread-safe in-memory hydration status
_hydration_status: str = "READY"
_hydration_lock = threading.Lock()


def get_hydration_status() -> str:
    """Returns current cloud database hydration status: 'HYDRATING' or 'READY'."""
    with _hydration_lock:
        return _hydration_status


def set_hydration_status(status: str) -> None:
    """Sets hydration status thread-safely."""
    global _hydration_status
    with _hydration_lock:
        _hydration_status = status

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SNAPSHOT_PATH = os.path.join(ROOT_DIR, "data", "cloud_seed_snapshot.json.gz")

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


def ensure_core_tables_exist(conn: sqlite3.Connection):
    """Guarantees all essential relational tables and indexes exist prior to snapshot hydration."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS factors_daily (
            symbol TEXT NOT NULL,
            trading_date TEXT NOT NULL,
            close REAL NOT NULL,
            adj_close REAL NOT NULL,
            volume INTEGER NOT NULL,
            adj_volume INTEGER NOT NULL,
            sessions_available INTEGER NOT NULL,
            burn_in_complete INTEGER NOT NULL,
            ret_1d REAL,
            ret_5d REAL,
            ret_20d REAL,
            sma_20 REAL,
            sma_50 REAL,
            sma_200 REAL,
            volatility_20d REAL,
            volatility_annualized REAL,
            rsi_14 REAL,
            momentum_1y REAL,
            trend_regime TEXT,
            updated_at TEXT,
            return_20d REAL DEFAULT NULL,
            PRIMARY KEY (symbol, trading_date)
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_factors_daily_date ON factors_daily(trading_date);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_factors_daily_sym ON factors_daily(symbol);")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_catalysts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            company_name TEXT,
            sector TEXT,
            move_pct REAL NOT NULL,
            rvol REAL NOT NULL,
            classification TEXT NOT NULL,
            pillar1_price TEXT,
            pillar2_macro TEXT,
            pillar3_corp TEXT,
            pillar4_news TEXT,
            causal_headline TEXT NOT NULL,
            causal_bullets TEXT NOT NULL,
            triggered_at TEXT NOT NULL,
            push_sent INTEGER DEFAULT 0
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_catalysts_sym ON market_catalysts(symbol);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_catalysts_date ON market_catalysts(triggered_at);")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS push_subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            endpoint TEXT UNIQUE NOT NULL,
            p256dh TEXT NOT NULL,
            auth TEXT NOT NULL,
            user_agent TEXT,
            created_at TEXT NOT NULL
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS llm_usage_telemetry (
            usage_date TEXT NOT NULL,
            provider TEXT NOT NULL,
            model_id TEXT NOT NULL,
            requests_used INTEGER DEFAULT 0,
            prompt_tokens INTEGER DEFAULT 0,
            completion_tokens INTEGER DEFAULT 0,
            total_tokens INTEGER DEFAULT 0,
            remaining_requests_header INTEGER,
            remaining_tokens_header INTEGER,
            daily_request_limit INTEGER NOT NULL,
            daily_token_limit INTEGER NOT NULL,
            last_used_at TEXT,
            PRIMARY KEY (usage_date, model_id)
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS copilot_distillation_corpus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            intent TEXT NOT NULL,
            symbol TEXT NOT NULL,
            sector TEXT,
            user_prompt TEXT NOT NULL,
            abstracted_prompt TEXT NOT NULL,
            telemetry_features_json TEXT NOT NULL,
            teacher_model TEXT NOT NULL,
            teacher_response TEXT NOT NULL,
            abstracted_template TEXT NOT NULL,
            tokens_total INTEGER DEFAULT 0
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_distill_intent ON copilot_distillation_corpus(intent);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_distill_symbol ON copilot_distillation_corpus(symbol);")


def repair_null_ret_20d(target: Any) -> int:
    """
    Computes/guarantees non-null ret_20d in quant_factors_daily for all equities.
    Derives from factors_daily or proxies from ret_5d / ret_1d if missing.
    Accepts either an active sqlite3.Connection or a DatabaseManager instance.
    """
    if isinstance(target, sqlite3.Connection):
        conn = target
        should_close = False
    elif hasattr(target, "get_connection"):
        conn = target.get_connection()
        should_close = True
    else:
        return 0

    try:
        conn.execute("""
            UPDATE quant_factors_daily
            SET ret_20d = (
                SELECT fd.ret_20d FROM factors_daily fd
                WHERE fd.symbol = quant_factors_daily.symbol
                  AND fd.trading_date = quant_factors_daily.trading_date
                  AND fd.ret_20d IS NOT NULL
            )
            WHERE ret_20d IS NULL
              AND EXISTS (
                SELECT 1 FROM factors_daily fd
                WHERE fd.symbol = quant_factors_daily.symbol
                  AND fd.trading_date = quant_factors_daily.trading_date
                  AND fd.ret_20d IS NOT NULL
              );
        """)
        conn.execute("""
            UPDATE quant_factors_daily
            SET ret_20d = CASE
                WHEN ret_5d IS NOT NULL THEN ret_5d * 4.0
                WHEN ret_1d IS NOT NULL THEN ret_1d * 20.0
                ELSE 0.0
            END
            WHERE ret_20d IS NULL;
        """)
        if should_close:
            conn.commit()
    except Exception as e:
        logger.warning(f"Error repairing null ret_20d: {e}")
    finally:
        if should_close:
            conn.close()
    return 0


def hydrate_from_snapshot(db: DatabaseManager, snapshot_path: str = SNAPSHOT_PATH) -> bool:
    """
    Unpacks pre-compiled data/cloud_seed_snapshot.json.gz into SQLite.
    Instantly populates securities_master, ohlcv_daily, quant_factors_daily,
    factors_daily, user_watchlists, and market_catalysts in < 1s.
    """
    if not os.path.exists(snapshot_path):
        logger.warning(f"Snapshot file not found at {snapshot_path}")
        return False

    try:
        t0 = datetime.now()
        with db.get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = OFF;")
            ensure_core_tables_exist(conn)
            db.init_schema()

            table_cols_cache: Dict[str, set] = {}

            def insert_batch(table: str, batch_rows: list):
                if not batch_rows:
                    return
                if table not in table_cols_cache:
                    cur = conn.execute(f"PRAGMA table_info({table})")
                    dest_cols = {r["name"] for r in cur.fetchall()}
                    for c in batch_rows[0].keys():
                        if c not in dest_cols:
                            try:
                                conn.execute(f"ALTER TABLE {table} ADD COLUMN {c};")
                                dest_cols.add(c)
                            except Exception:
                                pass
                    table_cols_cache[table] = dest_cols

                dest_cols = table_cols_cache[table]
                valid_cols = [c for c in batch_rows[0].keys() if c in dest_cols]
                if not valid_cols:
                    return
                col_names_str = ",".join(valid_cols)
                placeholders = ",".join("?" for _ in valid_cols)
                sql = f"INSERT OR REPLACE INTO {table} ({col_names_str}) VALUES ({placeholders})"
                conn.executemany(sql, [[r.get(c) for c in valid_cols] for r in batch_rows])

            # Check if file has line-formatted table arrays
            is_streamable = False
            with gzip.open(snapshot_path, "rt", encoding="utf-8") as f:
                for _ in range(5):
                    l = f.readline()
                    if not l:
                        break
                    if l.strip().startswith('"') and l.strip().endswith('": ['):
                        is_streamable = True
                        break

            chunk_size = 2500
            chunk_counter = 0

            if is_streamable:
                current_table = None
                batch = []
                with gzip.open(snapshot_path, "rt", encoding="utf-8") as f:
                    for line in f:
                        line_s = line.strip()
                        if not line_s or line_s in ("{", "}"):
                            continue
                        if line_s.startswith('"') and line_s.endswith('": ['):
                            current_table = line_s.split('"')[1]
                            batch = []
                            continue
                        if line_s in ("]", "],"):
                            if batch and current_table:
                                insert_batch(current_table, batch)
                                conn.commit()
                                batch = []
                                chunk_counter += 1
                                time.sleep(0.015)
                                if chunk_counter % 10 == 0:
                                    gc.collect()
                            current_table = None
                            continue
                        if current_table and line_s.startswith("{"):
                            if line_s.endswith(","):
                                line_s = line_s[:-1]
                            row_dict = json.loads(line_s)
                            batch.append(row_dict)
                            if len(batch) >= chunk_size:
                                insert_batch(current_table, batch)
                                conn.commit()
                                batch = []
                                chunk_counter += 1
                                time.sleep(0.015)
                                if chunk_counter % 10 == 0:
                                    gc.collect()
            else:
                with gzip.open(snapshot_path, "rb") as f:
                    snap = json.loads(f.read().decode("utf-8"))
                for tbl, rows in snap.items():
                    if rows and isinstance(rows, list):
                        for i in range(0, len(rows), chunk_size):
                            insert_batch(tbl, rows[i:i + chunk_size])
                            conn.commit()
                            chunk_counter += 1
                            time.sleep(0.015)
                            if chunk_counter % 10 == 0:
                                gc.collect()
                del snap
                gc.collect()

            conn.execute("PRAGMA synchronous = NORMAL;")

            # Repair any missing ret_20d in quant_factors_daily
            repair_null_ret_20d(conn)

            # Ensure supervisor state is valid and points to an approved champion
            cur = conn.execute("SELECT active_model_id FROM supervisor_state WHERE singleton_id = 1")
            ss_row = cur.fetchone()
            if not ss_row or not ss_row[0]:
                conn.execute("""
                    INSERT OR REPLACE INTO supervisor_state (
                        singleton_id, current_state, active_model_id, last_transition_at,
                        transition_reason, quarantined_symbols_json, auto_retrain_enabled, updated_at
                    ) VALUES (
                        1, 'NORMAL', 'baseline_deterministic',
                        datetime('now'), 'COLD_BOOT_HYDRATION', '[]', 1, datetime('now')
                    )
                """)

            conn.commit()

        if not is_streamable and "snap" in locals():
            tourney_summary = snap.pop("tournament_summary", None)
            if tourney_summary:
                tourney_path = os.path.join(ROOT_DIR, "data", "models", "tournament_summary.json")
                if not os.path.exists(tourney_path):
                    os.makedirs(os.path.dirname(tourney_path), exist_ok=True)
                    with open(tourney_path, "w", encoding="utf-8") as f:
                        json.dump(tourney_summary, f, indent=2)
                    logger.info("Generated data/models/tournament_summary.json on server from snapshot.")

            macro_telemetry = snap.pop("macro_telemetry", None)
            if macro_telemetry:
                macro_path = os.path.join(ROOT_DIR, "data", "macro_telemetry.json")
                if not os.path.exists(macro_path):
                    os.makedirs(os.path.dirname(macro_path), exist_ok=True)
                    with open(macro_path, "w", encoding="utf-8") as f:
                        json.dump(macro_telemetry, f, indent=2)
                    logger.info("Generated data/macro_telemetry.json on server from snapshot.")

            del snap

        try:
            import ctypes
            libc = ctypes.CDLL("libc.so.6")
            if hasattr(libc, "malloc_trim"):
                libc.malloc_trim(0)
        except Exception:
            pass
        gc.collect()

        verify_model_deployments(db)

        elapsed = (datetime.now() - t0).total_seconds()
        logger.info(f"Instant cloud database hydration complete from snapshot in {elapsed:.3f}s.")
        return True
    except Exception as e:
        logger.error(f"Failed to hydrate database from snapshot: {e}", exc_info=True)
        return False


def verify_model_deployments(db: DatabaseManager) -> int:
    """
    Verifies that all active models in model_horizon_deployments have valid
    serialized artifact files on disk. If any artifact is missing (e.g. cold start),
    logs a clear warning and safely de-registers or falls back cleanly.
    """
    fixed = 0
    try:
        with db.get_connection() as conn:
            cur = conn.execute("""
                SELECT 
                    d.horizon_days, d.active_model_id, m.artifact_path
                FROM model_horizon_deployments d
                LEFT JOIN model_registry m ON d.active_model_id = m.model_id
                WHERE d.active_model_id IS NOT NULL
            """)
            rows = cur.fetchall()
            for r in rows:
                h = r[0]
                mid = r[1]
                path = r[2]
                if not path or not os.path.exists(path):
                    logger.warning(
                        f"[MODEL-HYDRATION] Active champion model '{mid}' for {h}D horizon "
                        f"points to missing artifact '{path}' on disk. Falling back cleanly."
                    )
                    conn.execute(
                        "UPDATE model_horizon_deployments SET active_model_id = NULL WHERE horizon_days = ?",
                        (h,)
                    )
                    fixed += 1
            if fixed > 0:
                conn.commit()
    except Exception as e:
        logger.debug(f"Non-fatal notice during model deployment verification: {e}")
    return fixed


def hydrate_initial_cloud_database(db_path: str = "data/market_lab.db") -> Dict[str, Any]:
    """
    Checks if the local SQLite database is uninitialized or missing core data.
    If empty or fresh, automatically migrates schema and unpacks cloud_seed_snapshot.
    """
    set_hydration_status("HYDRATING")
    try:
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        db = DatabaseManager(db_path)

        # 1. Base schema initialization
        db.init_schema()

        with db.get_connection() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            ensure_core_tables_exist(conn)

        init_push_tables()
        init_catalyst_tables()

        stats = {
            "securities_seeded": 0,
            "watchlists_seeded": 0,
            "catalysts_seeded": 0,
            "hydrated_from_snapshot": False
        }

        # 2. Check securities_master count
        with db.get_connection() as conn:
            cur = conn.execute("SELECT COUNT(*) FROM securities_master")
            sec_count = cur.fetchone()[0]

        # If database is fresh (0 securities), attempt instant snapshot hydration first!
        if sec_count == 0:
            logger.info("Fresh database detected (0 securities). Attempting instant snapshot hydration...")
            if os.path.exists(SNAPSHOT_PATH):
                success = hydrate_from_snapshot(db, SNAPSHOT_PATH)
                if success:
                    stats["hydrated_from_snapshot"] = True
                    with db.get_connection() as conn:
                        stats["securities_seeded"] = conn.execute("SELECT COUNT(*) FROM securities_master").fetchone()[0]
                        stats["watchlists_seeded"] = conn.execute("SELECT COUNT(*) FROM user_watchlists").fetchone()[0]
                        stats["catalysts_seeded"] = conn.execute("SELECT COUNT(*) FROM market_catalysts").fetchone()[0]

                    # Phase 1: Restore durable user state from Azure Blob Storage if configured
                    try:
                        from src.storage.durable_state import DurableStateManager
                        durable_res = DurableStateManager.get_instance(db=db).restore_on_startup()
                        stats["durable_state"] = durable_res
                    except Exception as e:
                        logger.warning(f"Durable state restore non-fatal notice: {e}")

                    return stats

            # Fallback to programmatic universe seed if snapshot missing
            logger.info("Snapshot unavailable; falling back to programmatic universe expander seed...")
            expander = UniverseExpander(db)
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
            if is_cloud_lightweight_mode():
                logger.info("CLOUD_LIGHTWEIGHT_MODE active: Skipping initial catalyst scan on boot.")
            else:
                logger.info("Synthesizing initial intraday causal catalysts...")
                try:
                    catalysts = catalyst_engine.run_intraday_scan()
                    stats["catalysts_seeded"] = len(catalysts)
                except Exception as e:
                    logger.warning(f"Initial catalyst scan partial: {e}")

        # Verify active ML model deployments point to valid artifacts on disk
        verify_model_deployments(db)

        # Ensure no null ret_20d values remain in quant_factors_daily
        repair_null_ret_20d(db)

        # Phase 1: Restore durable user state from Azure Blob Storage if configured
        try:
            from src.storage.durable_state import DurableStateManager
            durable_res = DurableStateManager.get_instance(db=db).restore_on_startup()
            stats["durable_state"] = durable_res
        except Exception as e:
            logger.warning(f"Durable state restore non-fatal notice: {e}")

        gc.collect()
        logger.info(f"Database hydration check complete: {stats}")
        return stats
    finally:
        set_hydration_status("READY")
