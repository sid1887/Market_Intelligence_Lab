"use client";

import React, { useState, useMemo, useEffect, useRef } from "react";
import {
  Search,
  Table as TableIcon,
  LayoutGrid,
  X,
  FilterX,
  ArrowUp,
  ArrowDown,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScreenerCandidate } from "@/lib/api";
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

// ─── Memoized Desktop Row Component ─────────────────────────────────────────

interface DesktopRowProps {
  cand: ScreenerCandidate;
  idx: number;
  isSelected: boolean;
  onSelect: (sym: string) => void;
}

const DesktopScreenerRow = React.memo(function DesktopScreenerRow({
  cand,
  idx,
  isSelected,
  onSelect,
}: DesktopRowProps) {
  const ret20 = cand.ret_20d ?? cand.excess_ret_20d ?? 0.0;
  const isPositiveRet = ret20 > 0;
  const isNegativeRet = ret20 < 0;

  const score =
    cand.blended_score && cand.blended_score > 0
      ? cand.blended_score
      : cand.composite_score && cand.composite_score > 0
      ? cand.composite_score
      : null;

  return (
    <tr
      onClick={() => onSelect(cand.symbol)}
      className={cn(
        "cursor-pointer border-b border-white/[0.04] transition-colors text-xs font-mono select-none h-12",
        isSelected
          ? "bg-cyan-950/40 text-white font-medium shadow-[inset_0_0_15px_rgba(6,182,212,0.12)]"
          : "text-slate-300 hover:bg-white/[0.03] hover:text-white"
      )}
    >
      {/* 1. Rank */}
      <td className="px-3 py-2 text-slate-500 tabular-nums w-12 text-center">
        {cand.rank || idx + 1}
      </td>

      {/* 2. Ticker & Name */}
      <td className="px-3 py-2 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="font-bold tracking-tight text-slate-100">
            {cand.symbol}
          </span>
          {Boolean(cand.is_watchlist) && (
            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shrink-0" title="Watchlist" />
          )}
          {Boolean(cand.target_allocation_pct && cand.target_allocation_pct > 0) && (
            <span
              className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-950/90 text-emerald-300 border border-emerald-500/50"
              title={`Target: ${cand.target_allocation_pct!.toFixed(2)}%`}
            >
              {cand.target_allocation_pct!.toFixed(1)}%
            </span>
          )}
          {Boolean(cand.price_above_sma200) && (
            <span
              className="text-[8px] px-1 rounded bg-slate-900 text-slate-400 border border-white/[0.08]"
              title="Close > 200 SMA"
            >
              SMA
            </span>
          )}
        </div>
        <div className="text-[10px] text-slate-500 truncate max-w-[200px]">
          {cand.company_name}
        </div>
      </td>

      {/* 3. Close Price */}
      <td className="px-3 py-2 text-right tabular-nums">
        <div className="font-semibold text-slate-200">
          {cand.close !== null ? `₹${cand.close.toFixed(2)}` : "—"}
        </div>
        {cand.sma_200 !== null && (
          <div className="text-[9px] text-slate-500">
            SMA: ₹{cand.sma_200.toFixed(0)}
          </div>
        )}
      </td>

      {/* 4. Blended Score */}
      <td className="px-3 py-2 text-right">
        <div className="flex justify-end">
          {score !== null ? (
            <ScreenerScoreCell score={score} />
          ) : (
            <span className="text-slate-600">—</span>
          )}
        </div>
      </td>

      {/* 5. ROE */}
      <td className="px-3 py-2 text-right tabular-nums text-slate-300">
        {cand.roe_pct !== null ? `${cand.roe_pct.toFixed(1)}%` : "—"}
      </td>

      {/* 6. 20D Return */}
      <td className="px-3 py-2 text-right tabular-nums font-semibold">
        <span
          className={
            isPositiveRet
              ? "text-emerald-400"
              : isNegativeRet
              ? "text-rose-400"
              : "text-slate-400"
          }
        >
          {isPositiveRet ? "+" : ""}
          {(ret20 * 100).toFixed(1)}%
        </span>
      </td>
    </tr>
  );
});

// ─── Memoized Mobile Card Component (Grid-Isolated Columns) ──────────────────

interface MobileRowProps {
  cand: ScreenerCandidate;
  idx: number;
  isSelected: boolean;
  onSelect: (sym: string) => void;
}

