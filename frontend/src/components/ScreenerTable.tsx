"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { Search, ChevronRight, SlidersHorizontal } from "lucide-react";

export interface ScreenerCandidate {
  rank: number;
  symbol: string;
  company_name: string;
  sector: string;
  close: number | null;
  sma_200: number | null;
  debt_to_equity: number | null;
  roe_pct: number | null;
  opm_pct: number | null;
  excess_ret_20d: number | null;
  composite_score: number | null;
  price_above_sma200: boolean;
  is_watchlist: boolean;
}

interface ScreenerTableProps {
  candidates: ScreenerCandidate[];
  asOfDate?: string;
  loading?: boolean;
}

export default function ScreenerTable({ candidates, asOfDate, loading }: ScreenerTableProps) {
  const [search, setSearch] = useState("");
  const [minRoe, setMinRoe] = useState<number>(0);
  const [maxDe, setMaxDe] = useState<number>(999);
  const [onlyAbove200Sma, setOnlyAbove200Sma] = useState<boolean>(false);
  const [excludeFinancials, setExcludeFinancials] = useState<boolean>(false);
  const [onlyWatchlist, setOnlyWatchlist] = useState<boolean>(false);

  // Filter logic
  const filteredCandidates = useMemo(() => {
    return candidates.filter(item => {
      // Search filter
      if (search) {
        const q = search.toLowerCase();
        const matchesSym = item.symbol.toLowerCase().includes(q);
        const matchesName = item.company_name.toLowerCase().includes(q);
        const matchesSec = item.sector.toLowerCase().includes(q);
        if (!matchesSym && !matchesName && !matchesSec) return false;
      }

      // ROE filter
      if (minRoe > 0 && (item.roe_pct === null || item.roe_pct < minRoe)) {
        return false;
      }

      // D/E filter
      if (maxDe < 999 && (item.debt_to_equity === null || item.debt_to_equity > maxDe)) {
        return false;
      }

      // SMA 200 filter
      if (onlyAbove200Sma && !item.price_above_sma200) {
        return false;
      }

      // Exclude Financials
      if (excludeFinancials && item.sector.toLowerCase().includes("financial")) {
        return false;
      }

      // Watchlist filter
      if (onlyWatchlist && !item.is_watchlist) {
        return false;
      }

      return true;
    });
  }, [candidates, search, minRoe, maxDe, onlyAbove200Sma, excludeFinancials, onlyWatchlist]);

  return (
    <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl backdrop-blur-sm space-y-4">
      {/* Header & Controls */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <div className="flex items-center space-x-2.5">
            <h2 className="text-lg font-bold text-slate-100 tracking-tight">Top Screener Results</h2>
            <span className="text-xs px-2.5 py-0.5 rounded-full bg-indigo-950 border border-indigo-800/60 text-indigo-400 font-mono">
              Composite Quality-Momentum
            </span>
            {asOfDate && (
              <span className="text-xs text-slate-400 font-mono hidden sm:inline">
                Session: {asOfDate}
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Ranked percentile aggregation across ROE % (30%), Low D/E (25%), 20-Day Excess Return (25%), and OPM % (20%).
          </p>
        </div>

        {/* Search Input */}
        <div className="relative w-full lg:w-72">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Filter symbol, name, or sector..."
            className="w-full bg-slate-950 border border-slate-800 rounded-lg pl-9 pr-4 py-1.5 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
          />
        </div>
      </div>

      {/* Filter Quick Pills */}
      <div className="flex flex-wrap items-center gap-2 pt-1 text-xs font-mono">
        <span className="text-slate-400 flex items-center space-x-1 mr-1">
          <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
          <span>Filters:</span>
        </span>

        {/* Milestone B4.2 Preset Button */}
        <button
          onClick={() => {
            setMinRoe(15.0);
            setMaxDe(0.5);
            setOnlyAbove200Sma(true);
            setExcludeFinancials(true);
            setOnlyWatchlist(false);
          }}
          className={`px-2.5 py-1 rounded-md border text-xs transition-colors ${
            minRoe === 15.0 && maxDe === 0.5 && onlyAbove200Sma && excludeFinancials
              ? "bg-cyan-950 border-cyan-500 text-cyan-300 font-semibold"
              : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200 hover:border-slate-700"
          }`}
        >
          ⚡ Milestone B4.2 Strict Screen
        </button>

        <button
          onClick={() => setOnlyAbove200Sma(!onlyAbove200Sma)}
          className={`px-2.5 py-1 rounded-md border text-xs transition-colors ${
            onlyAbove200Sma
              ? "bg-emerald-950 border-emerald-500 text-emerald-300 font-semibold"
              : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          {onlyAbove200Sma ? "✓ Price > 200 SMA" : "Price > 200 SMA"}
        </button>

        <button
          onClick={() => setExcludeFinancials(!excludeFinancials)}
          className={`px-2.5 py-1 rounded-md border text-xs transition-colors ${
            excludeFinancials
              ? "bg-amber-950 border-amber-500 text-amber-300 font-semibold"
              : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          {excludeFinancials ? "✓ Excl. Financials" : "Excl. Financials"}
        </button>

        <button
          onClick={() => setMinRoe(minRoe === 15.0 ? 0 : 15.0)}
          className={`px-2.5 py-1 rounded-md border text-xs transition-colors ${
            minRoe === 15.0
              ? "bg-indigo-950 border-indigo-500 text-indigo-300 font-semibold"
              : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          {minRoe === 15.0 ? "✓ ROE > 15%" : "ROE > 15%"}
        </button>

        <button
          onClick={() => setMaxDe(maxDe === 0.5 ? 999 : 0.5)}
          className={`px-2.5 py-1 rounded-md border text-xs transition-colors ${
            maxDe === 0.5
              ? "bg-purple-950 border-purple-500 text-purple-300 font-semibold"
              : "bg-slate-950 border-slate-800 text-slate-400 hover:text-slate-200"
          }`}
        >
          {maxDe === 0.5 ? "✓ D/E < 0.5" : "D/E < 0.5"}
        </button>

        {(minRoe > 0 || maxDe < 999 || onlyAbove200Sma || excludeFinancials || onlyWatchlist || search) && (
          <button
            onClick={() => {
              setMinRoe(0);
              setMaxDe(999);
              setOnlyAbove200Sma(false);
              setExcludeFinancials(false);
              setOnlyWatchlist(false);
              setSearch("");
            }}
            className="px-2 py-1 text-xs text-rose-400 hover:text-rose-300 underline underline-offset-2 ml-auto"
          >
            Reset Filters
          </button>
        )}
      </div>

      {/* Candidates Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-xs font-mono">
          <thead className="bg-slate-950 text-slate-400 uppercase text-[11px] tracking-wider border-b border-slate-800">
            <tr>
              <th scope="col" className="py-3 px-3 w-12 text-center">#</th>
              <th scope="col" className="py-3 px-4">Symbol / Name</th>
              <th scope="col" className="py-3 px-3">Sector</th>
              <th scope="col" className="py-3 px-3 text-right">Close (₹)</th>
              <th scope="col" className="py-3 px-3 text-right">200 SMA</th>
              <th scope="col" className="py-3 px-3 text-right">D/E</th>
              <th scope="col" className="py-3 px-3 text-right">ROE %</th>
              <th scope="col" className="py-3 px-3 text-right">OPM %</th>
              <th scope="col" className="py-3 px-3 text-right">Excess (20D)</th>
              <th scope="col" className="py-3 px-4 text-center">Score</th>
              <th scope="col" className="py-3 px-3 text-center">Type</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 bg-slate-950/40">
            {loading ? (
              [1, 2, 3, 4, 5].map(i => (
                <tr key={i} className="animate-pulse">
                  <td colSpan={11} className="py-4 px-4 bg-slate-900/40" />
                </tr>
              ))
            ) : filteredCandidates.length === 0 ? (
              <tr>
                <td colSpan={11} className="py-8 text-center text-slate-500">
                  No securities match the selected screening criteria.
                </td>
              </tr>
            ) : (
              filteredCandidates.map((c, idx) => {
                const isWatchlist = c.is_watchlist;
                const score = c.composite_score || 0;
                return (
                  <tr
                    key={c.symbol}
                    className="hover:bg-slate-800/40 transition-colors group"
                  >
                    <td className="py-3 px-3 text-center font-bold text-slate-500">
                      {idx + 1}
                    </td>

                    <td className="py-3 px-4">
                      <Link
                        href={`/stocks/${c.symbol}`}
                        className="flex flex-col group-hover:text-cyan-400 transition-colors"
                      >
                        <span className="font-bold text-slate-100 flex items-center space-x-1">
                          <span>{c.symbol}</span>
                          <ChevronRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
                        </span>
                        <span className="text-[11px] text-slate-400 truncate max-w-[170px]" title={c.company_name}>
                          {c.company_name}
                        </span>
                      </Link>
                    </td>

                    <td className="py-3 px-3 text-slate-300">
                      <span className="truncate max-w-[130px] block" title={c.sector}>
                        {c.sector}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-right font-bold text-slate-100">
                      {c.close !== null ? `₹${c.close.toFixed(2)}` : "—"}
                    </td>

                    <td className="py-3 px-3 text-right text-slate-400">
                      {c.sma_200 !== null ? `₹${c.sma_200.toFixed(2)}` : "—"}
                    </td>

                    <td className="py-3 px-3 text-right">
                      <span className={c.debt_to_equity !== null && c.debt_to_equity < 0.5 ? "text-emerald-400" : "text-amber-400"}>
                        {c.debt_to_equity !== null ? c.debt_to_equity.toFixed(4) : "—"}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-right">
                      <span className={c.roe_pct !== null && c.roe_pct > 15.0 ? "text-emerald-400 font-semibold" : "text-slate-300"}>
                        {c.roe_pct !== null ? `${c.roe_pct.toFixed(2)}%` : "—"}
                      </span>
                    </td>

                    <td className="py-3 px-3 text-right text-slate-300">
                      {c.opm_pct !== null ? `${c.opm_pct.toFixed(2)}%` : "—"}
                    </td>

                    <td className="py-3 px-3 text-right">
                      {c.excess_ret_20d !== null ? (
                        <span className={c.excess_ret_20d >= 0 ? "text-emerald-400" : "text-red-400"}>
                          {c.excess_ret_20d >= 0 ? "+" : ""}{(c.excess_ret_20d * 100).toFixed(2)}%
                        </span>
                      ) : "—"}
                    </td>

                    <td className="py-3 px-4 text-center">
                      <div className="flex items-center justify-center space-x-2">
                        <div className="w-16 bg-slate-800 rounded-full h-1.5 overflow-hidden hidden sm:block">
                          <div
                            className="bg-gradient-to-r from-cyan-500 to-indigo-500 h-full rounded-full"
                            style={{ width: `${Math.min(100, Math.max(0, score))}%` }}
                          />
                        </div>
                        <span className="font-extrabold text-cyan-400 font-mono">
                          {score.toFixed(1)}
                        </span>
                      </div>
                    </td>

                    <td className="py-3 px-3 text-center">
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full font-semibold ${
                          isWatchlist
                            ? "bg-cyan-950 text-cyan-300 border border-cyan-800/80"
                            : "bg-slate-800 text-slate-400"
                        }`}
                      >
                        {isWatchlist ? "WATCHLIST" : "NIFTY 50"}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-slate-500 font-mono pt-1">
        <span>Showing {filteredCandidates.length} of {candidates.length} securities</span>
        <span className="hidden sm:inline">Sorting: Descending Composite Quality-Momentum Score</span>
      </div>
    </div>
  );
}
