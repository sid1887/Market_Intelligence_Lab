import math
import datetime
from typing import List, Dict, Any, Optional, Tuple

def parse_iso_date(d_str: str) -> datetime.date:
    return datetime.datetime.strptime(d_str, "%Y-%m-%d").date()

def calculate_returns_and_volatility(
    records: List[Dict[str, Any]],
    corporate_actions: Optional[List[Dict[str, Any]]] = None,
    pre_ex_start_price: Optional[float] = None,
    pre_ex_start_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    Computes rigorous deterministic return and risk metrics for a chronologically sorted OHLCV series.
    Enforces strict corporate action eligibility rules:
    - An investor purchasing at the closing price of Date[0] is ONLY eligible for dividends with ex_date > Date[0].
    - Price drops on ex-dates are explicitly decomposed into theoretical ex-dividend drops vs residual market moves.
    - Calendar-time CAGR and Trading-day annualisation are strictly distinguished and computed separately.
    """
    if not records or len(records) < 2:
        return {
            "error": "Insufficient records (minimum 2 required)",
            "total_records": len(records) if records else 0
        }

    prices = [float(r["close"]) for r in records]
    dates = [r["trading_date"] for r in records]
    n = len(prices)

    # 1. Daily Simple and Log Returns (Price-Only)
    simple_returns: List[float] = []
    log_returns: List[float] = []
    for i in range(1, n):
        p_prev = prices[i - 1]
        p_curr = prices[i]
        r_simple = (p_curr - p_prev) / p_prev
        r_log = math.log(p_curr / p_prev) if p_prev > 0 and p_curr > 0 else 0.0
        simple_returns.append(r_simple)
        log_returns.append(r_log)

    p_start = prices[0]
    p_end = prices[-1]
    start_date_str = dates[0]
    end_date_str = dates[-1]

    # 2. Price-Only Total Return
    unadjusted_price_return = (p_end - p_start) / p_start

    # 3. Calendar-Time CAGR vs Trading-Day Annualisation
    start_dt = parse_iso_date(start_date_str)
    end_dt = parse_iso_date(end_date_str)
    calendar_days = (end_dt - start_dt).days

    if calendar_days > 0 and p_start > 0:
        calendar_cagr = ((p_end / p_start) ** (365.25 / calendar_days)) - 1.0
    else:
        calendar_cagr = 0.0

    if (n - 1) > 0 and p_start > 0:
        trading_day_annualized = ((p_end / p_start) ** (252.0 / (n - 1))) - 1.0
    else:
        trading_day_annualized = 0.0

    # 4. Price-Only Volatility Calculations
    if len(simple_returns) > 1:
        mean_ret = sum(simple_returns) / len(simple_returns)
        variance = sum((r - mean_ret) ** 2 for r in simple_returns) / (len(simple_returns) - 1)
        daily_volatility = math.sqrt(variance)
        annualized_price_volatility = daily_volatility * math.sqrt(252.0)
    else:
        daily_volatility = 0.0
        annualized_price_volatility = 0.0

    # 5. Corporate Action Eligibility & Decomposition
    # Strict eligibility rule:
    # An investor purchasing at start_date close is only entitled to dividends with ex_date > start_date.
    eligible_cash_dividends = 0.0
    all_cash_dividends_in_window = 0.0
    ca_analysis: List[Dict[str, Any]] = []

    if corporate_actions:
        import re
        for ca in corporate_actions:
            ex_d = ca.get("ex_date", "")
            action_type = ca.get("action_type", "").upper()
            purpose = ca.get("purpose", "")
            adj_factor = float(ca.get("adjustment_factor", 1.0))

            div_amount = 0.0
            if "DIVIDEND" in action_type or "DIVIDEND" in purpose.upper():
                match = re.search(r"Rs\.?\s*(\d+(?:\.\d+)?)", purpose, re.IGNORECASE)
                if match:
                    div_amount = float(match.group(1))

            # Track window presence vs holding-period eligibility
            in_window = (start_date_str <= ex_d <= end_date_str)
            is_eligible = (ex_d > start_date_str and ex_d <= end_date_str)

            if in_window:
                all_cash_dividends_in_window += div_amount
            if is_eligible:
                eligible_cash_dividends += div_amount

            # Analyze price reaction around ex-date
            decomp = None
            if ex_d in dates:
                idx = dates.index(ex_d)
                if idx > 0:
                    p_prev_day = prices[idx - 1]
                    p_ex_day = prices[idx]
                    nominal_drop = p_ex_day - p_prev_day
                    nominal_drop_pct = nominal_drop / p_prev_day

                    # Decompose: expected dividend drop vs residual market move
                    expected_div_drop = -div_amount
                    theo_price = p_prev_day - div_amount
                    residual_move = p_ex_day - theo_price
                    residual_pct = residual_move / p_prev_day

                    decomp = {
                        "prev_close": p_prev_day,
                        "ex_close": p_ex_day,
                        "nominal_change": nominal_drop,
                        "nominal_change_pct": nominal_drop_pct,
                        "expected_div_drop": expected_div_drop,
                        "residual_market_move": residual_move,
                        "residual_market_move_pct": residual_pct
                    }

            if in_window:
                ca_analysis.append({
                    "ex_date": ex_d,
                    "action_type": action_type,
                    "purpose": purpose,
                    "dividend_amount": div_amount,
                    "adjustment_factor": adj_factor,
                    "eligible_for_start_close_investor": is_eligible,
                    "price_decomposition": decomp
                })

    # 6. Scenario A: Holding from Start Date Close (Eligible Dividends Only)
    # Formula: (P_end + D_eligible - P_start) / P_start
    cash_inclusive_return_eligible = (
        (p_end + eligible_cash_dividends - p_start) / p_start
        if p_start > 0 else unadjusted_price_return
    )
    dividend_yield_contribution_eligible = (
        (eligible_cash_dividends / p_start) if p_start > 0 else 0.0
    )

    # 7. Scenario B: Pre-Ex Comparison (e.g. cum-dividend purchase prior to first ex-date)
    pre_ex_scenario = None
    if pre_ex_start_price and pre_ex_start_price > 0:
        pre_start_d = pre_ex_start_date or "pre-ex"
        p_pre = pre_ex_start_price
        # All dividends in the full window apply
        pre_unadj = (p_end - p_pre) / p_pre
        pre_adj = (p_end + all_cash_dividends_in_window - p_pre) / p_pre
        pre_div_contrib = all_cash_dividends_in_window / p_pre
        pre_ex_scenario = {
            "pre_ex_start_date": pre_start_d,
            "pre_ex_start_price": p_pre,
            "terminal_price": p_end,
            "all_cash_dividends": all_cash_dividends_in_window,
            "unadjusted_return": pre_unadj,
            "cash_inclusive_return": pre_adj,
            "dividend_contribution": pre_div_contrib,
            "assumptions": "Investor purchased on or before cum-dividend close; received all dividends in window; no reinvestment."
        }

    return {
        "start_date": start_date_str,
        "end_date": end_date_str,
        "calendar_days": calendar_days,
        "trading_days": n,
        "first_close": p_start,
        "last_close": p_end,
        "unadjusted_price_return": unadjusted_price_return,
        "calendar_cagr": calendar_cagr,
        "trading_day_annualized": trading_day_annualized,
        "daily_volatility": daily_volatility,
        "price_only_annualized_volatility": annualized_price_volatility,
        # Scenario A (Strict post-ex holding period)
        "eligible_cash_dividends": eligible_cash_dividends,
        "cash_inclusive_return_eligible": cash_inclusive_return_eligible,
        "dividend_yield_contribution_eligible": dividend_yield_contribution_eligible,
        # Corporate actions audit
        "total_cash_dividends_in_window": all_cash_dividends_in_window,
        "corporate_actions": ca_analysis,
        # Scenario B (Pre-ex cum-dividend comparison)
        "pre_ex_scenario": pre_ex_scenario
    }

def calculate_drawdowns(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes price-only peak-to-trough drawdown series and Maximum Drawdown (MDD).
    Explicitly labelled as price-only (not total-return drawdown).
    """
    if not records:
        return {"max_drawdown": 0.0, "drawdown_series": []}

    prices = [float(r["close"]) for r in records]
    dates = [r["trading_date"] for r in records]

    peak = prices[0]
    peak_date = dates[0]
    mdd = 0.0
    mdd_peak_date = dates[0]
    mdd_trough_date = dates[0]
    mdd_peak_price = prices[0]
    mdd_trough_price = prices[0]

    drawdowns: List[Dict[str, Any]] = []

    for d, p in zip(dates, prices):
        if p > peak:
            peak = p
            peak_date = d

        dd = (p - peak) / peak if peak > 0 else 0.0
        drawdowns.append({
            "date": d,
            "close": p,
            "peak": peak,
            "drawdown": dd
        })

        if dd < mdd:
            mdd = dd
            mdd_peak_date = peak_date
            mdd_trough_date = d
            mdd_peak_price = peak
            mdd_trough_price = p

    return {
        "price_only_max_drawdown": mdd,
        "mdd_percentage": mdd * 100.0,
        "peak_date": mdd_peak_date,
        "peak_close": mdd_peak_price,
        "trough_date": mdd_trough_date,
        "trough_close": mdd_trough_price,
        "current_drawdown": drawdowns[-1]["drawdown"] if drawdowns else 0.0,
        "drawdown_series": drawdowns
    }

def calculate_52_week_position(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {"error": "No records provided"}

    window = records[-252:] if len(records) >= 252 else records

    high_rec = max(window, key=lambda r: float(r["high"]))
    low_rec = min(window, key=lambda r: float(r["low"]))
    latest_rec = window[-1]

    h52 = float(high_rec["high"])
    l52 = float(low_rec["low"])
    current_close = float(latest_rec["close"])

    range_span = h52 - l52
    pct_position = ((current_close - l52) / range_span) * 100.0 if range_span > 0 else 50.0

    dist_from_high = ((current_close - h52) / h52) * 100.0 if h52 > 0 else 0.0
    dist_from_low = ((current_close - l52) / l52) * 100.0 if l52 > 0 else 0.0

    return {
        "as_of_date": latest_rec["trading_date"],
        "current_close": current_close,
        "52w_high": h52,
        "52w_high_date": high_rec["trading_date"],
        "52w_low": l52,
        "52w_low_date": low_rec["trading_date"],
        "position_in_range_pct": pct_position,
        "distance_from_high_pct": dist_from_high,
        "distance_from_low_pct": dist_from_low
    }

def calculate_liquidity_metrics(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not records:
        return {"adv": 0, "adt_crores": 0.0}

    volumes = [int(r["volume"]) for r in records if r.get("volume") is not None]
    adv = sum(volumes) / len(volumes) if volumes else 0

    turnovers = [float(r["turnover"]) for r in records if r.get("turnover") is not None]
    adt_cr = (sum(turnovers) / len(turnovers)) / 10000000.0 if turnovers else 0.0

    return {
        "average_daily_volume": adv,
        "average_daily_turnover_cr": adt_cr,
        "sample_size": len(volumes)
    }
