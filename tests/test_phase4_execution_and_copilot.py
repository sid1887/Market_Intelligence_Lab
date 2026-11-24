"""
tests/test_phase4_execution_and_copilot.py
Comprehensive test suite verifying MIL 2.0 Phase 4 deliverables:
1. Friction-Aware Integer-Share Optimizer & Correlation-Cluster Risk Budgeter (src/portfolio/position_sizer.py).
2. Trader DNA Behavioral Telemetry, Post-Loss Cooldown & Horizon Mismatch Detection (src/copilot/trader_dna.py).
3. PIT Market Regime Analogs with Zero Future Leakage (src/copilot/regime_analogs.py).
4. Deterministic 3-Agent Copilot Consensus & Hard Veto Override (src/copilot/deliberation.py).
"""

import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from src.portfolio.position_sizer import FrictionAwarePositionSizer, PositionSizingResult
from src.portfolio.tradebook_engine import EncryptedTradebookEngine
from src.copilot.trader_dna import TraderDNAEngine
from src.copilot.regime_analogs import PITMarketRegimeAnalogEngine
from src.copilot.deliberation import MultiAgentDeliberationEngine
from src.storage.database import DatabaseManager
from src.storage.migrations import run_all_migrations
from src.portfolio.fee_engine import ANGEL_ONE_DP_CHARGE


class TestFrictionAwarePositionSizer(unittest.TestCase):
    """Verifies integer-share optimization, DP friction drag, net R:R, and cluster risk caps."""

    def setUp(self):
        self.sizer = FrictionAwarePositionSizer(
            max_risk_pct=0.02,
            max_position_pct=0.25,
            max_fee_drag_pct=1.25,
            min_net_rr=1.6,
            min_meta_prob=0.55,
            cluster_cap_pct=0.40,
            corr_threshold=0.65
        )

    def test_micro_capital_dp_drag_crushes_net_rr(self):
        """
        Micro-Capital Test:
        On ₹2,500 capital, ₹23.60 DP fee + statutory charges turn a setup with a gross 2.0x R:R
        into a sub-1.6x Net R:R, triggering an automatic NO_TRADE / POOR_NET_RR veto.
        """
        # Price = 100.0, Stop = 97.0 (risk = 3.0), Target = 106.0 (reward = 6.0) -> Gross R:R = 2.0x
        # On ₹2,500 capital: max risk 2% = ₹50. Q = 50 // 3 = 16 shares.
        # Investment = ₹1,600. Gross profit = 16 * 6 = ₹96.
        # But round-trip friction is ~₹27 (₹23.60 DP + statutory taxes).
        # Net reward = 96 - 27 = ₹69. Net risk = (16 * 3) + 27 = 48 + 27 = ₹75.
        # Net R:R = 69 / 75 = 0.92x < 1.6x minimum!
        res = self.sizer.solve_position_size(
            capital=2500.0,
            entry_price=100.0,
            stop_loss=97.0,
            target_price=106.0,
            meta_prob=0.65,
            candidate_symbol="RELIANCE"
        )

        self.assertFalse(res.can_trade)
        self.assertEqual(res.verdict, "NO_TRADE")
        self.assertGreater(res.gross_rr, 1.8)
        self.assertLess(res.net_rr, 1.6)
        self.assertTrue(any("POOR_NET_RR" in v for v in res.veto_reasons))

    def test_adequate_capital_clears_net_rr_and_allocates_integer_shares(self):
        """
        Adequate Capital Test:
        On ₹50,000 capital, ₹23.60 DP fee is negligible (e.g. 0.2% drag), allowing clean trade approval.
        """
        res = self.sizer.solve_position_size(
            capital=50000.0,
            entry_price=200.0,
            stop_loss=190.0,
            target_price=225.0,
            meta_prob=0.65,
            candidate_symbol="INFY"
        )

        self.assertTrue(res.can_trade)
        self.assertEqual(res.verdict, "APPROVED")
        self.assertGreater(res.shares, 0)
        self.assertGreater(res.net_rr, 1.6)
        self.assertLess(res.fee_drag_pct, 1.25)
        self.assertEqual(len(res.veto_reasons), 0)

    def test_low_meta_probability_veto(self):
        """Calibrated meta-probability p_meta < 0.55 triggers META_PROB_BELOW_HURDLE veto."""
        res = self.sizer.solve_position_size(
            capital=50000.0,
            entry_price=200.0,
            stop_loss=190.0,
            target_price=225.0,
            meta_prob=0.51,  # below 0.55 hurdle
            candidate_symbol="TCS"
        )

        self.assertFalse(res.can_trade)
        self.assertEqual(res.verdict, "NO_TRADE")
        self.assertTrue(any("META_PROB_BELOW_HURDLE" in v for v in res.veto_reasons))

    def test_correlation_cluster_cap_blocks_overconcentration(self):
        """
        Cluster Cap Test:
        When an existing open position already occupies 35% of capital, adding a correlated candidate
        that pushes cluster exposure above 40% is reduced or blocked.
        """
        # Open position in HDFCBANK: ₹18,000 out of ₹50,000 capital (36% exposure)
        open_positions = [{
            "symbol": "HDFCBANK",
            "qty": 10,
            "avg_buy_price": 1800.0,
            "buy_value": 18000.0
        }]

        # Candidate is ICICIBANK with high assumed correlation
        # Sizer with mock correlation helper
        mock_sizer = FrictionAwarePositionSizer(
            cluster_cap_pct=0.40,
            max_position_pct=0.25
        )
        mock_sizer.compute_trailing_correlation = lambda s1, s2: 0.85 if {s1, s2} == {"ICICIBANK", "HDFCBANK"} else 0.0

        res = mock_sizer.solve_position_size(
            capital=50000.0,
            entry_price=1000.0,
            stop_loss=960.0,
            target_price=1100.0,
            meta_prob=0.65,
            candidate_symbol="ICICIBANK",
            open_positions=open_positions
        )

        # 40% cap of ₹50,000 is ₹20,000. HDFCBANK is ₹18,000.
        # Remaining budget for cluster is ₹2,000 (at ₹1,000/sh -> max 2 shares).
        # Normal 25% single cap would have allowed 12 shares (₹12,000), but cluster cap constrains it to <= 2 shares.
        if res.can_trade:
            self.assertLessEqual(res.shares, 2)
            self.assertLessEqual(res.cluster_exposure_pct, 40.0)


