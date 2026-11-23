"""
tests/test_temporal_guard.py
Regression tests for TemporalInvariantGuard and Point-in-Time causality rules.
"""

import pytest
from src.storage.database import DatabaseManager
from src.storage.temporal_guard import TemporalInvariantGuard


def test_temporal_invariant_guard_clean_db(tmp_path):
    db_file = tmp_path / "test_pit.db"
    db = DatabaseManager(str(db_file))
    guard = TemporalInvariantGuard(db)

    report = guard.run_full_temporal_audit()
    assert report["overall_status"] == "PASS"
    assert report["financial_statements"]["cfs_violations_quarantined"] == 0
    assert report["quant_factors"]["future_leaks_qf"] == 0


def test_temporal_guard_quarantines_causality_violation(tmp_path):
    db_file = tmp_path / "test_pit_violation.db"
    db = DatabaseManager(str(db_file))

    with db.get_connection() as conn:
        conn.execute("""
            INSERT OR REPLACE INTO securities_master (symbol, company_name, isin, sector, industry, macro_sector, updated_at, is_active)
            VALUES ('TESTSYM', 'Test Company Ltd.', 'INE000000000', 'Information Technology', 'Software', 'Technology', '2026-11-23T00:00:00Z', 1);
        """)
        # Insert statement where publication_date is BEFORE period_end_date (violation)
        conn.execute("""
            INSERT OR REPLACE INTO company_financial_statements (
                statement_id, symbol, period_type, period_nature, fiscal_year, fiscal_quarter,
                period_start_date, period_end_date, publication_date, broadcast_timestamp,
                effective_session_date, source_timestamp_basis, is_pit_eligible, reporting_basis,
                statement_version, audit_status, currency, unit, source, retrieval_timestamp
            ) VALUES (
                'TEST_VIOLATION_01', 'TESTSYM', 'Q1', 'DISCRETE_QUARTER', 2026, 1,
                '2026-04-01', '2026-06-30', '2026-05-15', '2026-05-15T18:00:00+05:30',
                '2026-05-16', 'EXACT_EXCHANGE_TIMESTAMP', 1, 'CONSOLIDATED',
                1, 'AUDITED', 'INR', 'CRORE', 'test', '2026-05-15T19:00:00Z'
            );
        """)
        conn.commit()

    guard = TemporalInvariantGuard(db)
    report = guard.audit_financial_statements()
    assert report["cfs_violations_quarantined"] == 1

    # Verify is_pit_eligible was reset to 0
    with db.get_connection() as conn:
        cur = conn.execute("SELECT is_pit_eligible FROM company_financial_statements WHERE statement_id = 'TEST_VIOLATION_01';")
        assert cur.fetchone()[0] == 0
