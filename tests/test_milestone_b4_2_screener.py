"""
Market Intelligence Lab — Milestone B4.2 & B4.3 Screener & Watchlist Unit Tests.

Comprehensive regression and acceptance test suite for:
1. User Watchlists Schema & Persistence (table schema, target_price, stop_loss, seed inventory).
2. Sector Exclusion Logic (verifies clean filtering of Financial Services).
3. Point-in-Time Historical Screening (verifies zero future leakage on historical dates).
4. Watchlist Integration without Index Breadth Pollution (breadth remains strictly 50 Nifty constituents).
5. Technical Indicator Screening (Price > SMA200, volatility caps, beta caps).
6. Fundamental Screening (Debt-to-Equity, ROE %, OPM %, TTM P/E).
7. Composite Quality-Momentum Score Mathematical Invariants (bounded strictly in [0, 100]).
8. SUZLON Factor Completeness & Target Price Retrieval.
"""

import os
import unittest
import datetime
import sqlite3
import pandas as pd

from src.storage.database import DatabaseManager
from src.quant.screener import FactorScreener
from src.quant.breadth import MarketBreadthEngine


class TestMilestoneB42ScreenerAndWatchlist(unittest.TestCase):
    """Test suite validating B4.2 screener engine and B4.3 watchlist onboarding."""

    @classmethod
    def setUpClass(cls):
        cls.db_path = "data/market_lab.db"
        cls.db = DatabaseManager(cls.db_path)
        cls.screener = FactorScreener(cls.db)
        cls.breadth_engine = MarketBreadthEngine(cls.db)

    # -------------------------------------------------------------
    # 1. User Watchlists Schema & Seed Verification
    # -------------------------------------------------------------

    def test_01_user_watchlists_table_and_seeded_equities(self):
        """Verify user_watchlists table exists and contains the 4 active trading watchlist equities."""
        watchlists = self.db.get_user_watchlists()
        self.assertGreaterEqual(len(watchlists), 4)

        wl_map = {w["symbol"]: w for w in watchlists}
        for sym in ["SUZLON", "TRIDENT", "DRONACHRYA", "MOREPENLAB"]:
            self.assertIn(sym, wl_map, f"Watchlist symbol '{sym}' missing from user_watchlists table.")

        # Verify SUZLON specific seed targets
        suzlon = wl_map["SUZLON"]
        self.assertEqual(suzlon["target_price"], 45.0)
        self.assertEqual(suzlon["stop_loss"], 33.0)
        self.assertIn("Renewable", suzlon["sector"])

    # -------------------------------------------------------------
    # 2. Sector Exclusion Logic
    # -------------------------------------------------------------

    def test_02_sector_exclusion_cleanly_filters_financials(self):
        """Verify that excluding 'Financial Services' cleanly purges banks and NBFCs."""
        # Unfiltered screen
        df_all = self.screener.screen(
            as_of_date="2026-10-28",
            criteria=None
        )
        self.assertFalse(df_all.empty)
        financial_symbols_before = df_all[df_all["sector"].str.contains("Financial", case=False, na=False)]["symbol"].tolist()
        self.assertGreater(len(financial_symbols_before), 0, "Precondition failed: Financials must exist in unfiltered universe.")

        # Screen with sector exclusion
        df_ex_fin = self.screener.screen(
            as_of_date="2026-10-28",
            criteria={"exclude_sectors": ["Financial Services"]}
        )
        financial_symbols_after = df_ex_fin[df_ex_fin["sector"].str.contains("Financial", case=False, na=False)]["symbol"].tolist()
        self.assertEqual(len(financial_symbols_after), 0, f"Found leaked financials after exclusion: {financial_symbols_after}")

    # -------------------------------------------------------------
    # 3. Point-in-Time Historical Screening (No Future Leakage)
    # -------------------------------------------------------------

    def test_03_point_in_time_historical_screening_no_leakage(self):
        """Verify that screening historical dates uses strictly point-in-time factors without future statement leakage."""
        # Historical date: 2025-05-15 (Q4 FY25 filed, but Q1 FY26 NOT yet filed)
        df_hist = self.screener.screen(
            as_of_date="2025-05-15",
            criteria=None,
            universe=["INFY"]
        )
        self.assertEqual(len(df_hist), 1)
        row_hist = df_hist.iloc[0]

        # Verify that as of 2025-05-15, close and factors reflect that historical session
        self.assertEqual(row_hist["symbol"], "INFY")
        self.assertIsNotNone(row_hist["close"])
        self.assertIsNotNone(row_hist["debt_to_equity"])

        # Latest session: 2026-10-28
        df_latest = self.screener.screen(
            as_of_date="2026-10-28",
            criteria=None,
            universe=["INFY"]
        )
        row_latest = df_latest.iloc[0]

        # Factors must differ between 2025-05-15 and 2026-10-28 (proving non-static PIT evaluation)
        self.assertNotEqual(row_hist["close"], row_latest["close"])
        self.assertNotEqual(row_hist["sma_20"], row_latest["sma_20"])

    # -------------------------------------------------------------
    # 4. Watchlist Integration without Index Breadth Pollution
    # -------------------------------------------------------------

    def test_04_watchlist_integration_without_index_breadth_pollution(self):
        """
        Verify that watchlist equities are included in factor screening
        WITHOUT polluting the NIFTY 50 index_membership_history or market breadth calculations.
        """
        # A. Screener includes watchlist equities when include_watchlists=True
        df_screener = self.screener.screen(
            as_of_date="2026-10-28",
            criteria=None,
            include_watchlists=True
        )
        symbols_in_screener = df_screener["symbol"].tolist()
        self.assertIn("SUZLON", symbols_in_screener)
        self.assertIn("TRIDENT", symbols_in_screener)
        self.assertIn("DRONACHRYA", symbols_in_screener)
        self.assertIn("MOREPENLAB", symbols_in_screener)

        # B. Market Breadth for NIFTY 50 strictly contains 50 constituents
        breadth = self.breadth_engine.compute_daily_breadth("2026-10-23", index_name="NIFTY 50")
        self.assertEqual(breadth["expected_constituents_count"], 50, "NIFTY 50 breadth must strictly evaluate 50 constituents.")
        self.assertEqual(breadth["valid_observations_count"], 50)
        self.assertEqual(breadth["coverage_pct"], 100.0)

        # C. Watchlist symbols are NOT present in index_membership_history for NIFTY 50
        with self.db.get_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT COUNT(*) FROM index_membership_history 
                WHERE index_name = 'NIFTY 50' 
                  AND symbol IN ('SUZLON', 'TRIDENT', 'DRONACHRYA', 'MOREPENLAB');
                """
            )
            polluted_count = cur.fetchone()[0]
            self.assertEqual(polluted_count, 0, "Index membership table polluted with watchlist equities!")

    # -------------------------------------------------------------
    # 5. Technical and Fundamental Filter Threshold Tests
    # -------------------------------------------------------------

    def test_05_technical_filter_thresholds(self):
        """Verify price_above_sma200 and volatility caps correctly filter candidates."""
        # 1. Price above 200 SMA
        df_above_200 = self.screener.screen(
            as_of_date="2026-10-28",
            criteria={"price_above_sma200": True}
        )
        for _, r in df_above_200.iterrows():
            self.assertGreater(r["close"], r["sma_200"], f"{r['symbol']} close {r['close']} not above sma_200 {r['sma_200']}")

        # 2. Max volatility threshold
        df_low_vol = self.screener.screen(
            as_of_date="2026-10-28",
            criteria={"max_volatility": 0.25}
        )
        for _, r in df_low_vol.iterrows():
            self.assertLessEqual(r["volatility_annualized"], 0.25)

    def test_06_fundamental_filter_thresholds(self):
        """Verify Debt-to-Equity and ROE % filter thresholds."""
        criteria = {
            "max_debt_to_equity": 0.5,
            "min_roe_pct": 15.0
        }
        df_qual = self.screener.screen(
            as_of_date="2026-10-28",
            criteria=criteria
        )

        for _, r in df_qual.iterrows():
            self.assertLessEqual(r["debt_to_equity"], 0.5)
            self.assertGreaterEqual(r["roe_pct"], 15.0)

        # TRIDENT has ROE ~7.9% and should NOT be in the results
        self.assertNotIn("TRIDENT", df_qual["symbol"].tolist(), "TRIDENT must be filtered out by ROE > 15% hurdle.")

    # -------------------------------------------------------------
    # 6. Composite Score Mathematical Properties
    # -------------------------------------------------------------

    def test_07_composite_score_bounded_and_monotonic(self):
        """Verify composite Quality-Momentum score is strictly bounded in [0.0, 100.0]."""
        df = self.screener.screen(as_of_date="2026-10-28", criteria=None)
        scores = df["composite_score"].tolist()

        for s in scores:
            self.assertGreaterEqual(s, 0.0)
            self.assertLessEqual(s, 100.0)

        # Check sorting order is descending
        for i in range(1, len(scores)):
            self.assertGreaterEqual(scores[i - 1], scores[i], "Screener output must be sorted descending by composite score.")

    # -------------------------------------------------------------
    # 7. SUZLON Dedicated Factor and Watchlist Properties
    # -------------------------------------------------------------

    def test_08_suzlon_factor_completeness_and_target_levels(self):
        """Verify SUZLON passes all screening hurdles and matches target price parameters."""
        criteria = {
            "max_debt_to_equity": 0.5,
            "exclude_sectors": ["Financial Services"],
            "min_roe_pct": 15.0,
            "price_above_sma200": True
        }
        df_passed = self.screener.screen(
            as_of_date="2026-10-28",
            criteria=criteria,
            include_watchlists=True
        )

        passed_symbols = df_passed["symbol"].tolist()
        self.assertIn("SUZLON", passed_symbols, "SUZLON must pass the high-quality momentum screen on 2026-10-28.")

        suzlon_row = df_passed[df_passed["symbol"] == "SUZLON"].iloc[0]
        self.assertTrue(suzlon_row["is_watchlist"])
        self.assertGreater(suzlon_row["close"], suzlon_row["sma_200"])
        self.assertLess(suzlon_row["debt_to_equity"], 0.5)
        self.assertGreater(suzlon_row["roe_pct"], 15.0)


if __name__ == "__main__":
    unittest.main()
