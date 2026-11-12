"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  createChart,
  LineSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  IChartApi,
  ISeriesApi,
} from "lightweight-charts";

const SYMBOL_COLORS = [
  "#10b981", // Emerald
  "#06b6d4", // Cyan
  "#f59e0b", // Amber
  "#8b5cf6", // Violet
  "#f43f5e", // Rose
  "#3b82f6", // Blue
  "#ec4899", // Pink
  "#14b8a6", // Teal
];

interface BacktestCompareChartProps {
  normalizedSeries: Array<Record<string, string | number>>;
  symbols: string[];
  benchmarkSymbol?: string;
}

export default function BacktestCompareChart({
  normalizedSeries,
  symbols,
  benchmarkSymbol = "BENCHMARK",
}: BacktestCompareChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesMapRef = useRef<Map<string, ISeriesApi<"Line">>>(new Map());

  const [hoveredData, setHoveredData] = useState<{
    date: string;
    values: Record<string, number>;
  } | null>(null);

  // Map each symbol to a deterministic color
  const symbolColorMap = React.useMemo(() => {
    const map: Record<string, string> = {};
    symbols.forEach((sym, idx) => {
      map[sym] = SYMBOL_COLORS[idx % SYMBOL_COLORS.length];
    });
    map[benchmarkSymbol] = "#64748b"; // slate
    return map;
  }, [symbols, benchmarkSymbol]);

  useEffect(() => {
    if (!containerRef.current || !normalizedSeries || normalizedSeries.length === 0) {
      return;
    }

    // Clean previous chart instance
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
      seriesMapRef.current.clear();
    }

    const container = containerRef.current;
    const width = container.clientWidth || 800;

    const chart = createChart(container, {
      width,
      height: 380,
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
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#080c14",
        },
        horzLine: {
          color: "#06b6d4",
          width: 1,
          style: LineStyle.Dashed,
          labelBackgroundColor: "#080c14",
        },
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        timeVisible: false,
        secondsVisible: false,
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.08)",
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
    });

    chartRef.current = chart;

    // Add baseline at 100
    // Track series
    const newSeriesMap = new Map<string, ISeriesApi<"Line">>();

    // 1. Benchmark series
    const benchmarkSeriesData = normalizedSeries
      .filter((d) => d.trading_date && d[benchmarkSymbol] != null)
      .map((d) => ({
        time: String(d.trading_date),
        value: Number(d[benchmarkSymbol]),
      }));

    if (benchmarkSeriesData.length > 0) {
      const benchSeries = chart.addSeries(LineSeries, {
        color: "#64748b",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        title: benchmarkSymbol === "BENCHMARK" ? "NIFTY 50" : benchmarkSymbol,
      });
      benchSeries.setData(benchmarkSeriesData);
      newSeriesMap.set(benchmarkSymbol, benchSeries);
    }

    // 2. Stock series
    symbols.forEach((sym) => {
      const symData = normalizedSeries
        .filter((d) => d.trading_date && d[sym] != null)
        .map((d) => ({
          time: String(d.trading_date),
          value: Number(d[sym]),
        }));

      if (symData.length > 0) {
        const s = chart.addSeries(LineSeries, {
          color: symbolColorMap[sym] || "#38bdf8",
          lineWidth: 2,
          title: sym,
        });
        s.setData(symData);
        newSeriesMap.set(sym, s);
      }
    });

    seriesMapRef.current = newSeriesMap;

    // Add 100 baseline price line to the first available series
    const firstSeries = newSeriesMap.get(benchmarkSymbol) || newSeriesMap.values().next().value;
    if (firstSeries) {
      firstSeries.createPriceLine({
        price: 100,
        color: "#334155",
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: true,
        title: "Base 100",
      });
    }

    // Subscribe to crosshair move
    chart.subscribeCrosshairMove((param) => {
      if (!param || !param.time) {
        setHoveredPointFromLatest();
        return;
      }
      const timeStr = String(param.time);
      const row = normalizedSeries.find((r) => r.trading_date === timeStr);
      if (row) {
        const vals: Record<string, number> = {};
        symbols.forEach((s) => {
          if (row[s] != null) vals[s] = Number(row[s]);
        });
        if (row[benchmarkSymbol] != null) {
          vals[benchmarkSymbol] = Number(row[benchmarkSymbol]);
        }
        setHoveredData({ date: timeStr, values: vals });
      }
    });

    // Default hover point: latest session
    const setHoveredPointFromLatest = () => {
      const last = normalizedSeries[normalizedSeries.length - 1];
      if (last && last.trading_date) {
        const vals: Record<string, number> = {};
        symbols.forEach((s) => {
          if (last[s] != null) vals[s] = Number(last[s]);
        });
        if (last[benchmarkSymbol] != null) {
          vals[benchmarkSymbol] = Number(last[benchmarkSymbol]);
        }
        setHoveredData({ date: String(last.trading_date), values: vals });
      }
    };
    setHoveredPointFromLatest();

    // Container ResizeObserver with requestAnimationFrame debouncing
    let rafId: number | null = null;
    const resizeObserver = new ResizeObserver(() => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      rafId = requestAnimationFrame(() => {
        if (container && chartRef.current) {
          const w = container.clientWidth;
          if (w > 0) chartRef.current.applyOptions({ width: w });
        }
      });
    });

    resizeObserver.observe(container);

    chart.timeScale().fitContent();

    return () => {
      if (rafId !== null) {
        cancelAnimationFrame(rafId);
      }
      resizeObserver.disconnect();
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [normalizedSeries, symbols, benchmarkSymbol, symbolColorMap]);

  return (
    <div className="w-full flex flex-col space-y-3">
      {/* Legend & Hover inspection ribbon */}
      <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3 bg-[#050810] border border-white/[0.08] rounded-2xl text-xs font-mono shadow-[0_4px_20px_rgba(0,0,0,0.4)]">
        <div className="flex items-center space-x-2 text-slate-400">
          <span className="text-slate-500 font-semibold uppercase tracking-wider text-[10px]">Session:</span>
          <span className="text-cyan-400 font-semibold tabular-nums">{hoveredData?.date || "—"}</span>
        </div>
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Benchmark pill */}
          <div className="flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-white/[0.04] border border-white/[0.08]">
            <span className="w-2.5 h-0.5 bg-slate-400 inline-block border-b border-dashed border-slate-300" />
            <span className="text-slate-400 text-[11px]">{benchmarkSymbol}:</span>
            <span className="font-semibold text-slate-300 tabular-nums">
              {hoveredData?.values[benchmarkSymbol] != null
                ? hoveredData.values[benchmarkSymbol].toFixed(2)
                : "—"}
            </span>
          </div>
          {/* Symbol pills */}
          {symbols.map((sym) => {
            const val = hoveredData?.values[sym];
            const color = symbolColorMap[sym] || "#06b6d4";
            const diffFromBase = val != null ? val - 100 : null;
            return (
              <div
                key={sym}
                className="flex items-center space-x-1.5 px-2.5 py-1 rounded-xl bg-white/[0.04] border border-white/[0.08]"
              >
                <span
                  className="w-2 h-2 rounded-full inline-block shadow-[0_0_8px_currentColor]"
                  style={{ backgroundColor: color }}
                />
                <span className="text-slate-300 font-medium text-[11px]">{sym}:</span>
                <span className="font-semibold tabular-nums" style={{ color }}>
                  {val != null ? val.toFixed(2) : "—"}
                </span>
                {diffFromBase != null && (
                  <span
                    className={`text-[10px] font-mono tabular-nums font-semibold ${
                      diffFromBase >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    ({diffFromBase >= 0 ? "+" : ""}
                    {diffFromBase.toFixed(1)}%)
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Chart Canvas */}
      <div className="relative w-full rounded-2xl overflow-hidden border border-white/[0.08] bg-[#040609] p-3 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
        <div ref={containerRef} className="w-full h-[380px]" />
      </div>
    </div>
  );
}
