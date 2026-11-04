"""
Market Intelligence Lab: Deterministic Market-Movement Analyzer.
Provides mathematically rigorous decomposition of daily stock price action:
- Multi-horizon returns (1d raw/adj/total, 5d, 20d), overnight gap, intraday drift, and range.
- Benchmark (NIFTY 50 PRI) and sector benchmark alignment (Official PRI vs. Synthetic Peer Basket).
- OLS Market Model estimation over [-252, -21] with [-20, -1] buffer exclusion.
- Statistical safeguards: minimum 126 sessions required; zero data leakage.
- Corporate action volume adjustment and rolling volume anomalies (VR, Z-score).
- Deterministic movement classification taxonomy.
"""

import math
import datetime
from typing import Dict, Any, List, Optional, Tuple, Set

from src.storage.database import DatabaseManager
from src.evidence.models import (
    MovementClassification,
    SectorBenchmarkType,
    MovementAnalysisResult
)
from src.evidence.constants import (
    MINIMUM_SYNTHETIC_PEERS,
    resolve_sector_benchmark
)
from src.quant.benchmark import calculate_split_bonus_adjustment_factors
from src.quant.volume import adjust_volume_for_corporate_actions
from src.quant.calendar import (
    get_intermediate_trading_sessions,
    count_trading_sessions_between
)


