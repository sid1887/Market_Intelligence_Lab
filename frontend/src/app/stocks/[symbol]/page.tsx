"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import dynamic from "next/dynamic";
import type { CandleData, ForecastData } from "@/components/StockChart";

const StockChart = dynamic(() => import("@/components/StockChart"), {
  ssr: false,
  loading: () => (
    <div className="h-[440px] w-full flex items-center justify-center bg-[#050811] rounded-xl border border-white/[0.06] text-xs font-mono text-slate-500">
      Loading chart engine...
    </div>
  ),
});

import NewsImpactCard, { NewsArticle } from "@/components/NewsImpactCard";
import InvestmentMemoCard, { InvestmentMemo } from "@/components/InvestmentMemoCard";
import Navbar from "@/components/Navbar";
import { requestLifecycle, API_BASE, DEFAULT_HEADERS, apiFetch } from "@/lib/api";
import {
  ArrowLeft,
  TrendingUp,
  TrendingDown,
  Target,
  ShieldAlert,
  FileText,
  ExternalLink,
  ShieldCheck,
  AlertTriangle,
  Clock,
  Sparkles,
  Activity,
  CheckCircle2,
  Loader2,
  Circle,
  SearchX
} from "lucide-react";

interface Disclosure {
  disclosure_id: string;
  broadcast_timestamp: string;
  effective_session_date: string;
  category: string;
  subject: string;
  details_summary: string | null;
  source_url: string | null;
  verification_status: string;
  audit_status: string | null;
  dividend_declared: number | null;
  operating_margin_pct: number | null;
}

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
  };
  fundamentals: {
    roe_pct: number | null;
    debt_to_equity: number | null;
    ttm_pe: number | null;
    opm_pct: number | null;
  };
  recent_disclosures: Disclosure[];
  history: CandleData[];
}

