"use client";

import React, { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Activity,
  RefreshCw,
  Command,
  PanelRightOpen,
  BrainCircuit,
  LayoutDashboard,
  Briefcase,
  LineChart,
  X,
} from "lucide-react";
import NotificationCenterPopover from "@/components/NotificationCenterPopover";
import {
  apiFetch,
  peekCachedData,
  ScreenerCandidate,
  ScreenerResponse,
  WatchlistResponse,
  clearMemoryCache,
} from "@/lib/api";
import { milEvents } from "@/lib/store";
import { usePlatformEvents } from "@/hooks/usePlatformEvents";
import { checkPushSubscription, autoSyncPushSubscription } from "@/lib/pushNotifications";
import PushNotificationModal from "@/components/PushNotificationModal";
import MacroRibbon from "@/components/MacroRibbon";
import IngestionProgressBanner from "@/components/IngestionProgressBanner";
import ScreenerWorkspace from "@/components/ScreenerWorkspace";
import StockInspector from "@/components/StockInspector";
import IngestStatusButton from "@/components/IngestStatusButton";
import { CommandPaletteModal } from "@/components/CommandPaletteModal";
import ParticleField from "@/components/ParticleField";
import { PanelErrorBoundary } from "@/components/PanelErrorBoundary";
import { KeyboardShortcutModal } from "@/components/KeyboardShortcutModal";
import { useBackButtonClose } from "@/hooks/useBackButtonClose";
import { cn } from "@/lib/utils";

