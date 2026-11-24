"""
src/portfolio/fee_engine.py
Canonical Indian Equity Cash Delivery & Angel One Fee Engine.
Phase 1 Deliverable — Replaces all hardcoded fee constants across the codebase.

Specifications (Indian Cash Delivery Equity — NSE):
1. Profiles (via MIL_BROKER_PROFILE, default: angel_one_delivery_2026_standard):
   - 'angel_one_delivery_2026_zero': ₹0.00 delivery brokerage (iTrade Prime zero-brokerage delivery).
   - 'angel_one_delivery_2026_standard': min(20.0, max(5.0, 0.001 * turnover)) per executed delivery order.
2. Statutory & Regulatory Taxes:
   - Securities Transaction Tax (STT): 0.1% (0.001) on Buy and 0.1% on Sell, rounded to nearest rupee.
   - NSE Exchange Transaction Charge: 0.0030699% (0.000030699) on both Buy and Sell turnover.
   - SEBI Turnover Fee: 0.0001% (0.000001 = ₹10/crore) on both Buy and Sell turnover.
   - Stamp Duty: 0.015% (0.00015) on Buy turnover only, rounded to nearest rupee.
   - Goods & Services Tax (GST): 18% strictly on (Brokerage + Exchange Txn + SEBI Fee).
     STT and Stamp Duty are statutory government levies and are EXEMPT from GST.
3. Depository Participant (DP) Charges:
   - Angel One / CDSL standard: ₹20.00 base + 18% GST = ₹23.60 per ISIN per sell settlement debit (₹0 on buy).
"""

import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

logger = logging.getLogger("MIL.FeeEngine")

# Supported Brokerage Profiles
PROFILE_ZERO = "angel_one_delivery_2026_zero"
PROFILE_STANDARD = "angel_one_delivery_2026_standard"
DEFAULT_PROFILE = PROFILE_ZERO

# Exact Statutory Rates (NSE Cash Delivery)
STT_RATE = 0.001                  # 0.1% on Buy & Sell
NSE_TXN_RATE = 0.000030699        # 0.0030699% on Buy & Sell
SEBI_RATE = 0.000001              # ₹10 per crore (0.0001%)
STAMP_DUTY_BUY_RATE = 0.00015     # 0.015% on Buy only
GST_RATE = 0.18                   # 18% on Brokerage + Txn + SEBI

# Depository Participant (DP) Fee (CDSL + Angel One)
# Base: ₹16.50 (Angel One) + ₹3.50 (CDSL) = ₹20.00. Plus 18% GST (₹3.60) = ₹23.60.
ANGEL_ONE_BASE_DP = 20.00
ANGEL_ONE_DP_CHARGE = 23.60       # ₹23.60 per ISIN per sell debit

# Baseline institutional friction hurdles for ML training & alpha models
STATUTORY_ROUNDTRIP_RATE = round((STT_RATE * 2) + (NSE_TXN_RATE * 2) + (SEBI_RATE * 2) + STAMP_DUTY_BUY_RATE, 6)
DEFAULT_HURDLE_RATE = 0.0015      # 15 bps institutional minimum hurdle (ADR-0008)


@dataclass(frozen=True)
class OrderCharges:
    """Itemized statutory taxes, depository fees, and brokerage for a single order leg."""
    side: str                     # 'BUY' or 'SELL'
    turnover: float
    brokerage: float
    stt: float
    exchange_txn: float
    sebi_fee: float
    stamp_duty: float
    gst: float
    dp_charge: float
    total_charges: float
    net_cash_flow: float          # Negative for cash spent (BUY), positive for cash received (SELL)


@dataclass(frozen=True)
class RoundtripCharges:
    """Itemized roundtrip friction, gross/net P&L, and breakeven return metrics."""
    buy_turnover: float
    sell_turnover: float
    total_brokerage: float
    total_stt: float
    total_exchange_txn: float
    total_sebi_fee: float
    total_stamp_duty: float
    total_gst: float
    total_dp_charges: float
    total_friction: float
    gross_pnl: float
    net_pnl: float
    net_return_pct: float
    fee_drag_pct: float
    breakeven_sell_turnover: float
    breakeven_upside_pct: float


def get_active_profile() -> str:
    """Returns the currently active broker profile from environment or defaults."""
    env_profile = os.environ.get("MIL_BROKER_PROFILE", "").strip().lower()
    if env_profile in (PROFILE_ZERO, PROFILE_STANDARD):
        return env_profile
    return DEFAULT_PROFILE


def calculate_brokerage(turnover: float, profile: Optional[str] = None) -> float:
    """
    Computes delivery brokerage for an order turnover based on profile.
    - Zero: ₹0.00.
    - Standard: min(20.0, max(5.0, 0.001 * turnover)) on nonzero orders.
    """
    prof = (profile or get_active_profile()).lower()
    if prof == PROFILE_ZERO or turnover <= 0.0:
        return 0.0
    return round(min(20.0, max(5.0, 0.001 * turnover)), 2)


