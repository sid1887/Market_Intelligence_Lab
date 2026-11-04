import unittest
import math
from src.quant.metrics import (
    calculate_returns_and_volatility,
    calculate_drawdowns,
    calculate_52_week_position,
    calculate_liquidity_metrics
)

class TestQuantMetrics(unittest.TestCase):
    """Unit tests for deterministic mathematical models, annualization conventions, and corporate actions."""

    def test_cagr_conventions_distinction(self):
        """
        Verify that Calendar-time CAGR and Trading-day Annualization
        are strictly distinguished and match their exact theoretical values.
        """
        # Starting: 100 on 2025-01-01, Ending: 80 on 2026-01-01 (exactly 365 calendar days)
        # Over 253 trading sessions (N=253, N-1 = 252 return intervals)
        records = [
            {"trading_date": "2025-01-01", "close": 100.0}
        ]
        # Generate synthetic 251 intermediate days ending at 2026-01-01
        for i in range(1, 252):
            records.append({"trading_date": f"2025-temp-{i}", "close": 90.0})
        records.append({"trading_date": "2026-01-01", "close": 80.0})

        res = calculate_returns_and_volatility(records)

        # 1. Total Price Return: (80 - 100) / 100 = -20.0%
        self.assertAlmostEqual(res["unadjusted_price_return"], -0.20, places=4)

        # 2. Calendar-Time CAGR over 365 days: (80/100)^(365.25 / 365) - 1
        # (0.80)^(1.000685) - 1 ≈ -19.988%
        expected_calendar_cagr = (0.80 ** (365.25 / 365)) - 1.0
        self.assertAlmostEqual(res["calendar_cagr"], expected_calendar_cagr, places=4)

        # 3. Trading-Day Annualization over 252 return intervals: (80/100)^(252 / 252) - 1 = -20.0%
        expected_trading_ann = (0.80 ** (252.0 / 252)) - 1.0
        self.assertAlmostEqual(res["trading_day_annualized"], expected_trading_ann, places=4)

        # Confirm they differ when intervals/days differ
        self.assertNotEqual(res["calendar_cagr"], res["trading_day_annualized"])

    def test_dividend_eligibility_at_start_date(self):
        """
        Verify the crucial financial logic:
        An investor purchasing at the closing price of Date[0] (which is already the ex-date)
        is NOT entitled to that day's dividend! Only subsequent dividends are eligible.
        """
        records = [
            {"trading_date": "2025-10-27", "close": 1504.50},  # Day 0: Ex-date for Rs 23
            {"trading_date": "2026-06-10", "close": 1143.90},  # Day 1: Ex-date for Rs 25
            {"trading_date": "2026-10-23", "close": 1153.80}   # Terminal close
        ]
        corporate_actions = [
            {
                "symbol": "INFY",
                "ex_date": "2025-10-27",
                "action_type": "DIVIDEND",
                "purpose": "Interim Dividend - Rs 23 Per Share",
                "adjustment_factor": 1.0
            },
            {
                "symbol": "INFY",
                "ex_date": "2026-06-10",
                "action_type": "DIVIDEND",
                "purpose": "Dividend - Rs 25 Per Share",
                "adjustment_factor": 1.0
            }
        ]

        res = calculate_returns_and_volatility(records, corporate_actions)

        # 1. Unadjusted Price Return: (1153.80 - 1504.50) / 1504.50 = -23.3101%
        self.assertAlmostEqual(res["unadjusted_price_return"], -0.233101, places=4)

        # 2. Eligible Cash Dividends: ONLY Rs 25, NOT Rs 48!
        self.assertEqual(res["eligible_cash_dividends"], 25.0)
        self.assertEqual(res["total_cash_dividends_in_window"], 48.0)

        # 3. Cash-inclusive return from 2025-10-27 close:
        # (1153.80 + 25.00 - 1504.50) / 1504.50 = -325.70 / 1504.50 = -21.6484%
        self.assertAlmostEqual(res["cash_inclusive_return_eligible"], -0.216484, places=4)

        # 4. Dividend contribution from eligible dividend: 25 / 1504.50 = +1.6617%
        self.assertAlmostEqual(res["dividend_yield_contribution_eligible"], 0.016617, places=4)

    def test_pre_ex_comparison_scenario(self):
        """
        Verify Scenario B: An investor buying at the cum-dividend pre-ex close (e.g. 1525.40 on 2025-10-24)
        is entitled to BOTH dividends (Rs 23 + Rs 25 = Rs 48).
        """
        records = [
            {"trading_date": "2025-10-27", "close": 1504.50},
            {"trading_date": "2026-10-23", "close": 1153.80}
        ]
        corporate_actions = [
            {"ex_date": "2025-10-27", "action_type": "DIVIDEND", "purpose": "Rs 23"},
            {"ex_date": "2026-06-10", "action_type": "DIVIDEND", "purpose": "Rs 25"}
        ]

        # Starting price on 2025-10-24 is 1525.40
        res = calculate_returns_and_volatility(
            records,
            corporate_actions,
            pre_ex_start_price=1525.40,
            pre_ex_start_date="2025-10-24"
        )

        pre_sc = res["pre_ex_scenario"]
        self.assertIsNotNone(pre_sc)

        # Unadjusted: (1153.80 - 1525.40) / 1525.40 = -371.60 / 1525.40 = -24.3608%
        self.assertAlmostEqual(pre_sc["unadjusted_return"], -0.243608, places=4)

        # Cash-inclusive: (1153.80 + 48.00 - 1525.40) / 1525.40 = -323.60 / 1525.40 = -21.2141%
        self.assertAlmostEqual(pre_sc["cash_inclusive_return"], -0.212141, places=4)
        self.assertEqual(pre_sc["all_cash_dividends"], 48.0)

    def test_drawdowns_calculation(self):
        # Peak = 120, Trough = 90 -> MDD = (90 - 120)/120 = -25.0%
        records = [
            {"trading_date": "2026-01-01", "close": 100.0},
            {"trading_date": "2026-01-02", "close": 120.0},
            {"trading_date": "2026-01-03", "close": 90.0},
            {"trading_date": "2026-01-04", "close": 110.0}
        ]
        dd_res = calculate_drawdowns(records)
        self.assertAlmostEqual(dd_res["price_only_max_drawdown"], -0.25, places=4)
        self.assertAlmostEqual(dd_res["mdd_percentage"], -25.0, places=2)
        self.assertEqual(dd_res["peak_date"], "2026-01-02")
        self.assertEqual(dd_res["peak_close"], 120.0)
        self.assertEqual(dd_res["trough_date"], "2026-01-03")
        self.assertEqual(dd_res["trough_close"], 90.0)

    def test_drawdown_exact_numerical_consistency(self):
        """
        Regression Test:
        Verifies that maximum drawdown strictly satisfies:
        MDD = (trough_close - peak_close) / peak_close
        using exact stored observations for INFY (Peak close = 1689.8 on 2026-01-16,
        Trough close = 985.3 on 2026-07-01).
        Verifies that -41.6913% (rounds to -41.69%) is mathematically exact,
        and that mixing intraday extremes (980.40 / 1680.00 = -41.64%) is rejected.
        """
        records = [
            {"trading_date": "2026-01-15", "close": 1599.8},
            {"trading_date": "2026-01-16", "close": 1689.8},  # True Peak Close
            {"trading_date": "2026-01-19", "close": 1681.2},
            {"trading_date": "2026-06-30", "close": 1000.4},
            {"trading_date": "2026-07-01", "close": 985.3},   # True Trough Close
            {"trading_date": "2026-07-02", "close": 995.0}
        ]

        res = calculate_drawdowns(records)

        # 1. Exact Peak and Trough Close
        self.assertEqual(res["peak_date"], "2026-01-16")
        self.assertEqual(res["peak_close"], 1689.8)
        self.assertEqual(res["trough_date"], "2026-07-01")
        self.assertEqual(res["trough_close"], 985.3)

        # 2. Mathematical Identity Check
        expected_mdd = (985.3 - 1689.8) / 1689.8  # -704.5 / 1689.8 = -0.416913244...
        self.assertAlmostEqual(res["price_only_max_drawdown"], expected_mdd, places=8)
        self.assertAlmostEqual(res["mdd_percentage"], -41.6913244, places=4)
        self.assertEqual(f"{res['mdd_percentage']:.2f}%", "-41.69%")

        # 3. Reject the erroneous calculation (980.40 - 1680.00) / 1680.00 = -41.64%
        erroneous_mdd = (980.40 - 1680.00) / 1680.00
        self.assertNotAlmostEqual(res["price_only_max_drawdown"], erroneous_mdd, places=4)
        self.assertNotEqual(f"{res['mdd_percentage']:.2f}%", f"{erroneous_mdd * 100.0:.2f}%")

    def test_52_week_position(self):
        records = [
            {"trading_date": "2026-01-01", "high": 200.0, "low": 100.0, "close": 100.0},
            {"trading_date": "2026-01-02", "high": 200.0, "low": 100.0, "close": 150.0}
        ]
        res = calculate_52_week_position(records)
        self.assertAlmostEqual(res["52w_high"], 200.0)
        self.assertAlmostEqual(res["52w_low"], 100.0)
        self.assertAlmostEqual(res["position_in_range_pct"], 50.0)

if __name__ == "__main__":
    unittest.main()
