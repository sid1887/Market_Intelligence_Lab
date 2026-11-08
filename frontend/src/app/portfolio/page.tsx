"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  fetchPortfolioSummary,
  fetchPortfolioPositions,
  fetchPortfolioOrders,
  fetchLatestRebalanceProposal,
  executePortfolioProposal,
  PortfolioSummary,
  PortfolioPosition,
  PortfolioOrder,
  RebalanceProposalResponse
} from "@/lib/api";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  ArrowUpRight,
  RefreshCw,
  Play,
  Layers,
  Clock,
  ShieldCheck,
  AlertCircle,
  FileText,
  DollarSign,
  PieChart,
  CheckCircle2,
  Loader2
} from "lucide-react";

export default function PortfolioPage() {
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [orders, setOrders] = useState<PortfolioOrder[]>([]);
  const [proposal, setProposal] = useState<RebalanceProposalResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [executionMsg, setExecutionMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const loadData = useCallback(async () => {
    try {
      setError(null);
      const [sumRes, posRes, ordRes, propRes] = await Promise.allSettled([
        fetchPortfolioSummary("paper_alpha_1", { useCache: false }),
        fetchPortfolioPositions("paper_alpha_1", { useCache: false }),
        fetchPortfolioOrders("paper_alpha_1", 100, { useCache: false }),
        fetchLatestRebalanceProposal(),
      ]);

      if (sumRes.status === "fulfilled") setSummary(sumRes.value);
      if (posRes.status === "fulfilled") setPositions(posRes.value);
      if (ordRes.status === "fulfilled") setOrders(ordRes.value);
      if (propRes.status === "fulfilled") setProposal(propRes.value);
    } catch (err) {
      console.error("Error loading portfolio data:", err);
      setError("Failed to load portfolio telemetry. Verify backend connection.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleExecute = async () => {
    if (executing) return;
    setExecuting(true);
    setExecutionMsg(null);
    setError(null);
    try {
      const res = await executePortfolioProposal(proposal?.proposal_id || undefined, "paper_alpha_1");
      setExecutionMsg(
        `Successfully executed proposal ${res.proposal_id}! ` +
        `Logged ${res.orders_count} orders (Total friction paid: ₹${res.total_friction_paid.toFixed(2)}).`
      );
      await loadData();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Execution failed: ${msg}`);
    } finally {
      setExecuting(false);
    }
  };

  const formatINR = (val: number | null | undefined): string => {
    if (val === null || val === undefined || isNaN(val)) return "₹0.00";
    return new Intl.NumberFormat("en-IN", {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: 2,
    }).format(val);
  };

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Top Header & Execution Control */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                <Wallet className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                  Virtual Portfolio Ledger
                  <span className="text-xs px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700 font-mono text-cyan-400">
                    paper_alpha_1
                  </span>
                </h1>
                <p className="text-xs text-slate-400 font-mono">
                  Autonomous Paper Trading Simulation • Real-Time MTM Valuation • Statutory Indian Friction (STT + DP)
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={() => {
                setLoading(true);
                loadData();
              }}
              disabled={loading}
              className="px-3 py-2 rounded-lg bg-slate-900 border border-slate-700 hover:border-slate-600 text-slate-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
              <span>Refresh</span>
            </button>

            {proposal && proposal.status === "PROPOSED" && (
              <button
                onClick={handleExecute}
                disabled={executing}
                className="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-medium shadow-lg shadow-emerald-950/40 border border-emerald-500 flex items-center gap-2 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {executing ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Executing Proposal...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Execute Proposal ({proposal.proposal_id?.slice(0, 14)})</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Notifications / Alerts */}
        {error && (
          <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-xs flex items-center gap-3">
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
            <span>{error}</span>
          </div>
        )}

        {executionMsg && (
          <div className="p-4 rounded-xl bg-emerald-950/40 border border-emerald-800/60 text-emerald-300 text-xs flex items-center gap-3">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
            <span>{executionMsg}</span>
          </div>
        )}

        {/* Pending Proposal Banner */}
        {proposal && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-cyan-950/40 via-slate-900/60 to-slate-900/40 border border-cyan-800/40 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-cyan-300 font-semibold">
                    Rebalance Cycle: {proposal.session_date}
                  </span>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded font-mono border ${
                      proposal.status === "EXECUTED"
                        ? "bg-emerald-950/80 border-emerald-700/60 text-emerald-300"
                        : "bg-amber-950/80 border-amber-700/60 text-amber-300"
                    }`}
                  >
                    STATUS: {proposal.status}
                  </span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">
                  Model Composite: <span className="font-mono text-slate-300">{proposal.model_composite_id || "BLENDED"}</span> • Projected Turnover: <span className="font-mono text-cyan-400">{proposal.turnover_pct}%</span> • Est. Friction: <span className="font-mono text-slate-300">{proposal.projected_cost_bps} bps</span>
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-xs text-slate-400 font-mono">
                {Object.keys(proposal.holdings_after || {}).length} Target Equities
              </span>
            </div>
          </div>
        )}

        {/* Summary Metric Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
          {/* Total NAV */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-md">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Total Account NAV</span>
              <PieChart className="w-4 h-4 text-cyan-400" />
            </div>
            <div className="text-xl font-bold font-mono text-white">
              {formatINR(summary?.total_nav)}
            </div>
            <div className="flex items-center gap-1.5 mt-2 text-xs font-mono">
              {(summary?.total_pnl ?? 0) >= 0 ? (
                <>
                  <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                  <span className="text-emerald-400 font-medium">
                    +{summary?.total_pnl_pct.toFixed(2)}%
                  </span>
                </>
              ) : (
                <>
                  <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
                  <span className="text-rose-400 font-medium">
                    {summary?.total_pnl_pct.toFixed(2)}%
                  </span>
                </>
              )}
              <span className="text-slate-500">vs ₹10L seed</span>
            </div>
          </div>

          {/* Cash Balance */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-md">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Available Cash</span>
              <DollarSign className="w-4 h-4 text-amber-400" />
            </div>
            <div className="text-xl font-bold font-mono text-amber-300">
              {formatINR(summary?.cash_balance)}
            </div>
            <div className="text-xs text-slate-400 font-mono mt-2">
              Solvency: {summary?.total_nav ? ((summary.cash_balance / summary.total_nav) * 100).toFixed(1) : 0}% of NAV
            </div>
          </div>

          {/* Invested Value */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-md">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Invested Capital</span>
              <Wallet className="w-4 h-4 text-blue-400" />
            </div>
            <div className="text-xl font-bold font-mono text-blue-200">
              {formatINR(summary?.invested_value)}
            </div>
            <div className="text-xs text-slate-400 font-mono mt-2">
              Holdings: {summary?.positions_count || 0} active positions
            </div>
          </div>

          {/* Unrealized P&L */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-md">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Unrealized P&L</span>
              <ArrowUpRight className="w-4 h-4 text-emerald-400" />
            </div>
            <div
              className={`text-xl font-bold font-mono ${
                (summary?.unrealized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
              }`}
            >
              {(summary?.unrealized_pnl ?? 0) >= 0 ? "+" : ""}
              {formatINR(summary?.unrealized_pnl)}
            </div>
            <div className="text-xs font-mono text-slate-400 mt-2">
              MTM Return: {summary?.unrealized_pnl_pct ? summary.unrealized_pnl_pct.toFixed(2) : "0.00"}%
            </div>
          </div>

          {/* Friction Costs */}
          <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800/80 shadow-md">
            <div className="flex items-center justify-between text-slate-400 text-xs mb-1">
              <span>Total Friction Paid</span>
              <ShieldCheck className="w-4 h-4 text-indigo-400" />
            </div>
            <div className="text-xl font-bold font-mono text-indigo-300">
              {formatINR(summary?.total_friction_paid)}
            </div>
            <div className="text-[11px] text-slate-400 font-mono mt-2 truncate">
              0.10% STT • 0.05% Slip • ₹15 DP
            </div>
          </div>
        </div>

        {/* Active Holdings Table */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold text-white tracking-wide">
                Active Portfolio Positions ({positions.length})
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Mark-to-Market Real-Time Ledger
            </span>
          </div>

          {positions.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-slate-800/80 text-slate-400 flex items-center justify-center mx-auto">
                <Wallet className="w-6 h-6" />
              </div>
              <p className="text-sm text-slate-300 font-medium">No Open Positions</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                Virtual portfolio is currently 100% in cash. Execute a rebalance proposal above to deploy capital across institutional model champions.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 border-b border-slate-800 font-mono text-slate-400">
                  <tr>
                    <th className="py-3 px-4">Symbol</th>
                    <th className="py-3 px-4 text-right">Shares</th>
                    <th className="py-3 px-4 text-right">Avg Entry Price</th>
                    <th className="py-3 px-4 text-right">LTP (Close)</th>
                    <th className="py-3 px-4 text-right">Current Value</th>
                    <th className="py-3 px-4 text-right">Alloc %</th>
                    <th className="py-3 px-4 text-right">Unrealized P&L</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50 font-mono">
                  {positions.map((pos) => {
                    const isProfit = pos.unrealized_pnl >= 0;
                    return (
                      <tr key={pos.position_id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="py-3 px-4 font-bold">
                          <Link
                            href={`/stocks/${pos.symbol}`}
                            className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 group"
                          >
                            <span>{pos.symbol}</span>
                            <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                          </Link>
                        </td>
                        <td className="py-3 px-4 text-right text-slate-200">
                          {pos.quantity.toLocaleString("en-IN")}
                        </td>
                        <td className="py-3 px-4 text-right text-slate-400">
                          ₹{pos.average_entry_price.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-slate-200 font-semibold">
                          ₹{pos.current_price.toFixed(2)}
                        </td>
                        <td className="py-3 px-4 text-right text-slate-100">
                          {formatINR(pos.market_value)}
                        </td>
                        <td className="py-3 px-4 text-right text-cyan-300">
                          {pos.weight_pct.toFixed(2)}%
                        </td>
                        <td
                          className={`py-3 px-4 text-right font-semibold ${
                            isProfit ? "text-emerald-400" : "text-rose-400"
                          }`}
                        >
                          {isProfit ? "+" : ""}
                          {formatINR(pos.unrealized_pnl)}
                          <span className="text-[11px] font-normal ml-1 text-slate-400">
                            ({isProfit ? "+" : ""}{pos.unrealized_pnl_pct.toFixed(2)}%)
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Execution Blotter / Orders History */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-amber-400" />
              <h2 className="text-sm font-semibold text-white tracking-wide">
                Trade Execution Blotter ({orders.length} Virtual Fills)
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Audit-Ready Execution Log
            </span>
          </div>

          {orders.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500 font-mono">
              No executions logged yet. Fills with statutory friction breakdown will appear here.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 border-b border-slate-800 font-mono text-slate-400">
                  <tr>
                    <th className="py-2.5 px-4">Timestamp</th>
                    <th className="py-2.5 px-4">Action</th>
                    <th className="py-2.5 px-4">Symbol</th>
                    <th className="py-2.5 px-4 text-right">Quantity</th>
                    <th className="py-2.5 px-4 text-right">Fill Price</th>
                    <th className="py-2.5 px-4 text-right">Gross Value</th>
                    <th className="py-2.5 px-4 text-right">Friction Paid</th>
                    <th className="py-2.5 px-4 text-right">Order Ref</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/50 font-mono">
                  {orders.map((ord) => {
                    const isBuy = ord.action === "BUY";
                    const gross = ord.quantity * ord.fill_price;
                    return (
                      <tr key={ord.order_id} className="hover:bg-slate-800/30 transition-colors">
                        <td className="py-2.5 px-4 text-slate-400">
                          {ord.executed_at ? ord.executed_at.slice(0, 19).replace("T", " ") : "—"}
                        </td>
                        <td className="py-2.5 px-4">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              isBuy
                                ? "bg-emerald-950/80 border-emerald-700/60 text-emerald-300"
                                : "bg-rose-950/80 border-rose-700/60 text-rose-300"
                            }`}
                          >
                            {ord.action}
                          </span>
                        </td>
                        <td className="py-2.5 px-4 font-bold text-slate-200">
                          <Link href={`/stocks/${ord.symbol}`} className="hover:text-cyan-400">
                            {ord.symbol}
                          </Link>
                        </td>
                        <td className="py-2.5 px-4 text-right text-slate-300">
                          {ord.quantity.toLocaleString("en-IN")}
                        </td>
                        <td className="py-2.5 px-4 text-right text-slate-300">
                          ₹{ord.fill_price.toFixed(2)}
                        </td>
                        <td className="py-2.5 px-4 text-right text-slate-100 font-medium">
                          {formatINR(gross)}
                        </td>
                        <td className="py-2.5 px-4 text-right text-amber-400 font-medium">
                          {formatINR(ord.friction_paid)}
                        </td>
                        <td className="py-2.5 px-4 text-right text-slate-500 text-[11px] truncate max-w-[120px]">
                          {ord.order_id}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