export default function StockTearsheetPage() {
  const params = useParams();
  const rawSymbol = params.symbol as string;
  const symbol = rawSymbol ? rawSymbol.toUpperCase() : "";

  const [data, setData] = useState<TearsheetData | null>(null);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [newsArticles, setNewsArticles] = useState<NewsArticle[]>([]);
  const [newsLoading, setNewsLoading] = useState<boolean>(true);
  const [memo, setMemo] = useState<InvestmentMemo | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState<boolean>(false);
  const [ingestion, setIngestion] = useState<{
    isIngesting: boolean;
    progressPct: number;
    step: string;
    detail: string;
  }>({
    isIngesting: false,
    progressPct: 0,
    step: "IDLE",
    detail: ""
  });

  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);
  const fetchTearsheetRef = useRef<() => Promise<void>>();

  const startPolling = useCallback((generation: number, signal: AbortSignal) => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(async () => {
      if (!requestLifecycle.isLatest('stock_detail_active', generation) || signal.aborted) {
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
        if (!requestLifecycle.isLatest('stock_detail_active', generation)) return;

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
            detail: statusJson.detail || "Ingesting..."
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
    const { signal, generation } = requestLifecycle.prepareRequest('stock_detail_active');

    try {
      setLoading(true);
      setError(null);
      setNotFound(false);

      const res = await fetch(`${API_BASE}/stocks/${symbol}/tearsheet`, {
        headers: DEFAULT_HEADERS,
        signal,
        cache: "no-store",
      });

      if (!requestLifecycle.isLatest('stock_detail_active', generation)) {
        return; // Dropped: Out-of-order response superseded by a newer ticker request
      }

      if (res.status === 202) {
        const json = await res.json();
        if (!requestLifecycle.isLatest('stock_detail_active', generation)) return;
        setIngestion({
          isIngesting: true,
          progressPct: json.progress_pct || 25,
          step: json.step || "QUEUED",
          detail: json.message || "Discovered unseeded ticker. Ingesting 24-month historical series, fundamentals, and factors..."
        });
        setLoading(false);
        startPolling(generation, signal);
        return;
      }

      if (res.status === 404) {
        if (!requestLifecycle.isLatest('stock_detail_active', generation)) return;
        setNotFound(true);
        setLoading(false);
        return;
      }

      if (!res.ok) {
        throw new Error(`Failed to load tearsheet (HTTP ${res.status})`);
      }

      const json = await res.json();
      if (!requestLifecycle.isLatest('stock_detail_active', generation)) return;
      setData(json);

      // Fetch Forecast, News, and Memo concurrently with SWR caching & monotonic signal guard
      setNewsLoading(true);
      const [fRes, nRes, mRes] = await Promise.allSettled([
        apiFetch<ForecastData>(`/stocks/${symbol}/forecast?horizon_days=20`, { signal }),
        apiFetch<{ articles: NewsArticle[] }>(`/stocks/${symbol}/news?limit=5`, { signal }),
        apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`, { signal })
      ]);

      if (!requestLifecycle.isLatest('stock_detail_active', generation)) {
        return; // Dropped: superseded while secondary fetches were in-flight
      }

      if (fRes.status === "fulfilled" && fRes.value) {
        try {
          const fJson = fRes.value;
          if (requestLifecycle.isLatest('stock_detail_active', generation)) {
            setForecast(fJson);
          }
        } catch {}
      }

      if (nRes.status === "fulfilled" && nRes.value) {
        try {
          const nJson = nRes.value;
          if (requestLifecycle.isLatest('stock_detail_active', generation)) {
            setNewsArticles(nJson.articles || []);
          }
        } catch {}
      }
      setNewsLoading(false);

      if (mRes.status === "fulfilled" && mRes.value) {
        try {
          const mJson = mRes.value;
          if (requestLifecycle.isLatest('stock_detail_active', generation)) {
            setMemo(mJson);
          }
        } catch {}
      }

      setIngestion({ isIngesting: false, progressPct: 100, step: "READY", detail: "Ready" });
      setNotFound(false);
      setError(null);
    } catch (err: unknown) {
      if (err instanceof Error && err.name === "AbortError") {
        return; // Stale fetch aborted cleanly; do not update UI or show error
      }
      if (requestLifecycle.isLatest('stock_detail_active', generation)) {
        console.error("Tearsheet fetch error:", err);
        const msg = err instanceof Error ? err.message : "Failed to load stock data";
        setError(msg);
      }
    } finally {
      if (requestLifecycle.isLatest('stock_detail_active', generation)) {
        setLoading(false);
      }
    }
  }, [symbol, startPolling]);

  useEffect(() => {
    fetchTearsheetRef.current = fetchTearsheet;
  }, [fetchTearsheet]);

  useEffect(() => {
    if (!symbol) return;
    fetchTearsheet();

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
      requestLifecycle.cleanup('stock_detail_active');
    };
  }, [symbol, fetchTearsheet]);

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

            {/* Progress Bar & Percentage */}
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

            {/* Checklist */}
            <div className="space-y-3.5 bg-[#050810]/70 p-5 rounded-2xl border border-white/[0.06] font-mono text-xs">
              {/* Step 1 */}
              <div className="flex items-center space-x-3">
                {isStep1Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                )}
                <span className={isStep1Done ? "text-slate-200 line-through text-slate-400" : "text-cyan-300 font-semibold"}>
                  Resolving NSE Security Master & ISIN
                </span>
              </div>

              {/* Step 2 */}
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

              {/* Step 3 */}
              <div className="flex items-center space-x-3">
                {isStep3Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : isStep3Active ? (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                ) : (
                  <Circle className="w-5 h-5 text-slate-600 shrink-0" />
                )}
                <span className={isStep3Done ? "text-slate-400 line-through" : isStep3Active ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                  Ingesting P&L & Balance Sheet Statements
                </span>
              </div>

              {/* Step 4 */}
              <div className="flex items-center space-x-3">
                {isStep4Done ? (
                  <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
                ) : isStep4Active ? (
                  <Loader2 className="w-5 h-5 text-cyan-400 animate-spin shrink-0" />
                ) : (
                  <Circle className="w-5 h-5 text-slate-600 shrink-0" />
                )}
                <span className={isStep4Done ? "text-slate-400 line-through" : isStep4Active ? "text-cyan-300 font-semibold" : "text-slate-500"}>
                  Computing 200-Day SMAs & Factor Analytics
                </span>
              </div>
            </div>

            <div className="text-center">
              <p className="text-[11px] text-slate-500 font-mono">
                Auto-refreshing every 1.5s · Background Worker Active
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
            {[1, 2, 3, 4].map(i => (
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

  return (
    <div className="min-h-screen bg-[#040609] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300 relative">
      <Navbar />
      <main className="relative z-10 flex-1 max-w-[1600px] w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 pb-24">
        {/* Back Link & Navigation Bar */}
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center space-x-2 text-xs font-mono text-slate-400 hover:text-white transition-colors group px-3 py-1.5 rounded-xl bg-white/[0.03] border border-white/[0.06] hover:border-cyan-500/40"
          >
            <ArrowLeft className="w-4 h-4 text-cyan-400 group-hover:-translate-x-1 transition-transform" />
            <span>Back to Screener Workbench</span>
          </Link>

          <span className="text-xs text-slate-400 font-mono px-3 py-1 rounded-xl bg-white/[0.03] border border-white/[0.06]">
            Settled Session: <strong className="text-white tabular-nums">{data.as_of_date}</strong>
          </span>
        </div>

      {/* Hero Header Card */}
      <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-4 sm:p-6 shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white font-mono tracking-tight drop-shadow-[0_0_15px_rgba(255,255,255,0.2)]">
                {data.symbol}
              </h1>
              <span className="text-[11px] sm:text-xs px-2.5 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.1] text-slate-300 font-mono">
                {data.isin}
              </span>
              <span className="text-[11px] sm:text-xs px-3 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-semibold shadow-[0_0_10px_rgba(6,182,212,0.2)]">
                {data.sector}
              </span>
              {data.is_watchlist ? (
                <span className="text-[11px] sm:text-xs px-3 py-0.5 rounded-full bg-indigo-950/80 border border-indigo-500/40 text-indigo-300 font-semibold flex items-center space-x-1.5 shadow-[0_0_10px_rgba(99,102,241,0.2)]">
                  <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
                  <span>WATCHLIST HOLDING</span>
                </span>
              ) : null}
              {data.is_nifty50 ? (
                <span className="text-[11px] sm:text-xs px-2.5 py-0.5 rounded-full bg-white/[0.05] border border-white/[0.1] text-slate-300 font-mono">
                  NIFTY 50 CONSTITUENT
                </span>
              ) : null}
            </div>

            <p className="text-sm text-slate-300 mt-1.5 font-medium truncate">{data.company_name}</p>
            {data.notes && (
              <p className="text-xs text-slate-400 mt-1 italic font-mono max-w-2xl bg-white/[0.02] p-2 rounded-lg border border-white/[0.04]">
                Strategy Notes: &ldquo;{data.notes}&rdquo;
              </p>
            )}
          </div>

          {/* Right Price & Return Stack (Responsive) */}
          <div className="flex flex-wrap items-center gap-4 sm:gap-6 pt-2 sm:pt-0 sm:text-right shrink-0">
            <div>
              <span className="text-[11px] sm:text-xs text-slate-400 font-mono block">Latest Close</span>
              <div className="text-2xl sm:text-3xl font-extrabold text-white font-mono tracking-tight tabular-nums">
                ₹{data.latest_ohlcv.close.toFixed(2)}
              </div>
            </div>

            <div
              className={`flex flex-col items-center justify-center px-3.5 py-1.5 sm:px-4 sm:py-2 rounded-xl border font-mono ${
                isUp
                  ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
                  : "bg-rose-500/10 border-rose-500/30 text-rose-400 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
              }`}
            >
              <div className="flex items-center space-x-1 text-sm font-bold tabular-nums">
                {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                <span>{data.technicals.ret_1d_pct >= 0 ? "+" : ""}{data.technicals.ret_1d_pct.toFixed(2)}%</span>
              </div>
              <span className="text-[10px] text-slate-400 uppercase tracking-wider mt-0.5">1D Change</span>
            </div>
          </div>
        </div>

        {/* Watchlist Target Price / Stop Loss Ribbon */}
        {(data.target_price || data.stop_loss) && (
          <div className="mt-4 pt-3.5 border-t border-white/[0.06] flex flex-wrap items-center gap-4 text-xs font-mono">
            {data.target_price && (
              <span className="flex items-center space-x-2 px-3 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
                <Target className="w-3.5 h-3.5" />
                <span className="tabular-nums">Target Objective: <strong>₹{data.target_price.toFixed(2)}</strong> ({(((data.target_price / data.latest_ohlcv.close) - 1.0) * 100).toFixed(1)}% upside)</span>
              </span>
            )}
            {data.stop_loss && (
              <span className="flex items-center space-x-2 px-3 py-1 rounded-lg bg-rose-500/10 border border-rose-500/30 text-rose-400">
                <ShieldAlert className="w-3.5 h-3.5" />
                <span className="tabular-nums">Downside Stop: <strong>₹{data.stop_loss.toFixed(2)}</strong> ({(((data.stop_loss / data.latest_ohlcv.close) - 1.0) * 100).toFixed(1)}% risk)</span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Bento Grid Row 1: StockChart (8 cols) + 20-Day Forecast Cone (4 cols) */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* Candlestick Chart */}
        <section className={forecast && forecast.projections && forecast.projections.length > 0 ? "xl:col-span-8" : "xl:col-span-12"}>
          <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-4 shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
            <StockChart
              symbol={data.symbol}
              data={data.history}
              sma200={data.technicals.sma_200}
              forecast={forecast}
            />
          </div>
        </section>

        {/* Milestone B7.0: 20-Day Econometric Forecast & Tail Risk Card */}
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

                <div className="flex items-center space-x-2">
                  <span
                    className={`text-xs px-2.5 py-0.5 rounded-full font-mono font-semibold border ${
                      forecast.volatility_regime === "LOW"
                        ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30"
                        : forecast.volatility_regime === "NORMAL"
                        ? "bg-cyan-500/10 text-cyan-400 border-cyan-500/30"
                        : "bg-amber-500/10 text-amber-400 border-amber-500/30"
                    }`}
                  >
                    {forecast.volatility_regime} DISPERSION
                  </span>
                </div>
              </div>

              {/* Forecast Telemetry Grid (2x2) */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mt-4">
                {/* 1. Expected 20D Price */}
                <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                  <span className="text-[11px] text-slate-400 block uppercase tracking-wider">Expected 20D Price</span>
                  <div className="text-xl font-black text-cyan-300 mt-1 tabular-nums">
                    ₹{forecast.projections[forecast.projections.length - 1].expected.toFixed(2)}
                  </div>
                  <div className="text-[11px] text-slate-400 mt-1 tabular-nums">
                    {(() => {
                      const expPrice = forecast.projections[forecast.projections.length - 1].expected;
                      const diff = expPrice - data.latest_ohlcv.close;
                      const pct = (diff / data.latest_ohlcv.close) * 100;
                      return (
                        <span className={diff >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                          {diff >= 0 ? "+" : ""}{diff.toFixed(2)} ({pct >= 0 ? "+" : ""}{pct.toFixed(1)}%)
                        </span>
                      );
                    })()}
                  </div>
                </div>

                {/* 2. 80% Expected Range */}
                <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                  <span className="text-[11px] text-slate-400 block uppercase tracking-wider">80% Trajectory Band</span>
                  <div className="text-sm font-bold text-white mt-1.5 tabular-nums">
                    ₹{forecast.projections[forecast.projections.length - 1].lower_80.toFixed(0)} – ₹{forecast.projections[forecast.projections.length - 1].upper_80.toFixed(0)}
                  </div>
                  <div className="text-[10px] text-slate-500 mt-1">
                    High Probability Band
                  </div>
                </div>

                {/* 3. 95% Tail Risk Floor */}
                <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                  <span className="text-[11px] text-slate-400 block uppercase tracking-wider">95% Downside Floor</span>
                  <div className="text-xl font-black text-rose-400 mt-1 tabular-nums">
                    ₹{forecast.projections[forecast.projections.length - 1].lower_95.toFixed(2)}
                  </div>
                  <div className="text-[10px] text-rose-400/90 mt-1 tabular-nums font-semibold">
                    {(() => {
                      const floorPrice = forecast.projections[forecast.projections.length - 1].lower_95;
                      const maxDrawdownPct = ((floorPrice / data.latest_ohlcv.close) - 1.0) * 100;
                      return `${maxDrawdownPct.toFixed(1)}% Max Tail Risk`;
                    })()}
                  </div>
                </div>

                {/* 4. Model Calibration */}
                <div className="bg-[#050810]/70 p-4 rounded-xl border border-white/[0.06] font-mono">
                  <span className="text-[11px] text-slate-400 block uppercase tracking-wider">Annualized Vol</span>
                  <div className="text-xl font-black text-white mt-1 tabular-nums">
                    {(forecast.annualized_volatility * 100).toFixed(1)}%
                  </div>
                  <div className="text-[10px] text-slate-400 mt-1 tabular-nums">
                    {forecast.garch_parameters ? (
                      <span>α+β: <strong>{forecast.garch_parameters.persistence.toFixed(3)}</strong></span>
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

      {/* Milestone B9.0: Institutional Investment Decision Memo */}
      <section>
        <InvestmentMemoCard symbol={data.symbol} initialMemo={memo} />
      </section>

      {/* Core 4-Card Grid: Fundamentals & Technicals */}
      <section className="space-y-4">
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <h2 className="text-base font-bold text-white font-mono tracking-tight">
            Fundamentals & Technical Positioning
          </h2>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
          {/* Card 1: Debt-to-Equity */}
          <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider block">Debt-to-Equity (D/E)</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1.5 tabular-nums">
              {data.fundamentals.debt_to_equity !== null ? data.fundamentals.debt_to_equity.toFixed(4) : "N/A"}
            </div>
            <div className="mt-2.5 flex items-center space-x-1.5 text-[11px] font-mono">
              {data.fundamentals.debt_to_equity !== null && data.fundamentals.debt_to_equity < 0.5 ? (
                <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>&lt; 0.5 Conservative Threshold Met</span>
                </span>
              ) : (
                <span className="text-amber-400 font-semibold flex items-center space-x-1">
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Elevated Leverage Ratio</span>
                </span>
              )}
            </div>
          </div>

          {/* Card 2: Return on Equity (ROE %) */}
          <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider block">Return on Equity (ROE)</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1.5 tabular-nums">
              {data.fundamentals.roe_pct !== null ? `${data.fundamentals.roe_pct.toFixed(2)}%` : "N/A"}
            </div>
            <div className="mt-2.5 flex items-center space-x-1.5 text-[11px] font-mono">
              {data.fundamentals.roe_pct !== null && data.fundamentals.roe_pct > 15.0 ? (
                <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                  <ShieldCheck className="w-3.5 h-3.5" />
                  <span>&gt; 15% Hurdle Cleared (High Quality)</span>
                </span>
              ) : (
                <span className="text-slate-400">Sub-15% Capital Return</span>
              )}
            </div>
          </div>

          {/* Card 3: 60-Day Rolling Beta vs Nifty 50 */}
          <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider block">60D Rolling Beta (vs Nifty 50)</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1.5 tabular-nums">
              {data.technicals.beta_60d_nifty !== null ? data.technicals.beta_60d_nifty.toFixed(2) : "N/A"}
            </div>
            <div className="mt-2.5 text-[11px] font-mono text-slate-400">
              {data.technicals.beta_60d_nifty !== null && Math.abs(data.technicals.beta_60d_nifty) < 0.5
                ? "Low systematic benchmark exposure"
                : "Standard market systematic co-movement"}
            </div>
          </div>

          {/* Card 4: Distance from 200-day SMA */}
          <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider block">Distance from 200 SMA</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1.5 tabular-nums">
              {data.technicals.dist_sma200_pct !== null ? `${data.technicals.dist_sma200_pct >= 0 ? "+" : ""}${data.technicals.dist_sma200_pct.toFixed(2)}%` : "N/A"}
            </div>
            <div className="mt-2.5 flex items-center space-x-1.5 text-[11px] font-mono">
              <span className={isAboveSma200 ? "text-emerald-400 font-semibold" : "text-amber-400 font-semibold"}>
                {isAboveSma200 ? "✓ Price > 200 SMA (Structural Uptrend)" : "⚠️ Price < 200 SMA (Below Trend)"}
              </span>
            </div>
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
            <span className="text-slate-400 block text-[11px]">TTM P/E Ratio</span>
            <span className="text-slate-100 font-semibold font-mono mt-0.5 block tabular-nums">
              {data.fundamentals.ttm_pe !== null ? `${data.fundamentals.ttm_pe.toFixed(1)}x` : "—"}
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
              {data.technicals.volatility_annualized !== null ? `${(data.technicals.volatility_annualized * 100).toFixed(1)}%` : "—"}
            </span>
          </div>
        </div>
      </section>

      {/* 2-Column Responsive Grid: Corporate Disclosures (Left) + Real-Time News (Right) */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Section: Recent Corporate Filings & Disclosures Timeline */}
        <section className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-6 shadow-[0_12px_40px_rgba(0,0,0,0.6)] space-y-4">
          <div className="flex items-center justify-between pb-3.5 border-b border-white/[0.06]">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.15)]">
                <FileText className="w-4 h-4" />
              </div>
              <h2 className="text-base font-bold text-white font-mono tracking-tight">
                Corporate Disclosures &amp; Filings
              </h2>
            </div>
            <span className="text-xs text-slate-400 font-mono">Official Broadcasts</span>
          </div>

          {data.recent_disclosures.length === 0 ? (
            <p className="text-xs text-slate-500 font-mono py-6 text-center">
              No official exchange disclosures recorded in local database for {data.symbol}.
            </p>
          ) : (
            <div className="space-y-3">
              {data.recent_disclosures.map(d => {
                const isQuarantined = d.verification_status === "SYNTHETIC_SEED_QUARANTINED";
                const isVerified = d.verification_status === "VERIFIED";
                const isFlagged = d.verification_status === "SOURCE_UNVERIFIED";

                return (
                  <div
                    key={d.disclosure_id}
                    className={`border rounded-xl p-4 transition-all flex flex-col justify-between gap-3 text-xs font-mono ${
                      isQuarantined
                        ? "bg-rose-950/20 border-rose-900/60"
                        : "bg-[#050810]/70 border-white/[0.06] hover:border-white/[0.14]"
                    }`}
                  >
                    <div className="space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-bold text-slate-100 text-sm">{d.category}</span>
                        <span
                          className={`text-[10px] px-2.5 py-0.5 rounded-full font-semibold ${
                            isQuarantined
                              ? "bg-rose-950 text-rose-300 border border-rose-800"
                              : isVerified
                              ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30"
                              : isFlagged
                              ? "bg-amber-500/10 text-amber-300 border border-amber-500/30"
                              : "bg-white/[0.05] text-slate-400 border border-white/[0.08]"
                          }`}
                        >
                          {isQuarantined ? "SYNTHETIC_SEED_QUARANTINED" : d.verification_status}
                        </span>
                        {isQuarantined && (
                          <span className="text-[10px] px-2.5 py-0.5 rounded-full bg-rose-950/80 text-rose-300 border border-rose-800 font-mono">
                            ⚠ QUARANTINED
                          </span>
                        )}
                        <span className="text-slate-400 text-[11px] flex items-center space-x-1 tabular-nums">
                          <Clock className="w-3 h-3 text-slate-500" />
                          <span>{d.effective_session_date}</span>
                        </span>
                      </div>

                      <p className="text-slate-200 font-medium">{d.subject}</p>
                      {d.details_summary && (
                        <p className="text-slate-400 text-[11px] leading-relaxed line-clamp-2">{d.details_summary}</p>
                      )}
                    </div>

                    {/* Direct Document Action Link */}
                    <div>
                      {isQuarantined ? (
                        <span className="inline-flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-rose-950/50 border border-rose-900/60 text-rose-300 text-xs font-mono font-medium opacity-80 cursor-not-allowed">
                          <span>Quarantined Filing</span>
                        </span>
                      ) : d.source_url ? (
                        <a
                          href={d.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 hover:text-white transition-all text-xs font-mono font-medium shadow-[0_0_10px_rgba(6,182,212,0.15)]"
                        >
                          <span>{d.source_url.toLowerCase().endsWith(".pdf") ? "View Official PDF" : "Open Exchange Filing"}</span>
                          <ExternalLink className="w-3.5 h-3.5" />
                        </a>
                      ) : (
                        <span className="text-slate-600 text-xs italic">No Direct URL</span>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>

        {/* Section: Real-Time Equity News & Impact Analysis (Milestone B7.5) */}
        <div>
          <NewsImpactCard
            symbol={data.symbol}
            articles={newsArticles}
            loading={newsLoading}
          />
        </div>
      </div>
      </main>
    </div>
  );
}
