"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import { motion, AnimatePresence } from "framer-motion";
import { AnimatedNumber } from "@/lib/AnimatedNumber";
import { withRetry } from "@/lib/lazyWithRetry";
import type { CandleData, ForecastData } from "@/components/StockChart";

const StockChart = dynamic(withRetry(() => import("@/components/StockChart")), {
  ssr: false,
  loading: () => (
    <div className="h-[440px] w-full flex items-center justify-center bg-[#050811] rounded-xl border border-white/[0.06] text-xs font-mono text-slate-500">
      Loading chart engine...
    </div>
  ),
});

import InvestmentMemoCard, { InvestmentMemo } from "@/components/InvestmentMemoCard";
import UnifiedIntelligenceHub, { Disclosure } from "@/components/UnifiedIntelligenceHub";
import QuarterlyFinancialsCard, { QuarterlyStatement } from "@/components/QuarterlyFinancialsCard";
import { NewsArticle } from "@/components/NewsImpactCard";
import { FactorPentagonRadar } from "@/components/FactorPentagonRadar";
import { RiskRewardVectorBar } from "@/components/RiskRewardVectorBar";
import { RadialConvictionGauge } from "@/components/RadialConvictionGauge";
import { BentoCard } from "@/components/ui/BentoCard";
import Navbar from "@/components/Navbar";
import { cn } from "@/lib/utils";
import { milEvents } from "@/lib/store";
import {
  requestLifecycle,
  API_BASE,
  DEFAULT_HEADERS,
  apiFetch,
  peekCachedData,
  clearMemoryCache,
  toggleWatchlist,
} from "@/lib/api";

const TEARSHEET_SECTIONS = [
  { id: "tearsheet-overview", label: "Overview" },
  { id: "tearsheet-chart", label: "Chart & 20D Cone" },
  { id: "tearsheet-attribution", label: "Quant Attribution & Radar" },
  { id: "tearsheet-thesis", label: "Investment Memo" },
  { id: "tearsheet-health", label: "Fundamentals & Risk" },
  { id: "tearsheet-financials", label: "Quarterly Financials" },
  { id: "tearsheet-wire", label: "Live Intelligence & Filings" },
];

import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Target,
  ShieldAlert,
  AlertTriangle,
  Activity,
  CheckCircle2,
  Loader2,
  Circle,
  SearchX,
  Share2,
  Check,
  BrainCircuit,
  Zap,
  Star,
  Layers,
} from "lucide-react";

interface TearsheetData {
  symbol: string;
  company_name: string;
  isin: string;
  sector: string;
  industry: string;
  is_watchlist: boolean;
  is_nifty50?: boolean;
  target_price: number | null;
  stop_loss: number | null;
  notes: string | null;
  as_of_date: string;
  latest_ohlcv: {
    trading_date: string;
    open: number;
    high: number;
    low: number;
    close: number;
    volume: number;
    delivery_qty?: number | null;
    delivery_pct?: number | null;
    turnover_cr?: number | null;
  };
  technicals: {
    ret_1d: number;
    ret_1d_pct: number;
    ret_5d: number | null;
    ret_20d: number | null;
    sma_20: number | null;
    sma_50: number | null;
    sma_200: number | null;
    dist_sma200_pct: number | null;
    price_above_sma200: boolean;
    volatility_annualized: number | null;
    beta_60d_nifty: number | null;
    volume_ratio_20d: number | null;
    volume_zscore_50d: number | null;
    delivery_pct?: number | null;
    turnover_cr?: number | null;
    distance_52w_high?: number | null;
    distance_52w_low?: number | null;
    pct_from_52w_high?: number | null;
  };
  fundamentals: {
    roe_pct: number | null;
    debt_to_equity: number | null;
    ttm_pe: number | null;
    opm_pct: number | null;
  };
  ml_forecast?: {
    forecast_horizon_days?: number;
    predicted_excess_return?: number;
    conviction_score?: number;
    signal?: string;
    primary_driver?: string;
    horizons?: {
      "5d"?: { return?: number; conviction?: number; active?: boolean };
      "20d"?: { return?: number; conviction?: number };
      "60d"?: { return?: number; conviction?: number };
    };
  } | null;
  catalyst?: unknown;
  recent_disclosures: Disclosure[];
  quarterly_statements?: QuarterlyStatement[];
  history: CandleData[];
}

