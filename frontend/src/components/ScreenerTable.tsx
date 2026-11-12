"use client";

import React, { useState, useMemo, useRef, useEffect } from "react";
import Link from "next/link";
import { Search, ChevronRight, SlidersHorizontal, ExternalLink } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import { ScreenerScoreCell } from "./ScreenerScoreCell";
import QuickInspectDrawer from "./QuickInspectDrawer";

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

type SectorFilter = "All" | "IT" | "Energy" | "Pharma" | "Auto" | "Financials";

export default function ScreenerTable({ candidates, asOfDate, loading }: ScreenerTableProps) {
  const [search, setSearch] = useState("");
  const [selectedSector, setSelectedSector] = useState<SectorFilter>("All");
  const [minRoe, setMinRoe] = useState<number>(0);
  const [maxDe, setMaxDe] = useState<number>(999);
  const [onlyAbove200Sma, setOnlyAbove200Sma] = useState<boolean>(false);
  const [excludeFinancials, setExcludeFinancials] = useState<boolean>(false);
  const [onlyWatchlist, setOnlyWatchlist] = useState<boolean>(false);

  // Quick-Inspect Drawer state
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);

  const searchInputRef = useRef<HTMLInputElement>(null);

  // Keyboard shortcut listener (Cmd+K / Ctrl+K)
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        searchInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

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

      // Sector Segmented filter
      if (selectedSector !== "All") {
        const sec = item.sector.toLowerCase();
        if (selectedSector === "IT" && !sec.includes("it") && !sec.includes("tech") && !sec.includes("software")) return false;
        if (selectedSector === "Energy" && !sec.includes("energy") && !sec.includes("power") && !sec.includes("oil") && !sec.includes("gas") && !sec.includes("petro")) return false;
        if (selectedSector === "Pharma" && !sec.includes("pharma") && !sec.includes("health") && !sec.includes("bio")) return false;
        if (selectedSector === "Auto" && !sec.includes("auto") && !sec.includes("motor") && !sec.includes("vehicle")) return false;
        if (selectedSector === "Financials" && !sec.includes("financial") && !sec.includes("bank") && !sec.includes("insurance")) return false;
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
  }, [candidates, search, selectedSector, minRoe, maxDe, onlyAbove200Sma, excludeFinancials, onlyWatchlist]);

  return (
    <>
      <div className="relative bg-[#06090f] border border-white/[0.08] rounded-xl p-4 shadow-2xl space-y-3.5 overflow-hidden">
        {/* Top specular highlight edge */}
        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/30 to-transparent" />

        {/* Header & Command Search Bar */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-white/[0.07]">
          <div>
            <div className="flex items-center space-x-2.5">
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
              </span>
              <h2 className="text-base font-bold text-white font-mono tracking-tight">Institutional Factor Screener</h2>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-mono font-bold shadow-[0_0_10px_rgba(6,182,212,0.15)]">
                NIFTY Liquid Universe
              </span>
              {asOfDate && (
                <span className="text-[11px] text-slate-400 font-mono hidden sm:inline">
                  &middot; Session: {asOfDate}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 font-mono mt-0.5">
              Percentile weighted: ROE % (30%), Low D/E (25%), 20D Excess Return (25%), OPM % (20%). Click row for Quick Inspect.
            </p>
          </div>

          {/* Command-Bar Style Search */}
          <div className="relative w-full lg:w-80">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              ref={searchInputRef}
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search universe symbols, sector..."
              className="w-full bg-[#040711] border border-white/[0.08] focus:border-cyan-500 rounded-lg pl-8 pr-12 py-1.5 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none transition-colors shadow-inner"
            />
            <div className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center space-x-0.5 pointer-events-none">
              <kbd className="text-[9px] font-mono px-1 py-0.5 rounded bg-white/[0.05] text-slate-400 border border-white/[0.08]">
                ⌘K
              </kbd>
            </div>
          </div>
        </div>

        {/* Filter Toolbar: Sector Switches & Ratio Presets */}
        <div className="flex flex-wrap items-center justify-between gap-2.5 pt-0.5 text-xs font-mono">
          {/* Segmented Sector Pill Switches */}
          <div className="flex items-center space-x-1 p-1 bg-[#040711] rounded-lg border border-white/[0.06]">
            {(["All", "IT", "Energy", "Pharma", "Auto", "Financials"] as const).map(sec => (
              <button
                key={sec}
                onClick={() => setSelectedSector(sec)}
                className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-all ${
                  selectedSector === sec
                    ? "bg-cyan-500/20 text-cyan-200 border border-cyan-500/40 shadow-sm shadow-cyan-950/40"
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.04] border border-transparent"
                }`}
              >
                {sec}
              </button>
            ))}
          </div>

          {/* Quick Quantitative Criteria Pills */}
          <div className="flex flex-wrap items-center gap-1.5 text-xs font-mono">
            <span className="text-slate-400 flex items-center space-x-1 mr-1 text-[11px]">
              <SlidersHorizontal className="w-3 h-3 text-cyan-400" />
              <span>Filters:</span>
            </span>

            <button
              onClick={() => {
                setMinRoe(15.0);
                setMaxDe(0.5);
                setOnlyAbove200Sma(true);
                setExcludeFinancials(true);
                setOnlyWatchlist(false);
              }}
              className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${
                minRoe === 15.0 && maxDe === 0.5 && onlyAbove200Sma && excludeFinancials
                  ? "bg-cyan-950/90 border-cyan-500/60 text-cyan-200 font-bold shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                  : "bg-[#040711] border-white/[0.06] text-slate-400 hover:text-slate-200"
              }`}
            >
              ⚡ High Conviction Quality Screen
            </button>

            <button
              onClick={() => setOnlyAbove200Sma(!onlyAbove200Sma)}
              className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${
                onlyAbove200Sma
                  ? "bg-emerald-950/90 border-emerald-500/60 text-emerald-200 font-bold shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                  : "bg-[#040711] border-white/[0.06] text-slate-400 hover:text-slate-200"
              }`}
            >
              {onlyAbove200Sma ? "✓ Price > 200 SMA" : "Price > 200 SMA"}
            </button>

            <button
              onClick={() => setExcludeFinancials(!excludeFinancials)}
              className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${
                excludeFinancials
                  ? "bg-amber-950/90 border-amber-500/60 text-amber-200 font-bold shadow-[0_0_10px_rgba(245,158,11,0.2)]"
                  : "bg-[#040711] border-white/[0.06] text-slate-400 hover:text-slate-200"
              }`}
            >
              {excludeFinancials ? "✓ Excl. Financials" : "Excl. Financials"}
            </button>

            <button
              onClick={() => setMinRoe(minRoe === 15.0 ? 0 : 15.0)}
              className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${
                minRoe === 15.0
                  ? "bg-indigo-950/90 border-indigo-500/60 text-indigo-200 font-bold"
                  : "bg-[#040711] border-white/[0.06] text-slate-400 hover:text-slate-200"
              }`}
            >
              {minRoe === 15.0 ? "✓ ROE > 15%" : "ROE > 15%"}
            </button>

            <button
              onClick={() => setMaxDe(maxDe === 0.5 ? 999 : 0.5)}
              className={`px-2 py-0.5 rounded text-[11px] border transition-colors ${
                maxDe === 0.5
                  ? "bg-purple-950/90 border-purple-500/60 text-purple-200 font-bold"
                  : "bg-[#040711] border-white/[0.06] text-slate-400 hover:text-slate-200"
              }`}
            >
              {maxDe === 0.5 ? "✓ D/E < 0.5" : "D/E < 0.5"}
            </button>

            {(minRoe > 0 || maxDe < 999 || onlyAbove200Sma || excludeFinancials || onlyWatchlist || search || selectedSector !== "All") && (
              <button
                onClick={() => {
                  setMinRoe(0);
                  setMaxDe(999);
                  setOnlyAbove200Sma(false);
                  setExcludeFinancials(false);
                  setOnlyWatchlist(false);
                  setSelectedSector("All");
                  setSearch("");
                }}
                className="px-2 py-0.5 text-[11px] text-rose-400 hover:text-rose-300 underline underline-offset-2 ml-auto"
              >
                Reset
              </button>
            )}
          </div>
        </div>

        {/* High-Density Candidates Table with Frozen Columns */}
        <div className="overflow-x-auto rounded-lg border border-white/[0.08] relative shadow-inner">
          <table className="w-full text-left text-xs font-mono border-collapse">
            <thead className="bg-[#070c18] text-slate-400 uppercase text-[11px] font-mono tracking-wider border-b border-white/[0.08]">
              <tr className="h-9">
                <th scope="col" className="sticky left-0 bg-[#070c18] z-20 shadow-[2px_0_10px_-2px_rgba(0,0,0,0.8)] py-2 px-2.5 w-10 text-center">#</th>
                <th scope="col" className="sticky left-10 bg-[#070c18] z-20 shadow-[2px_0_10px_-2px_rgba(0,0,0,0.8)] py-2 px-3.5 min-w-[180px]">Symbol / Name</th>
                <th scope="col" className="py-2 px-3">Sector</th>
                <th scope="col" className="py-2 px-3 text-right">Close (₹)</th>
                <th scope="col" className="py-2 px-3 text-right">200 SMA</th>
                <th scope="col" className="py-2 px-3 text-right">D/E</th>
                <th scope="col" className="py-2 px-3 text-right">ROE %</th>
                <th scope="col" className="py-2 px-3 text-right">OPM %</th>
                <th scope="col" className="py-2 px-3 text-right">Excess (20D)</th>
                <th scope="col" className="py-2 px-3 text-right min-w-[130px]">Score</th>
                <th scope="col" className="py-2 px-2.5 text-center">Inspect</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04]">
              {loading ? (
                [1, 2, 3, 4, 5, 6, 7].map(i => (
                  <tr key={i} className="h-10 animate-pulse bg-[#060a14]">
                    <td colSpan={11} className="py-2 px-4 bg-white/[0.02]" />
                  </tr>
                ))
              ) : filteredCandidates.length === 0 ? (
                <tr>
                  <td colSpan={11} className="py-8 text-center text-slate-500 font-mono">
                    No securities match the selected screening criteria.
                  </td>
                </tr>
              ) : (
                <AnimatePresence mode="popLayout">
                  {filteredCandidates.map((c, idx) => {
                    const score = c.composite_score || 0;
                    const rowBg = idx % 2 === 0 ? "bg-[#060a14]/70" : "bg-[#04070e]/85";

                    return (
                      <motion.tr
                        key={c.symbol}
                        layout
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ type: "spring", stiffness: 260, damping: 24 }}
                        onClick={() => setSelectedSymbol(c.symbol)}
                        className={`h-10 ${rowBg} hover:bg-cyan-950/30 cursor-pointer transition-colors group border-b border-white/[0.04]`}
                      >
                        {/* Frozen Column 1: Rank */}
                        <td className={`sticky left-0 ${rowBg} group-hover:bg-cyan-950/30 z-10 shadow-[2px_0_10px_-2px_rgba(0,0,0,0.8)] py-1.5 px-2.5 text-center font-bold text-slate-500 text-[11px] tabular-nums`}>
                          {idx + 1}
                        </td>

                        {/* Frozen Column 2: Symbol & Name */}
                        <td className={`sticky left-10 ${rowBg} group-hover:bg-cyan-950/30 z-10 shadow-[2px_0_10px_-2px_rgba(0,0,0,0.8)] py-1.5 px-3.5`}>
                          <div className="flex items-center justify-between">
                            <div className="flex flex-col">
                              <span className="font-bold text-white text-[12px] group-hover:text-cyan-300 transition-colors flex items-center space-x-1">
                                <span>{c.symbol}</span>
                                <ChevronRight className="w-2.5 h-2.5 opacity-0 group-hover:opacity-100 text-cyan-400 transition-opacity" />
                              </span>
                              <span className="text-[11px] text-slate-400 truncate max-w-[150px] leading-tight" title={c.company_name}>
                                {c.company_name}
                              </span>
                            </div>

                            {/* Direct link icon to full tearsheet */}
                            <Link
                              href={`/stocks/${c.symbol}`}
                              onClick={(e) => e.stopPropagation()}
                              title="Open Full Tearsheet directly"
                              className="opacity-0 group-hover:opacity-100 p-1 text-slate-400 hover:text-cyan-400 transition-opacity"
                            >
                              <ExternalLink className="w-3 h-3" />
                            </Link>
                          </div>
                        </td>

                        {/* Sector */}
                        <td className="py-1.5 px-3 text-slate-300 text-[11px]">
                          <span className="truncate max-w-[120px] block" title={c.sector}>
                            {c.sector}
                          </span>
                        </td>

                        {/* Close Price */}
                        <td className="py-1.5 px-3 text-right font-bold text-slate-100 font-mono tabular-nums text-[13px]">
                          {c.close !== null ? `₹${c.close.toFixed(2)}` : "—"}
                        </td>

                        {/* 200 SMA */}
                        <td className="py-1.5 px-3 text-right text-slate-400 font-mono tabular-nums text-[12px]">
                          {c.sma_200 !== null ? `₹${c.sma_200.toFixed(2)}` : "—"}
                        </td>

                        {/* Debt / Equity */}
                        <td className="py-1.5 px-3 text-right font-mono tabular-nums text-[12px]">
                          <span className={c.debt_to_equity !== null && c.debt_to_equity < 0.5 ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                            {c.debt_to_equity !== null ? c.debt_to_equity.toFixed(3) : "—"}
                          </span>
                        </td>

                        {/* ROE % */}
                        <td className="py-1.5 px-3 text-right font-mono tabular-nums text-[12px]">
                          {c.roe_pct !== null ? (
                            <span
                              className={
                                c.roe_pct > 25.0
                                  ? "bg-emerald-500/15 text-emerald-300 font-semibold px-1.5 py-0.2 rounded border border-emerald-500/30 text-[11px]"
                                  : c.roe_pct > 15.0
                                  ? "text-emerald-400 font-semibold"
                                  : "text-slate-300"
                              }
                            >
                              {c.roe_pct.toFixed(1)}%
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>

                        {/* OPM % */}
                        <td className="py-1.5 px-3 text-right text-slate-300 font-mono tabular-nums text-[12px]">
                          {c.opm_pct !== null ? `${c.opm_pct.toFixed(1)}%` : "—"}
                        </td>

                        {/* 20-Day Excess Return */}
                        <td className="py-1.5 px-3 text-right font-mono tabular-nums text-[12px]">
                          {c.excess_ret_20d !== null ? (
                            <span className={c.excess_ret_20d >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                              {c.excess_ret_20d >= 0 ? "+" : ""}{(c.excess_ret_20d * 100).toFixed(1)}%
                            </span>
                          ) : "—"}
                        </td>

                        {/* Quality-Momentum Composite Score */}
                        <td className="py-1.5 px-3 text-right">
                          <ScreenerScoreCell score={score} />
                        </td>

                        {/* Quick Inspect Trigger Pill */}
                        <td className="py-1.5 px-2.5 text-center">
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedSymbol(c.symbol);
                            }}
                            className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 hover:bg-cyan-900/60 transition-colors shadow-sm"
                          >
                            Inspect
                          </button>
                        </td>
                      </motion.tr>
                    );
                  })}
                </AnimatePresence>
              )}
            </tbody>
          </table>
        </div>

        {/* Footer Summary */}
        <div className="flex items-center justify-between text-[11px] text-slate-400 font-mono pt-0.5">
          <span>Displaying {filteredCandidates.length} of {candidates.length} universe securities</span>
          <span className="hidden sm:inline">Sorted: Composite Quality-Momentum Score (Desc) &middot; Click any row to Inspect</span>
        </div>
      </div>

      {/* Quick-Inspect Slide-Over Drawer */}
      <AnimatePresence>
        {selectedSymbol && (
          <QuickInspectDrawer
            symbol={selectedSymbol}
            onClose={() => setSelectedSymbol(null)}
          />
        )}
      </AnimatePresence>
    </>
  );
}
