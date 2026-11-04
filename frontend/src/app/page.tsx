"use client";

import React, { useEffect, useState, useCallback, useRef } from "react";
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
  Loader2,
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
} from "@/lib/api";
import StockChart from "@/components/StockChart";
import { FactorPentagonRadar } from "@/components/FactorPentagonRadar";
import { RiskRewardVectorBar } from "@/components/RiskRewardVectorBar";
import { RadialConvictionGauge } from "@/components/RadialConvictionGauge";
import { CommandPaletteModal } from "@/components/CommandPaletteModal";

// ─── Verdict Config ───────────────────────────────────────────────────────────
const VERDICT_CONFIG: Record<
  VerdictType,
  { label: string; badge: string; aura: string; horizonLabel: string }
> = {
  STRONG_BUY_COMPOUNDER: {
    label: "STRONG BUY",
    badge: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300",
    aura: "radial-gradient(ellipse at 80% 0%, rgba(16,185,129,0.14) 0%, rgba(5,8,17,0) 60%)",
    horizonLabel: "12–24 Months",
  },
  TACTICAL_SWING_LONG: {
    label: "SWING LONG",
    badge: "bg-cyan-950/80 border-cyan-500/50 text-cyan-300",
    aura: "radial-gradient(ellipse at 80% 0%, rgba(6,182,212,0.14) 0%, rgba(5,8,17,0) 60%)",
    horizonLabel: "2–8 Weeks",
  },
  HOLD_FAIRLY_VALUED: {
    label: "HOLD",
    badge: "bg-amber-950/80 border-amber-500/50 text-amber-300",
    aura: "radial-gradient(ellipse at 80% 0%, rgba(245,158,11,0.10) 0%, rgba(5,8,17,0) 60%)",
    horizonLabel: "3–6 Months",
  },
  AVOID_CAPITAL_PRESERVATION: {
    label: "AVOID",
    badge: "bg-rose-950/80 border-rose-500/50 text-rose-300",
    aura: "radial-gradient(ellipse at 80% 0%, rgba(239,68,68,0.13) 0%, rgba(5,8,17,0) 60%)",
    horizonLabel: "Capital Preservation",
  },
};

const DEFAULT_VERDICT_CFG = VERDICT_CONFIG["HOLD_FAIRLY_VALUED"];

type SectorFilter = "All" | "IT" | "Energy" | "Pharma" | "Auto" | "Financials" | "Capital Goods";
const SECTOR_FILTERS: SectorFilter[] = ["All", "IT", "Energy", "Pharma", "Auto", "Financials", "Capital Goods"];

function matchSector(item: ScreenerCandidate, filter: SectorFilter): boolean {
  if (filter === "All") return true;
  const sec = item.sector.toLowerCase();
  if (filter === "IT") return sec.includes("it") || sec.includes("tech") || sec.includes("software") || sec.includes("information");
  if (filter === "Energy") return sec.includes("energy") || sec.includes("power") || sec.includes("oil") || sec.includes("gas") || sec.includes("petro");
  if (filter === "Pharma") return sec.includes("pharma") || sec.includes("health") || sec.includes("bio");
  if (filter === "Auto") return sec.includes("auto") || sec.includes("motor") || sec.includes("vehicle");
  if (filter === "Financials") return sec.includes("financial") || sec.includes("bank") || sec.includes("insurance") || sec.includes("nbfc");
  if (filter === "Capital Goods") return sec.includes("capital") || sec.includes("industrial") || sec.includes("engineering") || sec.includes("manufactur");
  return true;
}

// ─── Inspector Data State ─────────────────────────────────────────────────────
interface InspectorData {
  symbol: string;
  candles: CandleData[];
  forecast: ForecastData | null;
  memo: InvestmentMemo | null;
  news: NewsArticle[];
  loading: boolean;
  error: string | null;
}

const EMPTY_INSPECTOR: InspectorData = {
  symbol: "",
  candles: [],
  forecast: null,
  memo: null,
  news: [],
  loading: false,
  error: null,
};

