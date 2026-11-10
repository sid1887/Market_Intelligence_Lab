"use client";

import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  fetchBacktestPresets,
  runPortfolioBacktest,
  BacktestPresetsResponse,
  PortfolioBacktestResponse,
  BacktestSummaryMetrics
} from "@/lib/api";
import {
  Play,
  TrendingUp,
  TrendingDown,
  ShieldAlert,
  ShieldCheck,
  Percent,
  Calendar,
  Layers,
  Clock,
  DollarSign,
  PieChart,
  Activity,
  AlertCircle,
  Loader2,
  Filter,
  BarChart2
} from "lucide-react";
import CompareTerminal from "@/components/CompareTerminal";

// SSR-Isolated lightweight-charts visualizer
const BacktestChart = dynamic(() => import("@/components/BacktestChart"), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] w-full flex items-center justify-center bg-slate-900/60 rounded-xl border border-slate-800 text-xs font-mono text-slate-500">
      <Loader2 className="w-5 h-5 animate-spin text-cyan-400 mr-2" />
      Initializing Lightweight Charts Canvas...
    </div>
  ),
});

export default function BacktestPage() {
  const [activeTab, setActiveTab] = useState<"simulation" | "compare">("simulation");
  const [presets, setPresets] = useState<BacktestPresetsResponse | null>(null);
  const [strategyMode, setStrategyMode] = useState<string>("BLENDED_20D_60D");
  const [topN, setTopN] = useState<number>(15);
  const [rebalanceDays, setRebalanceDays] = useState<number>(20);
  const [startDate, setStartDate] = useState<string>("2024-10-21");
  const [endDate, setEndDate] = useState<string>("2026-11-06");
  const [initialCapital, setInitialCapital] = useState<number>(1000000);

  const [loading, setLoading] = useState<boolean>(false);
  const [result, setResult] = useState<PortfolioBacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load presets on mount
  useEffect(() => {
    async function loadPresets() {
      try {
        const data = await fetchBacktestPresets();
        setPresets(data);
        if (data.default_config) {
          setStrategyMode(data.default_config.strategy_mode);
          setTopN(data.default_config.top_n);
          setRebalanceDays(data.default_config.rebalance_every_n_days);
          setStartDate(data.default_config.start_date || "2024-10-21");
          setEndDate(data.default_config.end_date || "2026-11-06");
          setInitialCapital(data.default_config.initial_capital || 1000000);
        }
      } catch (err) {
        console.warn("Could not fetch backtest presets:", err);
      }
    }
    loadPresets();
  }, []);

  const handleRunBacktest = useCallback(async () => {
    if (loading) return;
    setLoading(true);
    setError(null);
    try {
      const res = await runPortfolioBacktest({
        strategy_mode: strategyMode,
        top_n: topN,
        rebalance_cadence: rebalanceDays,
        rebalance_every_n_days: rebalanceDays,
        start_date: startDate,
        end_date: endDate,
        initial_capital: initialCapital,
      });
      setResult(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Backtest simulation failed: ${msg}`);
    } finally {
      setLoading(false);
    }
  }, [strategyMode, topN, rebalanceDays, startDate, endDate, initialCapital, loading]);

  const formatINR = (val: number | null | undefined): string => {
    if (val === null || val === undefined || isNaN(val)) return "₹0.00";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  const metrics: BacktestSummaryMetrics | undefined = result?.summary_metrics;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar />

      <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400">
                <Activity className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                  Institutional Backtesting & Analytics
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 font-mono text-cyan-400">
                    Phase 9.0 + Advanced Regimes
                  </span>
                </h1>
                <p className="text-xs text-slate-400 font-mono">
                  Point-in-Time Walk-Forward Portfolio Simulation • Turnover Hysteresis • Dynamic Cash Gating • Cross-Sectional Multi-Stock Comparison
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-400">
            <Calendar className="w-4 h-4 text-cyan-400" />
            <span>Multi-Stock Universe: {presets?.date_bounds.start_date || "2020-01-01"} to {presets?.date_bounds.end_date || "2026-11-06"}</span>
          </div>
        </div>

        {/* Sub-Tab Navigation Switcher with micro-interactions */}
        <div className="flex items-center space-x-2 border-b border-slate-800/80 pb-2">
          <button
            onClick={() => setActiveTab("simulation")}
            className={`px-4 py-2 text-xs font-mono rounded-xl transition-all duration-150 active:scale-[0.98] flex items-center gap-2 ${
              activeTab === "simulation"
                ? "bg-slate-800 text-cyan-300 font-semibold border border-cyan-500/40 shadow-lg shadow-cyan-950/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
            }`}
          >
            <Activity className="w-4 h-4" />
            Portfolio Simulation Engine
          </button>
          <button
            onClick={() => setActiveTab("compare")}
            className={`px-4 py-2 text-xs font-mono rounded-xl transition-all duration-150 active:scale-[0.98] flex items-center gap-2 ${
              activeTab === "compare"
                ? "bg-slate-800 text-cyan-300 font-semibold border border-cyan-500/40 shadow-lg shadow-cyan-950/20"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
            }`}
          >
            <BarChart2 className="w-4 h-4" />
            Multi-Asset Cross-Sectional Comparison
          </button>
        </div>

        {activeTab === "compare" ? (
          <CompareTerminal />
        ) : (
          <>
        {/* Control Bar */}
        <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-lg space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3 text-xs">
            {/* Strategy Mode */}
            <div className="lg:col-span-2 space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                <span>Strategy Regime</span>
              </label>
              <select
                value={strategyMode}
                onChange={(e) => setStrategyMode(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-cyan-500"
              >
                <option value="BLENDED_20D_60D">Institutional Blended (62.5% Tactical + 37.5% Trend)</option>
                <option value="TACTICAL_20D">Tactical Swing (100% 20D Champion)</option>
                <option value="TREND_60D">Structural Trend (100% 60D Champion)</option>
              </select>
            </div>

            {/* Top N Basket Size */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5">
                <Filter className="w-3.5 h-3.5 text-emerald-400" />
                <span>Basket Size</span>
              </label>
              <select
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-cyan-500"
              >
                <option value={10}>Top 10 Equities</option>
                <option value={15}>Top 15 Equities</option>
                <option value={20}>Top 20 Equities</option>
              </select>
            </div>

            {/* Rebalance Frequency */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                <span>Rebalance Cadence</span>
              </label>
              <select
                value={rebalanceDays}
                onChange={(e) => setRebalanceDays(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-slate-100 font-mono focus:outline-none focus:border-cyan-500"
              >
                <option value={10}>10 Days (Bi-Weekly)</option>
                <option value={20}>20 Days (Monthly)</option>
                <option value={60}>60 Days (Quarterly)</option>
              </select>
            </div>

            {/* Initial Capital */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5">
                <DollarSign className="w-3.5 h-3.5 text-blue-400" />
                <span>Virtual Capital</span>
              </label>
              <input
                type="number"
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                step={100000}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-1.5 text-slate-100 font-mono focus:outline-none focus:border-cyan-500"
              />
            </div>

            {/* Run Button */}
            <div className="flex items-end">
              <button
                onClick={handleRunBacktest}
                disabled={loading}
                className="w-full h-[38px] px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-mono font-medium shadow-lg shadow-emerald-950/40 border border-emerald-500 flex items-center justify-center gap-2 transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {loading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Simulating...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-4 h-4 fill-current" />
                    <span>Run Simulation</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-3">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* KPI Tearsheet Grid (Standardized Bento Cards) */}
        {metrics && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
            {/* 1. Final NAV & Total Return */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Final Portfolio NAV</span>
                  <span className="text-slate-400 group-hover:text-cyan-400 transition-colors duration-200">
                    <PieChart className="w-4 h-4 text-cyan-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-white my-1.5">
                  {formatINR(metrics.final_nav)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  {metrics.total_return_pct >= 0 ? (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-emerald-950/80 border border-emerald-800 text-emerald-300">
                      <TrendingUp className="w-3 h-3 text-emerald-400" />
                      +{metrics.total_return_pct.toFixed(2)}%
                    </span>
                  ) : (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-rose-950/80 border border-rose-800 text-rose-300">
                      <TrendingDown className="w-3 h-3 text-rose-400" />
                      {metrics.total_return_pct.toFixed(2)}%
                    </span>
                  )}
                  <span className="text-slate-500 text-[11px]">Total Return</span>
                </div>
              </div>
            </div>

            {/* 2. Benchmark Return & Alpha */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Benchmark & Alpha</span>
                  <span className="text-slate-400 group-hover:text-amber-400 transition-colors duration-200">
                    <Percent className="w-4 h-4 text-amber-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-amber-300 my-1.5">
                  {metrics.alpha_pct >= 0 ? "+" : ""}{metrics.alpha_pct.toFixed(2)}%
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-amber-950/80 border border-amber-800/80 text-amber-300">
                    Nifty: {metrics.benchmark_return_pct.toFixed(2)}%
                  </span>
                  <span className="text-cyan-400 text-[11px] font-semibold">Alpha Spread</span>
                </div>
              </div>
            </div>

            {/* 3. Sharpe & Sortino */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Risk-Adjusted Return</span>
                  <span className="text-slate-400 group-hover:text-emerald-400 transition-colors duration-200">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-emerald-400 my-1.5">
                  Sharpe: {metrics.sharpe_ratio.toFixed(2)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-emerald-950/80 border border-emerald-800/80 text-emerald-300">
                    Sortino {metrics.sortino_ratio.toFixed(2)}
                  </span>
                  <span className="text-slate-400 text-[11px]">Calmar: {metrics.calmar_ratio.toFixed(2)}</span>
                </div>
              </div>
            </div>

            {/* 4. Drawdown & Volatility */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Max Drawdown & Vol</span>
                  <span className="text-slate-400 group-hover:text-rose-400 transition-colors duration-200">
                    <ShieldAlert className="w-4 h-4 text-rose-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-rose-400 my-1.5">
                  -{metrics.max_drawdown_pct.toFixed(2)}%
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-rose-950/80 border border-rose-800/80 text-rose-300">
                    Vol {metrics.annualized_volatility_pct.toFixed(1)}%
                  </span>
                  <span className="text-slate-400 text-[11px]">Win {metrics.win_rate_pct.toFixed(1)}%</span>
                </div>
              </div>
            </div>

            {/* 5. Annualized Return (CAGR) */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">CAGR (Ann. Return)</span>
                  <span className="text-slate-400 group-hover:text-blue-400 transition-colors duration-200">
                    <TrendingUp className="w-4 h-4 text-blue-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-blue-300 my-1.5">
                  {metrics.cagr_pct.toFixed(2)}%
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-blue-950/80 border border-blue-800/80 text-blue-300">
                    Compounded
                  </span>
                  <span className="text-slate-500 text-[11px]">Annual Growth Rate</span>
                </div>
              </div>
            </div>

            {/* 6. Total Friction Drag */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Total Friction Paid</span>
                  <span className="text-slate-400 group-hover:text-indigo-400 transition-colors duration-200">
                    <DollarSign className="w-4 h-4 text-indigo-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-indigo-300 my-1.5">
                  {formatINR(metrics.total_friction_paid)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-indigo-950/80 border border-indigo-800/80 text-indigo-300">
                    Drag {metrics.friction_drag_bps.toFixed(1)} bps
                  </span>
                  <span className="text-slate-500 text-[11px]">of initial capital</span>
                </div>
              </div>
            </div>

            {/* 7. Rebalances & Fills */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Simulation Activity</span>
                  <span className="text-slate-400 group-hover:text-cyan-400 transition-colors duration-200">
                    <Clock className="w-4 h-4 text-cyan-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-slate-200 my-1.5">
                  {metrics.total_rebalances} Rebalances
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-slate-800 text-slate-300">
                    {metrics.total_trades} orders
                  </span>
                  <span className="text-slate-500 text-[11px]">{metrics.trading_sessions} sessions</span>
                </div>
              </div>
            </div>

            {/* 8. Active Configuration */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Regime Specification</span>
                  <span className="text-slate-400 group-hover:text-emerald-400 transition-colors duration-200">
                    <Layers className="w-4 h-4 text-emerald-400" />
                  </span>
                </div>
                <div className="font-mono text-lg sm:text-xl font-bold tracking-tight text-emerald-300 my-1.5 truncate">
                  {metrics.strategy_mode}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-emerald-950/80 border border-emerald-800/80 text-emerald-300">
                    Top {metrics.top_n}
                  </span>
                  <span className="text-slate-500 text-[11px]">Cadence {metrics.rebalance_every_n_days}d</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Dual Lightweight Charts (Equity Curve + Underwater Drawdown) */}
        {result?.equity_curve && result.equity_curve.length > 0 && (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl p-4 shadow-lg space-y-2">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3 mb-2">
              <div className="flex items-center space-x-2">
                <Activity className="w-4 h-4 text-cyan-400" />
                <h2 className="text-sm font-semibold text-white tracking-wide">
                  Historical Mark-to-Market Equity & Underwater Drawdown Visualizer
                </h2>
              </div>
              <div className="flex items-center gap-4 text-xs font-mono">
                <span className="flex items-center gap-1.5 text-emerald-400">
                  <span className="w-3 h-0.5 bg-emerald-400 rounded-full" />
                  Strategy NAV
                </span>
                <span className="flex items-center gap-1.5 text-slate-400">
                  <span className="w-3 h-0.5 bg-slate-400 border-dashed rounded-full" />
                  NIFTY 50 Benchmark
                </span>
                <span className="flex items-center gap-1.5 text-rose-400">
                  <span className="w-2.5 h-2.5 bg-rose-500/40 border border-rose-500 rounded-sm" />
                  Underwater DD %
                </span>
              </div>
            </div>

            <BacktestChart data={result.equity_curve} initialCapital={initialCapital} />
          </div>
        )}

        {/* Empty State when no run performed yet */}
        {!result && !loading && (
          <div className="bg-slate-900/40 border border-slate-800/60 rounded-xl p-12 text-center space-y-4">
            <div className="w-12 h-12 rounded-full bg-slate-800/80 text-cyan-400 flex items-center justify-center mx-auto">
              <Activity className="w-6 h-6" />
            </div>
            <h2 className="text-base font-semibold text-white">Systematic Walk-Forward Backtester Ready</h2>
            <p className="text-xs text-slate-400 max-w-lg mx-auto font-mono">
              Configure strategy parameters in the control bar above and click &quot;Run Simulation&quot; to compute point-in-time multi-horizon rebalancing across authentic exchange sessions with statutory Indian friction.
            </p>
          </div>
        )}

        {/* Rebalance Audit Log Table */}
        {result?.rebalance_log && result.rebalance_log.length > 0 && (
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl overflow-hidden shadow-lg">
            <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
              <div className="flex items-center space-x-2">
                <Clock className="w-4 h-4 text-amber-400" />
                <h2 className="text-sm font-semibold text-white tracking-wide">
                  Historical Rebalance Audit Log ({result.rebalance_log.length} Rebalance Cycles)
                </h2>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Institutional Rebalance Ledger
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 border-b border-slate-800 font-mono text-slate-400">
                  <tr>
                    <th className="py-2.5 px-4">Cycle Date</th>
                    <th className="py-2.5 px-4 text-right">NAV Before</th>
                    <th className="py-2.5 px-4 text-right">NAV After</th>
                    <th className="py-2.5 px-4 text-right">Turnover %</th>
                    <th className="py-2.5 px-4 text-right">Orders Executed</th>
                    <th className="py-2.5 px-4 text-right">Friction Paid</th>
                    <th className="py-2.5 px-4">Top 5 Target Holdings</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50 font-mono">
                  {result.rebalance_log.map((reb, idx) => (
                    <tr key={idx} className="hover:bg-slate-800/30 transition-colors">
                      <td className="py-2.5 px-4 font-semibold text-slate-300">
                        {reb.date}
                      </td>
                      <td className="py-2.5 px-4 text-right text-slate-400">
                        {formatINR(reb.nav_before)}
                      </td>
                      <td className="py-2.5 px-4 text-right text-slate-200 font-semibold">
                        {formatINR(reb.nav_after)}
                      </td>
                      <td className="py-2.5 px-4 text-right text-cyan-300">
                        {reb.turnover_pct.toFixed(2)}%
                      </td>
                      <td className="py-2.5 px-4 text-right text-slate-300">
                        {reb.orders_count}
                      </td>
                      <td className="py-2.5 px-4 text-right text-amber-400 font-medium">
                        {formatINR(reb.friction_paid)}
                      </td>
                      <td className="py-2.5 px-4">
                        <div className="flex flex-wrap items-center gap-1">
                          {reb.top_holdings.map((sym) => (
                            <Link
                              key={sym}
                              href={`/stocks/${sym}`}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-slate-800 hover:bg-slate-700 text-cyan-400 border border-slate-700 hover:border-cyan-500 transition-colors"
                            >
                              {sym}
                            </Link>
                          ))}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
          </>
        )}
      </main>
    </div>
  );
}
