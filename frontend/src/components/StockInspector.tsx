"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  ExternalLink,
  PanelRightClose,
  BrainCircuit,
  Loader2,
  FileText,
  Radio,
  Star,
  Zap,
} from "lucide-react";
import dynamic from "next/dynamic";
import {
  apiFetch,
  fetchStockBundle,
  peekCachedData,
  toggleWatchlist,
  requestLifecycle,
  ScreenerCandidate,
  CandleData,
  ForecastData,
  InvestmentMemo,
  NewsArticle,
  NewsResponse,
  VerdictType,
} from "@/lib/api";
import { milEvents } from "@/lib/store";
import { AnimatedTabs, TabItem } from "./ui/AnimatedTabs";
import { SkeletonStockInspector } from "./ui/SkeletonLoader";
import UnifiedIntelligenceHub from "./UnifiedIntelligenceHub";
import { FactorPentagonRadar } from "./FactorPentagonRadar";
import { RiskRewardVectorBar } from "./RiskRewardVectorBar";
import { RadialConvictionGauge } from "./RadialConvictionGauge";
import InvestmentMemoCard from "./InvestmentMemoCard";
import { cn } from "@/lib/utils";
import { withRetry } from "@/lib/lazyWithRetry";

const StockChart = dynamic(withRetry(() => import("./StockChart")), {
  ssr: false,
  loading: () => (
    <div className="h-[300px] w-full flex items-center justify-center bg-[#050811] rounded-xl border border-white/[0.06] text-xs font-mono text-slate-500">
      Loading chart engine...
    </div>
  ),
});

interface StockInspectorProps {
  symbol: string | null;
  activeCandidate?: ScreenerCandidate | null;
  onClose?: () => void;
  onOpenCopilot?: (symbol: string) => void;
}

const VERDICT_CONFIG: Record<
  VerdictType,
  { label: string; badge: string; horizonLabel: string }
> = {
  STRONG_BUY_COMPOUNDER: {
    label: "STRONG BUY",
    badge: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.25)]",
    horizonLabel: "12–24 Months",
  },
  TACTICAL_SWING_LONG: {
    label: "SWING LONG",
    badge: "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.25)]",
    horizonLabel: "2–8 Weeks",
  },
  HOLD_FAIRLY_VALUED: {
    label: "HOLD",
    badge: "bg-amber-950/80 border-amber-500/50 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.2)]",
    horizonLabel: "3–6 Months",
  },
  AVOID_CAPITAL_PRESERVATION: {
    label: "AVOID",
    badge: "bg-rose-950/80 border-rose-500/50 text-rose-300 shadow-[0_0_12px_rgba(239,68,68,0.25)]",
    horizonLabel: "Capital Preservation",
  },
};

const DEFAULT_VERDICT_CFG = VERDICT_CONFIG["HOLD_FAIRLY_VALUED"];

type InspectorTabKey = "thesis" | "intelligence";