def calculate_order_charges(
    side: str,
    turnover: float,
    isin: Optional[str] = None,
    profile: Optional[str] = None,
    dp_override: Optional[float] = None
) -> OrderCharges:
    """
    Computes exact Indian statutory taxes and broker charges for a single BUY or SELL order.

    STT & Stamp Duty are rounded to the nearest rupee per exchange settlement conventions.
    GST strictly applies to (brokerage + exchange_txn + sebi_fee).
    DP charge applies strictly on SELL delivery legs (₹23.60).
    """
    s = side.upper().strip()
    if s not in ("BUY", "SELL"):
        raise ValueError(f"Invalid order side: {side}. Must be 'BUY' or 'SELL'.")

    v = max(0.0, float(turnover))
    if v == 0.0:
        return OrderCharges(
            side=s, turnover=0.0, brokerage=0.0, stt=0.0, exchange_txn=0.0,
            sebi_fee=0.0, stamp_duty=0.0, gst=0.0, dp_charge=0.0,
            total_charges=0.0, net_cash_flow=0.0
        )

    # 1. Brokerage
    brokerage = calculate_brokerage(v, profile)

    # 2. STT: 0.1% on buy and sell, rounded to nearest rupee
    stt = float(round(STT_RATE * v))

    # 3. NSE Exchange Turnover: 0.0030699%
    exchange_txn = round(NSE_TXN_RATE * v, 2)

    # 4. SEBI Turnover Fee: 0.0001% (₹10 / crore)
    sebi_fee = round(SEBI_RATE * v, 2)

    # 5. Stamp Duty: 0.015% on BUY only, rounded to nearest rupee
    stamp_duty = float(round(STAMP_DUTY_BUY_RATE * v)) if s == "BUY" else 0.0

    # 6. GST: 18% strictly on (Brokerage + Exchange Txn + SEBI Fee)
    taxable_services = brokerage + exchange_txn + sebi_fee
    gst = round(GST_RATE * taxable_services, 2)

    # 7. DP Charge: ₹23.60 on SELL only (unless overridden)
    if s == "SELL":
        dp_charge = ANGEL_ONE_DP_CHARGE if dp_override is None else max(0.0, float(dp_override))
    else:
        dp_charge = 0.0

    # 8. Total charges and net cash impact
    total_charges = round(brokerage + stt + exchange_txn + sebi_fee + stamp_duty + gst + dp_charge, 2)
    net_cash_flow = round(-(v + total_charges) if s == "BUY" else +(v - total_charges), 2)

    return OrderCharges(
        side=s,
        turnover=round(v, 2),
        brokerage=brokerage,
        stt=stt,
        exchange_txn=exchange_txn,
        sebi_fee=sebi_fee,
        stamp_duty=stamp_duty,
        gst=gst,
        dp_charge=dp_charge,
        total_charges=total_charges,
        net_cash_flow=net_cash_flow
    )


def calculate_roundtrip_friction(
    buy_turnover: float,
    sell_turnover: float,
    isin: Optional[str] = None,
    profile: Optional[str] = None,
    dp_override: Optional[float] = None
) -> RoundtripCharges:
    """
    Computes exact total roundtrip friction and net P&L across a completed BUY + SELL cycle.
    """
    buy_chg = calculate_order_charges("BUY", buy_turnover, isin=isin, profile=profile)
    sell_chg = calculate_order_charges("SELL", sell_turnover, isin=isin, profile=profile, dp_override=dp_override)

    total_brokerage = round(buy_chg.brokerage + sell_chg.brokerage, 2)
    total_stt = round(buy_chg.stt + sell_chg.stt, 2)
    total_exchange_txn = round(buy_chg.exchange_txn + sell_chg.exchange_txn, 2)
    total_sebi_fee = round(buy_chg.sebi_fee + sell_chg.sebi_fee, 2)
    total_stamp_duty = round(buy_chg.stamp_duty + sell_chg.stamp_duty, 2)
    total_gst = round(buy_chg.gst + sell_chg.gst, 2)
    total_dp_charges = round(sell_chg.dp_charge, 2)

    total_friction = round(
        total_brokerage + total_stt + total_exchange_txn + total_sebi_fee +
        total_stamp_duty + total_gst + total_dp_charges, 2
    )

    gross_pnl = round(sell_turnover - buy_turnover, 2)
    net_pnl = round(gross_pnl - total_friction, 2)
    net_return_pct = round((net_pnl / buy_turnover * 100.0), 2) if buy_turnover > 0 else 0.0
    fee_drag_pct = round((total_friction / buy_turnover * 100.0), 2) if buy_turnover > 0 else 0.0

    # Iterative breakeven solver (exact sell turnover where net_pnl == 0.0)
    be_sell = buy_turnover + total_friction
    for _ in range(5):
        trial_sell_chg = calculate_order_charges("SELL", be_sell, isin=isin, profile=profile, dp_override=dp_override)
        needed_friction = round(buy_chg.total_charges + trial_sell_chg.total_charges, 2)
        diff = (buy_turnover + needed_friction) - be_sell
        be_sell += diff
        if abs(diff) < 0.01:
            break
    be_sell = round(be_sell, 2)
    be_upside_pct = round(((be_sell - buy_turnover) / buy_turnover * 100.0), 2) if buy_turnover > 0 else 0.0

    return RoundtripCharges(
        buy_turnover=round(buy_turnover, 2),
        sell_turnover=round(sell_turnover, 2),
        total_brokerage=total_brokerage,
        total_stt=total_stt,
        total_exchange_txn=total_exchange_txn,
        total_sebi_fee=total_sebi_fee,
        total_stamp_duty=total_stamp_duty,
        total_gst=total_gst,
        total_dp_charges=total_dp_charges,
        total_friction=total_friction,
        gross_pnl=gross_pnl,
        net_pnl=net_pnl,
        net_return_pct=net_return_pct,
        fee_drag_pct=fee_drag_pct,
        breakeven_sell_turnover=be_sell,
        breakeven_upside_pct=be_upside_pct
    )


def minimum_breakeven_pct(invested_amount: float, profile: Optional[str] = None) -> float:
    """
    Computes the minimum gross percentage move required to achieve 0.0 net P&L after ₹23.60 DP & all taxes.
    Crucial for retail position sizing (e.g. ₹2,000 ticket requires ~1.7% gross gain just to break even).
    """
    if invested_amount <= 0.0:
        return 0.0
    rt = calculate_roundtrip_friction(invested_amount, invested_amount, profile=profile)
    return rt.breakeven_upside_pct
