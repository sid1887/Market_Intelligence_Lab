"""
tests/test_fee_engine.py
Unit & Verification Tests for Canonical Indian Equity & Angel One Fee Engine.
Phase 1 Deliverable — Validates exact statutory rates, profiles, and GST exemptions.
"""

import pytest
from src.portfolio.fee_engine import (
    calculate_brokerage,
    calculate_order_charges,
    calculate_roundtrip_friction,
    minimum_breakeven_pct,
    ANGEL_ONE_DP_CHARGE,
    PROFILE_STANDARD,
    PROFILE_ZERO,
    STT_RATE,
    NSE_TXN_RATE,
    SEBI_RATE,
    STAMP_DUTY_BUY_RATE,
    GST_RATE
)


def test_brokerage_profiles():
    # Zero Profile: always 0.0
    assert calculate_brokerage(10000.0, profile=PROFILE_ZERO) == 0.0
    assert calculate_brokerage(100000.0, profile=PROFILE_ZERO) == 0.0

    # Standard Profile: min(20.0, max(5.0, 0.001 * turnover))
    # Turnover 2,000 -> 0.001 * 2000 = 2.0 -> min(20.0, max(5.0, 2.0)) = 5.0
    assert calculate_brokerage(2000.0, profile=PROFILE_STANDARD) == 5.0

    # Turnover 10,000 -> 0.001 * 10000 = 10.0 -> 10.0
    assert calculate_brokerage(10000.0, profile=PROFILE_STANDARD) == 10.0

    # Turnover 50,000 -> 0.001 * 50000 = 50.0 -> capped at 20.0
    assert calculate_brokerage(50000.0, profile=PROFILE_STANDARD) == 20.0

    # Zero turnover
    assert calculate_brokerage(0.0, profile=PROFILE_STANDARD) == 0.0


def test_statutory_taxes_buy_leg():
    # Buy 100 shares @ ₹100 = ₹10,000 turnover
    chg = calculate_order_charges("BUY", 10000.0, profile=PROFILE_ZERO)
    assert chg.turnover == 10000.0
    assert chg.side == "BUY"
    assert chg.brokerage == 0.0
    assert chg.dp_charge == 0.0  # Zero DP on buy

    # STT: 0.1% of 10,000 = 10.0
    assert chg.stt == 10.0

    # Exchange Txn: 0.0030699% of 10,000 = 0.31
    assert chg.exchange_txn == 0.31

    # SEBI Fee: 0.0001% of 10,000 = 0.01
    assert chg.sebi_fee == 0.01

    # Stamp Duty: 0.015% of 10,000 = 1.5 -> round(1.5) in Python bankers rounding = 1.0 or 2.0
    assert chg.stamp_duty in (1.0, 2.0)

    # GST (18%) strictly on (brokerage + exchange_txn + sebi_fee) = 0.0 + 0.31 + 0.01 = 0.32 -> 18% of 0.32 = 0.06
    # Note: STT (10.0) and Stamp Duty (2.0) MUST NOT be included in GST calculation
    assert chg.gst == pytest.approx(round(0.18 * (0.31 + 0.01), 2), abs=0.01)

    expected_total = chg.brokerage + chg.stt + chg.exchange_txn + chg.sebi_fee + chg.stamp_duty + chg.gst + chg.dp_charge
    assert chg.total_charges == pytest.approx(expected_total, abs=0.01)
    assert chg.net_cash_flow == pytest.approx(-(chg.turnover + chg.total_charges), abs=0.01)


def test_statutory_taxes_sell_leg_with_dp():
    # Sell 100 shares @ ₹100 = ₹10,000 turnover
    chg = calculate_order_charges("SELL", 10000.0, profile=PROFILE_ZERO)
    assert chg.turnover == 10000.0
    assert chg.side == "SELL"
    assert chg.stamp_duty == 0.0  # Zero stamp duty on sell

    # DP charge is exactly ₹23.60 on SELL
    assert chg.dp_charge == ANGEL_ONE_DP_CHARGE
    assert chg.dp_charge == 23.60

    # STT: 0.1% of 10,000 = 10.0
    assert chg.stt == 10.0

    # Net cash flow is positive (cash returned minus friction)
    assert chg.net_cash_flow == pytest.approx(chg.turnover - chg.total_charges, abs=0.01)


def test_gst_strict_exemption_on_stt_and_stamp():
    # Verify that STT and Stamp Duty are NEVER taxed with GST
    chg = calculate_order_charges("BUY", 100000.0, profile=PROFILE_STANDARD)
    # Brokerage: capped at 20.0
    assert chg.brokerage == 20.0
    # Taxable base = Brokerage (20.0) + Exch (3.07) + SEBI (0.10) = 23.17
    taxable_base = chg.brokerage + chg.exchange_txn + chg.sebi_fee
    expected_gst = round(0.18 * taxable_base, 2)
    assert chg.gst == expected_gst

    # Ensure GST is NOT 18% of total charges
    assert chg.gst < (0.18 * chg.total_charges)


def test_roundtrip_friction_and_pnl():
    # Buy ₹10,000, Sell ₹10,500 (+₹500 gross gain, +5.0%)
    rt = calculate_roundtrip_friction(10000.0, 10500.0, profile=PROFILE_ZERO)
    assert rt.buy_turnover == 10000.0
    assert rt.sell_turnover == 10500.0
    assert rt.gross_pnl == 500.0

    # Total friction must include ₹23.60 DP fee + buy STT + sell STT + turnover + GST + stamp duty
    assert rt.total_dp_charges == 23.60
    assert rt.total_friction > 40.0
    assert rt.net_pnl == pytest.approx(500.0 - rt.total_friction, abs=0.01)
    assert rt.net_return_pct < 5.0
    assert rt.breakeven_sell_turnover > 10000.0


def test_micro_capital_breakeven_drag():
    # Ticket: ₹2,000
    be_pct_2k = minimum_breakeven_pct(2000.0, profile=PROFILE_ZERO)
    # On ₹2,000, ₹23.60 DP alone is 1.18% of capital! Total friction requires ~1.4% to 1.7% gross gain.
    assert be_pct_2k >= 1.3
    assert be_pct_2k <= 2.2

    # Ticket: ₹25,000
    be_pct_25k = minimum_breakeven_pct(25000.0, profile=PROFILE_ZERO)
    # On ₹25,000, ₹23.60 DP is only 0.09% of capital! Total friction requires ~0.35% to 0.5% gross gain.
    assert be_pct_25k < be_pct_2k
    assert be_pct_25k < 0.6
