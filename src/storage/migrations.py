"""
Market Intelligence Lab — Schema Migration & Truth Quarantine Engine.
ADR-0011, ADR-0012, P1-01.

Provides numbered, immutable schema migrations tracked in `schema_migrations`.
Guarantees database consistency, deduplication, and truth-quarantine tracking.
"""

import hashlib
import inspect
import json
import logging
import os
import sqlite3
import uuid
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


def compute_migration_checksum(action: Callable[[sqlite3.Connection], None]) -> str:
    """Computes a deterministic 16-character SHA-256 hash of the migration function source code."""
    try:
        source_code = inspect.getsource(action)
        return hashlib.sha256(source_code.encode("utf-8")).hexdigest()[:16]
    except Exception:
        fn_name = getattr(action, "__name__", str(action))
        return hashlib.sha256(fn_name.encode("utf-8")).hexdigest()[:16]


def apply_migration(
    conn: sqlite3.Connection,
    migration_id: str,
    action: Callable[[sqlite3.Connection], None],
    app_version: str = "0.3.0"
) -> bool:
    """Applies a migration within an isolated transaction and validates checksum integrity."""
    init_migrations_table(conn)
    cursor = conn.execute("SELECT checksum FROM schema_migrations WHERE migration_id = ? AND status = 'APPLIED'", (migration_id,))
    row = cursor.fetchone()

    current_checksum = compute_migration_checksum(action)
    legacy_checksum = hashlib.sha256(migration_id.encode("utf-8")).hexdigest()[:16]

    if row:
        stored_checksum = row[0]
        # Backwards compatibility for migrations 0001-0004 previously applied under ID hashing
        if stored_checksum != current_checksum and stored_checksum != legacy_checksum:
            raise RuntimeError(
                f"Migration integrity violation: Migration '{migration_id}' was previously applied with checksum "
                f"'{stored_checksum}', but the current source code checksum is '{current_checksum}'."
            )
        return False

    logger.info(f"Applying migration: {migration_id} (source hash: {current_checksum})")
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        if not conn.in_transaction:
            conn.execute("BEGIN TRANSACTION")
        action(conn)
        conn.execute("""
            INSERT INTO schema_migrations (migration_id, checksum, applied_at, app_version, status)
            VALUES (?, ?, ?, ?, 'APPLIED')
        """, (migration_id, current_checksum, now_iso, app_version))
        conn.commit()
    except Exception as e:
        if conn.in_transaction:
            conn.rollback()
        logger.error(f"Migration {migration_id} failed: {e}")
        raise

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


