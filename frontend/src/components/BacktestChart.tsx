"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
} from "lightweight-charts";

export interface EquityCurvePoint {
  trading_date?: string;
  date?: string;
  strategy_nav?: number;
  portfolio_value?: number;
  nav?: number;
  benchmark_value?: number;
  benchmark_nav?: number;
  cash_balance?: number;
  cash?: number;
  drawdown_pct?: number;
  benchmark_drawdown_pct?: number;
}

interface BacktestChartProps {
  data: EquityCurvePoint[];
  initialCapital?: number;
}

export default function BacktestChart({ data, initialCapital = 500000 }: BacktestChartProps) {
  const equityChartContainerRef = useRef<HTMLDivElement>(null);
  const drawdownChartContainerRef = useRef<HTMLDivElement>(null);

  const equityChartRef = useRef<IChartApi | null>(null);
  const drawdownChartRef = useRef<IChartApi | null>(null);

  const [hoveredPoint, setHoveredPoint] = useState<{
    date: string;
    portfolio: number;
    benchmark: number;
    drawdown: number;
    benchmarkDrawdown: number;
  } | null>(null);

  useEffect(() => {
    if (!equityChartContainerRef.current || !drawdownChartContainerRef.current || !data || data.length === 0) {
      return;
    }

    // Clean previous instances
    if (equityChartRef.current) {
      equityChartRef.current.remove();
      equityChartRef.current = null;
    }
    if (drawdownChartRef.current) {
      drawdownChartRef.current.remove();
      drawdownChartRef.current = null;
    }

    // Common chart options
    const commonOptions = {
      layout: {
        background: { type: ColorType.Solid, color: "#040609" },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.04)", style: LineStyle.Dotted },
        horzLines: { color: "rgba(255, 255, 255, 0.04)", style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#06b6d4",
          width: 1 as const,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#080c14",
        },
        horzLine: {
          color: "#06b6d4",
          width: 1 as const,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#080c14",
        },
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        timeVisible: false,
        secondsVisible: false,
      },
    };

    // 1. Equity Curve Chart
    const eqWidth = equityChartContainerRef.current.clientWidth || 800;
    const eqChart = createChart(equityChartContainerRef.current, {
      ...commonOptions,
      width: eqWidth,
      height: 320,
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    });
    equityChartRef.current = eqChart;

    const strategySeries = eqChart.addSeries(LineSeries, {
      color: "#10b981",
      lineWidth: 2,
      title: "Strategy",
    });

    const benchmarkSeries = eqChart.addSeries(LineSeries, {
      color: "#64748b",
      lineWidth: 1,
      lineStyle: LineStyle.Dashed,
      title: "NIFTY 50 TRI",
    });

    // 2. Drawdown Chart with dark rose area gradient fill
    const ddWidth = drawdownChartContainerRef.current.clientWidth || 800;
    const ddChart = createChart(drawdownChartContainerRef.current, {
      ...commonOptions,
      width: ddWidth,
      height: 150,
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        scaleMargins: { top: 0.05, bottom: 0.05 },
      },
    });
    drawdownChartRef.current = ddChart;

    const ddStrategySeries = ddChart.addSeries(AreaSeries, {
      lineColor: "#f43f5e",
      topColor: "rgba(244, 63, 94, 0.4)",
      bottomColor: "rgba(136, 19, 55, 0.01)",
      lineWidth: 2,
      title: "Strategy DD %",
    });

    const ddBenchmarkSeries = ddChart.addSeries(LineSeries, {
      color: "#475569",
      lineWidth: 1,
      lineStyle: LineStyle.Dotted,
      title: "NIFTY DD %",
    });

    // Prepare time-series data
    const strategyData: { time: string; value: number }[] = [];
    const benchmarkData: { time: string; value: number }[] = [];
    const ddStrategyData: { time: string; value: number }[] = [];
    const ddBenchmarkData: { time: string; value: number }[] = [];

    data.forEach((pt) => {
      const timeStr = pt.trading_date || pt.date || "";
      const pVal = pt.strategy_nav ?? pt.portfolio_value ?? pt.nav ?? 0.0;
      const bVal = pt.benchmark_nav ?? pt.benchmark_value ?? 0.0;
      strategyData.push({ time: timeStr, value: pVal });
      benchmarkData.push({ time: timeStr, value: bVal });
      ddStrategyData.push({ time: timeStr, value: pt.drawdown_pct || 0.0 });
      ddBenchmarkData.push({ time: timeStr, value: pt.benchmark_drawdown_pct || 0.0 });
    });

    strategySeries.setData(strategyData);
    benchmarkSeries.setData(benchmarkData);
    ddStrategySeries.setData(ddStrategyData);
    ddBenchmarkSeries.setData(ddBenchmarkData);

    eqChart.timeScale().fitContent();
    ddChart.timeScale().fitContent();

    // Two-way logical range synchronization
    eqChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) ddChart.timeScale().setVisibleLogicalRange(range);
    });
    ddChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) eqChart.timeScale().setVisibleLogicalRange(range);
    });

    // Crosshair hover sync
    eqChart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) {
        setHoveredPoint(null);
        return;
      }
      const timeStr = String(param.time);
      const sVal = param.seriesData.get(strategySeries) as { value?: number };
      const bVal = param.seriesData.get(benchmarkSeries) as { value?: number };
      const matched = data.find((d) => (d.trading_date || d.date) === timeStr);

      if (sVal?.value !== undefined && bVal?.value !== undefined) {
        setHoveredPoint({
          date: timeStr,
          portfolio: sVal.value,
          benchmark: bVal.value,
          drawdown: matched?.drawdown_pct || 0.0,
          benchmarkDrawdown: matched?.benchmark_drawdown_pct || 0.0,
        });
      }
    });

    ddChart.subscribeCrosshairMove((param) => {
      if (!param.time || !param.seriesData) return;
      const timeStr = String(param.time);
      const matched = data.find((d) => (d.trading_date || d.date) === timeStr);
      if (matched) {
        setHoveredPoint({
          date: timeStr,
          portfolio: matched.strategy_nav ?? matched.portfolio_value ?? matched.nav ?? 0,
          benchmark: matched.benchmark_nav ?? matched.benchmark_value ?? 0,
          drawdown: matched.drawdown_pct || 0.0,
          benchmarkDrawdown: matched.benchmark_drawdown_pct || 0.0,
        });
      }
    });

    // Container ResizeObserver with requestAnimationFrame debouncing
    let rafId: number | null = null;
    const resizeObserver = new ResizeObserver(() => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame(() => {
        if (equityChartContainerRef.current && equityChartRef.current) {
          const w = equityChartContainerRef.current.clientWidth;
          if (w > 0) equityChartRef.current.applyOptions({ width: w });
        }
        if (drawdownChartContainerRef.current && drawdownChartRef.current) {
          const w = drawdownChartContainerRef.current.clientWidth;
          if (w > 0) drawdownChartRef.current.applyOptions({ width: w });
        }
      });
    });

    if (equityChartContainerRef.current) resizeObserver.observe(equityChartContainerRef.current);
    if (drawdownChartContainerRef.current && drawdownChartContainerRef.current !== equityChartContainerRef.current) {
      resizeObserver.observe(drawdownChartContainerRef.current);
    }

    return () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      resizeObserver.disconnect();
      if (equityChartRef.current) {
        equityChartRef.current.remove();
        equityChartRef.current = null;
      }
      if (drawdownChartRef.current) {
        drawdownChartRef.current.remove();
        drawdownChartRef.current = null;
      }
    };
  }, [data]);

  const latestPoint = data && data.length > 0 ? data[data.length - 1] : null;
  const currentNav = hoveredPoint ? hoveredPoint.portfolio : (latestPoint?.strategy_nav ?? latestPoint?.portfolio_value ?? latestPoint?.nav ?? initialCapital);
  const currentBench = hoveredPoint ? hoveredPoint.benchmark : (latestPoint?.benchmark_nav ?? latestPoint?.benchmark_value ?? initialCapital);
  const currentDd = hoveredPoint ? hoveredPoint.drawdown : (latestPoint?.drawdown_pct || 0.0);
  const currentBenchDd = hoveredPoint ? hoveredPoint.benchmarkDrawdown : (latestPoint?.benchmark_drawdown_pct || 0.0);
  const currentDate = hoveredPoint ? hoveredPoint.date : (latestPoint?.trading_date || latestPoint?.date || "—");

  const pReturn = ((currentNav / initialCapital) - 1.0) * 100.0;
  const bReturn = ((currentBench / initialCapital) - 1.0) * 100.0;
  const alphaSpread = pReturn - bReturn;

  return (
    <div className="space-y-4">
      {/* Telemetry Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 bg-[#050810] rounded-2xl border border-white/[0.08] text-xs font-mono shadow-[0_4px_20px_rgba(0,0,0,0.4)]">
        <div className="flex items-center space-x-2">
          <span className="text-slate-400">Date:</span>
          <span className="font-semibold text-white tabular-nums">{currentDate}</span>
        </div>

        <div className="flex items-center flex-wrap gap-4">
          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
            <span className="text-slate-400">Strategy NAV:</span>
            <span className="font-semibold text-emerald-300 tabular-nums">
              ₹{currentNav.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
            <span className={`text-[11px] tabular-nums font-semibold ${pReturn >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              ({pReturn >= 0 ? "+" : ""}{pReturn.toFixed(1)}%)
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-500" />
            <span className="text-slate-400">NIFTY 50:</span>
            <span className="font-semibold text-slate-300 tabular-nums">
              ₹{currentBench.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
            <span className={`text-[11px] tabular-nums font-semibold ${bReturn >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              ({bReturn >= 0 ? "+" : ""}{bReturn.toFixed(1)}%)
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-slate-400">Excess Alpha:</span>
            <span className={`font-semibold tabular-nums ${alphaSpread >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {alphaSpread >= 0 ? "+" : ""}{alphaSpread.toFixed(1)}%
            </span>
          </div>

          <div className="flex items-center space-x-2">
            <span className="text-slate-400">Drawdown:</span>
            <span className="font-semibold text-rose-400 tabular-nums">{currentDd.toFixed(1)}%</span>
            <span className="text-slate-500 text-[11px] tabular-nums">(BM: {currentBenchDd.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      {/* Equity Curve Container */}
      <div className="relative bg-[#040609] rounded-2xl p-3 border border-white/[0.08] shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
        <div className="flex items-center justify-between pb-3 px-2 text-xs font-mono text-slate-400 border-b border-white/[0.06]">
          <span className="uppercase tracking-wider font-semibold text-slate-300">PORTFOLIO EQUITY CURVE (INR)</span>
          <div className="flex items-center space-x-3 text-[11px]">
            <span className="flex items-center space-x-1.5 text-emerald-400 font-medium">
              <span className="w-3 h-0.5 bg-emerald-400 inline-block rounded-full shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
              <span>Strategy</span>
            </span>
            <span className="flex items-center space-x-1.5 text-slate-400">
              <span className="w-3 h-0.5 border-t border-dashed border-slate-400 inline-block" />
              <span>NIFTY 50 TRI</span>
            </span>
          </div>
        </div>
        <div ref={equityChartContainerRef} className="w-full pt-2" />
      </div>

      {/* Underwater Drawdown Container */}
      <div className="relative bg-[#040609] rounded-2xl p-3 border border-white/[0.08] shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
        <div className="flex items-center justify-between pb-3 px-2 text-xs font-mono text-slate-400 border-b border-white/[0.06]">
          <span className="uppercase tracking-wider font-semibold text-slate-300">UNDERWATER DRAWDOWN PROFILE (% FROM PEAK)</span>
          <div className="flex items-center space-x-3 text-[11px]">
            <span className="flex items-center space-x-1.5 text-rose-400 font-medium">
              <span className="w-3 h-2 bg-rose-500/30 border border-rose-500 inline-block rounded-sm" />
              <span>Strategy Drawdown</span>
            </span>
            <span className="flex items-center space-x-1.5 text-slate-500">
              <span className="w-3 h-0.5 border-t border-dotted border-slate-500 inline-block" />
              <span>NIFTY 50</span>
            </span>
          </div>
        </div>
        <div ref={drawdownChartContainerRef} className="w-full pt-2" />
      </div>
    </div>
  );
}
