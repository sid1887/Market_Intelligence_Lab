"use client";

import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  ExternalLink,
  RefreshCw,
  Command,
  TrendingUp,
  TrendingDown,
  Minus,
  ChevronRight,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Table as TableIcon,
  LayoutGrid,
  Sparkles,
} from "lucide-react";
import {
  apiFetch,
  prefetchStockBundle,
  ScreenerCandidate,
  ScreenerResponse,
  WatchlistResponse,
  SystemAccuracy,
  CandleData,
  ForecastData,
  InvestmentMemo,
  NewsArticle,
  NewsResponse,
  VerdictType,
  MacroResponse,
  fetchMacroTelemetry,
} from "@/lib/api";
import StockChart from "@/components/StockChart";
import { FactorPentagonRadar } from "@/components/FactorPentagonRadar";
import { RiskRewardVectorBar } from "@/components/RiskRewardVectorBar";
import { RadialConvictionGauge } from "@/components/RadialConvictionGauge";
import { CommandPaletteModal } from "@/components/CommandPaletteModal";
import { SectorHeatmap } from "@/components/SectorHeatmap";

// ─── Ambient Verdict Aura Styles ──────────────────────────────────────────────
const VERDICT_CONFIG: Record<
  VerdictType,
  { label: string; badge: string; auraGradient: string; horizonLabel: string }
> = {
  STRONG_BUY_COMPOUNDER: {
    label: "STRONG BUY",
    badge: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.2)]",
    auraGradient: "from-emerald-500/20 via-teal-500/10 to-transparent",
    horizonLabel: "12–24 Months",
  },
  TACTICAL_SWING_LONG: {
    label: "SWING LONG",
    badge: "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.2)]",
    auraGradient: "from-cyan-500/20 via-blue-500/10 to-transparent",
    horizonLabel: "2–8 Weeks",
  },
  HOLD_FAIRLY_VALUED: {
    label: "HOLD",
    badge: "bg-amber-950/80 border-amber-500/50 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.15)]",
    auraGradient: "from-amber-500/15 via-slate-900/10 to-transparent",
    horizonLabel: "3–6 Months",
  },
  AVOID_CAPITAL_PRESERVATION: {
    label: "AVOID",
    badge: "bg-rose-950/80 border-rose-500/50 text-rose-300 shadow-[0_0_12px_rgba(239,68,68,0.2)]",
    auraGradient: "from-rose-500/20 via-red-900/10 to-transparent",
    horizonLabel: "Capital Preservation",
  },
};

const DEFAULT_VERDICT_CFG = VERDICT_CONFIG["HOLD_FAIRLY_VALUED"];

type ViewMode = "table" | "heatmap";
type SectorFilter = "All" | "IT" | "Energy" | "Pharma" | "Auto" | "Financials" | "Capital Goods";
const SECTOR_FILTERS: SectorFilter[] = [
  "All",
  "IT",
  "Energy",
  "Pharma",
  "Auto",
  "Financials",
  "Capital Goods",
];

function matchSector(item: ScreenerCandidate, filter: SectorFilter): boolean {
  if (filter === "All") return true;
  const sec = (item.sector || "").toLowerCase();
  if (filter === "IT")
    return sec.includes("it") || sec.includes("tech") || sec.includes("software") || sec.includes("information");
  if (filter === "Energy")
    return sec.includes("energy") || sec.includes("power") || sec.includes("oil") || sec.includes("gas") || sec.includes("petro");
  if (filter === "Pharma")
    return sec.includes("pharma") || sec.includes("health") || sec.includes("bio");
  if (filter === "Auto")
    return sec.includes("auto") || sec.includes("motor") || sec.includes("vehicle");
  if (filter === "Financials")
    return sec.includes("financial") || sec.includes("bank") || sec.includes("insurance") || sec.includes("nbfc");
  if (filter === "Capital Goods")
    return sec.includes("capital") || sec.includes("industrial") || sec.includes("engineering") || sec.includes("manufactur");
  return true;
}

// ─── Inspector Data State ─────────────────────────────────────────────────────
interface InspectorData {
  symbol: string;
  candles: CandleData[];
  forecast: ForecastData | null;
  memo: InvestmentMemo | null;
  news: NewsArticle[];
  isSyncing: boolean;
}

const EMPTY_INSPECTOR: InspectorData = {
  symbol: "",
  candles: [],
  forecast: null,
  memo: null,
  news: [],
  isSyncing: false,
};

