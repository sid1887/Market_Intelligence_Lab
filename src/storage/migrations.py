"""
Market Intelligence Lab — Schema Migration & Truth Quarantine Engine.
ADR-0011, ADR-0012, P1-01.

Provides numbered, immutable schema migrations tracked in `schema_migrations`.
Guarantees database consistency, deduplication, and truth-quarantine tracking.
"""

import hashlib
import logging
import os
import sqlite3
from datetime import datetime, timezone
from typing import List, Tuple, Callable

logger = logging.getLogger("market_lab.migrations")


def init_migrations_table(conn: sqlite3.Connection) -> None:
    """Creates the schema_migrations ledger table if not already present."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            migration_id TEXT PRIMARY KEY,
            checksum TEXT NOT NULL,
            applied_at TEXT NOT NULL,
            app_version TEXT NOT NULL,
            status TEXT NOT NULL
        );
    """)
    conn.commit()


def get_applied_migrations(conn: sqlite3.Connection) -> set[str]:
    """Returns the set of applied migration IDs."""
    init_migrations_table(conn)
    cursor = conn.execute("SELECT migration_id FROM schema_migrations WHERE status = 'APPLIED'")
    return {row[0] for row in cursor.fetchall()}


def apply_migration(
    conn: sqlite3.Connection,
    migration_id: str,
    action: Callable[[sqlite3.Connection], None],
    app_version: str = "0.3.0"
) -> bool:
    """Applies a migration within a transaction and logs it into schema_migrations."""
    applied = get_applied_migrations(conn)
    if migration_id in applied:
        return False

    logger.info(f"Applying migration: {migration_id}")
    action(conn)

    checksum = hashlib.sha256(migration_id.encode("utf-8")).hexdigest()[:16]
    now_iso = datetime.now(timezone.utc).isoformat()

    conn.execute("""
        INSERT INTO schema_migrations (migration_id, checksum, applied_at, app_version, status)
        VALUES (?, ?, ?, ?, 'APPLIED')
    """, (migration_id, checksum, now_iso, app_version))
    conn.commit()
    logger.info(f"Migration {migration_id} applied successfully.")
    return True


# ----------------------------------------------------------------------
# Migration 0001: Baseline Schema
# ----------------------------------------------------------------------
def _migration_0001(conn: sqlite3.Connection) -> None:
    """Marks baseline schema as tracked and ensures base tables exist."""
    pass  # Handled by base schema initialization


