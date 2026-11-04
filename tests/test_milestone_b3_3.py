"""
Market Intelligence Lab — Milestone B3.3 Unit Tests.

Comprehensive regression and acceptance test suite for Milestone B3.3:
- Deterministic Fundamental Ratio Calculators (TTM P/E, ROE, Debt-to-Equity, OPM %)
- True Assurance Status Preservation (is_audited=False for limited review/unaudited; True only for audited)
- Database Idempotency & Re-statement Upsert Resilience
- Schema Alignment for financial_statements_quarterly and annual
"""

import unittest
import os
import sqlite3
import datetime

from src.storage.database import DatabaseManager
from src.client.fundamentals_client import FundamentalsClient
from src.quant.fundamentals import (
    calculate_ttm_pe_ratio,
    calculate_roe,
    calculate_debt_to_equity,
    calculate_opm
)


class TestMilestoneB33FundamentalsAndRatios(unittest.TestCase):
    """
    Test suite validating B3.3 fundamental data layer completeness,
    ratio accuracy, and assurance status governance.
    """

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.client = FundamentalsClient(self.db)

    # -------------------------------------------------------------
    # 1. Deterministic Ratio Calculations & Edge Cases
    # -------------------------------------------------------------

    def test_ttm_pe_ratio_standard_and_guards(self):
        """1. Verify TTM P/E calculation and non-positive earnings safeguards."""
        # Standard positive P/E
        pe = calculate_ttm_pe_ratio(current_price=1500.0, ttm_eps=60.0)
        self.assertEqual(pe, 25.0)

        # Decimal precision check
        pe_dec = calculate_ttm_pe_ratio(current_price=1487.45, ttm_eps=63.66)
        self.assertEqual(pe_dec, 23.37)

        # Zero or negative EPS must return None (safeguard against non-sensical negative P/E)
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=1500.0, ttm_eps=0.0))
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=1500.0, ttm_eps=-12.5))
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=None, ttm_eps=50.0))
        self.assertIsNone(calculate_ttm_pe_ratio(current_price=1500.0, ttm_eps=None))

    def test_roe_standard_and_negative_equity_guard(self):
        """2. Verify ROE calculation and negative net worth safeguards."""
        # Standard ROE (percentage)
        # Net profit = 10,000 Cr, Total Equity = 50,000 Cr -> 20.0%
        roe = calculate_roe(net_profit_annualized=10000.0, total_equity=50000.0, as_percentage=True)
        self.assertEqual(roe, 20.0)

        # Decimal ratio format
        roe_dec = calculate_roe(net_profit_annualized=10000.0, total_equity=50000.0, as_percentage=False)
        self.assertEqual(roe_dec, 0.2000)

        # Negative net worth / equity guard
        self.assertIsNone(calculate_roe(net_profit_annualized=1000.0, total_equity=-5000.0))
        self.assertIsNone(calculate_roe(net_profit_annualized=1000.0, total_equity=0.0))
        self.assertIsNone(calculate_roe(net_profit_annualized=None, total_equity=50000.0))

    def test_debt_to_equity_zero_debt_and_guards(self):
        """3. Verify Debt-to-Equity calculation, zero debt handling, and equity guards."""
        # Standard leverage: Debt = 25,000 Cr, Equity = 50,000 Cr -> 0.5000
        de = calculate_debt_to_equity(total_debt=25000.0, total_equity=50000.0)
        self.assertEqual(de, 0.5000)

        # Debt-free company (Debt = 0.0 or None) -> 0.0000
        de_zero = calculate_debt_to_equity(total_debt=0.0, total_equity=50000.0)
        self.assertEqual(de_zero, 0.0)

        de_none_debt = calculate_debt_to_equity(total_debt=None, total_equity=50000.0)
        self.assertEqual(de_none_debt, 0.0)

        # Negative equity guard -> None
        self.assertIsNone(calculate_debt_to_equity(total_debt=1000.0, total_equity=-200.0))
        self.assertIsNone(calculate_debt_to_equity(total_debt=1000.0, total_equity=0.0))

    def test_opm_standard_and_revenue_guards(self):
        """4. Verify Operating Profit Margin (OPM %) calculation and non-positive revenue guards."""
        # Standard OPM: EBITDA = 5,000 Cr, Revenue = 20,000 Cr -> 25.0%
        opm = calculate_opm(ebitda=5000.0, revenue=20000.0, as_percentage=True)
        self.assertEqual(opm, 25.0)

        # Decimal format
        opm_dec = calculate_opm(ebitda=5000.0, revenue=20000.0, as_percentage=False)
        self.assertEqual(opm_dec, 0.2500)

        # Zero or negative revenue -> None
        self.assertIsNone(calculate_opm(ebitda=500.0, revenue=0.0))
        self.assertIsNone(calculate_opm(ebitda=500.0, revenue=-1000.0))
        self.assertIsNone(calculate_opm(ebitda=None, revenue=20000.0))

    # -------------------------------------------------------------
    # 2. Assurance Status Governance & Never Mislabeled Safeguard
    # -------------------------------------------------------------

    def test_assurance_status_governance_un_audited_not_mislabeled(self):
        """5. Verify un-audited/limited-review quarterly statements are never blanket-labeled as audited."""
        mock_quarterly_statements = [
            {
                "symbol": "INFY",
                "period_end_date": "2026-06-30",
                "filing_date": "2026-07-23",
                "audit_status": "UNAUDITED",
                "revenue": 43800.0,
                "ebitda": 10500.0,
                "net_profit": 7100.0,
                "eps": 17.11,
                "total_debt": 0.0,
                "total_equity": 91200.0
            },
            {
                "symbol": "INFY",
                "period_end_date": "2026-09-30",
                "filing_date": "2026-10-23",
                "audit_status": "LIMITED_REVIEW",
                "revenue": 49244.0,
                "ebitda": 11800.0,
                "net_profit": 6506.0,
                "eps": 15.68,
                "total_debt": 0.0,
                "total_equity": 89200.0
            },
            {
                "symbol": "INFY",
                "period_end_date": "2026-03-31",
                "filing_date": "2026-04-16",
                "audit_status": "AUDITED",
                "revenue": 46402.0,
                "ebitda": 11200.0,
                "net_profit": 8501.0,
                "eps": 20.48,
                "total_debt": 0.0,
                "total_equity": 91400.0
            }
        ]

        self.client.ingest_quarterly_statements(mock_quarterly_statements)

        records = self.db.get_financial_statements_quarterly("INFY")
        self.assertEqual(len(records), 3)

        records_by_date = {r["period_end_date"]: r for r in records}

        # Q1 (UNAUDITED) must be is_audited = 0
        self.assertEqual(records_by_date["2026-06-30"]["is_audited"], 0, "UNAUDITED filing must not be labeled audited")

        # Q2 (LIMITED_REVIEW) must be is_audited = 0
        self.assertEqual(records_by_date["2026-09-30"]["is_audited"], 0, "LIMITED_REVIEW filing must not be labeled audited")

        # Q4 (AUDITED) must be is_audited = 1
        self.assertEqual(records_by_date["2026-03-31"]["is_audited"], 1, "AUDITED filing must have is_audited = 1")

    # -------------------------------------------------------------
    # 3. Idempotent Upserts & Restatements
    # -------------------------------------------------------------

    def test_statement_upsert_idempotency_and_restatements(self):
        """6. Verify re-statements or corrections update existing rows on conflict without duplicates."""
        initial_stmt = {
            "symbol": "TCS",
            "period_end_date": "2026-03-31",
            "filing_date": "2026-04-15",
            "is_audited": 1,
            "revenue": 62000.0,
            "ebitda": 15000.0,
            "net_profit": 12000.0,
            "eps": 33.15,
            "total_debt": 0.0,
            "total_equity": 95000.0
        }
        self.client.ingest_annual_statements([initial_stmt])

        # Verify initial insertion
        stmts = self.db.get_financial_statements_annual("TCS")
        self.assertEqual(len(stmts), 1)
        self.assertEqual(stmts[0]["revenue"], 62000.0)

        # Restatement with updated audited revenue and net profit
        restated_stmt = dict(initial_stmt)
        restated_stmt["revenue"] = 62613.0
        restated_stmt["net_profit"] = 12434.0
        restated_stmt["filing_date"] = "2026-04-30"

        # Must execute without error and update row in-place
        self.client.ingest_annual_statements([restated_stmt])

        stmts_after = self.db.get_financial_statements_annual("TCS")
        self.assertEqual(len(stmts_after), 1, "Must update in place on (symbol, period_end_date) conflict")
        self.assertEqual(stmts_after[0]["revenue"], 62613.0)
        self.assertEqual(stmts_after[0]["net_profit"], 12434.0)
        self.assertEqual(stmts_after[0]["filing_date"], "2026-04-30")

    # -------------------------------------------------------------
    # 4. Schema Alignment & Database Integrity
    # -------------------------------------------------------------

    def test_schema_alignment_and_table_integrity(self):
        """7. Verify table schema DDL, foreign keys, and indexes in schema_v3."""
        with self.db.get_connection() as conn:
            # Check quarterly table
            cursor = conn.execute("PRAGMA table_info(financial_statements_quarterly);")
            cols_q = {r["name"]: r["type"] for r in cursor.fetchall()}
            for expected_col in ("symbol", "period_end_date", "filing_date", "is_audited", "revenue", "ebitda", "net_profit", "eps", "total_debt", "total_equity"):
                self.assertIn(expected_col, cols_q)
                if expected_col in ("revenue", "ebitda", "net_profit", "eps", "total_debt", "total_equity"):
                    self.assertEqual(cols_q[expected_col], "REAL")

            # Check annual table
            cursor = conn.execute("PRAGMA table_info(financial_statements_annual);")
            cols_a = {r["name"]: r["type"] for r in cursor.fetchall()}
            for expected_col in ("symbol", "period_end_date", "filing_date", "is_audited", "revenue", "ebitda", "net_profit", "eps", "total_debt", "total_equity"):
                self.assertIn(expected_col, cols_a)
                if expected_col in ("revenue", "ebitda", "net_profit", "eps", "total_debt", "total_equity"):
                    self.assertEqual(cols_a[expected_col], "REAL")

            # Check indexes
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_fsq_symbol_period';")
            self.assertIsNotNone(cursor.fetchone())
            cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_fsa_symbol_period';")
            self.assertIsNotNone(cursor.fetchone())


if __name__ == "__main__":
    unittest.main()