const MobileScreenerRow = React.memo(function MobileScreenerRow({
  cand,
  idx,
  isSelected,
  onSelect,
}: MobileRowProps) {
  const ret20 = cand.ret_20d ?? cand.excess_ret_20d ?? 0.0;
  const isPositiveRet = ret20 > 0;
  const isNegativeRet = ret20 < 0;

  const score =
    cand.blended_score && cand.blended_score > 0
      ? cand.blended_score
      : cand.composite_score && cand.composite_score > 0
      ? cand.composite_score
      : null;

  return (
    <div
      onClick={() => onSelect(cand.symbol)}
      className={cn(
        "grid grid-cols-12 items-center gap-2 px-3 py-2.5 cursor-pointer text-xs font-mono transition-colors border-b border-white/[0.05]",
        isSelected
          ? "bg-cyan-950/40 text-white font-medium"
          : "text-slate-300 hover:bg-white/[0.03]"
      )}
    >
      {/* Cols 1–6 (Left - Instrument) */}
      <div className="col-span-6 min-w-0">
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className="text-[11px] font-mono text-slate-500">#{cand.rank || idx + 1}</span>
          <span className="text-sm font-bold text-slate-100">{cand.symbol}</span>
          {Boolean(cand.target_allocation_pct && cand.target_allocation_pct > 0) && (
            <span className="px-1.5 py-0.2 rounded text-[9px] font-mono font-bold bg-emerald-500/15 text-emerald-400">
              {cand.target_allocation_pct!.toFixed(1)}%
            </span>
          )}
        </div>
        <div className="text-xs text-slate-400 truncate mt-0.5 max-w-[170px]">
          {cand.company_name || cand.sector || "Equity"}
        </div>
      </div>

      {/* Cols 7–9 (Middle - Price & 20D Return, text-right) */}
      <div className="col-span-3 text-right tabular-nums">
        <div className="text-sm font-mono font-semibold text-slate-100">
          ₹{cand.close !== null ? cand.close.toFixed(2) : "—"}
        </div>
        <div
          className={cn(
            "text-[11px] font-mono font-medium",
            isPositiveRet ? "text-emerald-400" : isNegativeRet ? "text-rose-400" : "text-slate-400"
          )}
        >
          {isPositiveRet ? "+" : ""}
          {(ret20 * 100).toFixed(1)}%
        </div>
      </div>

      {/* Cols 10–12 (Right - Score Pill, flex justify-end) */}
      <div className="col-span-3 flex justify-end items-center">
        <div className="min-w-[48px] px-2 py-1 rounded-md bg-cyan-500/10 border border-cyan-500/30 text-center font-mono text-xs font-bold text-cyan-300">
          {score !== null ? score.toFixed(1) : "—"}
        </div>
      </div>
    </div>
  );
});

