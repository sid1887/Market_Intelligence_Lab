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
  trading_date: string;
  portfolio_value: number;
  benchmark_value: number;
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
        background: { type: ColorType.Solid, color: "#090d16" },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "var(--font-geist-mono), monospace",
      },
      grid: {
        vertLines: { color: "#1e293b", style: LineStyle.Dotted },
        horzLines: { color: "#1e293b", style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#38bdf8",
          width: 1 as const,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#0f172a",
        },
        horzLine: {
          color: "#38bdf8",
          width: 1 as const,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#0f172a",
        },
      },
      timeScale: {
        borderColor: "#1e293b",
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
        borderColor: "#1e293b",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    });
    equityChartRef.current = eqChart;

    const strategySeries = eqChart.addSeries(LineSeries, {
      color: "#06b6d4",
      lineWidth: 2,
      title: "Strategy",
    });

    const benchmarkSeries = eqChart.addSeries(LineSeries, {
      color: "#94a3b8",
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
        borderColor: "#1e293b",
        scaleMargins: { top: 0.05, bottom: 0.05 },
      },
    });
    drawdownChartRef.current = ddChart;

    const ddStrategySeries = ddChart.addSeries(AreaSeries, {
      lineColor: "#f43f5e",
      topColor: "rgba(244, 63, 94, 0.45)",
      bottomColor: "rgba(136, 19, 55, 0.02)",
      lineWidth: 2,
      title: "Strategy DD %",
    });

    const ddBenchmarkSeries = ddChart.addSeries(LineSeries, {
      color: "#64748b",
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
      strategyData.push({ time: pt.trading_date, value: pt.portfolio_value });
      benchmarkData.push({ time: pt.trading_date, value: pt.benchmark_value });
      ddStrategyData.push({ time: pt.trading_date, value: pt.drawdown_pct || 0.0 });
      ddBenchmarkData.push({ time: pt.trading_date, value: pt.benchmark_drawdown_pct || 0.0 });
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
      const matched = data.find((d) => d.trading_date === timeStr);

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
      const matched = data.find((d) => d.trading_date === timeStr);
      if (matched) {
        setHoveredPoint({
          date: timeStr,
          portfolio: matched.portfolio_value,
          benchmark: matched.benchmark_value,
          drawdown: matched.drawdown_pct || 0.0,
          benchmarkDrawdown: matched.benchmark_drawdown_pct || 0.0,
        });
      }
    });

    // Handle Window Resize
    const handleResize = () => {
      if (equityChartContainerRef.current && eqChart) {
        eqChart.applyOptions({ width: equityChartContainerRef.current.clientWidth });
      }
      if (drawdownChartContainerRef.current && ddChart) {
        ddChart.applyOptions({ width: drawdownChartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
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
  const currentNav = hoveredPoint ? hoveredPoint.portfolio : (latestPoint?.portfolio_value || initialCapital);
  const currentBench = hoveredPoint ? hoveredPoint.benchmark : (latestPoint?.benchmark_value || initialCapital);
  const currentDd = hoveredPoint ? hoveredPoint.drawdown : (latestPoint?.drawdown_pct || 0.0);
  const currentBenchDd = hoveredPoint ? hoveredPoint.benchmarkDrawdown : (latestPoint?.benchmark_drawdown_pct || 0.0);
  const currentDate = hoveredPoint ? hoveredPoint.date : (latestPoint?.trading_date || "—");

  const pReturn = ((currentNav / initialCapital) - 1.0) * 100.0;
  const bReturn = ((currentBench / initialCapital) - 1.0) * 100.0;
  const alphaSpread = pReturn - bReturn;

  return (
    <div className="space-y-4">
      {/* Telemetry Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-3.5 bg-slate-950/80 rounded-lg border border-slate-800 text-xs font-mono">
        <div className="flex items-center space-x-2">
          <span className="text-slate-400">Date:</span>
          <span className="font-semibold text-slate-200">{currentDate}</span>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400" />
            <span className="text-slate-400">Strategy NAV:</span>
            <span className="font-semibold text-cyan-300">
              ₹{currentNav.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
            <span className={`text-[11px] ${pReturn >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              ({pReturn >= 0 ? "+" : ""}{pReturn.toFixed(1)}%)
            </span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
            <span className="text-slate-400">NIFTY 50:</span>
            <span className="font-semibold text-slate-300">
              ₹{currentBench.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
            </span>
            <span className={`text-[11px] ${bReturn >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              ({bReturn >= 0 ? "+" : ""}{bReturn.toFixed(1)}%)
            </span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="text-slate-400">Excess Alpha:</span>
            <span className={`font-semibold ${alphaSpread >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {alphaSpread >= 0 ? "+" : ""}{alphaSpread.toFixed(1)}%
            </span>
          </div>

          <div className="flex items-center space-x-1.5">
            <span className="text-slate-400">Drawdown:</span>
            <span className="font-semibold text-rose-400">{currentDd.toFixed(1)}%</span>
            <span className="text-slate-500 text-[11px]">(BM: {currentBenchDd.toFixed(1)}%)</span>
          </div>
        </div>
      </div>

      {/* Equity Curve Container */}
      <div className="relative bg-slate-950 rounded-lg p-2 border border-slate-800">
        <div className="flex items-center justify-between pb-2 px-2 text-xs font-mono text-slate-400 border-b border-slate-900">
          <span>PORTFOLIO EQUITY CURVE (INR)</span>
          <div className="flex items-center space-x-3 text-[11px]">
            <span className="flex items-center space-x-1 text-cyan-400">
              <span className="w-3 h-0.5 bg-cyan-400 inline-block" />
              <span>Strategy</span>
            </span>
            <span className="flex items-center space-x-1 text-slate-400">
              <span className="w-3 h-0.5 border-t border-dashed border-slate-400 inline-block" />
              <span>NIFTY 50 TRI</span>
            </span>
          </div>
        </div>
        <div ref={equityChartContainerRef} className="w-full" />
      </div>

      {/* Underwater Drawdown Container */}
      <div className="relative bg-slate-950 rounded-lg p-2 border border-slate-800">
        <div className="flex items-center justify-between pb-2 px-2 text-xs font-mono text-slate-400 border-b border-slate-900">
          <span>UNDERWATER DRAWDOWN PROFILE (% FROM PEAK)</span>
          <div className="flex items-center space-x-3 text-[11px]">
            <span className="flex items-center space-x-1 text-rose-400">
              <span className="w-3 h-2 bg-rose-500/30 border border-rose-500 inline-block" />
              <span>Strategy Drawdown</span>
            </span>
            <span className="flex items-center space-x-1 text-slate-500">
              <span className="w-3 h-0.5 border-t border-dotted border-slate-500 inline-block" />
              <span>NIFTY 50</span>
            </span>
          </div>
        </div>
        <div ref={drawdownChartContainerRef} className="w-full" />
      </div>
    </div>
  );
}
