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
  X,
  Bell,
  BellRing,
} from "lucide-react";
import dynamic from "next/dynamic";
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
import { checkPushSubscription } from "@/lib/pushNotifications";
import PushNotificationModal from "@/components/PushNotificationModal";
import MacroRibbon from "@/components/MacroRibbon";
import IngestionProgressBanner from "@/components/IngestionProgressBanner";
import ScreenerWorkspace from "@/components/ScreenerWorkspace";
import StockInspector from "@/components/StockInspector";
import CopilotDrawer from "@/components/CopilotDrawer";
import { CommandPaletteModal } from "@/components/CommandPaletteModal";

const TopographicBackground = dynamic(
  () => import("@/components/TopographicBackground"),
  { ssr: false }
);

export default function CockpitPage() {
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [pageLoading, setPageLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"table" | "heatmap">("table");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [isInspectorCollapsed, setIsInspectorCollapsed] = useState<boolean>(false);
  const [isMobileInspectorOpen, setIsMobileInspectorOpen] = useState<boolean>(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [isIngesting, setIsIngesting] = useState(false);
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [isPushSubscribed, setIsPushSubscribed] = useState(false);

  // 1. Unified Real-Time Event Hub
  const {
    macroData,
    supervisorStatus,
    activeJob,
    isConnected,
    lastTickAt,
    lastIngestTimestamp,
    dismissActiveJob,
    setActiveJob,
    setLastIngestTimestamp,
  } = usePlatformEvents();

  // 2. Initial Screener & Watchlist Data Fetch
  const loadPageData = useCallback(async (invalidateCache: boolean = false) => {
    setPageLoading(true);
    if (invalidateCache) {
      clearMemoryCache();
    }
    try {
      const [scrRes, wlRes] = await Promise.allSettled([
        apiFetch<ScreenerResponse>("/screener?limit=1000", !invalidateCache),
        apiFetch<WatchlistResponse>("/watchlist", !invalidateCache),
      ]);

      if (scrRes.status === "fulfilled") {
        const results = scrRes.value.results || [];
        setCandidates(results);
        if (scrRes.value.as_of_date) {
          setAsOfDate(scrRes.value.as_of_date);
        }
        setSelectedSymbol((prev) => prev || (results.length > 0 ? results[0].symbol : null));
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
  }, []);

  useEffect(() => {
    void loadPageData();
    checkPushSubscription().then((res) => {
      setIsPushSubscribed(res.isSubscribed);
    });
  }, [loadPageData]);

  // Active Candidate lookup
  const activeCandidate = useMemo(() => {
    if (!selectedSymbol || !candidates.length) return null;
    return candidates.find((c) => c.symbol === selectedSymbol) || null;
  }, [candidates, selectedSymbol]);

  // 3. Universal Ingest Action with Dynamic Animated Progress Stages
  const handleUniversalIngest = async () => {
    if (isIngesting) return;
    setIsIngesting(true);
    const jobId = `sys-ingest-${Date.now()}`;
    setActiveJob({
      job_id: jobId,
      stage: "FETCHING_NSE_SETTLEMENT",
      progress_pct: 15,
      status: "RUNNING",
      message: "Connecting to exchange feeds & bhavcopy...",
    });

    // Progressive simulated animation advancing smoothly while backend executes
    const progressInterval = setInterval(() => {
      setActiveJob((prev) => {
        if (!prev || prev.status !== "RUNNING") return prev;
        const currentPct = prev.progress_pct;
        if (currentPct < 35) {
          return {
            ...prev,
            stage: "PARALLEL_INGESTION",
            progress_pct: currentPct + 5,
            message: "Ingesting live multi-ticker bars across 16 worker threads...",
          };
        } else if (currentPct < 65) {
          return {
            ...prev,
            stage: "FACTOR_COMPUTATION",
            progress_pct: currentPct + 6,
            message: "Computing vectorized multi-horizon factors on multi-core pool...",
          };
        } else if (currentPct < 85) {
          return {
            ...prev,
            stage: "SECTOR_SENTIMENT",
            progress_pct: currentPct + 4,
            message: "Imputing hierarchical sector sentiment across universe...",
          };
        } else if (currentPct < 96) {
          return {
            ...prev,
            stage: "SYNCHRONIZING_CACHE",
            progress_pct: currentPct + 2,
            message: "Materializing screener snapshot view and cache...",
          };
        }
        return prev;
      });
    }, 450);

    try {
      const res = await triggerSystemIngest();
      clearInterval(progressInterval);
      const nowIso = new Date().toISOString();
      setLastIngestTimestamp(nowIso);

      setActiveJob({
        job_id: jobId,
        stage: "COMPLETED",
        progress_pct: 100,
        status: "SUCCEEDED",
        message: `Settled ${res.symbols_updated || "universe"} equities (${res.records_ingested || 0} bars) for session ${res.settled_date || "today"}.`,
      });

      // Auto-dismiss banner after 6 seconds on successful completion
      setTimeout(() => {
        setActiveJob((prev) => (prev?.status === "SUCCEEDED" ? null : prev));
      }, 6000);

      clearMemoryCache();
      await loadPageData();
    } catch (err: unknown) {
      clearInterval(progressInterval);
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
      {/* Immersive 3D Topographic WebGL Wave Canvas */}
      <TopographicBackground className="fixed inset-0 pointer-events-none z-0 overflow-hidden opacity-70" />

      {/* Ambient Radial Neon Bleeds */}
      <div className="absolute top-0 left-1/4 w-[500px] h-[500px] bg-emerald-500/5 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute bottom-0 right-1/4 w-[500px] h-[500px] bg-cyan-500/5 rounded-full blur-[128px] pointer-events-none" />

      {/* ──────────────── 1. TOP HEADER NAVIGATION ──────────────── */}
      <header className="h-12 shrink-0 border-b border-white/[0.06] flex items-center justify-between px-3 sm:px-4 bg-[#030508]/95 backdrop-blur-md z-30">
        {/* Left: Brand + Navigation Tabs (Desktop) */}
        <div className="flex items-center gap-3 sm:gap-4">
          <Link href="/" className="flex items-center gap-1.5 shrink-0 group">
            <span className="w-2 h-2 rounded-sm bg-cyan-400 shadow-[0_0_6px_#06b6d4] group-hover:scale-125 transition-transform" />
            <span className="text-sm font-mono font-bold text-white tracking-tight">
              MIL<span className="hidden sm:inline">.QUANT</span>
            </span>
            <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 hidden md:inline">
              PRO
            </span>
          </Link>

          {/* Desktop Navigation Links */}
          <nav className="hidden md:flex items-center gap-1">
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
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
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
            className="flex items-center gap-1.5 text-xs font-mono text-slate-400 px-2 sm:px-2.5 py-1 rounded-lg bg-slate-900/60 border border-white/[0.06] hover:border-cyan-500/30 hover:text-slate-200 transition-colors"
          >
            <Command className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline">Search</span>
            <kbd className="text-[10px] font-mono text-slate-500 bg-slate-800/80 px-1 rounded border border-white/[0.04]">⌘K</kbd>
          </button>

          <button
            onClick={() => {
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true }));
            }}
            title="Open Quant Copilot Committee (⌘J)"
            className="flex items-center gap-1.5 text-xs font-mono text-cyan-300 px-2 sm:px-2.5 py-1 rounded-lg bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-700/50 hover:border-cyan-400 transition-colors whitespace-nowrap"
          >
            <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Copilot</span>
            <kbd className="text-[10px] text-cyan-400/80 bg-slate-900 px-1 rounded border border-cyan-500/30">⌘J</kbd>
          </button>

          {/* Web Push Notification Bell */}
          <button
            onClick={() => setIsPushModalOpen(true)}
            title={
              isPushSubscribed
                ? "Mobile Web Push Connected (Causal Radar Active)"
                : "Enable Mobile Web Push & Causal Catalyst Alerts"
            }
            className="relative flex items-center justify-center p-1.5 sm:p-2 rounded-lg bg-white/[0.04] hover:bg-cyan-950/40 border border-white/[0.08] hover:border-cyan-500/40 text-slate-300 hover:text-cyan-300 transition-all shadow-sm"
          >
            {isPushSubscribed ? (
              <BellRing className="w-3.5 h-3.5 text-cyan-400" />
            ) : (
              <Bell className="w-3.5 h-3.5 text-slate-400" />
            )}
            <span className="absolute top-1 right-1 flex h-1.5 w-1.5">
              {isPushSubscribed ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-emerald-500" />
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-cyan-400/60" />
              )}
            </span>
          </button>

          {/* Dynamic Ingest (Desktop) */}
          <button
            onClick={handleUniversalIngest}
            disabled={isIngesting || pageLoading}
            title="Execute Dynamic Ingestion for live NSE settlement"
            className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/80 text-emerald-300 border border-emerald-600/40 hover:border-emerald-500 text-xs font-mono font-medium transition-all shadow-sm disabled:opacity-60 whitespace-nowrap"
          >
            {isIngesting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 animate-spin text-emerald-400" />
                <span className="animate-pulse">Ingesting...</span>
              </>
            ) : (
              <>
                <Zap className="w-3.5 h-3.5 text-emerald-400" />
                <span>Dynamic Ingest</span>
              </>
            )}
          </button>

          {isInspectorCollapsed && (
            <button
              onClick={() => setIsInspectorCollapsed(false)}
              title="Expand Details Inspector"
              className="hidden lg:flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-800/60 rounded-lg transition-colors"
            >
              <PanelRightOpen className="w-3.5 h-3.5 text-cyan-400" />
              <span>Inspect {selectedSymbol || "Stock"}</span>
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
          lastIngestTimestamp={lastIngestTimestamp}
        />
      </div>

      {/* ──────────────── 2. REAL-TIME INGESTION BANNER ──────────────── */}
      <IngestionProgressBanner activeJob={activeJob} onDismiss={dismissActiveJob} />

      {/* ──────────────── 3. RESPONSIVE MASTER-DETAIL SPLIT-PANE ──────────────── */}
      <div className="flex flex-1 overflow-hidden relative z-10 min-h-0 h-full pb-14 md:pb-0">
        {/* Master: Screener Workspace (Always full-width on mobile, 54% or 100% on desktop) */}
        <div
          className={`${
            isInspectorCollapsed ? "w-full" : "w-full lg:w-[54%]"
          } flex flex-col h-full overflow-hidden shrink-0 min-h-0 backdrop-blur-md bg-slate-950/75 border-r border-slate-800/80 transition-all duration-300 ease-in-out`}
        >
          <ScreenerWorkspace
            candidates={candidates}
            selectedSymbol={selectedSymbol}
            onSelectSymbol={(sym) => {
              setSelectedSymbol(sym);
              setIsInspectorCollapsed(false);
              setIsMobileInspectorOpen(true);
            }}
            asOfDate={asOfDate}
            loading={pageLoading}
            viewMode={viewMode}
            onViewModeChange={setViewMode}
          />
        </div>

        {/* Desktop Detail: Stock Deep Inspector (>= 1024px) */}
        {!isInspectorCollapsed && (
          <div className="hidden lg:flex flex-1 flex-col h-full overflow-hidden min-w-0 min-h-0 backdrop-blur-md bg-slate-950/75 transition-all duration-300 ease-in-out">
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

      {/* ──────────────── 4. MOBILE DETAIL SLIDE-OVER DRAWER (< 1024px) ──────────────── */}
      {isMobileInspectorOpen && selectedSymbol && (
        <div className="fixed inset-0 z-50 bg-[#040609] overflow-y-auto lg:hidden flex flex-col animate-in slide-in-from-bottom duration-200">
          {/* Sticky Mobile Back Header */}
          <div className="sticky top-0 z-50 flex items-center justify-between px-3.5 py-2.5 bg-[#060911]/95 backdrop-blur-xl border-b border-white/10 shrink-0">
            <button
              onClick={() => setIsMobileInspectorOpen(false)}
              className="flex items-center gap-1.5 text-xs font-mono text-cyan-400 hover:text-cyan-300 font-semibold px-2.5 py-1 rounded-lg bg-cyan-950/60 border border-cyan-800/50"
            >
              <span>← Back to Screener</span>
            </button>
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono font-bold text-white tracking-wider">
                {selectedSymbol}
              </span>
              <button
                onClick={() => setIsMobileInspectorOpen(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Mobile Inspector Viewport */}
          <div className="flex-1 overflow-y-auto min-h-0 pb-20">
            <StockInspector
              symbol={selectedSymbol}
              activeCandidate={activeCandidate}
              onClose={() => setIsMobileInspectorOpen(false)}
              onOpenCopilot={() => {
                window.dispatchEvent(
                  new KeyboardEvent("keydown", { key: "j", metaKey: true })
                );
              }}
            />
          </div>
        </div>
      )}

      {/* ──────────────── 5. FIXED MOBILE BOTTOM NAVIGATION BAR (< 768px) ──────────────── */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-[#040609]/95 backdrop-blur-2xl border-t border-white/[0.08] px-2 py-1.5 flex items-center justify-around pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        <Link
          href="/"
          className="flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-cyan-300 font-bold bg-cyan-950/40"
        >
          <LayoutDashboard className="w-4 h-4 mb-0.5 text-cyan-400" />
          <span>Screener</span>
        </Link>
        <Link
          href="/portfolio"
          className="flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-slate-400 hover:text-slate-200"
        >
          <Briefcase className="w-4 h-4 mb-0.5 text-slate-400" />
          <span>Portfolio</span>
        </Link>
        <Link
          href="/backtest"
          className="flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-slate-400 hover:text-slate-200"
        >
          <LineChart className="w-4 h-4 mb-0.5 text-slate-400" />
          <span>Backtest</span>
        </Link>
        <button
          onClick={handleUniversalIngest}
          disabled={isIngesting || pageLoading}
          className="flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-emerald-400 hover:text-emerald-300"
        >
          {isIngesting ? (
            <Loader2 className="w-4 h-4 mb-0.5 animate-spin text-emerald-400" />
          ) : (
            <Zap className="w-4 h-4 mb-0.5 text-emerald-400" />
          )}
          <span>{isIngesting ? "Syncing..." : "Ingest"}</span>
        </button>
      </nav>

      {/* ──────────────── 6. MODALS & COCKPIT DRAWERS ──────────────── */}
      <CopilotDrawer
        activeSymbol={selectedSymbol || "RELIANCE"}
        activePrice={activeCandidate?.close ?? undefined}
        activeVerdict={activeCandidate?.composite_score ? (activeCandidate.composite_score >= 75 ? "STRONG_BUY_COMPOUNDER" : "HOLD_FAIRLY_VALUED") : undefined}
        showFloatingTrigger={false}
      />

      <PushNotificationModal
        isOpen={isPushModalOpen}
        onClose={() => setIsPushModalOpen(false)}
        onSubscriptionChange={(sub) => setIsPushSubscribed(sub)}
      />

      {showCommandPalette && (
        <CommandPaletteModal
          candidates={candidates}
          watchlistSymbols={watchlistSymbols}
          onSelect={(sym) => {
            setSelectedSymbol(sym);
            setIsInspectorCollapsed(false);
            setIsMobileInspectorOpen(true);
            setShowCommandPalette(false);
          }}
          onClose={() => setShowCommandPalette(false)}
        />
      )}
    </div>
  );
}