// ─── Main Screener Workspace ────────────────────────────────────────────────

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
  const [currentPage, setCurrentPage] = useState<number>(1);
  const pageSize = 50;

  const searchInputRef = useRef<HTMLInputElement>(null);

  // Instant Sector & Filter Counts across the entire candidate universe
  const filterCounts = useMemo(() => {
    const counts: Record<string, number> = {
      All: candidates.length,
      IT: 0,
      Energy: 0,
      Pharma: 0,
      Auto: 0,
      Financials: 0,
      "Capital Goods": 0,
      aboveSma200: 0,
      rebalanceTargets: 0,
    };
    for (const c of candidates) {
      if (matchSector(c, "IT")) counts.IT++;
      if (matchSector(c, "Energy")) counts.Energy++;
      if (matchSector(c, "Pharma")) counts.Pharma++;
      if (matchSector(c, "Auto")) counts.Auto++;
      if (matchSector(c, "Financials")) counts.Financials++;
      if (matchSector(c, "Capital Goods")) counts["Capital Goods"]++;
      if (c.price_above_sma200) counts.aboveSma200++;
      if (c.is_rebalance_target || (c.target_allocation_pct || 0) > 0) counts.rebalanceTargets++;
    }
    return counts;
  }, [candidates]);

  // 1. Filtered and Sorted Candidates (1,000 kept in memory for instant operations)
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
          return item.blended_score && item.blended_score > 0
            ? item.blended_score
            : item.composite_score && item.composite_score > 0
            ? item.composite_score
            : 0;
        }
        if (sortField === "ret_20d" || sortField === "excess_ret_20d") {
          return item.ret_20d ?? item.excess_ret_20d ?? 0.0;
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

  // Reset pagination to page 1 whenever search, filters, or sorting change
  useEffect(() => {
    setCurrentPage(1);
  }, [search, sectorFilter, sortField, sortAsc, minRoe, onlyAbove200Sma, onlyRebalanceTargets]);

  // Total pages and sliced 50 rows
  const totalPages = Math.max(1, Math.ceil(filteredCandidates.length / pageSize));
  const pagedCandidates = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    return filteredCandidates.slice(start, start + pageSize);
  }, [filteredCandidates, currentPage]);

  // Auto-advance page if selected symbol is on a different page
  useEffect(() => {
    if (selectedSymbol) {
      const idx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
      if (idx !== -1) {
        const targetPage = Math.floor(idx / pageSize) + 1;
        if (targetPage !== currentPage) {
          setCurrentPage(targetPage);
        }
      }
    }
  }, [selectedSymbol, filteredCandidates, currentPage]);

  // Arrow Up / Down and Vim j / k Scrub Navigation
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
      } else if (e.key === "ArrowUp" || e.key === "k") {
        e.preventDefault();
        const currIdx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
        const prevIdx = currIdx === -1 ? 0 : Math.max(currIdx - 1, 0);
        const targetSym = filteredCandidates[prevIdx].symbol;
        onSelectSymbol(targetSym);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filteredCandidates, selectedSymbol, onSelectSymbol]);

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
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#070b14] text-slate-100 select-none min-h-0">
      {/* Top Filter and Navigation Strip */}
      <div className="shrink-0 border-b border-white/[0.06] px-3.5 py-2.5 flex flex-wrap items-center justify-between gap-3 bg-[#050811]">
        {/* Left: View Mode Toggle & Search */}
        <div className="flex items-center gap-2.5 flex-1 min-w-[280px]">
          {onViewModeChange && (
            <div className="flex items-center p-0.5 rounded-lg bg-[#050811] border border-white/[0.06]">
              <button
                onClick={() => onViewModeChange("table")}
                className={cn(
                  "px-2.5 py-1 text-[11px] font-mono transition-colors rounded-md",
                  viewMode === "table"
                    ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-bold"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <TableIcon className="w-3 h-3" />
                  <span>Screener</span>
                </span>
              </button>

              <button
                onClick={() => onViewModeChange("heatmap")}
                className={cn(
                  "px-2.5 py-1 text-[11px] font-mono transition-colors rounded-md",
                  viewMode === "heatmap"
                    ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-bold"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                <span className="flex items-center gap-1.5">
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

      {/* Sector Filter Chips with Live Quantitative Counts */}
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
            {sec} ({filterCounts[sec] ?? 0})
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
          {">"} 200 SMA ({filterCounts.aboveSma200})
        </button>

        {/* Quick Filter: Rebalance Targets Only */}
        <button
          onClick={() => setOnlyRebalanceTargets(!onlyRebalanceTargets)}
          className={`px-2 py-0.5 rounded text-[11px] font-mono whitespace-nowrap transition-all flex items-center gap-1.5 ${
            onlyRebalanceTargets
              ? "bg-emerald-950/90 text-emerald-300 border border-emerald-500/50 shadow-[0_0_12px_rgba(16,185,129,0.3)] font-bold"
              : "text-slate-400 hover:text-emerald-300 hover:bg-slate-900/60 border border-transparent"
          }`}
          title="Filter Top Rebalance Allocation Targets"
        >
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
          <span>Rebalance Targets ({filterCounts.rebalanceTargets})</span>
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
          {/* Desktop Table View (hidden on mobile, block on lg:) */}
          <div className="hidden lg:flex flex-col flex-1 overflow-hidden min-h-0">
            {/* Desktop Table Header */}
            <div className="shrink-0 grid grid-cols-12 gap-2 px-3 py-2 border-b border-white/[0.08] bg-[#050811] text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-400">
              <div
                className="col-span-1 cursor-pointer flex items-center justify-center gap-1 hover:text-slate-200"
                onClick={() => handleSort("rank")}
              >
                <span>#</span>
                {sortField === "rank" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              <div
                className="col-span-4 cursor-pointer flex items-center gap-1 hover:text-slate-200"
                onClick={() => handleSort("symbol")}
              >
                <span>Ticker &amp; Instrument</span>
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
                title="Blended Multi-Horizon Score"
              >
                <span>Blended</span>
                {sortField === "blended_score" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              <div
                className="col-span-1 text-right cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
                onClick={() => handleSort("roe_pct")}
              >
                <span>ROE</span>
                {sortField === "roe_pct" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              <div
                className="col-span-2 text-right cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
                onClick={() => handleSort("ret_20d")}
              >
                <span>20D Ret</span>
                {(sortField === "ret_20d" || sortField === "excess_ret_20d") && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>
            </div>

            {/* Desktop Table Body (Strict 50 Rows) */}
            <div className="flex-1 overflow-y-auto">
              {loading && candidates.length === 0 ? (
                <div className="p-8 text-center text-slate-500 font-mono text-xs">
                  Loading universe screener...
                </div>
              ) : pagedCandidates.length === 0 ? (
                <div className="p-8 text-center text-slate-500 font-mono text-xs">
                  No equities match the selected criteria.
                </div>
              ) : (
                <table className="w-full border-collapse">
                  <tbody>
                    {pagedCandidates.map((cand, idx) => {
                      const globalIdx = (currentPage - 1) * pageSize + idx;
                      return (
                        <DesktopScreenerRow
                          key={cand.symbol}
                          cand={cand}
                          idx={globalIdx}
                          isSelected={cand.symbol === selectedSymbol}
                          onSelect={onSelectSymbol}
                        />
                      );
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Mobile Card-Row List View (block on mobile, hidden on lg:) */}
          <div className="block lg:hidden flex-1 overflow-y-auto divide-y divide-white/[0.06]">
            {/* Mobile Header Banner */}
            <div className="flex items-center justify-between px-3 py-1.5 text-[10px] font-mono text-slate-400 border-b border-white/[0.06] bg-[#020406] sticky top-0 z-10">
              <span>RANK · INSTRUMENT</span>
              <div className="flex items-center gap-6">
                <span>PRICE · 20D</span>
                <span>SCORE</span>
              </div>
            </div>

            {loading && candidates.length === 0 ? (
              <div className="p-8 text-center text-slate-500 font-mono text-xs">
                Loading universe screener...
              </div>
            ) : pagedCandidates.length === 0 ? (
              <div className="p-8 text-center text-slate-500 font-mono text-xs">
                No equities match the selected criteria.
              </div>
            ) : (
              pagedCandidates.map((cand, idx) => {
                const globalIdx = (currentPage - 1) * pageSize + idx;
                return (
                  <MobileScreenerRow
                    key={cand.symbol}
                    cand={cand}
                    idx={globalIdx}
                    isSelected={cand.symbol === selectedSymbol}
                    onSelect={onSelectSymbol}
                  />
                );
              })
            )}
          </div>

          {/* Compact 50-Row Pagination Bar (Pinned to Bottom) */}
          <div className="shrink-0 border-t border-white/[0.08] px-3.5 py-2 flex items-center justify-between text-xs font-mono bg-[#050811] text-slate-400">
            <span className="text-[11px] truncate">
              Showing{" "}
              <strong className="text-slate-200">
                {filteredCandidates.length === 0 ? 0 : (currentPage - 1) * pageSize + 1}–
                {Math.min(currentPage * pageSize, filteredCandidates.length)}
              </strong>{" "}
              of <strong className="text-cyan-400">{filteredCandidates.length}</strong> Equities
            </span>

            <div className="flex items-center gap-1.5 shrink-0">
              <button
                onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                disabled={currentPage <= 1}
                className="px-2 py-1 rounded bg-[#090d18] border border-white/[0.08] text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white/[0.05] transition-colors flex items-center gap-1 text-[11px]"
              >
                <ChevronLeft className="w-3 h-3" />
                <span className="hidden sm:inline">Prev</span>
              </button>

              <span className="px-2 py-0.5 rounded bg-black/40 border border-white/[0.06] text-cyan-300 text-[11px] font-bold">
                {currentPage} / {totalPages}
              </span>

              <button
                onClick={() => setCurrentPage((p) => Math.min(totalPages, p + 1))}
                disabled={currentPage >= totalPages}
                className="px-2 py-1 rounded bg-[#090d18] border border-white/[0.08] text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-white/[0.05] transition-colors flex items-center gap-1 text-[11px]"
              >
                <span className="hidden sm:inline">Next</span>
                <ChevronRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bottom Keyboard Navigation Hint Bar */}
      <div className="hidden sm:flex shrink-0 border-t border-white/[0.04] px-3.5 py-1.5 items-center justify-between text-[10px] font-mono text-slate-500 bg-[#020406]">
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
