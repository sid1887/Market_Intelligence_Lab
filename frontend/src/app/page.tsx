"use client";

import React, { useEffect, useState } from "react";
import WatchlistPanel, { WatchlistItem } from "@/components/WatchlistPanel";
import ScreenerTable, { ScreenerCandidate } from "@/components/ScreenerTable";
import { RefreshCw, AlertCircle } from "lucide-react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

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
      const wlRes = await fetch(`${API_BASE}/watchlist`);
      if (!wlRes.ok) throw new Error(`Watchlist API returned ${wlRes.status}`);
      const wlData = await wlRes.json();
      setWatchlist(wlData.watchlist || []);

      // 2. Fetch Screener
      const scrRes = await fetch(`${API_BASE}/screener?limit=54`);
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
    <div className="space-y-8">
      {/* Top Banner / Pulse */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-5 rounded-xl bg-gradient-to-r from-slate-900 via-slate-900 to-slate-950 border border-slate-800 shadow-xl">
        <div className="space-y-1">
          <div className="flex items-center space-x-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
            <span className="text-xs font-mono uppercase tracking-wider text-cyan-400 font-bold">
              Active Session Settled: {asOfDate}
            </span>
          </div>
          <h1 className="text-2xl font-extrabold text-white tracking-tight">
            Market Intelligence & Quantitative Terminal
          </h1>
          <p className="text-xs text-slate-400 max-w-2xl">
            Live local-first SQLite research bridge. Tracking the authoritative 50-stock NIFTY 50 universe
            and high-conviction user trading watchlists without predictive ML hallucinations.
          </p>
        </div>

        <div className="flex items-center space-x-3">
          <button
            onClick={fetchData}
            disabled={loading}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-mono transition-colors border border-slate-700 disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Error Notice */}
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

      {/* Section 1: Watchlist Panel */}
      <section>
        <WatchlistPanel items={watchlist} loading={loading} />
      </section>

      {/* Section 2: Top Screener Results Table */}
      <section>
        <ScreenerTable candidates={candidates} asOfDate={asOfDate} loading={loading} />
      </section>
    </div>
  );
}
