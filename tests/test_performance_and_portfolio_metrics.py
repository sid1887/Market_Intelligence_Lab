"""
Unit tests for Performance Metrics Calculator & Calmar Ratio (Phases 21–25).
"""

import pytest
from src.quant.performance import PerformanceMetricsCalculator


def test_performance_metrics_with_calmar():
    # Construct synthetic 1-year equity curve with a known drawdown
    dates = [f"2024-{m:02d}-01" for m in range(1, 13)]
    # Starts at 100, goes to 120, drops to 108 (10% drawdown), recovers to 130
    values = [100.0, 105.0, 110.0, 115.0, 120.0, 112.0, 108.0, 115.0, 122.0, 125.0, 128.0, 130.0]
    benchmarks = [100.0 + i * 1.5 for i in range(12)]

    equity_curve = [
        {"trading_date": d, "portfolio_value": v, "benchmark_value": b}
        for d, v, b in zip(dates, values, benchmarks)
    ]

    metrics = PerformanceMetricsCalculator.calculate_metrics(equity_curve, periods_per_year=12)

    assert "portfolio" in metrics
    p = metrics["portfolio"]
    assert "calmar_ratio" in p
    assert p["calmar_ratio"] > 0.0
    assert p["max_drawdown_pct"] == 10.0  # (120 - 108) / 120 = 10%
    assert p["total_return_pct"] == 30.0

    b = metrics["benchmark"]
    assert "calmar_ratio" in b


def test_empty_metrics():
    empty = PerformanceMetricsCalculator._empty_metrics()
    assert empty["portfolio"]["calmar_ratio"] == 0.0
    assert empty["benchmark"]["calmar_ratio"] == 0.0
