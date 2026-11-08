"use client";

import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import {
  runMultiStockComparison,
  MultiStockCompareResponse,
  StockComparisonMetric,
} from "@/lib/api";
import {
  Plus,
  X,
  Play,
  Loader2,
  ShieldAlert,
  Percent,
  Activity,
  Layers,
  Sparkles,
  BarChart2,
  Sliders,
} from "lucide-react";

// Dynamic import with SSR disabled for lightweight-charts
const BacktestCompareChart = dynamic(() => import("./BacktestCompareChart"), {
  ssr: false,
  loading: () => (
    <div className="h-[380px] w-full flex items-center justify-center bg-slate-900/60 rounded-xl border border-slate-800 text-xs font-mono text-slate-500">
      <Loader2 className="w-5 h-5 animate-spin text-cyan-400 mr-2" />
      Initializing Comparison Engine Canvas...
    </div>
  ),
});

const POPULAR_SUGGESTIONS = [
  "TCS",
  "INFY",
  "HCLTECH",
  "RELIANCE",
  "HDFCBANK",
  "ICICIBANK",
  "LT",
  "SBIN",
  "TATAMOTORS",
  "BHARTIARTL",
];

const TIMEFRAME_PRESETS = [
  { label: "1Y", start: "2025-11-06", end: "2026-11-06" },
  { label: "3Y", start: "2023-11-06", end: "2026-11-06" },
  { label: "5Y", start: "2021-11-06", end: "2026-11-06" },
  { label: "Full Cycle (2020-2026)", start: "2020-01-01", end: "2026-11-06" },
];

