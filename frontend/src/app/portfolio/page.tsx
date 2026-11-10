"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import Navbar from "@/components/Navbar";
import {
  fetchPortfolioSummary,
  fetchPortfolioPositions,
  fetchPortfolioOrders,
  fetchLatestRebalanceProposal,
  executeRebalanceFlow,
  previewManualOrder,
  executeManualTrade,
  resetAccountCapital,
  adjustAccountCash,
  fetchUniverseStatus,
  fetchMLTelemetry,
  triggerUniverseExpansion,
  triggerMLTraining,
  clearMemoryCache,
  PortfolioSummary,
  PortfolioPosition,
  PortfolioOrder,
  RebalanceProposalResponse,
  ManualOrderPreview,
  UniverseStatus,
  MLTelemetry,
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
  Loader2,
  Sliders,
  Sparkles,
  Cpu,
  BrainCircuit,
  Check,
  X,
  Target,
  Database,
  RotateCcw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

interface AccountTab {
  id: string;
  name: string;
  badge: string;
  type: "SYSTEMATIC" | "MANUAL";
  desc: string;
}

const ACCOUNTS: AccountTab[] = [
  {
    id: "paper_alpha_2",
    name: "Autonomous Micro-Quant",
    badge: "V8 Capital-Aware",
    type: "SYSTEMATIC",
    desc: "Capital-scaled slots (K_eff), whole-share affordability gating & greedy residual sweeper.",
  },
  {
    id: "paper_manual_1",
    name: "FrontPage Discretionary",
    badge: "Manual Sandbox",
    type: "MANUAL",
    desc: "Discretionary paper trading with pre-trade FrontPage intelligence & thesis journal.",
  },
  {
    id: "paper_alpha_1",
    name: "Institutional Benchmark",
    badge: "₹10L Factor Alpha",
    type: "SYSTEMATIC",
    desc: "Classic 15-stock equal-weight institutional factor compounding benchmark.",
  },
];

export default function PortfolioPage() {
  const [activeAccount, setActiveAccount] = useState<string>("paper_alpha_2");
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [orders, setOrders] = useState<PortfolioOrder[]>([]);
  const [proposal, setProposal] = useState<RebalanceProposalResponse | null>(null);
  const [universeStatus, setUniverseStatus] = useState<UniverseStatus | null>(null);
  const [mlTelemetry, setMLTelemetry] = useState<MLTelemetry | null>(null);
  const [showSystemTelemetry, setShowSystemTelemetry] = useState(false);

  const [loading, setLoading] = useState(true);
  const [executing, setExecuting] = useState(false);
  const [executionMsg, setExecutionMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Capital Control Modal
  const [showCapitalModal, setShowCapitalModal] = useState(false);
  const [capitalInput, setCapitalInput] = useState<string>("1600");
  const [feeTierInput, setFeeTierInput] = useState<"RETAIL_MICRO" | "INSTITUTIONAL">("RETAIL_MICRO");
  const [cashDeltaInput, setCashDeltaInput] = useState<string>("");
  const [capitalActionLoading, setCapitalActionLoading] = useState(false);

  // Manual Trade Ticket State
  const [tradeSymbol, setTradeSymbol] = useState("NHPC");
  const [tradeAction, setTradeAction] = useState<"BUY" | "SELL">("BUY");
  const [tradeMode, setTradeMode] = useState<"INR" | "QTY">("INR");
  const [tradeAmount, setTradeAmount] = useState<string>("400");
  const [tradeQty, setTradeQty] = useState<string>("5");
  const [tradeThesis, setTradeThesis] = useState("");
  const [previewLoading, setPreviewLoading] = useState(false);
  const [tradePreview, setTradePreview] = useState<ManualOrderPreview | null>(null);
  const [tradeExecuting, setTradeExecuting] = useState(false);

  // Universe & ML Actions
  const [sysActionLoading, setSysActionLoading] = useState(false);

  const loadData = useCallback(async (accId: string, invalidateCache: boolean = false) => {
    try {
      setError(null);
      if (invalidateCache) {
        clearMemoryCache("/portfolio");
      }
      const [sumRes, posRes, ordRes, propRes, univRes, mlRes] = await Promise.allSettled([
        fetchPortfolioSummary(accId),
        fetchPortfolioPositions(accId),
        fetchPortfolioOrders(accId, 100),
        fetchLatestRebalanceProposal(),
        fetchUniverseStatus(),
        fetchMLTelemetry(10),
      ]);

      if (sumRes.status === "fulfilled") setSummary(sumRes.value);
      if (posRes.status === "fulfilled") setPositions(posRes.value);
      if (ordRes.status === "fulfilled") setOrders(ordRes.value);
      if (propRes.status === "fulfilled") setProposal(propRes.value);
      if (univRes.status === "fulfilled") setUniverseStatus(univRes.value);
      if (mlRes.status === "fulfilled") setMLTelemetry(mlRes.value);
    } catch (err) {
      console.error("Error loading portfolio data:", err);
      setError("Failed to load portfolio telemetry. Verify backend connection.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData(activeAccount);
  }, [activeAccount, loadData]);

  // Load manual order preview whenever trade inputs change
  useEffect(() => {
    if (activeAccount !== "paper_manual_1") return;
    if (!tradeSymbol.trim()) return;

    let isMounted = true;
    const fetchPreview = async () => {
      setPreviewLoading(true);
      try {
        const amt = tradeMode === "INR" ? parseFloat(tradeAmount) : undefined;
        const qty = tradeMode === "QTY" ? parseInt(tradeQty, 10) : undefined;
        const res = await previewManualOrder({
          accountId: activeAccount,
          symbol: tradeSymbol.trim(),
          action: tradeAction,
          amountInr: amt && !isNaN(amt) ? amt : undefined,
          quantity: qty && !isNaN(qty) ? qty : undefined,
        });
        if (isMounted) setTradePreview(res);
      } catch {
        if (isMounted) setTradePreview(null);
      } finally {
        if (isMounted) setPreviewLoading(false);
      }
    };

    const timer = setTimeout(fetchPreview, 350);
    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [activeAccount, tradeSymbol, tradeAction, tradeMode, tradeAmount, tradeQty]);

  const handleExecuteRebalance = async () => {
    if (executing) return;
    setExecuting(true);
    setExecutionMsg(null);
    setError(null);
    try {
      const res = await executeRebalanceFlow({
        accountId: activeAccount,
        proposalId: proposal?.proposal_id || undefined,
      });
      setExecutionMsg(
        `Executed rebalance on ${activeAccount}! ` +
        `Filled ${res.orders_count} orders (Friction: ₹${res.total_friction_paid.toFixed(2)}). New NAV: ₹${res.total_nav.toLocaleString("en-IN")}.`
      );
      await loadData(activeAccount);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Rebalance execution failed: ${msg}`);
    } finally {
      setExecuting(false);
    }
  };

  const handleExecuteManualTrade = async () => {
    if (tradeExecuting) return;
    setTradeExecuting(true);
    setExecutionMsg(null);
    setError(null);
    try {
      const amt = tradeMode === "INR" ? parseFloat(tradeAmount) : undefined;
      const qty = tradeMode === "QTY" ? parseInt(tradeQty, 10) : undefined;
      const res = await executeManualTrade({
        accountId: activeAccount,
        symbol: tradeSymbol.trim(),
        action: tradeAction,
        amountInr: amt && !isNaN(amt) ? amt : undefined,
        quantity: qty && !isNaN(qty) ? qty : undefined,
        thesisNote: tradeThesis.trim(),
      });
      setExecutionMsg(
        `Successfully executed ${res.action} ${res.quantity} shares of ${res.symbol} @ ₹${res.fill_price.toFixed(2)}! ` +
        `(Friction: ₹${res.friction_paid.toFixed(2)}).`
      );
      setTradeThesis("");
      await loadData(activeAccount);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Manual trade execution failed: ${msg}`);
    } finally {
      setTradeExecuting(false);
    }
  };

  const handleResetCapital = async (amount: number, feeTier: "RETAIL_MICRO" | "INSTITUTIONAL") => {
    setCapitalActionLoading(true);
    setError(null);
    try {
      const res = await resetAccountCapital({
        accountId: activeAccount,
        initialCapital: amount,
        feeTier: feeTier,
      });
      setSummary(res);
      setExecutionMsg(`Capital reset to ₹${amount.toLocaleString("en-IN")} on ${activeAccount} (${feeTier}).`);
      setShowCapitalModal(false);
      await loadData(activeAccount);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Capital reset failed: ${msg}`);
    } finally {
      setCapitalActionLoading(false);
    }
  };

  const handleAdjustCash = async () => {
    const delta = parseFloat(cashDeltaInput);
    if (isNaN(delta) || delta === 0) return;
    setCapitalActionLoading(true);
    setError(null);
    try {
      const res = await adjustAccountCash({
        accountId: activeAccount,
        deltaCash: delta,
      });
      setSummary(res);
      setExecutionMsg(`Adjusted cash by ${delta > 0 ? "+" : ""}₹${delta.toLocaleString("en-IN")} on ${activeAccount}.`);
      setCashDeltaInput("");
      setShowCapitalModal(false);
      await loadData(activeAccount);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Cash adjustment failed: ${msg}`);
    } finally {
      setCapitalActionLoading(false);
    }
  };

  const handleTriggerBackfill = async () => {
    setSysActionLoading(true);
    setError(null);
    try {
      await triggerUniverseExpansion({ batchSize: 15, targetStartDate: "2011-01-01" });
      setExecutionMsg("15-Year historical backfill batch dispatched successfully.");
      await loadData(activeAccount);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`Backfill trigger failed: ${msg}`);
    } finally {
      setSysActionLoading(false);
    }
  };

  const handleTriggerMLTrain = async () => {
    setSysActionLoading(true);
    setError(null);
    try {
      await triggerMLTraining([5, 20, 60]);
      setExecutionMsg("Purged walk-forward ML tournament completed and champion weights logged.");
      await loadData(activeAccount);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(`ML tournament failed: ${msg}`);
    } finally {
      setSysActionLoading(false);
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

  const initialCapital = summary?.initial_capital ?? (activeAccount === "paper_alpha_1" ? 1000000 : 1600);
  const totalNav = summary?.total_nav ?? initialCapital;
  const netPnl = totalNav - initialCapital;
  const netPnlPct = initialCapital > 0 ? (netPnl / initialCapital) * 100 : 0;

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col font-sans">
      <Navbar />

      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Account Selector Tabs & Top Actions */}
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4 pb-4 border-b border-slate-800">
          <div>
            <div className="flex items-center space-x-3">
              <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center justify-center text-amber-400">
                <Wallet className="w-5 h-5" />
              </div>
              <div>
                <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2">
                  Portfolio Command Center
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-800 text-cyan-300 font-mono">
                    MIL V8 Engine
                  </span>
                </h1>
                <p className="text-xs text-slate-400 font-mono">
                  Autonomous Rebalancing • FrontPage Sandbox • Whole-Share Micro Capital • Statutory Friction
                </p>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => setShowSystemTelemetry(!showSystemTelemetry)}
              className="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700/80 hover:border-slate-600 text-slate-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all duration-150 active:scale-[0.98]"
            >
              <Cpu className="w-3.5 h-3.5 text-indigo-400" />
              <span>Universe & ML ({universeStatus?.total_universe_symbols || 1147})</span>
              {showSystemTelemetry ? <ChevronUp className="w-3 h-3 ml-1" /> : <ChevronDown className="w-3 h-3 ml-1" />}
            </button>

            <button
              onClick={() => setShowCapitalModal(true)}
              className="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700/80 hover:border-slate-600 text-slate-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all duration-150 active:scale-[0.98]"
            >
              <Sliders className="w-3.5 h-3.5 text-amber-400" />
              <span>Capital Seed ({formatINR(initialCapital)})</span>
            </button>

            <button
              onClick={() => {
                setLoading(true);
                loadData(activeAccount, true);
              }}
              disabled={loading}
              className="px-3 py-2 rounded-xl bg-slate-900 border border-slate-700/80 hover:border-slate-600 text-slate-300 hover:text-white text-xs font-mono flex items-center gap-1.5 transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
              <span>Refresh</span>
            </button>

            {activeAccount !== "paper_manual_1" && (
              <button
                onClick={handleExecuteRebalance}
                disabled={executing}
                className="px-4 py-2 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-mono font-medium shadow-lg shadow-emerald-950/40 border border-emerald-500 flex items-center gap-2 transition-all duration-150 active:scale-[0.98] disabled:opacity-50"
              >
                {executing ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Rebalancing...</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    <span>Run Rebalance Cycle</span>
                  </>
                )}
              </button>
            )}
          </div>
        </div>

        {/* Account Switcher Bento Bar with Micro-interactions */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {ACCOUNTS.map((acc) => {
            const isActive = activeAccount === acc.id;
            return (
              <button
                key={acc.id}
                onClick={() => {
                  setActiveAccount(acc.id);
                  loadData(acc.id);
                }}
                className={`relative group overflow-hidden p-4 sm:p-5 rounded-2xl text-left border transition-all duration-200 active:scale-[0.98] flex flex-col justify-between min-h-[105px] ${
                  isActive
                    ? "bg-slate-900/90 border-cyan-500/80 shadow-lg shadow-cyan-950/20 ring-1 ring-cyan-500/40"
                    : "bg-slate-900/40 border-slate-800/80 hover:border-slate-700 hover:bg-slate-900/70 hover:-translate-y-0.5 hover:shadow-[0_4px_20px_rgba(0,0,0,0.3)]"
                }`}
              >
                {/* Ambient gradient hover backlight */}
                <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

                <div className="relative z-10 flex items-center justify-between w-full">
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-white">{acc.name}</span>
                    <span
                      className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold ${
                        isActive
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/30"
                          : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {acc.id}
                    </span>
                  </div>
                  <span className="text-[10px] font-mono text-slate-400">{acc.badge}</span>
                </div>
                <p className="relative z-10 text-[11px] text-slate-400 mt-2 line-clamp-2">{acc.desc}</p>
              </button>
            );
          })}
        </div>

        {/* System & ML Telemetry Bento Card (Collapsible) */}
        {showSystemTelemetry && (
          <div className="p-5 rounded-xl bg-slate-900/90 border border-indigo-800/50 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2.5">
                <BrainCircuit className="w-5 h-5 text-indigo-400" />
                <div>
                  <h3 className="text-sm font-bold text-white">NSE 1,000+ Universe & Walk-Forward ML Telemetry</h3>
                  <p className="text-xs text-slate-400 font-mono">
                    15-Year historical depth (2011–present) • 8-factor cross-sectional models • Purged walk-forward CV
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={handleTriggerBackfill}
                  disabled={sysActionLoading}
                  className="px-3 py-1.5 rounded-lg bg-indigo-950 border border-indigo-700/60 hover:bg-indigo-900 text-indigo-200 text-xs font-mono flex items-center gap-1.5"
                >
                  <Database className="w-3.5 h-3.5" />
                  <span>Run Backfill Batch</span>
                </button>
                <button
                  onClick={handleTriggerMLTrain}
                  disabled={sysActionLoading}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-mono flex items-center gap-1.5"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>Train ML Models</span>
                </button>
              </div>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="text-slate-400 text-[11px]">Universe Queued</div>
                <div className="text-base font-bold text-white mt-1">
                  {universeStatus?.total_universe_symbols ?? 1147} Equities
                </div>
                <div className="text-[10px] text-cyan-400 mt-1">
                  {universeStatus?.active_ohlcv_symbols ?? 181} active in OHLCV
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="text-slate-400 text-[11px]">OHLCV Daily Bars</div>
                <div className="text-base font-bold text-white mt-1">
                  {(universeStatus?.total_bars_ingested ?? 254011).toLocaleString("en-IN")}
                </div>
                <div className="text-[10px] text-slate-400 mt-1">
                  {universeStatus?.earliest_historical_date} to {universeStatus?.latest_historical_date}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="text-slate-400 text-[11px]">20D Horizon Champion</div>
                <div className="text-base font-bold text-emerald-400 mt-1">
                  {mlTelemetry?.active_champions?.["20D"]?.model_family || "HistGradientBoosting"}
                </div>
                <div className="text-[10px] text-slate-400 mt-1">
                  Rank IC: {(mlTelemetry?.active_champions?.["20D"]?.rank_ic ?? 0.082).toFixed(4)}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950/60 border border-slate-800">
                <div className="text-slate-400 text-[11px]">5D / 60D Champions</div>
                <div className="text-base font-bold text-indigo-300 mt-1">
                  {mlTelemetry?.active_champions?.["5D"]?.model_family || "Ridge"} / {mlTelemetry?.active_champions?.["60D"]?.model_family || "ElasticNet"}
                </div>
                <div className="text-[10px] text-slate-400 mt-1">
                  Multi-horizon factor integration active
                </div>
              </div>
            </div>
          </div>
        )}

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

        {/* Summary Bento Metric Cards */}
        {loading && !summary ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 sm:gap-5">
            {[...Array(5)].map((_, i) => (
              <div
                key={i}
                className="rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 min-h-[140px] flex flex-col justify-between animate-pulse"
              >
                <div className="flex items-center justify-between">
                  <div className="h-3 w-20 bg-slate-800 rounded" />
                  <div className="h-4 w-4 bg-slate-800 rounded" />
                </div>
                <div className="h-8 w-32 bg-slate-800 rounded my-2" />
                <div className="flex items-center gap-2">
                  <div className="h-4 w-16 bg-slate-800 rounded-full" />
                  <div className="h-3 w-24 bg-slate-800 rounded" />
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 sm:gap-5">
            {/* Total NAV */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Total NAV</span>
                  <span className="text-slate-400 group-hover:text-cyan-400 transition-colors duration-200">
                    <PieChart className="w-4 h-4 text-cyan-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-white my-1.5">
                  {formatINR(totalNav)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  {netPnl >= 0 ? (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-emerald-950/80 border border-emerald-800 text-emerald-300">
                      <TrendingUp className="w-3 h-3 text-emerald-400" />
                      +{netPnlPct.toFixed(2)}%
                    </span>
                  ) : (
                    <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-rose-950/80 border border-rose-800 text-rose-300">
                      <TrendingDown className="w-3 h-3 text-rose-400" />
                      {netPnlPct.toFixed(2)}%
                    </span>
                  )}
                  <span className="text-slate-500 text-[11px] truncate">vs {formatINR(initialCapital)} seed</span>
                </div>
              </div>
            </div>

            {/* Available Cash */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Available Cash</span>
                  <span className="text-slate-400 group-hover:text-amber-400 transition-colors duration-200">
                    <DollarSign className="w-4 h-4 text-amber-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-amber-300 my-1.5">
                  {formatINR(summary?.cash_balance)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-amber-950/80 border border-amber-800/80 text-amber-300">
                    Solvency
                  </span>
                  <span className="text-slate-400 text-[11px]">
                    {totalNav > 0 ? (((summary?.cash_balance ?? 0) / totalNav) * 100).toFixed(1) : 0}% of NAV
                  </span>
                </div>
              </div>
            </div>

            {/* Invested Capital */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Invested Capital</span>
                  <span className="text-slate-400 group-hover:text-blue-400 transition-colors duration-200">
                    <Wallet className="w-4 h-4 text-blue-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-blue-200 my-1.5">
                  {formatINR(summary?.invested_value ?? summary?.equity_value ?? 0)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-blue-950/80 border border-blue-800/80 text-blue-300">
                    {positions.length} Active
                  </span>
                  <span className="text-slate-400 text-[11px]">Equities Held</span>
                </div>
              </div>
            </div>

            {/* Unrealized P&L */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">Unrealized P&L</span>
                  <span className="text-slate-400 group-hover:text-emerald-400 transition-colors duration-200">
                    <ArrowUpRight className="w-4 h-4 text-emerald-400" />
                  </span>
                </div>
                <div
                  className={`font-mono text-2xl sm:text-3xl font-bold tracking-tight my-1.5 ${
                    (summary?.unrealized_pnl ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                  }`}
                >
                  {(summary?.unrealized_pnl ?? 0) >= 0 ? "+" : ""}
                  {formatINR(summary?.unrealized_pnl)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit border ${
                    (summary?.unrealized_pnl ?? 0) >= 0
                      ? "bg-emerald-950/80 border-emerald-800/80 text-emerald-300"
                      : "bg-rose-950/80 border-rose-800/80 text-rose-300"
                  }`}>
                    MTM {(summary?.unrealized_pnl_pct ?? 0) >= 0 ? "+" : ""}{(summary?.unrealized_pnl_pct ?? 0).toFixed(2)}%
                  </span>
                  <span className="text-slate-400 text-[11px]">Mark-to-Market</span>
                </div>
              </div>
            </div>

            {/* Friction Costs */}
            <div className="relative group overflow-hidden rounded-2xl border border-slate-800/80 bg-slate-900/60 p-5 sm:p-6 backdrop-blur-xl transition-all duration-300 hover:border-cyan-500/40 hover:shadow-[0_0_30px_rgba(6,182,212,0.12)] hover:-translate-y-0.5 min-h-[140px]">
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />
              <div className="relative z-10 flex flex-col justify-between h-full min-h-[110px]">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-semibold tracking-wider uppercase text-slate-400">
                    Friction Paid
                  </span>
                  <span className="text-slate-400 group-hover:text-indigo-400 transition-colors duration-200">
                    <ShieldCheck className="w-4 h-4 text-indigo-400" />
                  </span>
                </div>
                <div className="font-mono text-2xl sm:text-3xl font-bold tracking-tight text-indigo-300 my-1.5">
                  {formatINR(summary?.total_friction_paid)}
                </div>
                <div className="flex items-center gap-2 text-xs text-slate-400 font-mono">
                  <span className="text-xs font-medium px-2 py-0.5 rounded-full inline-flex items-center gap-1 w-fit bg-indigo-950/80 border border-indigo-800/80 text-indigo-300">
                    {summary?.fee_tier || "RETAIL_MICRO"}
                  </span>
                  <span className="text-slate-400 text-[11px] truncate">
                    {summary?.fee_tier === "RETAIL_MICRO" ? "12 bps + ₹15 DP" : "15 bps inst."}
                  </span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* FrontPage Discretionary Trade Ticket (Active for paper_manual_1) */}
        {activeAccount === "paper_manual_1" && (
          <div className="p-5 rounded-xl bg-slate-900/90 border border-cyan-800/50 shadow-xl space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <Target className="w-4 h-4 text-cyan-400" />
                <h2 className="text-sm font-bold text-white tracking-wide">
                  FrontPage Discretionary Trade Ticket
                </h2>
              </div>
              <span className="text-xs font-mono text-slate-400">
                Solvency Verification & Quantitative Pre-Trade Audit
              </span>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Form Controls */}
              <div className="space-y-4 lg:col-span-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-slate-400 font-mono">Quick Symbols:</span>
                  {["NHPC", "BPCL", "ASHOKLEY", "ABCAPITAL", "TATAPOWER", "RELIANCE"].map((sym) => (
                    <button
                      key={sym}
                      type="button"
                      onClick={() => setTradeSymbol(sym)}
                      className={`px-2.5 py-1 rounded-md text-xs font-mono font-semibold transition-all ${
                        tradeSymbol === sym
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500"
                          : "bg-slate-800/80 text-slate-300 hover:bg-slate-800"
                      }`}
                    >
                      {sym}
                    </button>
                  ))}
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                  <div>
                    <label className="text-xs font-mono text-slate-400 block mb-1">Equity Symbol</label>
                    <input
                      type="text"
                      value={tradeSymbol}
                      onChange={(e) => setTradeSymbol(e.target.value.toUpperCase())}
                      className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 font-mono text-sm text-white focus:outline-none focus:border-cyan-500"
                      placeholder="e.g. NHPC"
                    />
                  </div>

                  <div>
                    <label className="text-xs font-mono text-slate-400 block mb-1">Action</label>
                    <div className="grid grid-cols-2 gap-1 bg-slate-950 p-1 rounded-lg border border-slate-700">
                      <button
                        type="button"
                        onClick={() => setTradeAction("BUY")}
                        className={`py-1 text-xs font-mono font-bold rounded ${
                          tradeAction === "BUY"
                            ? "bg-emerald-600 text-white"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        BUY
                      </button>
                      <button
                        type="button"
                        onClick={() => setTradeAction("SELL")}
                        className={`py-1 text-xs font-mono font-bold rounded ${
                          tradeAction === "SELL"
                            ? "bg-rose-600 text-white"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        SELL
                      </button>
                    </div>
                  </div>

                  <div>
                    <label className="text-xs font-mono text-slate-400 block mb-1">Sizing Mode</label>
                    <div className="grid grid-cols-2 gap-1 bg-slate-950 p-1 rounded-lg border border-slate-700">
                      <button
                        type="button"
                        onClick={() => setTradeMode("INR")}
                        className={`py-1 text-xs font-mono font-bold rounded ${
                          tradeMode === "INR"
                            ? "bg-cyan-600 text-white"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        INR (₹)
                      </button>
                      <button
                        type="button"
                        onClick={() => setTradeMode("QTY")}
                        className={`py-1 text-xs font-mono font-bold rounded ${
                          tradeMode === "QTY"
                            ? "bg-cyan-600 text-white"
                            : "text-slate-400 hover:text-white"
                        }`}
                      >
                        Shares
                      </button>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-mono text-slate-400 block mb-1">
                      {tradeMode === "INR" ? "Allocation Amount (INR)" : "Number of Shares"}
                    </label>
                    <input
                      type="number"
                      value={tradeMode === "INR" ? tradeAmount : tradeQty}
                      onChange={(e) =>
                        tradeMode === "INR" ? setTradeAmount(e.target.value) : setTradeQty(e.target.value)
                      }
                      className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 font-mono text-sm text-white focus:outline-none focus:border-cyan-500"
                      placeholder={tradeMode === "INR" ? "400" : "5"}
                    />
                  </div>

                  <div>
                    <label className="text-xs font-mono text-slate-400 block mb-1">Investment Thesis Note</label>
                    <input
                      type="text"
                      value={tradeThesis}
                      onChange={(e) => setTradeThesis(e.target.value)}
                      className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 text-xs text-white focus:outline-none focus:border-cyan-500"
                      placeholder="e.g. Breakout above 200 SMA with volume accumulation"
                    />
                  </div>
                </div>
              </div>

              {/* Live FrontPage Intelligence Card Preview */}
              <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-xs font-bold text-white flex items-center gap-1.5 font-mono">
                      <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                      FrontPage Intelligence Card
                    </span>
                    {previewLoading ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                    ) : tradePreview?.is_solvency_approved ? (
                      <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-emerald-950 text-emerald-300 border border-emerald-800">
                        SOLVENCY APPROVED
                      </span>
                    ) : (
                      <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-rose-950 text-rose-300 border border-rose-800">
                        INSUFFICIENT CASH
                      </span>
                    )}
                  </div>

                  {tradePreview ? (
                    <div className="space-y-2 text-xs font-mono">
                      <div className="flex justify-between py-1 border-b border-slate-900">
                        <span className="text-slate-400">Target Shares:</span>
                        <span className="font-bold text-white">
                          {tradePreview.calculated_quantity} shares @ ₹{tradePreview.current_price.toFixed(2)}
                        </span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-900">
                        <span className="text-slate-400">Gross Value:</span>
                        <span className="text-slate-200">{formatINR(tradePreview.gross_value)}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-900">
                        <span className="text-slate-400">Est. Friction:</span>
                        <span className="text-amber-400">{formatINR(tradePreview.estimated_friction)}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-900">
                        <span className="text-slate-400">Net Cash Required:</span>
                        <span className="font-bold text-cyan-300">{formatINR(tradePreview.net_cash_required)}</span>
                      </div>
                      <div className="flex justify-between py-1 border-b border-slate-900">
                        <span className="text-slate-400">Momentum Verdict:</span>
                        <span className="font-bold text-emerald-400">
                          {tradePreview.frontpage_card?.momentum_verdict || "NEUTRAL"}
                        </span>
                      </div>
                      <div className="text-[11px] text-slate-400 mt-1 line-clamp-2">
                        {tradePreview.frontpage_card?.signal_summary || "Technical profile calibrated."}
                      </div>
                    </div>
                  ) : (
                    <p className="text-xs text-slate-500 font-mono py-6 text-center">
                      Enter symbol and amount to compute whole-share allocation.
                    </p>
                  )}
                </div>

                <button
                  type="button"
                  onClick={handleExecuteManualTrade}
                  disabled={tradeExecuting || !tradePreview?.is_solvency_approved || (tradePreview?.calculated_quantity ?? 0) <= 0}
                  className="w-full mt-3 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-all disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  {tradeExecuting ? (
                    <>
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      <span>Transacting...</span>
                    </>
                  ) : (
                    <>
                      <Check className="w-3.5 h-3.5" />
                      <span>Execute {tradeAction} Trade ({tradePreview?.calculated_quantity || 0} shares)</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Pending Rebalance Proposal Banner (Active for Systematic Accounts) */}
        {activeAccount !== "paper_manual_1" && proposal && (
          <div className="p-4 rounded-xl bg-gradient-to-r from-cyan-950/40 via-slate-900/60 to-slate-900/40 border border-cyan-800/40 flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono text-cyan-300 font-semibold">
                    Rebalance Session: {proposal.session_date}
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
                  Model: <span className="font-mono text-slate-300">{proposal.model_composite_id || "8_FACTOR_BLENDED"}</span> • Projected Turnover: <span className="font-mono text-cyan-400">{proposal.turnover_pct}%</span> • Est. Friction: <span className="font-mono text-slate-300">{proposal.projected_cost_bps} bps</span>
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

        {/* Active Holdings Table */}
        <div className="bg-slate-900/60 border border-slate-800/80 rounded-xl overflow-hidden shadow-lg">
          <div className="p-4 border-b border-slate-800/80 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <FileText className="w-4 h-4 text-cyan-400" />
              <h2 className="text-sm font-semibold text-white tracking-wide">
                Active Positions ({positions.length} Equities)
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Account: {activeAccount} • Mark-to-Market
            </span>
          </div>

          {positions.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <div className="w-12 h-12 rounded-full bg-slate-800/80 text-slate-400 flex items-center justify-center mx-auto">
                <Wallet className="w-6 h-6" />
              </div>
              <p className="text-sm text-slate-300 font-medium">No Open Positions</p>
              <p className="text-xs text-slate-500 max-w-md mx-auto">
                {activeAccount === "paper_manual_1"
                  ? "Use the FrontPage Discretionary Trade Ticket above to execute a trade."
                  : "Click 'Run Rebalance Cycle' to deploy capital across top-ranked factor compounders."}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="bg-slate-950/60 border-b border-slate-800 font-mono text-slate-400">
                  <tr>
                    <th className="py-3 px-4">Symbol</th>
                    <th className="py-3 px-4 text-right">Shares</th>
                    <th className="py-3 px-4 text-right">Avg Entry</th>
                    <th className="py-3 px-4 text-right">LTP (Close)</th>
                    <th className="py-3 px-4 text-right">Market Value</th>
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
                Execution Blotter ({orders.length} Fills on {activeAccount})
              </h2>
            </div>
            <span className="text-xs font-mono text-slate-400">
              Audit-Ready Execution Log
            </span>
          </div>

          {orders.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500 font-mono">
              No executions logged yet for this account.
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
                    <th className="py-2.5 px-4">Thesis Note</th>
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
                        <td className="py-2.5 px-4 text-slate-400 text-[11px] truncate max-w-[200px]">
                          {ord.thesis_note || "—"}
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

      {/* Capital Management Modal */}
      {showCapitalModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl max-w-md w-full p-6 space-y-5 shadow-2xl">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <Sliders className="w-5 h-5 text-amber-400" />
                <h3 className="font-bold text-white text-base">Capital Control: {activeAccount}</h3>
              </div>
              <button
                onClick={() => setShowCapitalModal(false)}
                className="text-slate-400 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label className="text-xs font-mono text-slate-400 block mb-1">
                  Preset Initial Seeds:
                </label>
                <div className="grid grid-cols-4 gap-2">
                  {[1600, 10000, 50000, 1000000].map((seed) => (
                    <button
                      key={seed}
                      type="button"
                      onClick={() => setCapitalInput(seed.toString())}
                      className={`py-1.5 px-2 rounded-lg text-xs font-mono border ${
                        capitalInput === seed.toString()
                          ? "bg-amber-500/20 border-amber-500 text-amber-300 font-bold"
                          : "bg-slate-950 border-slate-800 text-slate-300 hover:bg-slate-800"
                      }`}
                    >
                      {formatINR(seed)}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-xs font-mono text-slate-400 block mb-1">
                  Custom Starting Capital (INR):
                </label>
                <input
                  type="number"
                  value={capitalInput}
                  onChange={(e) => setCapitalInput(e.target.value)}
                  className="w-full px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 font-mono text-sm text-white focus:outline-none focus:border-amber-500"
                />
              </div>

              <div>
                <label className="text-xs font-mono text-slate-400 block mb-1">
                  Statutory Fee Tier:
                </label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setFeeTierInput("RETAIL_MICRO")}
                    className={`py-2 px-3 rounded-lg text-xs font-mono border text-left ${
                      feeTierInput === "RETAIL_MICRO"
                        ? "bg-cyan-950 border-cyan-500 text-cyan-300 font-bold"
                        : "bg-slate-950 border-slate-800 text-slate-400"
                    }`}
                  >
                    <div>RETAIL_MICRO</div>
                    <div className="text-[10px] text-slate-500">12 bps + ₹15 DP fee</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setFeeTierInput("INSTITUTIONAL")}
                    className={`py-2 px-3 rounded-lg text-xs font-mono border text-left ${
                      feeTierInput === "INSTITUTIONAL"
                        ? "bg-cyan-950 border-cyan-500 text-cyan-300 font-bold"
                        : "bg-slate-950 border-slate-800 text-slate-400"
                    }`}
                  >
                    <div>INSTITUTIONAL</div>
                    <div className="text-[10px] text-slate-500">15 bps blended</div>
                  </button>
                </div>
              </div>

              <button
                type="button"
                onClick={() => handleResetCapital(parseFloat(capitalInput), feeTierInput)}
                disabled={capitalActionLoading || isNaN(parseFloat(capitalInput)) || parseFloat(capitalInput) <= 0}
                className="w-full py-2.5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-mono text-xs font-bold flex items-center justify-center gap-2"
              >
                {capitalActionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
                <span>Reset Capital & Clear Positions</span>
              </button>

              <div className="pt-3 border-t border-slate-800">
                <label className="text-xs font-mono text-slate-400 block mb-1">
                  Deposit / Withdraw Cash (Keeps active positions):
                </label>
                <div className="flex gap-2">
                  <input
                    type="number"
                    value={cashDeltaInput}
                    onChange={(e) => setCashDeltaInput(e.target.value)}
                    placeholder="e.g. +500 or -200"
                    className="flex-1 px-3 py-2 rounded-lg bg-slate-950 border border-slate-700 font-mono text-xs text-white focus:outline-none focus:border-cyan-500"
                  />
                  <button
                    type="button"
                    onClick={handleAdjustCash}
                    disabled={capitalActionLoading || !cashDeltaInput}
                    className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-mono text-xs font-bold"
                  >
                    Apply Cash
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