export default function StockTearsheetPage() {
  const params = useParams();
  const rawSymbol = params.symbol as string;
  const symbol = rawSymbol ? rawSymbol.toUpperCase() : "";

  const [data, setData] = useState<TearsheetData | null>(null);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [memo, setMemo] = useState<InvestmentMemo | null>(null);
  const [newsArticles, setNewsArticles] = useState<NewsArticle[]>([]);

  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [activeSection, setActiveSection] = useState<string>("tearsheet-overview");
  const [isBookmarked, setIsBookmarked] = useState<boolean>(Boolean(data?.is_watchlist));

  useEffect(() => {
    if (data?.is_watchlist !== undefined) {
      setIsBookmarked(Boolean(data.is_watchlist));
    }
  }, [data?.is_watchlist]);

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
    milEvents.emit("mil:open-copilot", { symbol });
  };

  // Synchronize active section with viewport scroll
  useEffect(() => {
    const handleScroll = () => {
      const scrollPos = window.scrollY + 120;
      for (let i = TEARSHEET_SECTIONS.length - 1; i >= 0; i--) {
        const sec = TEARSHEET_SECTIONS[i];
        const el = document.getElementById(sec.id);
        if (el && el.offsetTop <= scrollPos) {
          setActiveSection(sec.id);
          break;
        }
      }
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (id: string) => {
    setActiveSection(id);
    const el = document.getElementById(id);
    if (el) {
      const yOffset = -110;
      const y = el.getBoundingClientRect().top + window.pageYOffset + yOffset;
      window.scrollTo({ top: y, behavior: "smooth" });
    }
  };

  const [copied, setCopied] = useState<boolean>(false);

  const handleShare = () => {
    if (typeof window !== "undefined") {
      const url = window.location.href;
      navigator.clipboard
        .writeText(url)
        .then(() => {
          setCopied(true);
          setTimeout(() => setCopied(false), 2000);
        })
        .catch(() => {});
    }
  };

  const [ingestion, setIngestion] = useState<{
    isIngesting: boolean;
    progressPct: number;
    step: string;
    detail: string;
  }>({
    isIngesting: false,
    progressPct: 0,
    step: "IDLE",
    detail: "",
  });

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const fetchTearsheetRef = useRef<() => Promise<void>>();

  const startPolling = useCallback((generation: number, signal: AbortSignal) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(async () => {
      if (!requestLifecycle.isLatest("stock_detail_active", generation) || signal.aborted) {
        if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
        return;
      }
      try {
        const statusRes = await fetch(`${API_BASE}/stocks/${symbol}/status`, {
          headers: DEFAULT_HEADERS,
          signal,
          cache: "no-store",
        });
        if (!statusRes.ok) return;
        const statusJson = await statusRes.json();
        if (!requestLifecycle.isLatest("stock_detail_active", generation)) return;

        if (statusJson.status === "READY") {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          fetchTearsheetRef.current?.();
        } else if (statusJson.status === "FAILED") {
          if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
          setIngestion({ isIngesting: false, progressPct: 0, step: "FAILED", detail: "" });
          setError(statusJson.detail || "Dynamic ingestion failed for this ticker.");
        } else if (statusJson.status === "INGESTING") {
          setIngestion({
            isIngesting: true,
            progressPct: statusJson.progress_pct || 50,
            step: statusJson.step || "INGESTING",
            detail: statusJson.detail || "Ingesting...",
          });
        }
      } catch (e: unknown) {
        if (e instanceof Error && e.name === "AbortError") return;
        console.error("Polling error:", e);
      }
    }, 1500);
  }, [symbol]);

  const fetchTearsheet = useCallback(async () => {
    if (!symbol) return;
    const { signal, generation } = requestLifecycle.prepareRequest("stock_detail_active");

    try {
      setLoading(true);
      setError(null);
      setNotFound(false);

      const res = await fetch(`${API_BASE}/stocks/${symbol}/tearsheet`, {
        headers: DEFAULT_HEADERS,
        signal,
        cache: "no-store",
      });

      if (!requestLifecycle.isLatest("stock_detail_active", generation)) {
        return;
      }

      if (res.status === 202) {
        const json = await res.json();
        if (!requestLifecycle.isLatest("stock_detail_active", generation)) return;
        setIngestion({
          isIngesting: true,
          progressPct: json.progress_pct || 25,
          step: json.step || "QUEUED",
          detail:
            json.message ||
            "Discovered unseeded ticker. Ingesting 24-month historical series, fundamentals, and factors...",
        });
        setLoading(false);
        startPolling(generation, signal);
        return;
      }

      if (res.status === 404) {
        if (!requestLifecycle.isLatest("stock_detail_active", generation)) return;
        setNotFound(true);
        setLoading(false);
        return;
      }

      if (!res.ok) {
        throw new Error(`Failed to load tearsheet (HTTP ${res.status})`);
      }

      const json = await res.json();
      if (!requestLifecycle.isLatest("stock_detail_active", generation)) return;
      setData(json);

      // Fetch secondary intelligence concurrently
      const [fRes, nRes, mRes] = await Promise.allSettled([
        apiFetch<ForecastData>(`/stocks/${symbol}/forecast?horizon_days=20`, { signal }),
        apiFetch<{ articles: NewsArticle[] }>(`/stocks/${symbol}/news?limit=8`, { signal }),
        apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`, { signal }),
      ]);

      if (!requestLifecycle.isLatest("stock_detail_active", generation)) {
        return;
      }

      if (fRes.status === "fulfilled" && fRes.value) {
        setForecast(fRes.value);
      }
      if (nRes.status === "fulfilled" && nRes.value) {
        setNewsArticles(nRes.value.articles || []);
      }

      if (mRes.status === "fulfilled" && mRes.value) {
        setMemo(mRes.value);
      }

      setIngestion({ isIngesting: false, progressPct: 100, step: "READY", detail: "Ready" });
      setNotFound(false);
      setError(null);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        return;
      }
      if (requestLifecycle.isLatest("stock_detail_active", generation)) {
        console.error("Tearsheet fetch error:", err);
        const msg = err instanceof Error ? err.message : "Failed to load stock data";
        setError(msg);
      }
    } finally {
      if (requestLifecycle.isLatest("stock_detail_active", generation)) {
        setLoading(false);
      }
    }
  }, [symbol, startPolling]);

  useEffect(() => {
    fetchTearsheetRef.current = fetchTearsheet;
  }, [fetchTearsheet]);

  useEffect(() => {
    if (!symbol) return;

    try {
      const cached = peekCachedData<TearsheetData>(`/stocks/${symbol}/tearsheet`);
      if (cached) {
        setData(cached);
        setLoading(false);
      }
      const cachedF = peekCachedData<ForecastData>(`/stocks/${symbol}/forecast?horizon_days=20`);
      if (cachedF) setForecast(cachedF);
      const cachedM = peekCachedData<InvestmentMemo>(`/stocks/${symbol}/memo`);
      if (cachedM) setMemo(cachedM);
    } catch {}

    fetchTearsheet();

    const handleRefresh = () => {
      clearMemoryCache();
      fetchTearsheet();
    };

    window.addEventListener("mil:tearsheet-refresh", handleRefresh);
    window.addEventListener("mil:screener-refresh", handleRefresh);

    return () => {
      window.removeEventListener("mil:tearsheet-refresh", handleRefresh);
      window.removeEventListener("mil:screener-refresh", handleRefresh);
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      requestLifecycle.cleanup("stock_detail_active");
    };
  }, [symbol, fetchTearsheet]);

  useEffect(() => {
    if (data) {
      milEvents.emit("mil:context-update", {
        symbol: data.symbol,
        price: data.latest_ohlcv?.close ?? null,
        verdict: data.ml_forecast?.signal ?? null,
      });
    }
  }, [data]);

  // Loading Screen: Ingestion in Progress
  if (ingestion.isIngesting) {
    const isStep1Done = ingestion.progressPct >= 35;
    const isStep2Done = ingestion.progressPct >= 60;
    const isStep3Done = ingestion.progressPct >= 90;
    const isStep4Done = ingestion.progressPct >= 100;

    const isStep2Active = ingestion.progressPct >= 35 && ingestion.progressPct < 60;
    const isStep3Active = ingestion.progressPct >= 60 && ingestion.progressPct < 90;
    const isStep4Active = ingestion.progressPct >= 90 && ingestion.progressPct < 100;

    return (
      <div className="min-h-screen bg-[#040609] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300 relative">
        <Navbar />
        <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex items-center justify-center">
          <div className="max-w-2xl w-full p-8 rounded-3xl bg-[#080c14] border border-white/[0.12] shadow-[0_25px_70px_rgba(0,0,0,0.9)] space-y-8">
            <div className="text-center space-y-2">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-cyan-950/70 border border-cyan-500/40 text-cyan-400 text-xs font-mono shadow-[0_0_12px_rgba(6,182,212,0.2)]">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                <span>On-Demand Dynamic Ingestion</span>
              </div>
              <h2 className="text-2xl font-black text-white tracking-tight">
                Universal Ingestion: <span className="text-cyan-400 font-mono">{symbol}</span>
              </h2>
              <p className="text-xs text-slate-400 font-mono max-w-md mx-auto">
                {ingestion.detail || "Connecting to NSE pipeline, resolving ISIN, and synchronizing data..."}
              </p>
            </div>

            <div className="space-y-2">
              <div className="flex justify-between text-xs font-mono text-slate-400">
                <span>Pipeline Progress</span>
                <span className="text-cyan-400 font-bold tabular-nums">{ingestion.progressPct}%</span>
              </div>
              <div className="w-full h-2.5 bg-[#050810] rounded-full overflow-hidden p-0.5 border border-white/[0.08]">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 rounded-full transition-all duration-500 ease-out shadow-[0_0_15px_rgba(6,182,212,0.5)]"
                  style={{ width: `${Math.max(5, ingestion.progressPct)}%` }}
                />
              </div>
            </div>

            <div className="space-y-3.5 bg-[#050810]/70 p-5 rounded-2xl border border-white/[0.06] font-mono text-xs">
              <div className="flex items-center space-x-3">
                {isStep1Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                )}
                <span className={isStep1Done ? "line-through text-slate-400" : "text-cyan-300 font-semibold"}>
                  Resolving NSE Security Master & ISIN
                </span>
              </div>

              <div className="flex items-center space-x-3">
                {isStep2Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : isStep2Active ? (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                ) : (
                  <Circle className="w-5 h-5 text-slate-600 shrink-0" />
                )}
                <span className={isStep2Done ? "text-slate-400 line-through" : isStep2Active ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                  Backfilling 24-Month EOD Historical Bars
                </span>
              </div>

              <div className="flex items-center space-x-3">
                {isStep3Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : isStep3Active ? (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                ) : (
                  <Circle className="w-5 h-5 text-slate-600 shrink-0" />
                )}
                <span className={isStep3Done ? "text-slate-400 line-through" : isStep3Active ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                  Ingesting P&amp;L &amp; Balance Sheet Statements
                </span>
              </div>

              <div className="flex items-center space-x-3">
                {isStep4Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : isStep4Active ? (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                ) : (
                  <Circle className="w-5 h-5 text-slate-600 shrink-0" />
                )}
                <span className={isStep4Done ? "text-slate-400 line-through" : isStep4Active ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                  Computing 200-Day SMAs &amp; Factor Analytics
                </span>
              </div>
            </div>

            <div className="text-center">
              <p className="text-[11px] text-slate-500 font-mono">
                Auto-refreshing every 1.5s &middot; Background Worker Active
              </p>
            </div>
          </div>
        </main>
      </div>
    );
  }

  // Not Found Error Boundary
  if (notFound) {
    return (
      <div className="min-h-screen bg-[#030508] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
        <Navbar />
        <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex items-center justify-center">
          <div className="p-8 rounded-2xl bg-slate-900 border border-rose-900/40 text-center space-y-4 max-w-lg w-full shadow-2xl">
            <div className="w-14 h-14 rounded-full bg-rose-950/60 border border-rose-800/60 flex items-center justify-center mx-auto text-rose-400">
              <SearchX className="w-7 h-7" />
            </div>
            <div className="space-y-1">
              <h2 className="text-xl font-bold text-white">Symbol Not Found on NSE</h2>
              <p className="text-xs text-slate-400 font-mono">
                The symbol <span className="text-rose-400 font-bold">{symbol}</span> is not listed or actively traded on the National Stock Exchange of India (series &apos;EQ&apos;).
              </p>
            </div>
            <div className="pt-2">
              <Link
                href="/"
                className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-mono transition-colors"
              >
                <ArrowLeft className="w-4 h-4" />
                <span>Return to Dashboard</span>
              </Link>
            </div>
          </div>
        </main>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-[#030508] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
        <Navbar />
        <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6 pb-24 animate-pulse">
          <div className="h-8 w-48 bg-slate-900 rounded" />
          <div className="h-28 bg-slate-900/80 rounded-xl" />
          <div className="h-96 bg-slate-900/80 rounded-xl" />
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
            {[1, 2, 3, 4].map((i) => (
              <div key={i} className="h-32 bg-slate-900/80 rounded-xl" />
            ))}
          </div>
        </main>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="min-h-screen bg-[#030508] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
        <Navbar />
        <main className="flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex items-center justify-center">
          <div className="p-8 rounded-xl bg-slate-900/80 border border-slate-800 text-center space-y-4 max-w-xl w-full shadow-2xl">
            <AlertTriangle className="w-12 h-12 text-rose-500 mx-auto" />
            <h2 className="text-xl font-bold text-white">Stock Tearsheet Unavailable</h2>
            <p className="text-xs text-slate-400 font-mono">{error || `Symbol ${symbol} not found.`}</p>
            <Link
              href="/"
              className="inline-flex items-center space-x-2 px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-white text-xs font-mono transition-colors"
            >
              <ArrowLeft className="w-4 h-4" />
              <span>Return to Dashboard</span>
            </Link>
          </div>
        </main>
      </div>
    );
  }

  const isUp = data.technicals.ret_1d >= 0;
  const isAboveSma200 = data.technicals.price_above_sma200;
  const currentPrice = data.latest_ohlcv.close;

  // Forecast bounds for RiskRewardVectorBar
  const lastProjection = forecast?.projections?.[forecast.projections.length - 1];
  const hasValidForecast = Boolean(
    lastProjection &&
      typeof lastProjection.lower_95 === "number" &&
      typeof lastProjection.upper_80 === "number" &&
      currentPrice > 0
  );
  const forecastLower95 = hasValidForecast ? lastProjection!.lower_95 : null;
  const forecastUpper80 = hasValidForecast ? lastProjection!.upper_80 : null;

  // Factor Pentagon metrics
  const factorRoe = data.fundamentals.roe_pct;
  const factorDe = data.fundamentals.debt_to_equity;
  const factorOpm = data.fundamentals.opm_pct;
  const factorMom =
    data.technicals.ret_20d !== null && data.technicals.ret_20d !== undefined
      ? data.technicals.ret_20d * 100
      : null;
  const factorConv =
    data.ml_forecast?.conviction_score ??
    memo?.institutional_conviction_score ??
    null;

  return (
    <div className="min-h-screen bg-[#040609] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300 relative">
      <Navbar />
      <main className="relative z-10 flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 pb-24">
        {/* Top Back & Session Info Bar */}
        <div className="flex items-center justify-between gap-3 flex-wrap">
          <Link
            href="/"
            className="inline-flex items-center space-x-2 text-xs font-mono text-slate-400 hover:text-white transition-colors group px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-cyan-500/40"
          >
            <ArrowLeft className="w-4 h-4 text-cyan-400 group-hover:-translate-x-1 transition-transform" />
            <span>Back to Screener Workbench</span>
          </Link>

          <div className="flex items-center gap-2">
            <button
              onClick={handleShare}
              className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-xl bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.08] hover:border-cyan-500/40 text-xs font-mono text-slate-300 hover:text-white transition-all shadow-sm"
              title="Share Tearsheet Link"
            >
              <AnimatePresence mode="wait">
                {copied ? (
                  <motion.span
                    key="copied"
                    initial={{ opacity: 0, y: -4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 4 }}
                    className="flex items-center gap-1.5 text-emerald-400 font-semibold"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Copied Link!</span>
                  </motion.span>
                ) : (
                  <motion.span
                    key="share"
                    initial={{ opacity: 0, y: 4 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -4 }}
                    className="flex items-center gap-1.5 text-slate-300"
                  >
                    <Share2 className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Share</span>
                  </motion.span>
                )}
              </AnimatePresence>
            </button>

            <span className="text-xs text-slate-400 font-mono px-3 py-1 rounded-xl bg-white/[0.03] border border-white/[0.06]">
              Settled Session: <strong className="text-white tabular-nums">{data.as_of_date}</strong>
            </span>
          </div>
        </div>

        {/* Sticky Mobile/Desktop Section Jump Sub-Navigation */}
        <div className="sticky top-14 z-20 -mx-4 sm:-mx-6 lg:-mx-8 px-4 sm:px-6 lg:px-8 py-2 bg-[#050811]/90 backdrop-blur-md border-b border-white/[0.08] flex items-center gap-1.5 overflow-x-auto thin-scrollbar shadow-lg">
          {TEARSHEET_SECTIONS.map((sec) => (
            <button
              key={sec.id}
              onClick={() => scrollToSection(sec.id)}
              className={cn(
                "relative px-3 py-1 rounded-lg text-xs font-mono whitespace-nowrap transition-colors",
                activeSection === sec.id
                  ? "text-cyan-300 font-semibold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]"
              )}
            >
              {activeSection === sec.id && (
                <motion.div
                  layoutId="tearsheet-active-section"
                  className="absolute inset-0 bg-cyan-950/80 border border-cyan-500/40 rounded-lg shadow-[0_0_10px_rgba(6,182,212,0.25)]"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">{sec.label}</span>
            </button>
          ))}
        </div>

        {/* Hero Header Card */}
        <div
          id="tearsheet-overview"
          className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 sm:p-6 shadow-[0_12px_40px_rgba(0,0,0,0.6)] relative overflow-hidden space-y-4"
        >
          {/* Top specular hairline */}
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent pointer-events-none" />

          <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-5">
            <div className="min-w-0 space-y-2">
              <div className="flex flex-wrap items-center gap-2.5">
                <div className="flex items-center gap-2">
                  <h1 className="text-2xl sm:text-3xl font-extrabold text-white font-mono tracking-tight drop-shadow-[0_0_15px_rgba(255,255,255,0.2)]">
                    {data.symbol}
                  </h1>
                  <motion.button
                    onClick={handleToggleWatchlist}
                    whileTap={{ scale: 0.85 }}
                    className="p-1 rounded-lg hover:bg-white/[0.08] transition-colors"
                    title={isBookmarked ? "Remove from Watchlist" : "Pin to Watchlist"}
                  >
                    <motion.div
                      animate={isBookmarked ? { scale: [1, 1.35, 1], rotate: [0, 15, -15, 0] } : {}}
                      transition={{ duration: 0.35 }}
                    >
                      <Star
                        className={cn(
                          "w-5 h-5 transition-colors",
                          isBookmarked
                            ? "fill-amber-400 text-amber-400 drop-shadow-[0_0_10px_rgba(245,158,11,0.6)]"
                            : "text-slate-500 hover:text-amber-300"
                        )}
                      />
                    </motion.div>
                  </motion.button>
                </div>

                <span className="text-[11px] sm:text-xs px-2.5 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.1] text-slate-300 font-mono">
                  {data.isin}
                </span>
                <span className="text-[11px] sm:text-xs px-3 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-semibold shadow-[0_0_10px_rgba(6,182,212,0.2)]">
                  {data.sector}
                </span>
                {data.is_nifty50 && (
                  <span className="text-[11px] sm:text-xs px-2.5 py-0.5 rounded-full bg-indigo-950/80 border border-indigo-500/40 text-indigo-300 font-mono font-bold">
                    NIFTY 50
                  </span>
                )}
              </div>

              <p className="text-sm text-slate-300 font-medium">{data.company_name}</p>

              {data.notes && (
                <p className="text-xs text-slate-400 italic font-mono max-w-2xl bg-white/[0.02] p-2.5 rounded-lg border border-white/[0.04]">
                  Strategy Notes: &ldquo;{data.notes}&rdquo;
                </p>
              )}
            </div>

            {/* Right Side: Spot Price & Action CTAs */}
            <div className="flex flex-wrap items-center gap-4 lg:gap-6 shrink-0 lg:text-right">
              <div>
                <span className="text-xs text-slate-400 font-mono block">Latest Close</span>
                <div className="text-2xl sm:text-3xl font-extrabold text-white font-mono tracking-tight tabular-nums">
                  ₹<AnimatedNumber value={data.latest_ohlcv.close} duration={600} />
                </div>
              </div>

              <div
                className={cn(
                  "flex flex-col items-center justify-center px-4 py-2 rounded-xl border font-mono",
                  isUp
                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
                    : "bg-rose-500/10 border-rose-500/30 text-rose-400 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
                )}
              >
                <div className="flex items-center space-x-1 text-sm font-bold tabular-nums">
                  {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                  <span>
                    {data.technicals.ret_1d_pct >= 0 ? "+" : ""}
                    {data.technicals.ret_1d_pct.toFixed(2)}%
                  </span>
                </div>
                <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">
                  1D Change
                </span>
              </div>

              {/* Action Buttons */}
              <div className="flex items-center gap-2">
                <button
                  onClick={handleOpenCopilot}
                  title="Launch Quant Copilot Committee for this stock"
                  className="flex items-center gap-1.5 px-3 py-2 text-xs font-mono font-bold text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-500/40 rounded-xl transition-all shadow-sm"
                >
                  <BrainCircuit className="w-4 h-4 text-cyan-400" />
                  <span>Ask Copilot</span>
                </button>

                <Link
                  href={`/portfolio?symbol=${data.symbol}`}
                  title="Trade stock in Paper Trading Blotter"
                  className="flex items-center gap-1.5 px-3 py-2 text-xs font-mono font-bold text-emerald-300 bg-emerald-950/50 hover:bg-emerald-900/70 border border-emerald-500/40 rounded-xl transition-all shadow-sm"
                >
                  <Zap className="w-4 h-4 text-emerald-400" />
                  <span>Paper Trade</span>
                </Link>
              </div>
            </div>
          </div>

          {/* Watchlist Target Price / Stop Loss Ribbon */}
          {(data.target_price || data.stop_loss) && (
            <div className="pt-3 border-t border-white/[0.06] flex flex-wrap items-center gap-4 text-xs font-mono">
              {data.target_price && (
                <span className="flex items-center space-x-2 px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                  <Target className="w-3.5 h-3.5" />
                  <span className="tabular-nums">
                    Target Objective: <strong>₹{data.target_price.toFixed(2)}</strong> (
                    {(((data.target_price / data.latest_ohlcv.close) - 1.0) * 100).toFixed(1)}% upside)
                  </span>
                </span>
              )}
              {data.stop_loss && (
                <span className="flex items-center space-x-2 px-3 py-1 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400">
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span className="tabular-nums">
                    Downside Stop: <strong>₹{data.stop_loss.toFixed(2)}</strong> (
                    {(((data.stop_loss / data.latest_ohlcv.close) - 1.0) * 100).toFixed(1)}% risk)
                  </span>
                </span>
              )}
            </div>
          )}
        </div>

        {/* Bento Grid Row 1: StockChart (8 cols) + 20-Day Forecast Cone (4 cols) */}
        <div id="tearsheet-chart" className="grid grid-cols-1 xl:grid-cols-12 gap-6 scroll-mt-28">
          <section
            className={
              forecast && forecast.projections && forecast.projections.length > 0
                ? "xl:col-span-8"
                : "xl:col-span-12"
            }
          >
            <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-4 shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
              <StockChart
                symbol={data.symbol}
                data={data.history}
                sma200={data.technicals.sma_200}
                forecast={forecast}
              />
            </div>
          </section>

          {/* 20-Day Econometric Forecast & Tail Risk Card */}
          {forecast && forecast.projections && forecast.projections.length > 0 && (
            <section className="xl:col-span-4 bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_12px_40px_rgba(0,0,0,0.6)] flex flex-col justify-between">
              <div>
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
                  <div className="flex items-center space-x-2.5">
                    <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.15)]">
                      <Activity className="w-4 h-4" />
                    </div>
                    <div>
                      <h3 className="text-base font-bold text-white font-mono tracking-tight">
                        20D Forecast &amp; Tail Risk
                      </h3>
                      <p className="text-[11px] text-slate-400 font-mono">
                        GARCH(1,1) &middot; OU Mean-Reversion
                      </p>
                    </div>
                  </div>

                  <span
                    className={cn(
                      "text-xs px-2.5 py-0.5 rounded-full font-mono font-semibold border",
                      forecast.volatility_regime === "LOW"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : forecast.volatility_regime === "NORMAL"
                        ? "bg-cyan-500/10 text-cyan-400 border-cyan-500/30"
                        : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                    )}
                  >
                    {forecast.volatility_regime} DISPERSION
                  </span>
                </div>

                {/* Forecast Telemetry Grid (2x2) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                  {/* Expected 20D Price */}
                  <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                    <span className="text-[11px] text-slate-400 block uppercase tracking-wider">
                      Expected 20D Price
                    </span>
                    <div className="text-xl font-black text-cyan-300 mt-1 tabular-nums">
                      ₹{forecast.projections[forecast.projections.length - 1].expected.toFixed(2)}
                    </div>
                    <div className="text-[11px] text-slate-400 mt-1 tabular-nums">
                      {(() => {
                        const expPrice =
                          forecast.projections[forecast.projections.length - 1].expected;
                        const diff = expPrice - data.latest_ohlcv.close;
                        const pct = (diff / data.latest_ohlcv.close) * 100;
                        return (
                          <span
                            className={
                              diff >= 0
                                ? "text-emerald-400 font-semibold"
                                : "text-rose-400 font-semibold"
                            }
                          >
                            {diff >= 0 ? "+" : ""}
                            {diff.toFixed(2)} ({pct >= 0 ? "+" : ""}
                            {pct.toFixed(1)}%)
                          </span>
                        );
                      })()}
                    </div>
                  </div>

                  {/* 80% Trajectory Band */}
                  <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                    <span className="text-[11px] text-slate-400 block uppercase tracking-wider">
                      80% Trajectory Band
                    </span>
                    <div className="text-sm font-bold text-white mt-1.5 tabular-nums">
                      ₹{forecast.projections[forecast.projections.length - 1].lower_80.toFixed(0)} – ₹
                      {forecast.projections[forecast.projections.length - 1].upper_80.toFixed(0)}
                    </div>
                    <div className="text-[10px] text-slate-500 mt-1">High Probability Band</div>
                  </div>

                  {/* 95% Downside Floor */}
                  <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                    <span className="text-[11px] text-slate-400 block uppercase tracking-wider">
                      95% Downside Floor
                    </span>
                    <div className="text-xl font-black text-rose-400 mt-1 tabular-nums">
                      ₹{forecast.projections[forecast.projections.length - 1].lower_95.toFixed(2)}
                    </div>
                    <div className="text-[10px] text-rose-400/90 mt-1 tabular-nums font-semibold">
                      {(() => {
                        const floorPrice =
                          forecast.projections[forecast.projections.length - 1].lower_95;
                        const maxDrawdownPct =
                          ((floorPrice / data.latest_ohlcv.close) - 1.0) * 100;
                        return `${maxDrawdownPct.toFixed(1)}% Max Tail Risk`;
                      })()}
                    </div>
                  </div>

                  {/* Model Calibration */}
                  <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                    <span className="text-[11px] text-slate-400 block uppercase tracking-wider">
                      Annualized Vol
                    </span>
                    <div className="text-xl font-black text-white mt-1 tabular-nums">
                      {(forecast.annualized_volatility * 100).toFixed(1)}%
                    </div>
                    <div className="text-[10px] text-slate-400 mt-1 tabular-nums">
                      {forecast.garch_parameters ? (
                        <span>
                          α+β: <strong>{forecast.garch_parameters.persistence.toFixed(3)}</strong>
                        </span>
                      ) : (
                        <span>Calibrated</span>
                      )}
                    </div>
                  </div>
                </div>
              </div>

              <div className="mt-4 pt-3 border-t border-white/[0.06] flex items-center justify-between text-xs font-mono text-slate-400">
                <span>Risk Anchor:</span>
                <span className="text-cyan-300 font-semibold">GARCH(1,1) Volatility Envelope</span>
              </div>
            </section>
          )}
        </div>

        {/* Section: Quantitative Attribution & Factor Radar */}
        <section id="tearsheet-attribution" className="space-y-4 scroll-mt-28">
          <div className="flex items-center space-x-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <h2 className="text-base font-bold text-white font-mono tracking-tight">
              Quantitative Multi-Horizon Attribution &amp; Factor Pentagon
            </h2>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* 1. Multi-Horizon ML Alpha Consensus */}
            <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col justify-between space-y-4">
              <div>
                <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
                  <span className="text-xs font-mono font-semibold text-white uppercase tracking-wider">
                    ML Multi-Horizon Alpha
                  </span>
                  <span className="text-xs font-mono font-bold text-cyan-300 px-2.5 py-0.5 rounded-lg bg-cyan-950/80 border border-cyan-500/40">
                    {data.ml_forecast?.signal || "CALIBRATED"}
                  </span>
                </div>

                <div className="space-y-3 pt-3 font-mono">
                  {/* 20D Tactical Horizon */}
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-300 flex items-center gap-1.5">
                        <span className="px-1.5 py-0.2 rounded text-[9px] bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-bold">
                          20D Tactical
                        </span>
                        <span className="text-slate-500 text-[10px]">(62.5% weight)</span>
                      </span>
                      <span className="text-cyan-300 font-semibold tabular-nums text-xs">
                        {data.ml_forecast?.predicted_excess_return !== undefined
                          ? `${(data.ml_forecast.predicted_excess_return * 100).toFixed(1)}%`
                          : "Active"}
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-900/80 rounded-full overflow-hidden border border-white/[0.06]">
                      <div className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full w-3/4 shadow-[0_0_8px_rgba(6,182,212,0.6)]" />
                    </div>
                  </div>

                  {/* 60D Trend Horizon */}
                  <div>
                    <div className="flex items-center justify-between text-xs mb-1">
                      <span className="text-slate-300 flex items-center gap-1.5">
                        <span className="px-1.5 py-0.2 rounded text-[9px] bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 font-bold">
                          60D Trend
                        </span>
                        <span className="text-slate-500 text-[10px]">(37.5% weight)</span>
                      </span>
                      <span className="text-emerald-300 font-semibold tabular-nums text-xs">
                        {data.technicals.sma_200 && data.latest_ohlcv.close > data.technicals.sma_200
                          ? "Bullish Drift"
                          : "Neutral/Defensive"}
                      </span>
                    </div>
                    <div className="h-1.5 w-full bg-slate-900/80 rounded-full overflow-hidden border border-white/[0.06]">
                      <div className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full w-2/3 shadow-[0_0_8px_rgba(16,185,129,0.6)]" />
                    </div>
                  </div>

                  {/* 5D Gate */}
                  <div className="p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.05] flex items-center justify-between text-[11px]">
                    <span className="text-slate-400">5D Mean-Reversion Gate:</span>
                    <span className="font-bold text-slate-300">
                      {data.technicals.ret_5d !== null
                        ? `${data.technicals.ret_5d >= 0 ? "+" : ""}${(data.technicals.ret_5d * 100).toFixed(1)}% (5D Return)`
                        : "Filtering Noise"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-white/[0.06] text-[11px] font-mono text-slate-400 flex items-center justify-between">
                <span>Primary Alpha Factor:</span>
                <span className="text-cyan-300 font-semibold truncate max-w-[180px]">
                  {data.ml_forecast?.primary_driver || "Low-Vol Quality Momentum"}
                </span>
              </div>
            </div>

            {/* 2. Factor Pentagon Radar */}
            <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col items-center justify-between">
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

            {/* 3. Institutional Conviction & Risk-Reward Bounds */}
            <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)] flex flex-col justify-between space-y-3">
              <div>
                <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
                  <span className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wider">
                    Institutional Conviction
                  </span>
                  <span className="text-[10px] font-mono text-slate-400">Target: 3–12 Months</span>
                </div>

                <div className="flex items-center justify-center py-2">
                  <RadialConvictionGauge score={factorConv} />
                </div>
              </div>

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
        </section>

        {/* Institutional Investment Decision Memo */}
        <section id="tearsheet-thesis" className="scroll-mt-28">
          <InvestmentMemoCard symbol={data.symbol} initialMemo={memo} />
        </section>

        {/* Core 5-Card Bento Grid: Fundamentals & Technicals (with strict null checking) */}
        <section id="tearsheet-health" className="space-y-4 scroll-mt-28">
          <div className="flex items-center space-x-2">
            <Activity className="w-4 h-4 text-cyan-400" />
            <h2 className="text-base font-bold text-white font-mono tracking-tight">
              Fundamentals &amp; Technical Positioning
            </h2>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4">
            {/* Card 1: Debt-to-Equity (D/E) */}
            <BentoCard
              title="DEBT-TO-EQUITY (D/E)"
              value={
                data.fundamentals.debt_to_equity !== null
                  ? `${data.fundamentals.debt_to_equity.toFixed(2)}x`
                  : "Awaiting BS"
              }
              subLabel={
                data.fundamentals.debt_to_equity === null
                  ? "Awaiting Balance Sheet"
                  : data.fundamentals.debt_to_equity < 0.5
                  ? "< 0.5 Conservative Threshold Met"
                  : "Elevated Leverage Ratio"
              }
              isPositive={
                data.fundamentals.debt_to_equity === null
                  ? undefined
                  : data.fundamentals.debt_to_equity < 0.5
              }
              badge={
                data.fundamentals.debt_to_equity !== null && data.fundamentals.debt_to_equity === 0
                  ? "ZERO DEBT"
                  : undefined
              }
            />

            {/* Card 2: Return on Equity (ROE %) */}
            <BentoCard
              title="RETURN ON EQUITY (ROE)"
              value={
                data.fundamentals.roe_pct !== null
                  ? `${data.fundamentals.roe_pct.toFixed(1)}%`
                  : "Awaiting Filing"
              }
              subLabel={
                data.fundamentals.roe_pct === null
                  ? "Awaiting Earnings Filing"
                  : data.fundamentals.roe_pct > 15.0
                  ? "> 15% Hurdle Cleared (High Quality)"
                  : "Sub-15% Capital Return"
              }
              isPositive={
                data.fundamentals.roe_pct === null
                  ? undefined
                  : data.fundamentals.roe_pct > 15.0
              }
              badge={
                data.fundamentals.roe_pct !== null && data.fundamentals.roe_pct > 25
                  ? "TOP DECILE"
                  : undefined
              }
            />

            {/* Card 3: TTM P/E Ratio (Coalesced) */}
            <BentoCard
              title="TTM P/E RATIO"
              value={
                data.fundamentals.ttm_pe !== null
                  ? `${data.fundamentals.ttm_pe.toFixed(1)}x`
                  : "Awaiting Earnings"
              }
              subLabel={
                data.fundamentals.ttm_pe === null
                  ? "Awaiting TTM Earnings"
                  : data.fundamentals.ttm_pe < 25.0
                  ? "< 25x Reasonable Multiple"
                  : "Growth / Premium Valuation"
              }
              isPositive={
                data.fundamentals.ttm_pe === null
                  ? undefined
                  : data.fundamentals.ttm_pe < 25.0
              }
              badge={
                data.fundamentals.ttm_pe !== null && data.fundamentals.ttm_pe < 15
                  ? "VALUE MULTIPLE"
                  : undefined
              }
            />

            {/* Card 4: 60-Day Rolling Beta vs Nifty 50 */}
            <BentoCard
              title="60D ROLLING BETA"
              value={
                data.technicals.beta_60d_nifty !== null
                  ? data.technicals.beta_60d_nifty.toFixed(2)
                  : "Awaiting Cal"
              }
              subLabel={
                data.technicals.beta_60d_nifty === null
                  ? "Awaiting Benchmark Calibration"
                  : Math.abs(data.technicals.beta_60d_nifty) < 0.5
                  ? "Low systematic benchmark exposure"
                  : "Standard market systematic co-movement"
              }
              isPositive={undefined}
            />

            {/* Card 5: Distance from 200-day SMA */}
            <BentoCard
              title="DISTANCE FROM 200 SMA"
              value={
                data.technicals.dist_sma200_pct !== null
                  ? `${data.technicals.dist_sma200_pct >= 0 ? "+" : ""}${data.technicals.dist_sma200_pct.toFixed(1)}%`
                  : "Awaiting Trend"
              }
              subLabel={
                data.technicals.dist_sma200_pct === null
                  ? "Awaiting Trend History"
                  : isAboveSma200
                  ? "✓ Price > 200 SMA (Structural Uptrend)"
                  : "⚠️ Price < 200 SMA (Below Trend)"
              }
              isPositive={
                data.technicals.dist_sma200_pct === null ? undefined : isAboveSma200
              }
            />
          </div>

          {/* Market Microstructure & Institutional Accumulation Strip */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2 text-xs font-mono">
            <div className="bg-[#050810]/80 p-3 rounded-xl border border-cyan-500/20 shadow-[0_0_15px_rgba(6,182,212,0.08)]">
              <span className="text-cyan-400 block text-[11px] font-semibold tracking-wide uppercase">Delivery %</span>
              <span className="text-cyan-200 font-bold font-mono text-base mt-0.5 block tabular-nums">
                {data.technicals.delivery_pct !== null && data.technicals.delivery_pct !== undefined
                  ? `${data.technicals.delivery_pct.toFixed(1)}%`
                  : "—"}
              </span>
              <span className="text-[10px] text-slate-500 block mt-0.5">
                {(data.technicals.delivery_pct ?? 0) >= 50
                  ? "Institutional Accumulation"
                  : "Exchange Settled"}
              </span>
            </div>

            <div className="bg-[#050810]/80 p-3 rounded-xl border border-white/[0.08]">
              <span className="text-slate-400 block text-[11px] font-semibold tracking-wide uppercase">Turnover (₹ Cr)</span>
              <span className="text-slate-100 font-bold font-mono text-base mt-0.5 block tabular-nums">
                {data.technicals.turnover_cr !== null && data.technicals.turnover_cr !== undefined
                  ? `₹${data.technicals.turnover_cr.toFixed(2)} Cr`
                  : "—"}
              </span>
              <span className="text-[10px] text-slate-500 block mt-0.5">Daily Traded Liquidity</span>
            </div>

            <div className="bg-[#050810]/80 p-3 rounded-xl border border-white/[0.08]">
              <span className="text-slate-400 block text-[11px] font-semibold tracking-wide uppercase">20D Volume Ratio</span>
              <span className="text-slate-100 font-bold font-mono text-base mt-0.5 block tabular-nums">
                {data.technicals.volume_ratio_20d !== null && data.technicals.volume_ratio_20d !== undefined
                  ? `${data.technicals.volume_ratio_20d.toFixed(2)}x`
                  : "1.00x"}
              </span>
              <span className="text-[10px] text-slate-500 block mt-0.5">
                {(data.technicals.volume_ratio_20d ?? 1) >= 2.0 ? "Volume Breakout Alert" : "Normal Baseline Flow"}
              </span>
            </div>

            <div className="bg-[#050810]/80 p-3 rounded-xl border border-white/[0.08]">
              <span className="text-slate-400 block text-[11px] font-semibold tracking-wide uppercase">From 52W High</span>
              <span className={`font-bold font-mono text-base mt-0.5 block tabular-nums ${
                (data.technicals.pct_from_52w_high ?? 0) >= -5 ? "text-emerald-400" : "text-amber-400"
              }`}>
                {data.technicals.pct_from_52w_high !== null && data.technicals.pct_from_52w_high !== undefined
                  ? `${data.technicals.pct_from_52w_high >= 0 ? "+" : ""}${data.technicals.pct_from_52w_high.toFixed(1)}%`
                  : "—"}
              </span>
              <span className="text-[10px] text-slate-500 block mt-0.5">52W Drawdown / Premium</span>
            </div>
          </div>

          {/* Supplementary Metrics Ribbon */}
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 pt-2 text-xs font-mono">
            <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
              <span className="text-slate-400 block text-[11px]">20-Day SMA</span>
              <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
                {data.technicals.sma_20 !== null ? `₹${data.technicals.sma_20.toFixed(2)}` : "—"}
              </span>
            </div>

            <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
              <span className="text-slate-400 block text-[11px]">50-Day SMA</span>
              <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
                {data.technicals.sma_50 !== null ? `₹${data.technicals.sma_50.toFixed(2)}` : "—"}
              </span>
            </div>

            <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
              <span className="text-slate-400 block text-[11px]">200-Day SMA</span>
              <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
                {data.technicals.sma_200 !== null ? `₹${data.technicals.sma_200.toFixed(2)}` : "—"}
              </span>
            </div>

            <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
              <span className="text-slate-400 block text-[11px]">Volume Z-Score</span>
              <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
                {data.technicals.volume_zscore_50d !== null && data.technicals.volume_zscore_50d !== undefined
                  ? `${data.technicals.volume_zscore_50d >= 0 ? "+" : ""}${data.technicals.volume_zscore_50d.toFixed(2)}σ`
                  : "0.00σ"}
              </span>
            </div>

            <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
              <span className="text-slate-400 block text-[11px]">Operating Margin</span>
              <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
                {data.fundamentals.opm_pct !== null ? `${data.fundamentals.opm_pct.toFixed(1)}%` : "—"}
              </span>
            </div>

            <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
              <span className="text-slate-400 block text-[11px]">20D Volatility</span>
              <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
                {data.technicals.volatility_annualized !== null
                  ? `${(data.technicals.volatility_annualized * 100).toFixed(1)}%`
                  : "—"}
              </span>
            </div>
          </div>
        </section>

        {/* Quarterly Financials & Performance Trajectory */}
        <section id="tearsheet-financials" className="scroll-mt-28">
          <QuarterlyFinancialsCard
            symbol={data.symbol}
            statements={data.quarterly_statements}
          />
        </section>

        {/* Unified Live Intelligence & Corporate Filings Hub */}
        <section id="tearsheet-wire" className="scroll-mt-28">
          <UnifiedIntelligenceHub
            symbol={data.symbol}
            initialDisclosures={data.recent_disclosures}
            initialNews={newsArticles}
          />
        </section>
      </main>
    </div>
  );
}
