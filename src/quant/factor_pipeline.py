"""
Market Intelligence Lab — Milestone B4.1 Batch Factor Calculation Engine.

Deterministically populates the `quant_factors_daily` table across the active
universe defined in `securities_master`. Integrates both technical factors
(20/50/200 SMAs, annualized volatility, 60-day rolling beta vs NIFTY 50 PRI,
volume ratio, volume z-scores) and fundamental ratios (TTM P/E, ROE %, D/E, OPM %)
into a single queryable table.

Strict Governance:
1. Point-in-Time (PIT) Fundamental Matching: Enforces filing_date <= trading_date
   to strictly eliminate look-ahead bias.
2. Technical Warm-up Handling: Returns NULL (None) during warm-up periods (N < window)
   without crashing or skewing metrics.
3. Idempotent Upserts: Safe re-runs update records in place using ON CONFLICT DO UPDATE.
"""

import math
import gc
import datetime
import logging
from typing import Dict, Any, List, Optional, Tuple, Set

from src.storage.database import DatabaseManager
from src.quant.benchmark import calculate_beta
from src.quant.volume import calculate_volume_ratio, calculate_volume_zscores
from src.quant.fundamentals import (
    calculate_ttm_pe_ratio,
    calculate_roe,
    calculate_debt_to_equity,
    calculate_opm
)
from src.quant.metrics import calculate_52_week_position
from src.fundamentals.ttm_builder import PointInTimeTTMBuilder

logger = logging.getLogger(__name__)


