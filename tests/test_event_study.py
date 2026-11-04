import unittest
import math
import datetime
from src.storage.database import DatabaseManager
from src.quant.event_study import EventStudyEngine

class TestEventStudy(unittest.TestCase):
    """
    Exhaustive regression test suite for Milestone 2.3 Event Study Engine:
    - IST timestamp session alignment (market hours vs post-market)
    - Strict [-252, -21] estimation window isolation (20-session pre-event buffer)
    - Exact 232 return observations (233 price sessions) reconciliation
    - Rejection of insufficient estimation runway (< 253 price sessions)
    - Rejection of incomplete post-event data (AWAITING_POST_EVENT_DATA)
    - Event category provenance (administrative schedule notice vs earnings release)
    - CAR and AR calculation accuracy on synthetic event data
    - Non-causal epistemic language guardrails & statistical significance classification
    """

    def setUp(self):
        self.db = DatabaseManager(":memory:")
        self.engine = EventStudyEngine(self.db)
        # Synthetic trading calendar: 400 business days in 2025-2026
        base_d = datetime.date(2025, 1, 1)
        self.calendar = []
        curr = base_d
        while len(self.calendar) < 400:
            if curr.weekday() < 5:  # Monday to Friday
                self.calendar.append(curr.strftime("%Y-%m-%d"))
            curr += datetime.timedelta(days=1)

    def test_timestamp_alignment_market_hours_vs_post_market(self):
        """
        Verifies session alignment rule:
        - <= 15:30 IST on trading day -> aligns to that trading day.
        - > 15:30 IST (post-market) -> aligns to next trading session.
        - Weekend / holiday -> aligns to next trading session.
        """
        wednesday = self.calendar[50]
        thursday = self.calendar[51]

        # 1. Market hours release: 14:15 IST
        t0_mkt = self.engine.align_disclosure_to_trading_session(f"{wednesday} 14:15:00", self.calendar)
        self.assertEqual(t0_mkt, wednesday)

        # 2. Exact market close release: 15:30 IST
        t0_close = self.engine.align_disclosure_to_trading_session(f"{wednesday} 15:30:00", self.calendar)
        self.assertEqual(t0_close, wednesday)

        # 3. Post-market release: 16:45 IST -> must align to Thursday
        t0_post = self.engine.align_disclosure_to_trading_session(f"{wednesday} 16:45:00", self.calendar)
        self.assertEqual(t0_post, thursday)

        # 4. Saturday release: 11:00 IST -> must align to Monday (next trading session)
        friday = self.calendar[4]
        next_monday = self.calendar[5]
        sat_date = (datetime.datetime.strptime(friday, "%Y-%m-%d") + datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        t0_weekend = self.engine.align_disclosure_to_trading_session(f"{sat_date} 11:00:00", self.calendar)
        self.assertEqual(t0_weekend, next_monday)

    def test_insufficient_history_rejection(self):
        """
        Verifies that an event occurring with fewer than 253 price sessions of prior history
        is rejected with INSUFFICIENT_ESTIMATION_HISTORY rather than silently shortening the window.
        """
        dates_100 = self.calendar[:100]
        stock_recs = []
        bench_recs = []
        for i, d in enumerate(dates_100):
            stock_recs.append({
                "symbol": "TEST_SYM", "trading_date": d, "series": "EQ",
                "open": 100, "high": 102, "low": 99, "close": 100 + i * 0.1,
                "volume": 10000, "source": "test", "retrieval_timestamp": "now"
            })
            bench_recs.append({
                "index_name": "NIFTY 50", "trading_date": d, "index_type": "PRI",
                "open": 20000, "high": 20100, "low": 19900, "close": 20000 + i * 10,
                "volume": None, "source": "test", "retrieval_timestamp": "now"
            })
        self.db.upsert_ohlcv_records(stock_recs)
        self.db.upsert_index_daily(bench_recs)

        # Event at index 80 (only 80 sessions of prior history)
        event_d = dates_100[80]
        res = self.engine.run_event_study("TEST_SYM", event_d)
        self.assertEqual(res["status"], "INSUFFICIENT_ESTIMATION_HISTORY")
        self.assertEqual(res["required_sessions_before_event"], 253)
        self.assertEqual(res["available_sessions_before_event"], 80)
        self.assertIn("Insufficient historical runway", res["reason"])

    def test_post_event_boundary_rejection(self):
        """
        Verifies that when an event occurs at the end of the available dataset
        (or in the future), the engine returns AWAITING_POST_EVENT_DATA rather than manufacturing data.
        """
        dates_300 = self.calendar[:300]
        stock_recs = []
        bench_recs = []
        for i, d in enumerate(dates_300):
            stock_recs.append({
                "symbol": "RECENT_SYM", "trading_date": d, "series": "EQ",
                "open": 100, "high": 102, "low": 99, "close": 100 + i * 0.1,
                "volume": 10000, "source": "test", "retrieval_timestamp": "now"
            })
            bench_recs.append({
                "index_name": "NIFTY 50", "trading_date": d, "index_type": "PRI",
                "open": 20000, "high": 20100, "low": 19900, "close": 20000 + i * 10,
                "volume": None, "source": "test", "retrieval_timestamp": "now"
            })
        self.db.upsert_ohlcv_records(stock_recs)
        self.db.upsert_index_daily(bench_recs)

        # Case 1: Event on the very last available date (index 299)
        # Event window [0, +2] requires 2 future sessions that do not exist yet
        last_d = dates_300[-1]
        res_last = self.engine.run_event_study("RECENT_SYM", last_d)
        self.assertEqual(res_last["status"], "AWAITING_POST_EVENT_DATA")
        self.assertIn("Incomplete post-event history", res_last["reason"])

        # Case 2: Event on a future date not yet in the database (e.g. calendar index 350)
        future_d = self.calendar[350]
        res_future = self.engine.run_event_study("RECENT_SYM", future_d)
        self.assertEqual(res_future["status"], "AWAITING_POST_EVENT_DATA")
        self.assertIn("has not yet traded in the database", res_future["reason"])

    def test_synthetic_abnormal_returns_and_car_reconciliation(self):
        """
        Tests market model estimation, abnormal return (AR), and CAR
        using a synthetic dataset with known alpha, beta, and injected abnormal shock.
        Reconciles the exact 232 return observations (from 233 price sessions) in [-252, -21].
        """
        dates_350 = self.calendar[:350]
        event_idx = 280  # Leaves 280 days before event (> 253 required), and 70 days after
        event_d = dates_350[event_idx]

        stock_recs = []
        bench_recs = []
        p_s = 1000.0
        p_b = 20000.0

        for i, d in enumerate(dates_350):
            if i == 0:
                r_b = 0.0
                r_s = 0.0
            else:
                r_b = 0.01 * math.sin(i * 0.1)
                r_s = 0.001 + 1.2 * r_b
                if i == event_idx:
                    r_s += 0.05

            p_s *= (1.0 + r_s)
            p_b *= (1.0 + r_b)

            stock_recs.append({
                "symbol": "SHOCK_STOCK", "trading_date": d, "series": "EQ",
                "open": p_s, "high": p_s * 1.01, "low": p_s * 0.99, "close": p_s,
                "volume": 50000, "source": "test", "retrieval_timestamp": "now"
            })
            bench_recs.append({
                "index_name": "NIFTY 50", "trading_date": d, "index_type": "PRI",
                "open": p_b, "high": p_b * 1.01, "low": p_b * 0.99, "close": p_b,
                "volume": None, "source": "test", "retrieval_timestamp": "now"
            })

        self.db.upsert_ohlcv_records(stock_recs)
        self.db.upsert_index_daily(bench_recs)

        res = self.engine.run_event_study("SHOCK_STOCK", event_d, event_category="EARNINGS")
        self.assertEqual(res["status"], "SUCCESS")

        est = res["estimation_window"]
        self.assertAlmostEqual(est["model_alpha"], 0.001, places=3)
        self.assertAlmostEqual(est["model_beta"], 1.200, places=2)
        # Reconcile exact 232 return observations from 233 price sessions
        self.assertEqual(est["return_observations_count"], 232)
        self.assertEqual(est["price_sessions_count"], 233)

        # Injected abnormal return at t=0 was +5.0%
        evt = res["event_window"]
        self.assertAlmostEqual(evt["ar_t0_pct"], 5.0, places=1)

        # CAR [-1, +1] should be approximately +5.0%
        car_short = evt["car_short"]
        self.assertAlmostEqual(car_short["car_pct"], 5.0, places=1)
        self.assertTrue(car_short["is_statistically_significant"])

        # Hypothesis guardrails
        hypo = res["explanatory_hypothesis"]
        self.assertIn("explanatory hypothesis", hypo)
        self.assertIn("statistically significant", hypo)
        self.assertNotIn("caused the stock to", hypo)
        self.assertNotIn("resulted in the drop", hypo)

    def test_event_category_classification_and_provenance(self):
        """
        Verifies that an administrative board meeting schedule notification
        is explicitly tagged in the hypothesis so it cannot be misconstrued as an earnings reaction.
        """
        dates_350 = self.calendar[:350]
        event_idx = 280
        event_d = dates_350[event_idx]

        stock_recs = []
        bench_recs = []
        p_s = 1000.0
        p_b = 20000.0

        for i, d in enumerate(dates_350):
            r_b = 0.005 * math.sin(i * 0.1) if i > 0 else 0.0
            r_s = 0.001 + 0.9 * r_b if i > 0 else 0.0
            p_s *= (1.0 + r_s)
            p_b *= (1.0 + r_b)

            stock_recs.append({
                "symbol": "NOTICE_STOCK", "trading_date": d, "series": "EQ",
                "open": p_s, "high": p_s, "low": p_s, "close": p_s,
                "volume": 50000, "source": "test", "retrieval_timestamp": "now"
            })
            bench_recs.append({
                "index_name": "NIFTY 50", "trading_date": d, "index_type": "PRI",
                "open": p_b, "high": p_b, "low": p_b, "close": p_b,
                "volume": None, "source": "test", "retrieval_timestamp": "now"
            })

        self.db.upsert_ohlcv_records(stock_recs)
        self.db.upsert_index_daily(bench_recs)

        res = self.engine.run_event_study(
            "NOTICE_STOCK", event_d, event_category="BOARD_MEETING_SCHEDULE"
        )
        self.assertEqual(res["status"], "SUCCESS")

        hypo = res["explanatory_hypothesis"]
        self.assertIn("administrative notice of meeting schedule", hypo)
        self.assertIn("cannot be interpreted as a market response to underlying financial performance", hypo)

    def test_future_event_date_returns_awaiting_post_event_data_with_no_numerical_metrics(self):
        """
        Regression Test (Item B.4):
        Verifies that an event occurring beyond the settled market data cutoff
        (such as Q2 earnings effective session 2026-10-26 when dataset ends 2026-10-23):
        1. Returns status 'AWAITING_POST_EVENT_DATA'.
        2. Does NOT calculate or publish numerical AR, CAR, t-statistics, or p-values.
        3. Never manufactures synthetic prices or future observations.
        """
        dates_300 = self.calendar[:300]
        stock_recs = []
        bench_recs = []
        for i, d in enumerate(dates_300):
            stock_recs.append({
                "symbol": "CUTOFF_SYM", "trading_date": d, "series": "EQ",
                "open": 1000.0, "high": 1010.0, "low": 990.0, "close": 1000.0 + i,
                "volume": 25000, "source": "test", "retrieval_timestamp": "now"
            })
            bench_recs.append({
                "index_name": "NIFTY 50", "trading_date": d, "index_type": "PRI",
                "open": 20000.0, "high": 20100.0, "low": 19900.0, "close": 20000.0 + i * 5,
                "volume": None, "source": "test", "retrieval_timestamp": "now"
            })
        self.db.upsert_ohlcv_records(stock_recs)
        self.db.upsert_index_daily(bench_recs)

        # Event occurs on next calendar day (index 300) beyond the available dataset
        future_event_date = self.calendar[300]
        res = self.engine.run_event_study(
            symbol="CUTOFF_SYM",
            effective_event_date=future_event_date,
            benchmark_name="NIFTY 50",
            event_category="EARNINGS"
        )

        self.assertEqual(res["status"], "AWAITING_POST_EVENT_DATA")
        self.assertIn("has not yet traded in the database", res["reason"])
        self.assertNotIn("event_window", res)
        self.assertNotIn("ar_t0_pct", res)
        self.assertNotIn("car_short", res)
        self.assertNotIn("t_stat", res)
        self.assertNotIn("p_value", res)

    def test_event_study_isolation_schedule_metrics_never_assigned_to_earnings(self):
        """
        Regression Test (Item B.3 & B.4):
        Verifies that historical event study results from an administrative schedule announcement
        (e.g. INFY_DISC_20261015_SCHED with AR = +4.23%) are strictly quarantined by disclosure_id
        and are NEVER assigned to or reported as the actual Q2 earnings disclosure (INFY_DISC_20261023_Q2).
        """
        # Seed an administrative schedule result
        self.db.record_event_study_result({
            "symbol": "INFY",
            "disclosure_id": "INFY_DISC_20261015_SCHED",
            "event_date": "2026-10-16",
            "estimation_window_start": "2025-10-06",
            "estimation_window_end": "2026-09-16",
            "model_alpha": -0.000953,
            "model_beta": 0.7368,
            "model_r2": 0.1022,
            "ar_t0": 0.04231,
            "car_minus1_plus1": 0.03416,
            "car_0_plus2": 0.06163,
            "t_stat": 1.06,
            "p_value": 0.2884,
            "explanatory_hypothesis": "Administrative schedule notice",
            "calculated_at": "2026-10-25T14:30:00Z"
        })

        # Query database for earnings disclosure ID
        earnings_studies = [
            s for s in self.db.get_event_study_results("INFY")
            if s["disclosure_id"] == "INFY_DISC_20261023_Q2"
        ]
        # Must be empty because effective session 2026-10-26 has not occurred
        self.assertEqual(len(earnings_studies), 0)

        # All existing studies must match their respective disclosure IDs
        all_studies = self.db.get_event_study_results("INFY")
        for s in all_studies:
            self.assertNotEqual(s["disclosure_id"], "INFY_DISC_20261023_Q2")
            if s["disclosure_id"] == "INFY_DISC_20261015_SCHED":
                self.assertEqual(s["event_date"], "2026-10-16")

if __name__ == "__main__":
    unittest.main()