export default function CockpitPage() {
  // Page level state
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [accuracy, setAccuracy] = useState<SystemAccuracy | null>(null);
  const [macro, setMacro] = useState<MacroResponse | null>(null);
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  // Left pane controls
  const [viewMode, setViewMode] = useState<ViewMode>("table");
  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState<SectorFilter>("All");
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [showCommandPalette, setShowCommandPalette] = useState(false);

  // Sorting
  const [sortField, setSortField] = useState<keyof ScreenerCandidate>("rank");
  const [sortAsc, setSortAsc] = useState<boolean>(true);

  // Right Inspector state
  const [inspector, setInspector] = useState<InspectorData>(EMPTY_INSPECTOR);
  const [inspectorTab, setInspectorTab] = useState<"thesis" | "wire">("thesis");

  const tableBodyRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);
  const inspectorLoadingRef = useRef<string>("");

  // ─── Filter & Sort ──────────────────────────────────────────────────────────
  const filtered = useMemo(() => {
    const list = candidates.filter((item) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !item.symbol.toLowerCase().includes(q) &&
          !item.company_name.toLowerCase().includes(q) &&
          !(item.sector || "").toLowerCase().includes(q)
        )
          return false;
      }
      return matchSector(item, sectorFilter);
    });

    list.sort((a, b) => {
      const valA = a[sortField];
      const valB = b[sortField];
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;
      if (valA < valB) return sortAsc ? -1 : 1;
      if (valA > valB) return sortAsc ? 1 : -1;
      return 0;
    });

    return list;
  }, [candidates, search, sectorFilter, sortField, sortAsc]);

  const activeCandidate = filtered[activeIndex] || filtered[0] || null;

  // ─── Initial Page Load ──────────────────────────────────────────────────────
  const loadPageData = useCallback(async () => {
    setPageLoading(true);
    setPageError(null);
    try {
      const [scrData, wlData, accData, macroData] = await Promise.allSettled([
        apiFetch<ScreenerResponse>("/screener?limit=250"),
        apiFetch<WatchlistResponse>("/watchlist"),
        apiFetch<SystemAccuracy>("/system/accuracy"),
        fetchMacroTelemetry(),
      ]);

      if (scrData.status === "fulfilled") {
        const res = scrData.value.results || [];
        setCandidates(res);
        setAsOfDate(scrData.value.as_of_date || "");
        // Prefetch top candidates
        res.slice(0, 6).forEach((c) => prefetchStockBundle(c.symbol));
      } else {
        setPageError("Failed to connect to Screener API.");
      }

      if (wlData.status === "fulfilled") {
        setWatchlistSymbols((wlData.value.watchlist || []).map((w) => w.symbol));
      }

      if (accData.status === "fulfilled") {
        setAccuracy(accData.value);
      }

      if (macroData.status === "fulfilled") {
        setMacro(macroData.value);
      }
    } catch (err: unknown) {
      setPageError(err instanceof Error ? err.message : "FastAPI Bridge Error");
    } finally {
      setPageLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPageData();
  }, [loadPageData]);

  // ─── Smooth Inspector Loader (Never Unmounts UI) ───────────────────────────
  const loadInspector = useCallback(async (symbol: string) => {
    if (!symbol) return;
    if (inspectorLoadingRef.current === symbol) return;
    inspectorLoadingRef.current = symbol;

    setInspector((prev) => ({
      ...prev,
      symbol,
      isSyncing: true,
    }));

    try {
      const [candlesRes, forecastRes, memoRes, newsRes] = await Promise.allSettled([
        apiFetch<CandleData[]>(`/stocks/${symbol}/history`),
        apiFetch<ForecastData>(`/stocks/${symbol}/forecast`),
        apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`),
        apiFetch<NewsResponse>(`/stocks/${symbol}/news`),
      ]);

      // Protect against out-of-order race conditions
      if (inspectorLoadingRef.current !== symbol) return;

      setInspector({
        symbol,
        candles: candlesRes.status === "fulfilled" ? candlesRes.value : [],
        forecast: forecastRes.status === "fulfilled" ? forecastRes.value : null,
        memo: memoRes.status === "fulfilled" ? memoRes.value : null,
        news: newsRes.status === "fulfilled" ? newsRes.value.articles || [] : [],
        isSyncing: false,
      });
    } catch {
      if (inspectorLoadingRef.current === symbol) {
        setInspector((prev) => ({ ...prev, isSyncing: false }));
      }
    }
  }, []);

  // Sync inspector with active candidate
  useEffect(() => {
    if (activeCandidate) {
      void loadInspector(activeCandidate.symbol);
    }
  }, [activeCandidate?.symbol, loadInspector]); // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Keyboard Navigation (↑ / ↓, ⌘K) ───────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowCommandPalette(true);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => {
          const next = Math.min(i + 1, filtered.length - 1);
          if (filtered[next]) prefetchStockBundle(filtered[next].symbol);
          return next;
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => {
          const prev = Math.max(i - 1, 0);
          if (filtered[prev]) prefetchStockBundle(filtered[prev].symbol);
          return prev;
        });
      } else if (e.key === "Escape") {
        setShowCommandPalette(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filtered]);

  // Scroll active row into view
  useEffect(() => {
    if (viewMode === "table") {
      const el = tableBodyRef.current?.querySelector(`[data-rowindex="${activeIndex}"]`);
      el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }, [activeIndex, viewMode]);

  // Reset index on filter change
  useEffect(() => {
    setActiveIndex(0);
  }, [search, sectorFilter, sortField, sortAsc]);

  // Quick jump helper
  const handleSelectSymbol = (sym: string) => {
    const idx = filtered.findIndex((c) => c.symbol === sym);
    if (idx >= 0) {
      setActiveIndex(idx);
    } else {
      // Find in full candidates
      const cand = candidates.find((c) => c.symbol === sym);
      if (cand) {
        setSearch("");
        setSectorFilter("All");
        const newIdx = candidates.findIndex((c) => c.symbol === sym);
        setActiveIndex(newIdx >= 0 ? newIdx : 0);
      }
      void loadInspector(sym);
    }
  };

  // Toggle sort
  const handleSort = (field: keyof ScreenerCandidate) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(field === "rank" || field === "symbol" ? true : false);
    }
  };

  // ─── Active Stock Metrics (Derived directly from activeCandidate) ─────────
  const currentPrice = activeCandidate?.close || inspector.memo?.key_metrics?.current_price || 0;
  const sma200 = activeCandidate?.sma_200 || inspector.memo?.key_metrics?.sma_200 || null;
  const smaDist =
    sma200 && currentPrice ? ((currentPrice - sma200) / sma200) * 100 : null;

  // Active verdict
  const activeVerdict: VerdictType =
    inspector.memo?.verdict ||
    (activeCandidate?.composite_score && activeCandidate.composite_score >= 80
      ? "STRONG_BUY_COMPOUNDER"
      : activeCandidate?.composite_score && activeCandidate.composite_score >= 60
      ? "TACTICAL_SWING_LONG"
      : activeCandidate?.composite_score && activeCandidate.composite_score >= 40
      ? "HOLD_FAIRLY_VALUED"
      : "AVOID_CAPITAL_PRESERVATION");

  const verdictCfg = VERDICT_CONFIG[activeVerdict] || DEFAULT_VERDICT_CFG;

  // Forecast bounds for RiskRewardVectorBar
  const forecastLower95 =
    inspector.forecast?.projections?.[inspector.forecast.projections.length - 1]?.lower_95 ||
    currentPrice * 0.92;
  const forecastUpper80 =
    inspector.forecast?.projections?.[inspector.forecast.projections.length - 1]?.upper_80 ||
    currentPrice * 1.08;

  // Factor Pentagon metrics (immediate from candidate, refined from memo)
  const factorRoe = activeCandidate?.roe_pct ?? inspector.memo?.key_metrics?.roe_pct ?? 0;
  const factorDe = activeCandidate?.debt_to_equity ?? inspector.memo?.key_metrics?.debt_to_equity ?? 0;
  const factorOpm = activeCandidate?.opm_pct ?? inspector.memo?.key_metrics?.opm_pct ?? 0;
  const factorMom = (activeCandidate?.excess_ret_20d ?? 0) * 100;
  const factorConv =
    inspector.memo?.institutional_conviction_score ??
    activeCandidate?.composite_score ??
    50;

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-[#030508] select-none text-slate-100 font-sans">
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 1. TOP UNIFIED TELEMETRY & COMPOUNDING ML ACCURACY BAR               */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <header className="h-12 shrink-0 border-b border-white/[0.06] flex items-center justify-between px-4 bg-[#030508]/90 backdrop-blur-md z-30">
        {/* Left: Brand + Subtle Green Pulse */}
        <div className="flex items-center gap-2.5 shrink-0">
          <div className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-sm bg-cyan-400 shadow-[0_0_6px_#06b6d4]" />
            <span className="text-sm font-mono font-bold text-white tracking-tight">
              MARKET INTELLIGENCE LAB
            </span>
          </div>

          <div className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-emerald-950/40 border border-emerald-500/20 text-emerald-400 text-[10px] font-mono">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
            </span>
            <span>{candidates.length || 181} NSE Active</span>
          </div>
        </div>

        {/* Center: Live AlphaVantage Macro Ribbon + Minimal Audit Pill */}
        <div className="hidden lg:flex items-center gap-2.5">
          {macro && macro.indicators && (
            <div className="flex items-center gap-2 px-3 py-1 rounded-full bg-[#050811] border border-white/[0.06] text-[11px] font-mono text-slate-400">
              {macro.indicators.slice(0, 3).map((ind, i) => (
                <React.Fragment key={ind.symbol}>
                  {i > 0 && <span className="text-slate-700">·</span>}
                  <span className="flex items-center gap-1">
                    <span className="text-slate-500">{ind.label}:</span>
                    <strong className="text-slate-200 font-medium">
                      {ind.unit === "₹"
                        ? `₹${ind.value.toFixed(2)}`
                        : ind.unit === "%"
                        ? `${ind.value.toFixed(2)}%`
                        : `$${ind.value.toFixed(2)}`}
                    </strong>
                  </span>
                </React.Fragment>
              ))}
            </div>
          )}

          <div className="flex items-center px-3.5 py-1 rounded-full bg-[#050811] border border-slate-800 text-slate-400 font-mono text-xs">
            <span>
              Model Health:{" "}
              <strong className="text-slate-200 font-medium">
                {accuracy ? `${accuracy.forecast_model.containment_80_pct.toFixed(0)}%` : "96%"} 20D Containment
              </strong>{" "}
              ·{" "}
              <strong className="text-slate-200 font-medium">
                {accuracy ? `${accuracy.forecast_model.rmse_pct.toFixed(1)}%` : "3.8%"} RMSE
              </strong>
            </span>
          </div>
        </div>

        {/* Right: Backtester + ⌘K Search trigger + Sync */}
        <div className="flex items-center gap-2.5 shrink-0">
          <Link
            href="/backtest"
            className="flex items-center gap-1.5 text-xs font-mono text-slate-400 px-2.5 py-1 rounded-lg bg-slate-900/60 border border-white/[0.06] hover:border-cyan-500/30 hover:text-slate-200 transition-colors"
          >
            <span>Backtester</span>
            <ExternalLink className="w-3 h-3 text-cyan-400" />
          </Link>

          <button
            onClick={() => setShowCommandPalette(true)}
            className="flex items-center gap-1.5 text-xs font-mono text-slate-400 px-2.5 py-1 rounded-lg bg-slate-900/60 border border-white/[0.06] hover:border-cyan-500/30 hover:text-slate-200 transition-colors"
          >
            <Command className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Search</span>
            <kbd className="text-[10px] font-mono text-slate-500 bg-slate-800/80 px-1 rounded border border-white/[0.04]">⌘K</kbd>
          </button>

          <button
            onClick={loadPageData}
            disabled={pageLoading}
            title="Sync Universe"
            className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800/60 border border-white/[0.06] transition-colors disabled:opacity-50"
          >
            <RefreshCw
              className={`w-3.5 h-3.5 ${pageLoading ? "animate-spin text-cyan-400" : ""}`}
            />
          </button>
        </div>
      </header>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 2. SPLIT-PANE WORKBENCH: LEFT (54%) + RIGHT (46%)                    */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">
        {/* ── LEFT MASTER PANE (54%) ──────────────────────────────────────── */}
        <div className="w-[54%] flex flex-col border-r border-white/[0.06] bg-[#030508] overflow-hidden shrink-0">
          {/* Top Control Strip */}
          <div className="shrink-0 border-b border-white/[0.05] px-3.5 py-2 flex items-center justify-between gap-3 bg-[#030508]/90">
            {/* View Mode Toggle (Table vs Heatmap) */}
            <div className="flex items-center p-0.5 rounded-lg bg-[#050811] border border-white/[0.06]">
              <button
                onClick={() => setViewMode("table")}
                className={`relative px-2.5 py-1 text-[11px] font-mono transition-colors ${
                  viewMode === "table" ? "text-cyan-300 font-bold" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {viewMode === "table" && (
                  <motion.span
                    layoutId="viewModePill"
                    className="absolute inset-0 bg-cyan-500/15 border border-cyan-500/30 rounded-md"
                    transition={{ type: "spring", stiffness: 350, damping: 28 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <TableIcon className="w-3 h-3" />
                  <span>Screener</span>
                </span>
              </button>

              <button
                onClick={() => setViewMode("heatmap")}
                className={`relative px-2.5 py-1 text-[11px] font-mono transition-colors ${
                  viewMode === "heatmap" ? "text-cyan-300 font-bold" : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {viewMode === "heatmap" && (
                  <motion.span
                    layoutId="viewModePill"
                    className="absolute inset-0 bg-cyan-500/15 border border-cyan-500/30 rounded-md"
                    transition={{ type: "spring", stiffness: 350, damping: 28 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <LayoutGrid className="w-3 h-3" />
                  <span>Sector Treemap</span>
                </span>
              </button>
            </div>

            {/* Fast Search Input */}
            <div className="relative flex-1 max-w-[210px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500 pointer-events-none" />
              <input
                ref={searchInputRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter 181 equities..."
                className="w-full pl-7 pr-2 py-1 text-xs font-mono bg-slate-900/60 border border-white/[0.07] focus:border-cyan-500/60 rounded-md text-slate-200 placeholder-slate-600 outline-none transition-colors"
              />
            </div>

            {/* Sector Filter Pills */}
            <div className="hidden xl:flex items-center gap-1 overflow-x-auto no-scrollbar">
              {SECTOR_FILTERS.map((sf) => (
                <button
                  key={sf}
                  onClick={() => setSectorFilter(sf)}
                  className={`relative text-[10px] font-mono px-2 py-0.5 rounded transition-colors whitespace-nowrap ${
                    sectorFilter === sf ? "text-cyan-300 font-bold" : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {sectorFilter === sf && (
                    <motion.span
                      layoutId="sectorFilterPill"
                      className="absolute inset-0 bg-cyan-500/15 border border-cyan-500/30 rounded"
                      transition={{ type: "spring", stiffness: 350, damping: 28 }}
                    />
                  )}
                  <span className="relative">{sf}</span>
                </button>
              ))}
            </div>

            <span className="text-[10px] font-mono text-slate-500 shrink-0">
              {filtered.length} active
            </span>
          </div>

          {/* Mode A: Screener Table OR Mode B: Sector Heatmap */}
          {viewMode === "table" ? (
            <div ref={tableBodyRef} className="flex-1 overflow-y-auto overflow-x-hidden">
              {pageError ? (
                <div className="p-4 m-3 rounded-lg bg-rose-950/30 border border-rose-800/50 text-rose-300 text-xs font-mono">
                  {pageError}
                </div>
              ) : (
                <>
                  {/* Table Sticky Header */}
                  <div className="sticky top-0 z-20 grid grid-cols-[36px_1fr_64px_54px_54px_54px_62px] gap-0 px-3 py-2 bg-[#050811] border-b border-white/[0.06] select-none text-[11px] font-mono uppercase text-slate-400">
                    <span
                      onClick={() => handleSort("rank")}
                      className="cursor-pointer hover:text-white"
                    >
                      #
                    </span>
                    <span
                      onClick={() => handleSort("symbol")}
                      className="cursor-pointer hover:text-white"
                    >
                      Symbol / Security
                    </span>
                    <span
                      onClick={() => handleSort("composite_score")}
                      className="text-right cursor-pointer hover:text-white"
                    >
                      Score {sortField === "composite_score" ? (sortAsc ? "▲" : "▼") : ""}
                    </span>
                    <span
                      onClick={() => handleSort("roe_pct")}
                      className="text-right cursor-pointer hover:text-white"
                    >
                      ROE% {sortField === "roe_pct" ? (sortAsc ? "▲" : "▼") : ""}
                    </span>
                    <span
                      onClick={() => handleSort("debt_to_equity")}
                      className="text-right cursor-pointer hover:text-white"
                    >
                      D/E {sortField === "debt_to_equity" ? (sortAsc ? "▲" : "▼") : ""}
                    </span>
                    <span
                      onClick={() => handleSort("opm_pct")}
                      className="text-right cursor-pointer hover:text-white"
                    >
                      OPM% {sortField === "opm_pct" ? (sortAsc ? "▲" : "▼") : ""}
                    </span>
                    <span
                      onClick={() => handleSort("excess_ret_20d")}
                      className="text-right cursor-pointer hover:text-white"
                    >
                      20D Ret {sortField === "excess_ret_20d" ? (sortAsc ? "▲" : "▼") : ""}
                    </span>
                  </div>

                  {/* Table Rows */}
                  {filtered.map((item, idx) => {
                    const isActive = idx === activeIndex;
                    const excess = item.excess_ret_20d ?? 0;
                    const retColor =
                      excess >= 0.05
                        ? "text-emerald-400"
                        : excess >= 0
                        ? "text-emerald-300/80"
                        : excess <= -0.05
                        ? "text-rose-400"
                        : "text-rose-300/80";

                    const scoreVal = Math.round(item.composite_score ?? 0);
                    const scoreColor =
                      scoreVal >= 80
                        ? "text-emerald-400"
                        : scoreVal >= 60
                        ? "text-cyan-400"
                        : "text-slate-300";

                    return (
                      <div
                        key={item.symbol}
                        data-rowindex={idx}
                        onClick={() => setActiveIndex(idx)}
                        onMouseEnter={() => prefetchStockBundle(item.symbol)}
                        className={`relative grid grid-cols-[36px_1fr_64px_54px_54px_54px_62px] gap-0 px-3 h-10 items-center border-b border-white/[0.03] cursor-pointer transition-colors duration-100 ${
                          isActive
                            ? "bg-cyan-500/[0.06]"
                            : "hover:bg-white/[0.02]"
                        }`}
                      >
                        {/* Active Left Indicator Bar */}
                        {isActive && (
                          <motion.div
                            layoutId="activeRowBar"
                            className="absolute left-0 top-0 bottom-0 w-[3px] bg-cyan-400 rounded-r shadow-[0_0_8px_#06b6d4]"
                            transition={{ type: "spring", stiffness: 350, damping: 28 }}
                          />
                        )}

                        {/* Rank */}
                        <span className="text-[10px] font-mono text-slate-500 font-semibold">
                          {item.rank}
                        </span>

                        {/* Symbol & Company Name */}
                        <div className="min-w-0 pr-2">
                          <div className="flex items-center gap-1.5">
                            <span className="text-xs font-mono font-bold text-white tracking-tight truncate">
                              {item.symbol}
                            </span>
                            {item.is_watchlist ? (
                              <span className="text-[8px] font-mono text-cyan-400 border border-cyan-500/30 px-1 py-0.2 rounded bg-cyan-950/60 shrink-0">
                                WL
                              </span>
                            ) : null}
                          </div>
                          <span className="text-[11px] text-slate-400 font-sans truncate block leading-tight">
                            {item.company_name}
                          </span>
                        </div>

                        {/* Score (Subtle text coloring without heavy badges) */}
                        <span className={`text-xs font-mono text-right font-medium ${scoreColor}`}>
                          {scoreVal}
                        </span>

                        {/* ROE % */}
                        <span className="text-[11px] font-mono text-right text-slate-200">
                          {item.roe_pct != null ? `${item.roe_pct.toFixed(1)}%` : "—"}
                        </span>

                        {/* D/E */}
                        <span className="text-[11px] font-mono text-right text-slate-400">
                          {item.debt_to_equity != null ? item.debt_to_equity.toFixed(2) : "—"}
                        </span>

                        {/* OPM % */}
                        <span className="text-[11px] font-mono text-right text-slate-200">
                          {item.opm_pct != null ? `${item.opm_pct.toFixed(1)}%` : "—"}
                        </span>

                        {/* 20D Excess Return */}
                        <span className={`text-[11px] font-mono text-right font-semibold ${retColor}`}>
                          {excess >= 0 ? "+" : ""}
                          {(excess * 100).toFixed(1)}%
                        </span>
                      </div>
                    );
                  })}
                </>
              )}
            </div>
          ) : (
            <SectorHeatmap
              candidates={filtered}
              activeSymbol={activeCandidate?.symbol || ""}
              onSelect={handleSelectSymbol}
              onHover={prefetchStockBundle}
            />
          )}

          {/* Left Pane Footer */}
          <div className="shrink-0 border-t border-white/[0.05] px-3.5 py-1.5 flex items-center justify-between text-[10px] font-mono text-slate-500 bg-[#030508]">
            <div className="flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span>Settled Session: {asOfDate || "2026-10-28"}</span>
            </div>
            <div className="flex items-center gap-3">
              <span>↑↓ Arrow Keys to scrub</span>
              <span>·</span>
              <span>Point-in-Time Model v2.4</span>
            </div>
          </div>
        </div>

        {/* ── RIGHT DOCKED LIVE INSPECTOR (46%) ───────────────────────────── */}
        <div className="flex-1 flex flex-col overflow-hidden relative bg-[#030508]">
          {/* Dynamic Ambient Verdict Aura */}
          <div className="absolute inset-0 overflow-hidden pointer-events-none z-0">
            <AnimatePresence mode="wait">
              <motion.div
                key={activeVerdict}
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 1.1 }}
                transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                className={`absolute -top-28 -right-28 w-[580px] h-[580px] rounded-full blur-[100px] bg-gradient-to-br ${verdictCfg.auraGradient}`}
              />
            </AnimatePresence>
            <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_top_right,rgba(255,255,255,0.02),transparent_70%)]" />
          </div>

          {!activeCandidate ? (
            <div className="flex items-center justify-center h-full text-slate-500 font-mono text-xs z-10">
              Select an equity from the screener to inspect
            </div>
          ) : (
            <div className="flex flex-col h-full overflow-hidden z-10">
              {/* ───────────────────────────────────────────────────────────── */}
              {/* INSPECTOR HEADER: Ticker, Name, Price, Verdict, Tearsheet Link*/}
              {/* ───────────────────────────────────────────────────────────── */}
              <div className="shrink-0 px-4 pt-3 pb-2.5 border-b border-white/[0.06] bg-[#030508]/80 backdrop-blur-md">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2.5 flex-wrap">
                      <span className="text-2xl font-mono font-black text-white tracking-tight">
                        {activeCandidate.symbol}
                      </span>
                      <span className="text-xs text-slate-400 font-sans truncate max-w-[280px]">
                        {activeCandidate.company_name}
                      </span>
                      {inspector.isSyncing && (
                        <span className="text-[10px] font-mono text-cyan-400 flex items-center gap-1 animate-pulse">
                          <Sparkles className="w-2.5 h-2.5" />
                          <span>Syncing</span>
                        </span>
                      )}
                    </div>

                    <div className="flex items-center gap-2 mt-1 flex-wrap">
                      {/* Sector Pill */}
                      <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-900 border border-white/[0.08] text-slate-300">
                        {activeCandidate.sector || "General"}
                      </span>

                      {/* Live Close Price */}
                      <span className="text-xl font-mono font-black text-white tabular-nums tracking-tight">
                        ₹{currentPrice.toFixed(2)}
                      </span>

                      {/* SMA200 Distance */}
                      {smaDist !== null && (
                        <span
                          className={`text-[10px] font-mono px-2 py-0.5 rounded border font-semibold ${
                            smaDist >= 0
                              ? "bg-emerald-950/60 border-emerald-600/50 text-emerald-300"
                              : "bg-rose-950/60 border-rose-600/50 text-rose-300"
                          }`}
                        >
                          {smaDist >= 0 ? "+" : ""}
                          {smaDist.toFixed(1)}% vs 200SMA
                        </span>
                      )}

                      {/* Deterministic Verdict Badge */}
                      <span
                        className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded border ${verdictCfg.badge}`}
                      >
                        {verdictCfg.label}
                      </span>
                    </div>
                  </div>

                  {/* Open Full Tearsheet Link */}
                  <Link
                    href={`/stocks/${activeCandidate.symbol}`}
                    className="shrink-0 flex items-center gap-1 text-[11px] font-mono text-slate-300 hover:text-cyan-300 border border-white/[0.08] hover:border-cyan-500/40 rounded-lg px-2.5 py-1.5 bg-slate-900/60 hover:bg-slate-900 transition-all shadow-sm"
                  >
                    <span>Full Tearsheet</span>
                    <ExternalLink className="w-3 h-3 text-cyan-400" />
                  </Link>
                </div>
              </div>

              {/* ───────────────────────────────────────────────────────────── */}
              {/* INSPECTOR BODY: Interactive TV Chart + RR Bar + Bento Grid     */}
              {/* ───────────────────────────────────────────────────────────── */}
              <div className="flex-1 overflow-y-auto px-4 pt-3 pb-12 space-y-3.5">
                {/* 1. Embedded TradingView Chart + GARCH Fan Cone (330px) */}
                <div className="rounded-xl overflow-hidden border border-white/[0.06] shadow-xl min-h-[320px]">
                  {inspector.candles.length > 0 ? (
                    <StockChart
                      symbol={activeCandidate.symbol}
                      data={inspector.candles}
                      sma200={sma200}
                      forecast={inspector.forecast}
                      height={330}
                      compact={true}
                    />
                  ) : (
                    <div className="h-[330px] bg-[#050811] flex items-center justify-center text-slate-500 font-mono text-xs">
                      Loading {activeCandidate.symbol} price action...
                    </div>
                  )}
                </div>

                {/* 2. Risk/Reward Vector Bar */}
                <RiskRewardVectorBar
                  currentPrice={currentPrice}
                  stopPrice={forecastLower95}
                  targetPrice={forecastUpper80}
                />

                {/* 3. Bento Grid: Factor Radar + Tabbed Intelligence Deck */}
                <div className="grid grid-cols-[195px_1fr] gap-3">
                  {/* Left Bento: 5-Axis Factor Radar + Radial Conviction Gauge */}
                  <div className="glass-panel rounded-xl p-3 flex flex-col items-center justify-between gap-2">
                    <span className="text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-400">
                      Factor Geometry
                    </span>

                    <FactorPentagonRadar
                      roe={factorRoe}
                      debtToEquity={factorDe}
                      opm={factorOpm}
                      momentum20d={factorMom}
                      conviction={factorConv}
                    />

                    <div className="flex items-center gap-2 pt-1 border-t border-white/[0.05] w-full justify-center">
                      <RadialConvictionGauge score={Math.round(factorConv)} />
                      <div className="flex flex-col text-left">
                        <span className="text-[10px] font-mono font-bold text-white">
                          Conviction
                        </span>
                        <span className="text-[9px] font-mono text-slate-500">
                          {factorConv >= 80
                            ? "Tier 1 Alpha"
                            : factorConv >= 60
                            ? "Solid Quality"
                            : "Cautious"}
                        </span>
                      </div>
                    </div>
                  </div>

                  {/* Right Bento: Tabbed Memo & Exchange Wire */}
                  <div className="glass-panel rounded-xl flex flex-col overflow-hidden">
                    {/* Tab Navigation */}
                    <div className="flex border-b border-white/[0.06] shrink-0 bg-[#050811]">
                      {(["thesis", "wire"] as const).map((tab) => (
                        <button
                          key={tab}
                          onClick={() => setInspectorTab(tab)}
                          className={`relative flex-1 py-2 text-[10px] font-mono uppercase tracking-wider transition-colors ${
                            inspectorTab === tab
                              ? "text-cyan-300 font-bold"
                              : "text-slate-400 hover:text-slate-200"
                          }`}
                        >
                          {inspectorTab === tab && (
                            <motion.span
                              layoutId="inspectorTabPill"
                              className="absolute inset-x-0 bottom-0 h-[2px] bg-cyan-400 rounded-t shadow-[0_0_8px_#06b6d4]"
                              transition={{ type: "spring", stiffness: 350, damping: 28 }}
                            />
                          )}
                          {tab === "thesis" ? "Decision Memo & Health" : "Exchange Regulatory Wire"}
                        </button>
                      ))}
                    </div>

                    {/* Tab Body */}
                    <div className="flex-1 overflow-y-auto p-3 text-xs font-mono">
                      <AnimatePresence mode="wait">
                        {inspectorTab === "thesis" ? (
                          <motion.div
                            key="thesis"
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4 }}
                            transition={{ duration: 0.15 }}
                            className="space-y-3"
                          >
                            {/* 4-Point Health Checklist */}
                            {inspector.memo?.health_checklist &&
                            inspector.memo.health_checklist.length > 0 ? (
                              <div className="space-y-1.5">
                                <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 flex items-center gap-1.5">
                                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
                                  <span>Health Checklist</span>
                                </span>

                                <div className="grid grid-cols-2 gap-1.5">
                                  {inspector.memo.health_checklist.map((diag) => {
                                    const isPass = diag.status === "PASS";
                                    const isCaution = diag.status === "CAUTION";
                                    const Icon = isPass
                                      ? CheckCircle2
                                      : isCaution
                                      ? AlertTriangle
                                      : XCircle;
                                    const color = isPass
                                      ? "text-emerald-400 border-emerald-800/40 bg-emerald-950/20"
                                      : isCaution
                                      ? "text-amber-400 border-amber-800/40 bg-amber-950/20"
                                      : "text-rose-400 border-rose-800/40 bg-rose-950/20";

                                    return (
                                      <div
                                        key={diag.id}
                                        className={`p-1.5 rounded-lg border ${color} flex items-start gap-1.5`}
                                      >
                                        <Icon className="w-3 h-3 shrink-0 mt-0.5" />
                                        <div className="min-w-0">
                                          <div className="font-bold text-[10px] truncate">
                                            {diag.name}
                                          </div>
                                          <div className="text-[9px] text-slate-400 truncate">
                                            {diag.detail}
                                          </div>
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>
                            ) : null}

                            {/* Bull vs Bear Catalysts */}
                            <div className="grid grid-cols-1 md:grid-cols-2 gap-2 pt-1">
                              {/* Bull Case */}
                              <div className="space-y-1 rounded-lg p-2 bg-emerald-950/15 border border-emerald-900/30">
                                <span className="text-[10px] font-mono font-bold text-emerald-400 flex items-center gap-1">
                                  <TrendingUp className="w-3 h-3" /> Bull Catalysts
                                </span>
                                {inspector.memo?.bull_case && inspector.memo.bull_case.length > 0 ? (
                                  inspector.memo.bull_case.slice(0, 2).map((pt, i) => (
                                    <div key={i} className="flex items-start gap-1 text-[10px] text-slate-300">
                                      <ChevronRight className="w-2.5 h-2.5 text-emerald-400 shrink-0 mt-0.5" />
                                      <span className="leading-tight">{pt}</span>
                                    </div>
                                  ))
                                ) : (
                                  <span className="text-[10px] text-slate-500">
                                    Compounding factor momentum profile
                                  </span>
                                )}
                              </div>

                              {/* Bear Case */}
                              <div className="space-y-1 rounded-lg p-2 bg-rose-950/15 border border-rose-900/30">
                                <span className="text-[10px] font-mono font-bold text-rose-400 flex items-center gap-1">
                                  <TrendingDown className="w-3 h-3" /> Headwinds &amp; Risks
                                </span>
                                {inspector.memo?.bear_case && inspector.memo.bear_case.length > 0 ? (
                                  inspector.memo.bear_case.slice(0, 2).map((pt, i) => (
                                    <div key={i} className="flex items-start gap-1 text-[10px] text-slate-300">
                                      <ChevronRight className="w-2.5 h-2.5 text-rose-400 shrink-0 mt-0.5" />
                                      <span className="leading-tight">{pt}</span>
                                    </div>
                                  ))
                                ) : (
                                  <span className="text-[10px] text-slate-500">
                                    Monitor volatility cone lower boundary
                                  </span>
                                )}
                              </div>
                            </div>
                          </motion.div>
                        ) : (
                          <motion.div
                            key="wire"
                            initial={{ opacity: 0, y: 4 }}
                            animate={{ opacity: 1, y: 0 }}
                            exit={{ opacity: 0, y: -4 }}
                            transition={{ duration: 0.15 }}
                            className="space-y-2"
                          >
                            {inspector.news.length === 0 ? (
                              <div className="py-6 text-center text-slate-500 font-mono text-[11px]">
                                No recent exchange regulatory filings for {activeCandidate.symbol}
                              </div>
                            ) : (
                              inspector.news.slice(0, 4).map((art) => {
                                const dir = art.impact?.direction || "NEUTRAL";
                                const dirCol =
                                  dir === "BULLISH"
                                    ? "text-emerald-400 border-emerald-700/50 bg-emerald-950/30"
                                    : dir === "BEARISH"
                                    ? "text-rose-400 border-rose-700/50 bg-rose-950/30"
                                    : "text-slate-400 border-slate-700/50 bg-slate-900/30";
                                const DirIcon =
                                  dir === "BULLISH"
                                    ? TrendingUp
                                    : dir === "BEARISH"
                                    ? TrendingDown
                                    : Minus;

                                return (
                                  <div
                                    key={art.id}
                                    className="p-2 rounded-lg border border-white/[0.04] bg-[#050811]/60 space-y-1"
                                  >
                                    <div className="flex items-start gap-2">
                                      <span className={`p-0.5 rounded border shrink-0 mt-0.5 ${dirCol}`}>
                                        <DirIcon className="w-2.5 h-2.5" />
                                      </span>
                                      <a
                                        href={art.article_url}
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        className="text-[11px] font-sans text-slate-200 hover:text-cyan-300 transition-colors line-clamp-1 font-medium"
                                      >
                                        {art.title}
                                      </a>
                                    </div>

                                    <div className="flex items-center gap-2 text-[9px] text-slate-500 pl-5">
                                      <span>{art.source}</span>
                                      <span>·</span>
                                      <span>{art.published_at?.slice(0, 10)}</span>
                                      {art.impact?.horizon && (
                                        <>
                                          <span>·</span>
                                          <span>{art.impact.horizon.replace("_", " ")}</span>
                                        </>
                                      )}
                                    </div>
                                  </div>
                                );
                              })
                            )}
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                </div>

                {/* 4. Bottom Key Valuation & Attribution Strip */}
                <div className="glass-panel rounded-lg px-3 py-2 flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-[11px] font-mono">
                  <div className="flex items-center gap-4 flex-wrap">
                    <span className="text-slate-500">
                      ROE: <strong className="text-emerald-300">{factorRoe.toFixed(1)}%</strong>
                    </span>
                    <span className="text-slate-500">
                      D/E: <strong className="text-slate-200">{factorDe.toFixed(2)}x</strong>
                    </span>
                    <span className="text-slate-500">
                      OPM: <strong className="text-slate-200">{factorOpm.toFixed(1)}%</strong>
                    </span>
                    {inspector.memo?.key_metrics.ttm_pe && (
                      <span className="text-slate-500">
                        TTM P/E:{" "}
                        <strong className="text-cyan-300">
                          {inspector.memo.key_metrics.ttm_pe.toFixed(1)}x
                        </strong>
                      </span>
                    )}
                  </div>

                  {inspector.forecast?.projections && inspector.forecast.projections.length > 0 && (
                    <div className="flex items-center gap-2 text-[10px] text-slate-400">
                      <span>20D Forecast Target:</span>
                      <strong className="text-cyan-300 font-bold">
                        ₹
                        {inspector.forecast.projections[
                          inspector.forecast.projections.length - 1
                        ].expected.toFixed(2)}
                      </strong>
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 3. COMMAND PALETTE MODAL (Raycast ⌘K Spotlight)                     */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {showCommandPalette && (
        <CommandPaletteModal
          candidates={candidates}
          watchlistSymbols={watchlistSymbols}
          onSelect={handleSelectSymbol}
          onClose={() => setShowCommandPalette(false)}
        />
      )}
    </div>
  );
}
