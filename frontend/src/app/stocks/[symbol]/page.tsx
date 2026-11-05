"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import StockChart, { CandleData, ForecastData } from "@/components/StockChart";
import NewsImpactCard, { NewsArticle } from "@/components/NewsImpactCard";
import InvestmentMemoCard, { InvestmentMemo } from "@/components/InvestmentMemoCard";
import Navbar from "@/components/Navbar";
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

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const NGROK_HEADERS = {
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

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

  const startPolling = useCallback(() => {
    if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    pollIntervalRef.current = setInterval(async () => {
      try {
        const statusRes = await fetch(`${API_BASE}/stocks/${symbol}/status`, {
          headers: NGROK_HEADERS
        });
        if (!statusRes.ok) return;
        const statusJson = await statusRes.json();
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
      } catch (e) {
        console.error("Polling error:", e);
      }
    }, 1500);
  }, [symbol]);

  const fetchTearsheet = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/stocks/${symbol}/tearsheet`, {
        headers: NGROK_HEADERS
      });
      if (res.status === 202) {
        const json = await res.json();
        setIngestion({
          isIngesting: true,
          progressPct: json.progress_pct || 25,
          step: json.step || "QUEUED",
          detail: json.message || "Discovered unseeded ticker. Ingesting 24-month historical series, fundamentals, and factors..."
        });
        setLoading(false);
        startPolling();
        return;
      }

      if (res.status === 404) {
        setNotFound(true);
        setLoading(false);
        return;
      }

      if (!res.ok) {
        throw new Error(`Failed to load tearsheet (HTTP ${res.status})`);
      }

      const json = await res.json();
      setData(json);

      // Fetch Walk-Forward Econometric Forecast (Milestone B7.0)
      try {
        const fRes = await fetch(`${API_BASE}/stocks/${symbol}/forecast?horizon_days=20`, {
          headers: NGROK_HEADERS
        });
        if (fRes.ok) {
          const fJson = await fRes.json();
          setForecast(fJson);
        }
      } catch (fErr) {
        console.warn("Forecast fetch warning:", fErr);
      }

      // Fetch Real-Time News & Directional Impact (Milestone B7.5)
      try {
        setNewsLoading(true);
        const nRes = await fetch(`${API_BASE}/stocks/${symbol}/news?limit=5`, {
          headers: NGROK_HEADERS
        });
        if (nRes.ok) {
          const nJson = await nRes.json();
          setNewsArticles(nJson.articles || []);
        }
      } catch (nErr) {
        console.warn("News fetch warning:", nErr);
      } finally {
        setNewsLoading(false);
      }

      // Fetch Institutional Investment Decision Memo (Milestone B9.0)
      try {
        const mRes = await fetch(`${API_BASE}/stocks/${symbol}/memo`, {
          headers: NGROK_HEADERS
        });
        if (mRes.ok) {
          const mJson = await mRes.json();
          setMemo(mJson);
        }
      } catch (mErr) {
        console.warn("Memo fetch warning:", mErr);
      }

      setIngestion({ isIngesting: false, progressPct: 100, step: "READY", detail: "Ready" });
      setNotFound(false);
      setError(null);
    } catch (err: unknown) {
      console.error("Tearsheet fetch error:", err);
      const msg = err instanceof Error ? err.message : "Failed to load stock data";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [symbol, startPolling]);

  useEffect(() => {
    fetchTearsheetRef.current = fetchTearsheet;
  }, [fetchTearsheet]);

  useEffect(() => {
    if (!symbol) return;
    setLoading(true);
    fetchTearsheet();

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
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
      <div className="min-h-screen bg-[#030508] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
        <Navbar />
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex items-center justify-center">
          <div className="max-w-2xl w-full p-8 rounded-2xl bg-slate-900/90 border border-slate-800 shadow-2xl space-y-8 backdrop-blur-xl">
            <div className="text-center space-y-2">
              <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full bg-cyan-950/70 border border-cyan-700/60 text-cyan-400 text-xs font-mono">
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
                <span className="text-cyan-400 font-bold">{ingestion.progressPct}%</span>
              </div>
              <div className="w-full h-2.5 bg-slate-950 rounded-full overflow-hidden p-0.5 border border-slate-800">
                <div
                  className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 rounded-full transition-all duration-500 ease-out shadow-lg shadow-cyan-500/50"
                  style={{ width: `${Math.max(5, ingestion.progressPct)}%` }}
                />
              </div>
            </div>

            {/* Checklist */}
            <div className="space-y-3.5 bg-slate-950/60 p-5 rounded-xl border border-slate-800/80 font-mono text-xs">
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
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex items-center justify-center">
          <div className="p-8 rounded-2xl bg-slate-900/90 border border-rose-900/40 text-center space-y-4 max-w-lg w-full shadow-2xl backdrop-blur-md">
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
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6 pb-24 animate-pulse">
          <div className="h-8 w-48 bg-slate-900 rounded" />
          <div className="h-28 bg-slate-900/80 rounded-xl" />
          <div className="h-96 bg-slate-900/80 rounded-xl" />
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
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
        <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-10 flex items-center justify-center">
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
    <div className="min-h-screen bg-[#030508] text-slate-100 flex flex-col font-sans selection:bg-cyan-500/20 selection:text-cyan-300">
      <Navbar />
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6 pb-24">
        {/* Back Link & Navigation Bar */}
        <div className="flex items-center justify-between">
          <Link
            href="/"
            className="inline-flex items-center space-x-1.5 text-xs font-mono text-slate-400 hover:text-white transition-colors group"
          >
            <ArrowLeft className="w-4 h-4 text-cyan-400 group-hover:-translate-x-1 transition-transform" />
            <span>Back to Terminal Dashboard</span>
          </Link>

          <span className="text-xs text-slate-400 font-mono">
            Settled Session: <strong className="text-slate-200">{data.as_of_date}</strong>
          </span>
        </div>

      {/* Hero Header Card */}
      <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-3xl font-extrabold text-white font-mono tracking-tight">
                {data.symbol}
              </h1>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300 font-mono">
                {data.isin}
              </span>
              <span className="text-xs px-2.5 py-0.5 rounded-full bg-cyan-950 border border-cyan-800/80 text-cyan-300 font-semibold">
                {data.sector}
              </span>
              {data.is_watchlist ? (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-950 border border-indigo-700 text-indigo-300 font-semibold flex items-center space-x-1">
                  <Sparkles className="w-3 h-3 text-indigo-400" />
                  <span>WATCHLIST HOLDING</span>
                </span>
              ) : (
                <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
                  NIFTY 50 CONSTITUENT
                </span>
              )}
            </div>

            <p className="text-sm text-slate-300 mt-1 font-medium">{data.company_name}</p>
            {data.notes && (
              <p className="text-xs text-slate-400 mt-1 italic font-mono max-w-2xl">
                Strategy Notes: &ldquo;{data.notes}&rdquo;
              </p>
            )}
          </div>

          {/* Right Price & Return Stack */}
          <div className="flex items-center space-x-6 md:text-right">
            <div>
              <span className="text-xs text-slate-500 font-mono block">Latest Close</span>
              <div className="text-3xl font-extrabold text-white font-mono tracking-tight">
                ₹{data.latest_ohlcv.close.toFixed(2)}
              </div>
            </div>

            <div
              className={`flex flex-col items-center justify-center px-3 py-1.5 rounded-lg border font-mono ${
                isUp
                  ? "bg-emerald-950/70 border-emerald-800/80 text-emerald-300"
                  : "bg-red-950/70 border-red-800/80 text-red-300"
              }`}
            >
              <div className="flex items-center space-x-1 text-sm font-bold">
                {isUp ? <TrendingUp className="w-4 h-4" /> : <TrendingDown className="w-4 h-4" />}
                <span>{data.technicals.ret_1d_pct >= 0 ? "+" : ""}{data.technicals.ret_1d_pct.toFixed(2)}%</span>
              </div>
              <span className="text-[10px] text-slate-400 uppercase tracking-wider">1D Change</span>
            </div>
          </div>
        </div>

        {/* Watchlist Target Price / Stop Loss Ribbon */}
        {(data.target_price || data.stop_loss) && (
          <div className="mt-4 pt-3 border-t border-slate-800/80 flex flex-wrap items-center gap-4 text-xs font-mono">
            {data.target_price && (
              <span className="flex items-center space-x-1.5 px-3 py-1 rounded-md bg-emerald-950/40 border border-emerald-900 text-emerald-400">
                <Target className="w-3.5 h-3.5" />
                <span>Target Objective: <strong>₹{data.target_price.toFixed(2)}</strong> ({(((data.target_price / data.latest_ohlcv.close) - 1.0) * 100).toFixed(1)}% upside)</span>
              </span>
            )}
            {data.stop_loss && (
              <span className="flex items-center space-x-1.5 px-3 py-1 rounded-md bg-red-950/40 border border-red-900 text-red-400">
                <ShieldAlert className="w-3.5 h-3.5" />
                <span>Downside Stop: <strong>₹{data.stop_loss.toFixed(2)}</strong> ({(((data.stop_loss / data.latest_ohlcv.close) - 1.0) * 100).toFixed(1)}% risk)</span>
              </span>
            )}
          </div>
        )}
      </div>

      {/* Milestone B9.0: Institutional Investment Decision Memo */}
      <section>
        <InvestmentMemoCard symbol={data.symbol} initialMemo={memo} />
      </section>

      {/* Embed TradingView HTML5 Lightweight-Charts Candlestick Component */}
      <section>
        <StockChart
          symbol={data.symbol}
          data={data.history}
          sma200={data.technicals.sma_200}
          forecast={forecast}
        />
      </section>

      {/* Milestone B7.0: 20-Day Econometric Forecast & Tail Risk Card */}
      {forecast && forecast.projections && forecast.projections.length > 0 && (
        <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 rounded-lg bg-cyan-950/70 border border-cyan-800/80 text-cyan-400">
                <Activity className="w-4 h-4" />
              </div>
              <div>
                <h3 className="text-base font-bold text-white font-mono tracking-tight">
                  20-Day Econometric Forecast &amp; Tail Risk
                </h3>
                <p className="text-[11px] text-slate-400 font-mono">
                  GARCH(1,1) Conditional Volatility &middot; Ornstein-Uhlenbeck Mean-Reverting Drift
                </p>
              </div>
            </div>

            <div className="flex items-center space-x-2">
              <span className="text-xs font-mono text-slate-400">Regime:</span>
              <span
                className={`text-xs px-2.5 py-0.5 rounded-full font-mono font-semibold border ${
                  forecast.volatility_regime === "LOW"
                    ? "bg-emerald-950/70 text-emerald-400 border-emerald-800/80"
                    : forecast.volatility_regime === "NORMAL"
                    ? "bg-cyan-950/70 text-cyan-400 border-cyan-800/80"
                    : "bg-amber-950/70 text-amber-400 border-amber-800/80"
                }`}
              >
                {forecast.volatility_regime} DISPERSION
              </span>
            </div>
          </div>

          {/* Forecast Telemetry Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 mt-4">
            {/* 1. Expected 20D Price */}
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 font-mono">
              <span className="text-xs text-slate-400 block">Expected 20D Price</span>
              <div className="text-2xl font-black text-cyan-300 mt-1">
                ₹{forecast.projections[forecast.projections.length - 1].expected.toFixed(2)}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                {(() => {
                  const expPrice = forecast.projections[forecast.projections.length - 1].expected;
                  const diff = expPrice - data.latest_ohlcv.close;
                  const pct = (diff / data.latest_ohlcv.close) * 100;
                  return (
                    <span className={diff >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                      {diff >= 0 ? "+" : ""}{diff.toFixed(2)} ({pct >= 0 ? "+" : ""}{pct.toFixed(2)}%)
                    </span>
                  );
                })()}
                <span className="text-slate-500 ml-1">expected return</span>
              </div>
            </div>

            {/* 2. 80% Expected Range */}
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 font-mono">
              <span className="text-xs text-slate-400 block">80% Expected Range</span>
              <div className="text-lg font-bold text-white mt-1">
                ₹{forecast.projections[forecast.projections.length - 1].lower_80.toFixed(2)} – ₹{forecast.projections[forecast.projections.length - 1].upper_80.toFixed(2)}
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                High Probability Trajectory Envelope
              </div>
            </div>

            {/* 3. 95% Tail Risk Floor */}
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 font-mono">
              <span className="text-xs text-slate-400 block">95% Tail Risk Floor</span>
              <div className="text-2xl font-black text-rose-400 mt-1">
                ₹{forecast.projections[forecast.projections.length - 1].lower_95.toFixed(2)}
              </div>
              <div className="text-[11px] text-rose-400/90 mt-1">
                {(() => {
                  const floorPrice = forecast.projections[forecast.projections.length - 1].lower_95;
                  const maxDrawdownPct = ((floorPrice / data.latest_ohlcv.close) - 1.0) * 100;
                  return `${maxDrawdownPct.toFixed(1)}% Max Modeled Drawdown`;
                })()}
              </div>
            </div>

            {/* 4. Model Calibration Telemetry */}
            <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80 font-mono">
              <span className="text-xs text-slate-400 block">Annualized Volatility</span>
              <div className="text-2xl font-black text-white mt-1">
                {(forecast.annualized_volatility * 100).toFixed(2)}%
              </div>
              <div className="text-[11px] text-slate-400 mt-1">
                {forecast.garch_parameters ? (
                  <span>
                    Persistence (α+β): <strong className="text-slate-200">{forecast.garch_parameters.persistence.toFixed(3)}</strong>
                  </span>
                ) : (
                  <span>Walk-Forward Risk Calibrated</span>
                )}
              </div>
            </div>
          </div>
        </section>
      )}

      {/* Core 4-Card Grid: Fundamentals & Technicals */}
      <section className="space-y-3">
        <div className="flex items-center space-x-2">
          <Activity className="w-4 h-4 text-cyan-400" />
          <h2 className="text-base font-bold text-slate-100 font-mono tracking-tight">
            Fundamentals & Technical Positioning
          </h2>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Card 1: Debt-to-Equity */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg">
            <span className="text-xs font-mono text-slate-400 block">Debt-to-Equity (D/E)</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1">
              {data.fundamentals.debt_to_equity !== null ? data.fundamentals.debt_to_equity.toFixed(4) : "N/A"}
            </div>
            <div className="mt-2 flex items-center space-x-1 text-[11px] font-mono">
              {data.fundamentals.debt_to_equity !== null && data.fundamentals.debt_to_equity < 0.5 ? (
                <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                  <ShieldCheck className="w-3 h-3" />
                  <span>&lt; 0.5 Conservative Threshold Met</span>
                </span>
              ) : (
                <span className="text-amber-400 font-semibold flex items-center space-x-1">
                  <AlertTriangle className="w-3 h-3" />
                  <span>Elevated Leverage Ratio</span>
                </span>
              )}
            </div>
          </div>

          {/* Card 2: Return on Equity (ROE %) */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg">
            <span className="text-xs font-mono text-slate-400 block">Return on Equity (ROE)</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1">
              {data.fundamentals.roe_pct !== null ? `${data.fundamentals.roe_pct.toFixed(2)}%` : "N/A"}
            </div>
            <div className="mt-2 flex items-center space-x-1 text-[11px] font-mono">
              {data.fundamentals.roe_pct !== null && data.fundamentals.roe_pct > 15.0 ? (
                <span className="text-emerald-400 font-semibold flex items-center space-x-1">
                  <ShieldCheck className="w-3 h-3" />
                  <span>&gt; 15% Hurdle Cleared (High Quality)</span>
                </span>
              ) : (
                <span className="text-slate-400">Sub-15% Capital Return</span>
              )}
            </div>
          </div>

          {/* Card 3: 60-Day Rolling Beta vs Nifty 50 */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg">
            <span className="text-xs font-mono text-slate-400 block">60D Rolling Beta (vs Nifty 50)</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1">
              {data.technicals.beta_60d_nifty !== null ? data.technicals.beta_60d_nifty.toFixed(2) : "N/A"}
            </div>
            <div className="mt-2 text-[11px] font-mono text-slate-400">
              {data.technicals.beta_60d_nifty !== null && Math.abs(data.technicals.beta_60d_nifty) < 0.5
                ? "Low systematic benchmark exposure"
                : "Standard market systematic co-movement"}
            </div>
          </div>

          {/* Card 4: Distance from 200-day SMA */}
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-4 shadow-lg">
            <span className="text-xs font-mono text-slate-400 block">Distance from 200 SMA</span>
            <div className="text-2xl font-extrabold font-mono text-white mt-1">
              {data.technicals.dist_sma200_pct !== null ? `${data.technicals.dist_sma200_pct >= 0 ? "+" : ""}${data.technicals.dist_sma200_pct.toFixed(2)}%` : "N/A"}
            </div>
            <div className="mt-2 flex items-center space-x-1 text-[11px] font-mono">
              <span className={isAboveSma200 ? "text-emerald-400 font-semibold" : "text-amber-400 font-semibold"}>
                {isAboveSma200 ? "✓ Price > 200 SMA (Structural Uptrend)" : "⚠️ Price < 200 SMA (Below Trend)"}
              </span>
            </div>
          </div>
        </div>

        {/* Supplementary Metrics Ribbon */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-3 pt-2 text-xs font-mono">
          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block">20-Day SMA</span>
            <span className="text-slate-200 font-semibold font-mono">
              {data.technicals.sma_20 !== null ? `₹${data.technicals.sma_20.toFixed(2)}` : "—"}
            </span>
          </div>

          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block">50-Day SMA</span>
            <span className="text-slate-200 font-semibold font-mono">
              {data.technicals.sma_50 !== null ? `₹${data.technicals.sma_50.toFixed(2)}` : "—"}
            </span>
          </div>

          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block">200-Day SMA</span>
            <span className="text-slate-200 font-semibold font-mono">
              {data.technicals.sma_200 !== null ? `₹${data.technicals.sma_200.toFixed(2)}` : "—"}
            </span>
          </div>

          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block">TTM P/E Ratio</span>
            <span className="text-slate-200 font-semibold font-mono">
              {data.fundamentals.ttm_pe !== null ? `${data.fundamentals.ttm_pe.toFixed(1)}x` : "—"}
            </span>
          </div>

          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block">Operating Margin</span>
            <span className="text-slate-200 font-semibold font-mono">
              {data.fundamentals.opm_pct !== null ? `${data.fundamentals.opm_pct.toFixed(1)}%` : "—"}
            </span>
          </div>

          <div className="bg-slate-950 p-2.5 rounded-lg border border-slate-800/80">
            <span className="text-slate-500 block">20D Volatility</span>
            <span className="text-slate-200 font-semibold font-mono">
              {data.technicals.volatility_annualized !== null ? `${(data.technicals.volatility_annualized * 100).toFixed(1)}%` : "—"}
            </span>
          </div>
        </div>
      </section>

      {/* Section: Real-Time Equity News & Impact Analysis (Milestone B7.5) */}
      <NewsImpactCard
        symbol={data.symbol}
        articles={newsArticles}
        loading={newsLoading}
      />

      {/* Section: Recent Corporate Filings & Disclosures Timeline */}
      <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <FileText className="w-4 h-4 text-cyan-400" />
            <h2 className="text-base font-bold text-slate-100 font-mono tracking-tight">
              Recent Corporate Disclosures & Regulatory Filings
            </h2>
          </div>
          <span className="text-xs text-slate-400 font-mono">Official Exchange Broadcasts</span>
        </div>

        {data.recent_disclosures.length === 0 ? (
          <p className="text-xs text-slate-500 font-mono py-4 text-center">
            No official exchange disclosures recorded in local database for {data.symbol}.
          </p>
        ) : (
          <div className="space-y-3">
            {data.recent_disclosures.map(d => {
              const isVerified = d.verification_status === "VERIFIED";
              const isFlagged = d.verification_status === "SOURCE_UNVERIFIED";

              return (
                <div
                  key={d.disclosure_id}
                  className="bg-slate-950/80 border border-slate-800/80 hover:border-slate-700 rounded-lg p-4 transition-colors flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs font-mono"
                >
                  <div className="space-y-1 max-w-3xl">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-slate-200 text-sm">{d.category}</span>
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                          isVerified
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                            : isFlagged
                            ? "bg-amber-950 text-amber-300 border border-amber-800"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {d.verification_status}
                      </span>
                      {d.audit_status && (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-300">
                          {d.audit_status}
                        </span>
                      )}
                      <span className="text-slate-500 text-[11px] flex items-center space-x-1">
                        <Clock className="w-3 h-3" />
                        <span>Effective: {d.effective_session_date}</span>
                      </span>
                    </div>

                    <p className="text-slate-300 font-medium">{d.subject}</p>
                    {d.details_summary && (
                      <p className="text-slate-400 text-[11px] leading-relaxed">{d.details_summary}</p>
                    )}
                  </div>

                  {/* Direct Document Action Link */}
                  {d.source_url ? (
                    <a
                      href={d.source_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center space-x-1.5 px-3 py-1.5 rounded-md bg-cyan-950 hover:bg-cyan-900 border border-cyan-800 text-cyan-300 hover:text-white transition-colors shrink-0 text-xs font-mono font-medium"
                    >
                      <span>{d.source_url.toLowerCase().endsWith(".pdf") ? "View Official PDF" : "Open Exchange Filing"}</span>
                      <ExternalLink className="w-3 h-3" />
                    </a>
                  ) : (
                    <span className="text-slate-600 text-xs italic shrink-0">No Direct URL</span>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </section>
      </main>
    </div>
  );
}