# ----------------------------------------------------------------------
# Migration 0004: Data Provenance & Synthetic Quarantine (MIL-P0-001, MIL-DATA-001)
# ----------------------------------------------------------------------
def _migration_0004(conn: sqlite3.Connection) -> None:
    """
    1. Adds data provenance and eligibility columns to ohlcv_daily:
       provenance_class, is_synthetic, is_eligible_for_live_analytics,
       is_eligible_for_backtest, is_eligible_for_training.
    2. Quarantines synthetic rows from offline_multi_regime_generator, watchlist_backfill_24m,
       and synthetic dynamic_ingestion_24m:
       sets is_synthetic = 1, provenance_class = 'SYNTHETIC_TEST', and eligibility flags = 0.
    3. Ensures is_orphaned column on quant_factors_daily is added and indexed.
    4. Flags factor records without matching ohlcv_daily records as is_orphaned = 1.
    """
    cursor = conn.execute("PRAGMA table_info(ohlcv_daily);")
    cols = {row["name"] for row in cursor.fetchall()}

    if "provenance_class" not in cols:
        conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN provenance_class TEXT NOT NULL DEFAULT 'EXCHANGE_OFFICIAL';")
    if "is_synthetic" not in cols:
        conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN is_synthetic INTEGER NOT NULL DEFAULT 0;")
    if "is_eligible_for_live_analytics" not in cols:
        conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN is_eligible_for_live_analytics INTEGER NOT NULL DEFAULT 1;")
    if "is_eligible_for_backtest" not in cols:
        conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN is_eligible_for_backtest INTEGER NOT NULL DEFAULT 1;")
    if "is_eligible_for_training" not in cols:
        conn.execute("ALTER TABLE ohlcv_daily ADD COLUMN is_eligible_for_training INTEGER NOT NULL DEFAULT 1;")

    # Quarantine synthetic rows
    cursor_q = conn.execute("""
        UPDATE ohlcv_daily
        SET is_synthetic = 1,
            provenance_class = 'SYNTHETIC_TEST',
            is_eligible_for_live_analytics = 0,
            is_eligible_for_backtest = 0,
            is_eligible_for_training = 0
        WHERE source IN ('offline_multi_regime_generator', 'watchlist_backfill_24m')
           OR source LIKE '%synthetic%'
           OR source = 'dynamic_ingestion_24m';
    """)
    quarantined_bars = cursor_q.rowcount
    logger.info(f"Quarantined {quarantined_bars} synthetic OHLCV rows.")

    # Quarantine orphan factors
    qf_cursor = conn.execute("PRAGMA table_info(quant_factors_daily);")
    qf_cols = {row["name"] for row in qf_cursor.fetchall()}
    if "is_orphaned" not in qf_cols:
        conn.execute("ALTER TABLE quant_factors_daily ADD COLUMN is_orphaned INTEGER NOT NULL DEFAULT 0;")

    conn.execute("""
        UPDATE quant_factors_daily
        SET is_orphaned = 1
        WHERE NOT EXISTS (
            SELECT 1 FROM ohlcv_daily o 
            WHERE o.symbol = quant_factors_daily.symbol 
              AND o.trading_date = quant_factors_daily.trading_date
        );
    """)

    conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_provenance ON ohlcv_daily(symbol, trading_date, is_synthetic, is_eligible_for_live_analytics);")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_qf_orphaned ON quant_factors_daily(symbol, trading_date, is_orphaned);")


