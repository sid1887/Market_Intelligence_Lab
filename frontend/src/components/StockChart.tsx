"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi
} from "lightweight-charts";
// Lightweight charts wrapper

export interface CandleData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface StockChartProps {
  symbol: string;
  data: CandleData[];
  sma200?: number | null;
}

export default function StockChart({ symbol, data, sma200 }: StockChartProps) {
  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candlestickSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  const [activeRange, setActiveRange] = useState<"3M" | "6M" | "1Y" | "ALL">("6M");
  const [hoverData, setHoverData] = useState<CandleData | null>(null);

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
      height: 420,
      layout: {
        background: { type: ColorType.Solid, color: "#090d16" },
        textColor: "#94a3b8",
        fontSize: 12,
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
      },
      grid: {
        vertLines: { color: "#1e293b", style: 1 },
        horzLines: { color: "#1e293b", style: 1 }
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
        borderColor: "#1e293b",
        scaleMargins: {
          top: 0.1,
          bottom: 0.25
        }
      },
      timeScale: {
        borderColor: "#1e293b",
        timeVisible: true,
        secondsVisible: false
      }
    });

    chartRef.current = chart;

    // 1. Add Candlestick Series
    const candlestickSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#10b981",        // Emerald 500
      downColor: "#ef4444",      // Red 500
      borderUpColor: "#10b981",
      borderDownColor: "#ef4444",
      wickUpColor: "#10b981",
      wickDownColor: "#ef4444"
    });
    candlestickSeriesRef.current = candlestickSeries;

    // 2. Add Volume Histogram Series
    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: {
        type: "volume"
      },
      priceScaleId: "" // Overlay on separate sub-scale
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: {
        top: 0.8,
        bottom: 0
      }
    });
    volumeSeriesRef.current = volumeSeries;

    // Format & Set Data
    // Ensure chronological order
    const sortedData = [...data].sort((a, b) => (a.time > b.time ? 1 : -1));

    // Filter by timeframe
    let filteredData = sortedData;
    if (activeRange === "3M") {
      filteredData = sortedData.slice(-63);
    } else if (activeRange === "6M") {
      filteredData = sortedData.slice(-126);
    } else if (activeRange === "1Y") {
      filteredData = sortedData.slice(-252);
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

    // Initial default hover data (latest session)
    if (filteredData.length > 0) {
      setHoverData(filteredData[filteredData.length - 1]);
    }

    // Subscribe to crosshair move for real-time OHLCV legend
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
        }
      } else {
        const item = filteredData.find(d => d.time === param.time);
        if (item) {
          setHoverData(item);
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
  }, [data, activeRange]);

  const latest = hoverData || (data && data.length > 0 ? data[data.length - 1] : null);
  const isUp = latest ? latest.close >= latest.open : true;
  const changeVal = latest ? latest.close - latest.open : 0;
  const changePct = latest && latest.open > 0 ? (changeVal / latest.open) * 100 : 0;

  return (
    <div className="bg-slate-900/70 border border-slate-800 rounded-xl p-4 shadow-xl backdrop-blur-sm">
      {/* Top Header & Range Buttons */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-3 pb-3 border-b border-slate-800/80">
        <div>
          <div className="flex items-center space-x-3">
            <h2 className="text-lg font-bold text-slate-100 font-mono tracking-tight">{symbol} Price Action</h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-mono">
              NSE Cash (EQ)
            </span>
          </div>

          {latest && (
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 mt-1 text-xs font-mono">
              <span className="text-slate-400">Date: <strong className="text-slate-200">{latest.time}</strong></span>
              <span className="text-slate-400">O: <strong className="text-slate-200">₹{latest.open.toFixed(2)}</strong></span>
              <span className="text-slate-400">H: <strong className="text-slate-200">₹{latest.high.toFixed(2)}</strong></span>
              <span className="text-slate-400">L: <strong className="text-slate-200">₹{latest.low.toFixed(2)}</strong></span>
              <span className="text-slate-400">C: <strong className={isUp ? "text-emerald-400 font-bold" : "text-red-400 font-bold"}>₹{latest.close.toFixed(2)}</strong></span>
              <span className={isUp ? "text-emerald-400 font-semibold" : "text-red-400 font-semibold"}>
                {changeVal >= 0 ? "+" : ""}{changeVal.toFixed(2)} ({changePct >= 0 ? "+" : ""}{changePct.toFixed(2)}%)
              </span>
              <span className="text-slate-400">Vol: <strong className="text-slate-200">{latest.volume.toLocaleString()}</strong></span>
            </div>
          )}
        </div>

        {/* Time Horizon Selector */}
        <div className="flex items-center space-x-1 bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
          {(["3M", "6M", "1Y", "ALL"] as const).map(range => (
            <button
              key={range}
              onClick={() => setActiveRange(range)}
              className={`px-3 py-1 rounded transition-colors ${
                activeRange === range
                  ? "bg-cyan-600 text-white font-semibold shadow-sm"
                  : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"
              }`}
            >
              {range}
            </button>
          ))}
        </div>
      </div>

      {/* Chart Canvas Mount Point */}
      <div ref={chartContainerRef} className="w-full relative min-h-[420px]" />

      {/* Legend Footer */}
      <div className="flex items-center justify-between text-xs text-slate-500 font-mono mt-3 pt-2 border-t border-slate-800/60">
        <div className="flex items-center space-x-4">
          <span className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" />
            <span>Bullish Session</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-red-500" />
            <span>Bearish Session</span>
          </span>
          <span className="flex items-center space-x-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-slate-600" />
            <span>Volume Bars</span>
          </span>
          {sma200 && (
            <span className="text-slate-400">
              200 SMA: <strong className="text-amber-400">₹{sma200.toFixed(2)}</strong>
            </span>
          )}
        </div>
        <div className="text-slate-500 hidden sm:block">
          TradingView Lightweight-Charts · HTML5 Canvas
        </div>
      </div>
    </div>
  );
}
