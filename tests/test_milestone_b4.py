import unittest
import os
import sqlite3
import tempfile
import datetime
from typing import Dict, Any, List

from src.storage.database import DatabaseManager
from src.client.validator import RecordValidator
from src.quant.fundamentals import FundamentalsEngine
from src.client.fundamentals_client import FundamentalsClient

class TestMilestoneB4(unittest.TestCase):
    """
    Exhaustive deterministic test suite for Milestone B4:
    - Company Financial Statements normalization and publication-time provenance.
    - Point-in-time availability and restatement handling.
    - Discrete vs Cumulative accounting safeguards.
    - Corporate actions per-share and dividend scaling.
    - Sector-aware valuation exclusions (Financials vs Industrials).
    - Negative earnings and equity masking.
    - Cross-sectional sector medians, spreads, and universe valuation deciles.
    - End-to-end ingestion, audit logging, and index valuation updates.
    """

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_b4.db")
        self.db = DatabaseManager(self.db_path)
        self.validator = RecordValidator()
        self.engine = FundamentalsEngine(db_manager=self.db)
        self.client = FundamentalsClient(db_manager=self.db, validator=self.validator, engine=self.engine)

        # Seed minimal master data for testing
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO securities_master (symbol, company_name, isin, industry, sector, macro_sector, is_active, updated_at)
            VALUES
                ('TEST_TECH', 'Test Tech Ltd.', 'INE000000001', 'Software', 'Information Technology', 'Information Technology', 1, ?),
                ('TEST_FIN', 'Test Bank Ltd.', 'INE000000002', 'Private Bank', 'Financial Services', 'Financial Services', 1, ?),
                ('TEST_CORP', 'Test Corp Ltd.', 'INE000000003', 'Software', 'Information Technology', 'Information Technology', 1, ?),
                ('TEST_LOSS', 'Test Loss Maker Ltd.', 'INE000000004', 'Pharma', 'Healthcare', 'Healthcare', 1, ?);
            """, (now_ts, now_ts, now_ts, now_ts))

    def tearDown(self):
        self.temp_dir.cleanup()

    # -------------------------------------------------------------
    # 1. Publication-Time Provenance & Availability Policy
    # -------------------------------------------------------------
    def test_publication_time_intraday_vs_after_hours(self):
        """Exact exchange timestamp: before 15:30 -> same-day session; after 15:30 -> next session."""
        # Intraday statement (14:15 IST)
        stmt_intraday = {
            "statement_id": "STMT_INTRADAY",
            "symbol": "TEST_TECH",
            "period_type": "Q1",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-04-01",
            "period_end_date": "2025-06-30",
            "broadcast_timestamp": "2025-07-15T14:15:00+05:30",
            "source_timestamp_basis": "EXACT_EXCHANGE_TIMESTAMP",
            "total_revenue": 1000.0,
            "net_profit": 200.0
        }
        valid, cleaned, err = self.validator.validate_financial_statement(stmt_intraday)
        self.assertTrue(valid, msg=err)
        self.assertEqual(cleaned["effective_session_date"], "2025-07-15")
        self.assertEqual(cleaned["is_pit_eligible"], 1)

        # After-hours statement (17:45 IST)
        stmt_after_hours = {
            "statement_id": "STMT_AFTER_HOURS",
            "symbol": "TEST_TECH",
            "period_type": "Q2",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-07-01",
            "period_end_date": "2025-09-30",
            "broadcast_timestamp": "2025-10-18T17:45:00+05:30",
            "source_timestamp_basis": "EXACT_EXCHANGE_TIMESTAMP",
            "total_revenue": 1100.0,
            "net_profit": 220.0
        }
        valid, cleaned, err = self.validator.validate_financial_statement(stmt_after_hours)
        self.assertTrue(valid, msg=err)
        self.assertEqual(cleaned["effective_session_date"], "2025-10-19")
        self.assertEqual(cleaned["is_pit_eligible"], 1)

    def test_announcement_date_verified_conservative_t_plus_1(self):
        """Announcement date verified without exact timestamp assigns conservative t+1 session."""
        stmt = {
            "statement_id": "STMT_DATE_ONLY",
            "symbol": "TEST_TECH",
            "period_type": "Q3",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-10-01",
            "period_end_date": "2025-12-31",
            "publication_date": "2026-01-15",
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "total_revenue": 1200.0,
            "net_profit": 240.0
        }
        valid, cleaned, err = self.validator.validate_financial_statement(stmt)
        self.assertTrue(valid, msg=err)
        self.assertEqual(cleaned["effective_session_date"], "2026-01-16")
        self.assertEqual(cleaned["is_pit_eligible"], 1)

    def test_unknown_untimed_strictly_excluded_from_pit(self):
        """Untimed records must have is_pit_eligible = 0 and be ignored by PIT engine."""
        stmt_untimed = {
            "statement_id": "STMT_UNTIMED",
            "symbol": "TEST_TECH",
            "period_type": "Q4",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2026-01-01",
            "period_end_date": "2026-03-31",
            "source_timestamp_basis": "UNKNOWN_UNTIMED",
            "is_pit_eligible": 1,  # Attempting to declare eligible
            "total_revenue": 1300.0,
            "net_profit": 260.0
        }
        valid, cleaned, err = self.validator.validate_financial_statement(stmt_untimed)
        self.assertTrue(valid, msg=err)
        # Safeguard MUST override is_pit_eligible to 0
        self.assertEqual(cleaned["is_pit_eligible"], 0)
        self.assertIsNone(cleaned["effective_session_date"])

        # Persist and verify PIT query ignores it
        self.db.upsert_financial_statements([cleaned])
        pit_stmts = self.engine.get_as_of_statements("TEST_TECH", "2026-05-01", db=self.db)
        self.assertEqual(len(pit_stmts), 0)

    # -------------------------------------------------------------
    # 2. Restatement Handling & Zero Look-Ahead Bias
    # -------------------------------------------------------------
    def test_restatement_point_in_time_isolation(self):
        """Point-in-time query sees original statement before restatement date, and restated version after."""
        # Version 1 published on 2025-07-20
        v1 = {
            "statement_id": "INFY_Q1_26_V1",
            "symbol": "TEST_TECH",
            "period_type": "Q1",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-04-01",
            "period_end_date": "2025-06-30",
            "publication_date": "2025-07-20",
            "effective_session_date": "2025-07-20",
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "statement_version": 1,
            "total_revenue": 1000.0,
            "net_profit": 200.0
        }
        # Version 2 (Restated) published on 2025-09-15
        v2 = {
            "statement_id": "INFY_Q1_26_V2",
            "symbol": "TEST_TECH",
            "period_type": "Q1",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-04-01",
            "period_end_date": "2025-06-30",
            "publication_date": "2025-09-15",
            "effective_session_date": "2025-09-15",
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "statement_version": 2,
            "is_restated": 1,
            "restatement_reason": "Auditor adjustment in deferred tax",
            "total_revenue": 1000.0,
            "net_profit": 180.0
        }

        _, c1, _ = self.validator.validate_financial_statement(v1)
        _, c2, _ = self.validator.validate_financial_statement(v2)
        self.db.upsert_financial_statements([c1, c2])

        # Query on 2025-08-01 (before restatement) -> MUST see version 1 (net_profit = 200.0)
        as_of_aug = self.engine.get_as_of_statements("TEST_TECH", "2025-08-01", db=self.db)
        self.assertEqual(len(as_of_aug), 1)
        self.assertEqual(as_of_aug[0]["statement_version"], 1)
        self.assertEqual(as_of_aug[0]["net_profit"], 200.0)

        # Query on 2025-09-20 (after restatement) -> MUST see version 2 (net_profit = 180.0)
        as_of_sep = self.engine.get_as_of_statements("TEST_TECH", "2025-09-20", db=self.db)
        self.assertEqual(len(as_of_sep), 1)
        self.assertEqual(as_of_sep[0]["statement_version"], 2)
        self.assertEqual(as_of_sep[0]["net_profit"], 180.0)

    def test_restatement_requires_reason(self):
        """Restated statements (version > 1) without a restatement_reason are rejected."""
        v2_bad = {
            "statement_id": "TEST_V2_BAD",
            "symbol": "TEST_TECH",
            "period_type": "Q1",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-04-01",
            "period_end_date": "2025-06-30",
            "publication_date": "2025-09-15",
            "statement_version": 2,
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "restatement_reason": ""  # Missing
        }
        valid, _, err = self.validator.validate_financial_statement(v2_bad)
        self.assertFalse(valid)
        self.assertIn("restatement_reason", err)

    # -------------------------------------------------------------
    # 3. Discrete vs Cumulative Accounting Normalization
    # -------------------------------------------------------------
    def test_cumulative_ytd_rejected_in_ttm_sum(self):
        """compute_ttm_metrics raises ValueError if non-discrete statements are passed."""
        ytd_stmt = {
            "period_nature": "CUMULATIVE_YTD",
            "period_end_date": "2025-12-31",
            "total_revenue": 3000.0,
            "net_profit": 600.0
        }
        with self.assertRaises(ValueError):
            self.engine.compute_ttm_metrics([ytd_stmt])

    def test_ttm_discrete_quarter_summation(self):
        """compute_ttm_metrics sums flow items across 4 discrete quarters and takes latest balance sheet."""
        quarters = [
            {"statement_id": "Q4", "period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-12-31",
             "total_revenue": 1000.0, "ebitda": 250.0, "ebit": 200.0, "net_profit": 150.0,
             "total_equity": 2000.0, "total_debt": 500.0, "cash_and_equivalents": 200.0, "shares_outstanding": 10000000},
            {"statement_id": "Q3", "period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-09-30",
             "total_revenue": 950.0, "ebitda": 240.0, "ebit": 190.0, "net_profit": 140.0},
            {"statement_id": "Q2", "period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-06-30",
             "total_revenue": 900.0, "ebitda": 230.0, "ebit": 180.0, "net_profit": 130.0},
            {"statement_id": "Q1", "period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-03-31",
             "total_revenue": 850.0, "ebitda": 220.0, "ebit": 170.0, "net_profit": 120.0},
        ]
        ttm = self.engine.compute_ttm_metrics(quarters)
        self.assertEqual(ttm["statements_count_ttm"], 4)
        self.assertIsNone(ttm["data_quality_flag"])
        self.assertEqual(ttm["ttm_revenue"], 3700.0)
        self.assertEqual(ttm["ttm_ebitda"], 940.0)
        self.assertEqual(ttm["ttm_ebit"], 740.0)
        self.assertEqual(ttm["ttm_net_profit"], 540.0)
        self.assertEqual(ttm["latest_equity"], 2000.0)
        self.assertEqual(ttm["latest_debt"], 500.0)
        self.assertEqual(ttm["latest_cash"], 200.0)

    # -------------------------------------------------------------
    # 4. Corporate Actions Adjustments: Shares & Dividends
    # -------------------------------------------------------------
    def test_shares_and_dividend_split_adjustment(self):
        """2:1 stock split adjusts reported statement shares and scales trailing cash dividends."""
        # Insert corporate action: 2:1 Split (multiplier 0.5) on 2025-08-01
        # and Dividend ₹10 on 2025-05-01 (prior to split)
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO corporate_actions (symbol, action_type, ex_date, purpose, adjustment_factor, source, retrieval_timestamp)
            VALUES
                ('TEST_TECH', 'DIVIDEND', '2025-05-01', 'Interim Dividend - Rs 10 Per Share', 1.0, 'test', ?),
                ('TEST_TECH', 'SPLIT', '2025-08-01', 'Sub-division 1:2', 0.5, 'test', ?);
            """, (now_ts, now_ts))

        # Statement as of 2025-06-30 reported 10,000,000 shares
        # Evaluation date 2025-10-01 (after split)
        adj_shares, trailing_div = self.engine.adjust_for_corporate_actions(
            symbol="TEST_TECH",
            statement_date="2025-06-30",
            trading_date="2025-10-01",
            statement_shares=10000000,
            db=self.db
        )
        # 10,000,000 / 0.5 = 20,000,000 shares
        self.assertEqual(adj_shares, 20000000)
        # ₹10 dividend scaled by 0.5 = ₹5.00
        self.assertEqual(trailing_div, 5.0)

    # -------------------------------------------------------------
    # 5. Sector-Aware Valuation Exclusions (Financials vs Industrials)
    # -------------------------------------------------------------
    def test_sector_aware_valuation_exclusions(self):
        """Banks and Financials have EV/EBITDA, D/E, and ROCE set to NULL with FINANCIAL_SECTOR_ADJUSTED flag."""
        # Seed OHLCV prices
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES
                ('TEST_TECH', '2025-10-01', 'EQ', 100.0, 105.0, 99.0, 100.0, 10000, 'test', ?),
                ('TEST_FIN', '2025-10-01', 'EQ', 500.0, 510.0, 495.0, 500.0, 20000, 'test', ?);
            """, (now_ts, now_ts))

        # Seed 4 discrete quarterly statements for both to complete full TTM
        for sym, name in [("TEST_TECH", "Tech"), ("TEST_FIN", "Fin")]:
            for i, end_d in enumerate(["2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30"]):
                stmt = {
                    "statement_id": f"{sym}_Q{i}",
                    "symbol": sym,
                    "period_type": f"Q{i+1}",
                    "period_nature": "DISCRETE_QUARTER",
                    "fiscal_year": "FY26",
                    "period_start_date": "2024-10-01",
                    "period_end_date": end_d,
                    "publication_date": end_d,
                    "effective_session_date": end_d,
                    "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
                    "total_revenue": 500.0,
                    "ebitda": 150.0,
                    "ebit": 120.0,
                    "net_profit": 100.0,
                    "total_equity": 1000.0,
                    "total_debt": 400.0,
                    "cash_and_equivalents": 100.0,
                    "shares_outstanding": 10000000
                }
                _, cl, _ = self.validator.validate_financial_statement(stmt)
                self.db.upsert_financial_statements([cl])

        factors_tech = self.engine.calculate_fundamental_factors("TEST_TECH", "2025-10-01", db=self.db)
        factors_fin = self.engine.calculate_fundamental_factors("TEST_FIN", "2025-10-01", db=self.db)

        # Industrial (TEST_TECH): EV/EBITDA, D/E, and ROCE computed
        self.assertEqual(factors_tech["metric_applicability_flag"], "STANDARD_INDUSTRIAL")
        self.assertIsNotNone(factors_tech["ev_ebitda"])
        self.assertIsNotNone(factors_tech["debt_to_equity"])
        self.assertIsNotNone(factors_tech["roce_pct"])

        # Financial (TEST_FIN): EV/EBITDA, D/E, and ROCE MUST be NULL
        self.assertEqual(factors_fin["metric_applicability_flag"], "FINANCIAL_SECTOR_ADJUSTED")
        self.assertIsNone(factors_fin["ev_ebitda"])
        self.assertIsNone(factors_fin["debt_to_equity"])
        self.assertIsNone(factors_fin["roce_pct"])

    # -------------------------------------------------------------
    # 6. Negative Earnings and Negative Equity Masking
    # -------------------------------------------------------------
    def test_negative_earnings_and_equity_masking(self):
        """P/E is masked to NULL when PAT <= 0; P/B is masked to NULL when Equity <= 0."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES ('TEST_LOSS', '2025-10-01', 'EQ', 50.0, 52.0, 49.0, 50.0, 5000, 'test', ?);
            """, (now_ts,))

        # Seed 4 discrete quarters of losses
        for i, end_d in enumerate(["2024-12-31", "2025-03-31", "2025-06-30", "2025-09-30"]):
            stmt_loss = {
                "statement_id": f"LOSS_Q{i+1}",
                "symbol": "TEST_LOSS",
                "period_type": f"Q{i+1}",
                "period_nature": "DISCRETE_QUARTER",
                "fiscal_year": "FY26",
                "period_start_date": "2024-10-01",
                "period_end_date": end_d,
                "publication_date": end_d,
                "effective_session_date": end_d,
                "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
                "total_revenue": 100.0,
                "ebitda": -20.0,
                "ebit": -30.0,
                "net_profit": -50.0,  # Negative PAT
                "total_equity": -10.0, # Negative Equity
                "shares_outstanding": 1000000
            }
            _, cl, _ = self.validator.validate_financial_statement(stmt_loss)
            self.db.upsert_financial_statements([cl])

        factors = self.engine.calculate_fundamental_factors("TEST_LOSS", "2025-10-01", db=self.db)
        self.assertIsNone(factors["pe_ratio"])
        self.assertIsNone(factors["pb_ratio"])
        self.assertIn("NEGATIVE_EARNINGS", factors["data_quality_flag"])
        self.assertIn("NEGATIVE_EQUITY", factors["data_quality_flag"])

    # -------------------------------------------------------------
    # 7. Cross-Sectional Sector Medians, Spreads, and Deciles
    # -------------------------------------------------------------
    def test_sector_relative_metrics_and_deciles(self):
        """Sector medians, relative spreads, sector percentiles, and universe deciles compute properly."""
        factors = [
            {"symbol": "S1", "sector": "IT", "pe_ratio": 20.0},
            {"symbol": "S2", "sector": "IT", "pe_ratio": 30.0},
            {"symbol": "S3", "sector": "IT", "pe_ratio": 40.0},
            {"symbol": "S4", "sector": "IT", "pe_ratio": None},   # Loss maker
            {"symbol": "F1", "sector": "FIN", "pe_ratio": 15.0},
            {"symbol": "F2", "sector": "FIN", "pe_ratio": 25.0},
        ]
        result = FundamentalsEngine.compute_sector_relative_factors(factors)

        # For IT: valid P/Es are [20.0, 30.0, 40.0], median = 30.0
        s1 = next(r for r in result if r["symbol"] == "S1")
        s2 = next(r for r in result if r["symbol"] == "S2")
        s3 = next(r for r in result if r["symbol"] == "S3")
        s4 = next(r for r in result if r["symbol"] == "S4")

        self.assertEqual(s1["sector_pe_median"], 30.0)
        self.assertEqual(s1["pe_vs_sector_spread"], -10.0)
        self.assertEqual(s1["pe_percentile_sector"], 0.0)

        self.assertEqual(s2["sector_pe_median"], 30.0)
        self.assertEqual(s2["pe_vs_sector_spread"], 0.0)
        self.assertEqual(s2["pe_percentile_sector"], 50.0)

        self.assertEqual(s3["sector_pe_median"], 30.0)
        self.assertEqual(s3["pe_vs_sector_spread"], 10.0)
        self.assertEqual(s3["pe_percentile_sector"], 100.0)

        self.assertEqual(s4["sector_pe_median"], 30.0)
        self.assertIsNone(s4["pe_vs_sector_spread"])
        self.assertIsNone(s4["pe_percentile_sector"])
        self.assertIsNone(s4["valuation_decile_universe"])

        # Universe deciles across the 5 profitable stocks [15, 20, 25, 30, 40]
        f1 = next(r for r in result if r["symbol"] == "F1")
        self.assertIsNotNone(f1["valuation_decile_universe"])

    # -------------------------------------------------------------
    # 8. End-to-End Pipeline & Index Valuation Update
    # -------------------------------------------------------------
    def test_index_valuation_update(self):
        """Index valuations (P/E, P/B, Div Yield) can be updated in index_daily."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO index_daily (index_name, trading_date, index_type, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES ('NIFTY 50', '2025-10-01', 'PRI', 25000.0, 25200.0, 24900.0, 25100.0, 1000000, 'test', ?);
            """, (now_ts,))

        updated = self.client.update_index_valuations([
            {
                "index_name": "NIFTY 50",
                "trading_date": "2025-10-01",
                "pe_ratio": 22.45,
                "pb_ratio": 3.85,
                "div_yield": 1.25
            }
        ])
        self.assertEqual(updated, 1)

        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT pe_ratio, pb_ratio, div_yield FROM index_daily WHERE index_name = 'NIFTY 50' AND trading_date = '2025-10-01';"
            ).fetchone()
            self.assertEqual(row["pe_ratio"], 22.45)
            self.assertEqual(row["pb_ratio"], 3.85)
            self.assertEqual(row["div_yield"], 1.25)

    # -------------------------------------------------------------
    # 9. Strict TTM Discipline: Partial Periods vs True 4-Quarter TTM
    # -------------------------------------------------------------
    def test_insufficient_periods_for_ttm(self):
        """When fewer than 4 quarters are present, flow TTM fields and P/E are masked to NULL with INSUFFICIENT_PERIODS_FOR_TTM."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES ('TEST_CORP', '2025-10-01', 'EQ', 1000.0, 1020.0, 990.0, 1000.0, 10000, 'test', ?);
            """, (now_ts,))

        # Only 1 quarter available
        stmt = {
            "statement_id": "CORP_Q1_ONLY",
            "symbol": "TEST_CORP",
            "period_type": "Q1",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-04-01",
            "period_end_date": "2025-06-30",
            "publication_date": "2025-07-15",
            "effective_session_date": "2025-07-15",
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "total_revenue": 500.0,
            "net_profit": 100.0,
            "total_equity": 2000.0,
            "shares_outstanding": 10000000
        }
        _, cl, _ = self.validator.validate_financial_statement(stmt)
        self.db.upsert_financial_statements([cl])

        factors = self.engine.calculate_fundamental_factors("TEST_CORP", "2025-10-01", db=self.db)
        self.assertEqual(factors["statements_count_ttm"], 1)
        self.assertIn("INSUFFICIENT_PERIODS_FOR_TTM", factors["data_quality_flag"])
        # Flow items and P/E MUST be None (never annualized or treated as full-year TTM)
        self.assertIsNone(factors["ttm_revenue"])
        self.assertIsNone(factors["ttm_net_profit"])
        self.assertIsNone(factors["pe_ratio"])
        self.assertIsNone(factors["ps_ratio"])
        self.assertIsNone(factors["ttm_eps_adjusted"])
        # Balance sheet snapshot P/B is validly computed
        # Market Cap = 1000.0 * 10,000,000 / 1e7 = 1000.0 Cr. Equity = 2000.0 Cr -> P/B = 0.5
        self.assertEqual(factors["market_cap_inr_crore"], 1000.0)
        self.assertEqual(factors["pb_ratio"], 0.5)

    # -------------------------------------------------------------
    # 10. Shares-Outstanding Units Normalization (Crores vs Absolute)
    # -------------------------------------------------------------
    def test_shares_unit_normalization_crore_vs_absolute(self):
        """Validator normalizes shares passed in Crores or Absolute count to absolute shares."""
        # 1. Input in Crores (415.0 Cr shares)
        raw_crore = {
            "statement_id": "UNIT_TEST_CR",
            "symbol": "TEST_TECH",
            "period_type": "Q1",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-04-01",
            "period_end_date": "2025-06-30",
            "publication_date": "2025-07-15",
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "shares_outstanding": 415.0,
            "shares_unit": "CRORE"
        }
        valid1, c1, _ = self.validator.validate_financial_statement(raw_crore)
        self.assertTrue(valid1)
        self.assertEqual(c1["shares_outstanding"], 4150000000.0)

        # 2. Input in Absolute count (4,150,000,000 shares)
        raw_abs = {
            "statement_id": "UNIT_TEST_ABS",
            "symbol": "TEST_TECH",
            "period_type": "Q2",
            "period_nature": "DISCRETE_QUARTER",
            "fiscal_year": "FY26",
            "period_start_date": "2025-07-01",
            "period_end_date": "2025-09-30",
            "publication_date": "2025-10-15",
            "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
            "shares_outstanding": 4150000000,
            "shares_unit": "ABSOLUTE"
        }
        valid2, c2, _ = self.validator.validate_financial_statement(raw_abs)
        self.assertTrue(valid2)
        self.assertEqual(c2["shares_outstanding"], 4150000000.0)

    # -------------------------------------------------------------
    # 11. Independent Formula Reconciliation Against Synthetic Fixture
    # -------------------------------------------------------------
    def test_independent_valuation_formula_reconciliation(self):
        """Mathematically reconciles Market Cap, P/E, P/B, P/S, EPS, EV/EBITDA, and Div Yield against manual formulas."""
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with self.db.get_connection() as conn:
            conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES ('TEST_TECH', '2026-03-31', 'EQ', 200.0, 205.0, 195.0, 200.0, 10000, 'test', ?);
            """, (now_ts,))
            conn.execute("""
            INSERT INTO corporate_actions (symbol, action_type, ex_date, purpose, adjustment_factor, source, retrieval_timestamp)
            VALUES ('TEST_TECH', 'DIVIDEND', '2025-11-01', 'Interim Dividend - Rs 4 Per Share', 1.0, 'test', ?);
            """, (now_ts,))

        # Seed 4 discrete quarters
        for i, end_d in enumerate(["2025-06-30", "2025-09-30", "2025-12-31", "2026-03-31"]):
            stmt = {
                "statement_id": f"RECON_Q{i+1}",
                "symbol": "TEST_TECH",
                "period_type": f"Q{i+1}",
                "period_nature": "DISCRETE_QUARTER",
                "fiscal_year": "FY26",
                "period_start_date": "2025-04-01",
                "period_end_date": end_d,
                "publication_date": end_d,
                "effective_session_date": end_d,
                "source_timestamp_basis": "ANNOUNCEMENT_DATE_VERIFIED",
                "total_revenue": 250.0,
                "ebitda": 50.0,
                "ebit": 40.0,
                "net_profit": 25.0,
                "total_equity": 500.0,
                "total_debt": 100.0,
                "cash_and_equivalents": 50.0,
                "shares_outstanding": 50000000  # 5 Crore shares
            }
            _, cl, _ = self.validator.validate_financial_statement(stmt)
            self.db.upsert_financial_statements([cl])

        factors = self.engine.calculate_fundamental_factors("TEST_TECH", "2026-03-31", db=self.db)

        # 1. Market Cap: 200.0 * 50,000,000 / 1e7 = 1,000.0 Crore
        self.assertEqual(factors["market_cap_inr_crore"], 1000.0)

        # 2. TTM Net Profit: 4 * 25.0 = 100.0 Crore
        self.assertEqual(factors["ttm_net_profit"], 100.0)

        # 3. P/E: 1000.0 / 100.0 = 10.0
        self.assertEqual(factors["pe_ratio"], 10.0)

        # 4. Adjusted EPS: (100.0 * 1e7) / 50,000,000 = 20.0 INR/share
        self.assertEqual(factors["ttm_eps_adjusted"], 20.0)

        # 5. Exact Identity: Price / EPS = 200.0 / 20.0 = 10.0 == P/E
        self.assertEqual(round(factors["close_price"] / factors["ttm_eps_adjusted"], 2), factors["pe_ratio"])

        # 6. P/B: 1000.0 / 500.0 = 2.0
        self.assertEqual(factors["pb_ratio"], 2.0)

        # 7. P/S: 1000.0 / (4 * 250.0) = 1.0
        self.assertEqual(factors["ps_ratio"], 1.0)

        # 8. EV/EBITDA: (1000.0 + 100.0 - 50.0) / (4 * 50.0) = 1050.0 / 200.0 = 5.25
        self.assertEqual(factors["ev_ebitda"], 5.25)

        # 9. Dividend Yield: (4.0 / 200.0) * 100 = 2.0%
        self.assertEqual(factors["dividend_yield_ttm"], 2.0)

        # 10. Debt-to-Equity: 100.0 / 500.0 = 0.2
        self.assertEqual(factors["debt_to_equity"], 0.2)

    def test_universe_financial_statement_completeness_and_canonical_units(self):
        """16. Verify all 50 active constituents in data/market_lab.db have complete, verified quarterly statements."""
        db_path = "data/market_lab.db"
        if not os.path.exists(db_path):
            self.skipTest("Live database not found.")
        db = DatabaseManager(db_path)
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT symbol FROM securities_master WHERE is_active = 1;")
            active_symbols = set(r[0] for r in cur.fetchall())
            self.assertEqual(len(active_symbols), 50)

            cur.execute("SELECT DISTINCT symbol FROM company_financial_statements;")
            ingested_symbols = set(r[0] for r in cur.fetchall())
            self.assertEqual(active_symbols, ingested_symbols)

            # Check that every statement has is_pit_eligible = 1 and canonical absolute share count
            cur.execute("SELECT symbol, statement_id, shares_outstanding, is_pit_eligible, verification_status FROM company_financial_statements;")
            rows = cur.fetchall()
            self.assertGreaterEqual(len(rows), 400)
            for r in rows:
                self.assertEqual(r["is_pit_eligible"], 1)
                self.assertEqual(r["verification_status"], "VERIFIED")
                self.assertGreaterEqual(r["shares_outstanding"], 10_000_000, f"Shares unnormalized for {r['statement_id']}")

    def test_cross_sectional_sector_relative_consistency(self):
        """17. Verify cross-sectional factor ranking computes valid sector medians, spreads, and deciles (1-10) for 50 constituents."""
        db_path = "data/market_lab.db"
        if not os.path.exists(db_path):
            self.skipTest("Live database not found.")
        db = DatabaseManager(db_path)
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT symbol, pe_ratio, sector_pe_median, pe_vs_sector_spread, pe_percentile_sector, valuation_decile_universe
                FROM fundamental_factors_daily
                WHERE trading_date = '2026-05-15';
            """)
            rows = cur.fetchall()
            self.assertEqual(len(rows), 50)
            deciles = set()
            for r in rows:
                if r["pe_ratio"] is not None:
                    self.assertIsNotNone(r["sector_pe_median"])
                    self.assertIsNotNone(r["pe_vs_sector_spread"])
                    self.assertIsNotNone(r["valuation_decile_universe"])
                    self.assertTrue(1 <= r["valuation_decile_universe"] <= 10)
                    deciles.add(r["valuation_decile_universe"])
            # All 10 valuation deciles should be represented across 50 constituents
            self.assertEqual(len(deciles), 10)

    def test_tmpv_demerger_boundary_and_recast_pit_isolation(self):
        """18. Verify TMPV point-in-time statement selection respects the demerger boundary and recast availability."""
        db_path = "data/market_lab.db"
        if not os.path.exists(db_path):
            self.skipTest("Live database not found.")
        db = DatabaseManager(db_path)
        engine = FundamentalsEngine(db)

        # Before recast announcement (e.g. 2025-08-01): must select Version 1 (Combined Tata Motors)
        stmts_pre = engine.get_as_of_statements("TMPV", "2025-08-01")
        q1_26_pre = next((s for s in stmts_pre if s["fiscal_year"] == "FY26" and s["fiscal_quarter"] == 1), None)
        self.assertIsNotNone(q1_26_pre)
        self.assertEqual(q1_26_pre["statement_version"], 1)
        self.assertEqual(q1_26_pre["revenue_operations"], 116000.0)
        self.assertEqual(q1_26_pre["restatement_reason"], "PRE_DEMERGER_COMBINED_TATA_MOTORS")

        # After recast effective date (e.g. 2026-05-15): must select Version 2 Recast (Continuing Passenger Vehicles)
        stmts_post = engine.get_as_of_statements("TMPV", "2026-05-15")
        q1_26_post = next((s for s in stmts_post if s["fiscal_year"] == "FY26" and s["fiscal_quarter"] == 1), None)
        self.assertIsNotNone(q1_26_post)
        self.assertEqual(q1_26_post["statement_version"], 2)
        self.assertEqual(q1_26_post["revenue_operations"], 78500.0)
        self.assertEqual(q1_26_post["restatement_reason"], "POST_DEMERGER_RECAST_CONTINUING_PV")

        # Full TTM calculation on 2026-05-15 must have 4 consistent post-demerger quarters
        factors = engine.calculate_fundamental_factors("TMPV", "2026-05-15")
        self.assertEqual(factors["data_quality_flag"], "COMPLETE")
        self.assertEqual(factors["ttm_revenue"], 323900.0)
        self.assertEqual(factors["ttm_net_profit"], 20100.0)
        self.assertEqual(factors["pe_ratio"], 6.53)

    def test_tmpv_inconsistent_perimeter_guard(self):
        """19. Verify mixing un-recast pre-demerger statements with post-demerger statements flags INCONSISTENT_REPORTING_PERIMETER."""
        engine = FundamentalsEngine()
        inconsistent_quarters = [
            {"period_nature": "DISCRETE_QUARTER", "period_end_date": "2026-03-31", "total_revenue": 89800.0, "net_profit": 6400.0, "restatement_reason": "POST_DEMERGER_TMPV"},
            {"period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-12-31", "total_revenue": 82400.0, "net_profit": 5200.0, "restatement_reason": "POST_DEMERGER_TMPV"},
            {"period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-09-30", "total_revenue": 73200.0, "net_profit": 3850.0, "restatement_reason": "POST_DEMERGER_TMPV"},
            {"period_nature": "DISCRETE_QUARTER", "period_end_date": "2025-03-31", "total_revenue": 124000.0, "net_profit": 8200.0, "restatement_reason": "PRE_DEMERGER_COMBINED_TATA_MOTORS"}
        ]
        ttm_res = engine.compute_ttm_metrics(inconsistent_quarters)
        self.assertEqual(ttm_res["data_quality_flag"], "INCONSISTENT_REPORTING_PERIMETER")
        self.assertIsNone(ttm_res["ttm_revenue"])
        self.assertIsNone(ttm_res["ttm_net_profit"])

    def test_index_valuation_coverage_and_budget_day_null_preservation(self):
        """20. Verify 8,928 populated index valuation records (99.6%) and exact 36 Budget Day NULL preservation."""
        db_path = "data/market_lab.db"
        if not os.path.exists(db_path):
            self.skipTest("Live database not found.")
        db = DatabaseManager(db_path)
        with db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT 
                    COUNT(*) as total_rows,
                    COUNT(pe_ratio) as non_null_pe,
                    COUNT(pb_ratio) as non_null_pb,
                    COUNT(div_yield) as non_null_div_yield,
                    SUM(CASE WHEN pe_ratio IS NULL THEN 1 ELSE 0 END) as null_pe
                FROM index_daily;
            """)
            totals = cur.fetchone()
            self.assertEqual(totals["total_rows"], 8964)
            self.assertEqual(totals["non_null_pe"], 8928)
            self.assertEqual(totals["non_null_pb"], 8928)
            self.assertEqual(totals["non_null_div_yield"], 8928)
            self.assertEqual(totals["null_pe"], 36)

            cur.execute("SELECT DISTINCT trading_date FROM index_daily WHERE pe_ratio IS NULL ORDER BY trading_date;")
            null_dates = [r[0] for r in cur.fetchall()]
            self.assertEqual(null_dates, ["2025-02-01", "2026-02-01"])


if __name__ == "__main__":
    unittest.main()