class TestTraderDNASuitabilityAndCooldown(unittest.TestCase):
    """Verifies Trader DNA behavioral metrics, consecutive loss cooldown, and horizon mismatch detection."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_trader_dna.db"
        self.db = DatabaseManager(db_path=self.db_path)
        with self.db.get_connection() as conn:
            run_all_migrations(conn)
        EncryptedTradebookEngine(self.db)
        self.engine = TraderDNAEngine(self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_cooldown_activation_after_consecutive_losses(self):
        """
        Verifies that >= 3 consecutive losses activates COOLDOWN_ACTIVE and sets size_multiplier = 0.5
        without altering the underlying market alpha signals.
        """
        with self.db.get_connection() as conn:
            # Insert 3 consecutive losing trades
            for i in range(1, 4):
                conn.execute("""
                    INSERT INTO real_closed_roundtrips (
                        id, symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                        avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                        trade_charges, dp_charge, net_pnl, net_return_pct, outcome
                    ) VALUES (?, 'RVNL', 'INE415G01027', 'RVNL', 20, '2026-01-01', ?, 3, 100.0, 2000.0, 95.0, 1900.0, -100.0, 4.0, 23.60, -127.60, -6.38, 'LOSS')
                """, (i, f"2026-01-0{i+1}"))
            conn.commit()

        profile = self.engine.get_live_execution_profile()

        self.assertEqual(profile["consecutive_losses"], 3)
        self.assertTrue(profile["defensive_cooldown_active"])
        self.assertTrue(profile["half_size_guard"])
        self.assertEqual(profile["size_multiplier"], 0.5)

        eval_res = self.engine.evaluate_proposed_trade(
            symbol="INFY", entry_price=1500.0, target_price=1600.0, stop_loss=1450.0
        )
        self.assertEqual(eval_res["coaching_status"], "COOLDOWN_ACTIVE")
        self.assertFalse(eval_res["can_trade"])

    def test_horizon_mismatch_warning(self):
        """
        Verifies that when a candidate trade requires a 20-day holding horizon,
        but the trader's historical median hold is only 2 days, a HORIZON_MISMATCH warning is issued.
        """
        with self.db.get_connection() as conn:
            # Insert short-duration trades (median hold = 2 days)
            for i in range(1, 5):
                conn.execute("""
                    INSERT INTO real_closed_roundtrips (
                        id, symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                        avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                        trade_charges, dp_charge, net_pnl, net_return_pct, outcome
                    ) VALUES (?, 'TCS', 'INE467B01029', 'TCS', 5, ?, ?, 2, 3000.0, 15000.0, 3100.0, 15500.0, 500.0, 10.0, 23.60, 466.40, 3.11, 'WIN')
                """, (i, f"2026-01-0{i}", f"2026-01-0{i+2}"))
            conn.commit()

        eval_res = self.engine.evaluate_proposed_trade(
            symbol="RELIANCE", entry_price=2500.0, target_price=2700.0, stop_loss=2400.0,
            holding_horizon_days=20
        )

        self.assertTrue(any("HORIZON_MISMATCH" in w for w in eval_res["warnings"]))


class TestPITMarketRegimeAnalogs(unittest.TestCase):
    """Verifies that market regime analogs enforce zero future data leakage."""

    def test_zero_future_leakage_invariant(self):
        """
        Strict PIT Invariant:
        All returned analog dates must strictly be <= as_of_date - horizon_sessions.
        """
        engine = PITMarketRegimeAnalogEngine(top_k=5, horizon_sessions=20)

        # Generate 350 sessions of synthetic benchmark data
        dates = pd.date_range("2023-01-01", periods=350, freq="B").astype(str)
        prices = 18000.0 * np.exp(np.cumsum(np.random.normal(0.0005, 0.01, 350)))
        df_bench = pd.DataFrame({
            "trading_date": dates,
            "open": prices,
            "high": prices * 1.01,
            "low": prices * 0.99,
            "close": prices,
            "volume": np.random.uniform(1e6, 5e6, 350)
        })

        engine.extract_benchmark_history = lambda as_of_date: df_bench[df_bench["trading_date"] <= as_of_date]

        as_of = dates[300]
        report = engine.find_analogs(as_of_date=as_of, k=5)

        self.assertIsNotNone(report)
        self.assertGreater(len(report.matches), 0)

        # Verify all analog dates are strictly before as_of - 20 sessions
        as_of_idx = list(dates).index(as_of)
        max_allowed_date = dates[as_of_idx - 20]

        for match in report.matches:
            self.assertLessEqual(
                match.analog_date, max_allowed_date,
                f"Future leakage detected! Analog date {match.analog_date} > max allowed date {max_allowed_date}"
            )


class TestDeterministicCopilotConsensus(unittest.TestCase):
    """Verifies 3-Agent Copilot consensus binding and deterministic hard-veto enforcement."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test_copilot.db"
        self.db = DatabaseManager(db_path=self.db_path)
        with self.db.get_connection() as conn:
            run_all_migrations(conn)
        EncryptedTradebookEngine(self.db)
        self.engine = MultiAgentDeliberationEngine(bridge=self.db)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_hard_veto_on_stale_or_missing_fundamentals(self):
        """
        Hard Veto Invariant:
        When a stock has no verified financial statements (or data_status='SECTOR_ESTIMATE'),
        the PM Judge MUST issue an ABSTAIN / NO_TRADE verdict regardless of technical momentum.
        """
        ctx = {
            "symbol": "SPECULATIVE",
            "current_price": 50.0,
            "technicals": {"price_above_sma200": True, "ret_20d_pct": 15.0},
            "fundamentals": {"data_status": "SECTOR_ESTIMATE", "roe_pct": None, "debt_to_equity": None},
            "forecast_20d": {"target_objective": 60.0, "invalidation_floor": 45.0}
        }

        memo, decision = self.engine._generate_deterministic_judge(ctx)

        self.assertIn("ABSTAIN", decision["verdict"])
        self.assertFalse(decision["can_trade"])
        self.assertGreaterEqual(len(decision["hard_veto_reasons"]), 1)
        self.assertTrue(any("STALE_OR_FABRICATED" in r for r in decision["hard_veto_reasons"]))
        self.assertIn("Hard Veto Override Active", memo)

    def test_hard_veto_on_cooldown_active(self):
        """
        Hard Veto Invariant:
        When trader is in active cooldown streak, the PM Judge verdict MUST be COOLDOWN_PAUSE / ABSTAIN.
        """
        # Inject losing streak into database
        with self.db.get_connection() as conn:
            for i in range(1, 4):
                conn.execute("""
                    INSERT INTO real_closed_roundtrips (
                        id, symbol, isin, scrip_name, qty, buy_date, sell_date, hold_days,
                        avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                        trade_charges, dp_charge, net_pnl, net_return_pct, outcome
                    ) VALUES (?, 'TATAMOTORS', 'INE155A01022', 'TATAMOTORS', 10, '2026-01-01', ?, 3, 500.0, 5000.0, 480.0, 4800.0, -200.0, 5.0, 23.60, -228.60, -4.57, 'LOSS')
                """, (i, f"2026-01-0{i+1}"))
            conn.commit()

        ctx = {
            "symbol": "INFY",
            "current_price": 1500.0,
            "technicals": {"price_above_sma200": True, "ret_20d_pct": 5.0},
            "fundamentals": {"roe_pct": 28.0, "debt_to_equity": 0.05, "data_status": "OBSERVED"},
            "forecast_20d": {"target_objective": 1650.0, "invalidation_floor": 1420.0}
        }

        memo, decision = self.engine._generate_deterministic_judge(ctx)

        self.assertIn(decision["verdict"], ["COOLDOWN_PAUSE", "ABSTAIN"])
        self.assertFalse(decision["can_trade"])
        self.assertIn("COOLDOWN_ACTIVE", str(decision["hard_veto_reasons"]))


if __name__ == "__main__":
    unittest.main()
