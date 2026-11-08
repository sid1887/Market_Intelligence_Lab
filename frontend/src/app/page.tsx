"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import {
  RefreshCw,
  Command,
  PanelRightOpen,
  Loader2,
  Zap,
  BrainCircuit,
  LayoutDashboard,
  Briefcase,
  LineChart,
} from "lucide-react";
import {
  apiFetch,
  prefetchStockBundle,
  ScreenerCandidate,
  ScreenerResponse,
  WatchlistResponse,
  triggerSystemIngest,
  clearMemoryCache,
} from "@/lib/api";
import { usePlatformEvents } from "@/hooks/usePlatformEvents";
import MacroRibbon from "@/components/MacroRibbon";
import IngestionProgressBanner from "@/components/IngestionProgressBanner";
import ScreenerWorkspace from "@/components/ScreenerWorkspace";
import StockInspector from "@/components/StockInspector";
import CopilotDrawer from "@/components/CopilotDrawer";
import { CommandPaletteModal } from "@/components/CommandPaletteModal";

export default function CockpitPage() {
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"table" | "heatmap">("table");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [isInspectorCollapsed, setIsInspectorCollapsed] = useState<boolean>(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);

  // 1. Unified Real-Time Event Hub
  const {
    macroData,
    supervisorStatus,
    activeJob,
    isConnected,
    lastTickAt,
    dismissActiveJob,
    setActiveJob,
  } = usePlatformEvents();

  // 2. Initial Screener & Watchlist Data Fetch
  const loadPageData = useCallback(async (invalidateCache: boolean = false) => {
    setPageLoading(true);
    if (invalidateCache) {
      clearMemoryCache();
    }
    try {
      const [scrRes, wlRes] = await Promise.allSettled([
        apiFetch<ScreenerResponse>("/screener?limit=250", !invalidateCache),
        apiFetch<WatchlistResponse>("/watchlist", !invalidateCache),
      ]);

      if (scrRes.status === "fulfilled") {
        const results = scrRes.value.results || [];
        setCandidates(results);
        if (scrRes.value.as_of_date) {
          setAsOfDate(scrRes.value.as_of_date);
        }
        if (results.length > 0 && !selectedSymbol) {
          setSelectedSymbol(results[0].symbol);
        }
        // Prefetch first 6 stocks for instant switching
        results.slice(0, 6).forEach((c) => prefetchStockBundle(c.symbol));
      }

      if (wlRes.status === "fulfilled") {
        setWatchlistSymbols((wlRes.value.watchlist || []).map((w) => w.symbol));
      }
    } catch (err) {
      console.error("Cockpit initial load error:", err);
    } finally {
      setPageLoading(false);
    }
  }, [selectedSymbol]);

  useEffect(() => {
    void loadPageData();
  }, [loadPageData]);

  // Active Candidate lookup
  const activeCandidate = useMemo(() => {
    if (!selectedSymbol || !candidates.length) return null;
    return candidates.find((c) => c.symbol === selectedSymbol) || null;
  }, [candidates, selectedSymbol]);

  // 3. Universal Ingest Action
  const handleUniversalIngest = async () => {
    if (isIngesting) return;
    setIsIngesting(true);
    setActiveJob({
      job_id: `sys-ingest-${Date.now()}`,
      stage: "FETCHING_NSE_SETTLEMENT",
      progress_pct: 15,
      status: "RUNNING",
      message: "Fetching live bhavcopy and corporate actions...",
    });

    try {
      const res = await triggerSystemIngest();
      setActiveJob({
        job_id: `sys-ingest-${Date.now()}`,
        stage: "COMPLETED",
        progress_pct: 100,
        status: "SUCCEEDED",
        message: `Settled ${res.symbols_updated || "universe"} equities for session ${res.settled_date || "today"}.`,
      });
      clearMemoryCache();
      await loadPageData();
    } catch (err: unknown) {
      setActiveJob({
        job_id: `sys-ingest-err-${Date.now()}`,
        stage: "FAILED",
        progress_pct: 100,
        status: "FAILED",
        error: err instanceof Error ? err.message : "Ingestion failed",
      });
    } finally {
      setIsIngesting(false);
    }
  };

  // Keyboard shortcut for command palette (⌘K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowCommandPalette((prev) => !prev);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-[#030508] bg-grid-pattern relative select-none text-slate-100 font-sans">
      {/* Ambient Radial Neon Bleeds */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-emerald-500/5 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-500/5 rounded-full blur-[128px] pointer-events-none" />

      {/* ──────────────── 1. TOP HEADER NAVIGATION ──────────────── */}
      <header className="h-12 shrink-0 border-b border-white/[0.06] flex items-center justify-between px-3 sm:px-4 bg-[#030508]/95 backdrop-blur-md z-30">
        {/* Left: Brand + Navigation Tabs */}
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1.5 shrink-0">
            <span className="w-2 h-2 rounded-sm bg-cyan-400 shadow-[0_0_6px_#06b6d4]" />
            <span className="text-sm font-mono font-bold text-white tracking-tight">
              MIL<span className="hidden xl:inline"> — MARKET INTELLIGENCE LAB</span>
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 hidden sm:inline">
              PRO
            </span>
          </div>

          {/* Navigation Links */}
          <nav className="flex items-center gap-1">
            <Link
              href="/"
              className="px-2.5 py-1 rounded-md text-xs font-mono font-semibold bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 flex items-center gap-1.5 transition-colors"
            >
              <LayoutDashboard className="w-3.5 h-3.5 text-cyan-400" />
              <span>Screener</span>
            </Link>

            <Link
              href="/portfolio"
              className="px-2.5 py-1 rounded-md text-xs font-mono text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent hover:border-white/[0.06] flex items-center gap-1.5 transition-colors"
            >
              <Briefcase className="w-3.5 h-3.5 text-slate-400" />
              <span>Portfolio</span>
            </Link>

            <Link
              href="/backtest"
              className="px-2.5 py-1 rounded-md text-xs font-mono text-slate-400 hover:text-slate-200 hover:bg-slate-900 border border-transparent hover:border-white/[0.06] flex items-center gap-1.5 transition-colors"
            >
              <LineChart className="w-3.5 h-3.5 text-slate-400" />
              <span>Backtest</span>
            </Link>
          </nav>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => void loadPageData(true)}
            disabled={pageLoading || isIngesting}
            title="Force refresh universe and invalidate cache"
            className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-slate-800/60 border border-white/[0.06] transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${pageLoading ? "animate-spin text-cyan-400" : ""}`} />
          </button>

          <button
            onClick={() => setShowCommandPalette(true)}
            className="flex items-center gap-1.5 text-xs font-mono text-slate-400 px-2.5 py-1 rounded-lg bg-slate-900/60 border border-white/[0.06] hover:border-cyan-500/30 hover:text-slate-200 transition-colors"
          >
            <Command className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline">Search</span>
            <kbd className="text-[10px] font-mono text-slate-500 bg-slate-800/80 px-1 rounded border border-white/[0.04]">⌘K</kbd>
          </button>

          <button
            onClick={handleUniversalIngest}
            disabled={isIngesting || pageLoading}
            title="Execute Dynamic Ingestion for live NSE settlement"
            className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/80 text-emerald-300 border border-emerald-600/40 hover:border-emerald-500 text-xs font-mono font-medium transition-all shadow-sm disabled:opacity-60 whitespace-nowrap"
          >
            {isIngesting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                <span className="animate-pulse">Ingesting...</span>
              </>
            ) : (
              <>
                <Zap className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden sm:inline">Dynamic Ingest</span>
                <span className="sm:hidden">Ingest</span>
              </>
            )}
          </button>

          <button
            onClick={() => {
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true }));
            }}
            title="Open Quant Copilot Committee (⌘J)"
            className="flex items-center gap-1.5 text-xs font-mono text-cyan-300 px-2.5 py-1 rounded-lg bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-700/50 hover:border-cyan-400 transition-colors whitespace-nowrap"
          >
            <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
            <span>Copilot</span>
            <kbd className="text-[10px] text-cyan-400/80 bg-slate-900 px-1 rounded border border-cyan-500/30">⌘J</kbd>
          </button>

          {isInspectorCollapsed && (
            <button
              onClick={() => setIsInspectorCollapsed(false)}
              title="Expand Details Inspector"
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-800/60 rounded-lg transition-colors"
            >
              <PanelRightOpen className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden lg:inline">Inspect {selectedSymbol || "Stock"}</span>
            </button>
          )}
        </div>
      </header>

      {/* ──────────────── 2. DEDICATED TELEMETRY SUB-BAR ──────────────── */}
      <div className="h-8 shrink-0 border-b border-white/[0.04] bg-[#020306] px-3 sm:px-4 flex items-center overflow-x-auto scrollbar-none z-20">
        <MacroRibbon
          macroData={macroData}
          supervisorStatus={supervisorStatus}
          isConnected={isConnected}
          lastTickAt={lastTickAt}
        />
      </div>

      {/* ──────────────── 2. REAL-TIME INGESTION BANNER ──────────────── */}
      <IngestionProgressBanner activeJob={activeJob} onDismiss={dismissActiveJob} />

      {/* ──────────────── 3. SPLIT-PANE WORKBENCH ──────────────── */}
      <div className="flex flex-1 overflow-hidden relative z-10">
        {/* Left: Screener Workspace */}
        <div
          className={`${
            isInspectorCollapsed ? "w-full" : "hidden lg:flex w-full lg:w-[54%]"
          } flex flex-col overflow-hidden shrink-0 backdrop-blur-md bg-slate-950/75 border-r border-slate-800/80 transition-all duration-300 ease-in-out`}
        >
          <ScreenerWorkspace
            candidates={candidates}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={(sym) => {
              setSelectedSymbol(sym);
              setIsInspectorCollapsed(false);
            }}
            asOfDate={asOfDate}
            loading={pageLoading}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
          />
        </div>

        {/* Right: Stock Deep Inspector */}
        {!isInspectorCollapsed && (
          <div className="flex-1 flex flex-col overflow-hidden min-w-0 backdrop-blur-md bg-slate-950/75 transition-all duration-300 ease-in-out">
            <StockInspector
              symbol={selectedSymbol}
              activeCandidate={activeCandidate}
              onClose={() => setIsInspectorCollapsed(true)}
              onOpenCopilot={() => {
                window.dispatchEvent(
                  new KeyboardEvent("keydown", { key: "j", metaKey: true })
                );
              }}
            />
          </div>
        )}
      </div>

      {/* ──────────────── 4. MODALS & COCKPIT DRAWERS ──────────────── */}
      <CopilotDrawer
        activeSymbol={selectedSymbol || "RELIANCE"}
        activePrice={activeCandidate?.close ?? undefined}
        activeVerdict={activeCandidate?.composite_score ? (activeCandidate.composite_score >= 75 ? "STRONG_BUY_COMPOUNDER" : "HOLD_FAIRLY_VALUED") : undefined}
        showFloatingTrigger={false}
      />

      {showCommandPalette && (
        <CommandPaletteModal
          candidates={candidates}
          watchlistSymbols={watchlistSymbols}
          onSelect={(sym) => {
            setSelectedSymbol(sym);
            setIsInspectorCollapsed(false);
            setShowCommandPalette(false);
          }}
          onClose={() => setShowCommandPalette(false)}
        />
      )}
    </div>
  );
}