# ----------------------------------------------------------------------
# Migration 0005: Corporate Disclosures Truth & EQ Reconciliation (P0-Remediation)
# ----------------------------------------------------------------------
def _migration_0005(conn: sqlite3.Connection) -> None:
    """
    1. Adds 11 evidence columns to corporate_disclosures for cryptographic verification:
       source_provider, source_response_id, document_retrieved_at, document_sha256,
       http_status, mime_type, document_size_bytes, parser_version,
       verification_method, verification_actor, verification_timestamp.
    2. Creates corporate_disclosure_audit_events table for append-only audit trail.
    3. Quarantines 25 fabricated corporate disclosures in corporate_disclosures:
       sets verification_status = 'SYNTHETIC_SEED_QUARANTINED', operating_margin_pct = NULL,
       and logs append-only audit event for each row.
    4. Adds metric_validity column to model_registry and invalidates historical
       faulty Sharpe baseline models.
    5. Reconciles quant_factors_daily.is_orphaned where no ohlcv_daily row with series = 'EQ' exists.
    """
    now_iso = datetime.now(timezone.utc).isoformat()

    # 1. Add evidence columns to corporate_disclosures
    cur = conn.execute("PRAGMA table_info(corporate_disclosures);")
    cd_cols = {row[1] if isinstance(row, tuple) else row["name"] for row in cur.fetchall()}

    evidence_columns = [
        ("source_provider", "TEXT"),
        ("source_response_id", "TEXT"),
        ("document_retrieved_at", "TEXT"),
        ("document_sha256", "TEXT"),
        ("http_status", "INTEGER"),
        ("mime_type", "TEXT"),
        ("document_size_bytes", "INTEGER"),
        ("parser_version", "TEXT"),
        ("verification_method", "TEXT"),
        ("verification_actor", "TEXT"),
        ("verification_timestamp", "TEXT"),
    ]
    for col_name, col_type in evidence_columns:
        if col_name not in cd_cols:
            conn.execute(f"ALTER TABLE corporate_disclosures ADD COLUMN {col_name} {col_type};")

    # 2. Create corporate_disclosure_audit_events table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS corporate_disclosure_audit_events (
            event_id TEXT PRIMARY KEY,
            disclosure_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            actor TEXT NOT NULL,
            details_json TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_cdae_disc_id 
        ON corporate_disclosure_audit_events(disclosure_id);
    """)

    # 3. Find and quarantine fabricated corporate disclosures
    cur_fab = conn.execute("""
        SELECT disclosure_id, symbol, category, subject, source_url, operating_margin_pct
        FROM corporate_disclosures
        WHERE symbol IN ('CANBK', 'IDEA', 'NHPC', 'RVNL', 'TATAPOWER')
          AND (disclosure_id LIKE '%_DISC_2026%' OR source_url LIKE '%archives.nseindia.com%');
    """)
    fabricated_rows = cur_fab.fetchall()

    for r in fabricated_rows:
        disc_id = r[0] if isinstance(r, tuple) else r["disclosure_id"]
        sym = r[1] if isinstance(r, tuple) else r["symbol"]
        event_id = f"cdae_quarantine_{uuid.uuid4().hex[:12]}"
        audit_details = json.dumps({
            "action": "QUARANTINE_FABRICATED_DISCLOSURE",
            "symbol": sym,
            "previous_status": "VERIFIED",
            "reason": "Eliminated fictional exchange filing with hardcoded 18.5% OPM seeded by legacy fallback.",
            "rule": "ADR-0001, ADR-0012, P0-Audit"
        })
        conn.execute("""
            INSERT INTO corporate_disclosure_audit_events (
                event_id, disclosure_id, event_type, actor, details_json, created_at
            ) VALUES (?, ?, 'QUARANTINE', 'SYSTEM_MIGRATION_ENGINE', ?, ?)
        """, (event_id, disc_id, audit_details, now_iso))

    cursor_q = conn.execute("""
        UPDATE corporate_disclosures
        SET verification_status = 'SYNTHETIC_SEED_QUARANTINED',
            operating_margin_pct = NULL,
            verification_method = 'AUDIT_QUARANTINE_MIGRATION_0005',
            verification_actor = 'SYSTEM_MIGRATION_ENGINE',
            verification_timestamp = ?
        WHERE symbol IN ('CANBK', 'IDEA', 'NHPC', 'RVNL', 'TATAPOWER')
          AND (disclosure_id LIKE '%_DISC_2026%' OR source_url LIKE '%archives.nseindia.com%');
    """, (now_iso,))
    logger.info(f"Quarantined {cursor_q.rowcount} fabricated corporate disclosures.")

    # 4. Invalidate faulty baseline Sharpe models in model_registry
    mr_cur = conn.execute("PRAGMA table_info(model_registry);")
    mr_cols = {row[1] if isinstance(row, tuple) else row["name"] for row in mr_cur.fetchall()}
    if "metric_validity" not in mr_cols:
        conn.execute("ALTER TABLE model_registry ADD COLUMN metric_validity TEXT NOT NULL DEFAULT 'VALID';")

    conn.execute("""
        UPDATE model_registry
        SET metric_validity = 'INVALIDATED_FAULTY_SHARPE'
        WHERE model_name = 'ZeroReturnBaseline'
          AND (
              metrics_json LIKE '%"validation_sharpe": 1.405%'
              OR metrics_json LIKE '%"validation_sharpe": 0.13%'
          );
    """)

    # 5. Reconcile quant_factors_daily orphans with series = 'EQ'
    conn.execute("""
        UPDATE quant_factors_daily
        SET is_orphaned = 1
        WHERE NOT EXISTS (
            SELECT 1 FROM ohlcv_daily o 
            WHERE o.symbol = quant_factors_daily.symbol 
              AND o.trading_date = quant_factors_daily.trading_date
              AND o.series = 'EQ'
        );
    """)


ALL_MIGRATIONS: List[Tuple[str, Callable[[sqlite3.Connection], None]]] = [
    ("0001_baseline_schema", _migration_0001),
    ("0002_truth_layer_invariants", _migration_0002),
    ("0003_adaptive_ml_and_supervisor", _migration_0003),
    ("0004_data_provenance_and_synthetic_quarantine", _migration_0004),
    ("0005_corporate_disclosures_truth_and_eq_reconciliation", _migration_0005),
]


def run_all_migrations(conn: sqlite3.Connection) -> int:
    """Runs all unapplied migrations sequentially. Returns number of migrations applied."""
    applied_count = 0
    for mig_id, mig_fn in ALL_MIGRATIONS:
        if apply_migration(conn, mig_id, mig_fn):
            applied_count += 1
    return applied_count
