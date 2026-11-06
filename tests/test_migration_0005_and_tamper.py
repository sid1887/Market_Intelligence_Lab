"""
Tests for Migration 0005, source code checksumming, tamper detection, and rollback safety.
"""

import os
import shutil
import sqlite3
import tempfile
import pytest

from src.storage.migrations import (
    apply_migration,
    run_all_migrations,
    get_applied_migrations,
    compute_migration_checksum,
    _migration_0005,
)


def test_migration_0005_quarantines_and_reconciles_eq(tmp_path):
    """Verifies that Migration 0005 adds evidence columns, quarantines fabricated disclosures, and reconciles EQ orphans."""
    db_path = str(tmp_path / "test_migration.db")
    # Copy from production db to verify real data structures
    shutil.copy2("data/market_lab.db", db_path)

    conn = sqlite3.connect(db_path)
    # Ensure migration 0005 executes cleanly
    run_all_migrations(conn)

    cur = conn.cursor()

    # 1. Check evidence columns on corporate_disclosures
    cur.execute("PRAGMA table_info(corporate_disclosures);")
    cols = {row[1] for row in cur.fetchall()}
    for expected_col in [
        "source_provider", "source_response_id", "document_retrieved_at",
        "document_sha256", "http_status", "mime_type", "document_size_bytes",
        "parser_version", "verification_method", "verification_actor", "verification_timestamp"
    ]:
        assert expected_col in cols, f"Missing evidence column: {expected_col}"

    # 2. Check audit ledger table
    cur.execute("SELECT count(*) FROM corporate_disclosure_audit_events")
    audit_count = cur.fetchone()[0]
    assert audit_count >= 25

    # 3. Check quarantined disclosures
    cur.execute("""
        SELECT count(*) FROM corporate_disclosures 
        WHERE verification_status = 'SYNTHETIC_SEED_QUARANTINED'
    """)
    quarantined = cur.fetchone()[0]
    assert quarantined >= 25

    # Check that operating_margin_pct is NULL for all quarantined rows
    cur.execute("""
        SELECT count(*) FROM corporate_disclosures 
        WHERE verification_status = 'SYNTHETIC_SEED_QUARANTINED' AND operating_margin_pct IS NOT NULL
    """)
    assert cur.fetchone()[0] == 0

    # 4. Check model registry metric validity
    cur.execute("PRAGMA table_info(model_registry);")
    mr_cols = {row[1] for row in cur.fetchall()}
    assert "metric_validity" in mr_cols

    cur.execute("""
        SELECT count(*) FROM model_registry
        WHERE metric_validity = 'INVALIDATED_FAULTY_SHARPE'
    """)
    invalidated = cur.fetchone()[0]
    assert invalidated >= 7

    # 5. Check orphan factors without EQ
    cur.execute("SELECT count(*) FROM quant_factors_daily WHERE is_orphaned = 1")
    orphans = cur.fetchone()[0]
    assert orphans >= 168000
    conn.close()


def test_migration_tamper_detection(tmp_path):
    """Verifies that altering a migration's source code raises RuntimeError upon integrity check."""
    db_path = str(tmp_path / "tamper_test.db")
    conn = sqlite3.connect(db_path)

    def dummy_action_v1(c):
        c.execute("CREATE TABLE test_table (id INTEGER PRIMARY KEY);")

    # Apply v1
    mig_id = "9999_test_dummy_migration"
    applied = apply_migration(conn, mig_id, dummy_action_v1)
    assert applied is True

    # Re-running same unmodified action should return False (already applied, checksum matches)
    re_applied = apply_migration(conn, mig_id, dummy_action_v1)
    assert re_applied is False

    # Tampered action with different source code
    def dummy_action_v2_tampered(c):
        # Tampered code body
        c.execute("CREATE TABLE test_table_tampered (id INTEGER PRIMARY KEY);")

    # Re-running tampered action MUST raise RuntimeError
    with pytest.raises(RuntimeError, match="Migration integrity violation"):
        apply_migration(conn, mig_id, dummy_action_v2_tampered)

    conn.close()


def test_migration_rollback_on_failure(tmp_path):
    """Verifies that if an error occurs inside a migration action, changes are rolled back cleanly."""
    db_path = str(tmp_path / "rollback_test.db")
    conn = sqlite3.connect(db_path)

    def failing_action(c):
        c.execute("CREATE TABLE half_baked (id INT);")
        raise ValueError("Simulated migration failure mid-transaction")

    mig_id = "9998_failing_migration"
    with pytest.raises(ValueError, match="Simulated migration failure"):
        apply_migration(conn, mig_id, failing_action)

    # Check table was NOT created (rolled back)
    cur = conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='half_baked'")
    assert cur.fetchone() is None

    # Check migration was NOT logged as APPLIED
    applied = get_applied_migrations(conn)
    assert mig_id not in applied
    conn.close()
