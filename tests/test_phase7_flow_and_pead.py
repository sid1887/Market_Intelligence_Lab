"""
tests/test_phase7_flow_and_pead.py
Comprehensive test suite verifying MIL 2.0 Phase 7 deliverables:
1. NSE Institutional Delivery Flow & Microstructure Accumulation Features.
2. PIT Post-Earnings Announcement Drift (PEAD) Engine with strict provenance gating.
3. Upgraded Two-Stage CPCV(6, 2) Tournament with exact Angel One delivery friction hurdle.
"""

import math
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

from src.ml.features.institutional_flow import (
    validate_and_clean_session_dates,
    compute_delivery_percentage_series,
    calculate_institutional_flow_features,
    FLOW_FEATURE_COLUMNS
)
from src.ml.features.pead_engine import (
    resolve_effective_filing_session,
    calculate_pead_features,
    PEAD_FEATURE_COLUMNS
)
from src.quant.ml_trainer import (
    TwoStageTournamentRunner,
    get_canonical_roundtrip_friction_rate,
    FEATURE_COLUMNS_8,
    FEATURE_COLUMNS_ALPHA_V2
)
from src.portfolio.fee_engine import (
    calculate_roundtrip_friction,
    ANGEL_ONE_DP_CHARGE,
    PROFILE_ZERO
)
from src.storage.database import DatabaseManager


