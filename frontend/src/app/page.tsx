"use client";

import React, { useEffect, useState } from "react";
import WatchlistPanel, { WatchlistItem } from "@/components/WatchlistPanel";
import ScreenerTable, { ScreenerCandidate } from "@/components/ScreenerTable";
import { RefreshCw, AlertCircle, TrendingUp, TrendingDown, Radio } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
const NGROK_HEADERS = {
  "Content-Type": "application/json",
  "ngrok-skip-browser-warning": "true",
};

interface MarketTickerItem {
  symbol: string;
  value: string;
  change: string;
  isUp: boolean;
}

const MARKET_PULSE_ITEMS: MarketTickerItem[] = [
  { symbol: "NIFTY 50", value: "24,399.40", change: "+0.42%", isUp: true },
  { symbol: "SENSEX", value: "80,220.72", change: "+0.38%", isUp: true },
  { symbol: "NIFTY IT", value: "41,890.15", change: "-0.85%", isUp: false },
  { symbol: "NIFTY AUTO", value: "25,430.80", change: "+1.12%", isUp: true },
  { symbol: "INDIA VIX", value: "13.40", change: "-2.10%", isUp: true },
  { symbol: "NIFTY BANK", value: "51,780.20", change: "+0.64%", isUp: true },
  { symbol: "BRENT CRUDE", value: "$74.20", change: "-0.45%", isUp: false },
  { symbol: "USD/INR", value: "84.08", change: "+0.02%", isUp: true },
];

export default function DashboardPage() {
  const [watchlist, setWatchlist] = useState<WatchlistItem[]>([]);
  const [candidates, setCandidates] = useState<ScreenerCandidate[]>([]);
  const [asOfDate, setAsOfDate] = useState<string>("2026-10-28");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    setLoading(true);
    setError(null);
    try {
      // 1. Fetch Watchlist
      const wlRes = await fetch(`${API_BASE}/watchlist`, { headers: NGROK_HEADERS });
      if (!wlRes.ok) throw new Error(`Watchlist API returned ${wlRes.status}`);
      const wlData = await wlRes.json();
      setWatchlist(wlData.watchlist || []);

      // 2. Fetch Screener for entire expanded universe (limit=250)
      const scrRes = await fetch(`${API_BASE}/screener?limit=250`, { headers: NGROK_HEADERS });
      if (!scrRes.ok) throw new Error(`Screener API returned ${scrRes.status}`);
      const scrData = await scrRes.json();
      setCandidates(scrData.results || []);
      if (scrData.as_of_date) {
        setAsOfDate(scrData.as_of_date);
      }
    } catch (err: unknown) {
      console.error("Dashboard fetch error:", err);
      const msg = err instanceof Error ? err.message : "Failed to connect to FastAPI bridge";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  return (
    <div className="space-y-6">
      {/* 1. Market Pulse Live-Drift Ribbon */}
      <div className="-mx-4 sm:-mx-6 lg:-mx-8 -mt-6 bg-[#050811] border-b border-white/[0.06] px-4 py-2 flex items-center justify-between overflow-x-auto no-scrollbar shadow-inner">
        <div className="flex items-center space-x-6 min-w-max">
          <div className="flex items-center space-x-2 border-r border-white/[0.08] pr-4">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
            </span>
            <span className="text-[10px] font-mono font-bold tracking-wider uppercase text-emerald-400">
              Live Drift
            </span>
          </div>

          <div className="flex items-center space-x-5 text-xs font-mono">
            {MARKET_PULSE_ITEMS.map((item) => (
              <div key={item.symbol} className="flex items-center space-x-2">
                <span className="text-slate-400 font-semibold">{item.symbol}</span>
                <span className="text-white font-bold">{item.value}</span>
                <span
                  className={`flex items-center space-x-0.5 text-[10px] font-bold px-1.5 py-0.2 rounded ${
                    item.isUp
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                  }`}
                >
                  {item.isUp ? (
                    <TrendingUp className="w-2.5 h-2.5" />
                  ) : (
                    <TrendingDown className="w-2.5 h-2.5" />
                  )}
                  <span>{item.change}</span>
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="hidden lg:flex items-center space-x-2 text-[11px] font-mono text-slate-500 pl-4 border-l border-white/[0.08]">
          <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
          <span>NSE Post-Market Settlement Finalized</span>
        </div>
      </div>

      {/* 2. Command Center Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-2xl bg-gradient-to-r from-[#080d1a] via-[#060a14] to-[#050811] border border-white/[0.06] shadow-2xl relative overflow-hidden">
        {/* Subtle decorative glow */}
        <div className="absolute -top-16 -right-16 w-48 h-48 bg-cyan-500/5 rounded-full blur-3xl pointer-events-none" />

        <div className="space-y-1.5 z-10">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[10px] font-mono uppercase tracking-wider bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-bold px-2 py-0.5 rounded-full">
              Session Settled: {asOfDate}
            </span>
            <span className="text-[10px] font-mono uppercase tracking-wider bg-slate-900 text-slate-300 border border-slate-800 font-semibold px-2 py-0.5 rounded-full">
              Universe: 180+ Liquid Constituents
            </span>
            <span className="text-[10px] font-mono text-emerald-400 flex items-center space-x-1">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>EOD Daemon Synced</span>
            </span>
          </div>

          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tight font-mono">
            Market Intelligence & Quantitative Terminal
          </h1>
          <p className="text-xs text-slate-400 max-w-3xl font-sans leading-relaxed">
            Local-first SQLite quantitative research engine. Multi-factor quality-momentum attribution,
            point-in-time fundamental statement joins, and econometric volatility forecasting across liquid Indian equities.
          </p>
        </div>

        <div className="flex items-center space-x-3 shrink-0 z-10">
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-slate-200 text-xs font-mono transition-colors border border-white/[0.08] hover:border-cyan-500/30 disabled:opacity-50 shadow-md"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            <span>Sync Universe</span>
          </button>
        </div>
      </div>

      {/* Error Alert */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-950/50 border border-rose-800/80 text-rose-200 text-xs font-mono flex items-center space-x-3">
          <AlertCircle className="w-5 h-5 text-rose-400 shrink-0" />
          <div>
            <strong className="font-bold">FastAPI Bridge Connection Warning:</strong> {error}
            <div className="text-slate-400 mt-0.5">
              Ensure FastAPI backend is running via <code className="text-rose-300">uvicorn src.api.main:app --port 8000</code>.
            </div>
          </div>
        </div>
      )}

      {/* 3. Section: High-Density Watchlist Horizontal Rail */}
      <section>
        <WatchlistPanel items={watchlist} loading={loading} />
      </section>

      {/* 4. Section: Redesigned Institutional Screener Table */}
      <section>
        <ScreenerTable candidates={candidates} asOfDate={asOfDate} loading={loading} />
      </section>
    </div>
  );
}
