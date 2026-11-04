"use client";

import React, { useState, useEffect, useCallback } from "react";
import Navbar from "@/components/Navbar";
import BacktestChart, { EquityCurvePoint } from "@/components/BacktestChart";
import {
  Play,
  Sliders,
  TrendingUp,
  TrendingDown,
  Receipt,
  ChevronDown,
  ChevronUp,
  AlertTriangle,
  Loader2,
  BarChart3,
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

interface BacktestMetrics {
  initial_value: number;
  final_value: number;
  total_return_pct: number;
  cagr_pct: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
  mdd_duration_days: number;
  alpha_pct: number;
  beta: number;
  win_rate_pct: number;
  turnover_pct: number;
  total_friction_inr: number;
  stt_paid_inr: number;
  dp_charges_paid_inr: number;
  turnover_charges_paid_inr: number;
  slippage_cost_inr: number;
}

interface BenchmarkMetrics {
  initial_value: number;
  final_value: number;
  total_return_pct: number;
  cagr_pct: number;
  annualized_volatility_pct: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown_pct: number;
}

interface RebalanceStock {
  symbol: string;
  shares: number;
  price: number;
  position_value: number;
  weight_pct: number;
}

interface RebalanceTrade {
  symbol: string;
  shares: number;
  exec_price: number;
  gross_value: number;
  stt?: number;
  dp_charge?: number;
}

interface RebalanceEvent {
  rebalance_date: string;
  execution_date: string;
  portfolio_value: number;
  cash_balance: number;
  friction_inr: number;
  stt_inr: number;
  dp_charges_inr: number;
  turnover_charges_inr: number;
  slippage_drag_inr: number;
  turnover_traded_inr: number;
  period_net_return_pct: number;
  stocks_held: RebalanceStock[];
  buys: RebalanceTrade[];
  sells: RebalanceTrade[];
}

interface BacktestResult {
  run_id: string;
  strategy_name: string;
  parameters: {
    strategy_name: string;
    start_date: string;
    end_date: string;
    initial_capital: number;
    rebalance_frequency: string;
    top_n: number;
    weighting: string;
    slippage_bps: number;
  };
  metrics: BacktestMetrics;
  benchmark_metrics: BenchmarkMetrics;
  simulation: {
    start_date: string;
    end_date: string;
    total_trading_days: number;
    calendar_years: number;
    risk_free_rate_pct: number;
  };
  equity_curve: EquityCurvePoint[];
  rebalance_events: RebalanceEvent[];
}

export default function BacktestPage() {
  // Parameters State
  const [rebalanceFreq, setRebalanceFreq] = useState<"MONTHLY" | "QUARTERLY">("MONTHLY");
  const [topN, setTopN] = useState<number>(10);
  const [weighting, setWeighting] = useState<"EQUAL_WEIGHT" | "INVERSE_VOLATILITY">("EQUAL_WEIGHT");
  const [initialCapital, setInitialCapital] = useState<number>(500000);
  const [slippageBps, setSlippageBps] = useState<number>(5.0);

  // Execution State
  const [running, setRunning] = useState<boolean>(false);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [expandedRebalance, setExpandedRebalance] = useState<number | null>(null);

  const runBacktest = useCallback(async () => {
    try {
      setRunning(true);
      setError(null);
      const payload = {
        strategy_name: `Quality_Momentum_Top${topN}`,
        start_date: "2024-01-01",
        end_date: "2026-10-28",
        initial_capital: initialCapital,
        rebalance_frequency: rebalanceFreq,
        top_n: topN,
        weighting: weighting,
        slippage_bps: slippageBps,
      };

      const res = await fetch(`${API_BASE}/backtest/run`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "true"
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errJson = await res.json().catch(() => ({}));
        throw new Error(errJson.detail || `Backtest failed with status ${res.status}`);
      }

      const json = await res.json();
      setResult(json);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Backtest execution error";
      setError(msg);
    } finally {
      setRunning(false);
    }
  }, [topN, initialCapital, rebalanceFreq, weighting, slippageBps]);

  // Load latest or default on mount
  const fetchLatest = useCallback(async () => {
    try {
      setRunning(true);
      setError(null);
      const res = await fetch(`${API_BASE}/backtest/latest`, {
        headers: { "ngrok-skip-browser-warning": "true" }
      });
      if (res.ok) {
        const json = await res.json();
        // If complete run object returned, set it
        if (json.equity_curve && json.metrics) {
          setResult(json);
        } else {
          await runBacktest();
        }
      } else {
        await runBacktest();
      }
    } catch {
      await runBacktest();
    } finally {
      setRunning(false);
    }
  }, [runBacktest]);

  useEffect(() => {
    fetchLatest();
  }, [fetchLatest]);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-black">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between pb-6 border-b border-slate-800 gap-4">
          <div>
            <div className="flex items-center space-x-2.5">
              <BarChart3 className="w-6 h-6 text-cyan-400" />
              <h1 className="text-2xl font-bold tracking-tight text-white font-mono">
                Systematic Strategy Backtest Terminal
              </h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 font-semibold">
                Milestone B8.0
              </span>
            </div>
            <p className="text-sm text-slate-400 mt-1">
              Multi-factor Quality-Momentum portfolio simulation with realistic exchange frictions (STT, DP fees, slippage) benchmarked against NIFTY 50 TRI.
            </p>
          </div>

          <div className="flex items-center space-x-3">
            <button
              onClick={runBacktest}
              disabled={running}
              className={`flex items-center space-x-2 px-5 py-2.5 rounded-lg text-sm font-semibold font-mono transition-all shadow-lg ${
                running
                  ? "bg-slate-800 text-slate-400 cursor-not-allowed border border-slate-700"
                  : "bg-gradient-to-r from-cyan-500 to-blue-600 text-black hover:from-cyan-400 hover:to-blue-500 shadow-cyan-900/30"
              }`}
            >
              {running ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>Simulating...</span>
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 fill-current" />
                  <span>Run Backtest</span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Error Alert */}
        {error && (
          <div className="p-4 bg-rose-950/40 border border-rose-800/80 rounded-xl flex items-start space-x-3 text-rose-300 text-sm">
            <AlertTriangle className="w-5 h-5 text-rose-400 flex-shrink-0 mt-0.5" />
            <div>
              <p className="font-semibold font-mono">Backtest Simulation Exception</p>
              <p className="text-xs text-rose-400 mt-0.5">{error}</p>
            </div>
          </div>
        )}

        {/* Control Parameter Bar */}
        <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-800">
            <div className="flex items-center space-x-2">
              <Sliders className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-bold text-slate-200 font-mono uppercase tracking-wider">
                Strategy Configuration & Constraints
              </h2>
            </div>
            <span className="text-xs text-slate-500 font-mono">Strict Point-in-Time Filters (ROE &gt; 15%, D/E &lt; 0.5, &gt; SMA200)</span>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-4">
            {/* Rebalance Frequency */}
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1.5">Rebalance Frequency</label>
              <div className="flex bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
                <button
                  type="button"
                  onClick={() => setRebalanceFreq("MONTHLY")}
                  className={`flex-1 py-1 rounded transition-colors text-center ${
                    rebalanceFreq === "MONTHLY"
                      ? "bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Monthly
                </button>
                <button
                  type="button"
                  onClick={() => setRebalanceFreq("QUARTERLY")}
                  className={`flex-1 py-1 rounded transition-colors text-center ${
                    rebalanceFreq === "QUARTERLY"
                      ? "bg-cyan-500/20 text-cyan-400 font-bold border border-cyan-500/40"
                      : "text-slate-400 hover:text-slate-200"
                  }`}
                >
                  Quarterly
                </button>
              </div>
            </div>

            {/* Portfolio Size Top N */}
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1.5">Top-N Holdings (K)</label>
              <select
                value={topN}
                onChange={(e) => setTopN(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value={5}>Top 5 Stocks</option>
                <option value={10}>Top 10 Stocks (Default)</option>
                <option value={15}>Top 15 Stocks</option>
                <option value={20}>Top 20 Stocks</option>
              </select>
            </div>

            {/* Weighting Method */}
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1.5">Allocation Weighting</label>
              <select
                value={weighting}
                onChange={(e) => setWeighting(e.target.value as "EQUAL_WEIGHT" | "INVERSE_VOLATILITY")}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
              >
                <option value="EQUAL_WEIGHT">Equal Weight (1/K)</option>
                <option value="INVERSE_VOLATILITY">Inverse Volatility (1/σ)</option>
              </select>
            </div>

            {/* Initial Capital */}
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1.5">Initial Capital (INR)</label>
              <input
                type="number"
                step="50000"
                min="50000"
                value={initialCapital}
                onChange={(e) => setInitialCapital(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
              />
            </div>

            {/* Slippage Bps */}
            <div>
              <label className="text-xs font-mono text-slate-400 block mb-1.5">Slippage Penalty (bps)</label>
              <input
                type="number"
                step="1"
                min="0"
                max="50"
                value={slippageBps}
                onChange={(e) => setSlippageBps(Number(e.target.value))}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>
        </section>

        {/* Performance Metric Cards */}
        {result && (
          <section className="space-y-4">
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
              {/* CAGR */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg space-y-1">
                <span className="text-[11px] font-mono text-slate-400 block">CAGR</span>
                <div className="flex items-baseline space-x-1.5">
                  <span
                    className={`text-xl font-bold font-mono ${
                      result.metrics.cagr_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {result.metrics.cagr_pct >= 0 ? "+" : ""}
                    {result.metrics.cagr_pct.toFixed(1)}%
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono block">
                  BM: {result.benchmark_metrics.cagr_pct.toFixed(1)}%
                </span>
              </div>

              {/* Sharpe Ratio */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg space-y-1">
                <span className="text-[11px] font-mono text-slate-400 block">Sharpe Ratio</span>
                <span
                  className={`text-xl font-bold font-mono ${
                    result.metrics.sharpe_ratio >= 1.0
                      ? "text-emerald-400"
                      : result.metrics.sharpe_ratio >= 0
                      ? "text-cyan-300"
                      : "text-rose-400"
                  }`}
                >
                  {result.metrics.sharpe_ratio.toFixed(2)}
                </span>
                <span className="text-[10px] text-slate-500 font-mono block">
                  BM: {result.benchmark_metrics.sharpe_ratio.toFixed(2)}
                </span>
              </div>

              {/* Sortino Ratio */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg space-y-1">
                <span className="text-[11px] font-mono text-slate-400 block">Sortino Ratio</span>
                <span
                  className={`text-xl font-bold font-mono ${
                    result.metrics.sortino_ratio >= 1.0 ? "text-emerald-400" : "text-slate-200"
                  }`}
                >
                  {result.metrics.sortino_ratio.toFixed(2)}
                </span>
                <span className="text-[10px] text-slate-500 font-mono block">
                  BM: {result.benchmark_metrics.sortino_ratio.toFixed(2)}
                </span>
              </div>

              {/* Max Drawdown */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg space-y-1">
                <span className="text-[11px] font-mono text-slate-400 block">Max Drawdown</span>
                <span className="text-xl font-bold font-mono text-rose-400">
                  -{result.metrics.max_drawdown_pct.toFixed(1)}%
                </span>
                <span className="text-[10px] text-slate-500 font-mono block">
                  BM: -{result.benchmark_metrics.max_drawdown_pct.toFixed(1)}%
                </span>
              </div>

              {/* Alpha & Beta */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg space-y-1">
                <span className="text-[11px] font-mono text-slate-400 block">Jensen&apos;s Alpha</span>
                <div className="flex items-baseline space-x-1">
                  <span
                    className={`text-xl font-bold font-mono ${
                      result.metrics.alpha_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                    }`}
                  >
                    {result.metrics.alpha_pct >= 0 ? "+" : ""}
                    {result.metrics.alpha_pct.toFixed(1)}%
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono block">
                  Beta: {result.metrics.beta.toFixed(2)}
                </span>
              </div>

              {/* Frictional Drag */}
              <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg space-y-1">
                <span className="text-[11px] font-mono text-slate-400 block">Friction Paid</span>
                <span className="text-xl font-bold font-mono text-amber-400">
                  ₹{result.metrics.total_friction_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
                <span className="text-[10px] text-slate-500 font-mono block">
                  STT: ₹{result.metrics.stt_paid_inr.toFixed(0)} | DP: ₹{result.metrics.dp_charges_paid_inr.toFixed(0)}
                </span>
              </div>
            </div>

            {/* Interactive Dual-Chart Visualizer */}
            <BacktestChart
              data={result.equity_curve}
              initialCapital={result.parameters.initial_capital}
            />

            {/* Institutional Side-by-Side Comparison */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <h3 className="text-sm font-bold text-slate-200 font-mono uppercase tracking-wider">
                  Risk & Return Factor Attribution vs NIFTY 50 TRI
                </h3>
                <span className="text-xs text-slate-400 font-mono">
                  Simulation Window: {result.simulation.start_date} to {result.simulation.end_date} ({result.simulation.total_trading_days} Days)
                </span>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs font-mono">
                  <thead>
                    <tr className="border-b border-slate-800 text-slate-400">
                      <th className="py-2.5 px-3">Performance Metric</th>
                      <th className="py-2.5 px-3 text-cyan-400 font-bold">Strategy ({result.strategy_name})</th>
                      <th className="py-2.5 px-3 text-slate-300">NIFTY 50 Benchmark</th>
                      <th className="py-2.5 px-3 text-right">Spread / Active Delta</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-850 text-slate-200">
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Total Cumulative Return</td>
                      <td className="py-2 px-3 font-semibold text-cyan-300">
                        {result.metrics.total_return_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3">{result.benchmark_metrics.total_return_pct.toFixed(2)}%</td>
                      <td className="py-2 px-3 text-right font-semibold">
                        {(result.metrics.total_return_pct - result.benchmark_metrics.total_return_pct).toFixed(2)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Annualized Compound Return (CAGR)</td>
                      <td className="py-2 px-3 font-semibold text-cyan-300">
                        {result.metrics.cagr_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3">{result.benchmark_metrics.cagr_pct.toFixed(2)}%</td>
                      <td className="py-2 px-3 text-right font-semibold">
                        {(result.metrics.cagr_pct - result.benchmark_metrics.cagr_pct).toFixed(2)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Annualized Volatility (σ)</td>
                      <td className="py-2 px-3">{result.metrics.annualized_volatility_pct.toFixed(2)}%</td>
                      <td className="py-2 px-3">{result.benchmark_metrics.annualized_volatility_pct.toFixed(2)}%</td>
                      <td className="py-2 px-3 text-right">
                        {(result.metrics.annualized_volatility_pct - result.benchmark_metrics.annualized_volatility_pct).toFixed(2)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Sharpe Ratio (Rf = 6.5%)</td>
                      <td className="py-2 px-3 font-semibold text-cyan-300">{result.metrics.sharpe_ratio.toFixed(2)}</td>
                      <td className="py-2 px-3">{result.benchmark_metrics.sharpe_ratio.toFixed(2)}</td>
                      <td className="py-2 px-3 text-right font-semibold">
                        {(result.metrics.sharpe_ratio - result.benchmark_metrics.sharpe_ratio).toFixed(2)}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Sortino Ratio</td>
                      <td className="py-2 px-3">{result.metrics.sortino_ratio.toFixed(2)}</td>
                      <td className="py-2 px-3">{result.benchmark_metrics.sortino_ratio.toFixed(2)}</td>
                      <td className="py-2 px-3 text-right">
                        {(result.metrics.sortino_ratio - result.benchmark_metrics.sortino_ratio).toFixed(2)}
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Maximum Drawdown (MDD)</td>
                      <td className="py-2 px-3 text-rose-400 font-semibold">
                        -{result.metrics.max_drawdown_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3 text-rose-400">
                        -{result.benchmark_metrics.max_drawdown_pct.toFixed(2)}%
                      </td>
                      <td className="py-2 px-3 text-right">
                        {(result.benchmark_metrics.max_drawdown_pct - result.metrics.max_drawdown_pct).toFixed(2)}%
                      </td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Portfolio Turnover (Annualized)</td>
                      <td className="py-2 px-3">{result.metrics.turnover_pct.toFixed(1)}% / yr</td>
                      <td className="py-2 px-3 text-slate-500">—</td>
                      <td className="py-2 px-3 text-right text-slate-500">—</td>
                    </tr>
                    <tr>
                      <td className="py-2 px-3 text-slate-400">Rebalance Cycle Win Rate</td>
                      <td className="py-2 px-3 font-semibold">{result.metrics.win_rate_pct.toFixed(1)}%</td>
                      <td className="py-2 px-3 text-slate-500">—</td>
                      <td className="py-2 px-3 text-right text-slate-500">—</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            {/* Rebalance Audit Log */}
            <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-800">
                <div className="flex items-center space-x-2">
                  <Receipt className="w-4 h-4 text-cyan-400" />
                  <h3 className="text-sm font-bold text-slate-200 font-mono uppercase tracking-wider">
                    Rebalance Execution Audit Ledger ({result.rebalance_events.length} Cycles)
                  </h3>
                </div>
                <span className="text-xs text-slate-400 font-mono">
                  Total Friction: ₹{result.metrics.total_friction_inr.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                </span>
              </div>

              <div className="space-y-3">
                {result.rebalance_events.map((reb, idx) => {
                  const isExpanded = expandedRebalance === idx;
                  const isPositive = reb.period_net_return_pct >= 0;

                  return (
                    <div
                      key={idx}
                      className="bg-slate-950/70 border border-slate-800/80 rounded-lg overflow-hidden transition-all"
                    >
                      <button
                        type="button"
                        onClick={() => setExpandedRebalance(isExpanded ? null : idx)}
                        className="w-full p-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-left hover:bg-slate-900/50 transition-colors"
                      >
                        <div className="flex items-center space-x-3">
                          <span className="w-6 h-6 rounded-full bg-slate-800 text-slate-300 font-mono text-xs flex items-center justify-center font-bold">
                            #{idx + 1}
                          </span>
                          <div>
                            <span className="font-mono text-sm font-semibold text-slate-100">
                              {reb.rebalance_date}
                            </span>
                            <span className="text-xs text-slate-400 font-mono ml-2">
                              (Executed: {reb.execution_date})
                            </span>
                          </div>
                        </div>

                        <div className="flex flex-wrap items-center gap-4 text-xs font-mono">
                          <div>
                            <span className="text-slate-500 block text-[10px]">NAV</span>
                            <span className="font-semibold text-slate-200">
                              ₹{reb.portfolio_value.toLocaleString("en-IN", { maximumFractionDigits: 0 })}
                            </span>
                          </div>

                          <div>
                            <span className="text-slate-500 block text-[10px]">Cycle Return</span>
                            <span className={`font-semibold ${isPositive ? "text-emerald-400" : "text-rose-400"}`}>
                              {isPositive ? "+" : ""}{reb.period_net_return_pct.toFixed(2)}%
                            </span>
                          </div>

                          <div>
                            <span className="text-slate-500 block text-[10px]">Friction</span>
                            <span className="text-amber-400">₹{reb.friction_inr.toFixed(0)}</span>
                          </div>

                          <div className="text-slate-400">
                            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                          </div>
                        </div>
                      </button>

                      {isExpanded && (
                        <div className="p-4 border-t border-slate-800/80 bg-slate-900/40 space-y-4 text-xs font-mono">
                          {/* Stocks Held Summary */}
                          <div>
                            <h4 className="text-[11px] text-slate-400 font-bold uppercase mb-2">
                              Holdings Portfolio ({reb.stocks_held.length} Instruments)
                            </h4>
                            <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-5 gap-2">
                              {reb.stocks_held.map((stock, sIdx) => (
                                <div key={sIdx} className="p-2 bg-slate-950 rounded border border-slate-800">
                                  <div className="flex justify-between items-center">
                                    <span className="font-bold text-slate-200">{stock.symbol}</span>
                                    <span className="text-[10px] text-cyan-400">{stock.weight_pct}%</span>
                                  </div>
                                  <div className="text-[11px] text-slate-400 mt-0.5">
                                    {stock.shares} shs @ ₹{stock.price.toFixed(1)}
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>

                          {/* Buys & Sells Log */}
                          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {/* Sells */}
                            <div className="p-3 bg-slate-950/60 rounded border border-slate-800/80 space-y-2">
                              <span className="text-[11px] font-bold text-rose-400 flex items-center">
                                <TrendingDown className="w-3.5 h-3.5 mr-1" />
                                Liquidations / Sells ({reb.sells.length})
                              </span>
                              {reb.sells.length === 0 ? (
                                <p className="text-slate-500 italic text-[11px]">No stocks liquidated in this cycle.</p>
                              ) : (
                                <ul className="space-y-1">
                                  {reb.sells.map((s, sIdx) => (
                                    <li key={sIdx} className="flex justify-between text-slate-300">
                                      <span>
                                        {s.symbol} (-{s.shares} shs @ ₹{s.exec_price})
                                      </span>
                                      <span className="text-slate-400">₹{s.gross_value.toLocaleString("en-IN")}</span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>

                            {/* Buys */}
                            <div className="p-3 bg-slate-950/60 rounded border border-slate-800/80 space-y-2">
                              <span className="text-[11px] font-bold text-emerald-400 flex items-center">
                                <TrendingUp className="w-3.5 h-3.5 mr-1" />
                                Purchases / Buys ({reb.buys.length})
                              </span>
                              {reb.buys.length === 0 ? (
                                <p className="text-slate-500 italic text-[11px]">No new positions initiated.</p>
                              ) : (
                                <ul className="space-y-1">
                                  {reb.buys.map((b, bIdx) => (
                                    <li key={bIdx} className="flex justify-between text-slate-300">
                                      <span>
                                        {b.symbol} (+{b.shares} shs @ ₹{b.exec_price})
                                      </span>
                                      <span className="text-slate-400">₹{b.gross_value.toLocaleString("en-IN")}</span>
                                    </li>
                                  ))}
                                </ul>
                              )}
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}