class TestInstitutionalFlowFeatures(unittest.TestCase):
    """Verifies Deliverable 1: Delivery Flow and Microstructure Features."""

    def test_session_date_deduplication_and_sorting(self):
        """Tests that duplicate symbol-date entries are dropped and sorted chronologically."""
        raw_df = pd.DataFrame([
            {"symbol": "RELIANCE", "trading_date": "2026-01-05", "close": 2500.0},
            {"symbol": "RELIANCE", "trading_date": "2026-01-02", "close": 2480.0},
            {"symbol": "RELIANCE", "trading_date": "2026-01-02", "close": 2485.0},  # duplicate
            {"symbol": "TCS", "trading_date": "2026-01-02", "close": 3900.0},
        ])
        clean_df = validate_and_clean_session_dates(raw_df, drop_non_trading=False)
        self.assertEqual(len(clean_df), 3)
        # Check sort order
        rel_dates = clean_df[clean_df["symbol"] == "RELIANCE"]["trading_date"].tolist()
        self.assertEqual(rel_dates, ["2026-01-02", "2026-01-05"])
        # Check keep='last'
        rel_close_02 = clean_df[(clean_df["symbol"] == "RELIANCE") & (clean_df["trading_date"] == "2026-01-02")]["close"].values[0]
        self.assertEqual(rel_close_02, 2485.0)

    def test_clv_and_deliv_impulse_bounds_and_circuit_locks(self):
        """Tests Close Location Value (CLV) clamped to [0, 1] and circuit locks default to 0.5."""
        # 1. Flat candle (Circuit limit hit: High == Low)
        flat_df = pd.DataFrame([{
            "symbol": "INFY", "trading_date": "2026-01-02",
            "open": 1500.0, "high": 1500.0, "low": 1500.0, "close": 1500.0,
            "volume": 100000, "delivery_qty": 70000
        }])
        res = calculate_institutional_flow_features(flat_df)
        self.assertEqual(res.iloc[0]["clv_1d"], 0.5)
        # (2 * 0.5 - 1) = 0 -> deliv_clv_impulse must be 0.0
        self.assertEqual(res.iloc[0]["deliv_clv_impulse"], 0.0)

        # 2. Bullish candle: Close at high -> CLV = 1.0
        bull_df = pd.DataFrame([{
            "symbol": "INFY", "trading_date": "2026-01-02",
            "open": 1500.0, "high": 1550.0, "low": 1500.0, "close": 1550.0,
            "volume": 100000, "delivery_qty": 70000
        }])
        res_bull = calculate_institutional_flow_features(bull_df)
        self.assertAlmostEqual(res_bull.iloc[0]["clv_1d"], 1.0, places=4)

        # 3. Bearish candle: Close at low -> CLV = 0.0
        bear_df = pd.DataFrame([{
            "symbol": "INFY", "trading_date": "2026-01-02",
            "open": 1550.0, "high": 1550.0, "low": 1500.0, "close": 1500.0,
            "volume": 100000, "delivery_qty": 70000
        }])
        res_bear = calculate_institutional_flow_features(bear_df)
        self.assertAlmostEqual(res_bear.iloc[0]["clv_1d"], 0.0, places=4)

    def test_deliv_zscore_and_atpt_zscore_bounds(self):
        """Tests rolling 60-session z-scores are winsorized strictly to [-4.0, +4.0]."""
        dates = [f"2026-01-{i:02d}" for i in range(1, 32)] + [f"2026-02-{i:02d}" for i in range(1, 32)]
        records = []
        for i, d in enumerate(dates[:65]):
            # Extreme spike at the end
            deliv = 99.0 if i == 64 else 30.0 + (i % 5)
            turnover = 1e9 if i == 64 else 1e7
            records.append({
                "symbol": "TCS",
                "trading_date": d,
                "open": 3800.0,
                "high": 3850.0,
                "low": 3780.0,
                "close": 3820.0,
                "volume": 500000,
                "delivery_pct": deliv,
                "turnover": turnover,
                "trades_count": 5000
            })
        df = pd.DataFrame(records)
        res = calculate_institutional_flow_features(df)

        deliv_z = res["deliv_zscore_60d"].values
        atpt_z = res["atpt_zscore_60d"].values
        impulse = res["deliv_clv_impulse"].values

        # All values strictly within theoretical boundaries
        self.assertTrue(np.all(deliv_z >= -4.0))
        self.assertTrue(np.all(deliv_z <= 4.0))
        self.assertTrue(np.all(atpt_z >= -4.0))
        self.assertTrue(np.all(atpt_z <= 4.0))
        self.assertTrue(np.all(impulse >= -8.0))
        self.assertTrue(np.all(impulse <= 8.0))

    def test_pit_shareholding_delta_isolation(self):
        """Tests that shareholding filings are strictly gated by eligible_from_date."""
        daily_df = pd.DataFrame([
            {"symbol": "INFY", "trading_date": "2026-01-10", "close": 1500.0, "high": 1520.0, "low": 1490.0},
            {"symbol": "INFY", "trading_date": "2026-01-20", "close": 1520.0, "high": 1530.0, "low": 1510.0},
            {"symbol": "INFY", "trading_date": "2026-01-25", "close": 1540.0, "high": 1550.0, "low": 1530.0},
        ])
        # Filing published on 2026-01-21
        sh_df = pd.DataFrame([
            {
                "symbol": "INFY",
                "period_end_date": "2025-09-30",
                "eligible_from_date": "2025-10-21",
                "fii_pct": 32.0,
                "dii_pct": 34.0,
                "promoter_pledged_pct": 0.0
            },
            {
                "symbol": "INFY",
                "period_end_date": "2025-12-31",
                "eligible_from_date": "2026-01-21",  # Becomes eligible between 2026-01-20 and 2026-01-25
                "fii_pct": 35.0,  # FII+DII rose from 66% to 70% (+4.0%)
                "dii_pct": 35.0,
                "promoter_pledged_pct": 1.5  # Pledge rose +1.5%
            }
        ])
        res = calculate_institutional_flow_features(daily_df, shareholding_df=sh_df)

        # On 2026-01-10 and 2026-01-20: previous filing delta was 0.0 (first filing in series)
        row_20 = res[res["trading_date"] == "2026-01-20"].iloc[0]
        self.assertEqual(row_20["fii_dii_delta_qoq"], 0.0)
        self.assertEqual(row_20["promoter_pledge_delta"], 0.0)

        # On 2026-01-25: new filing is active (fii_dii delta = +4.0, pledge delta = +1.5)
        row_25 = res[res["trading_date"] == "2026-01-25"].iloc[0]
        self.assertAlmostEqual(row_25["fii_dii_delta_qoq"], 4.0, places=2)
        self.assertAlmostEqual(row_25["promoter_pledge_delta"], 1.5, places=2)


