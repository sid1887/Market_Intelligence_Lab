"""
tests/test_post_phase7_hotfix.py
Unit tests verifying MIL 2.0 Post-Phase 7 Hotfix:
1. Active champion model synchronization in /api/v1/health with tournament_summary.json.
2. Lightweight, sub-100ms cached /api/v1/supervisor/status.
3. Deduplication of phantom incomplete rows in real_closed_roundtrips + mark_state_dirty.
4. Carry-forward duplicate detection in ttm_builder.py and pead_engine.py.
"""

import time
import json
import sqlite3
import unittest
import pandas as pd
from starlette.testclient import TestClient

from src.api.main import app
from src.storage.database import DatabaseManager
from src.portfolio.tradebook_engine import EncryptedTradebookEngine
from src.storage.durable_state import is_state_dirty, mark_state_dirty
from src.fundamentals.ttm_builder import flag_carry_forward_duplicates, PointInTimeTTMBuilder
from src.ml.features.pead_engine import calculate_pead_features


class TestPostPhase7Hotfix(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)
        self.db = DatabaseManager()

    def test_health_active_champion_from_tournament_summary(self):
        """Task 1: /api/v1/health derives active_champion_model authoritatively from tournament_summary.json."""
        resp = self.client.get("/api/v1/health")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("active_champion_model", data)
        # When ML models were rejected below baseline, active champion is the Deterministic Baseline
        self.assertEqual(data["active_champion_model"], "Deterministic Baseline (Momentum+LowVol+PIT)")

    def test_supervisor_status_sub_100ms_and_ttl_cache(self):
        """Task 2: /api/v1/supervisor/status executes in < 100ms and utilizes 30s TTL cache."""
        # Warm-up ASGI client router
        self.client.get("/api/v1/health")

        # First call (cold / refreshed)
        t0 = time.perf_counter()
        resp1 = self.client.get("/api/v1/supervisor/status?force_refresh=true")
        lat1_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(resp1.status_code, 200)
        data1 = resp1.json()
        self.assertIn("supervisor_state", data1)
        self.assertIn("latest_settled_session", data1)
        self.assertLess(lat1_ms, 100.0, f"Uncached supervisor status took {lat1_ms:.2f} ms (> 100 ms target)")

        # Second call (cached via 30s TTL)
        t0 = time.perf_counter()
        resp2 = self.client.get("/api/v1/supervisor/status")
        lat2_ms = (time.perf_counter() - t0) * 1000.0
        self.assertEqual(resp2.status_code, 200)
        data2 = resp2.json()
        self.assertEqual(data1["latest_settled_session"], data2["latest_settled_session"])
        self.assertLess(lat2_ms, 25.0, f"Cached supervisor status took {lat2_ms:.2f} ms (> 25 ms target)")

    def test_tradebook_roundtrip_deduplication(self):
        """Task 3: Incomplete duplicate rows matching complete rows are purged idempotently."""
        engine = EncryptedTradebookEngine(self.db)
        
        # Insert a synthetic complete row and an incomplete duplicate row
        with self.db.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO real_closed_roundtrips (
                    id, isin, symbol, scrip_name, qty, buy_date, sell_date, hold_days,
                    avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                    trade_charges, stt, dp_charge, net_pnl, net_return_pct, outcome
                ) VALUES (
                    99901, 'INE999A01010', 'TESTDEDUP', 'TESTDEDUP LTD', 10, '2024-01-01', '2024-01-10', 9,
                    100.0, 1000.0, 110.0, 1100.0, 100.0, 5.0, 2.0, 23.60, 69.40, 6.94, 'WIN'
                );
            """)
            # Incomplete duplicate with empty ISIN and None sell_date
            conn.execute("""
                INSERT OR REPLACE INTO real_closed_roundtrips (
                    id, isin, symbol, scrip_name, qty, buy_date, sell_date, hold_days,
                    avg_buy_price, buy_value, avg_sell_price, sell_value, gross_pnl,
                    trade_charges, stt, dp_charge, net_pnl, net_return_pct, outcome
                ) VALUES (
                    99902, '', 'TESTDEDUP', 'TESTDEDUP LTD', 10, NULL, NULL, 0,
                    100.0, 1000.0, 110.0, 1100.0, 100.0, 5.0, 2.0, 23.60, 69.40, 6.94, 'WIN'
                );
            """)
            conn.commit()

        # Run deduplication
        deleted = engine.deduplicate_closed_roundtrips()
        self.assertGreaterEqual(deleted, 1)

        # Verify only the complete row remains
        with self.db.get_connection() as conn:
            rows = conn.execute("SELECT id, isin, sell_date FROM real_closed_roundtrips WHERE symbol = 'TESTDEDUP';").fetchall()
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0][0], 99901)
            self.assertEqual(rows[0][1], "INE999A01010")
            self.assertEqual(rows[0][2], "2024-01-10")

            # Clean up synthetic test row
            conn.execute("DELETE FROM real_closed_roundtrips WHERE symbol = 'TESTDEDUP';")
            conn.commit()

    def test_carry_forward_duplicate_flagging_and_pead_isolation(self):
        """Task 4: Consecutive quarters with identical (revenue, pat, eps_diluted) are flagged and ignored in PEAD."""
        statements = [
            {
                "symbol": "CARRYTEST",
                "period_end_date": "2023-06-30",
                "published_at_ist": "2023-07-25 14:00:00",
                "revenue": 1000.0,
                "net_profit": 150.0,
                "eps_diluted": 5.0,
                "ebitda": 250.0,
            },
            {
                "symbol": "CARRYTEST",
                "period_end_date": "2023-09-30",
                "published_at_ist": "2023-10-25 14:00:00",
                "revenue": 1000.0,  # Repeated identical numbers
                "net_profit": 150.0,
                "eps_diluted": 5.0,
                "ebitda": 250.0,
            },
            {
                "symbol": "CARRYTEST",
                "period_end_date": "2023-12-31",
                "published_at_ist": "2024-01-25 14:00:00",
                "revenue": 1200.0,  # Fresh quarter
                "net_profit": 180.0,
                "eps_diluted": 6.0,
                "ebitda": 300.0,
            }
        ]

        # 1. Verify flagging in ttm_builder
        flagged = flag_carry_forward_duplicates(statements)
        self.assertEqual(len(flagged), 3)
        self.assertFalse(flagged[0].get("is_carry_forward_duplicate", False))
        self.assertTrue(flagged[1].get("is_carry_forward_duplicate", False))
        self.assertEqual(flagged[1].get("data_status"), "CARRY_FORWARD_DUPLICATE")
        self.assertFalse(flagged[2].get("is_carry_forward_duplicate", False))

        # 2. Verify PEAD feature engine filters out carry-forward duplicate
        ohlcv_df = pd.DataFrame({
            "symbol": ["CARRYTEST"] * 10,
            "trading_date": pd.date_range("2023-10-20", periods=10, freq="B").strftime("%Y-%m-%d").tolist(),
            "close": [100.0] * 10,
            "volume": [10000] * 10
        })

        fin_df = pd.DataFrame(flagged)
        pead_res = calculate_pead_features(ohlcv_df, fin_df)

        # On and after 2023-10-25, since 2023-09-30 filing was a carry-forward duplicate,
        # it was filtered out and thus is_observed_pead must be 0 and pead_reaction_score must be 0.0
        self.assertEqual(pead_res["is_observed_pead"].sum(), 0)
        self.assertEqual(pead_res["pead_reaction_score"].sum(), 0.0)

    def test_non_blocking_health_check_latency_and_hydration_status(self):
        """Verifies /api/v1/health exposes hydration_status and responds in < 25ms without SQLite locking."""
        from src.storage.hydration import get_hydration_status
        status = get_hydration_status()
        self.assertIn(status, ("HYDRATING", "READY", "INITIALIZING"))

        # Measure 5 consecutive health checks
        latencies = []
        for _ in range(5):
            t0 = time.perf_counter()
            resp = self.client.get("/api/v1/health")
            latencies.append((time.perf_counter() - t0) * 1000.0)
            self.assertEqual(resp.status_code, 200)

        data = resp.json()
        self.assertIn("hydration_status", data)
        self.assertIn(data["hydration_status"], ("HYDRATING", "READY"))
        avg_lat = sum(latencies) / len(latencies)
        self.assertLess(avg_lat, 25.0, f"Average health latency {avg_lat:.2f} ms exceeds 25.0 ms target")

    def test_supervisor_recovers_to_deterministic_baseline(self):
        """Verifies supervisor state machine recognizes Deterministic Baseline as valid NORMAL state."""
        from src.supervisor.state_machine import SupervisorStateMachine
        sup_mgr = SupervisorStateMachine(self.db)
        state = sup_mgr.evaluate_and_recover()
        self.assertEqual(state["status"], "NORMAL")
        self.assertEqual(state["active_model_id"], "baseline_deterministic")
        self.assertIn("Deterministic Baseline", state.get("model_name", ""))
        self.assertTrue(state["can_infer"])


if __name__ == "__main__":
    unittest.main()