class MarketMovementAnalyzer:
    """
    Deterministic Quantitative Market-Movement Analyzer.
    Investigates price action for a stock on any trading session T,
    producing auditable, reproducible mathematical decompositions.
    """

    # Econometric estimation window parameters
    ESTIMATION_WINDOW_RETURN_SESSIONS = 232  # Ideal [-252, -21] return sessions
    MINIMUM_ESTIMATION_SESSIONS = 126        # Strict minimum required (6 months)
    BUFFER_SESSIONS = 20                     # [-20, -1] sessions strictly excluded from OLS
    MINIMUM_SYNTHETIC_PEERS = MINIMUM_SYNTHETIC_PEERS

    # Configurable movement classification thresholds
    IDIOSYNCRATIC_AR_THRESHOLD = 0.02        # |AR| >= 2.0%
    IDIOSYNCRATIC_SAR_THRESHOLD = 0.015      # |SAR| >= 1.5%
    SECTOR_MOMENTUM_THRESHOLD = 0.015        # |R_sec| >= 1.5%
    SECTOR_ALIGNED_TOLERANCE = 0.01          # |SAR| <= 1.0% (co-moving with sector)
    VOLUME_SPIKE_VR_THRESHOLD = 2.5          # Volume Ratio >= 2.5x
    VOLUME_SPIKE_Z_THRESHOLD = 2.5           # Volume Log Z-Score >= 2.5
    MUTED_RETURN_THRESHOLD = 0.005           # |R_1d| < 0.5%

    def __init__(self, db: DatabaseManager):
        self.db = db

    def analyze_session_movement(
        self,
        symbol: str,
        target_date: str
    ) -> MovementAnalysisResult:
        """
        Performs exhaustive mathematical decomposition of symbol's price action on target_date.
        """
        # 1. Fetch full stock history & corporate actions
        stock_raw = self.db.get_stock_history(symbol)
        if not stock_raw:
            raise ValueError(f"Symbol '{symbol}' not found in database or has no historical OHLCV data.")

        # Sort chronologically
        stock_raw_sorted = sorted(stock_raw, key=lambda x: x["trading_date"])
        dates = [r["trading_date"] for r in stock_raw_sorted]

        if target_date not in dates:
            raise ValueError(f"Symbol '{symbol}' has no trading observation on date '{target_date}'.")

        target_idx = dates.index(target_date)
        target_row = stock_raw_sorted[target_idx]

        open_p = float(target_row["open"])
        high_p = float(target_row["high"])
        low_p = float(target_row["low"])
        close_p = float(target_row["close"])
        vol_t = int(target_row.get("volume", 0))

        # Check for previous session
        if target_idx == 0:
            # Opening session in database; cannot compute 1d returns
            return MovementAnalysisResult(
                symbol=symbol,
                trading_date=target_date,
                open=open_p, high=high_p, low=low_p, close=close_p, prev_close=open_p,
                volume=vol_t,
                ret_1d_raw=0.0, ret_1d_adj=0.0, ret_1d_total=0.0,
                gap_open=0.0, intraday_drift=0.0, intraday_range=0.0,
                ret_5d=None, ret_20d=None,
                benchmark_return=None,
                sector_benchmark_type=SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI,
                sector_benchmark_name="NIFTY 50",
                sector_return=None,
                model_status="INSUFFICIENT_HISTORY",
                primary_classification=MovementClassification.INSUFFICIENT_DATA,
                classifications=[MovementClassification.INSUFFICIENT_DATA],
                details={"reason": "First session in database; no previous close available."}
            )

        prev_row = stock_raw_sorted[target_idx - 1]
        prev_stored_date = prev_row["trading_date"]
        prev_stored_close = float(prev_row["close"])

        # Check for calendar gap (missing intermediate exchange trading sessions)
        missing_intermediate = get_intermediate_trading_sessions(prev_stored_date, target_date)
        has_calendar_gap = len(missing_intermediate) > 0

        # Extract exchange-reported previous close if available in target row
        raw_source_prev_close = target_row.get("prev_close")
        if raw_source_prev_close is not None and float(raw_source_prev_close) > 0:
            source_prev_close = float(raw_source_prev_close)
            source_prev_close_provenance = "exchange_udiff_prvsclsgpric" if has_calendar_gap else "database_consecutive_session"
        else:
            source_prev_close = None
            source_prev_close_provenance = None

        # Multi-session returns
        ret_5d = None
        if target_idx >= 5:
            p_5d = float(stock_raw_sorted[target_idx - 5]["close"])
            ret_5d = (close_p - p_5d) / p_5d if p_5d > 0 else 0.0

        ret_20d = None
        if target_idx >= 20:
            p_20d = float(stock_raw_sorted[target_idx - 20]["close"])
            ret_20d = (close_p - p_20d) / p_20d if p_20d > 0 else 0.0

        # Corporate actions adjustment on target_date (Point-in-Time filter: ex_date <= target_date)
        cas_all = self.db.get_corporate_actions(symbol=symbol)
        cas = [c for c in cas_all if c["ex_date"] <= target_date]
        ca_on_date = [c for c in cas if c["ex_date"] == target_date]

        cum_ca_factor = 1.0
        dividend_amount = 0.0
        for ca in ca_on_date:
            atype = ca["action_type"].upper()
            factor = float(ca.get("adjustment_factor", 1.0))
            if any(term in atype for term in ["SPLIT", "BONUS"]) and factor > 0:
                cum_ca_factor *= factor
            if "DIVIDEND" in atype:
                # Attempt to extract cash dividend amount per share from purpose
                purp = ca.get("purpose", "")
                import re
                m = re.search(r"(?:Rs\.?|INR)\s*(\d+(?:\.\d+)?)", purp, re.IGNORECASE)
                if m:
                    try:
                        dividend_amount += float(m.group(1))
                    except ValueError:
                        pass

        intraday_drift = (close_p - open_p) / open_p if open_p > 0 else 0.0

        if has_calendar_gap:
            missing_intermediate_sessions = missing_intermediate
            interval_sessions_count = count_trading_sessions_between(prev_stored_date, target_date)
            interval_start_date = prev_stored_date
            prev_stored_adj = prev_stored_close * cum_ca_factor
            interval_return_raw = (close_p - prev_stored_close) / prev_stored_close if prev_stored_close > 0 else 0.0
            interval_return_adj = (close_p - prev_stored_adj) / prev_stored_adj if prev_stored_adj > 0 else interval_return_raw

            if source_prev_close is not None:
                source_prev_adj = source_prev_close * cum_ca_factor
                ret_1d_raw = (close_p - source_prev_close) / source_prev_close if source_prev_close > 0 else 0.0
                ret_1d_adj = (close_p - source_prev_adj) / source_prev_adj if source_prev_adj > 0 else ret_1d_raw
                ret_1d_total = ((close_p + dividend_amount - source_prev_adj) / source_prev_adj) if source_prev_adj > 0 else ret_1d_adj
                gap_open = (open_p - source_prev_close) / source_prev_close if source_prev_close > 0 else 0.0
                intraday_range = (high_p - low_p) / source_prev_close if source_prev_close > 0 else 0.0
                effective_prev_close = source_prev_close
            else:
                ret_1d_raw = None
                ret_1d_adj = None
                ret_1d_total = None
                gap_open = None
                intraday_range = (high_p - low_p) / prev_stored_close if prev_stored_close > 0 else 0.0
                effective_prev_close = prev_stored_close
        else:
            missing_intermediate_sessions = []
            interval_sessions_count = 1
            interval_start_date = None
            interval_return_raw = None
            interval_return_adj = None
            effective_prev_close = prev_stored_close
            prev_close_adj = prev_stored_close * cum_ca_factor
            ret_1d_raw = (close_p - prev_stored_close) / prev_stored_close if prev_stored_close > 0 else 0.0
            ret_1d_adj = (close_p - prev_close_adj) / prev_close_adj if prev_close_adj > 0 else ret_1d_raw
            ret_1d_total = ((close_p + dividend_amount - prev_close_adj) / prev_close_adj) if prev_close_adj > 0 else ret_1d_adj
            gap_open = (open_p - prev_stored_close) / prev_stored_close if prev_stored_close > 0 else 0.0
            intraday_range = (high_p - low_p) / prev_stored_close if prev_stored_close > 0 else 0.0

        # 3. Benchmark (NIFTY 50 PRI) Return
        nifty_records = self.db.get_index_history("NIFTY 50", "PRI")
        nifty_sorted = sorted(nifty_records, key=lambda x: x["trading_date"])
        nifty_dates = [r["trading_date"] for r in nifty_sorted]

        benchmark_return: Optional[float] = None
        if target_date not in nifty_dates:
            benchmark_return = None
        else:
            n_idx = nifty_dates.index(target_date)
            if n_idx > 0:
                p_m_prev_date = nifty_sorted[n_idx - 1]["trading_date"]
                # Ensure strictly consecutive exchange trading sessions
                if get_intermediate_trading_sessions(p_m_prev_date, target_date):
                    benchmark_return = None
                else:
                    p_m_prev = float(nifty_sorted[n_idx - 1]["close"])
                    p_m_curr = float(nifty_sorted[n_idx]["close"])
                    benchmark_return = (p_m_curr - p_m_prev) / p_m_prev if p_m_prev > 0 else 0.0
            else:
                benchmark_return = None

        # 4. Sector Benchmark Resolution & Returns
        sec_info = self.db.get_securities_master(symbol=symbol)
        sector_name = sec_info[0]["sector"] if sec_info else "Unknown"
        industry_name = sec_info[0]["industry"] if sec_info else "Unknown"

        b_type, b_name, cand_peers, is_proxy, sec_notes = resolve_sector_benchmark(
            symbol=symbol,
            sector=sector_name,
            industry=industry_name
        )

        sector_return: Optional[float] = None
        eligible_peers: List[str] = []
        peer_returns: Dict[str, float] = {}

        if b_type == SectorBenchmarkType.OFFICIAL_SECTOR_PRI:
            # Query official sectoral PRI index
            sec_records = self.db.get_index_history(b_name, "PRI")
            sec_sorted = sorted(sec_records, key=lambda x: x["trading_date"])
            s_dates = [r["trading_date"] for r in sec_sorted]
            if target_date in s_dates:
                s_idx = s_dates.index(target_date)
                if s_idx > 0:
                    p_s_prev_date = sec_sorted[s_idx - 1]["trading_date"]
                    # Ensure strictly consecutive exchange trading sessions
                    if not get_intermediate_trading_sessions(p_s_prev_date, target_date):
                        p_s_prev = float(sec_sorted[s_idx - 1]["close"])
                        p_s_curr = float(sec_sorted[s_idx]["close"])
                        sector_return = (p_s_curr - p_s_prev) / p_s_prev if p_s_prev > 0 else 0.0
                    else:
                        sector_return = None

        elif b_type == SectorBenchmarkType.SYNTHETIC_PEER_BASKET:
            # Compute equal-weighted return of eligible peers on target_date
            for p in cand_peers:
                p_hist = self.db.get_stock_history(p)
                p_sorted = sorted(p_hist, key=lambda x: x["trading_date"])
                p_dates = [r["trading_date"] for r in p_sorted]
                if target_date in p_dates:
                    p_idx = p_dates.index(target_date)
                    if p_idx > 0:
                        p_prev_date = p_sorted[p_idx - 1]["trading_date"]
                        # Ensure strictly consecutive exchange trading sessions for peer
                        if get_intermediate_trading_sessions(p_prev_date, target_date):
                            continue
                        p_prev = float(p_sorted[p_idx - 1]["close"])
                        p_curr = float(p_sorted[p_idx]["close"])
                        if p_prev > 0:
                            peer_returns[p] = (p_curr - p_prev) / p_prev

            if len(peer_returns) >= self.MINIMUM_SYNTHETIC_PEERS:
                eligible_peers = list(peer_returns.keys())
                sector_return = sum(peer_returns.values()) / float(len(peer_returns))
            else:
                # Fails minimum peers threshold on this specific session
                b_type = SectorBenchmarkType.BROAD_MARKET_NIFTY50_PRI
                b_name = "NIFTY 50"
                sector_return = benchmark_return
                sec_notes = (
                    f"Synthetic basket had only {len(peer_returns)} active peers on {target_date} "
                    f"(minimum {self.MINIMUM_SYNTHETIC_PEERS} required). Falling back to broad-market NIFTY 50 PRI."
                )

        else:
            # BROAD_MARKET_NIFTY50_PRI fallback
            sector_return = benchmark_return

        # 5. Econometric Market Model OLS Estimation
        # Estimation window covers sessions [-252, -21] relative to target_idx
        # Buffer window [-20, -1] is strictly excluded
        model_status = "ESTIMATED"
        alpha: Optional[float] = None
        beta: Optional[float] = None
        r_squared: Optional[float] = None
        residual_std_err: Optional[float] = None
        expected_return: Optional[float] = None
        abnormal_return: Optional[float] = None
        t_statistic: Optional[float] = None
        estimation_count = 0

        # We need historical sessions strictly preceding target_idx - 20
        est_end_idx = target_idx - self.BUFFER_SESSIONS - 1
        est_start_idx = max(0, target_idx - self.BUFFER_SESSIONS - self.ESTIMATION_WINDOW_RETURN_SESSIONS)

        # Check if we have sufficient observations
        available_est_sessions = est_end_idx - est_start_idx + 1

        if available_est_sessions < self.MINIMUM_ESTIMATION_SESSIONS or est_end_idx < 1:
            model_status = "INSUFFICIENT_HISTORY"
        else:
            # Extract historical returns aligned with NIFTY 50 PRI
            stock_adj_full = calculate_split_bonus_adjustment_factors(stock_raw_sorted, cas)
            stock_price_map = {r["trading_date"]: float(r["adjusted_close"]) for r in stock_adj_full}
            nifty_price_map = {r["trading_date"]: float(r["close"]) for r in nifty_sorted}

            # Build aligned daily returns for estimation window
            aligned_s_ret = []
            aligned_m_ret = []

            for i in range(est_start_idx + 1, est_end_idx + 1):
                d_curr = dates[i]
                d_prev = dates[i - 1]

                # Ensure strictly consecutive sessions (no missing intermediate trading sessions)
                if get_intermediate_trading_sessions(d_prev, d_curr):
                    continue

                if d_curr in nifty_price_map and d_prev in nifty_price_map:
                    p_s_curr = stock_price_map.get(d_curr)
                    p_s_prev = stock_price_map.get(d_prev)
                    p_m_curr = nifty_price_map.get(d_curr)
                    p_m_prev = nifty_price_map.get(d_prev)

                    if p_s_curr and p_s_prev and p_m_curr and p_m_prev and p_s_prev > 0 and p_m_prev > 0:
                        aligned_s_ret.append((p_s_curr - p_s_prev) / p_s_prev)
                        aligned_m_ret.append((p_m_curr - p_m_prev) / p_m_prev)

            estimation_count = len(aligned_s_ret)

            if estimation_count < self.MINIMUM_ESTIMATION_SESSIONS:
                model_status = "INSUFFICIENT_HISTORY"
            else:
                # OLS Estimation
                mean_s = sum(aligned_s_ret) / float(estimation_count)
                mean_m = sum(aligned_m_ret) / float(estimation_count)

                cov_sm = sum((s - mean_s) * (m - mean_m) for s, m in zip(aligned_s_ret, aligned_m_ret))
                var_m = sum((m - mean_m) ** 2 for m in aligned_m_ret)

                if var_m <= 1e-12:
                    model_status = "ESTIMATION_FAILED"
                else:
                    beta_val = cov_sm / var_m
                    alpha_val = mean_s - beta_val * mean_m

                    residuals = [s - (alpha_val + beta_val * m) for s, m in zip(aligned_s_ret, aligned_m_ret)]
                    ssr = sum(e ** 2 for e in residuals)
                    sst = sum((s - mean_s) ** 2 for s in aligned_s_ret)

                    r2_val = 1.0 - (ssr / sst) if sst > 0 else 0.0
                    s_e = math.sqrt(ssr / float(estimation_count - 2)) if estimation_count > 2 else 0.0

                    alpha = alpha_val
                    beta = beta_val
                    r_squared = r2_val
                    residual_std_err = s_e

                    # On target_date: compute Expected Return and Abnormal Return
                    if benchmark_return is not None and ret_1d_adj is not None:
                        exp_ret = alpha_val + beta_val * benchmark_return
                        ab_ret = ret_1d_adj - exp_ret

                        # Prediction variance: s_e^2 * [1 + 1/N + (R_m - mean_m)^2 / var_m]
                        pred_var = (s_e ** 2) * (1.0 + (1.0 / float(estimation_count)) + ((benchmark_return - mean_m) ** 2) / var_m)
                        pred_se = math.sqrt(pred_var) if pred_var > 0 else 1e-6
                        t_stat = ab_ret / pred_se

                        expected_return = exp_ret
                        abnormal_return = ab_ret
                        t_statistic = t_stat
                    else:
                        model_status = "BENCHMARK_UNAVAILABLE" if benchmark_return is None else "RETURN_UNAVAILABLE"
                        expected_return = None
                        abnormal_return = None
                        t_statistic = None

        # Sector-adjusted abnormal return: SAR_t = R_stock - R_sector
        sector_adjusted_return = (ret_1d_adj - sector_return) if (ret_1d_adj is not None and sector_return is not None) else None

        # 6. Volume Anomaly & Liquidity Analysis
        # Use up to 50 previous sessions strictly < target_idx
        volume_ratio_20d: Optional[float] = None
        volume_log_zscore_50d: Optional[float] = None
        is_volume_spike = False
        is_zero_volume = (vol_t == 0)

        hist_records_for_vol = stock_raw_sorted[max(0, target_idx - 50):target_idx]
        adj_volumes = adjust_volume_for_corporate_actions(hist_records_for_vol, cas)

        if len(adj_volumes) >= 20:
            vol_20_slice = adj_volumes[-20:]
            sma_20_vol = sum(vol_20_slice) / 20.0
            if sma_20_vol > 0:
                volume_ratio_20d = float(vol_t) / sma_20_vol

        if len(adj_volumes) >= 50:
            log_vols = [math.log(v + 1.0) for v in adj_volumes]
            mean_log = sum(log_vols) / 50.0
            var_log = sum((lv - mean_log) ** 2 for lv in log_vols) / 49.0
            std_log = math.sqrt(var_log) if var_log > 0 else 0.0

            if std_log > 1e-6:
                curr_log_v = math.log(vol_t + 1.0)
                volume_log_zscore_50d = (curr_log_v - mean_log) / std_log

        if volume_ratio_20d is not None and volume_ratio_20d >= self.VOLUME_SPIKE_VR_THRESHOLD:
            is_volume_spike = True
        if volume_log_zscore_50d is not None and volume_log_zscore_50d >= self.VOLUME_SPIKE_Z_THRESHOLD:
            is_volume_spike = True

        # 7. Deterministic Movement Classification Taxonomy
        classifications: List[MovementClassification] = []

        if model_status in ("INSUFFICIENT_HISTORY", "BENCHMARK_UNAVAILABLE", "ESTIMATION_FAILED") or abnormal_return is None:
            classifications.append(MovementClassification.INSUFFICIENT_DATA)
            primary_classification = MovementClassification.INSUFFICIENT_DATA
        else:
            sar_val = sector_adjusted_return  # Strictly None if sector benchmark is unavailable; never fall back to abnormal_return
            sec_ret_val = sector_return

            # Check Idiosyncratic moves: Requires BOTH AR and SAR confirmation
            if sar_val is not None:
                if abnormal_return >= self.IDIOSYNCRATIC_AR_THRESHOLD and sar_val >= self.IDIOSYNCRATIC_SAR_THRESHOLD:
                    classifications.append(MovementClassification.IDIOSYNCRATIC_OUTPERFORMANCE)
                elif abnormal_return <= -self.IDIOSYNCRATIC_AR_THRESHOLD and sar_val <= -self.IDIOSYNCRATIC_SAR_THRESHOLD:
                    classifications.append(MovementClassification.IDIOSYNCRATIC_UNDERPERFORMANCE)

            # Check Sector Systematic moves
            if sec_ret_val is not None and sar_val is not None:
                if sec_ret_val >= self.SECTOR_MOMENTUM_THRESHOLD and abs(sar_val) <= self.SECTOR_ALIGNED_TOLERANCE:
                    classifications.append(MovementClassification.SECTOR_SYSTEMATIC_SURGE)
                elif sec_ret_val <= -self.SECTOR_MOMENTUM_THRESHOLD and abs(sar_val) <= self.SECTOR_ALIGNED_TOLERANCE:
                    classifications.append(MovementClassification.SECTOR_SYSTEMATIC_DRAG)

            # Check Market Beta Driven moves
            if (sar_val is not None and abs(sar_val) <= self.SECTOR_ALIGNED_TOLERANCE and
                abs(abnormal_return) <= self.SECTOR_ALIGNED_TOLERANCE and
                benchmark_return is not None and abs(benchmark_return) >= 0.005):
                classifications.append(MovementClassification.MARKET_BETA_DRIVEN)

            # Check Muted Consolidation
            if ret_1d_raw is not None and abs(ret_1d_raw) < self.MUTED_RETURN_THRESHOLD and not is_volume_spike:
                classifications.append(MovementClassification.MUTED_CONSOLIDATION)

            # Check Anomalous Volume independently
            if is_volume_spike:
                classifications.append(MovementClassification.ANOMALOUS_VOLUME)

            # Determine Primary Price-Movement Classification
            # Requirement 4: ANOMALOUS_VOLUME remains an independent secondary tag and never overwrites price classification
            if MovementClassification.IDIOSYNCRATIC_OUTPERFORMANCE in classifications:
                primary_classification = MovementClassification.IDIOSYNCRATIC_OUTPERFORMANCE
            elif MovementClassification.IDIOSYNCRATIC_UNDERPERFORMANCE in classifications:
                primary_classification = MovementClassification.IDIOSYNCRATIC_UNDERPERFORMANCE
            elif MovementClassification.SECTOR_SYSTEMATIC_SURGE in classifications:
                primary_classification = MovementClassification.SECTOR_SYSTEMATIC_SURGE
            elif MovementClassification.SECTOR_SYSTEMATIC_DRAG in classifications:
                primary_classification = MovementClassification.SECTOR_SYSTEMATIC_DRAG
            elif MovementClassification.MARKET_BETA_DRIVEN in classifications:
                primary_classification = MovementClassification.MARKET_BETA_DRIVEN
            elif MovementClassification.MUTED_CONSOLIDATION in classifications:
                primary_classification = MovementClassification.MUTED_CONSOLIDATION
            else:
                primary_classification = MovementClassification.UNEXPLAINED_MOVEMENT
                if MovementClassification.UNEXPLAINED_MOVEMENT not in classifications:
                    classifications.insert(0, MovementClassification.UNEXPLAINED_MOVEMENT)

        details_dict = {
            "symbol": symbol,
            "target_date": target_date,
            "cum_ca_factor": cum_ca_factor,
            "dividend_amount": dividend_amount,
            "estimation_sessions_count": estimation_count,
            "minimum_required_sessions": self.MINIMUM_ESTIMATION_SESSIONS,
            "sector_name": sector_name,
            "industry_name": industry_name,
            "eligible_peers_count": len(eligible_peers)
        }

        return MovementAnalysisResult(
            symbol=symbol,
            trading_date=target_date,
            open=open_p, high=high_p, low=low_p, close=close_p, prev_close=effective_prev_close,
            volume=vol_t,
            ret_1d_raw=ret_1d_raw, ret_1d_adj=ret_1d_adj, ret_1d_total=ret_1d_total,
            gap_open=gap_open, intraday_drift=intraday_drift, intraday_range=intraday_range,
            ret_5d=ret_5d, ret_20d=ret_20d,
            benchmark_return=benchmark_return,
            sector_benchmark_type=b_type,
            sector_benchmark_name=b_name,
            sector_return=sector_return,
            eligible_peers=eligible_peers,
            peer_returns=peer_returns,
            is_survivorship_biased_proxy=is_proxy,
            sector_notes=sec_notes,
            model_status=model_status,
            alpha=alpha, beta=beta, r_squared=r_squared, residual_std_err=residual_std_err,
            estimation_sessions_count=estimation_count,
            expected_return=expected_return,
            abnormal_return=abnormal_return,
            t_statistic=t_statistic,
            sector_adjusted_return=sector_adjusted_return,
            volume_ratio_20d=volume_ratio_20d,
            volume_log_zscore_50d=volume_log_zscore_50d,
            is_volume_spike=is_volume_spike,
            is_zero_volume=is_zero_volume,
            primary_classification=primary_classification,
            classifications=classifications,
            details=details_dict,
            prev_stored_date=prev_stored_date,
            prev_stored_close=prev_stored_close,
            source_prev_close=source_prev_close,
            source_prev_close_provenance=source_prev_close_provenance,
            has_calendar_gap=has_calendar_gap,
            missing_intermediate_sessions=missing_intermediate_sessions,
            interval_return_raw=interval_return_raw,
            interval_return_adj=interval_return_adj,
            interval_sessions_count=interval_sessions_count,
            interval_start_date=interval_start_date
        )