// ─── Main Page Component ──────────────────────────────────────────────────────
export default function CockpitPage() {
  // Data
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [accuracy, setAccuracy] = useState<SystemAccuracy | null>(null);
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [pageError, setPageError] = useState<string | null>(null);

  // Screener state
  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState<SectorFilter>("All");
  const [activeIndex, setActiveIndex] = useState<number>(0);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const tableBodyRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);

  // Inspector state
  const [inspector, setInspector] = useState<InspectorData>(EMPTY_INSPECTOR);
  const [inspectorTab, setInspectorTab] = useState<"thesis" | "wire">("thesis");
  const inspectorLoadingRef = useRef<string>("");

  // Filtered + sorted candidates
  const filtered = React.useMemo(() => {
    return candidates.filter((item) => {
      if (search) {
        const q = search.toLowerCase();
        if (
          !item.symbol.toLowerCase().includes(q) &&
          !item.company_name.toLowerCase().includes(q) &&
          !item.sector.toLowerCase().includes(q)
        )
          return false;
      }
      return matchSector(item, sectorFilter);
    });
  }, [candidates, search, sectorFilter]);

  const activeCandidate = filtered[activeIndex] ?? null;

  // ─── Initial Data Load ──────────────────────────────────────────────────────
  const loadPageData = useCallback(async () => {
    setPageLoading(true);
    setPageError(null);
    try {
      const [scrData, wlData, accData] = await Promise.allSettled([
        apiFetch<ScreenerResponse>("/screener?limit=250"),
        apiFetch<WatchlistResponse>("/watchlist"),
        apiFetch<SystemAccuracy>("/system/accuracy"),
      ]);

      if (scrData.status === "fulfilled") {
        setCandidates(scrData.value.results ?? []);
        setAsOfDate(scrData.value.as_of_date ?? "");
      } else {
        setPageError("Failed to load screener data.");
      }

      if (wlData.status === "fulfilled") {
        setWatchlistSymbols((wlData.value.watchlist ?? []).map((w) => w.symbol));
      }

      if (accData.status === "fulfilled") {
        setAccuracy(accData.value);
      }
    } catch (err: unknown) {
      setPageError(err instanceof Error ? err.message : "Failed to connect to FastAPI bridge.");
    } finally {
      setPageLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadPageData();
  }, [loadPageData]);

  // ─── Load Inspector for selected symbol ────────────────────────────────────
  const loadInspector = useCallback(async (symbol: string) => {
    if (!symbol) return;
    if (inspectorLoadingRef.current === symbol) return;
    inspectorLoadingRef.current = symbol;

    setInspector((prev) => ({ ...prev, symbol, loading: true, error: null }));

    try {
      const [candlesRes, forecastRes, memoRes, newsRes] = await Promise.allSettled([
        apiFetch<CandleData[]>(`/stocks/${symbol}/history`),
        apiFetch<ForecastData>(`/stocks/${symbol}/forecast`),
        apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`),
        apiFetch<NewsResponse>(`/stocks/${symbol}/news`),
      ]);

      // Only commit if still the same symbol (no race condition)
      if (inspectorLoadingRef.current !== symbol) return;

      setInspector({
        symbol,
        candles: candlesRes.status === "fulfilled" ? candlesRes.value : [],
        forecast: forecastRes.status === "fulfilled" ? forecastRes.value : null,
        memo: memoRes.status === "fulfilled" ? memoRes.value : null,
        news: newsRes.status === "fulfilled" ? (newsRes.value.articles ?? []) : [],
        loading: false,
        error: null,
      });
    } catch (err: unknown) {
      if (inspectorLoadingRef.current === symbol) {
        setInspector((prev) => ({
          ...prev,
          loading: false,
          error: err instanceof Error ? err.message : "Load error",
        }));
      }
    }
  }, []);

  // Load inspector when active candidate changes
  useEffect(() => {
    if (activeCandidate) {
      void loadInspector(activeCandidate.symbol);
    }
  }, [activeCandidate?.symbol, loadInspector]); // eslint-disable-line react-hooks/exhaustive-deps

  // Pre-load top 5 stocks after initial load
  useEffect(() => {
    if (!pageLoading && candidates.length > 0) {
      candidates.slice(0, 5).forEach((c) => prefetchStockBundle(c.symbol));
    }
  }, [pageLoading, candidates]);

  // ─── Keyboard navigation ───────────────────────────────────────────────────
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowCommandPalette(true);
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setActiveIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActiveIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Escape") {
        setShowCommandPalette(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filtered.length]);

  // Scroll active row into view
  useEffect(() => {
    const el = tableBodyRef.current?.querySelector(`[data-rowindex="${activeIndex}"]`);
    el?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex]);

  // Reset active index when filter changes
  useEffect(() => {
    setActiveIndex(0);
  }, [search, sectorFilter]);

  // ─── Inspector derived values ──────────────────────────────────────────────
  const { memo, forecast, candles, news } = inspector;
  const verdictCfg = memo ? (VERDICT_CONFIG[memo.verdict] ?? DEFAULT_VERDICT_CFG) : DEFAULT_VERDICT_CFG;
  const currentPrice = memo?.key_metrics?.current_price ?? activeCandidate?.close ?? 0;
  const sma200 = memo?.key_metrics?.sma_200 ?? activeCandidate?.sma_200 ?? null;
  const smaDist = sma200 && currentPrice ? (((currentPrice - sma200) / sma200) * 100) : null;

  const forecastLower95 = forecast?.projections?.[forecast.projections.length - 1]?.lower_95 ?? currentPrice * 0.9;
  const forecastUpper80 = forecast?.projections?.[forecast.projections.length - 1]?.upper_80 ?? currentPrice * 1.08;

  const roe = memo?.key_metrics?.roe_pct ?? activeCandidate?.roe_pct ?? 0;
  const de = memo?.key_metrics?.debt_to_equity ?? activeCandidate?.debt_to_equity ?? 0;
  const opm = memo?.key_metrics?.opm_pct ?? activeCandidate?.opm_pct ?? 0;
  const mom20d = (activeCandidate?.excess_ret_20d ?? 0) * 100;
  const conviction = memo?.institutional_conviction_score ?? activeCandidate?.composite_score ?? 50;

  // ─── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-[#030508]">

      {/* ── TOP TELEMETRY BAR ─────────────────────────────────────────────── */}
      <header className="h-11 shrink-0 border-b border-white/[0.05] flex items-center justify-between px-4 gap-3 bg-[#030508] z-30">

        {/* Brand + Status */}
        <div className="flex items-center gap-2.5 shrink-0">
          <span className="text-xs font-mono font-bold text-white tracking-tight">MIL</span>
          <span className="hidden sm:block text-[11px] font-mono text-slate-500">
            Market Intelligence Lab
          </span>
          <div className="flex items-center gap-1.5 ml-1">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
            </span>
            <span className="text-[10px] font-mono text-emerald-400 hidden sm:block">
              {pageLoading ? "Loading…" : `${candidates.length} NSE Equities`}
            </span>
          </div>
        </div>

        {/* ML Accuracy Pill */}
        {accuracy && (
          <div className="hidden md:flex items-center gap-2 px-3 py-1 rounded-full bg-slate-900/80 border border-white/[0.06] chip-specular">
            <span className="text-[10px] font-mono text-slate-400">🧠 ML Audit:</span>
            <span className="text-[10px] font-mono font-bold text-cyan-300">
              {accuracy.forecast_model.containment_80_pct.toFixed(1)}% Cone Hit Rate
            </span>
            <span className="text-[10px] text-slate-500">·</span>
            <span className="text-[10px] font-mono text-slate-400">
              {accuracy.forecast_model.rmse_pct.toFixed(2)}% RMSE
            </span>
          </div>
        )}

        {/* Right: Watchlist pills + ⌘K + Backtester */}
        <div className="flex items-center gap-2 shrink-0">
          {watchlistSymbols.slice(0, 4).map((sym) => (
            <button
              key={sym}
              onClick={() => {
                const idx = filtered.findIndex((c) => c.symbol === sym);
                if (idx >= 0) setActiveIndex(idx);
                else void loadInspector(sym);
              }}
              className="hidden sm:block text-[10px] font-mono text-slate-300 px-2 py-0.5 rounded bg-slate-900/60 border border-white/[0.06] hover:border-cyan-500/40 hover:text-cyan-300 transition-colors chip-specular"
            >
              {sym}
            </button>
          ))}

          <button
            onClick={() => setShowCommandPalette(true)}
            className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400 px-2.5 py-1 rounded-lg bg-slate-900/80 border border-white/[0.06] hover:border-white/10 transition-colors chip-specular"
          >
            <Command className="w-3 h-3" />
            <span className="hidden sm:block">⌘K</span>
          </button>

          <Link
            href="/backtest"
            className="hidden sm:flex items-center gap-1 text-[10px] font-mono text-slate-400 px-2.5 py-1 rounded-lg bg-slate-900/80 border border-white/[0.06] hover:border-white/10 transition-colors"
          >
            Backtester <ExternalLink className="w-2.5 h-2.5" />
          </Link>

          <button
            onClick={loadPageData}
            disabled={pageLoading}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-200 hover:bg-slate-800/60 transition-colors disabled:opacity-50"
            title="Sync Universe"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${pageLoading ? "animate-spin text-cyan-400" : ""}`} />
          </button>
        </div>
      </header>

      {/* ── BODY: LEFT PANE + RIGHT INSPECTOR ────────────────────────────── */}
      <div className="flex flex-1 overflow-hidden">

        {/* ── LEFT MASTER PANE (54%) ─────────────────────────────────────── */}
        <div className="w-[54%] flex flex-col border-r border-white/[0.05] overflow-hidden shrink-0">

          {/* Filter Control Strip */}
          <div className="shrink-0 border-b border-white/[0.04] px-3 py-2 flex items-center gap-2 bg-[#030508]">
            {/* Search */}
            <div className="relative flex-1 max-w-[200px]">
              <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3 h-3 text-slate-500" />
              <input
                ref={searchRef}
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Filter stocks…"
                className="w-full pl-7 pr-2 py-1 text-[11px] font-mono bg-slate-900/60 border border-white/[0.06] rounded text-slate-200 placeholder-slate-600 outline-none focus:border-cyan-500/40 focus:bg-slate-900/80 transition-colors"
              />
            </div>

            {/* Sector filter pills */}
            <div className="flex items-center gap-1 overflow-x-auto no-scrollbar">
              {SECTOR_FILTERS.map((sf) => (
                <button
                  key={sf}
                  onClick={() => setSectorFilter(sf)}
                  className={`relative shrink-0 text-[10px] font-mono px-2 py-0.5 rounded transition-colors whitespace-nowrap ${
                    sectorFilter === sf
                      ? "text-cyan-300"
                      : "text-slate-500 hover:text-slate-300"
                  }`}
                >
                  {sectorFilter === sf && (
                    <motion.span
                      layoutId="sectorPill"
                      className="absolute inset-0 bg-cyan-500/10 border border-cyan-500/25 rounded"
                    />
                  )}
                  <span className="relative">{sf}</span>
                </button>
              ))}
            </div>

            <span className="ml-auto shrink-0 text-[10px] font-mono text-slate-500">
              {filtered.length} stocks
            </span>
          </div>

          {/* Screener Table */}
          <div ref={tableBodyRef} className="flex-1 overflow-y-auto overflow-x-hidden">
            {pageLoading ? (
              <div className="flex items-center justify-center h-32 gap-2 text-slate-500 font-mono text-xs">
                <Loader2 className="w-4 h-4 animate-spin text-cyan-500" />
                Loading universe…
              </div>
            ) : pageError ? (
              <div className="p-4 m-3 rounded-lg bg-rose-950/30 border border-rose-800/50 text-rose-300 text-xs font-mono">
                {pageError}
              </div>
            ) : (
              <>
                {/* Header row */}
                <div className="sticky top-0 z-10 grid grid-cols-[32px_1fr_60px_52px_52px_52px_56px] gap-0 px-3 py-1.5 bg-[#030508] border-b border-white/[0.04]">
                  {["#", "Symbol / Name", "Score", "ROE%", "D/E", "OPM%", "20D Ret"].map((h, i) => (
                    <span
                      key={h}
                      className={`text-[9px] font-mono font-semibold uppercase tracking-widest text-slate-500 ${
                        i >= 2 ? "text-right" : ""
                      }`}
                    >
                      {h}
                    </span>
                  ))}
                </div>

                {filtered.map((item, idx) => {
                  const isActive = idx === activeIndex;
                  const excess = item.excess_ret_20d ?? 0;
                  const retColor = excess > 0.03 ? "text-emerald-400" : excess < -0.02 ? "text-rose-400" : "text-slate-400";
                  const scoreVal = item.composite_score ?? 0;
                  const scoreColor = scoreVal >= 80 ? "text-emerald-400" : scoreVal >= 60 ? "text-cyan-400" : "text-amber-400";

                  return (
                    <div
                      key={item.symbol}
                      data-rowindex={idx}
                      className={`relative grid grid-cols-[32px_1fr_60px_52px_52px_52px_56px] gap-0 px-3 h-10 items-center border-b border-white/[0.03] cursor-pointer transition-colors ${
                        isActive ? "screener-row-active" : "hover:bg-white/[0.015]"
                      }`}
                      onClick={() => setActiveIndex(idx)}
                      onMouseEnter={() => prefetchStockBundle(item.symbol)}
                    >
                      {/* Active indicator bar */}
                      {isActive && (
                        <motion.div
                          layoutId="activeRowBar"
                          className="absolute left-0 top-0 bottom-0 w-[3px] bg-cyan-400 rounded-r"
                        />
                      )}

                      {/* Rank */}
                      <span className="text-[10px] font-mono text-slate-600">{item.rank}</span>

                      {/* Symbol / Name */}
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="text-[11px] font-mono font-bold text-white tracking-tight truncate">
                            {item.symbol}
                          </span>
                          {item.is_watchlist ? (
                            <span className="text-[8px] font-mono text-cyan-400 border border-cyan-500/30 rounded px-1 shrink-0">
                              WL
                            </span>
                          ) : null}
                        </div>
                        <span className="text-[9px] text-slate-500 font-sans truncate block leading-tight">
                          {item.company_name}
                        </span>
                      </div>

                      {/* Score */}
                      <span className={`text-[11px] font-mono font-bold text-right ${scoreColor}`}>
                        {scoreVal.toFixed(0)}
                      </span>

                      {/* ROE */}
                      <span className="text-[10px] font-mono text-right text-slate-300">
                        {item.roe_pct != null ? item.roe_pct.toFixed(1) : "—"}
                      </span>

                      {/* D/E */}
                      <span className="text-[10px] font-mono text-right text-slate-400">
                        {item.debt_to_equity != null ? item.debt_to_equity.toFixed(2) : "—"}
                      </span>

                      {/* OPM */}
                      <span className="text-[10px] font-mono text-right text-slate-300">
                        {item.opm_pct != null ? item.opm_pct.toFixed(1) : "—"}
                      </span>

                      {/* 20D Excess Ret */}
                      <span className={`text-[10px] font-mono font-semibold text-right ${retColor}`}>
                        {excess >= 0 ? "+" : ""}
                        {(excess * 100).toFixed(1)}%
                      </span>
                    </div>
                  );
                })}
              </>
            )}
          </div>

          {/* Footer */}
          <div className="shrink-0 border-t border-white/[0.04] px-3 py-1.5 flex items-center justify-between">
            <span className="text-[9px] font-mono text-slate-600">
              Point-in-Time · {asOfDate} · ↑↓ navigate
            </span>
            <span className="text-[9px] font-mono text-slate-600">
              Engine v2.4 · GARCH(1,1) · Quality-Momentum
            </span>
          </div>
        </div>

        {/* ── RIGHT INSPECTOR PANE (46%) ─────────────────────────────────── */}
        <div
          className="flex-1 flex flex-col overflow-hidden relative verdict-aura"
          style={{ background: verdictCfg.aura }}
        >
          {!activeCandidate ? (
            <div className="flex items-center justify-center h-full text-slate-600 font-mono text-sm">
              Select a stock to begin inspection ↑↓
            </div>
          ) : (
            <div className="flex flex-col h-full overflow-hidden">

              {/* Inspector Header */}
              <div className="shrink-0 px-4 pt-3 pb-2 border-b border-white/[0.05]">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-baseline gap-2 flex-wrap">
                      <span className="text-xl font-mono font-black text-white tracking-tight">
                        {activeCandidate.symbol}
                      </span>
                      <span className="text-sm text-slate-400 font-sans truncate">
                        {activeCandidate.company_name}
                      </span>
                    </div>

                    <div className="flex items-center gap-2 mt-0.5 flex-wrap">
                      {/* Sector pill */}
                      <span className="text-[9px] font-mono px-1.5 py-0.5 rounded bg-slate-800/80 border border-white/[0.06] text-slate-400">
                        {activeCandidate.sector}
                      </span>

                      {/* Live price */}
                      <span className="text-base font-mono font-bold text-white tabular-nums">
                        ₹{(currentPrice).toFixed(2)}
                      </span>

                      {/* SMA200 distance */}
                      {smaDist != null && (
                        <span
                          className={`text-[10px] font-mono px-1.5 py-0.5 rounded border ${
                            smaDist >= 0
                              ? "bg-emerald-950/40 border-emerald-700/40 text-emerald-400"
                              : "bg-rose-950/40 border-rose-700/40 text-rose-400"
                          }`}
                        >
                          {smaDist >= 0 ? "+" : ""}
                          {smaDist.toFixed(1)}% vs 200SMA
                        </span>
                      )}

                      {/* Verdict */}
                      {memo && (
                        <span
                          className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${verdictCfg.badge}`}
                        >
                          {verdictCfg.label}
                        </span>
                      )}
                    </div>
                  </div>

                  {/* Open full tearsheet */}
                  <Link
                    href={`/stocks/${activeCandidate.symbol}`}
                    className="shrink-0 flex items-center gap-1 text-[10px] font-mono text-slate-400 hover:text-cyan-300 border border-white/[0.06] hover:border-cyan-500/30 rounded px-2 py-1 transition-colors"
                  >
                    Full Tearsheet <ExternalLink className="w-2.5 h-2.5" />
                  </Link>
                </div>
              </div>

              {/* Scrollable inspector body */}
              <div className="flex-1 overflow-y-auto px-4 pb-4 space-y-3 pt-3">

                {inspector.loading && inspector.symbol === activeCandidate.symbol ? (
                  <div className="flex items-center justify-center h-32 gap-2 text-slate-500 font-mono text-xs">
                    <Loader2 className="w-4 h-4 animate-spin text-cyan-500" />
                    Loading {activeCandidate.symbol}…
                  </div>
                ) : (
                  <>
                    {/* TradingView Chart */}
                    {candles.length > 0 ? (
                      <div className="rounded-xl overflow-hidden border border-white/[0.05]">
                        <StockChart
                          symbol={activeCandidate.symbol}
                          data={candles}
                          sma200={sma200}
                          forecast={forecast}
                        />
                      </div>
                    ) : (
                      <div className="h-[220px] rounded-xl bg-slate-900/40 border border-white/[0.04] flex items-center justify-center text-slate-600 text-xs font-mono">
                        No chart data available
                      </div>
                    )}

                    {/* Risk/Reward Vector Bar */}
                    {currentPrice > 0 && (
                      <RiskRewardVectorBar
                        currentPrice={currentPrice}
                        stopPrice={forecastLower95}
                        targetPrice={forecastUpper80}
                      />
                    )}

                    {/* Bento Grid: Factor Radar + Tabbed Intelligence */}
                    <div className="grid grid-cols-[180px_1fr] gap-3">

                      {/* Factor Pentagon + Conviction Gauge */}
                      <div className="glass-panel rounded-xl p-3 flex flex-col items-center gap-2">
                        <span className="text-[9px] font-mono uppercase tracking-widest text-slate-500">
                          5-Factor Profile
                        </span>
                        <FactorPentagonRadar
                          roe={roe ?? 0}
                          debtToEquity={de ?? 0}
                          opm={opm ?? 0}
                          momentum20d={mom20d}
                          conviction={conviction ?? 50}
                        />
                        <div className="flex flex-col items-center gap-0.5">
                          <RadialConvictionGauge score={Math.round(conviction ?? 50)} />
                          <span className="text-[9px] font-mono text-slate-500 mt-0.5">
                            Conviction Score
                          </span>
                        </div>
                      </div>

                      {/* Right bento: Tabbed intelligence */}
                      <div className="glass-panel rounded-xl flex flex-col overflow-hidden">
                        {/* Tab bar */}
                        <div className="flex border-b border-white/[0.05] shrink-0">
                          {(["thesis", "wire"] as const).map((tab) => (
                            <button
                              key={tab}
                              onClick={() => setInspectorTab(tab)}
                              className={`relative flex-1 py-2 text-[10px] font-mono uppercase tracking-wider transition-colors ${
                                inspectorTab === tab ? "text-cyan-300" : "text-slate-500 hover:text-slate-300"
                              }`}
                            >
                              {inspectorTab === tab && (
                                <motion.span
                                  layoutId="inspectorTabPill"
                                  className="absolute inset-x-0 bottom-0 h-[2px] bg-cyan-400 rounded-t"
                                />
                              )}
                              {tab === "thesis" ? "Thesis & Checklist" : "Exchange Wire"}
                            </button>
                          ))}
                        </div>

                        {/* Tab content */}
                        <div className="flex-1 overflow-y-auto p-3">
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
                                {/* Health checklist */}
                                {memo?.health_checklist && memo.health_checklist.length > 0 && (
                                  <div className="space-y-1.5">
                                    <span className="text-[9px] font-mono uppercase tracking-widest text-slate-500 flex items-center gap-1.5">
                                      <ShieldCheck className="w-3 h-3 text-emerald-400" />
                                      Health Diagnostics
                                    </span>
                                    {memo.health_checklist.map((diag) => {
                                      const Icon =
                                        diag.status === "PASS"
                                          ? CheckCircle2
                                          : diag.status === "CAUTION"
                                          ? AlertTriangle
                                          : XCircle;
                                      const col =
                                        diag.status === "PASS"
                                          ? "text-emerald-400"
                                          : diag.status === "CAUTION"
                                          ? "text-amber-400"
                                          : "text-rose-400";
                                      return (
                                        <div key={diag.id} className="flex items-start gap-2">
                                          <Icon className={`w-3 h-3 ${col} shrink-0 mt-0.5`} />
                                          <div className="min-w-0">
                                            <span className={`text-[10px] font-mono font-semibold ${col}`}>
                                              {diag.name}
                                            </span>
                                            <p className="text-[9px] text-slate-500 leading-relaxed">
                                              {diag.detail}
                                            </p>
                                          </div>
                                        </div>
                                      );
                                    })}
                                  </div>
                                )}

                                {/* Bull / Bear catalysts */}
                                {memo?.bull_case && memo.bull_case.length > 0 && (
                                  <div className="space-y-1">
                                    <span className="text-[9px] font-mono uppercase tracking-widest text-emerald-500 flex items-center gap-1">
                                      <TrendingUp className="w-2.5 h-2.5" /> Bull Catalysts
                                    </span>
                                    {memo.bull_case.map((pt, i) => (
                                      <div key={i} className="flex items-start gap-1.5">
                                        <ChevronRight className="w-2.5 h-2.5 text-emerald-500 shrink-0 mt-0.5" />
                                        <p className="text-[9px] text-slate-400 leading-relaxed">{pt}</p>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {memo?.bear_case && memo.bear_case.length > 0 && (
                                  <div className="space-y-1">
                                    <span className="text-[9px] font-mono uppercase tracking-widest text-rose-500 flex items-center gap-1">
                                      <TrendingDown className="w-2.5 h-2.5" /> Bear Headwinds
                                    </span>
                                    {memo.bear_case.map((pt, i) => (
                                      <div key={i} className="flex items-start gap-1.5">
                                        <ChevronRight className="w-2.5 h-2.5 text-rose-500 shrink-0 mt-0.5" />
                                        <p className="text-[9px] text-slate-400 leading-relaxed">{pt}</p>
                                      </div>
                                    ))}
                                  </div>
                                )}

                                {!memo && !inspector.loading && (
                                  <p className="text-[10px] font-mono text-slate-500 text-center py-4">
                                    Investment memo generating…
                                  </p>
                                )}
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
                                {news.length === 0 ? (
                                  <p className="text-[10px] font-mono text-slate-500 text-center py-4">
                                    No regulatory wire items
                                  </p>
                                ) : (
                                  news.slice(0, 5).map((article) => {
                                    const dir = article.impact?.direction ?? "NEUTRAL";
                                    const dirColor =
                                      dir === "BULLISH"
                                        ? "text-emerald-400 border-emerald-700/40 bg-emerald-950/20"
                                        : dir === "BEARISH"
                                        ? "text-rose-400 border-rose-700/40 bg-rose-950/20"
                                        : "text-slate-400 border-slate-700/40 bg-slate-900/20";
                                    const DirIcon =
                                      dir === "BULLISH" ? TrendingUp : dir === "BEARISH" ? TrendingDown : Minus;

                                    return (
                                      <div
                                        key={article.id}
                                        className="border border-white/[0.04] rounded-lg p-2.5 space-y-1.5"
                                      >
                                        <div className="flex items-start gap-2">
                                          <div className={`mt-0.5 shrink-0 p-0.5 rounded border ${dirColor}`}>
                                            <DirIcon className="w-2.5 h-2.5" />
                                          </div>
                                          <a
                                            href={article.article_url}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            className="text-[10px] font-sans text-slate-200 hover:text-cyan-300 leading-snug transition-colors line-clamp-2"
                                          >
                                            {article.title}
                                          </a>
                                        </div>
                                        <div className="flex items-center gap-2 text-[8px] font-mono text-slate-500">
                                          <span>{article.source}</span>
                                          <span>·</span>
                                          <span>{article.published_at?.slice(0, 10)}</span>
                                          {article.impact?.horizon && (
                                            <>
                                              <span>·</span>
                                              <span>{article.impact.horizon.replace("_", " ")}</span>
                                            </>
                                          )}
                                        </div>
                                        {article.summary?.length > 0 && (
                                          <p className="text-[9px] text-slate-500 leading-relaxed">
                                            {article.summary[0]}
                                          </p>
                                        )}
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

                    {/* Key metrics strip */}
                    {memo && (
                      <div className="glass-panel rounded-lg px-3 py-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[10px] font-mono">
                        {[
                          ["P/E", memo.key_metrics.ttm_pe != null ? `${memo.key_metrics.ttm_pe.toFixed(1)}×` : "N/A", "text-cyan-300"],
                          ["ROE", memo.key_metrics.roe_pct != null ? `${memo.key_metrics.roe_pct.toFixed(1)}%` : "N/A", "text-emerald-300"],
                          ["D/E", memo.key_metrics.debt_to_equity != null ? `${memo.key_metrics.debt_to_equity.toFixed(2)}×` : "0.00×", "text-slate-200"],
                          ["OPM", memo.key_metrics.opm_pct != null ? `${memo.key_metrics.opm_pct.toFixed(1)}%` : "N/A", "text-slate-200"],
                          ["β60D", memo.key_metrics.beta_60d_nifty != null ? memo.key_metrics.beta_60d_nifty.toFixed(2) : "N/A", "text-slate-300"],
                          ["σ Annualized", memo.key_metrics.volatility_annualized != null ? `${(memo.key_metrics.volatility_annualized * 100).toFixed(1)}%` : "N/A", "text-slate-300"],
                        ].map(([label, val, col]) => (
                          <span key={label as string} className="text-slate-500">
                            {label}:{" "}
                            <strong className={col as string}>{val as string}</strong>
                          </span>
                        ))}
                        {memo.forecast_cone_summary && (
                          <span className="text-slate-500 ml-auto">
                            20D Expected:{" "}
                            <strong className="text-cyan-300">
                              ₹{memo.forecast_cone_summary.expected_20d_price.toFixed(2)}
                            </strong>{" "}
                            <span
                              className={
                                memo.forecast_cone_summary.upside_pct >= 0
                                  ? "text-emerald-400 font-semibold"
                                  : "text-rose-400 font-semibold"
                              }
                            >
                              ({memo.forecast_cone_summary.upside_pct >= 0 ? "+" : ""}
                              {memo.forecast_cone_summary.upside_pct.toFixed(1)}%)
                            </span>
                          </span>
                        )}
                      </div>
                    )}
                  </>
                )}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── COMMAND PALETTE MODAL ─────────────────────────────────────────── */}
      {showCommandPalette && (
        <CommandPaletteModal
          candidates={candidates}
          onSelect={(sym) => {
            const idx = filtered.findIndex((c) => c.symbol === sym);
            if (idx >= 0) setActiveIndex(idx);
            else void loadInspector(sym);
          }}
          onClose={() => setShowCommandPalette(false)}
        />
      )}
    </div>
  );
}
