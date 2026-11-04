import math
from typing import List, Dict, Any, Optional, Tuple

class ReturnModeMismatchError(ValueError):
    """
    Raised when comparing stock returns and benchmark returns of mismatched economic modes.
    Mode 1 (Price Return) must compare split-adjusted stock price returns to Nifty 50 PRI.
    Mode 2 (Total Return) must compare dividend-reinvested stock total returns to Nifty 50 TRI.
    Cross-mode comparisons (e.g. Stock Price Return vs TRI, or Total Return vs PRI) are strictly prohibited.
    """
    pass

class BenchmarkMode:
    PRI = "PRI"  # Mode 1: Price Return Index
    TRI = "TRI"  # Mode 2: Total Return Index

def calculate_split_bonus_adjustment_factors(
    records: List[Dict[str, Any]],
    corporate_actions: Optional[List[Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Propagates cumulative share-count adjustments (stock splits and bonus issues)
    backward so historical prices reflect today's share base without artificial discontinuities.
    Formula: P_adj,t = P_t * product_{ex_date > t} (adjustment_factor)
    """
    if not records:
        return []

    # Sort records chronologically
    sorted_recs = sorted(records, key=lambda r: r["trading_date"])
    dates = [r["trading_date"] for r in sorted_recs]

    # Filter corporate actions to splits and bonuses
    split_bonus_events = []
    if corporate_actions:
        for ca in corporate_actions:
            atype = ca.get("action_type", "").upper()
            ex_d = ca.get("ex_date", "")
            factor = float(ca.get("adjustment_factor", 1.0))
            if any(term in atype for term in ["SPLIT", "BONUS", "CONSOLIDATION"]) and factor > 0:
                split_bonus_events.append((ex_d, factor))

    adjusted_records = []
    for r in sorted_recs:
        d = r["trading_date"]
        cum_factor = 1.0
        for ex_d, factor in split_bonus_events:
            if ex_d > d:
                cum_factor *= factor

        item = dict(r)
        orig_close = float(r["close"])
        item["split_bonus_cum_factor"] = cum_factor
        item["adjusted_close"] = orig_close * cum_factor
        if r.get("open") is not None:
            item["adjusted_open"] = float(r["open"]) * cum_factor
        if r.get("high") is not None:
            item["adjusted_high"] = float(r["high"]) * cum_factor
        if r.get("low") is not None:
            item["adjusted_low"] = float(r["low"]) * cum_factor
        adjusted_records.append(item)

    return adjusted_records

def validate_comparison_modes(stock_mode: str, benchmark_mode: str) -> None:
    """
    Enforces matching return modes between stock and benchmark.
    Raises ReturnModeMismatchError if modes do not match.
    """
    s_mode = stock_mode.upper().strip()
    b_mode = benchmark_mode.upper().strip()

    valid_modes = {BenchmarkMode.PRI, BenchmarkMode.TRI}
    if s_mode not in valid_modes:
        raise ValueError(f"Invalid stock return mode '{stock_mode}'. Must be PRI or TRI.")
    if b_mode not in valid_modes:
        raise ValueError(f"Invalid benchmark return mode '{benchmark_mode}'. Must be PRI or TRI.")

    if s_mode != b_mode:
        raise ReturnModeMismatchError(
            f"Economically invalid comparison: stock return mode '{s_mode}' cannot be compared "
            f"against benchmark return mode '{b_mode}'. "
            f"Mode 1 requires Stock PRI vs Benchmark PRI; Mode 2 requires Stock TRI vs Benchmark TRI."
        )

def calculate_excess_return(
    stock_return: float,
    stock_mode: str,
    benchmark_return: float,
    benchmark_mode: str
) -> Dict[str, Any]:
    """
    Computes excess return over benchmark after enforcing return-mode consistency.
    """
    validate_comparison_modes(stock_mode, benchmark_mode)
    excess = stock_return - benchmark_return
    return {
        "stock_return": stock_return,
        "benchmark_return": benchmark_return,
        "excess_return": excess,
        "mode": stock_mode.upper(),
        "is_outperforming": excess > 0
    }

def calculate_beta(
    stock_returns: List[float],
    benchmark_returns: List[float],
    stock_mode: str,
    benchmark_mode: str,
    min_observations: int = 10
) -> Optional[float]:
    """
    Computes sample beta (Cov(Rs, Rb) / Var(Rb)) while strictly enforcing return-mode consistency.
    Returns None if:
    - Benchmark variance is zero or negligible (<= 1e-12), as beta is mathematically undefined.
    - Fewer than min_observations aligned return pairs exist.
    """
    validate_comparison_modes(stock_mode, benchmark_mode)

    n = len(stock_returns)
    if n != len(benchmark_returns) or n < min_observations:
        return None

    mean_s = sum(stock_returns) / float(n)
    mean_b = sum(benchmark_returns) / float(n)

    cov = sum((s - mean_s) * (b - mean_b) for s, b in zip(stock_returns, benchmark_returns)) / float(n - 1)
    var_b = sum((b - mean_b) ** 2 for b in benchmark_returns) / float(n - 1)

    # Mathematically undefined if benchmark variance is zero
    if var_b <= 1e-12:
        return None

    return cov / var_b