export default function CompareTerminal() {
  const [symbols, setSymbols] = useState<string[]>(["TCS", "INFY", "HCLTECH"]);
  const [newSymbolInput, setNewSymbolInput] = useState<string>("");
  const [startDate, setStartDate] = useState<string>("2021-01-04");
  const [endDate, setEndDate] = useState<string>("2026-11-06");
  const [activePreset, setActivePreset] = useState<string>("Full Cycle (2020-2026)");

  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<MultiStockCompareResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const executeComparison = useCallback(
    async (syms: string[], start: string, end: string) => {
      if (syms.length === 0) return;
      setLoading(true);
      setError(null);
      try {
        const data = await runMultiStockComparison({
          symbols: syms,
          start_date: start,
          end_date: end,
          benchmark_symbol: "BENCHMARK",
        });
        setResult(data);
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err);
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Auto-run on mount with defaults
  useEffect(() => {
    executeComparison(symbols, startDate, endDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleAddSymbol = (sym: string) => {
    const cleaned = sym.trim().toUpperCase();
    if (!cleaned) return;
    if (symbols.includes(cleaned)) return;
    if (symbols.length >= 8) {
      alert("Maximum 8 symbols allowed in comparison.");
      return;
    }
    const updated = [...symbols, cleaned];
    setSymbols(updated);
    setNewSymbolInput("");
    executeComparison(updated, startDate, endDate);
  };

  const handleRemoveSymbol = (sym: string) => {
    if (symbols.length <= 1) {
      alert("At least 1 symbol required.");
      return;
    }
    const updated = symbols.filter((s) => s !== sym);
    setSymbols(updated);
    executeComparison(updated, startDate, endDate);
  };

  const handleSelectPreset = (preset: (typeof TIMEFRAME_PRESETS)[0]) => {
    setActivePreset(preset.label);
    setStartDate(preset.start);
    setEndDate(preset.end);
    executeComparison(symbols, preset.start, preset.end);
  };

  const handleCustomRun = () => {
    setActivePreset("Custom");
    executeComparison(symbols, startDate, endDate);
  };

  // Helper for correlation cell background color
  const getCorrelationColor = (val: number): string => {
    if (val >= 0.8) return "bg-emerald-500/20 text-emerald-300 font-bold border-emerald-500/30";
    if (val >= 0.5) return "bg-teal-500/15 text-teal-300 border-teal-500/20";
    if (val >= 0.2) return "bg-cyan-500/10 text-cyan-300 border-cyan-500/20";
    if (val >= 0) return "bg-slate-800/40 text-slate-300 border-slate-700/30";
    if (val >= -0.2) return "bg-amber-500/10 text-amber-300 border-amber-500/20";
    return "bg-rose-500/20 text-rose-300 font-bold border-rose-500/30";
  };

  return (
    <div className="flex flex-col space-y-6">
      {/* Control Banner */}
      <div className="p-5 rounded-2xl bg-slate-900/80 border border-slate-800 backdrop-blur-md shadow-xl flex flex-col space-y-4">
        {/* Top row: Symbol Chips + Input */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs uppercase font-mono tracking-wider text-slate-400 flex items-center gap-1.5 mr-1">
              <Layers className="w-3.5 h-3.5 text-cyan-400" />
              Active Assets:
            </span>
            {symbols.map((sym) => (
              <span
                key={sym}
                className="inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-slate-800/80 border border-cyan-500/30 text-cyan-300 font-mono text-xs font-semibold shadow-sm"
              >
                {sym}
                <button
                  onClick={() => handleRemoveSymbol(sym)}
                  className="hover:text-rose-400 transition-colors p-0.5 rounded"
                  title={`Remove ${sym}`}
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            ))}

            {/* Quick add input */}
            <div className="flex items-center space-x-1">
              <input
                type="text"
                placeholder="+ ADD SYMBOL"
                value={newSymbolInput}
                onChange={(e) => setNewSymbolInput(e.target.value.toUpperCase())}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    handleAddSymbol(newSymbolInput);
                  }
                }}
                className="w-28 px-2.5 py-1 text-xs font-mono bg-slate-950 border border-slate-700/80 rounded-lg text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-400"
              />
              <button
                onClick={() => handleAddSymbol(newSymbolInput)}
                disabled={!newSymbolInput.trim()}
                className="p-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 disabled:opacity-40 transition-colors"
                title="Add symbol"
              >
                <Plus className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Popular suggestion chips */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-[11px] font-mono text-slate-500">Suggested:</span>
            {POPULAR_SUGGESTIONS.filter((s) => !symbols.includes(s))
              .slice(0, 5)
              .map((s) => (
                <button
                  key={s}
                  onClick={() => handleAddSymbol(s)}
                  className="px-2 py-0.5 text-[11px] font-mono rounded bg-slate-800/50 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/40 transition-colors"
                >
                  +{s}
                </button>
              ))}
          </div>
        </div>

        {/* Bottom row: Timeframe presets & Date Pickers */}
        <div className="flex flex-wrap items-center justify-between gap-4 pt-3 border-t border-slate-800/80">
          <div className="flex items-center gap-2">
            <span className="text-xs uppercase font-mono tracking-wider text-slate-400 flex items-center gap-1.5 mr-1">
              <Sliders className="w-3.5 h-3.5 text-cyan-400" />
              Horizon:
            </span>
            <div className="flex items-center rounded-lg bg-slate-950 p-1 border border-slate-800">
              {TIMEFRAME_PRESETS.map((p) => (
                <button
                  key={p.label}
                  onClick={() => handleSelectPreset(p)}
                  className={`px-3 py-1 text-xs font-mono rounded-md transition-all ${
                    activePreset === p.label
                      ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/40 shadow-sm"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-3">
            <div className="flex items-center space-x-2 text-xs font-mono">
              <span className="text-slate-500">From:</span>
              <input
                type="date"
                value={startDate}
                onChange={(e) => setStartDate(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-cyan-400"
              />
              <span className="text-slate-500">To:</span>
              <input
                type="date"
                value={endDate}
                onChange={(e) => setEndDate(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-300 focus:outline-none focus:border-cyan-400"
              />
            </div>
            <button
              onClick={handleCustomRun}
              disabled={loading}
              className="px-4 py-1.5 rounded-lg bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold font-mono text-xs flex items-center gap-1.5 shadow-lg shadow-cyan-500/10 transition-all disabled:opacity-50"
            >
              {loading ? (
                <>
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                  Calculating...
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  Compare
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs font-mono flex items-center justify-between">
          <div className="flex items-center gap-2">
            <ShieldAlert className="w-4 h-4 text-rose-400 flex-shrink-0" />
            <span>{error}</span>
          </div>
          <button
            onClick={() => executeComparison(symbols, startDate, endDate)}
            className="px-2.5 py-1 rounded bg-rose-500/20 hover:bg-rose-500/30 text-rose-200 text-xs font-mono"
          >
            Retry
          </button>
        </div>
      )}

      {/* Main Multi-Line Normalized Chart */}
      {result && result.normalized_series && result.normalized_series.length > 0 && (
        <div className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <div className="flex items-center gap-2">
              <BarChart2 className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-semibold font-mono text-slate-200">
                Base-100 Performance Continuum
              </h3>
              <span className="text-[11px] font-mono text-slate-500">
                ({result.start_date} → {result.end_date} | {result.normalized_series.length} sessions)
              </span>
            </div>
            <div className="text-[11px] font-mono text-slate-400">
              Benchmark: <span className="text-slate-300 font-semibold">{result.benchmark_symbol}</span>
            </div>
          </div>

          <BacktestCompareChart
            normalizedSeries={result.normalized_series}
            symbols={result.symbols}
            benchmarkSymbol={result.benchmark_symbol}
          />
        </div>
      )}

      {/* Comparative Performance Table & Metric Cards */}
      {result && result.comparison_metrics && (
        <div className="space-y-4">
          <div className="flex items-center gap-2 px-1">
            <Sparkles className="w-4 h-4 text-amber-400" />
            <h3 className="text-sm font-semibold font-mono text-slate-200">
              Cross-Sectional Risk & Return Matrix
            </h3>
          </div>

          <div className="overflow-x-auto rounded-xl border border-slate-800 bg-slate-900/60 backdrop-blur-md">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-950/70 text-slate-400">
                  <th className="py-3 px-4 font-semibold uppercase tracking-wider">Asset / Instrument</th>
                  <th className="py-3 px-3 text-right font-semibold uppercase tracking-wider">Total Return</th>
                  <th className="py-3 px-3 text-right font-semibold uppercase tracking-wider">CAGR</th>
                  <th className="py-3 px-3 text-right font-semibold uppercase tracking-wider">Volatility (Ann.)</th>
                  <th className="py-3 px-3 text-right font-semibold uppercase tracking-wider">Sharpe Ratio</th>
                  <th className="py-3 px-3 text-right font-semibold uppercase tracking-wider">Max Drawdown</th>
                  <th className="py-3 px-3 text-right font-semibold uppercase tracking-wider">Beta (to Bench)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60">
                {Object.values(result.comparison_metrics).map((m: StockComparisonMetric) => {
                  const isBench = m.symbol === result.benchmark_symbol;
                  return (
                    <tr
                      key={m.symbol}
                      className={`hover:bg-slate-800/40 transition-colors ${
                        isBench ? "bg-slate-950/40 font-semibold text-slate-300" : ""
                      }`}
                    >
                      <td className="py-3 px-4 flex items-center gap-2">
                        <span
                          className={`w-2 h-2 rounded-full ${
                            isBench ? "bg-slate-400" : "bg-cyan-400"
                          }`}
                        />
                        <span className={isBench ? "text-slate-400" : "text-slate-100 font-bold"}>
                          {m.symbol}
                        </span>
                        {isBench && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded bg-slate-800 border border-slate-700 text-slate-400">
                            BENCHMARK
                          </span>
                        )}
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-semibold ${
                          m.total_return_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {m.total_return_pct >= 0 ? "+" : ""}
                        {m.total_return_pct.toFixed(2)}%
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-semibold ${
                          m.cagr_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                        }`}
                      >
                        {m.cagr_pct >= 0 ? "+" : ""}
                        {m.cagr_pct.toFixed(2)}%
                      </td>
                      <td className="py-3 px-3 text-right text-slate-300">
                        {m.annualized_volatility_pct.toFixed(2)}%
                      </td>
                      <td
                        className={`py-3 px-3 text-right font-semibold ${
                          m.sharpe_ratio >= 1.0
                            ? "text-emerald-400"
                            : m.sharpe_ratio >= 0.5
                            ? "text-cyan-400"
                            : m.sharpe_ratio >= 0
                            ? "text-slate-300"
                            : "text-rose-400"
                        }`}
                      >
                        {m.sharpe_ratio.toFixed(2)}
                      </td>
                      <td className="py-3 px-3 text-right text-rose-400 font-semibold">
                        {m.max_drawdown_pct.toFixed(2)}%
                      </td>
                      <td className="py-3 px-3 text-right text-slate-300 font-mono">
                        {m.beta_to_bench.toFixed(2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Pairwise Pearson Correlation Matrix & Radar Factor Attributes */}
      {result && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* 1. Correlation Matrix Heatmap */}
          {result.correlation_matrix && (
            <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 backdrop-blur-md flex flex-col space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Activity className="w-4 h-4 text-cyan-400" />
                  <h4 className="text-sm font-semibold font-mono text-slate-200">
                    Pairwise Correlation Matrix
                  </h4>
                </div>
                <span className="text-[10px] font-mono text-slate-500">Daily Log-Returns</span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-center text-xs font-mono border-collapse">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="p-2 text-left font-semibold">Asset</th>
                      {Object.keys(result.correlation_matrix).map((col) => (
                        <th key={col} className="p-2 font-semibold">
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/40">
                    {Object.entries(result.correlation_matrix).map(([rowKey, rowVals]) => (
                      <tr key={rowKey}>
                        <td className="p-2 text-left font-bold text-slate-300 bg-slate-950/40">
                          {rowKey}
                        </td>
                        {Object.keys(result.correlation_matrix).map((colKey) => {
                          const val = rowVals[colKey] ?? 0;
                          return (
                            <td key={colKey} className="p-1">
                              <div
                                className={`py-1.5 px-2 rounded border text-xs font-mono transition-all ${getCorrelationColor(
                                  val
                                )}`}
                              >
                                {val.toFixed(2)}
                              </div>
                            </td>
                          );
                        })}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* 2. Factor Radar Breakdown */}
          {result.radar_scores && (
            <div className="p-5 rounded-2xl bg-slate-900/70 border border-slate-800 backdrop-blur-md flex flex-col space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Percent className="w-4 h-4 text-emerald-400" />
                  <h4 className="text-sm font-semibold font-mono text-slate-200">
                    Quant Factor Quintile Profiles
                  </h4>
                </div>
                <span className="text-[10px] font-mono text-slate-500">Normalized [0–100]</span>
              </div>

              <div className="space-y-4 pt-1">
                {result.symbols.map((sym) => {
                  const scores = result.radar_scores[sym] || {
                    quality: 50,
                    momentum: 50,
                    trend: 50,
                    volatility: 50,
                  };
                  return (
                    <div
                      key={sym}
                      className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80 flex flex-col space-y-2"
                    >
                      <div className="flex items-center justify-between text-xs font-mono">
                        <span className="font-bold text-slate-200">{sym}</span>
                        <div className="flex items-center space-x-3 text-[11px] text-slate-400">
                          <span>
                            Q: <span className="text-cyan-400">{scores.quality.toFixed(0)}</span>
                          </span>
                          <span>
                            M: <span className="text-emerald-400">{scores.momentum.toFixed(0)}</span>
                          </span>
                          <span>
                            T: <span className="text-amber-400">{scores.trend.toFixed(0)}</span>
                          </span>
                          <span>
                            V: <span className="text-purple-400">{scores.volatility.toFixed(0)}</span>
                          </span>
                        </div>
                      </div>

                      {/* Mini stacked/segmented bar */}
                      <div className="grid grid-cols-4 gap-1.5 text-[10px] font-mono">
                        <div className="flex flex-col">
                          <span className="text-slate-500 text-[9px] mb-0.5">Quality</span>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-cyan-400 h-full rounded-full"
                              style={{ width: `${Math.min(100, Math.max(0, scores.quality))}%` }}
                            />
                          </div>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-slate-500 text-[9px] mb-0.5">Momentum</span>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-emerald-400 h-full rounded-full"
                              style={{ width: `${Math.min(100, Math.max(0, scores.momentum))}%` }}
                            />
                          </div>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-slate-500 text-[9px] mb-0.5">Trend</span>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-amber-400 h-full rounded-full"
                              style={{ width: `${Math.min(100, Math.max(0, scores.trend))}%` }}
                            />
                          </div>
                        </div>
                        <div className="flex flex-col">
                          <span className="text-slate-500 text-[9px] mb-0.5">Low-Vol</span>
                          <div className="w-full bg-slate-800 rounded-full h-1.5 overflow-hidden">
                            <div
                              className="bg-purple-400 h-full rounded-full"
                              style={{ width: `${Math.min(100, Math.max(0, scores.volatility))}%` }}
                            />
                          </div>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
