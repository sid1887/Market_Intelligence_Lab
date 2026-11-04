"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import StockChart, { CandleData } from "@/components/StockChart";
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
  Activity
} from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;

    const fetchTearsheet = async () => {
      setLoading(true);
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/stocks/${symbol}/tearsheet`);
        if (!res.ok) {
          throw new Error(`Failed to fetch tearsheet for ${symbol} (status ${res.status})`);
        }
        const json = await res.json();
        setData(json);
      } catch (err: unknown) {
        console.error("Tearsheet fetch error:", err);
        const msg = err instanceof Error ? err.message : "Failed to load stock data";
        setError(msg);
      } finally {
        setLoading(false);
      }
    };

    fetchTearsheet();
  }, [symbol]);

  if (loading) {
    return (
      <div className="space-y-6 animate-pulse">
        <div className="h-8 w-48 bg-slate-900 rounded" />
        <div className="h-28 bg-slate-900/80 rounded-xl" />
        <div className="h-96 bg-slate-900/80 rounded-xl" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-32 bg-slate-900/80 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-8 rounded-xl bg-slate-900/80 border border-slate-800 text-center space-y-4 max-w-xl mx-auto my-12">
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
    );
  }

  const isUp = data.technicals.ret_1d >= 0;
  const isAboveSma200 = data.technicals.price_above_sma200;

  return (
    <div className="space-y-6">
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

      {/* Embed TradingView HTML5 Lightweight-Charts Candlestick Component */}
      <section>
        <StockChart
          symbol={data.symbol}
          data={data.history}
          sma200={data.technicals.sma_200}
        />
      </section>

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
    </div>
  );
}
