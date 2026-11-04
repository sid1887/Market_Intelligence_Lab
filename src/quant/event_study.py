import math
import datetime
from typing import List, Dict, Any, Optional, Tuple
from src.storage.database import DatabaseManager
from src.quant.alignment import AlignedSeries
from src.quant.benchmark import (
    calculate_split_bonus_adjustment_factors,
    validate_comparison_modes,
    BenchmarkMode
)

class InsufficientEstimationHistoryError(ValueError):
    """Raised when available history is insufficient to satisfy the full [-252, -21] estimation window."""
    pass

class EventStudyEngine:
    """
    Econometric Event Study Engine for analyzing market reaction to corporate disclosures.
    Implements:
    - Accurate IST timestamp alignment to trading sessions (market-hours vs post-market).
    - Market model OLS estimation strictly on [-252, -21] window (232 sessions).
    - Pre-event buffer [-20, -1] exclusion to prevent information leakage contamination.
    - Abnormal Return (AR) and Cumulative Abnormal Return (CAR) calculations with t-tests.
    - Strict non-causal hypothesis framing.
    """

    # Econometric estimation window parameters
    # The estimation window covers sessions t in [-252, -21] inclusive = 232 trading sessions.
    # To compute 232 daily returns (R_t = (P_t - P_{t-1})/P_{t-1}), we require 233 price sessions,
    # starting with base price session t = -253.
    ESTIMATION_WINDOW_RETURN_SESSIONS = 232
    ESTIMATION_WINDOW_PRICE_SESSIONS = 233
    BASE_PRICE_OFFSET = -253
    ESTIMATION_END_OFFSET = -21
    BUFFER_SESSIONS = 20  # Sessions [-20, -1] excluded from estimation to prevent leakage

    def __init__(self, db: DatabaseManager):
        self.db = db

    @staticmethod
    def align_disclosure_to_trading_session(
        broadcast_timestamp_ist: str,
        trading_calendar_dates: List[str]
    ) -> str:
        """
        Aligns a corporate announcement timestamp to its effective trading session t=0.
        Rule:
        - If released on a trading day at or before 15:30 IST: effective session t=0 is that trading day.
        - If released after 15:30 IST on a trading day (post-market) or on a non-trading day
          (weekend/exchange holiday): effective session t=0 is the next valid trading session.
        """
        ts_clean = broadcast_timestamp_ist.replace("Z", "+00:00")
        if "T" in ts_clean:
            dt_part, tm_part = ts_clean.split("T")
        else:
            dt_part, tm_part = ts_clean.split(" ")

        time_str = tm_part[:8]  # HH:MM:SS
        cal_sorted = sorted(trading_calendar_dates)

        is_trading_day = dt_part in cal_sorted
        is_market_hours = time_str <= "15:30:00"

        if is_trading_day and is_market_hours:
            return dt_part
        else:
            # Next available trading session strictly after dt_part
            subsequent = [d for d in cal_sorted if d > dt_part]
            if not subsequent:
                # Target session is beyond current calendar
                # Return projected date or indicate future trading day
                import datetime as dt_mod
                dt_obj = dt_mod.datetime.strptime(dt_part, "%Y-%m-%d").date()
                next_day = dt_obj + dt_mod.timedelta(days=1)
                while next_day.weekday() >= 5:  # skip weekend
                    next_day += dt_mod.timedelta(days=1)
                return next_day.strftime("%Y-%m-%d")
            return subsequent[0]

    def estimate_market_model(
        self,
        stock_returns: List[float],
        benchmark_returns: List[float]
    ) -> Tuple[float, float, float, float]:
        """
        Estimates market model R_i = alpha + beta * R_m + epsilon via OLS.
        Returns (alpha, beta, r_squared, residual_std_err).
        """
        n = len(stock_returns)
        if n != len(benchmark_returns) or n < 30:
            raise ValueError(f"Requires at least 30 observations for OLS estimation (got {n})")

        mean_s = sum(stock_returns) / float(n)
        mean_b = sum(benchmark_returns) / float(n)

        cov = sum((s - mean_s) * (b - mean_b) for s, b in zip(stock_returns, benchmark_returns))
        var_b = sum((b - mean_b) ** 2 for b in benchmark_returns)

        if var_b <= 1e-12:
            raise ValueError("Zero benchmark variance during estimation window")

        beta = cov / var_b
        alpha = mean_s - beta * mean_b

        # Residuals
        residuals = [s - (alpha + beta * b) for s, b in zip(stock_returns, benchmark_returns)]
        ssr = sum(e ** 2 for e in residuals)
        sst = sum((s - mean_s) ** 2 for s in stock_returns)

        r_squared = 1.0 - (ssr / sst) if sst > 0 else 0.0
        # Degrees of freedom: n - 2
        s_e = math.sqrt(ssr / float(n - 2)) if n > 2 else 0.0

        return alpha, beta, r_squared, s_e

    def run_event_study(
        self,
        symbol: str,
        effective_event_date: str,
        benchmark_name: str = "NIFTY 50",
        mode: str = BenchmarkMode.PRI,
        event_window_short: Tuple[int, int] = (-1, 1),
        event_window_drift: Tuple[int, int] = (0, 2),
        event_category: str = "OTHER",
        verification_status: str = "VERIFIED"
    ) -> Dict[str, Any]:
        """
        Executes an event study for a stock around effective_event_date (session t=0).
        Strictly enforces the [-252, -21] estimation window (232 return observations).
        """
        validate_comparison_modes(mode, mode)

        # 1. Fetch stock and benchmark history
        stock_raw = self.db.get_stock_history(symbol)
        cas = self.db.get_corporate_actions(symbol)
        stock_adj = calculate_split_bonus_adjustment_factors(stock_raw, cas)

        bench_raw = self.db.get_index_history(benchmark_name, mode)

        # 2. Align series on exact trading dates
        aligned = AlignedSeries.align_stock_and_benchmark(
            stock_records=stock_adj,
            benchmark_records=bench_raw,
            stock_price_key="adjusted_close",
            benchmark_value_key="close"
        )

        aligned_dates = [a["trading_date"] for a in aligned]

        # Check if effective_event_date is in the future relative to aligned database
        if not aligned_dates or effective_event_date > aligned_dates[-1]:
            latest_d = aligned_dates[-1] if aligned_dates else "None"
            return {
                "symbol": symbol,
                "event_date": effective_event_date,
                "status": "AWAITING_POST_EVENT_DATA",
                "reason": (
                    f"Effective event session t=0 ({effective_event_date}) has not yet traded in the database. "
                    f"Current settled market data ends on {latest_d}. "
                    "Study is awaiting post-event trading session settlement."
                )
            }

        if effective_event_date not in aligned_dates:
            return {
                "symbol": symbol,
                "event_date": effective_event_date,
                "status": "UNAVAILABLE",
                "reason": f"Effective event date {effective_event_date} not found in aligned market history."
            }

        t0_idx = aligned_dates.index(effective_event_date)

        # 3. Check Estimation Window Boundary
        # Need base price session at t0_idx + BASE_PRICE_OFFSET (t0 - 253 >= 0)
        est_price_start_idx = t0_idx + self.BASE_PRICE_OFFSET
        est_price_end_idx = t0_idx + self.ESTIMATION_END_OFFSET

        if est_price_start_idx < 0:
            available_history = t0_idx
            return {
                "symbol": symbol,
                "event_date": effective_event_date,
                "status": "INSUFFICIENT_ESTIMATION_HISTORY",
                "reason": (
                    f"Insufficient historical runway: requires 253 price sessions before event date "
                    f"(yielding 232 returns for estimation + 20 buffer sessions), "
                    f"but only {available_history} sessions available prior to {effective_event_date}."
                ),
                "required_sessions_before_event": 253,
                "available_sessions_before_event": available_history
            }

        # 4. Check Event Window Boundary (Must have all sessions in post-event window)
        max_event_offset = max(event_window_short[1], event_window_drift[1])
        if t0_idx + max_event_offset >= len(aligned):
            available_post_sessions = len(aligned) - 1 - t0_idx
            return {
                "symbol": symbol,
                "event_date": effective_event_date,
                "status": "AWAITING_POST_EVENT_DATA",
                "reason": (
                    f"Incomplete post-event history for event window [0, +{max_event_offset}]: "
                    f"only {available_post_sessions} sessions available after t=0. "
                    f"Current database ends on {aligned_dates[-1]}."
                )
            }

        # 5. Extract Estimation Window Aligned Pairs and Returns
        # est_aligned has 233 price points -> exactly 232 return pairs!
        est_aligned = aligned[est_price_start_idx : est_price_end_idx + 1]
        est_ret_dates, est_s_rets, est_b_rets = AlignedSeries.compute_aligned_returns(est_aligned, mode, mode)

        alpha, beta, r2, s_e = self.estimate_market_model(est_s_rets, est_b_rets)

        # 6. Extract Event Window Data & Compute Abnormal Returns
        min_offset = min(event_window_short[0], event_window_drift[0])
        event_slice = aligned[t0_idx + min_offset - 1 : t0_idx + max_event_offset + 1]
        event_dates, event_s_rets, event_b_rets = AlignedSeries.compute_aligned_returns(event_slice, mode, mode)

        ar_by_offset: Dict[int, float] = {}
        for idx_offset, (d, r_s, r_b) in enumerate(zip(event_dates, event_s_rets, event_b_rets)):
            offset = min_offset + idx_offset
            expected_ret = alpha + beta * r_b
            ar = r_s - expected_ret
            ar_by_offset[offset] = ar

        # Cumulative Abnormal Returns
        car_short = sum(ar_by_offset.get(k, 0.0) for k in range(event_window_short[0], event_window_short[1] + 1))
        len_short = event_window_short[1] - event_window_short[0] + 1
        var_car_short = len_short * (s_e ** 2)
        se_car_short = math.sqrt(var_car_short) if var_car_short > 0 else 1e-6
        t_stat_short = car_short / se_car_short

        car_drift = sum(ar_by_offset.get(k, 0.0) for k in range(event_window_drift[0], event_window_drift[1] + 1))
        len_drift = event_window_drift[1] - event_window_drift[0] + 1
        var_car_drift = len_drift * (s_e ** 2)
        se_car_drift = math.sqrt(var_car_drift) if var_car_drift > 0 else 1e-6
        t_stat_drift = car_drift / se_car_drift

        # Approximate two-tailed p-value from normal distribution
        def p_val_from_t(t_val):
            z = abs(t_val)
            t_k = 1.0 / (1.0 + 0.2316419 * z)
            poly = t_k * (0.319381530 + t_k * (-0.356563782 + t_k * (1.781477937 + t_k * (-1.821255978 + t_k * 1.330274429))))
            phi = 1.0 - (1.0 / math.sqrt(2.0 * math.pi)) * math.exp(-0.5 * z * z) * poly
            return round(2.0 * (1.0 - phi), 4)

        p_short = p_val_from_t(t_stat_short)
        p_drift = p_val_from_t(t_stat_drift)

        is_sig_short = p_short < 0.05
        is_sig_drift = p_drift < 0.05

        # 7. Non-Causal Epistemic Hypothesis Framing with Statistical Rigor
        ar_t0 = ar_by_offset.get(0, 0.0)
        direction = "positive" if ar_t0 > 0 else "negative"

        significance_note = (
            f"This abnormal movement is statistically significant at the 5% level (t={t_stat_short:.2f}, p={p_short})."
            if is_sig_short else
            f"This abnormal movement is NOT statistically significant at the conventional 5% level (t={t_stat_short:.2f}, p={p_short})."
        )

        unverified_prefix = ""
        if verification_status.upper() == "SOURCE_UNVERIFIED":
            unverified_prefix = (
                "[SOURCE_UNVERIFIED DISCLOSURE] WARNING: This event is based on an unverified filing record "
                "that has not been confirmed against official regulatory exchange filings. "
                "Co-occurring price movements must NOT be presented as a verified reaction to an official exchange disclosure. "
            )

        category_context = ""
        if "SCHEDULE" in event_category.upper() or "NOTICE" in event_category.upper():
            category_context = (
                " Note: This corporate filing represents an administrative notice of meeting schedule, "
                "not the publication of financial results. Co-occurring price movements cannot be interpreted "
                "as a market response to underlying financial performance."
            )

        hypothesis_text = (
            f"{unverified_prefix}On trading session t=0 ({effective_event_date}), {symbol} recorded an abnormal return of {ar_t0*100:+.2f}% "
            f"(CAR[-1, +1] = {car_short*100:+.2f}%, t-stat = {t_stat_short:.2f}, p = {p_short}). {significance_note}"
            f"{category_context} While temporal proximity presents an explanatory hypothesis, broader market movements, "
            f"sectoral rotation, and unobservable order flows remain co-occurring factors."
        )

        return {
            "symbol": symbol,
            "event_date": effective_event_date,
            "status": "SUCCESS",
            "verification_status": verification_status,
            "estimation_window": {
                "start_date": est_ret_dates[0],
                "end_date": est_ret_dates[-1],
                "price_sessions_count": len(est_aligned),
                "return_observations_count": len(est_s_rets),
                "model_alpha": round(alpha, 6),
                "model_beta": round(beta, 4),
                "model_r2": round(r2, 4),
                "residual_std_error": round(s_e, 5)
            },
            "event_window": {
                "ar_t0": round(ar_t0, 5),
                "ar_t0_pct": round(ar_t0 * 100.0, 2),
                "car_short": {
                    "window": list(event_window_short),
                    "car_value": round(car_short, 5),
                    "car_pct": round(car_short * 100.0, 2),
                    "t_statistic": round(t_stat_short, 2),
                    "p_value": p_short,
                    "is_statistically_significant": is_sig_short
                },
                "car_drift": {
                    "window": list(event_window_drift),
                    "car_value": round(car_drift, 5),
                    "car_pct": round(car_drift * 100.0, 2),
                    "t_statistic": round(t_stat_drift, 2),
                    "p_value": p_drift,
                    "is_statistically_significant": is_sig_drift
                }
            },
            "explanatory_hypothesis": hypothesis_text
        }
