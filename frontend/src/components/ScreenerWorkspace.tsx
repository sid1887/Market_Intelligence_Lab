"use client";

import React, { useState, useMemo, useRef, useEffect } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import {
  Search,
  Table as TableIcon,
  LayoutGrid,
  X,
  FilterX,
  ArrowUp,
  ArrowDown,
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";
import { ScreenerCandidate, prefetchStockBundle } from "@/lib/api";
import { ScreenerScoreCell } from "./ScreenerScoreCell";
import { SectorHeatmap } from "./SectorHeatmap";

export type SectorFilter =
  | "All"
  | "IT"
  | "Energy"
  | "Pharma"
  | "Auto"
  | "Financials"
  | "Capital Goods";

export const SECTOR_FILTERS: SectorFilter[] = [
  "All",
  "IT",
  "Energy",
  "Pharma",
  "Auto",
  "Financials",
  "Capital Goods",
];

function matchSector(item: ScreenerCandidate, filter: SectorFilter): boolean {
  if (filter === "All") return true;
  const sec = (item.sector || "").toLowerCase();
  if (filter === "IT")
    return (
      sec.includes("it") ||
      sec.includes("tech") ||
      sec.includes("software") ||
      sec.includes("information")
    );
  if (filter === "Energy")
    return (
      sec.includes("energy") ||
      sec.includes("power") ||
      sec.includes("oil") ||
      sec.includes("gas") ||
      sec.includes("petro")
    );
  if (filter === "Pharma")
    return sec.includes("pharma") || sec.includes("health") || sec.includes("bio");
  if (filter === "Auto")
    return sec.includes("auto") || sec.includes("motor") || sec.includes("vehicle");
  if (filter === "Financials")
    return (
      sec.includes("financial") ||
      sec.includes("bank") ||
      sec.includes("insurance") ||
      sec.includes("nbfc")
    );
  if (filter === "Capital Goods")
    return (
      sec.includes("capital") ||
      sec.includes("industrial") ||
      sec.includes("engineering") ||
      sec.includes("manufactur")
    );
  return true;
}

interface ScreenerWorkspaceProps {
  candidates: ScreenerCandidate[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  asOfDate?: string;
  loading?: boolean;
  viewMode?: "table" | "heatmap";
  onViewModeChange?: (mode: "table" | "heatmap") => void;
}

export default function ScreenerWorkspace({
  candidates,
  selectedSymbol,
  onSelectSymbol,
  asOfDate,
  loading = false,
  viewMode = "table",
  onViewModeChange,
}: ScreenerWorkspaceProps) {
  const [search, setSearch] = useState("");
  const [sectorFilter, setSectorFilter] = useState<SectorFilter>("All");
  const [sortField, setSortField] = useState<keyof ScreenerCandidate>("blended_score");
  const [sortAsc, setSortAsc] = useState<boolean>(false);
  const [minRoe, setMinRoe] = useState<number | null>(null);
  const [onlyAbove200Sma, setOnlyAbove200Sma] = useState<boolean>(false);
  const [onlyRebalanceTargets, setOnlyRebalanceTargets] = useState<boolean>(false);

  const tableBodyRef = useRef<HTMLDivElement>(null);
  const searchInputRef = useRef<HTMLInputElement>(null);

  // 1. Filtered and Sorted Candidates
  const filteredCandidates = useMemo(() => {
    const list = candidates.filter((item) => {
      if (search) {
        const q = search.toLowerCase();
        const matchesSym = item.symbol.toLowerCase().includes(q);
        const matchesName = item.company_name.toLowerCase().includes(q);
        const matchesSec = (item.sector || "").toLowerCase().includes(q);
        if (!matchesSym && !matchesName && !matchesSec) return false;
      }

      if (!matchSector(item, sectorFilter)) return false;

      if (minRoe !== null && (item.roe_pct === null || item.roe_pct < minRoe)) {
        return false;
      }

      if (onlyAbove200Sma && !item.price_above_sma200) {
        return false;
      }

      if (onlyRebalanceTargets && !item.is_rebalance_target && (item.target_allocation_pct || 0) <= 0) {
        return false;
      }

      return true;
    });

    list.sort((a, b) => {
      const getVal = (item: ScreenerCandidate) => {
        if (sortField === "blended_score") {
          return (item.blended_score && item.blended_score > 0)
            ? item.blended_score
            : ((item.composite_score && item.composite_score > 0) ? item.composite_score : 0);
        }
        return item[sortField];
      };
      const valA = getVal(a);
      const valB = getVal(b);
      if (valA === null || valA === undefined) return 1;
      if (valB === null || valB === undefined) return -1;
      if (valA < valB) return sortAsc ? -1 : 1;
      if (valA > valB) return sortAsc ? 1 : -1;
      return 0;
    });

    return list;
  }, [candidates, search, sectorFilter, sortField, sortAsc, minRoe, onlyAbove200Sma, onlyRebalanceTargets]);

  // Virtualizer for 60 FPS scrolling across large universes (1,000+ equities)
  const rowVirtualizer = useVirtualizer({
    count: filteredCandidates.length,
    getScrollElement: () => tableBodyRef.current,
    estimateSize: () => 64,
    overscan: 12,
  });

  // 2. Stable Selection Check
  const isSelectedVisible = useMemo(() => {
    if (!selectedSymbol) return true;
    return filteredCandidates.some((c) => c.symbol === selectedSymbol);
  }, [filteredCandidates, selectedSymbol]);

  // 3. Arrow Up / Down and Vim j / k Scrub Navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      if (
        target.tagName === "INPUT" ||
        target.tagName === "TEXTAREA" ||
        target.isContentEditable
      ) {
        return;
      }

      if (filteredCandidates.length === 0) return;

      if (e.key === "ArrowDown" || e.key === "j") {
        e.preventDefault();
        const currIdx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
        const nextIdx = currIdx === -1 ? 0 : Math.min(currIdx + 1, filteredCandidates.length - 1);
        const targetSym = filteredCandidates[nextIdx].symbol;
        onSelectSymbol(targetSym);
        prefetchStockBundle(targetSym);
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const currIdx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
        const prevIdx = currIdx === -1 ? 0 : Math.max(currIdx - 1, 0);
        const targetSym = filteredCandidates[prevIdx].symbol;
        onSelectSymbol(targetSym);
        prefetchStockBundle(targetSym);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filteredCandidates, selectedSymbol, onSelectSymbol]);

  // 4. Scroll Active Row into View using Virtualizer
  useEffect(() => {
    if (viewMode === "table" && selectedSymbol) {
      const idx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
      if (idx !== -1) {
        rowVirtualizer.scrollToIndex(idx, { align: "auto" });
      }
    }
  }, [selectedSymbol, viewMode, filteredCandidates, rowVirtualizer]);

  // Column Sort Handler
  const handleSort = (field: keyof ScreenerCandidate) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(field === "rank" || field === "symbol");
    }
  };

  const clearAllFilters = () => {
    setSearch("");
    setSectorFilter("All");
    setMinRoe(null);
    setOnlyAbove200Sma(false);
    setOnlyRebalanceTargets(false);
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#030508]/65 backdrop-blur-xl text-slate-100 select-none min-h-0">
      {/* Top Filter and Navigation Strip */}
      <div className="shrink-0 border-b border-white/[0.06] px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-3 bg-[#030508]/75 backdrop-blur-md">
        {/* Left: View Mode Toggle & Search */}
        <div className="flex items-center gap-2.5 flex-1 min-w-[280px]">
          {onViewModeChange && (
            <div className="flex items-center p-0.5 rounded-lg bg-[#050811] border border-white/[0.06]">
              <button
                onClick={() => onViewModeChange("table")}
                className={`relative px-2.5 py-1 text-[11px] font-mono transition-colors ${
                  viewMode === "table"
                    ? "text-cyan-300 font-bold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {viewMode === "table" && (
                  <motion.span
                    layoutId="viewModePill"
                    className="absolute inset-0 bg-cyan-500/15 border border-cyan-500/30 rounded-md"
                    transition={{ type: "spring", stiffness: 350, damping: 28 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <TableIcon className="w-3 h-3" />
                  <span>Screener</span>
                </span>
              </button>

              <button
                onClick={() => onViewModeChange("heatmap")}
                className={`relative px-2.5 py-1 text-[11px] font-mono transition-colors ${
                  viewMode === "heatmap"
                    ? "text-cyan-300 font-bold"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                {viewMode === "heatmap" && (
                  <motion.span
                    layoutId="viewModePill"
                    className="absolute inset-0 bg-cyan-500/15 border border-cyan-500/30 rounded-md"
                    transition={{ type: "spring", stiffness: 350, damping: 28 }}
                  />
                )}
                <span className="relative flex items-center gap-1.5">
                  <LayoutGrid className="w-3 h-3" />
                  <span>Heatmap</span>
                </span>
              </button>
            </div>
          )}

          {/* Quick Search Input */}
          <div className="relative flex-1 max-w-xs">
            <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
            <input
              ref={searchInputRef}
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter ticker, name, sector..."
              className="w-full bg-[#050811] border border-white/[0.08] focus:border-cyan-500/60 rounded-md pl-8 pr-7 py-1 text-xs font-mono text-slate-200 placeholder-slate-600 focus:outline-none transition-all"
            />
            {search && (
              <button
                onClick={() => setSearch("")}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
              >
                <X className="w-3 h-3" />
              </button>
            )}
          </div>
        </div>

        {/* Right: As of Date & Candidate Count */}
        <div className="flex items-center gap-2 text-[11px] font-mono text-slate-400 shrink-0">
          {asOfDate && (
            <span className="px-2 py-0.5 rounded bg-slate-900 border border-white/[0.06] text-slate-400">
              Session: <strong className="text-slate-200">{asOfDate}</strong>
            </span>
          )}
          <span className="px-2 py-0.5 rounded bg-slate-900 border border-white/[0.06] text-slate-400">
            <strong className="text-cyan-400">{filteredCandidates.length}</strong> / {candidates.length} Equities
          </span>
        </div>
      </div>

      {/* Sector Filter Chips */}
      <div className="shrink-0 border-b border-white/[0.04] px-3.5 py-1.5 flex items-center gap-1.5 overflow-x-auto no-scrollbar bg-[#020406]">
        {SECTOR_FILTERS.map((sec) => (
          <button
            key={sec}
            onClick={() => setSectorFilter(sec)}
            className={`px-2 py-0.5 rounded text-[11px] font-mono whitespace-nowrap transition-colors ${
              sectorFilter === sec
                ? "bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-semibold"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60 border border-transparent"
            }`}
          >
            {sec}
          </button>
        ))}

        <div className="h-3 w-[1px] bg-white/[0.08] mx-1 shrink-0" />

        {/* Toggle 200 SMA */}
        <button
          onClick={() => setOnlyAbove200Sma(!onlyAbove200Sma)}
          className={`px-2 py-0.5 rounded text-[11px] font-mono whitespace-nowrap transition-colors ${
            onlyAbove200Sma
              ? "bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-semibold"
              : "text-slate-500 hover:text-slate-300 border border-transparent"
          }`}
          title="Filter stocks where Close > 200 SMA"
        >
          {">"} 200 SMA
        </button>

        {/* Quick Filter: Rebalance Targets Only */}
        <button
          onClick={() => setOnlyRebalanceTargets(!onlyRebalanceTargets)}
          className={`px-2 py-0.5 rounded text-[11px] font-mono whitespace-nowrap transition-all flex items-center gap-1.5 ${
            onlyRebalanceTargets
              ? "bg-emerald-950/90 text-emerald-300 border border-emerald-500/50 shadow-[0_0_12px_rgba(16,185,129,0.3)] font-bold"
              : "text-slate-400 hover:text-emerald-300 hover:bg-slate-900/60 border border-transparent"
          }`}
          title="Filter Top Rebalance Allocation Targets (Top 15 Champions)"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>Rebalance Targets Only</span>
        </button>

        {/* Filter Reset if Active */}
        {(search || sectorFilter !== "All" || onlyAbove200Sma || onlyRebalanceTargets || minRoe !== null) && (
          <button
            onClick={clearAllFilters}
            className="flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-mono text-amber-400 hover:bg-amber-950/40 border border-amber-500/30 transition-colors ml-auto"
            title="Clear all active filters"
          >
            <FilterX className="w-3 h-3" />
            <span>Reset</span>
          </button>
        )}
      </div>

      {/* Selection Filter Warning Banner (Shown if selectedSymbol is hidden by filters) */}
      {!isSelectedVisible && selectedSymbol && (
        <div className="shrink-0 px-3.5 py-1.5 bg-amber-950/30 border-b border-amber-500/20 flex items-center justify-between text-xs font-mono text-amber-300">
          <span>
            Selected stock <strong>[{selectedSymbol}]</strong> is hidden by active filters.
          </span>
          <button
            onClick={clearAllFilters}
            className="text-[11px] underline hover:text-amber-100"
          >
            Clear Filters to View
          </button>
        </div>
      )}

      {/* Main Content: Table or Heatmap */}
      {viewMode === "heatmap" ? (
        <div className="flex-1 overflow-y-auto p-4 min-h-0">
          <SectorHeatmap
            candidates={candidates}
            activeSymbol={selectedSymbol || ""}
            onSelect={onSelectSymbol}
          />
        </div>
      ) : (
        <div className="flex-1 flex flex-col overflow-hidden min-h-0 h-full">
          {/* Table Header: Desktop 12-Col vs Mobile Streamlined */}
          <div className="hidden md:grid shrink-0 grid-cols-12 gap-2 px-3 py-2 border-b border-white/[0.08] bg-[#050811]/80 backdrop-blur-md text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-400">
            <div
              className="col-span-1 cursor-pointer flex items-center gap-1 hover:text-slate-200"
              onClick={() => handleSort("rank")}
            >
              <span>#</span>
              {sortField === "rank" && (
                sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
              )}
            </div>

            <div
              className="col-span-3 cursor-pointer flex items-center gap-1 hover:text-slate-200"
              onClick={() => handleSort("symbol")}
            >
              <span>Ticker</span>
              {sortField === "symbol" && (
                sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
              )}
            </div>

            <div
              className="col-span-2 text-right cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
              onClick={() => handleSort("close")}
            >
              <span>Close</span>
              {sortField === "close" && (
                sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
              )}
            </div>

            <div
              className="col-span-2 text-right cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
              onClick={() => handleSort("blended_score")}
              title="Multi-Horizon Blended Score (20D 62.5% + 60D 37.5%)"
            >
              <span>Blended</span>
              {sortField === "blended_score" && (
                sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
              )}
            </div>

            <div
              className="col-span-2 text-right cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
              onClick={() => handleSort("roe_pct")}
            >
              <span>ROE</span>
              {sortField === "roe_pct" && (
                sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
              )}
            </div>

            <div
              className="col-span-2 text-right cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
              onClick={() => handleSort("excess_ret_20d")}
            >
              <span>20D Ret</span>
              {sortField === "excess_ret_20d" && (
                sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
              )}
            </div>
          </div>

          {/* Mobile Table Header (< 768px) */}
          <div className="flex md:hidden items-center justify-between px-3.5 py-1.5 text-[10px] font-mono text-slate-400 border-b border-white/[0.06] bg-[#020406]/90 shrink-0 sticky top-0 z-10">
            <span>RANK · INSTRUMENT</span>
            <span>PRICE · SCORE · 20D</span>
          </div>

          {/* Table Body (Virtual Windowed Chunk Rendering for 60 FPS) */}
          <div
            ref={tableBodyRef}
            className="flex-1 overflow-y-auto relative scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent min-h-0 h-full w-full"
          >
            {loading && candidates.length === 0 ? (
              <div className="p-8 text-center text-slate-500 font-mono text-xs">
                Loading universe screener...
              </div>
            ) : filteredCandidates.length === 0 ? (
              <div className="p-8 text-center text-slate-500 font-mono text-xs">
                No equities match the selected criteria.
              </div>
            ) : (
              <div
                style={{
                  height: `${rowVirtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {rowVirtualizer.getVirtualItems().map((virtualRow) => {
                  const cand = filteredCandidates[virtualRow.index];
                  const idx = virtualRow.index;
                  const isSelected = cand.symbol === selectedSymbol;
                  const excessRet = cand.excess_ret_20d;
                  const isPositiveRet = typeof excessRet === "number" && excessRet > 0;
                  const isNegativeRet = typeof excessRet === "number" && excessRet < 0;

                  return (
                    <div
                      key={cand.symbol}
                      data-symbol={cand.symbol}
                      data-index={virtualRow.index}
                      ref={rowVirtualizer.measureElement}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: `${virtualRow.size}px`,
                        transform: `translateY(${virtualRow.start}px) translateZ(0)`,
                      }}
                    >
                      <motion.div
                        initial={virtualRow.index < 18 ? { opacity: 0, x: -10 } : false}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{
                          duration: 0.15,
                          delay: virtualRow.index < 18 ? virtualRow.index * 0.015 : 0,
                          ease: "easeOut",
                        }}
                        onClick={() => {
                          onSelectSymbol(cand.symbol);
                          prefetchStockBundle(cand.symbol);
                        }}
                        className={cn(
                          "h-[64px] w-full relative group flex md:grid md:grid-cols-12 md:gap-2 px-3.5 py-2 cursor-pointer items-center text-xs font-mono transition-all duration-150 hover:bg-white/[0.04] active:bg-white/[0.08] border-b border-white/[0.04]",
                          isSelected
                            ? "bg-cyan-950/40 text-white font-medium shadow-[inset_0_0_20px_rgba(6,182,212,0.12)]"
                            : "text-slate-300 hover:text-white"
                        )}
                      >
                        {/* Kinetic glowing left-edge indicator */}
                        {isSelected && (
                          <div
                            className="absolute left-0 top-0 bottom-0 w-[3px] bg-gradient-to-b from-cyan-400 via-emerald-400 to-teal-400 shadow-[0_0_12px_rgba(6,182,212,0.9)]"
                          />
                        )}

                        {/* Mobile Streamlined View (< 768px) */}
                        <div className="flex md:hidden items-center justify-between w-full h-full gap-2">
                          <div className="flex items-center gap-2 min-w-0">
                            <span className="text-slate-500 text-[11px] tabular-nums font-mono w-6 shrink-0">
                              #{cand.rank || idx + 1}
                            </span>
                            <div className="min-w-0">
                              <div className="flex items-center gap-1.5 flex-wrap">
                                <span className="font-bold tracking-tight text-slate-100 text-xs">
                                  {cand.symbol}
                                </span>
                                {Boolean(cand.is_watchlist) && (
                                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" title="Watchlist" />
                                )}
                                {Boolean(cand.target_allocation_pct && cand.target_allocation_pct > 0) && (
                                  <span
                                    className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-emerald-950/90 text-emerald-300 border border-emerald-500/50"
                                    title={`Target: ${cand.target_allocation_pct!.toFixed(2)}%`}
                                  >
                                    {cand.target_allocation_pct!.toFixed(1)}%
                                  </span>
                                )}
                              </div>
                              <div className="text-[10px] text-slate-400 truncate max-w-[150px]">
                                {cand.company_name || cand.sector || "Equity"}
                              </div>
                            </div>
                          </div>

                          <div className="flex items-center gap-3 shrink-0 text-right">
                            <div>
                              <div className={`font-semibold text-xs text-slate-200 ${isPositiveRet ? "animate-tick-up" : isNegativeRet ? "animate-tick-down" : ""}`}>
                                {cand.close !== null ? `₹${cand.close.toFixed(1)}` : "—"}
                              </div>
                              <div className="text-[10px] font-medium">
                                {excessRet !== null && excessRet !== undefined ? (
                                  <span className={isPositiveRet ? "text-emerald-400" : isNegativeRet ? "text-rose-400" : "text-slate-500"}>
                                    {isPositiveRet ? "+" : ""}{(excessRet * 100).toFixed(1)}%
                                  </span>
                                ) : (
                                  <span className="text-slate-600">—</span>
                                )}
                              </div>
                            </div>
                            <div className="w-12 flex justify-end">
                              {(() => {
                                const score = (cand.blended_score !== null && cand.blended_score !== undefined && cand.blended_score > 0)
                                  ? cand.blended_score
                                  : ((cand.composite_score !== null && cand.composite_score !== undefined && cand.composite_score > 0)
                                      ? cand.composite_score
                                      : null);
                                return score !== null ? (
                                  <ScreenerScoreCell score={score} />
                                ) : (
                                  <span className="text-slate-600 text-xs">—</span>
                                );
                              })()}
                            </div>
                          </div>
                        </div>

                        {/* Desktop 12-Column Grid (>= 768px) */}
                        <div className="hidden md:contents">
                          {/* Rank */}
                          <div className="col-span-1 text-slate-500 text-[11px] tabular-nums pl-1">
                            {cand.rank || idx + 1}
                          </div>

                          {/* Ticker & Name */}
                          <div className="col-span-3 min-w-0">
                            <div className="flex items-center flex-wrap gap-1.5">
                              <span className="font-bold tracking-tight text-slate-100">
                                {cand.symbol}
                              </span>
                              {Boolean(cand.is_watchlist) && (
                                <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" title="Watchlist" />
                              )}
                              {/* Target Rebalance Allocation Pill */}
                              {Boolean(cand.target_allocation_pct && cand.target_allocation_pct > 0) && (
                                <span
                                  className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-emerald-950/90 text-emerald-300 border border-emerald-500/50 shadow-[0_0_8px_rgba(16,185,129,0.35)] animate-pulse"
                                  title={`Recommended Target Allocation: ${cand.target_allocation_pct!.toFixed(2)}%`}
                                >
                                  Alloc: {cand.target_allocation_pct!.toFixed(2)}%
                                </span>
                              )}
                              {/* Horizon Drivers Badges */}
                              {Boolean(cand.horizon_drivers && cand.horizon_drivers.length > 0) && (
                                <div className="flex items-center gap-1">
                                  {cand.horizon_drivers!.includes("20D") && (
                                    <span
                                      className="px-1 py-0.2 rounded text-[8px] font-mono bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-semibold"
                                      title="20-Day Tactical Horizon Contributor (62.5% weight)"
                                    >
                                      20D
                                    </span>
                                  )}
                                  {cand.horizon_drivers!.includes("60D") && (
                                    <span
                                      className="px-1 py-0.2 rounded text-[8px] font-mono bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 font-semibold"
                                      title="60-Day Trend Drift Horizon Contributor (37.5% weight)"
                                    >
                                      60D
                                    </span>
                                  )}
                                </div>
                              )}
                              {Boolean(cand.price_above_sma200) && (
                                <span
                                  className="text-[9px] px-1 rounded bg-slate-900 text-slate-400 border border-white/[0.08]"
                                  title="Price above 200-day SMA"
                                >
                                  SMA
                                </span>
                              )}
                            </div>
                            <div className="text-[10px] text-slate-500 truncate mt-0.5">
                              {cand.company_name}
                            </div>
                          </div>

                          {/* Close Price */}
                          <div className="col-span-2 text-right tabular-nums">
                            <div className={`font-semibold text-slate-200 transition-colors ${isPositiveRet ? "animate-tick-up" : isNegativeRet ? "animate-tick-down" : ""}`}>
                              {cand.close !== null ? `₹${cand.close.toFixed(2)}` : "—"}
                            </div>
                            {cand.sma_200 !== null && (
                              <div className="text-[10px] text-slate-500">
                                SMA: ₹{cand.sma_200.toFixed(0)}
                              </div>
                            )}
                          </div>

                          {/* Blended / Composite Score */}
                          <div className="col-span-2 flex justify-end">
                            {(() => {
                              const score = (cand.blended_score !== null && cand.blended_score !== undefined && cand.blended_score > 0)
                                ? cand.blended_score
                                : ((cand.composite_score !== null && cand.composite_score !== undefined && cand.composite_score > 0)
                                    ? cand.composite_score
                                    : null);
                              return score !== null ? (
                                <ScreenerScoreCell score={score} />
                              ) : (
                                <span className="text-slate-600">—</span>
                              );
                            })()}
                          </div>

                          {/* ROE */}
                          <div className="col-span-2 text-right tabular-nums text-slate-300">
                            {cand.roe_pct !== null ? `${cand.roe_pct.toFixed(1)}%` : "—"}
                          </div>

                          {/* 20D Excess Return */}
                          <div className="col-span-2 text-right tabular-nums font-semibold">
                            {excessRet !== null && excessRet !== undefined ? (
                              <span
                                className={`inline-flex items-center justify-end px-1 py-0.5 rounded ${
                                  isPositiveRet
                                    ? "text-emerald-400 animate-tick-up"
                                    : isNegativeRet
                                    ? "text-rose-400 animate-tick-down"
                                    : "text-slate-400"
                                }`}
                              >
                                {isPositiveRet ? "+" : ""}
                                {(excessRet * 100).toFixed(1)}%
                              </span>
                            ) : (
                              <span className="text-slate-600">—</span>
                            )}
                          </div>
                        </div>
                    </motion.div>
                  </div>
                );
                })}
              </div>
            )}
          </div>
        </div>
      )}

      {/* Bottom Keyboard Navigation Hint Bar */}
      <div className="shrink-0 border-t border-white/[0.04] px-3.5 py-1.5 flex items-center justify-between text-[10px] font-mono text-slate-500 bg-[#020406]">
        <div className="flex items-center gap-3">
          <span>
            <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-white/[0.08] text-slate-400">↑</kbd>
            {" "}
            <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-white/[0.08] text-slate-400">↓</kbd>
            {" or "}
            <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-white/[0.08] text-slate-400">j</kbd>
            {" "}
            <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-white/[0.08] text-slate-400">k</kbd>
            {" to navigate"}
          </span>
        </div>
        <div>
          <span>Press <kbd className="px-1 py-0.5 rounded bg-slate-900 border border-white/[0.08] text-slate-400">⌘K</kbd> to search</span>
        </div>
      </div>
    </div>
  );
}