function StockInspectorComponent({
  symbol,
  activeCandidate,
  onClose,
  onOpenCopilot,
}: StockInspectorProps) {
  const [candles, setCandles] = useState<CandleData[]>([]);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [memo, setMemo] = useState<InvestmentMemo | null>(null);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [activeTab, setActiveTab] = useState<InspectorTabKey>("thesis");
  const [isBookmarked, setIsBookmarked] = useState<boolean>(Boolean(activeCandidate?.is_watchlist));

  useEffect(() => {
    setIsBookmarked(Boolean(activeCandidate?.is_watchlist));
  }, [symbol, activeCandidate?.is_watchlist]);

  useEffect(() => {
    if (activeCandidate?.symbol) {
      milEvents.emit("mil:context-update", {
        symbol: activeCandidate.symbol,
        price: activeCandidate.close ?? null,
        verdict: memo?.verdict ?? (activeCandidate.composite_score !== null && activeCandidate.composite_score !== undefined && activeCandidate.composite_score >= 70 ? "STRONG_BUY" : "SWING_LONG"),
      });
    }
  }, [activeCandidate?.symbol, activeCandidate?.close, activeCandidate?.composite_score, memo?.verdict]);

  const handleToggleWatchlist = async () => {
    if (!symbol) return;
    const nextState = !isBookmarked;
    setIsBookmarked(nextState);
    const res = await toggleWatchlist(symbol, nextState);
    if (!res.success) {
      setIsBookmarked(!nextState);
    }
  };

  const handleOpenCopilot = () => {
    if (!symbol) return;
    if (onOpenCopilot) {
      onOpenCopilot(symbol);
    } else {
      milEvents.emit("mil:open-copilot", { symbol });
    }
  };

  // Load bundle with 150ms debounce and AbortController
  useEffect(() => {
    if (!symbol) {
      setCandles([]);
      setForecast(null);
      setMemo(null);
      setNews([]);
      setIsSyncing(false);
      return;
    }

    // Synchronously hydrate from SWR memory or sessionStorage L2 cache
    const cachedTearsheet = peekCachedData<{ history?: CandleData[] }>(`/stocks/${symbol}/tearsheet`);
    const cachedForecast = peekCachedData<ForecastData>(`/stocks/${symbol}/forecast`);
    const cachedMemo = peekCachedData<InvestmentMemo>(`/stocks/${symbol}/memo`);
    if (cachedTearsheet?.history) setCandles(cachedTearsheet.history);
    if (cachedForecast) setForecast(cachedForecast);
    if (cachedMemo) setMemo(cachedMemo);
    if (cachedTearsheet && cachedForecast && cachedMemo) {
      setIsSyncing(false);
    } else {
      setIsSyncing(true);
    }

    const fetchBundleData = async (skipCache: boolean = false) => {
      const { signal, generation } = requestLifecycle.prepareRequest("inspector_active");

      try {
        const bundle = await fetchStockBundle(symbol, { signal, useCache: !skipCache });
        if (requestLifecycle.isLatest("inspector_active", generation) && !signal.aborted) {
          setCandles(bundle.tearsheet?.history || []);
          setForecast(bundle.forecast || null);
          setMemo(bundle.memo || null);
          const rawNews = bundle.news;
          const newsList = Array.isArray(rawNews)
            ? rawNews
            : rawNews && typeof rawNews === "object" && "articles" in rawNews
            ? (rawNews.articles as NewsArticle[])
            : [];
          setNews(newsList);
          setIsSyncing(false);
        }
      } catch {
        if (signal.aborted || !requestLifecycle.isLatest("inspector_active", generation)) return;
        Promise.allSettled([
          apiFetch<{ history?: CandleData[] }>(`/stocks/${symbol}/tearsheet`, { signal, useCache: !skipCache }),
          apiFetch<ForecastData>(`/stocks/${symbol}/forecast`, { signal, useCache: !skipCache }),
          apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`, { signal, useCache: !skipCache }),
          apiFetch<NewsResponse>(`/stocks/${symbol}/news`, { signal, useCache: !skipCache }),
        ]).then(([tearsheetRes, forecastRes, memoRes, newsRes]) => {
          if (signal.aborted || !requestLifecycle.isLatest("inspector_active", generation)) return;
          setCandles(tearsheetRes.status === "fulfilled" && tearsheetRes.value ? tearsheetRes.value.history || [] : []);
          setForecast(forecastRes.status === "fulfilled" ? forecastRes.value : null);
          setMemo(memoRes.status === "fulfilled" ? memoRes.value : null);
          setNews(newsRes.status === "fulfilled" && newsRes.value ? newsRes.value.articles || [] : []);
          setIsSyncing(false);
        });
      }
    };

    const timer = setTimeout(() => {
      void fetchBundleData(false);
    }, 150);

    const handleRefresh = () => {
      setIsSyncing(true);
      void fetchBundleData(true);
    };

    window.addEventListener("mil:tearsheet-refresh", handleRefresh);
    window.addEventListener("mil:screener-refresh", handleRefresh);

    return () => {
      clearTimeout(timer);
      window.removeEventListener("mil:tearsheet-refresh", handleRefresh);
      window.removeEventListener("mil:screener-refresh", handleRefresh);
      requestLifecycle.cleanup("inspector_active");
    };
  }, [symbol]);

  if (!symbol) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center text-slate-500 font-mono text-xs">
        Select an equity from the screener to view deep quantitative inspection.
      </div>
    );
  }

  if (isSyncing && !activeCandidate && !memo && candles.length === 0) {
    return (
      <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#040609] border-l border-white/[0.08] text-slate-100">
        <SkeletonStockInspector />
      </div>
    );
  }

  const currentPrice =
    activeCandidate?.close || memo?.key_metrics?.current_price || 0;
  const sma200 = activeCandidate?.sma_200 || memo?.key_metrics?.sma_200 || null;
  const smaDist =
    sma200 && currentPrice ? ((currentPrice - sma200) / sma200) * 100 : null;

  // Active verdict
  const activeVerdict: VerdictType =
    memo?.verdict ||
    (activeCandidate?.composite_score && activeCandidate.composite_score >= 80
      ? "STRONG_BUY_COMPOUNDER"
      : activeCandidate?.composite_score && activeCandidate.composite_score >= 60
      ? "TACTICAL_SWING_LONG"
      : activeCandidate?.composite_score && activeCandidate.composite_score >= 40
      ? "HOLD_FAIRLY_VALUED"
      : "AVOID_CAPITAL_PRESERVATION");

  const verdictCfg = VERDICT_CONFIG[activeVerdict] || DEFAULT_VERDICT_CFG;

  // Forecast bounds for RiskRewardVectorBar
  const lastProjection =
    forecast?.projections?.[forecast.projections.length - 1];
  const hasValidForecast = Boolean(
    lastProjection &&
      typeof lastProjection.lower_95 === "number" &&
      typeof lastProjection.upper_80 === "number" &&
      currentPrice > 0
  );
  const forecastLower95 = hasValidForecast ? lastProjection!.lower_95 : null;
  const forecastUpper80 = hasValidForecast ? lastProjection!.upper_80 : null;

  // Factor Pentagon metrics
  const factorRoe = activeCandidate?.roe_pct ?? memo?.key_metrics?.roe_pct ?? null;
  const factorDe =
    activeCandidate?.debt_to_equity ?? memo?.key_metrics?.debt_to_equity ?? null;
  const factorOpm = activeCandidate?.opm_pct ?? memo?.key_metrics?.opm_pct ?? null;
  const factorMom =
    activeCandidate?.excess_ret_20d !== null &&
    activeCandidate?.excess_ret_20d !== undefined
      ? activeCandidate.excess_ret_20d * 100
      : null;
  const factorConv =
    memo?.institutional_conviction_score ??
    activeCandidate?.composite_score ??
    null;

  const is5dActive = Boolean(
    activeCandidate?.horizon_drivers?.some((d) => d.toUpperCase().includes("5D")) ||
    forecast?.forecast_horizon_days === 5
  );

  const inspectorTabs: TabItem<InspectorTabKey>[] = [
    {
      id: "thesis",
      label: "Thesis & Quant Model",
      icon: <FileText className="w-3.5 h-3.5" />,
    },
    {
      id: "intelligence",
      label: "Live Intelligence & Filings",
      badge: news.length > 0 ? `${news.length} Items` : "Live",
      icon: <Radio className="w-3.5 h-3.5 text-cyan-400" />,
    },
  ];

  return (
    <div
      className="flex-1 flex flex-col h-full overflow-hidden bg-[#040609] border-l border-white/[0.08] text-slate-100 select-none relative"
      style={{ containerType: "inline-size" }}
    >
      {/* Top subtle specular edge */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent pointer-events-none" />

      {/* 1. Responsive Header (Specular Hairline & Clean Badges) */}
      <div className="shrink-0 border-b border-white/[0.08] px-4 sm:px-5 py-3 bg-[#060a12] space-y-2">
        {/* Top Row: Symbol + Watchlist Star + Sector + Verdict | Spot + SMA Dist + Close */}
        <div className="flex items-center justify-between gap-2 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <div className="flex items-center gap-1.5">
              <h2 className="text-lg lg:text-xl font-bold font-mono tracking-tight text-white drop-shadow-[0_0_12px_rgba(255,255,255,0.2)]">
                {symbol}
              </h2>
              <button
                onClick={handleToggleWatchlist}
                className="p-1 rounded-md hover:bg-white/[0.08] transition-colors"
                title={isBookmarked ? "Remove from Watchlist" : "Pin to Watchlist"}
              >
                <Star
                  className={cn(
                    "w-4 h-4 transition-all",
                    isBookmarked
                      ? "fill-amber-400 text-amber-400 drop-shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                      : "text-slate-500 hover:text-amber-300"
                  )}
                />
              </button>
            </div>
            {isSyncing && (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400 shrink-0" />
            )}
            {activeCandidate?.sector && (
              <span className="text-[11px] px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono truncate max-w-[140px]">
                {activeCandidate.sector}
              </span>
            )}
            <motion.span
              key={activeVerdict}
              initial={{ scale: 0.7, opacity: 0 }}
              animate={{ scale: 1, opacity: 1 }}
              transition={{ type: "spring", stiffness: 400, damping: 20 }}
              className={cn(
                "px-2.5 py-0.5 rounded-full border text-[10px] font-mono font-bold tracking-wider shrink-0",
                verdictCfg.badge
              )}
            >
              {verdictCfg.label}
            </motion.span>
          </div>

          <div className="flex items-center gap-2.5 shrink-0 text-right">
            <div>
              <motion.span
                key={`${symbol}-${currentPrice}`}
                initial={{ opacity: 0, y: -4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ type: "spring", stiffness: 350, damping: 25 }}
                className="text-xs font-mono font-semibold text-slate-100 tabular-nums"
              >
                ₹{currentPrice ? currentPrice.toFixed(2) : "—"}
              </motion.span>
              {smaDist !== null && (
                <span
                  className={cn(
                    "ml-2 text-[10px] font-mono tabular-nums",
                    smaDist >= 0 ? "text-emerald-400" : "text-rose-400"
                  )}
                >
                  {smaDist >= 0 ? "+" : ""}
                  {smaDist.toFixed(1)}% vs 200 SMA
                </span>
              )}
            </div>
            {onClose && (
              <button
                onClick={onClose}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
                title="Collapse Inspector"
              >
                <PanelRightClose className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>

        {/* Second Row: Company Name on Left | Action CTAs on Right */}
        <div className="flex items-center justify-between gap-2 pt-0.5 flex-wrap">
          <span className="text-xs text-slate-400 truncate max-w-[200px] sm:max-w-none">
            {activeCandidate?.company_name || memo?.company_name || symbol}
          </span>

          <div className="flex items-center gap-1.5 shrink-0">
            {/* Ask Copilot CTA */}
            <button
              onClick={handleOpenCopilot}
              title="Launch Quant Copilot Committee (⌘J)"
              className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-500/40 hover:border-cyan-400/80 rounded-lg transition-all shadow-sm"
            >
              <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
              <span className="font-semibold">Copilot</span>
            </button>

            {/* Paper Trade CTA */}
            <Link
              href={`/portfolio?symbol=${symbol}`}
              title="Trade symbol in Paper Trading Blotter"
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-mono text-emerald-300 bg-emerald-950/40 hover:bg-emerald-900/60 border border-emerald-500/30 hover:border-emerald-400/60 rounded-lg transition-all"
            >
              <Zap className="w-3 h-3 text-emerald-400" />
              <span>Trade</span>
            </Link>

            {/* Deep Tearsheet Link */}
            <Link
              href={`/stocks/${symbol}`}
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-mono text-slate-200 bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.08] hover:border-cyan-500/40 rounded-lg transition-all"
              title="Open Deep Institutional Tearsheet"
            >
              <span>Tearsheet</span>
              <ExternalLink className="w-3 h-3 text-cyan-400" />
            </Link>
          </div>
        </div>
      </div>

      {/* 2. Responsive 2-Tab Animated Header */}
      <div className="shrink-0 px-4 py-2 bg-[#04070e] border-b border-white/[0.06]">
        <AnimatedTabs<InspectorTabKey>
          tabs={inspectorTabs}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          layoutId="stock-inspector-tab-pill"
          className="w-full justify-start"
        />
      </div>

      {/* 3. Tab Body Container with @container queries */}
      <div className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-5 thin-scrollbar">
        {isSyncing && candles.length === 0 && !memo ? (
          <div className="space-y-4 animate-pulse">
            <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 h-[300px] flex items-center justify-center">
              <span className="text-xs font-mono text-slate-500">
                Loading quantitative market telemetry for {symbol}...
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 h-[220px]" />
              <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 h-[220px]" />
            </div>
          </div>
        ) : activeTab === "thesis" ? (
          <>
            {/* Card 1: 100% Width Price Chart & 20D Forecast Cone */}
            <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 shadow-[0_8px_32px_rgba(0,0,0,0.5)] relative overflow-hidden">
              <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent pointer-events-none" />
              <div className="flex items-center justify-between mb-3 pb-2 border-b border-white/[0.06]">
                <div className="flex items-center space-x-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,1)]" />
                  <span className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider">
                    Historical Price & 20D Forecast Cone
                  </span>
                </div>
                <span className="text-[10px] font-mono text-cyan-400 tabular-nums">
                  {candles.length.toLocaleString()} Bars ({(candles.length / 252).toFixed(1)}Y)
                </span>
              </div>
              <StockChart
                symbol={symbol}
                data={candles}
                sma200={sma200}
                forecast={forecast}
                compact={true}
                height={290}
              />
            </div>

            {/* Market Microstructure Strip: Delivery %, Turnover, 20D Return, 52W Position */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5 text-xs font-mono">
              <div className="bg-[#080c14] border border-cyan-500/20 rounded-xl p-2.5 shadow-[0_0_12px_rgba(6,182,212,0.06)]">
                <span className="text-[10px] uppercase tracking-wider text-cyan-400 font-semibold block">Deliv %</span>
                <span className="text-cyan-200 font-bold font-mono text-sm mt-0.5 block tabular-nums">
                  {activeCandidate?.delivery_pct !== null && activeCandidate?.delivery_pct !== undefined
                    ? `${activeCandidate.delivery_pct.toFixed(1)}%`
                    : "—"}
                </span>
                <span className="text-[9px] text-slate-500 block truncate">
                  {(activeCandidate?.delivery_pct ?? 0) >= 50 ? "Accumulation" : "Settled"}
                </span>
              </div>

              <div className="bg-[#080c14] border border-white/[0.08] rounded-xl p-2.5">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold block">Turnover</span>
                <span className="text-slate-100 font-bold font-mono text-sm mt-0.5 block tabular-nums">
                  {activeCandidate?.turnover_cr !== null && activeCandidate?.turnover_cr !== undefined
                    ? `₹${activeCandidate.turnover_cr.toFixed(1)} Cr`
                    : "—"}
                </span>
                <span className="text-[9px] text-slate-500 block truncate">Traded Val</span>
              </div>

              <div className="bg-[#080c14] border border-white/[0.08] rounded-xl p-2.5">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold block">20D Momentum</span>
                <span className="text-slate-100 font-bold font-mono text-sm mt-0.5 block tabular-nums">
                  {activeCandidate?.ret_20d !== null && activeCandidate?.ret_20d !== undefined
                    ? `${((activeCandidate?.ret_20d ?? 0) >= 0 ? "+" : "") + ((activeCandidate?.ret_20d ?? 0) * 100).toFixed(1)}%`
                    : "—"}
                </span>
                <span className="text-[9px] text-slate-500 block truncate">Price Velocity</span>
              </div>

              <div className="bg-[#080c14] border border-white/[0.08] rounded-xl p-2.5">
                <span className="text-[10px] uppercase tracking-wider text-slate-400 font-semibold block">52W Position</span>
                {(() => {
                  const rawVal = activeCandidate?.pct_from_52w_high ?? (
                    activeCandidate?.distance_52w_high !== null && activeCandidate?.distance_52w_high !== undefined
                      ? (Math.abs(activeCandidate.distance_52w_high) <= 1.0 ? activeCandidate.distance_52w_high * 100 : activeCandidate.distance_52w_high)
                      : null
                  );
                  const displayPct = rawVal !== null && rawVal !== undefined ? Math.max(-100, Math.min(0, rawVal)) : null;
                  return (
                    <span className={`font-bold font-mono text-sm mt-0.5 block tabular-nums ${
                      (displayPct ?? 0) >= -5 ? "text-emerald-400" : "text-amber-400"
                    }`}>
                      {displayPct !== null ? `${displayPct >= 0 ? "+" : ""}${displayPct.toFixed(1)}%` : "—"}
                    </span>
                  );
                })()}
                <span className="text-[9px] text-slate-500 block truncate">From 52W High</span>
              </div>
            </div>

            {/* Row 2: Symmetric 2-Column Bento Grid: Consensus (Left) + Conviction & Risk/Reward (Right) */}
            <div className="grid grid-cols-1 @[520px]:grid-cols-2 min-[640px]:grid-cols-2 gap-4 items-stretch">
              {/* Left Column: Multi-Horizon Factor Consensus */}
              <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col justify-between space-y-3 relative overflow-hidden">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent pointer-events-none" />
                <div>
                  <div className="flex flex-wrap sm:flex-nowrap items-center justify-between gap-1.5 border-b border-white/[0.06] pb-2.5">
                    <div className="flex items-center gap-1.5 shrink-0">
                      <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,1)] shrink-0" />
                      <span className="text-xs font-mono font-semibold text-white uppercase tracking-wider whitespace-nowrap">
                        Multi-Horizon Consensus
                      </span>
                    </div>
                    <span className="text-xs font-mono font-bold text-cyan-300 px-2 py-0.5 rounded-lg bg-cyan-950/80 border border-cyan-500/40 shadow-[0_0_10px_rgba(6,182,212,0.2)] tabular-nums shrink-0">
                      {activeCandidate?.blended_score !== undefined && activeCandidate?.blended_score !== null
                        ? `${activeCandidate.blended_score.toFixed(1)}/100`
                        : activeCandidate?.composite_score !== undefined && activeCandidate?.composite_score !== null
                        ? `${activeCandidate.composite_score.toFixed(1)}/100`
                        : "—"}
                    </span>
                  </div>

                  {/* Horizon Attribution Breakdown Bars */}
                  <div className="space-y-3 pt-3">
                    {/* 20D Tactical Horizon */}
                    <div>
                      <div className="flex items-center justify-between text-xs font-mono mb-1">
                        <span className="text-slate-300 flex items-center gap-1.5">
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-bold">20D Tactical</span>
                          <span className="text-slate-500 text-[10px]">(62.5%)</span>
                        </span>
                        <span className="text-cyan-300 font-semibold tabular-nums text-xs">
                          {activeCandidate?.score_20d !== undefined && activeCandidate.score_20d !== null ? `${activeCandidate.score_20d.toFixed(1)}` : "—"}
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900/80 rounded-full overflow-hidden border border-white/[0.06]">
                        <div
                          className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full transition-all duration-500 shadow-[0_0_8px_rgba(6,182,212,0.6)]"
                          style={{ width: `${Math.min(100, Math.max(0, activeCandidate?.score_20d ?? 50))}%` }}
                        />
                      </div>
                    </div>

                    {/* 60D Trend Drift Horizon */}
                    <div>
                      <div className="flex items-center justify-between text-xs font-mono mb-1">
                        <span className="text-slate-300 flex items-center gap-1.5">
                          <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 font-bold">60D Trend</span>
                          <span className="text-slate-500 text-[10px]">(37.5%)</span>
                        </span>
                        <span className="text-emerald-300 font-semibold tabular-nums text-xs">
                          {activeCandidate?.score_60d !== undefined && activeCandidate.score_60d !== null ? `${activeCandidate.score_60d.toFixed(1)}` : "—"}
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900/80 rounded-full overflow-hidden border border-white/[0.06]">
                        <div
                          className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full transition-all duration-500 shadow-[0_0_8px_rgba(16,185,129,0.6)]"
                          style={{ width: `${Math.min(100, Math.max(0, activeCandidate?.score_60d ?? 50))}%` }}
                        />
                      </div>
                    </div>

                    {/* 5D Swing Horizon */}
                    <div
                      className={cn(
                        "pt-1 flex items-center justify-between text-[11px] font-mono p-2 rounded-xl border transition-all duration-300",
                        is5dActive
                          ? "text-slate-200 bg-emerald-950/25 border-emerald-500/35"
                          : "text-slate-400 bg-white/[0.02] border-white/[0.04]"
                      )}
                    >
                      <span className="font-semibold flex items-center gap-1.5 text-[10px]">
                        <span className="px-1.5 py-0.2 rounded bg-slate-800 text-slate-300 border border-white/[0.08]">
                          5D Swing
                        </span>
                        <span>Gate:</span>
                      </span>
                      <span
                        className={cn(
                          "font-bold text-[10px] flex items-center gap-1",
                          is5dActive ? "text-emerald-300" : "text-slate-400"
                        )}
                      >
                        {is5dActive ? "Active" : "Disarmed"}
                      </span>
                    </div>
                  </div>
                </div>

                {/* Target Allocation */}
                <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400 text-[11px]">Allocation:</span>
                  {activeCandidate?.target_allocation_pct !== undefined && activeCandidate.target_allocation_pct !== null && activeCandidate.target_allocation_pct > 0 ? (
                    <span className="px-2 py-0.5 rounded-lg font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-500/50 tabular-nums text-[11px]">
                      {activeCandidate.target_allocation_pct.toFixed(2)}%
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded-lg text-slate-500 bg-white/[0.02] border border-white/[0.06] text-[10px]">
                      Unallocated
                    </span>
                  )}
                </div>
              </div>

              {/* Right Column: Institutional Conviction & Risk/Reward Gauge */}
              <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col justify-between space-y-3 relative overflow-hidden">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent pointer-events-none" />
                <div>
                  <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
                    <span className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider">
                      Institutional Conviction
                    </span>
                    <span className="text-[10px] font-mono text-slate-400">
                      {verdictCfg.horizonLabel}
                    </span>
                  </div>

                  <div className="flex items-center justify-center py-2">
                    <RadialConvictionGauge score={factorConv} />
                  </div>
                </div>

                {/* Risk Reward Vector Bar */}
                <div className="pt-2 border-t border-white/[0.06]">
                  <span className="text-[10px] font-mono text-slate-400 block mb-1">
                    Statistical Bounds (95% CI vs 80% CI)
                  </span>
                  {hasValidForecast && forecastLower95 && forecastUpper80 ? (
                    <RiskRewardVectorBar
                      currentPrice={currentPrice}
                      stopPrice={forecastLower95}
                      targetPrice={forecastUpper80}
                    />
                  ) : (
                    <div className="text-[11px] font-mono text-slate-500 py-1 italic">
                      Forecast bounds pending active model evaluation
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Row 3: Factor Pentagon Radar + Key Telemetry */}
            <div className="grid grid-cols-1 @[520px]:grid-cols-2 min-[640px]:grid-cols-2 gap-4 items-stretch">
              {/* Factor Radar Card */}
              <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col items-center justify-between relative overflow-hidden">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent pointer-events-none" />
                <span className="text-xs font-mono font-semibold text-slate-200 mb-1 self-start uppercase tracking-wider">
                  Quantitative Factor Pentagon
                </span>
                <FactorPentagonRadar
                  roe={factorRoe}
                  debtToEquity={factorDe}
                  opm={factorOpm}
                  momentum20d={factorMom}
                  conviction={factorConv}
                  enableBenchmarkToggle={true}
                />
              </div>

              {/* Factor Telemetry 2x2 Grid */}
              <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col justify-between space-y-3 relative overflow-hidden">
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/20 to-transparent pointer-events-none" />
                <span className="text-xs font-mono font-semibold text-slate-200 border-b border-white/[0.06] pb-2 uppercase tracking-wider">
                  Fundamental &amp; Risk Telemetry
                </span>

                <div className="grid grid-cols-2 gap-2.5 flex-1 items-center">
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                    <div className="text-[10px] text-slate-400 font-mono">RETURN ON EQUITY</div>
                    <div className="text-sm font-bold text-white font-mono mt-0.5 tabular-nums">
                      {factorRoe !== null ? `${factorRoe.toFixed(1)}%` : "Awaiting Filing"}
                    </div>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                    <div className="text-[10px] text-slate-400 font-mono">DEBT-TO-EQUITY</div>
                    <div className="text-sm font-bold text-white font-mono mt-0.5 tabular-nums">
                      {factorDe !== null ? `${factorDe.toFixed(2)}x` : "Awaiting BS"}
                    </div>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                    <div className="text-[10px] text-slate-400 font-mono">OPERATING MARGIN</div>
                    <div className="text-sm font-bold text-white font-mono mt-0.5 tabular-nums">
                      {factorOpm !== null ? `${factorOpm.toFixed(1)}%` : "Awaiting Filing"}
                    </div>
                  </div>
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.06]">
                    <div className="text-[10px] text-slate-400 font-mono">20D MOMENTUM</div>
                    <div
                      className={cn(
                        "text-sm font-bold font-mono mt-0.5 tabular-nums",
                        factorMom !== null && factorMom >= 0 ? "text-emerald-400" : "text-rose-400"
                      )}
                    >
                      {factorMom !== null ? `${factorMom >= 0 ? "+" : ""}${factorMom.toFixed(1)}%` : "—"}
                    </div>
                  </div>
                </div>

                <div className="pt-2 border-t border-white/[0.06] text-[10px] text-slate-500 flex items-center justify-between">
                  <span>Audit Tier: Clean Factor Pipeline</span>
                  <span className="text-cyan-400 font-semibold">Normalized V8</span>
                </div>
              </div>
            </div>

            {/* Row 4: Investment Memo Component (Compact Mode) */}
            <div className="rounded-2xl border border-white/[0.08] bg-[#080c14] p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
              <InvestmentMemoCard symbol={symbol} initialMemo={memo} compact={true} />
            </div>
          </>
        ) : (
          /* Tab 2: Live Intelligence & Filings Hub */
          <div className="space-y-4">
            <UnifiedIntelligenceHub
              symbol={symbol}
              initialNews={news}
              compact={true}
            />
          </div>
        )}
      </div>
    </div>
  );
}

const StockInspector = React.memo(StockInspectorComponent);
export default StockInspector;