# ----------------------------------------------------------------------
# Migration 0002: Truth Layer Invariants & Quarantine (P0-01, P0-04, P0-02)
# ----------------------------------------------------------------------
def _migration_0002(conn: sqlite3.Connection) -> None:
    """
    1. Quarantines fabricated fundamentals (18.5, 0.12, 22.0) by resetting to NULL.
    2. Deduplicates forecast_audit_ledger keeping earliest record per key.
    3. Adds model_version column & unique index on forecast_audit_ledger.
    4. Quarantines corrupted legacy backtests with status 'LEGACY_INVALID_VALUATION'.
    5. Ensures corporate_action_adjustments ledger table exists.
    """
    # 1. Reset fabricated defaults in quant_factors_daily
    cursor = conn.execute("""
        UPDATE quant_factors_daily
        SET roe_pct = NULL, debt_to_equity = NULL, opm_pct = NULL
        WHERE roe_pct = 18.5 AND debt_to_equity = 0.12 AND opm_pct = 22.0;
    """)
    quarantined_factors = cursor.rowcount
    logger.info(f"Quarantined {quarantined_factors} factor rows with fabricated fundamental defaults.")

    # 2. Ensure model_version column exists on forecast_audit_ledger
    f_cols = {row[1] for row in conn.execute("PRAGMA table_info(forecast_audit_ledger)").fetchall()}
    if "model_version" not in f_cols:
        conn.execute("ALTER TABLE forecast_audit_ledger ADD COLUMN model_version TEXT NOT NULL DEFAULT 'garch_ou_v1';")
    if "status" not in f_cols:
        conn.execute("ALTER TABLE forecast_audit_ledger ADD COLUMN status TEXT NOT NULL DEFAULT 'PENDING_MATURITY';")
        conn.execute("UPDATE forecast_audit_ledger SET status = 'EVALUATED' WHERE evaluated_at IS NOT NULL;")

    # 3. Deduplicate forecast_audit_ledger (keep row with min id for each logical key)
    conn.execute("""
        DELETE FROM forecast_audit_ledger
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM forecast_audit_ledger
            GROUP BY symbol, prediction_date, horizon_days, model_version
        );
    """)

    # 4. Create unique index on forecast_audit_ledger
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_forecast_ledger_unique_run
        ON forecast_audit_ledger(symbol, prediction_date, horizon_days, model_version);
    """)

    # 5. Quarantine legacy corrupted backtest runs (e.g. 99.99% drawdown runs)
    cur_bt = conn.execute("PRAGMA table_info(backtest_runs);")
    bt_cols = {row[1] if isinstance(row, tuple) else row["name"] for row in cur_bt.fetchall()}
    if "status" not in bt_cols:
        conn.execute("ALTER TABLE backtest_runs ADD COLUMN status TEXT DEFAULT 'COMPLETED';")
    if "max_drawdown_pct" in bt_cols:
        conn.execute("""
            UPDATE backtest_runs
            SET status = 'LEGACY_INVALID_VALUATION'
            WHERE max_drawdown_pct > 90.0;
        """)

    # 6. Corporate Action Adjustments Ledger
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corporate_action_adjustments (
            id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            ex_date TEXT NOT NULL,
            action_type TEXT NOT NULL,
            ratio REAL NOT NULL,
            multiplier REAL NOT NULL,
            applied_at TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ca_adj_symbol_date ON corporate_action_adjustments(symbol, ex_date);")


# ----------------------------------------------------------------------
# Migration 0003: Adaptive ML Foundation & Supervisor Tables (Stage A1)
# ----------------------------------------------------------------------
def _migration_0003(conn: sqlite3.Connection) -> None:
    """Creates the Adaptive ML and deterministic MIL Supervisor schema tables."""
    # 1. Feature Definitions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_definitions (
            feature_name TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            dtype TEXT NOT NULL,
            unit TEXT NOT NULL,
            formula TEXT NOT NULL,
            pit_rule TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # 2. Feature Snapshots (Immutable point-in-time features)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feature_snapshots (
            snapshot_id TEXT PRIMARY KEY,
            symbol TEXT NOT NULL,
            trading_date TEXT NOT NULL,
            feature_version TEXT NOT NULL,
            features_json TEXT NOT NULL,
            snapshot_hash TEXT NOT NULL,
            available_at TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fs_sym_date ON feature_snapshots(symbol, trading_date);")

    # 3. Label Definitions
    conn.execute("""
        CREATE TABLE IF NOT EXISTS label_definitions (
            label_name TEXT PRIMARY KEY,
            version TEXT NOT NULL,
            horizon_sessions INTEGER NOT NULL,
            benchmark_id TEXT NOT NULL,
            cost_bps REAL NOT NULL,
            formula TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # 4. Training Examples (Matured & pending training labels)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS training_examples (
            example_id TEXT PRIMARY KEY,
            snapshot_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            signal_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            label_version TEXT NOT NULL,
            realized_excess_ret REAL,
            status TEXT NOT NULL, -- PENDING / MATURED / CENSORED / INVALID
            reason_code TEXT,
            created_at TEXT NOT NULL,
            matured_at TEXT,
            FOREIGN KEY (snapshot_id) REFERENCES feature_snapshots(snapshot_id)
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_te_sym_signal ON training_examples(symbol, signal_date);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_te_status ON training_examples(status);")

    # 5. Model Registry (Champions, Challengers, Baselines)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_registry (
            model_id TEXT PRIMARY KEY,
            model_name TEXT NOT NULL,
            model_version TEXT NOT NULL,
            task_type TEXT NOT NULL, -- REGRESSION / CLASSIFICATION
            status TEXT NOT NULL,    -- CANDIDATE / SHADOW_CHALLENGER / CHAMPION / RETIRED
            artifact_path TEXT,
            artifact_hash TEXT,
            train_start TEXT NOT NULL,
            train_end TEXT NOT NULL,
            metrics_json TEXT NOT NULL,
            approved_by TEXT,
            rollback_model_id TEXT,
            created_at TEXT NOT NULL
        );
    """)

    # 6. Model Predictions (Shadow & Active inference)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_predictions (
            prediction_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            snapshot_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            prediction_date TEXT NOT NULL,
            target_date TEXT NOT NULL,
            predicted_value REAL NOT NULL,
            predicted_prob REAL,
            is_shadow INTEGER NOT NULL DEFAULT 1,
            realized_value REAL,
            evaluated_at TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (model_id) REFERENCES model_registry(model_id),
            FOREIGN KEY (snapshot_id) REFERENCES feature_snapshots(snapshot_id)
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mp_model_sym ON model_predictions(model_id, symbol);")

    # 7. Drift Events Ledger
    conn.execute("""
        CREATE TABLE IF NOT EXISTS drift_events (
            event_id TEXT PRIMARY KEY,
            model_id TEXT NOT NULL,
            detected_at TEXT NOT NULL,
            drift_type TEXT NOT NULL, -- FEATURE / PREDICTION / CONCEPT
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            threshold REAL NOT NULL,
            status TEXT NOT NULL      -- ALERT / MITIGATED / DISMISSED
        );
    """)

    # 8. Deterministic Supervisor Jobs Queue
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_jobs (
            job_id TEXT PRIMARY KEY,
            idempotency_key TEXT UNIQUE NOT NULL,
            action_type TEXT NOT NULL,
            status TEXT NOT NULL, -- QUEUED / RUNNING / COMPLETED / FAILED / PAUSED
            priority INTEGER NOT NULL DEFAULT 50,
            retry_count INTEGER NOT NULL DEFAULT 0,
            max_retries INTEGER NOT NULL DEFAULT 3,
            payload_json TEXT,
            reason TEXT,
            actor TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sj_status_priority ON supervisor_jobs(status, priority DESC);")

    # 9. Supervisor State Machine & Telemetry Ledger
    conn.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_state (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            current_state TEXT NOT NULL DEFAULT 'NORMAL',
            active_model_id TEXT,
            last_transition_at TEXT NOT NULL,
            transition_reason TEXT,
            quarantined_symbols_json TEXT DEFAULT '[]',
            auto_retrain_enabled INTEGER NOT NULL DEFAULT 1,
            updated_at TEXT
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS supervisor_telemetry_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            threshold_breached INTEGER NOT NULL DEFAULT 0,
            severity TEXT NOT NULL DEFAULT 'INFO',
            message TEXT,
            context_json TEXT
        );
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS model_predictions_shadow (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            model_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            horizon_days INTEGER NOT NULL,
            predicted_excess_return REAL NOT NULL,
            predicted_prob_up REAL,
            confidence_interval_low REAL,
            confidence_interval_high REAL,
            features_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_mps_model_date ON model_predictions_shadow(model_id, as_of_date);")


ALL_MIGRATIONS: List[Tuple[str, Callable[[sqlite3.Connection], None]]] = [
    ("0001_baseline_schema", _migration_0001),
    ("0002_truth_layer_invariants", _migration_0002),
    ("0003_adaptive_ml_and_supervisor", _migration_0003),
]


def run_all_migrations(conn: sqlite3.Connection) -> int:
    """Runs all unapplied migrations sequentially. Returns number of migrations applied."""
    applied_count = 0
    for mig_id, mig_fn in ALL_MIGRATIONS:
        if apply_migration(conn, mig_id, mig_fn):
            applied_count += 1
    return applied_count
