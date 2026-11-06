"""
Unit and Integration Tests for Milestone B9.0:
Data Bedrock Expansion, Synthesis Decision Engine & Compounding ML Feedback Ledger.
"""

import unittest
import datetime
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.client.backfill_manager import BackfillManager
from src.explanation.decision_engine import InvestmentDecisionEngine
from src.quant.feedback_evaluator import FeedbackEvaluator
from src.api.main import app


class TestMilestoneB9Compounding(unittest.TestCase):
    """
    Test suite verifying universe expansion, benchmark isolation, 5-year OHLCV bedrock,
    institutional memo synthesis, and compounding ML feedback ledgers.
    """

    def setUp(self):
        self.db = DatabaseManager()
        self.db.init_schema()
        self.decision_engine = InvestmentDecisionEngine(self.db)
        self.evaluator = FeedbackEvaluator(self.db)
        self.client = TestClient(app)

    def test_universe_expansion_and_benchmark_isolation(self):
        """
        Pillar 1: Verify NIFTY 500 constituents in securities_master,
        ensuring strict benchmark isolation (index_membership_history untouched).
        """
        with self.db.get_connection() as conn:
            # 1. Total securities count in master >= 500
            cur = conn.execute("SELECT COUNT(*) as cnt FROM securities_master")
            total_sec = cur.fetchone()["cnt"]
            self.assertGreaterEqual(total_sec, 500, "securities_master must contain at least 500 constituents")

            # 2. Strict NIFTY 50 benchmark isolation
            cur_n50 = conn.execute("SELECT COUNT(*) as cnt FROM securities_master WHERE is_nifty50 = 1 AND is_active = 1")
            n50_active = cur_n50.fetchone()["cnt"]
            self.assertEqual(n50_active, 50, "Exactly 50 active constituents must have is_nifty50 = 1 and is_active = 1")

            # 3. index_membership_history must remain exactly 300 records
            cur_idx = conn.execute("SELECT COUNT(*) as cnt FROM index_membership_history")
            idx_count = cur_idx.fetchone()["cnt"]
            self.assertEqual(idx_count, 300, "index_membership_history must remain untouched with exactly 300 records")

    def test_historical_bedrock_5year_depth(self):
        """
        Pillar 1: Verify 5-year OHLCV bedrock (>= 1,250 bars) for tracked instruments
        and strict candlestick invariants.
        """
        tracked = ["INFY", "TCS", "SUZLON", "TRIDENT", "MOREPENLAB"]
        with self.db.get_connection() as conn:
            for sym in tracked:
                cur = conn.execute(
                    "SELECT COUNT(*) as cnt, MIN(trading_date) as min_d, MAX(trading_date) as max_d FROM ohlcv_daily WHERE symbol = ? AND series = 'EQ'",
                    (sym,)
                )
                row = cur.fetchone()
                cnt = row["cnt"]
                self.assertGreaterEqual(cnt, 1250, f"{sym} must have >= 1,250 daily bars for 5-year depth (found {cnt})")
                self.assertLessEqual(row["min_d"], "2021-10-28", f"{sym} earliest date must extend to 2021 or earlier (found {row['min_d']})")

                # Invariant check: high >= max(open, close), low <= min(open, close), low > 0, volume > 0
                cur_inv = conn.execute(
                    """
                    SELECT COUNT(*) as corrupted FROM ohlcv_daily
                    WHERE symbol = ? AND (
                        high < open OR high < close OR low > open OR low > close OR low <= 0 OR volume <= 0
                    )
                    """,
                    (sym,)
                )
                corrupted = cur_inv.fetchone()["corrupted"]
                self.assertEqual(corrupted, 0, f"Found {corrupted} corrupted candlestick bars for {sym}")

    def test_investment_decision_memo_synthesis(self):
        """
        Pillar 2: Verify that InvestmentDecisionEngine generates a complete, deterministic memo.
        """
        memo = self.decision_engine.generate_memo("INFY")

        # Required fields
        self.assertEqual(memo["symbol"], "INFY")
        self.assertIn("verdict", memo)
        self.assertIn(
            memo["verdict"],
            ["STRONG_BUY_COMPOUNDER", "TACTICAL_SWING_LONG", "HOLD_FAIRLY_VALUED", "AVOID_CAPITAL_PRESERVATION"]
        )
        self.assertIn("target_horizon", memo)
        self.assertIsInstance(memo["institutional_conviction_score"], int)
        self.assertTrue(0 <= memo["institutional_conviction_score"] <= 100)

        # Business Profile
        bp = memo["business_profile"]
        self.assertTrue(len(bp["operating_segments"]) > 10)
        self.assertTrue(len(bp["core_revenue_drivers"]) > 10)
        self.assertTrue(len(bp["geographic_concentration"]) > 5)

        # 4-Point Health Checklist
        checklist = memo["health_checklist"]
        self.assertEqual(len(checklist), 4)
        diag_ids = {c["id"] for c in checklist}
        self.assertEqual(diag_ids, {"solvency_leverage", "dilution_promoters", "structural_trend", "valuation_percentile"})
        for c in checklist:
            self.assertIn(c["status"], ["PASS", "CAUTION", "FAIL"])
            self.assertTrue(len(c["detail"]) > 5)

        # Bull & Bear Cases (3 points each)
        self.assertEqual(len(memo["bull_case"]), 3)
        self.assertEqual(len(memo["bear_case"]), 3)

    def test_compounding_feedback_evaluator_ledgers(self):
        """
        Pillar 3: Verify forecast and catalyst audit ledgers, evaluation mechanics, and weight tuning.
        """
        today_iso = datetime.date.today().strftime("%Y-%m-%d")

        # 1. Record Forecast
        fc_id = self.evaluator.record_forecast(
            symbol="INFY",
            prediction_date="2026-10-01",
            horizon_days=20,
            target_evaluation_date="2026-10-23",
            current_price=1050.0,
            expected_price=1100.0,
            lower_80=1020.0,
            upper_80=1180.0,
            lower_95=980.0,
            upper_95=1220.0
        )
        self.assertTrue(fc_id.startswith("FC_INFY_"))

        # 2. Record Catalyst
        cat_id = self.evaluator.record_catalyst(
            symbol="INFY",
            article_id="ART_TEST_001",
            published_at="2026-10-01T10:00:00Z",
            direction="BULLISH",
            price_at_publish=1050.0
        )
        self.assertTrue(cat_id.startswith("CAT_INFY_"))

        # 3. Evaluate Predictions
        eval_res = self.evaluator.evaluate_past_predictions(as_of_date="2026-10-28")
        self.assertIn("accuracy_summary", eval_res)
        summary = eval_res["accuracy_summary"]
        self.assertIn("forecast_model", summary)
        self.assertIn("catalyst_model", summary)

        # 4. Institutional Conviction Dynamic Weight Tuning
        conviction = self.evaluator.calculate_institutional_conviction(
            symbol="INFY",
            tech_score=80.0,
            fund_score=85.0,
            news_score=75.0,
            forecast_score=70.0
        )
        self.assertTrue(0 <= conviction["institutional_conviction_score"] <= 100)
        self.assertIn("weights", conviction)
        total_w = sum(conviction["weights"].values())
        self.assertAlmostEqual(total_w, 1.0, places=2)

    def test_api_memo_and_accuracy_endpoints(self):
        """
        Phase 4: Verify FastAPI endpoints for memo and system accuracy with ngrok headers.
        """
        # GET /api/v1/stocks/INFY/memo
        r_memo = self.client.get(
            "/api/v1/stocks/INFY/memo",
            headers={"ngrok-skip-browser-warning": "true"}
        )
        self.assertEqual(r_memo.status_code, 200)
        memo_json = r_memo.json()
        self.assertEqual(memo_json["symbol"], "INFY")
        self.assertIn("verdict", memo_json)
        self.assertIn("institutional_conviction_score", memo_json)

        # GET /api/v1/system/accuracy
        r_acc = self.client.get(
            "/api/v1/system/accuracy",
            headers={"ngrok-skip-browser-warning": "true"}
        )
        self.assertEqual(r_acc.status_code, 200)
        acc_json = r_acc.json()
        self.assertIn("forecast_model", acc_json)
        self.assertIn("catalyst_model", acc_json)
        self.assertIn(acc_json["forecast_model"]["status"], ["CALIBRATED", "DRIFT_DETECTED", "PENDING_MATURITY"])


if __name__ == "__main__":
    unittest.main()