class TestPEADEngine(unittest.TestCase):
    """Verifies Deliverable 2: Post-Earnings Announcement Drift (PEAD) Engine."""

    def test_effective_filing_session_rolls_after_1530(self):
        """Tests that filings after 15:30 IST advance to the next open session."""
        # 16:30 IST on a Friday -> Next Monday
        eff_date, is_obs = resolve_effective_filing_session(
            "2026-01-09 16:30:00",  # 2026-01-09 is Friday
            provenance="OBSERVED_TIMESTAMP"
        )
        self.assertEqual(is_obs, 1)
        self.assertEqual(eff_date, "2026-01-12")  # Next Monday

        # 14:00 IST on a Tuesday -> Same day
        eff_date_same, is_obs_same = resolve_effective_filing_session(
            "2026-01-13 14:00:00",
            provenance="OBSERVED_TIMESTAMP"
        )
        self.assertEqual(is_obs_same, 1)
        self.assertEqual(eff_date_same, "2026-01-13")

    def test_strict_provenance_gating_statutory_fallback_isolation(self):
        """
        STRICT INVARIANT:
        Rows with STATUTORY_FALLBACK_LAG_* MUST have is_observed_pead = 0
        and pead_reaction_score = 0.0 to prevent artificial post-earnings drift spikes!
        """
        daily_df = pd.DataFrame([
            {"symbol": "INFY", "trading_date": "2026-02-15"},
            {"symbol": "INFY", "trading_date": "2026-02-16"},
            {"symbol": "INFY", "trading_date": "2026-02-17"},
        ])
        # Unobserved filing with statutory fallback lag (+45d)
        fin_df = pd.DataFrame([{
            "symbol": "INFY",
            "period_end_date": "2025-12-31",
            "published_at_ist": "2026-02-14",
            "pit_provenance": "STATUTORY_FALLBACK_LAG_45D",
            "eps": 18.5,
            "revenue": 40000.0,
            "ebitda": 9500.0
        }])

        res = calculate_pead_features(daily_df, fin_df)

        # Invariant check across all sessions
        for _, row in res.iterrows():
            self.assertEqual(row["is_observed_pead"], 0)
            self.assertEqual(row["pead_reaction_score"], 0.0)

    def test_observed_pead_exponential_decay_window(self):
        """Tests that observed filings produce decaying reaction score over 20 sessions."""
        dates = [f"2026-01-{i:02d}" for i in range(1, 32)]
        daily_df = pd.DataFrame([{"symbol": "TCS", "trading_date": d} for d in dates])

        # Historical 5 quarters to establish YoY EPS diff and std
        fin_df = pd.DataFrame([
            {"symbol": "TCS", "period_end_date": "2024-12-31", "published_at_ist": "2025-01-10 14:00:00", "pit_provenance": "OBSERVED_TIMESTAMP", "eps": 25.0, "revenue": 50000.0, "ebitda": 12000.0},
            {"symbol": "TCS", "period_end_date": "2025-03-31", "published_at_ist": "2025-04-10 14:00:00", "pit_provenance": "OBSERVED_TIMESTAMP", "eps": 26.0, "revenue": 52000.0, "ebitda": 12500.0},
            {"symbol": "TCS", "period_end_date": "2025-06-30", "published_at_ist": "2025-07-10 14:00:00", "pit_provenance": "OBSERVED_TIMESTAMP", "eps": 27.0, "revenue": 53000.0, "ebitda": 12800.0},
            {"symbol": "TCS", "period_end_date": "2025-09-30", "published_at_ist": "2025-10-10 14:00:00", "pit_provenance": "OBSERVED_TIMESTAMP", "eps": 28.0, "revenue": 55000.0, "ebitda": 13000.0},
            {"symbol": "TCS", "period_end_date": "2025-12-31", "published_at_ist": "2026-01-05 14:00:00", "pit_provenance": "OBSERVED_TIMESTAMP", "eps": 32.0, "revenue": 60000.0, "ebitda": 15000.0},
        ])

        res = calculate_pead_features(daily_df, fin_df)

        # Before 2026-01-05: score is 0.0
        row_02 = res[res["trading_date"] == "2026-01-02"].iloc[0]
        self.assertEqual(row_02["pead_reaction_score"], 0.0)

        # On 2026-01-05 (t=0): positive reaction score
        row_05 = res[res["trading_date"] == "2026-01-05"].iloc[0]
        self.assertEqual(row_05["is_observed_pead"], 1)
        self.assertGreater(row_05["pead_reaction_score"], 0.0)

        # On 2026-01-15 (t=10): reaction score must be decayed (smaller than t=0)
        row_15 = res[res["trading_date"] == "2026-01-15"].iloc[0]
        self.assertLess(row_15["pead_reaction_score"], row_05["pead_reaction_score"])
        self.assertGreater(row_15["pead_reaction_score"], 0.0)

        # Beyond 20 sessions (t > 20): score decays to 0.0
        row_31 = res[res["trading_date"] == "2026-01-31"].iloc[0]
        self.assertEqual(row_31["pead_reaction_score"], 0.0)


