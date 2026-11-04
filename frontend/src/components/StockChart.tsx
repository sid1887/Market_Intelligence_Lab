"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  AreaSeries,
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi
} from "lightweight-charts";

export interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface ProjectionStep {
  step: number;
  target_date: string;
  expected: number;
  upper_80: number;
  lower_80: number;
  upper_95: number;
  lower_95: number;
}

export interface ForecastData {
  symbol: string;
  as_of_date: string;
  current_close: number;
  annualized_volatility: number;
  volatility_regime: "LOW" | "NORMAL" | "ELEVATED";
  forecast_horizon_days: number;
  garch_parameters?: {
    omega: number;
    alpha: number;
    beta: number;
    persistence: number;
  };
  mean_reversion_anchor?: number;
  projections: ProjectionStep[];
}

interface StockChartProps {
  symbol: string;
  data: CandleData[];
  sma200?: number | null;
  forecast?: ForecastData | null;
  height?: number;
  compact?: boolean;
}

export default function StockChart({
  symbol,
  data,
  sma200,
  forecast,
  height,
  compact = false,
}: StockChartProps) {
  const chartHeight = height || (compact ? 270 : 440);
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const [activeRange, setActiveRange] = useState<"3M" | "6M" | "1Y" | "3Y" | "5Y" | "MAX">("1Y");
  const [showForecast, setShowForecast] = useState<boolean>(true);
  const [hoverData, setHoverData] = useState<CandleData | null>(null);
  const [hoverProjection, setHoverProjection] = useState<ProjectionStep | null>(null);

  useEffect(() => {
    if (!chartContainerRef.current || !data || data.length === 0) return;

    // Clean up existing chart instance
    if (chartRef.current) {
      chartRef.current.remove();
      chartRef.current = null;
    }

    const container = chartContainerRef.current;

    // Initialize Chart
    const chart = createChart(container, {
      width: container.clientWidth,
      height: chartHeight,
      layout: {
        background: { type: ColorType.Solid, color: "#050811" },
        textColor: "#94a3b8",
        fontSize: 11,
        fontFamily: "var(--font-jetbrains-mono), monospace"
      },
      grid: {
        vertLines: { color: "rgba(255, 255, 255, 0.03)", style: 1 },
        horzLines: { color: "rgba(255, 255, 255, 0.03)", style: 1 }
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: {
          color: "#475569",
          width: 1,
          style: 3,
          labelBackgroundColor: "#1e293b"
        },
        horzLine: {
          color: "#475569",
          width: 1,
          style: 3,
          labelBackgroundColor: "#1e293b"
        }
      },
      rightPriceScale: {
        borderColor: "rgba(255, 255, 255, 0.06)",
        scaleMargins: {
          top: 0.08,
          bottom: 0.22
        }
      },
      timeScale: {
        borderColor: "rgba(255, 255, 255, 0.06)",
        timeVisible: true,
        secondsVisible: false
      }
    });

    chartRef.current = chart;

    // 1. Candlestick Series
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",        // Emerald 500
      downColor: "#ef4444",      // Red 500
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444"
    });
    candlestickSeriesRef.current = candlestickSeries;

    // 2. Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: "volume"
      },
      priceScaleId: ""
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.82,
        bottom: 0
      }
    });
    volumeSeriesRef.current = volumeSeries;

    // Sort historical data chronologically
    const sortedData = [...data].sort((a, b) => (a.time > b.time ? 1 : -1));

    // Timeframe filtering
    let filteredData = sortedData;
    if (activeRange === "3M") {
      filteredData = sortedData.slice(-63);
    } else if (activeRange === "6M") {
      filteredData = sortedData.slice(-126);
    } else if (activeRange === "1Y") {
      filteredData = sortedData.slice(-252);
    } else if (activeRange === "3Y") {
      filteredData = sortedData.slice(-756);
    } else if (activeRange === "5Y") {
      filteredData = sortedData.slice(-1260);
    } else if (activeRange === "MAX") {
      filteredData = sortedData;
    }

    const candlePayload = filteredData.map(d => ({
      time: d.time,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close
    }));

    const volumePayload = filteredData.map(d => ({
      time: d.time,
      value: d.volume,
      color: d.close >= d.open ? "rgba(16, 185, 129, 0.35)" : "rgba(239, 68, 68, 0.35)"
    }));

    candlestickSeries.setData(candlePayload);
    volumeSeries.setData(volumePayload);

    // 3. Econometric Forecast Cones (B7.0 / B10.0 Walk-Forward Shaded Area Projection)
    const lastBar = sortedData[sortedData.length - 1];

    if (showForecast && forecast && forecast.projections && forecast.projections.length > 0 && lastBar) {
      const anchorPoint = { time: lastBar.time, value: lastBar.close };

      // (A) 95% Confidence Cone (0.06 opacity shaded area)
      const cone95Series = chart.addSeries(AreaSeries, {
        topColor: "rgba(6, 182, 212, 0.06)",
        bottomColor: "rgba(6, 182, 212, 0.06)",
        lineColor: "rgba(6, 182, 212, 0.3)",
        lineWidth: 1,
        title: "95% Cone"
      });
      cone95Series.setData([
        anchorPoint,
        ...forecast.projections.map(p => ({ time: p.target_date, value: p.upper_95 }))
      ]);

      // (B) 80% Confidence Cone (0.16 opacity shaded area)
      const cone80Series = chart.addSeries(AreaSeries, {
        topColor: "rgba(6, 182, 212, 0.16)",
        bottomColor: "rgba(6, 182, 212, 0.16)",
        lineColor: "rgba(6, 182, 212, 0.6)",
        lineWidth: 1,
        title: "80% Cone"
      });
      cone80Series.setData([
        anchorPoint,
        ...forecast.projections.map(p => ({ time: p.target_date, value: p.upper_80 }))
      ]);

      // (C) Lower Envelope Boundaries
      const lower80Series = chart.addSeries(LineSeries, {
        color: "rgba(6, 182, 212, 0.6)",
        lineWidth: 1,
        lineStyle: 2, // Dashed
        title: "Lower 80%"
      });
      lower80Series.setData([
        anchorPoint,
        ...forecast.projections.map(p => ({ time: p.target_date, value: p.lower_80 }))
      ]);

      const lower95Series = chart.addSeries(LineSeries, {
        color: "rgba(6, 182, 212, 0.3)",
        lineWidth: 1,
        lineStyle: 2, // Dashed
        title: "Lower 95%"
      });
      lower95Series.setData([
        anchorPoint,
        ...forecast.projections.map(p => ({ time: p.target_date, value: p.lower_95 }))
      ]);

      // (D) Central Expected Trajectory (Dashed Cyan Line)
      const expectedSeries = chart.addSeries(LineSeries, {
        color: "#06b6d4",
        lineWidth: 2,
        lineStyle: 2, // LineStyle.Dashed
        title: "Expected Path"
      });
      expectedSeries.setData([
        anchorPoint,
        ...forecast.projections.map(p => ({ time: p.target_date, value: p.expected }))
      ]);
    }

    // Default hover data: latest historical session
    if (filteredData.length > 0) {
      setHoverData(filteredData[filteredData.length - 1]);
      setHoverProjection(null);
    }

    // Crosshair hover listener
    chart.subscribeCrosshairMove(param => {
      if (
        param.point === undefined ||
        !param.time ||
        param.point.x < 0 ||
        param.point.x > container.clientWidth ||
        param.point.y < 0 ||
        param.point.y > container.clientHeight
      ) {
        if (filteredData.length > 0) {
          setHoverData(filteredData[filteredData.length - 1]);
          setHoverProjection(null);
        }
      } else {
        const histItem = filteredData.find(d => d.time === param.time);
        if (histItem) {
          setHoverData(histItem);
          setHoverProjection(null);
        } else if (forecast && forecast.projections) {
          const projItem = forecast.projections.find(p => p.target_date === param.time);
          if (projItem) {
            setHoverProjection(projItem);
          }
        }
      }
    });

    chart.timeScale().fitContent();

    // Resize Observer for dynamic responsiveness
    const handleResize = () => {
      if (chartContainerRef.current && chartRef.current) {
        chartRef.current.applyOptions({
          width: chartContainerRef.current.clientWidth
        });
      }
    };

    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (chartRef.current) {
        chartRef.current.remove();
        chartRef.current = null;
      }
    };
  }, [data, activeRange, showForecast, forecast, chartHeight]);

  const latest = hoverData || (data && data.length > 0 ? data[data.length - 1] : null);
  const isUp = latest ? latest.close >= latest.open : true;
  const changeVal = latest ? latest.close - latest.open : 0;
  const changePct = latest && latest.open > 0 ? (changeVal / latest.open) * 100 : 0;

  return (
    <div className={`bg-[#050811] border border-white/[0.05] rounded-xl shadow-xl backdrop-blur-sm overflow-hidden ${compact ? "p-2.5" : "p-4"}`}>
      {/* Top Header: Title, Live Telemetry & Controls */}
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2 pb-2 border-b border-white/[0.05]">
        <div>
          {!compact && (
            <div className="flex items-center space-x-3 mb-1">
              <h2 className="text-base font-bold text-slate-100 font-mono tracking-tight">{symbol} Price Action</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                NSE Cash (EQ)
              </span>
            </div>
          )}

          {/* Crosshair Header Telemetry: Historical Bar vs Future Projection */}
          {hoverProjection ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] font-mono bg-cyan-950/40 px-2 py-0.5 rounded border border-cyan-800/60">
              <span className="text-cyan-400 font-semibold">Forecast +{hoverProjection.step}d:</span>
              <span className="text-slate-300">Target: <strong className="text-cyan-300">₹{hoverProjection.expected.toFixed(2)}</strong></span>
              <span className="text-slate-400">80% CI: <strong className="text-slate-200">₹{hoverProjection.lower_80.toFixed(1)}–₹{hoverProjection.upper_80.toFixed(1)}</strong></span>
            </div>
          ) : latest ? (
            <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[10px] font-mono">
              <span className="text-slate-400">{latest.time}</span>
              <span className="text-slate-400">O: <strong className="text-slate-200">₹{latest.open.toFixed(2)}</strong></span>
              <span className="text-slate-400">H: <strong className="text-slate-200">₹{latest.high.toFixed(2)}</strong></span>
              <span className="text-slate-400">L: <strong className="text-slate-200">₹{latest.low.toFixed(2)}</strong></span>
              <span className="text-slate-400">C: <strong className={isUp ? "text-emerald-400 font-bold" : "text-red-400 font-bold"}>₹{latest.close.toFixed(2)}</strong></span>
              <span className={isUp ? "text-emerald-400 font-semibold" : "text-red-400 font-semibold"}>
                {changeVal >= 0 ? "+" : ""}{changeVal.toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
              </span>
              <span className="text-slate-500 hidden sm:inline">Vol: {latest.volume.toLocaleString()}</span>
            </div>
          ) : null}
        </div>

        {/* Forecast Cone Toggle & Time Horizon Buttons */}
        <div className="flex flex-wrap items-center gap-1.5 ml-auto">
          {/* 20D Forecast Cone Toggle */}
          <button
            onClick={() => setShowForecast(!showForecast)}
            title="Toggle Walk-Forward GARCH(1,1) & OU Mean-Reversion Fan Cone"
            className={`flex items-center space-x-1 px-2 py-0.5 rounded text-[10px] font-mono transition-all border ${
              showForecast
                ? "bg-cyan-950/80 border-cyan-500/60 text-cyan-300 font-semibold"
                : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
            }`}
          >
            <span className={`w-1.5 h-1.5 rounded-full ${showForecast ? "bg-cyan-400 animate-pulse" : "bg-slate-600"}`} />
            <span>20D Cone</span>
          </button>

          {/* Time Horizon Selector */}
          <div className="flex items-center space-x-0.5 bg-slate-950 p-0.5 rounded border border-white/[0.06] text-[10px] font-mono">
            {(["3M", "6M", "1Y", "3Y", "MAX"] as const).map(range => (
              <button
                key={range}
                onClick={() => setActiveRange(range)}
                className={`px-1.5 py-0.5 rounded transition-colors ${
                  activeRange === range
                    ? "bg-cyan-600 text-white font-semibold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Chart Canvas Mount Point */}
      <div
        ref={chartContainerRef}
        style={{ height: chartHeight }}
        className="w-full relative"
      />

      {/* Legend Footer */}
      <div className="flex flex-wrap items-center justify-between gap-y-1 text-[9px] text-slate-500 font-mono mt-1.5 pt-1.5 border-t border-white/[0.04]">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-0.5">
          <span className="flex items-center space-x-1">
            <span className="w-2 h-2 rounded-sm bg-emerald-500" />
            <span>Bull</span>
          </span>
          <span className="flex items-center space-x-1">
            <span className="w-2 h-2 rounded-sm bg-red-500" />
            <span>Bear</span>
          </span>
          {showForecast && (
            <>
              <span className="flex items-center space-x-1 text-cyan-400">
                <span className="w-2.5 h-0.5 bg-cyan-400" />
                <span>Forecast Path</span>
              </span>
              <span className="flex items-center space-x-1 text-cyan-300">
                <span className="w-2.5 h-0.5 bg-cyan-400 opacity-60" />
                <span>80% Envelope</span>
              </span>
            </>
          )}
          {sma200 && (
            <span className="text-slate-400">
              200SMA: <strong className="text-amber-400">₹{sma200.toFixed(2)}</strong>
            </span>
          )}
        </div>
        <div className="text-slate-600 hidden sm:block">
          TradingView Lightweight-Charts
        </div>
      </div>
    </div>
  );
}
