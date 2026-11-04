from typing import List, Dict, Any, Tuple, Optional
from src.quant.benchmark import validate_comparison_modes, BenchmarkMode

class AlignedSeries:
    """
    Pairs stock prices/returns with benchmark index values/returns on exact trading dates.
    Discards unaligned dates and validates return mode consistency.
    """

    @staticmethod
    def align_stock_and_benchmark(
        stock_records: List[Dict[str, Any]],
        benchmark_records: List[Dict[str, Any]],
        stock_price_key: str = "close",
        benchmark_value_key: str = "close"
    ) -> List[Dict[str, Any]]:
        """
        Inner-joins stock records and benchmark records on exact trading_date.
        Returns chronologically sorted aligned observations.
        """
        stock_by_date = {r["trading_date"]: r for r in stock_records}
        bench_by_date = {r["trading_date"]: r for r in benchmark_records}

        common_dates = sorted(set(stock_by_date.keys()) & set(bench_by_date.keys()))

        aligned = []
        for d in common_dates:
            s_rec = stock_by_date[d]
            b_rec = bench_by_date[d]
            aligned.append({
                "trading_date": d,
                "stock_price": float(s_rec[stock_price_key]),
                "benchmark_value": float(b_rec[benchmark_value_key]),
                "stock_volume": s_rec.get("volume"),
                "stock_raw": s_rec,
                "benchmark_raw": b_rec
            })

        return aligned

    @staticmethod
    def compute_aligned_returns(
        aligned_pairs: List[Dict[str, Any]],
        stock_mode: str = BenchmarkMode.PRI,
        benchmark_mode: str = BenchmarkMode.PRI
    ) -> Tuple[List[str], List[float], List[float]]:
        """
        Computes aligned simple daily returns: (R_s,t, R_b,t).
        Validates return mode consistency.
        Returns (dates, stock_returns, benchmark_returns).
        """
        validate_comparison_modes(stock_mode, benchmark_mode)

        if len(aligned_pairs) < 2:
            return [], [], []

        dates = []
        s_returns = []
        b_returns = []

        for i in range(1, len(aligned_pairs)):
            prev = aligned_pairs[i - 1]
            curr = aligned_pairs[i]

            s_prev = prev["stock_price"]
            s_curr = curr["stock_price"]
            b_prev = prev["benchmark_value"]
            b_curr = curr["benchmark_value"]

            if s_prev > 0 and b_prev > 0:
                r_s = (s_curr - s_prev) / s_prev
                r_b = (b_curr - b_prev) / b_prev
                dates.append(curr["trading_date"])
                s_returns.append(r_s)
                b_returns.append(r_b)

        return dates, s_returns, b_returns