export default function CockpitPage() {
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [asOfDate, setAsOfDate] = useState<string>("");
  const [watchlistSymbols, setWatchlistSymbols] = useState<string[]>([]);
  const [pageLoading, setPageLoading] = useState<boolean>(true);
  const [viewMode, setViewMode] = useState<"table" | "heatmap" | "cards">("table");
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [isInspectorCollapsed, setIsInspectorCollapsed] = useState<boolean>(false);
  const [isMobileInspectorOpen, setIsMobileInspectorOpen] = useState<boolean>(false);
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showShortcutModal, setShowShortcutModal] = useState(false);
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [isPushSubscribed, setIsPushSubscribed] = useState(false);

  // Intercept Android hardware back / left-swipe gestures to close drawers/modals instead of exiting the PWA
  useBackButtonClose(isMobileInspectorOpen, () => setIsMobileInspectorOpen(false), "mobileInspector");
  useBackButtonClose(showCommandPalette, () => setShowCommandPalette(false), "commandPalette");
  useBackButtonClose(isPushModalOpen, () => setIsPushModalOpen(false), "pushModal");

  // Resizable Split-Pane Ratio (M3)
  const [splitPct, setSplitPct] = useState<number>(54);

  const isDraggingRef = React.useRef(false);

  const startDragging = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDraggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onMouseMove = (moveEvent: MouseEvent) => {
      if (!isDraggingRef.current) return;
      const totalWidth = window.innerWidth;
      const newPct = Math.min(Math.max((moveEvent.clientX / totalWidth) * 100, 30), 75);
      setSplitPct(newPct);
    };

    const onMouseUp = () => {
      isDraggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      setSplitPct((curr) => {
        try {
          localStorage.setItem("mil:split-pct", curr.toFixed(1));
        } catch {}
        return curr;
      });
    };

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }, []);

  // 1. Unified Real-Time Event Hub
  const {
    macroData,
    supervisorStatus,
    activeJob,
    isConnected,
    lastTickAt,
    lastIngestTimestamp,
    dismissActiveJob,
  } = usePlatformEvents();

  // 2. Initial Screener & Watchlist Data Fetch
  const loadPageData = useCallback(async (invalidateCache: boolean = false) => {
    if (invalidateCache || candidates.length === 0) {
      setPageLoading(true);
    }
    if (invalidateCache) {
      clearMemoryCache();
    }
    try {
      const [scrRes, wlRes] = await Promise.allSettled([
        apiFetch<ScreenerResponse>("/screener?limit=1500", !invalidateCache),
        apiFetch<WatchlistResponse>("/watchlist", !invalidateCache),
      ]);

      if (scrRes.status === "fulfilled") {
        const results = scrRes.value.results || [];
        setCandidates(results);
        if (scrRes.value.as_of_date) {
          setAsOfDate(scrRes.value.as_of_date);
        }
        setSelectedSymbol((prev) => prev || (results.length > 0 ? results[0].symbol : null));
      }

      if (wlRes.status === "fulfilled") {
        const items = wlRes.value.watchlist || [];
        setWatchlistSymbols(items.map((w) => w.symbol));
      }
    } catch (err) {
      console.error("Cockpit initial load error:", err);
    } finally {
      setPageLoading(false);
    }
  }, [candidates.length]);

  // 3. Initial Load, Session-Gated Push Subscription & URL Query Parameter Initialization
  useEffect(() => {
    // Client-side cache hydration on mount (zero SSR mismatch)
    try {
      const cachedScr = peekCachedData<ScreenerResponse>("/screener?limit=1500");
      if (cachedScr?.results && cachedScr.results.length > 0) {
        setCandidates(cachedScr.results);
        if (cachedScr.as_of_date) setAsOfDate(cachedScr.as_of_date);
        setSelectedSymbol((prev) => prev || cachedScr.results[0].symbol);
        setPageLoading(false);
      }
      const cachedWl = peekCachedData<WatchlistResponse>("/watchlist");
      if (cachedWl?.watchlist && cachedWl.watchlist.length > 0) {
        setWatchlistSymbols(cachedWl.watchlist.map((w) => w.symbol));
      }
      const savedSplit = localStorage.getItem("mil:split-pct");
      if (savedSplit) {
        const val = parseFloat(savedSplit);
        if (!isNaN(val) && val >= 30 && val <= 75) setSplitPct(val);
      }
    } catch {}

    void loadPageData();
    if (typeof window !== "undefined") {
      const alreadySynced = sessionStorage.getItem("mil:push-synced");
      if (!alreadySynced && "Notification" in window && Notification.permission === "granted") {
        autoSyncPushSubscription().then((res) => {
          setIsPushSubscribed(res.isSubscribed);
          sessionStorage.setItem("mil:push-synced", "true");
        });
      } else {
        checkPushSubscription().then((res) => {
          setIsPushSubscribed(res.isSubscribed);
        });
      }
    }

    if (typeof window !== "undefined") {
      const params = new URLSearchParams(window.location.search);
      const symParam = params.get("symbol");
      if (symParam) {
        setSelectedSymbol(symParam.toUpperCase());
        if (window.innerWidth < 1024) {
          setIsMobileInspectorOpen(true);
        }
      }
      const viewParam = params.get("view");
      if (viewParam === "heatmap" || viewParam === "cards") {
        setViewMode(viewParam);
      }
    }

    const handleRefresh = () => {
      void loadPageData(true);
    };
    window.addEventListener("mil:screener-refresh", handleRefresh);

    const handleSwrRevalidate = (e: Event) => {
      const detail = (e as CustomEvent).detail;
      if (detail?.url && detail.url.includes("/screener")) {
        const payload = detail.data as ScreenerResponse;
        if (payload?.results && payload.results.length > 0) {
          setCandidates(payload.results);
        }
        if (payload?.as_of_date) {
          setAsOfDate(payload.as_of_date);
        }
      }
    };
    window.addEventListener("mil:swr-revalidated", handleSwrRevalidate);

    return () => {
      window.removeEventListener("mil:screener-refresh", handleRefresh);
      window.removeEventListener("mil:swr-revalidated", handleSwrRevalidate);
    };
  }, [loadPageData]);

  // 4. URL State Synchronization (Non-reloading history replace)
  useEffect(() => {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (selectedSymbol) {
      url.searchParams.set("symbol", selectedSymbol);
    } else {
      url.searchParams.delete("symbol");
    }
    if (viewMode === "heatmap") {
      url.searchParams.set("view", "heatmap");
    } else if (viewMode === "cards") {
      url.searchParams.set("view", "cards");
    } else {
      url.searchParams.delete("view");
    }
    window.history.replaceState(null, "", url.toString());
  }, [selectedSymbol, viewMode]);

  // Active Candidate lookup
  const activeCandidate = useMemo(() => {
    if (!selectedSymbol || !candidates.length) return null;
    return candidates.find((c) => c.symbol === selectedSymbol) || null;
  }, [candidates, selectedSymbol]);

  // Memoized Symbol Selection Callback
  const handleSelectSymbol = useCallback((sym: string) => {
    setSelectedSymbol(sym);
    setIsInspectorCollapsed(false);
    if (typeof window !== "undefined" && window.innerWidth < 1024) {
      setIsMobileInspectorOpen(true);
    }
  }, []);

  // Global Keyboard Shortcuts (⌘K, ?, V) (M5)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isInput =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable);

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setShowCommandPalette((prev) => !prev);
      } else if (!isInput) {
        if (e.key === "?" && !e.metaKey && !e.ctrlKey) {
          e.preventDefault();
          setShowShortcutModal((prev) => !prev);
        } else if (e.key.toLowerCase() === "v" && !e.metaKey && !e.ctrlKey) {
          e.preventDefault();
          setViewMode((prev) => (prev === "table" ? "heatmap" : prev === "heatmap" ? "cards" : "table"));
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col bg-[#030508] bg-grid-pattern relative select-none text-slate-100 font-sans">
      <ParticleField />
      {/* ──────────────── 1. TOP HEADER NAVIGATION (V8 Institutional Aesthetic) ──────────────── */}
      <header className="h-14 shrink-0 border-b border-white/[0.08] bg-[#040609] flex items-center justify-between px-3 sm:px-6 z-30 transition-all">
        {/* Left: Brand + Navigation Tabs with Framer Motion Spring Indicator */}
        <div className="flex items-center space-x-3 sm:space-x-4 shrink-0">
          <Link href="/" className="flex items-center space-x-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 via-teal-500 to-indigo-600 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.35)] group-hover:scale-105 transition-transform duration-200">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm sm:text-base text-slate-100 tracking-tight font-mono">
                MIL<span className="text-cyan-400 font-sans hidden md:inline">.QUANT</span>
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 hidden sm:inline">
                V8
              </span>
            </div>
          </Link>

          {/* Navigation Tabs with Framer Motion Spring Layout Indicator (Desktop) */}
          <nav className="hidden md:flex items-center space-x-1 sm:space-x-1.5 bg-[#080c14] border border-white/[0.06] p-1 rounded-xl">
            <Link
              href="/"
              className="relative px-3 py-1.5 text-xs font-mono font-medium rounded-lg transition-colors flex items-center gap-1.5 text-cyan-300 font-semibold"
            >
              <motion.div
                layoutId="navbar-tab-indicator"
                className="absolute inset-0 bg-cyan-950/60 border border-cyan-500/40 rounded-lg shadow-[0_0_15px_rgba(6,182,212,0.25)]"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
              <LayoutDashboard className="w-3.5 h-3.5 relative z-10 text-cyan-400" />
              <span className="relative z-10 hidden sm:inline">Screener</span>
            </Link>

            <Link
              href="/portfolio"
              className="relative px-3 py-1.5 text-xs font-mono font-medium rounded-lg transition-colors flex items-center gap-1.5 text-slate-400 hover:text-slate-200"
            >
              <Briefcase className="w-3.5 h-3.5 relative z-10" />
              <span className="relative z-10 hidden sm:inline">Portfolio</span>
            </Link>

            <Link
              href="/backtest"
              className="relative px-3 py-1.5 text-xs font-mono font-medium rounded-lg transition-colors flex items-center gap-1.5 text-slate-400 hover:text-slate-200"
            >
              <LineChart className="w-3.5 h-3.5 relative z-10" />
              <span className="relative z-10 hidden sm:inline">Backtest</span>
            </Link>
          </nav>
        </div>

        {/* Right: Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => void loadPageData(true)}
            disabled={pageLoading}
            title="Force refresh universe and invalidate cache"
            aria-label="Force refresh universe"
            className="p-2 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-white/[0.04] border border-white/[0.08] transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${pageLoading ? "animate-spin text-cyan-400" : ""}`} />
          </button>

          <button
            onClick={() => setShowCommandPalette(true)}
            aria-label="Open Command Palette"
            className="flex items-center gap-1.5 text-xs font-mono text-slate-400 px-2.5 py-1.5 rounded-xl bg-slate-900/60 border border-white/[0.08] hover:border-cyan-500/30 hover:text-slate-200 transition-colors"
          >
            <Command className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden md:inline">Search</span>
            <kbd className="text-[10px] font-mono text-slate-500 bg-slate-800/80 px-1 rounded border border-white/[0.04]">⌘K</kbd>
          </button>

          <button
            onClick={() => {
              milEvents.emit("mil:open-copilot", { symbol: selectedSymbol || "RELIANCE" });
            }}
            title="Open Quant Copilot Committee (⌘J)"
            aria-label="Open Quant Copilot Committee"
            className="flex items-center gap-1.5 text-xs font-mono text-cyan-300 px-2.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-cyan-950/40 border border-white/[0.08] hover:border-cyan-500/40 transition-all shadow-sm whitespace-nowrap"
          >
            <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Copilot</span>
            <kbd className="text-[10px] text-cyan-400/80 bg-slate-900 px-1 rounded border border-cyan-500/30">⌘J</kbd>
          </button>

          {/* Keyboard Shortcuts Cheatsheet (M5) */}
          <button
            onClick={() => setShowShortcutModal(true)}
            title="Terminal Keyboard Shortcuts (?)"
            aria-label="Terminal keyboard shortcuts"
            className="hidden sm:flex items-center justify-center w-8 h-8 rounded-xl text-slate-400 hover:text-cyan-300 hover:bg-white/[0.04] border border-white/[0.08] transition-colors font-mono text-xs font-bold"
          >
            ?
          </button>

          {/* Real-time Notification Center Popover */}
          <NotificationCenterPopover
            isPushSubscribed={isPushSubscribed}
            onOpenPushSettings={() => setIsPushModalOpen(true)}
          />

          {/* Real-Time Dynamic Ingest Button (Desktop) */}
          <IngestStatusButton />

          {isInspectorCollapsed && (
            <button
              onClick={() => setIsInspectorCollapsed(false)}
              title="Expand Details Inspector"
              aria-label="Expand Details Inspector"
              className="hidden lg:flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-mono text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-800/60 rounded-xl transition-colors"
            >
              <PanelRightOpen className="w-3.5 h-3.5 text-cyan-400" />
              <span>Inspect {selectedSymbol || "Stock"}</span>
            </button>
          )}
        </div>
      </header>

      {/* ──────────────── 2. DEDICATED TELEMETRY SUB-BAR ──────────────── */}
      <div className="h-8 shrink-0 border-b border-white/[0.04] bg-[#020306] flex items-center overflow-hidden z-20">
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
      <div
        style={{
          "--split-pct": `${splitPct}%`,
          "--inspector-pct": `${100 - splitPct}%`,
        } as React.CSSProperties}
        className="flex flex-1 overflow-hidden relative z-10 min-h-0 h-full pb-14 md:pb-0"
      >
        {/* Master: Screener Workspace (100% full width on mobile/tablet via w-full, splitPct on >= 1024px desktop) */}
        <div
          className={cn(
            "w-full flex flex-col h-full overflow-hidden shrink-0 min-h-0 bg-[#040609] transition-all duration-75 ease-out",
            !isInspectorCollapsed && "lg:w-[var(--split-pct)]"
          )}
        >
          <PanelErrorBoundary panelName="Screener Workspace">
            <ScreenerWorkspace
              candidates={candidates}
              selectedSymbol={selectedSymbol}
              onSelectSymbol={handleSelectSymbol}
              asOfDate={asOfDate}
              loading={pageLoading}
              viewMode={viewMode}
              onViewModeChange={setViewMode}
            />
          </PanelErrorBoundary>
        </div>

        {/* Resizable Divider Handle (M3) */}
        {!isInspectorCollapsed && (
          <div
            onMouseDown={startDragging}
            onDoubleClick={() => setSplitPct(54)}
            title="Drag to resize panels (Double-click to reset to 54%)"
            className="hidden lg:flex w-1.5 hover:w-2 bg-black/80 hover:bg-cyan-500/50 active:bg-cyan-400 cursor-col-resize items-center justify-center transition-all z-20 group relative border-x border-white/[0.04]"
          >
            <div className="w-[1px] h-8 bg-slate-700 group-hover:bg-cyan-300 transition-colors" />
          </div>
        )}

        {/* Desktop Detail: Stock Deep Inspector (>= 1024px) */}
        {!isInspectorCollapsed && (
          <div
            className="hidden lg:flex lg:w-[var(--inspector-pct)] flex-col h-full overflow-hidden min-w-0 min-h-0 bg-[#040609] transition-all duration-75 ease-out"
          >
            <PanelErrorBoundary panelName="Stock Inspector">
              <StockInspector
                symbol={selectedSymbol}
                activeCandidate={activeCandidate}
                onClose={() => setIsInspectorCollapsed(true)}
                onOpenCopilot={() => {
                  milEvents.emit("mil:open-copilot", { symbol: selectedSymbol || "RELIANCE" });
                }}
              />
            </PanelErrorBoundary>
          </div>
        )}
      </div>

      {/* ──────────────── 4. MOBILE DETAIL SLIDE-OVER DRAWER (< 1024px) ──────────────── */}
      {isMobileInspectorOpen && selectedSymbol && (
        <div className="fixed inset-0 z-50 bg-[#040609] overflow-y-auto lg:hidden flex flex-col animate-in slide-in-from-bottom duration-200">
          {/* Sticky Mobile Back Header */}
          <div className="sticky top-0 z-50 flex items-center justify-between px-3.5 py-2.5 bg-[#060911] border-b border-white/10 shrink-0">
            <button
              onClick={() => setIsMobileInspectorOpen(false)}
              aria-label="Back to Screener"
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
                aria-label="Close details inspector"
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
                milEvents.emit("mil:open-copilot", { symbol: selectedSymbol || "RELIANCE" });
              }}
            />
          </div>
        </div>
      )}

      {/* ──────────────── 5. FIXED MOBILE BOTTOM NAVIGATION BAR (< 768px) ──────────────── */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-[#040609]/95 backdrop-blur-lg border-t border-white/[0.08] px-2 py-1.5 flex items-center justify-around pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        <Link
          href="/"
          className="relative flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-cyan-300 font-bold"
        >
          <motion.div
            layoutId="mobile-nav-indicator"
            className="absolute inset-0 bg-cyan-950/60 border border-cyan-800/40 rounded-lg shadow-[0_0_12px_rgba(6,182,212,0.2)]"
            transition={{ type: "spring", stiffness: 400, damping: 30 }}
          />
          <LayoutDashboard className="w-4 h-4 mb-0.5 text-cyan-400 relative z-10" />
          <span className="relative z-10">Screener</span>
        </Link>
        <Link
          href="/portfolio"
          className="relative flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-slate-400 hover:text-slate-200"
        >
          <Briefcase className="w-4 h-4 mb-0.5 text-slate-400" />
          <span>Portfolio</span>
        </Link>
        <Link
          href="/backtest"
          className="relative flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-slate-400 hover:text-slate-200"
        >
          <LineChart className="w-4 h-4 mb-0.5 text-slate-400" />
          <span>Backtest</span>
        </Link>
        <button
          onClick={() => milEvents.emit("mil:open-copilot", { symbol: selectedSymbol || "RELIANCE" })}
          className="relative flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono text-slate-400 hover:text-cyan-300"
        >
          <BrainCircuit className="w-4 h-4 mb-0.5 text-cyan-400" />
          <span>Copilot</span>
        </button>
        {/* Dynamic Ingest in Mobile Bottom Bar */}
        <IngestStatusButton compact />
      </nav>

      {/* ──────────────── 6. MODALS & COCKPIT DRAWERS ──────────────── */}
      <KeyboardShortcutModal
        isOpen={showShortcutModal}
        onClose={() => setShowShortcutModal(false)}
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