class TestTournamentAndExactFriction(unittest.TestCase):
    """Verifies Deliverable 3: Upgraded Model Tournament & Canonical Friction Hurdle."""

    def test_canonical_friction_rate_computation(self):
        """Verifies exact Angel One delivery fee drag matches fee_engine specification."""
        rate = get_canonical_roundtrip_friction_rate(ticket=5000.0, profile=PROFILE_ZERO)
        expected = calculate_roundtrip_friction(
            buy_turnover=5000.0,
            sell_turnover=5000.0,
            profile=PROFILE_ZERO,
            dp_override=ANGEL_ONE_DP_CHARGE
        ).fee_drag_pct / 100.0

        self.assertAlmostEqual(rate, expected, places=5)
        # On ₹5,000, friction is ~0.0070 (70 bps), far higher than naive 15 bps (0.0015)
        self.assertGreater(rate, 0.0050)
        self.assertLess(rate, 0.0100)

    def test_tournament_runner_with_alpha_v2_features(self):
        """Tests complete CPCV(6, 2) tournament execution across 3 candidates with alpha_v2 features."""
        np.random.seed(42)
        n_samples = 400

        # Construct synthetic feature matrix with all alpha_v2 features
        data = {
            "symbol": ["INFY"] * n_samples,
            "trading_date": [f"2025-{i//30+1:02d}-{i%30+1:02d}" for i in range(n_samples)],
            "close": np.random.uniform(1400.0, 1600.0, n_samples),
            "net_return": np.random.normal(0.002, 0.03, n_samples),
        }
        for feat in FEATURE_COLUMNS_ALPHA_V2:
            data[feat] = np.random.uniform(0.1, 0.9, n_samples)

        df = pd.DataFrame(data)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tf:
            summary_path = tf.name

        try:
            runner = TwoStageTournamentRunner(
                horizon_days=20,
                n_splits=6,
                n_test_splits=2,
                min_meta_prob=0.55,
                reference_ticket=5000.0,
                holdout_sessions=50,
                summary_path=summary_path,
                feature_set="alpha_v2_flow_pead"
            )

            self.assertEqual(len(runner.feature_cols), len(FEATURE_COLUMNS_ALPHA_V2))
            summary = runner.run_full_tournament(df=df)

            # Check tournament payload structure
            self.assertIn("baseline", summary)
            self.assertIn("candidates", summary)
            self.assertEqual(len(summary["candidates"]), 3)  # Ridge, HGB, ExtraTrees
            self.assertIn("champion", summary)
            self.assertEqual(summary["feature_set"], "alpha_v2_flow_pead")

            # Verify compact JSON size (< 15 KB)
            json_size = Path(summary_path).stat().st_size
            self.assertLess(json_size, 15360, f"Summary JSON exceeded 15 KB limit: {json_size} bytes")

        finally:
            Path(summary_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