class FactorPipeline:
    """
    Batch Factor Calculation Engine orchestrating technical indicators and
    point-in-time fundamental statement joins across the active equity universe.
    """

    def __init__(
        self,
        db_manager: Optional[DatabaseManager] = None,
        benchmark_index: str = "NIFTY 50",
        benchmark_type: str = "PRI"
    ):
        self.db = db_manager or DatabaseManager()
        self.benchmark_index = benchmark_index
        self.benchmark_type = benchmark_type
        self._benchmark_ret_map: Optional[Dict[str, float]] = None
        self._benchmark_dates: Optional[List[str]] = None

    def preload_benchmark_returns(self) -> Dict[str, float]:
        """
        Loads and caches official daily benchmark returns from index_daily.
        Returns mapping of trading_date -> 1-day simple return.
        """
        if self._benchmark_ret_map is not None:
            return self._benchmark_ret_map

        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT trading_date, close
                FROM index_daily
                WHERE index_name = ? AND index_type = ?
                ORDER BY trading_date ASC
                """,
                (self.benchmark_index, self.benchmark_type)
            )
            rows = cursor.fetchall()

        if not rows or len(rows) < 2:
            self._benchmark_ret_map = {}
            self._benchmark_dates = []
            return self._benchmark_ret_map

        b_dates = [r["trading_date"] for r in rows]
        b_closes = [float(r["close"]) for r in rows]

        ret_map: Dict[str, float] = {}
        for i in range(1, len(b_closes)):
            prev_c = b_closes[i - 1]
            curr_c = b_closes[i]
            if prev_c > 0:
                ret_map[b_dates[i]] = (curr_c - prev_c) / prev_c

        self._benchmark_ret_map = ret_map
        self._benchmark_dates = b_dates
        return self._benchmark_ret_map

    def compute_technical_factors(
        self,
        ohlcv_records: List[Dict[str, Any]],
        benchmark_ret_map: Optional[Dict[str, float]] = None
    ) -> List[Dict[str, Any]]:
        """
        Computes 20/50/200 SMAs, annualized volatility (sigma * sqrt(252)),
        60-day rolling beta vs NIFTY 50 PRI, volume ratio 20d, and volume z-score 50d.
        Warm-up periods strictly return None (NULL).
        """
        if not ohlcv_records:
            return []

        b_map = benchmark_ret_map if benchmark_ret_map is not None else self.preload_benchmark_returns()

        # Chronologically sorted OHLCV lists
        dates = [r["trading_date"] for r in ohlcv_records]
        closes = [float(r["close"]) for r in ohlcv_records]
        volumes = [int(r["volume"]) if r.get("volume") is not None else 0 for r in ohlcv_records]
        n = len(dates)

        # 1. Daily simple returns for stock
        stock_returns: List[float] = [0.0]
        stock_ret_map: Dict[str, float] = {}
        for i in range(1, n):
            prev_c = closes[i - 1]
            curr_c = closes[i]
            r = (curr_c - prev_c) / prev_c if prev_c > 0 else 0.0
            stock_returns.append(r)
            stock_ret_map[dates[i]] = r

        # Common dates between stock and benchmark
        common_benchmark_dates = sorted(set(stock_ret_map.keys()) & set(b_map.keys()))

        technical_factors: List[Dict[str, Any]] = []

        for i in range(n):
            d = dates[i]
            c = closes[i]

            # 1-day return
            ret_1d = round(stock_returns[i], 4) if i > 0 else 0.0

            # 5-day and 20-day cumulative returns
            ret_5d = round((c - closes[i - 5]) / closes[i - 5], 4) if i >= 5 and closes[i - 5] > 0 else None
            ret_20d = round((c - closes[i - 20]) / closes[i - 20], 4) if i >= 20 and closes[i - 20] > 0 else None

            # Simple Moving Averages (20, 50, 200)
            sma_20 = round(sum(closes[i - 19:i + 1]) / 20.0, 2) if i >= 19 else None
            sma_50 = round(sum(closes[i - 49:i + 1]) / 50.0, 2) if i >= 49 else None
            sma_200 = round(sum(closes[i - 199:i + 1]) / 200.0, 2) if i >= 199 else None

            # Annualized Volatility: sample std dev of 20 daily returns * sqrt(252)
            # Requires 20 daily returns (i.e. i >= 20)
            if i >= 20:
                ret_slice = stock_returns[i - 19:i + 1]  # 20 observations
                mean_r = sum(ret_slice) / 20.0
                var_r = sum((r - mean_r) ** 2 for r in ret_slice) / 19.0
                vol_ann = math.sqrt(var_r) * math.sqrt(252.0)
                volatility_annualized = round(vol_ann, 4)
            else:
                volatility_annualized = None

            # 60-day Rolling Beta vs Nifty 50 PRI
            # Aligns 60 consecutive or available common return sessions ending on or before date d
            aligned_dates = [dt for dt in common_benchmark_dates if dt <= d]
            if len(aligned_dates) >= 60:
                win_dates = aligned_dates[-60:]
                # Check benchmark staleness (P0-03, ADR-0004):
                # If latest aligned benchmark date lags d by > 4 calendar days (~2 sessions), mark beta as None
                latest_b_date = win_dates[-1]
                try:
                    cal_lag = (datetime.date.fromisoformat(d) - datetime.date.fromisoformat(latest_b_date)).days
                except Exception:
                    cal_lag = 0
                if cal_lag > 4:
                    beta_60d = None
                else:
                    s_r_slice = [stock_ret_map[dt] for dt in win_dates]
                    b_r_slice = [b_map[dt] for dt in win_dates]
                    raw_beta = calculate_beta(s_r_slice, b_r_slice, stock_mode="PRI", benchmark_mode="PRI", min_observations=60)
                    beta_60d = round(raw_beta, 4) if raw_beta is not None else None
            else:
                beta_60d = None

            # Volume Ratio (20-day) and Volume Z-Score (50-day)
            vr = calculate_volume_ratio(volumes[:i + 1], window=20)
            raw_z, log_z = calculate_volume_zscores(volumes[:i + 1], window=50)

            vr_val = round(vr, 4) if vr is not None else None
            z_val = round(raw_z, 4) if raw_z is not None else None
            log_z_val = round(log_z, 4) if log_z is not None else None

            is_vol_spike_ratio = 1 if (vr_val is not None and vr_val >= 2.5) else 0
            is_vol_spike_zscore = 1 if (z_val is not None and z_val >= 2.5) else 0

            # 52-week position
            pos = calculate_52_week_position(ohlcv_records[:i + 1])
            dist_high = round(pos["distance_from_high_pct"], 4) if "distance_from_high_pct" in pos else None
            dist_low = round(pos["distance_from_low_pct"], 4) if "distance_from_low_pct" in pos else None

            technical_factors.append({
                "trading_date": d,
                "close": c,
                "ret_1d": ret_1d,
                "ret_5d": ret_5d,
                "ret_20d": ret_20d,
                "vol_20d_annualized": volatility_annualized,
                "volatility_annualized": volatility_annualized,
                "sma_20": sma_20,
                "sma_50": sma_50,
                "sma_200": sma_200,
                "beta_60d_nifty": beta_60d,
                "volume_ratio_20d": vr_val,
                "volume_zscore_50d": z_val,
                "volume_log_zscore_50d": log_z_val,
                "is_volume_spike_ratio": is_vol_spike_ratio,
                "is_volume_spike_zscore": is_vol_spike_zscore,
                "distance_52w_high": dist_high,
                "distance_52w_low": dist_low
            })

        return technical_factors

    def match_point_in_time_fundamentals(
        self,
        trading_date: str,
        close_price: float,
        quarterly_statements: List[Dict[str, Any]],
        annual_statements: Optional[List[Dict[str, Any]]] = None,
        fundamental_statements: Optional[List[Dict[str, Any]]] = None,
        sector: Optional[str] = None
    ) -> Dict[str, Optional[float]]:
        """
        Point-in-Time (PIT) fundamental matching strictly enforcing:
        filing_date <= trading_date (eliminating look-ahead bias).
        Zero synthetic or fabricated fallback numbers (P0-01, ADR-0006).
        """
        ratios = PointInTimeTTMBuilder.compute_ratios(
            symbol="",
            as_of_date=trading_date,
            close_price=close_price,
            quarterly_statements=quarterly_statements,
            annual_statements=annual_statements,
            sector=sector
        )

        ttm_pe = ratios["ttm_pe"].value
        roe_pct = ratios["roe_pct"].value
        debt_to_equity = ratios["debt_to_equity"].value
        opm_pct = ratios["opm_pct"].value

        # Fallback to fundamental_factors_daily only if discrete statements missing and cached row is genuinely PIT and non-synthetic
        if roe_pct is None and fundamental_statements:
            eligible_ff = [f for f in fundamental_statements if f.get("trading_date", "") <= trading_date]
            if eligible_ff:
                latest_ff = eligible_ff[-1]
                # Filter out legacy synthetic markers (18.5, 0.12, 22.0)
                ff_roe = latest_ff.get("roe_pct")
                if ff_roe is not None and ff_roe != 18.5:
                    roe_pct = float(ff_roe)
                    debt_to_equity = float(latest_ff["debt_to_equity"]) if latest_ff.get("debt_to_equity") is not None else None
                    opm_pct = float(latest_ff["operating_margin_ttm"]) if latest_ff.get("operating_margin_ttm") is not None else None
                    ttm_pe = float(latest_ff["pe_ratio"]) if latest_ff.get("pe_ratio") is not None else None

        return {
            "ttm_pe": ttm_pe,
            "roe_pct": roe_pct,
            "debt_to_equity": debt_to_equity,
            "opm_pct": opm_pct
        }

    def compute_daily_factors_for_symbol(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Orchestrates full factor extraction for a single symbol over its historical dates.
        """
        # 1. Fetch OHLCV
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                """
                SELECT trading_date, open, high, low, close, volume
                FROM ohlcv_daily
                WHERE symbol = ?
                ORDER BY trading_date ASC
                """,
                (symbol,)
            )
            ohlcv_rows = [dict(r) for r in cursor.fetchall()]

            # 2. Fetch Financial Statements
            cursor_q = conn.execute(
                """
                SELECT period_end_date, filing_date, revenue, ebitda, net_profit,
                       eps, total_debt, total_equity
                FROM financial_statements_quarterly
                WHERE symbol = ?
                ORDER BY period_end_date ASC
                """,
                (symbol,)
            )
            q_rows = [dict(r) for r in cursor_q.fetchall()]

            cursor_a = conn.execute(
                """
                SELECT period_end_date, filing_date, revenue, ebitda, net_profit,
                       eps, total_debt, total_equity
                FROM financial_statements_annual
                WHERE symbol = ?
                ORDER BY period_end_date ASC
                """,
                (symbol,)
            )
            a_rows = [dict(r) for r in cursor_a.fetchall()]

            cursor_ff = conn.execute(
                """
                SELECT trading_date, roe_pct, debt_to_equity, operating_margin_ttm, pe_ratio
                FROM fundamental_factors_daily
                WHERE symbol = ?
                ORDER BY trading_date ASC
                """,
                (symbol,)
            )
            ff_rows = [dict(r) for r in cursor_ff.fetchall()]

            cursor_sec = conn.execute("SELECT sector FROM securities_master WHERE symbol = ?", (symbol,))
            sec_row = cursor_sec.fetchone()
            symbol_sector = sec_row["sector"] if sec_row and sec_row["sector"] else None

        if not ohlcv_rows:
            return []

        # 3. Compute Technical Factors
        tech_list = self.compute_technical_factors(ohlcv_rows)

        # 4. Point-in-Time Fundamental Matching
        now_ts = datetime.datetime.now(datetime.timezone.utc).isoformat()
        final_factors: List[Dict[str, Any]] = []

        for tf in tech_list:
            t_date = tf["trading_date"]

            if start_date and t_date < start_date:
                continue
            if end_date and t_date > end_date:
                continue

            c = tf["close"]
            fund_dict = self.match_point_in_time_fundamentals(
                trading_date=t_date,
                close_price=c,
                quarterly_statements=q_rows,
                annual_statements=a_rows,
                fundamental_statements=ff_rows,
                sector=symbol_sector
            )

            factor_row = {
                "symbol": symbol,
                "trading_date": t_date,
                "ret_1d": tf["ret_1d"],
                "ret_5d": tf["ret_5d"],
                "ret_20d": tf["ret_20d"],
                "vol_20d_annualized": tf["vol_20d_annualized"],
                "volatility_annualized": tf["volatility_annualized"],
                "sma_20": tf["sma_20"],
                "sma_50": tf["sma_50"],
                "sma_200": tf["sma_200"],
                "beta_60d_nifty": tf["beta_60d_nifty"],
                "volume_ratio_20d": tf["volume_ratio_20d"],
                "volume_zscore_50d": tf["volume_zscore_50d"],
                "volume_log_zscore_50d": tf["volume_log_zscore_50d"],
                "is_volume_spike_ratio": tf["is_volume_spike_ratio"],
                "is_volume_spike_zscore": tf["is_volume_spike_zscore"],
                "distance_52w_high": tf["distance_52w_high"],
                "distance_52w_low": tf["distance_52w_low"],
                "ttm_pe": fund_dict["ttm_pe"],
                "roe_pct": fund_dict["roe_pct"],
                "debt_to_equity": fund_dict["debt_to_equity"],
                "opm_pct": fund_dict["opm_pct"],
                "updated_at": now_ts
            }
            final_factors.append(factor_row)

        return final_factors

    def compute_factors_for_symbol(
        self,
        symbol: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Alias for compute_daily_factors_for_symbol (Milestone B4.3)."""
        return self.compute_daily_factors_for_symbol(symbol, start_date=start_date, end_date=end_date)

    def run_universe_pipeline(
        self,
        symbols: Optional[List[str]] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        batch_size: int = 1000
    ) -> Dict[str, Any]:
        """
        Executes factor generation across active constituents in securities_master
        and upserts rows into quant_factors_daily using idempotent queries.
        """
        t0 = datetime.datetime.now(datetime.timezone.utc)

        # 1. Resolve active constituents
        if not symbols:
            with self.db.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT symbol FROM securities_master WHERE is_active = 1 ORDER BY symbol ASC"
                )
                symbols = [r["symbol"] for r in cursor.fetchall()]

        if not symbols:
            return {
                "total_symbols": 0,
                "symbols_processed": [],
                "total_factors_calculated": 0,
                "total_factors_upserted": 0,
                "duration_seconds": 0.0
            }

        # 2. Preload benchmark once
        self.preload_benchmark_returns()

        total_calculated = 0
        total_upserted = 0
        symbols_processed = []

        batch: List[Dict[str, Any]] = []

        for sym in symbols:
            sym_factors = self.compute_daily_factors_for_symbol(
                symbol=sym,
                start_date=start_date,
                end_date=end_date
            )

            total_calculated += len(sym_factors)
            symbols_processed.append(sym)
            batch.extend(sym_factors)

            # Flush batch if threshold reached
            if len(batch) >= batch_size:
                upserted = self.db.upsert_quant_factors(batch)
                total_upserted += upserted
                batch = []

            del sym_factors
            gc.collect()

        # Flush any remaining rows
        if batch:
            upserted = self.db.upsert_quant_factors(batch)
            total_upserted += upserted
            batch = []

        t1 = datetime.datetime.now(datetime.timezone.utc)
        duration = (t1 - t0).total_seconds()

        return {
            "total_symbols": len(symbols_processed),
            "symbols_processed": symbols_processed,
            "total_factors_calculated": total_calculated,
            "total_factors_upserted": total_upserted,
            "start_date": start_date,
            "end_date": end_date,
            "duration_seconds": duration
        }
