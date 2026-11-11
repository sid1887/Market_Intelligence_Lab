"use client";

import React, { useState, useEffect, useCallback } from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import { BentoCard } from "@/components/ui/BentoCard";
import { AnimatedTabs } from "@/components/ui/AnimatedTabs";
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
    <div className="min-h-screen bg-[#040609] text-slate-100 flex flex-col font-sans relative selection:bg-cyan-500/20 selection:text-cyan-200">
      {/* Ambient background lighting */}
      <div className="fixed inset-0 pointer-events-none z-0">
        <div className="absolute top-0 right-1/4 w-[600px] h-[400px] bg-cyan-500/[0.03] rounded-full blur-[140px]" />
        <div className="absolute top-1/3 left-1/4 w-[500px] h-[500px] bg-emerald-500/[0.025] rounded-full blur-[160px]" />
      </div>

      <Navbar />

      <main className="relative z-10 flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-white/[0.08]">
          <div>
            <div className="flex items-center space-x-3.5">
              <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 border border-emerald-500/25 flex items-center justify-center text-emerald-400 shadow-[0_0_20px_rgba(16,185,129,0.15)]">
                <Activity className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
                  Institutional Backtesting & Analytics
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 font-mono shadow-[0_0_10px_rgba(6,182,212,0.2)]">
                    Phase 9.0 + Advanced Regimes
                  </span>
                </h1>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  Point-in-Time Walk-Forward Portfolio Simulation • Turnover Hysteresis • Dynamic Cash Gating • Cross-Sectional Multi-Stock Comparison
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2 text-xs font-mono text-slate-400 px-3.5 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.06] tabular-nums">
            <Calendar className="w-4 h-4 text-cyan-400" />
            <span>Universe: {presets?.date_bounds.start_date || "2020-01-01"} to {presets?.date_bounds.end_date || "2026-11-06"}</span>
          </div>
        </div>

        {/* Sub-Tab Navigation Switcher with micro-interactions */}
        <AnimatedTabs<"simulation" | "compare">
          tabs={[
            {
              id: "simulation",
              label: "Portfolio Simulation Engine",
              icon: <Activity className="w-4 h-4 text-cyan-400" />,
            },
            {
              id: "compare",
              label: "Multi-Asset Cross-Sectional Comparison",
              icon: <BarChart2 className="w-4 h-4 text-emerald-400" />,
            },
          ]}
          activeTab={activeTab}
          setActiveTab={(tab) => setActiveTab(tab)}
          layoutId="active-backtest-tab"
        />

        {activeTab === "compare" ? (
          <CompareTerminal />
        ) : (
          <>
        {/* Control Bar */}
        <div className="p-5 rounded-2xl bg-[#080c14]/90 backdrop-blur-2xl border border-white/[0.08] shadow-[0_12px_40px_rgba(0,0,0,0.6)] space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-6 gap-3.5 text-xs">
            {/* Strategy Mode */}
            <div className="lg:col-span-2 space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                <span>Strategy Regime</span>
              </label>
              <select
                value={strategyMode}
                onChange={(e) => setStrategyMode(e.target.value)}
                className="w-full bg-[#050810] border border-white/[0.1] rounded-xl px-3.5 py-2.5 text-slate-100 font-mono focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(6,182,212,0.2)]"
              >
                <option value="BLENDED_20D_60D">Institutional Blended (62.5% Tactical + 37.5% Trend)</option>
                <option value="TACTICAL_20D">Tactical Swing (100% 20D Champion)</option>
                <option value="TREND_60D">Structural Trend (100% 60D Champion)</option>
              </select>
            </div>

            {/* Top N Basket Size */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                <Filter className="w-3.5 h-3.5 text-emerald-400" />
                <span>Basket Size</span>
              </label>
              <select
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className="w-full bg-[#050810] border border-white/[0.1] rounded-xl px-3.5 py-2.5 text-slate-100 font-mono focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(6,182,212,0.2)]"
              >
                <option value={10}>Top 10 Equities</option>
                <option value={15}>Top 15 Equities</option>
                <option value={20}>Top 20 Equities</option>
              </select>
            </div>

            {/* Rebalance Frequency */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                <span>Rebalance Cadence</span>
              </label>
              <select
                value={rebalanceDays}
                onChange={(e) => setRebalanceDays(Number(e.target.value))}
                className="w-full bg-[#050810] border border-white/[0.1] rounded-xl px-3.5 py-2.5 text-slate-100 font-mono focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(6,182,212,0.2)]"
              >
                <option value={10}>10 Days (Bi-Weekly)</option>
                <option value={20}>20 Days (Monthly)</option>
                <option value={60}>60 Days (Quarterly)</option>
              </select>
            </div>

            {/* Initial Capital */}
            <div className="space-y-1.5">
              <label className="text-slate-400 font-mono flex items-center gap-1.5 uppercase tracking-wider text-[11px]">
                <DollarSign className="w-3.5 h-3.5 text-blue-400" />
                <span>Virtual Capital</span>
              </label>
              <input
                type="number"
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                step={100000}
                className="w-full bg-[#050810] border border-white/[0.1] rounded-xl px-3.5 py-2.5 text-slate-100 font-mono focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(6,182,212,0.2)] tabular-nums"
              />
            </div>

            {/* Run Button */}
            <div className="flex items-end">
              <button
                onClick={handleRunBacktest}
                disabled={loading}
                className="w-full h-[42px] px-4 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-white font-mono text-xs font-semibold shadow-[0_0_20px_rgba(16,185,129,0.3)] border border-emerald-400/40 flex items-center justify-center gap-2 transition-all duration-150 active:scale-[0.98] disabled:opacity-50 disabled:cursor-not-allowed"
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
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/40 text-rose-300 text-xs flex items-center gap-3 shadow-[0_4px_20px_rgba(244,63,94,0.15)]">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {/* KPI Tearsheet Grid (Standardized Bento Cards) */}
        {metrics && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 sm:gap-5">
            <BentoCard
              title="Final Portfolio NAV"
              value={formatINR(metrics.final_nav)}
              delta={`${Math.abs(metrics.total_return_pct).toFixed(2)}%`}
              isPositive={metrics.total_return_pct >= 0}
              subLabel="Total Return"
              icon={<PieChart className="w-4 h-4 text-cyan-400" />}
              delay={0.05}
            />
            <BentoCard
              title="Benchmark & Alpha"
              value={`${metrics.alpha_pct >= 0 ? "+" : ""}${metrics.alpha_pct.toFixed(2)}%`}
              delta={`Nifty: ${metrics.benchmark_return_pct.toFixed(2)}%`}
              isPositive={metrics.alpha_pct >= 0}
              subLabel="Alpha Spread"
              icon={<Percent className="w-4 h-4 text-amber-400" />}
              delay={0.1}
            />
            <BentoCard
              title="Risk-Adjusted Return"
              value={`Sharpe: ${metrics.sharpe_ratio.toFixed(2)}`}
              badge={`Sortino ${metrics.sortino_ratio.toFixed(2)}`}
              subLabel={`Calmar: ${metrics.calmar_ratio.toFixed(2)}`}
              icon={<ShieldCheck className="w-4 h-4 text-emerald-400" />}
              delay={0.15}
            />
            <BentoCard
              title="Max Drawdown & Vol"
              value={`-${metrics.max_drawdown_pct.toFixed(2)}%`}
              delta={`Vol ${metrics.annualized_volatility_pct.toFixed(1)}%`}
              isPositive={false}
              subLabel={`Win ${metrics.win_rate_pct.toFixed(1)}%`}
              icon={<ShieldAlert className="w-4 h-4 text-rose-400" />}
              delay={0.2}
            />
            <BentoCard
              title="CAGR (Ann. Return)"
              value={`${metrics.cagr_pct.toFixed(2)}%`}
              badge="Compounded"
              subLabel="Annual Growth Rate"
              icon={<TrendingUp className="w-4 h-4 text-blue-400" />}
              delay={0.25}
            />
            <BentoCard
              title="Total Friction Paid"
              value={formatINR(metrics.total_friction_paid)}
              badge={`Drag ${metrics.friction_drag_bps.toFixed(1)} bps`}
              subLabel="of initial capital"
              icon={<DollarSign className="w-4 h-4 text-indigo-400" />}
              delay={0.3}
            />
            <BentoCard
              title="Simulation Activity"
              value={`${metrics.total_rebalances} Rebalances`}
              badge={`${metrics.total_trades} orders`}
              subLabel={`${metrics.trading_sessions} sessions`}
              icon={<Clock className="w-4 h-4 text-cyan-400" />}
              delay={0.35}
            />
            <BentoCard
              title="Regime Specification"
              value={metrics.strategy_mode}
              badge={`Top ${metrics.top_n}`}
              subLabel={`Cadence ${metrics.rebalance_every_n_days}d`}
              icon={<Layers className="w-4 h-4 text-emerald-400" />}
              delay={0.4}
            />
          </div>
        )}

        {/* Dual Lightweight Charts (Equity Curve + Underwater Drawdown) */}
        {result?.equity_curve && result.equity_curve.length > 0 && (
          <div className="bg-[#080c14]/85 backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-5 shadow-[0_12px_40px_rgba(0,0,0,0.6)] space-y-3">
            <div className="flex items-center justify-between border-b border-white/[0.08] pb-3 mb-2">
              <div className="flex items-center space-x-2.5">
                <Activity className="w-4 h-4 text-cyan-400" />
                <h2 className="text-sm font-semibold text-white tracking-wide">
                  Historical Mark-to-Market Equity & Underwater Drawdown Visualizer
                </h2>
              </div>
              <div className="flex items-center gap-4 text-xs font-mono">
                <span className="flex items-center gap-1.5 text-emerald-400 font-medium">
                  <span className="w-3 h-0.5 bg-emerald-400 rounded-full shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
                  Strategy NAV
                </span>
                <span className="flex items-center gap-1.5 text-slate-400">
                  <span className="w-3 h-0.5 bg-slate-400 border-dashed rounded-full" />
                  NIFTY 50 Benchmark
                </span>
                <span className="flex items-center gap-1.5 text-rose-400 font-medium">
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
          <div className="bg-[#080c14]/70 border border-white/[0.08] rounded-2xl p-12 text-center space-y-4 backdrop-blur-xl">
            <div className="w-12 h-12 rounded-2xl bg-white/[0.04] border border-white/[0.08] text-cyan-400 flex items-center justify-center mx-auto shadow-[0_0_20px_rgba(6,182,212,0.15)]">
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
          <div className="bg-[#080c14]/85 backdrop-blur-2xl border border-white/[0.08] rounded-2xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
            <div className="p-5 border-b border-white/[0.08] flex items-center justify-between">
              <div className="flex items-center space-x-2.5">
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
                <thead className="bg-[#050810]/80 border-b border-white/[0.08] font-mono text-slate-400 text-[11px] uppercase tracking-wider">
                  <tr>
                    <th className="py-3 px-5">Cycle Date</th>
                    <th className="py-3 px-5 text-right">NAV Before</th>
                    <th className="py-3 px-5 text-right">NAV After</th>
                    <th className="py-3 px-5 text-right">Turnover %</th>
                    <th className="py-3 px-5 text-right">Orders Executed</th>
                    <th className="py-3 px-5 text-right">Friction Paid</th>
                    <th className="py-3 px-5">Top 5 Target Holdings</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04] font-mono">
                  {result.rebalance_log.map((reb, idx) => (
                    <tr key={idx} className="hover:bg-white/[0.03] transition-colors">
                      <td className="py-3 px-5 font-semibold text-slate-300 tabular-nums">
                        {reb.date}
                      </td>
                      <td className="py-3 px-5 text-right text-slate-400 tabular-nums">
                        {formatINR(reb.nav_before)}
                      </td>
                      <td className="py-3 px-5 text-right text-slate-200 font-semibold tabular-nums">
                        {formatINR(reb.nav_after)}
                      </td>
                      <td className="py-3 px-5 text-right text-cyan-300 tabular-nums font-semibold">
                        {reb.turnover_pct.toFixed(2)}%
                      </td>
                      <td className="py-3 px-5 text-right text-slate-300 tabular-nums">
                        {reb.orders_count}
                      </td>
                      <td className="py-3 px-5 text-right text-amber-400 font-medium tabular-nums">
                        {formatINR(reb.friction_paid)}
                      </td>
                      <td className="py-3 px-5">
                        <div className="flex flex-wrap items-center gap-1.5">
                          {reb.top_holdings.map((sym) => (
                            <Link
                              key={sym}
                              href={`/stocks/${sym}`}
                              className="px-2 py-0.5 rounded-md text-[10px] bg-white/[0.04] hover:bg-cyan-500/10 text-cyan-300 border border-white/[0.08] hover:border-cyan-500/40 transition-all"
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
