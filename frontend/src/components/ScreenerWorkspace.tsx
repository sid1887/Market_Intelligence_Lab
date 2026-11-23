"use client";

import React, { useState, useMemo, useEffect, useRef } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useVirtualizer } from "@tanstack/react-virtual";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  SearchX,
  Table as TableIcon,
  LayoutGrid,
  Grid3X3,
  X,
  FilterX,
  ArrowUp,
  ArrowDown,
  SlidersHorizontal,
  Eye,
  Copy,
  Star,
  ExternalLink,
  Check,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { ScreenerCandidate, toggleWatchlist } from "@/lib/api";
import { ScreenerScoreCell } from "./ScreenerScoreCell";
import { SectorHeatmap } from "./SectorHeatmap";

export type SectorFilter = string;

export interface OptionalColumn {
  id: string;
  label: string;
  field: keyof ScreenerCandidate;
  width: string;
}

export const SCREENER_COLUMNS: OptionalColumn[] = [
  { id: "roe", label: "ROE", field: "roe_pct", width: "w-20" },
  { id: "ret20", label: "20D Ret", field: "ret_20d", width: "w-24" },
  { id: "deliv", label: "Deliv %", field: "delivery_pct", width: "w-20" },
  { id: "turnover", label: "Turn (Cr)", field: "turnover_cr", width: "w-28" },
  { id: "opm", label: "OPM", field: "opm_pct", width: "w-20" },
  { id: "de", label: "D/E", field: "debt_to_equity", width: "w-20" },
  { id: "score60", label: "60D Score", field: "score_60d", width: "w-24" },
  { id: "targetAlloc", label: "Target %", field: "target_allocation_pct", width: "w-20" },
];

export const DEFAULT_COLUMNS: Record<string, boolean> = {
  roe: true,
  ret20: true,
  deliv: true,
  turnover: true,
  opm: false,
  de: false,
  score60: false,
  targetAlloc: false,
};

export const SECTOR_FILTERS: string[] = [
  "All",
  "IT",
  "Energy",
  "Pharma",
  "Auto",
  "Financials",
  "Capital Goods",
  "FMCG",
  "Metals",
  "Chemicals",
  "Real Estate",
  "Construction Materials",
  "Telecom",
  "Media",
];

function matchSector(item: ScreenerCandidate, filter: string): boolean {
  if (filter === "All") return true;
  const sec = (item.sector || "").trim().toLowerCase();
  if (!sec || sec === "equities" || sec === "general" || sec === "unclassified") {
    return false;
  }
  const fLower = filter.toLowerCase();
  if (filter === "IT")
    return (
      sec === "it" ||
      sec.includes("tech") ||
      sec.includes("software") ||
      sec.includes("information technology") ||
      /\bit\b/.test(sec)
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
    return sec.includes("pharma") || sec.includes("health") || sec.includes("bio") || sec.includes("drug");
  if (filter === "Auto")
    return sec.includes("auto") || sec.includes("motor") || sec.includes("vehicle");
  if (filter === "Financials")
    return (
      sec.includes("financial") ||
      sec.includes("bank") ||
      sec.includes("insurance") ||
      sec.includes("nbfc") ||
      sec.includes("invest")
    );
  if (filter === "Capital Goods")
    return (
      sec.includes("capital") ||
      sec.includes("industrial") ||
      sec.includes("engineering") ||
      sec.includes("manufactur") ||
      sec.includes("equip")
    );
  if (filter === "FMCG")
    return (
      sec.includes("fmcg") ||
      sec.includes("consumer") ||
      sec.includes("food") ||
      sec.includes("beverag")
    );
  if (filter === "Metals")
    return (
      sec.includes("metal") ||
      sec.includes("steel") ||
      sec.includes("iron") ||
      sec.includes("mining") ||
      sec.includes("mineral")
    );
  if (filter === "Chemicals")
    return sec.includes("chem") || sec.includes("fertiliz");
  if (filter === "Real Estate")
    return sec.includes("realt") || sec.includes("estate") || sec.includes("infra") || sec.includes("construct");
  if (filter === "Construction Materials")
    return sec.includes("construction") || sec.includes("material") || sec.includes("cement") || sec.includes("ceramic");
  if (filter === "Telecom")
    return sec.includes("telecom") || sec.includes("communi");
  if (filter === "Media")
    return sec.includes("media") || sec.includes("entertain") || sec.includes("broadcast") || sec.includes("publish");
  return sec.includes(fLower);
}

export type ScreenerViewMode = "table" | "watchlist" | "heatmap" | "cards";

interface ScreenerWorkspaceProps {
  candidates: ScreenerCandidate[];
  selectedSymbol: string | null;
  onSelectSymbol: (symbol: string) => void;
  asOfDate?: string;
  loading?: boolean;
  viewMode?: ScreenerViewMode;
  onViewModeChange?: (mode: ScreenerViewMode) => void;
}

// ─── Memoized Desktop Row Component ─────────────────────────────────────────

interface DesktopRowProps {
  cand: ScreenerCandidate;
  idx: number;
  isSelected: boolean;
  onSelect: (sym: string) => void;
  columns: Record<string, boolean>;
  onContextMenu?: (e: React.MouseEvent, cand: ScreenerCandidate) => void;
  onMouseEnter?: (e: React.MouseEvent, cand: ScreenerCandidate) => void;
  onMouseLeave?: () => void;
}

const DesktopScreenerRow = React.memo(function DesktopScreenerRow({
  cand,
  idx,
  isSelected,
  onSelect,
  columns,
  onContextMenu,
  onMouseEnter,
  onMouseLeave,
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
    <div
      onClick={() => onSelect(cand.symbol)}
      onContextMenu={(e) => onContextMenu?.(e, cand)}
      onMouseEnter={(e) => onMouseEnter?.(e, cand)}
      onMouseLeave={onMouseLeave}
      className={cn(
        "flex items-center px-3 border-b border-white/[0.04] transition-colors text-xs font-mono select-none h-[52px] cursor-pointer",
        isSelected
          ? "bg-cyan-950/40 text-white font-medium shadow-[inset_0_0_15px_rgba(6,182,212,0.12)]"
          : "text-slate-300 hover:bg-white/[0.03] hover:text-white"
      )}
    >
      {/* 1. Rank */}
      <div className="w-12 text-slate-400 tabular-nums text-center shrink-0">
        {cand.rank || idx + 1}
      </div>

      {/* 2. Ticker & Name */}
      <div className="flex-1 min-w-[180px] min-w-0 pr-2">
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
              className="text-[8px] px-1 rounded bg-slate-900 text-slate-300 border border-white/[0.08]"
              title="Close > 200 SMA"
            >
              SMA
            </span>
          )}
        </div>
        <div className="text-[10px] text-slate-400 truncate max-w-[200px]">
          {cand.company_name}
        </div>
      </div>

      {/* 3. Close Price */}
      <div className="w-28 text-right tabular-nums shrink-0">
        <div className="font-semibold text-slate-100">
          {cand.close !== null ? `₹${cand.close.toFixed(2)}` : "—"}
        </div>
        {cand.sma_200 !== null && (
          <div className="text-[9px] text-slate-400">
            SMA: ₹{cand.sma_200.toFixed(2)}
          </div>
        )}
      </div>

      {/* 4. Blended Score */}
      <div className="w-28 text-right shrink-0 flex justify-end score-cell-reveal">
        {score !== null ? (
          <ScreenerScoreCell score={score} />
        ) : (
          <span className="text-slate-600">—</span>
        )}
      </div>

      {/* Optional Dynamic Columns */}
      {columns.roe && (
        <div className="hidden lg:block w-20 text-right tabular-nums text-slate-300 shrink-0">
          {cand.roe_pct !== null ? `${cand.roe_pct.toFixed(1)}%` : "—"}
        </div>
      )}

      {columns.ret20 && (
        <div className="w-24 text-right tabular-nums font-semibold shrink-0 pr-2">
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
        </div>
      )}

      {columns.deliv && (
        <div className="hidden lg:block w-20 text-right tabular-nums text-cyan-300 shrink-0">
          {cand.delivery_pct !== null && cand.delivery_pct !== undefined ? `${cand.delivery_pct.toFixed(1)}%` : "—"}
        </div>
      )}

      {columns.turnover && (
        <div className="hidden lg:block w-28 pr-2 text-right tabular-nums text-slate-300 shrink-0">
          {cand.turnover_cr !== null && cand.turnover_cr !== undefined ? `₹${cand.turnover_cr.toFixed(1)} Cr` : "—"}
        </div>
      )}

      {columns.opm && (
        <div className="hidden lg:block w-20 text-right tabular-nums text-slate-300 shrink-0">
          {cand.opm_pct !== null ? `${cand.opm_pct.toFixed(1)}%` : "—"}
        </div>
      )}

      {columns.de && (
        <div className="hidden lg:block w-20 text-right tabular-nums text-slate-300 shrink-0">
          {cand.debt_to_equity !== null ? cand.debt_to_equity.toFixed(2) : "—"}
        </div>
      )}

      {columns.score60 && (
        <div className="hidden lg:block w-24 text-right tabular-nums text-slate-300 shrink-0">
          {cand.score_60d !== null && cand.score_60d !== undefined
            ? cand.score_60d.toFixed(1)
            : "—"}
        </div>
      )}

      {columns.targetAlloc && (
        <div className="hidden lg:block w-20 text-right tabular-nums text-emerald-400 shrink-0 pr-2">
          {cand.target_allocation_pct
            ? `${cand.target_allocation_pct.toFixed(1)}%`
            : "—"}
        </div>
      )}
    </div>
  );
});

// ─── Memoized Mobile Card Component (Grid-Isolated Columns) ──────────────────

interface MobileRowProps {
  cand: ScreenerCandidate;
  idx: number;
  isSelected: boolean;
  onSelect: (sym: string) => void;
  onContextMenu?: (e: React.MouseEvent, cand: ScreenerCandidate) => void;
}

const MobileScreenerRow = React.memo(function MobileScreenerRow({
  cand,
  idx,
  isSelected,
  onSelect,
  onContextMenu,
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
      onContextMenu={(e) => onContextMenu?.(e, cand)}
      className={cn(
        "flex items-center justify-between px-3 h-[68px] cursor-pointer text-xs font-mono transition-colors border-b border-white/[0.05] select-none overflow-hidden",
        isSelected
          ? "bg-cyan-950/40 text-white font-medium"
          : "text-slate-300 hover:bg-white/[0.03]"
      )}
    >
      {/* Left - Instrument */}
      <div className="flex-1 min-w-0 pr-2">
        <div className="flex items-center gap-1.5 whitespace-nowrap overflow-hidden">
          <span className="text-[11px] font-mono text-slate-400 shrink-0">#{cand.rank || idx + 1}</span>
          <span className="text-sm font-bold text-slate-100 truncate">{cand.symbol}</span>
          {Boolean(cand.target_allocation_pct && cand.target_allocation_pct > 0) && (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0">
              {cand.target_allocation_pct!.toFixed(1)}%
            </span>
          )}
        </div>
        <span className="truncate block text-[11px] text-slate-400 mt-0.5 max-w-full">
          {cand.company_name || cand.sector || "Equity"}
        </span>
      </div>

      {/* Middle - Price & 20D Return, deterministic 88px */}
      <div className="w-[88px] text-right shrink-0 tabular-nums">
        <div className="text-xs sm:text-sm font-mono font-semibold text-slate-100 whitespace-nowrap">
          ₹{cand.close !== null ? cand.close.toFixed(2) : "—"}
        </div>
        <div
          className={cn(
            "text-[10px] sm:text-[11px] font-mono font-medium whitespace-nowrap",
            isPositiveRet ? "text-emerald-400" : isNegativeRet ? "text-rose-400" : "text-slate-400"
          )}
        >
          {isPositiveRet ? "+" : ""}
          {(ret20 * 100).toFixed(1)}%
        </div>
      </div>

      {/* Right - Score Pill, deterministic 52px */}
      <div className="w-[52px] flex justify-end shrink-0 items-center pl-1">
        <div className="min-w-[42px] px-1.5 py-0.5 rounded-md bg-cyan-500/10 border border-cyan-500/30 text-center font-mono text-xs font-bold text-cyan-300">
          {score !== null ? score.toFixed(1) : "—"}
        </div>
      </div>
    </div>
  );
});

// ─── Main Screener Workspace ────────────────────────────────────────────────

function ScreenerWorkspaceComponent({
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
  const [columns, setColumns] = useState<Record<string, boolean>>(DEFAULT_COLUMNS);
  const [showColumnPicker, setShowColumnPicker] = useState<boolean>(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem("mil:screener-columns");
      if (stored) setColumns(JSON.parse(stored));
    } catch {}
  }, []);

  const router = useRouter();
  const [hoveredCandidate, setHoveredCandidate] = useState<ScreenerCandidate | null>(null);
  const [hoverPosition, setHoverPosition] = useState<{ x: number; y: number } | null>(null);
  const hoverTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [contextMenu, setContextMenu] = useState<{
    x: number;
    y: number;
    cand: ScreenerCandidate;
  } | null>(null);
  const [copiedSymbol, setCopiedSymbol] = useState<string | null>(null);

  const handleRowMouseEnter = (e: React.MouseEvent, cand: ScreenerCandidate) => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    const rect = e.currentTarget.getBoundingClientRect();
    hoverTimerRef.current = setTimeout(() => {
      setHoveredCandidate(cand);
      setHoverPosition({
        x: Math.min(rect.left + 220, window.innerWidth - 300),
        y: Math.min(rect.top + 30, window.innerHeight - 200),
      });
    }, 350);
  };

  const handleRowMouseLeave = () => {
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    setHoveredCandidate(null);
    setHoverPosition(null);
  };

  const handleContextMenu = (e: React.MouseEvent, cand: ScreenerCandidate) => {
    e.preventDefault();
    e.stopPropagation();
    if (hoverTimerRef.current) clearTimeout(hoverTimerRef.current);
    setHoveredCandidate(null);
    const clickX = Math.min(e.clientX, window.innerWidth - 210);
    const clickY = Math.min(e.clientY, window.innerHeight - 220);
    setContextMenu({ x: clickX, y: clickY, cand });
  };

  useEffect(() => {
    const handleDismiss = () => setContextMenu(null);
    window.addEventListener("click", handleDismiss);
    window.addEventListener("scroll", handleDismiss, true);
    return () => {
      window.removeEventListener("click", handleDismiss);
      window.removeEventListener("scroll", handleDismiss, true);
    };
  }, []);

  const toggleColumn = (colId: string) => {
    setColumns((prev) => {
      const next = { ...prev, [colId]: !prev[colId] };
      try {
        localStorage.setItem("mil:screener-columns", JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  const searchInputRef = useRef<HTMLInputElement>(null);
  const desktopParentRef = useRef<HTMLDivElement>(null);
  const mobileParentRef = useRef<HTMLDivElement>(null);

  // Watchlist Count across candidate universe
  const watchlistCount = useMemo(() => {
    return candidates.filter((c) => Boolean(c.is_watchlist)).length;
  }, [candidates]);

  // Instant Sector & Filter Counts across the active universe pool
  const filterCounts = useMemo(() => {
    const baseList = viewMode === "watchlist" ? candidates.filter((c) => Boolean(c.is_watchlist)) : candidates;
    const counts: Record<string, number> = {
      All: baseList.length,
      aboveSma200: 0,
      rebalanceTargets: 0,
    };
    for (const sec of SECTOR_FILTERS) {
      if (sec !== "All") counts[sec] = 0;
    }
    for (const c of baseList) {
      for (const sec of SECTOR_FILTERS) {
        if (sec !== "All" && matchSector(c, sec)) {
          counts[sec] = (counts[sec] || 0) + 1;
        }
      }
      if (c.price_above_sma200) counts.aboveSma200++;
      if (c.is_rebalance_target || (c.target_allocation_pct || 0) > 0) counts.rebalanceTargets++;
    }
    return counts;
  }, [candidates, viewMode]);

  // Filtered and Sorted Candidates
  const filteredCandidates = useMemo(() => {
    const list = candidates.filter((item) => {
      if (viewMode === "watchlist" && !item.is_watchlist) {
        return false;
      }

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
  }, [candidates, viewMode, search, sectorFilter, sortField, sortAsc, minRoe, onlyAbove200Sma, onlyRebalanceTargets]);

  // TanStack Virtualizers for continuous 60fps scrolling
  const desktopVirtualizer = useVirtualizer({
    count: filteredCandidates.length,
    getScrollElement: () => desktopParentRef.current,
    estimateSize: () => 52,
    overscan: 12,
  });

  const mobileVirtualizer = useVirtualizer({
    count: filteredCandidates.length,
    getScrollElement: () => mobileParentRef.current,
    estimateSize: () => 68,
    overscan: 12,
  });

  // Auto-scroll virtual list to selected symbol if changed externally
  useEffect(() => {
    if (selectedSymbol) {
      const idx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
      if (idx !== -1) {
        desktopVirtualizer.scrollToIndex(idx, { align: "auto" });
        mobileVirtualizer.scrollToIndex(idx, { align: "auto" });
      }
    }
  }, [selectedSymbol, filteredCandidates, desktopVirtualizer, mobileVirtualizer]);

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

      const isPlainJ = e.key === "j" && !e.metaKey && !e.ctrlKey && !e.altKey;
      const isPlainK = e.key === "k" && !e.metaKey && !e.ctrlKey && !e.altKey;

      if (e.key === "ArrowDown" || isPlainJ) {
        e.preventDefault();
        const currIdx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
        const nextIdx = currIdx === -1 ? 0 : Math.min(currIdx + 1, filteredCandidates.length - 1);
        const targetSym = filteredCandidates[nextIdx].symbol;
        onSelectSymbol(targetSym);
        desktopVirtualizer.scrollToIndex(nextIdx, { align: "auto" });
        mobileVirtualizer.scrollToIndex(nextIdx, { align: "auto" });
      } else if (e.key === "ArrowUp" || isPlainK) {
        e.preventDefault();
        const currIdx = filteredCandidates.findIndex((c) => c.symbol === selectedSymbol);
        const prevIdx = currIdx === -1 ? 0 : Math.max(currIdx - 1, 0);
        const targetSym = filteredCandidates[prevIdx].symbol;
        onSelectSymbol(targetSym);
        desktopVirtualizer.scrollToIndex(prevIdx, { align: "auto" });
        mobileVirtualizer.scrollToIndex(prevIdx, { align: "auto" });
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filteredCandidates, selectedSymbol, onSelectSymbol, desktopVirtualizer, mobileVirtualizer]);

  // Restore UI filter & scroll state from sessionStorage
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const saved = sessionStorage.getItem("mil:screener-ui-state");
      if (saved) {
        const parsed = JSON.parse(saved);
        if (parsed.search !== undefined) setSearch(parsed.search);
        if (parsed.sectorFilter !== undefined) setSectorFilter(parsed.sectorFilter);
        if (parsed.sortField !== undefined) setSortField(parsed.sortField);
        if (parsed.sortAsc !== undefined) setSortAsc(parsed.sortAsc);
        if (parsed.minRoe !== undefined) setMinRoe(parsed.minRoe);
        if (parsed.onlyAbove200Sma !== undefined) setOnlyAbove200Sma(parsed.onlyAbove200Sma);
        if (parsed.onlyRebalanceTargets !== undefined) setOnlyRebalanceTargets(parsed.onlyRebalanceTargets);
        if (parsed.scrollTop && desktopParentRef.current) {
          desktopParentRef.current.scrollTop = parsed.scrollTop;
        }
      }
    } catch {}
  }, []);

  // Save UI filter state to sessionStorage
  useEffect(() => {
    if (typeof window === "undefined") return;
    try {
      const stateToSave = {
        search,
        sectorFilter,
        sortField,
        sortAsc,
        minRoe,
        onlyAbove200Sma,
        onlyRebalanceTargets,
        scrollTop: desktopParentRef.current?.scrollTop || 0,
      };
      sessionStorage.setItem("mil:screener-ui-state", JSON.stringify(stateToSave));
    } catch {}
  }, [search, sectorFilter, sortField, sortAsc, minRoe, onlyAbove200Sma, onlyRebalanceTargets]);

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

  const renderEmptyState = (compact = false) => {
    if (viewMode === "watchlist") {
      return (
        <div className={cn("flex flex-col items-center justify-center text-center font-mono text-xs gap-3 select-none", compact ? "p-6" : "p-12")}>
          <div className="w-12 h-12 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center shadow-[0_0_20px_rgba(245,158,11,0.15)]">
            <Star className="w-6 h-6 text-amber-400 fill-amber-400/20" />
          </div>
          <div className="text-slate-200 font-semibold text-sm">Your Wishlist is Empty</div>
          <p className="text-slate-400 max-w-sm text-xs leading-relaxed">
            Star any stock in the Screener, Cards, or Stock Inspector to track your highest-conviction ideas here.
          </p>
          {onViewModeChange && (
            <button
              onClick={() => onViewModeChange("table")}
              className="mt-2 px-3 py-1.5 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-mono text-xs transition-colors flex items-center gap-1.5"
            >
              <TableIcon className="w-3.5 h-3.5" />
              <span>Browse All Screener Equities</span>
            </button>
          )}
        </div>
      );
    }
    return (
      <div className={cn("flex flex-col items-center justify-center text-center text-slate-500 font-mono text-xs gap-3", compact ? "p-6" : "p-12")}>
        <SearchX className="w-8 h-8 text-slate-600 animate-pulse" />
        <span>No equities match the selected criteria.</span>
      </div>
    );
  };

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#070b14] text-slate-100 select-none min-h-0">
      {/* Top Filter and Navigation Strip (2-Row Responsive Layout) */}
      <div className="shrink-0 border-b border-white/[0.06] px-3.5 py-2 flex flex-col gap-2 bg-[#050811]">
        {/* Row 1: View Mode Switcher on Left, Columns/Session/Equities on Right */}
        <div className="flex items-center justify-between gap-2 w-full">
          {onViewModeChange && (
            <div className="flex items-center p-0.5 rounded-lg bg-[#070b14] border border-white/[0.06] shrink-0">
              <button
                onClick={() => onViewModeChange("table")}
                aria-label="Table view mode"
                className={cn(
                  "px-2 sm:px-2.5 py-1 text-[11px] font-mono transition-colors rounded-md",
                  viewMode === "table"
                    ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-bold shadow-[0_0_10px_rgba(6,182,212,0.15)]"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <TableIcon className="w-3 h-3" />
                  <span className="hidden sm:inline">Screener</span>
                </span>
              </button>

              <button
                onClick={() => onViewModeChange("watchlist")}
                aria-label="Wishlist view mode"
                className={cn(
                  "px-2 sm:px-2.5 py-1 text-[11px] font-mono transition-colors rounded-md relative",
                  viewMode === "watchlist"
                    ? "bg-amber-500/15 border border-amber-500/30 text-amber-300 font-bold shadow-[0_0_12px_rgba(245,158,11,0.2)]"
                    : "text-slate-400 hover:text-amber-200"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <Star className={cn("w-3 h-3", viewMode === "watchlist" ? "text-amber-400 fill-amber-400" : "text-amber-400/80")} />
                  <span className="hidden sm:inline">Wishlist</span>
                  {watchlistCount > 0 && (
                    <span
                      className={cn(
                        "text-[9px] font-mono px-1 py-0.2 rounded-full font-bold",
                        viewMode === "watchlist"
                          ? "bg-amber-400 text-black"
                          : "bg-amber-500/20 text-amber-300 border border-amber-500/30"
                      )}
                    >
                      {watchlistCount}
                    </span>
                  )}
                </span>
              </button>

              <button
                onClick={() => onViewModeChange("heatmap")}
                aria-label="Heatmap view mode"
                className={cn(
                  "px-2 sm:px-2.5 py-1 text-[11px] font-mono transition-colors rounded-md",
                  viewMode === "heatmap"
                    ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-bold shadow-[0_0_10px_rgba(6,182,212,0.15)]"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <LayoutGrid className="w-3 h-3" />
                  <span className="hidden sm:inline">Heatmap</span>
                </span>
              </button>

              <button
                onClick={() => onViewModeChange("cards")}
                aria-label="Cards view mode"
                className={cn(
                  "px-2 sm:px-2.5 py-1 text-[11px] font-mono transition-colors rounded-md",
                  viewMode === "cards"
                    ? "bg-cyan-500/15 border border-cyan-500/30 text-cyan-300 font-bold shadow-[0_0_10px_rgba(6,182,212,0.15)]"
                    : "text-slate-400 hover:text-slate-200"
                )}
              >
                <span className="flex items-center gap-1.5">
                  <Grid3X3 className="w-3 h-3" />
                  <span className="hidden sm:inline">Cards</span>
                </span>
              </button>
            </div>
          )}

          {/* Right: Column Picker, As of Date & Candidate Count */}
          <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400 shrink-0">
            <div className="relative">
              <button
                onClick={() => setShowColumnPicker((v) => !v)}
                className={cn(
                  "flex items-center gap-1.5 px-2 py-1 rounded text-[11px] font-mono border transition-colors",
                  showColumnPicker
                    ? "bg-cyan-950/80 text-cyan-300 border-cyan-500/40"
                    : "bg-slate-900 border-white/[0.08] text-slate-400 hover:text-slate-200 hover:border-white/[0.15]"
                )}
                title="Customize Screener Table Columns"
              >
                <SlidersHorizontal className="w-3 h-3 text-cyan-400" />
                <span className="hidden sm:inline">Columns</span>
              </button>
              {showColumnPicker && (
                <div className="absolute right-0 mt-1.5 w-44 bg-[#0a0e17] border border-white/[0.12] rounded-xl shadow-2xl p-2 z-40 space-y-1">
                  <div className="text-[10px] font-mono text-slate-400 uppercase tracking-wider px-1 pb-1 border-b border-white/[0.06] flex justify-between items-center">
                    <span>Columns</span>
                    <button
                      onClick={() => {
                        setColumns(DEFAULT_COLUMNS);
                        try {
                          localStorage.setItem("mil:screener-columns", JSON.stringify(DEFAULT_COLUMNS));
                        } catch {}
                      }}
                      className="text-cyan-400 hover:text-cyan-300 text-[10px]"
                    >
                      Reset
                    </button>
                  </div>
                  {SCREENER_COLUMNS.map((col) => (
                    <label
                      key={col.id}
                      className="flex items-center justify-between px-2 py-1 rounded text-xs font-mono text-slate-300 hover:bg-white/[0.04] cursor-pointer"
                    >
                      <span>{col.label}</span>
                      <input
                        type="checkbox"
                        checked={Boolean(columns[col.id])}
                        onChange={() => toggleColumn(col.id)}
                        className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0 focus:ring-offset-0 cursor-pointer"
                      />
                    </label>
                  ))}
                </div>
              )}
            </div>

            {asOfDate && (
              <span className="hidden sm:inline px-2 py-1 rounded bg-slate-900 border border-white/[0.06] text-slate-400">
                <span className="text-slate-500">Session: </span>
                <strong className="text-slate-200">{asOfDate}</strong>
              </span>
            )}
            <span className="px-2 py-1 rounded bg-slate-900 border border-white/[0.06] text-slate-400">
              <strong className={viewMode === "watchlist" ? "text-amber-400" : "text-cyan-400"}>
                {filteredCandidates.length}
              </strong>
              <span className="hidden sm:inline text-slate-500"> / {candidates.length}</span>
              <span className="text-slate-400">{viewMode === "watchlist" ? " in Wishlist" : " Equities"}</span>
            </span>
          </div>
        </div>

        {/* Row 2: Full-Width Search Input */}
        <div className="relative w-full">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-500" />
          <input
            ref={searchInputRef}
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={
              viewMode === "watchlist"
                ? "Search in your wishlist (e.g. BSE, RVNL, GAIL)..."
                : "Search ticker, company name, sector (e.g. RELIANCE, Tata, Pharma)..."
            }
            aria-label="Filter tickers, company names, or sectors"
            className="w-full bg-[#070b14] border border-white/[0.08] focus:border-cyan-500/60 rounded-md pl-8 pr-7 py-1.5 text-xs font-mono text-slate-200 placeholder-slate-500 focus:outline-none transition-all"
          />
          {search && (
            <button
              onClick={() => setSearch("")}
              aria-label="Clear search"
              className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
            >
              <X className="w-3 h-3" />
            </button>
          )}
        </div>
      </div>

      {/* Sector Filter Chips with Live Quantitative Counts */}
      <div className="h-9 shrink-0 border-b border-white/[0.04] px-3.5 flex items-center gap-1.5 overflow-x-auto overflow-y-hidden thin-scrollbar bg-[#020406]">
        {SECTOR_FILTERS.map((sec) => (
          <button
            key={sec}
            onClick={() => setSectorFilter(sec)}
            className={`relative px-2.5 py-0.5 rounded text-[11px] font-mono whitespace-nowrap transition-colors ${
              sectorFilter === sec
                ? "text-cyan-300 font-semibold"
                : "text-slate-400 hover:text-slate-200 hover:bg-slate-900/60"
            }`}
          >
            {sectorFilter === sec && (
              <motion.div
                layoutId="screener-sector-pill"
                className="absolute inset-0 bg-cyan-950/80 border border-cyan-500/40 rounded shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                transition={{ type: "spring", stiffness: 400, damping: 30 }}
              />
            )}
            <span className="relative z-10">
              {sec} ({filterCounts[sec] ?? 0})
            </span>
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

        <div className="h-3 w-[1px] bg-white/[0.08] mx-1 shrink-0" />

        {/* Min ROE % Input (H3) */}
        <div className="flex items-center gap-1 bg-[#050811] border border-white/[0.08] px-2 py-0.5 rounded text-[11px] font-mono text-slate-300 shrink-0">
          <span className="text-[10px] text-slate-400">Min ROE:</span>
          <input
            type="number"
            min="0"
            max="100"
            placeholder="0"
            aria-label="Minimum ROE percentage"
            value={minRoe !== null ? minRoe : ""}
            onChange={(e) => setMinRoe(e.target.value ? Math.max(0, parseFloat(e.target.value)) : null)}
            className="w-9 bg-transparent text-right text-cyan-300 font-bold focus:outline-none tabular-nums placeholder-slate-600"
          />
          <span className="text-[10px] text-slate-500">%</span>
          {minRoe !== null && (
            <button
              onClick={() => setMinRoe(null)}
              aria-label="Clear Min ROE filter"
              className="text-slate-500 hover:text-slate-200 text-xs leading-none ml-0.5"
              title="Clear Min ROE"
            >
              ×
            </button>
          )}
        </div>

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

      {/* Main Content: Heatmap, Cards Grid, or Virtualized Table */}
      <AnimatePresence mode="wait">
        {viewMode === "heatmap" ? (
          <motion.div
            key="heatmap"
            initial={{ opacity: 0, scale: 0.98 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.22, ease: [0.16, 1, 0.3, 1] }}
            className="flex-1 overflow-y-auto p-4 min-h-0"
          >
            <SectorHeatmap
              candidates={candidates}
              activeSymbol={selectedSymbol || ""}
              onSelect={onSelectSymbol}
            />
          </motion.div>
        ) : viewMode === "cards" ? (
          <motion.div
            key="cards"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
            className="flex-1 overflow-y-auto p-4 min-h-0"
          >
            {loading && candidates.length === 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 animate-pulse">
                {Array.from({ length: 12 }).map((_, i) => (
                  <div key={i} className="h-36 rounded-xl bg-white/[0.03] border border-white/[0.06]" />
                ))}
              </div>
            ) : filteredCandidates.length === 0 ? (
              renderEmptyState()
            ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {filteredCandidates.map((cand, idx) => {
                const isSelected = selectedSymbol === cand.symbol;
                const ret20 = cand.ret_20d ?? cand.excess_ret_20d ?? 0.0;
                const score = cand.blended_score && cand.blended_score > 0 ? cand.blended_score : cand.composite_score;
                return (
                  <div
                    key={cand.symbol}
                    onClick={() => onSelectSymbol(cand.symbol)}
                    onContextMenu={(e) => handleContextMenu(e, cand)}
                    className={cn(
                      "p-3.5 rounded-xl border transition-all cursor-pointer group flex flex-col justify-between select-none relative overflow-hidden",
                      isSelected
                        ? "bg-cyan-950/40 border-cyan-500/50 shadow-[0_0_20px_rgba(6,182,212,0.15)]"
                        : "bg-[#070b14] hover:bg-[#0c1220] border-white/[0.06] hover:border-white/[0.12]"
                    )}
                  >
                    {/* Top Row: Symbol, Rank, Price */}
                    <div className="flex items-start justify-between gap-2 mb-2">
                      <div>
                        <div className="flex items-center gap-1.5">
                          <span className="font-bold text-sm text-slate-100 group-hover:text-cyan-300 transition-colors">
                            {cand.symbol}
                          </span>
                          <span className="text-[9px] px-1 py-0.2 rounded bg-white/[0.04] text-slate-400 font-mono">
                            #{cand.rank || idx + 1}
                          </span>
                          {cand.is_watchlist && (
                            <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
                          )}
                        </div>
                        <div className="text-[10px] text-slate-400 truncate max-w-[150px]">
                          {cand.company_name}
                        </div>
                      </div>

                      <div className="text-right">
                        <div className="font-bold text-sm text-slate-100 tabular-nums">
                          {cand.close !== null ? `₹${cand.close.toFixed(2)}` : "—"}
                        </div>
                        <span
                          className={cn(
                            "text-[10px] font-mono font-bold",
                            ret20 > 0 ? "text-emerald-400" : ret20 < 0 ? "text-rose-400" : "text-slate-400"
                          )}
                        >
                          {ret20 > 0 ? "+" : ""}
                          {(ret20 * 100).toFixed(1)}% 20D
                        </span>
                      </div>
                    </div>

                    {/* Factor Metrics Mini-Strip */}
                    <div className="grid grid-cols-3 gap-1.5 py-2 my-1 border-y border-white/[0.04] text-[10px] font-mono">
                      <div>
                        <span className="text-slate-500 block text-[9px]">ROE</span>
                        <span className="text-slate-200 font-semibold">{cand.roe_pct !== null ? `${cand.roe_pct.toFixed(1)}%` : "—"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[9px]">D/E</span>
                        <span className="text-slate-200 font-semibold">{cand.debt_to_equity !== null ? cand.debt_to_equity.toFixed(2) : "—"}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block text-[9px]">SMA 200</span>
                        <span className={cand.price_above_sma200 ? "text-emerald-400 font-semibold" : "text-slate-400"}>
                          {cand.price_above_sma200 ? "Above" : "Below"}
                        </span>
                      </div>
                    </div>

                    {/* Bottom Row: Score Progress Bar & Quick Actions */}
                    <div className="flex items-center justify-between pt-1 gap-2">
                      <div className="flex-1">
                        <div className="flex items-center justify-between text-[9px] font-mono text-slate-400 mb-1">
                          <span>Conviction</span>
                          <span className="font-bold text-cyan-400">{score ? score.toFixed(0) : "—"}/100</span>
                        </div>
                        <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden border border-white/[0.06]">
                          <div
                            className="h-full bg-gradient-to-r from-cyan-500 to-emerald-400 rounded-full"
                            style={{ width: `${Math.min(100, Math.max(0, score || 0))}%` }}
                          />
                        </div>
                      </div>

                      <Link
                        href={`/stocks/${cand.symbol}`}
                        onClick={(e) => e.stopPropagation()}
                        className="p-1 rounded text-slate-500 hover:text-cyan-300 hover:bg-white/[0.05] transition-colors"
                        title="Open full tearsheet"
                      >
                        <ExternalLink className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </motion.div>
      ) : (
        <motion.div
          key="table"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          className="flex-1 flex flex-col overflow-hidden min-h-0 h-full"
        >
          {/* Desktop Virtual Table View (hidden on mobile, flex on md:) */}
          <div className="hidden md:flex flex-col flex-1 overflow-hidden min-h-0">
            {/* Fixed Sticky Header */}
            <div className="shrink-0 flex items-center px-3 py-2 border-b border-white/[0.08] bg-[#060a12] sticky top-0 z-20 text-[10px] font-mono font-semibold uppercase tracking-wider text-slate-400">
              <div
                role="columnheader"
                tabIndex={0}
                aria-label="Sort by rank"
                aria-sort={sortField === "rank" ? (sortAsc ? "ascending" : "descending") : "none"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleSort("rank");
                  }
                }}
                className="w-12 text-center shrink-0 cursor-pointer flex items-center justify-center gap-1 hover:text-slate-200"
                onClick={() => handleSort("rank")}
              >
                <span>#</span>
                {sortField === "rank" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              <div
                role="columnheader"
                tabIndex={0}
                aria-label="Sort by symbol"
                aria-sort={sortField === "symbol" ? (sortAsc ? "ascending" : "descending") : "none"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleSort("symbol");
                  }
                }}
                className="flex-1 min-w-[180px] cursor-pointer flex items-center gap-1 hover:text-slate-200"
                onClick={() => handleSort("symbol")}
              >
                <span>Ticker &amp; Instrument</span>
                {sortField === "symbol" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              <div
                role="columnheader"
                tabIndex={0}
                aria-label="Sort by close price"
                aria-sort={sortField === "close" ? (sortAsc ? "ascending" : "descending") : "none"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleSort("close");
                  }
                }}
                className="w-28 text-right shrink-0 cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
                onClick={() => handleSort("close")}
              >
                <span>Close</span>
                {sortField === "close" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              <div
                role="columnheader"
                tabIndex={0}
                aria-label="Sort by blended score"
                aria-sort={sortField === "blended_score" ? (sortAsc ? "ascending" : "descending") : "none"}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    handleSort("blended_score");
                  }
                }}
                className="w-28 text-right shrink-0 cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200"
                onClick={() => handleSort("blended_score")}
                title="Blended Multi-Horizon Score"
              >
                <span>Blended</span>
                {sortField === "blended_score" && (
                  sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                )}
              </div>

              {/* Dynamic Optional Column Headers */}
              {columns.roe && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by ROE"
                  aria-sort={sortField === "roe_pct" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("roe_pct");
                    }
                  }}
                  className="hidden lg:flex w-20 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200"
                  onClick={() => handleSort("roe_pct")}
                >
                  <span>ROE</span>
                  {sortField === "roe_pct" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.ret20 && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by 20D return"
                  aria-sort={(sortField === "ret_20d" || sortField === "excess_ret_20d") ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("ret_20d");
                    }
                  }}
                  className="w-24 text-right shrink-0 cursor-pointer flex items-center justify-end gap-1 hover:text-slate-200 pr-2"
                  onClick={() => handleSort("ret_20d")}
                >
                  <span>20D Ret</span>
                  {(sortField === "ret_20d" || sortField === "excess_ret_20d") && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.deliv && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by Delivery Percentage"
                  aria-sort={sortField === "delivery_pct" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("delivery_pct");
                    }
                  }}
                  className="hidden lg:flex w-20 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200"
                  onClick={() => handleSort("delivery_pct")}
                >
                  <span>Deliv %</span>
                  {sortField === "delivery_pct" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.turnover && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by Turnover in Crores"
                  aria-sort={sortField === "turnover_cr" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("turnover_cr");
                    }
                  }}
                  className="hidden lg:flex w-28 pr-2 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200"
                  onClick={() => handleSort("turnover_cr")}
                >
                  <span>Turn (Cr)</span>
                  {sortField === "turnover_cr" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.opm && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by OPM"
                  aria-sort={sortField === "opm_pct" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("opm_pct");
                    }
                  }}
                  className="hidden lg:flex w-20 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200"
                  onClick={() => handleSort("opm_pct")}
                >
                  <span>OPM</span>
                  {sortField === "opm_pct" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.de && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by Debt to Equity"
                  aria-sort={sortField === "debt_to_equity" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("debt_to_equity");
                    }
                  }}
                  className="hidden lg:flex w-20 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200"
                  onClick={() => handleSort("debt_to_equity")}
                >
                  <span>D/E</span>
                  {sortField === "debt_to_equity" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.score60 && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by 60D score"
                  aria-sort={sortField === "score_60d" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("score_60d");
                    }
                  }}
                  className="hidden lg:flex w-28 pr-2 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200"
                  onClick={() => handleSort("score_60d")}
                >
                  <span>60D Score</span>
                  {sortField === "score_60d" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}

              {columns.targetAlloc && (
                <div
                  role="columnheader"
                  tabIndex={0}
                  aria-label="Sort by target allocation percentage"
                  aria-sort={sortField === "target_allocation_pct" ? (sortAsc ? "ascending" : "descending") : "none"}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      handleSort("target_allocation_pct");
                    }
                  }}
                  className="hidden lg:flex w-20 text-right shrink-0 cursor-pointer items-center justify-end gap-1 hover:text-slate-200 pr-2"
                  onClick={() => handleSort("target_allocation_pct")}
                >
                  <span>Target %</span>
                  {sortField === "target_allocation_pct" && (
                    sortAsc ? <ArrowUp className="w-2.5 h-2.5 text-cyan-400" /> : <ArrowDown className="w-2.5 h-2.5 text-cyan-400" />
                  )}
                </div>
              )}
            </div>

            {/* Desktop Virtualized Scroll Area */}
            <div ref={desktopParentRef} className="flex-1 overflow-y-auto min-h-0 relative">
              {loading && candidates.length === 0 ? (
                <div className="divide-y divide-white/[0.04] animate-pulse">
                  {Array.from({ length: 12 }).map((_, i) => (
                    <div key={i} className="flex items-center px-3 h-[52px]">
                      <div className="w-12 flex justify-center">
                        <div className="w-5 h-4 bg-white/[0.06] rounded" />
                      </div>
                      <div className="flex-1 min-w-[180px] pr-2 space-y-1.5">
                        <div className="w-24 h-3.5 bg-white/[0.08] rounded" />
                        <div className="w-36 h-2.5 bg-white/[0.04] rounded" />
                      </div>
                      <div className="w-28 flex flex-col items-end space-y-1">
                        <div className="w-16 h-3.5 bg-white/[0.08] rounded" />
                        <div className="w-12 h-2.5 bg-white/[0.04] rounded" />
                      </div>
                      <div className="w-28 flex justify-end">
                        <div className="w-16 h-5 bg-white/[0.06] rounded-md" />
                      </div>
                      {columns.roe && (
                        <div className="hidden lg:flex w-20 justify-end">
                          <div className="w-10 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.ret20 && (
                        <div className="w-24 flex justify-end pr-2">
                          <div className="w-12 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.deliv && (
                        <div className="hidden lg:flex w-20 justify-end">
                          <div className="w-10 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.turnover && (
                        <div className="hidden lg:flex w-24 justify-end">
                          <div className="w-12 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.opm && (
                        <div className="hidden lg:flex w-20 justify-end">
                          <div className="w-10 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.de && (
                        <div className="hidden lg:flex w-20 justify-end">
                          <div className="w-10 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.score60 && (
                        <div className="hidden lg:flex w-24 justify-end">
                          <div className="w-12 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                      {columns.targetAlloc && (
                        <div className="hidden lg:flex w-20 justify-end pr-2">
                          <div className="w-10 h-3.5 bg-white/[0.06] rounded" />
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              ) : filteredCandidates.length === 0 ? (
                renderEmptyState()
              ) : (
                <div
                  style={{
                    height: `${desktopVirtualizer.getTotalSize()}px`,
                    width: "100%",
                    position: "relative",
                  }}
                >
                  {desktopVirtualizer.getVirtualItems().map((virtualRow) => {
                    const cand = filteredCandidates[virtualRow.index];
                    return (
                      <div
                        key={cand.symbol}
                        style={{
                          position: "absolute",
                          top: 0,
                          left: 0,
                          width: "100%",
                          height: `${virtualRow.size}px`,
                          transform: `translateY(${virtualRow.start}px)`,
                        }}
                      >
                        <DesktopScreenerRow
                          cand={cand}
                          idx={virtualRow.index}
                          isSelected={cand.symbol === selectedSymbol}
                          onSelect={onSelectSymbol}
                          columns={columns}
                          onContextMenu={handleContextMenu}
                          onMouseEnter={handleRowMouseEnter}
                          onMouseLeave={handleRowMouseLeave}
                        />
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>

          {/* Mobile Card-Row List View (block on mobile, hidden on md:) */}
          <div ref={mobileParentRef} className="block md:hidden flex-1 overflow-y-auto min-h-0 relative">
            {/* Mobile Header Banner */}
            <div className="flex items-center justify-between px-3 py-1.5 text-[10px] font-mono text-slate-400 border-b border-white/[0.06] bg-[#020406] sticky top-0 z-10">
              <span>RANK · INSTRUMENT</span>
              <div className="flex items-center gap-6">
                <span>PRICE · 20D</span>
                <span>SCORE</span>
              </div>
            </div>

            {loading && candidates.length === 0 ? (
              <div className="divide-y divide-white/[0.04] animate-pulse">
                {Array.from({ length: 8 }).map((_, i) => (
                  <div key={i} className="p-3.5 flex items-center justify-between">
                    <div className="space-y-1.5">
                      <div className="w-20 h-4 bg-white/[0.08] rounded" />
                      <div className="w-32 h-2.5 bg-white/[0.04] rounded" />
                    </div>
                    <div className="flex items-center gap-3">
                      <div className="w-14 h-4 bg-white/[0.08] rounded" />
                      <div className="w-12 h-5 bg-white/[0.06] rounded" />
                    </div>
                  </div>
                ))}
              </div>
            ) : filteredCandidates.length === 0 ? (
              renderEmptyState(true)
            ) : (
              <div
                style={{
                  height: `${mobileVirtualizer.getTotalSize()}px`,
                  width: "100%",
                  position: "relative",
                }}
              >
                {mobileVirtualizer.getVirtualItems().map((virtualRow) => {
                  const cand = filteredCandidates[virtualRow.index];
                  return (
                    <div
                      key={cand.symbol}
                      style={{
                        position: "absolute",
                        top: 0,
                        left: 0,
                        width: "100%",
                        height: `${virtualRow.size}px`,
                        transform: `translateY(${virtualRow.start}px)`,
                      }}
                    >
                      <MobileScreenerRow
                        cand={cand}
                        idx={virtualRow.index}
                        isSelected={cand.symbol === selectedSymbol}
                        onSelect={onSelectSymbol}
                        onContextMenu={handleContextMenu}
                      />
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Continuous Virtualization Footer Status Strip */}
          <div className="shrink-0 border-t border-white/[0.08] px-3.5 py-2 flex items-center justify-between text-xs font-mono bg-[#050811] text-slate-400">
            <span className="text-[11px] truncate">
              Virtual Grid: <strong className="text-cyan-400">{filteredCandidates.length}</strong> / {candidates.length} Equities loaded
            </span>
            <span className="text-[10px] text-slate-500 hidden sm:inline">
              60 FPS TanStack Virtualization
            </span>
          </div>
        </motion.div>
      )}
      </AnimatePresence>

      {/* Bottom Keyboard Navigation Hint Bar */}
      <div className="hidden md:flex shrink-0 border-t border-white/[0.04] px-3.5 py-1.5 items-center justify-between text-[10px] font-mono text-slate-500 bg-[#020406]">
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

      {/* ─── L2: Floating Row Hover Preview Popover ─────────────────────────── */}
      {hoveredCandidate && hoverPosition && (
        <div
          style={{ left: hoverPosition.x, top: hoverPosition.y }}
          className="fixed z-50 w-72 p-3 rounded-xl bg-[#080d1a]/95 border border-cyan-500/40 shadow-[0_10px_35px_rgba(0,0,0,0.85),0_0_15px_rgba(6,182,212,0.2)] backdrop-blur-xl pointer-events-none text-xs font-mono animate-in fade-in zoom-in-95 duration-100"
        >
          <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-white/[0.08]">
            <div>
              <span className="font-bold text-slate-100 text-sm">{hoveredCandidate.symbol}</span>
              <span className="text-[10px] text-slate-400 block truncate max-w-[150px]">{hoveredCandidate.company_name}</span>
            </div>
            <div className="text-right">
              <span className="font-bold text-slate-100">₹{hoveredCandidate.close?.toFixed(2) ?? "—"}</span>
              <span className="text-[9px] text-cyan-400 block">{hoveredCandidate.sector || "Equities"}</span>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px] py-1">
            <div>
              <span className="text-slate-500">20D Return:</span>{" "}
              <strong className={(hoveredCandidate.ret_20d ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}>
                {((hoveredCandidate.ret_20d ?? 0) * 100).toFixed(1)}%
              </strong>
            </div>
            <div>
              <span className="text-slate-500">ROE:</span>{" "}
              <strong className="text-slate-200">{hoveredCandidate.roe_pct?.toFixed(1) ?? "—"}%</strong>
            </div>
            <div>
              <span className="text-slate-500">200 SMA:</span>{" "}
              <strong className={hoveredCandidate.price_above_sma200 ? "text-emerald-400" : "text-rose-400"}>
                {hoveredCandidate.price_above_sma200 ? "Above" : "Below"}
              </strong>
            </div>
            <div>
              <span className="text-slate-500">Score:</span>{" "}
              <strong className="text-cyan-300">{hoveredCandidate.blended_score?.toFixed(0) ?? "—"}/100</strong>
            </div>
          </div>
        </div>
      )}

      {/* ─── L3: Right-Click Context Menu ───────────────────────────────────── */}
      {contextMenu && (
        <div
          style={{ left: contextMenu.x, top: contextMenu.y }}
          className="fixed z-50 w-52 py-1.5 rounded-xl bg-[#080d1a] border border-cyan-500/40 shadow-[0_10px_35px_rgba(0,0,0,0.85),0_0_15px_rgba(6,182,212,0.25)] backdrop-blur-xl text-xs font-mono animate-in fade-in zoom-in-95 duration-100"
          onClick={(e) => e.stopPropagation()}
        >
          <div className="px-3 py-1 pb-1.5 border-b border-white/[0.08] text-[10px] text-cyan-400 font-bold flex items-center justify-between">
            <span>{contextMenu.cand.symbol}</span>
            <span className="text-slate-500">₹{contextMenu.cand.close?.toFixed(1) ?? "—"}</span>
          </div>

          <button
            onClick={() => {
              onSelectSymbol(contextMenu.cand.symbol);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-left text-slate-200 hover:text-cyan-300 hover:bg-white/[0.05] flex items-center gap-2 transition-colors"
          >
            <Eye className="w-3.5 h-3.5 text-cyan-400" />
            <span>Inspect Stock</span>
          </button>

          <button
            onClick={() => {
              router.push(`/stocks/${contextMenu.cand.symbol}`);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-left text-slate-200 hover:text-cyan-300 hover:bg-white/[0.05] flex items-center gap-2 transition-colors"
          >
            <ExternalLink className="w-3.5 h-3.5 text-cyan-400" />
            <span>Open Tearsheet</span>
          </button>

          <button
            onClick={() => {
              navigator.clipboard.writeText(contextMenu.cand.symbol);
              setCopiedSymbol(contextMenu.cand.symbol);
              setTimeout(() => setCopiedSymbol(null), 2000);
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-left text-slate-200 hover:text-cyan-300 hover:bg-white/[0.05] flex items-center gap-2 transition-colors"
          >
            <Copy className="w-3.5 h-3.5 text-cyan-400" />
            <span>Copy Symbol</span>
          </button>

          <button
            onClick={async () => {
              const sym = contextMenu.cand.symbol;
              const nextState = !contextMenu.cand.is_watchlist;
              await toggleWatchlist(sym, nextState);
              contextMenu.cand.is_watchlist = nextState ? 1 : 0;
              window.dispatchEvent(
                new CustomEvent("mil:watchlist-change", {
                  detail: { symbol: sym, is_watchlist: nextState },
                })
              );
              setContextMenu(null);
            }}
            className="w-full px-3 py-1.5 text-left text-slate-200 hover:text-cyan-300 hover:bg-white/[0.05] flex items-center gap-2 transition-colors"
          >
            <Star
              className={cn(
                "w-3.5 h-3.5",
                contextMenu.cand.is_watchlist
                  ? "text-amber-400 fill-amber-400"
                  : "text-slate-400"
              )}
            />
            <span>
              {contextMenu.cand.is_watchlist ? "Remove Watchlist" : "Add to Watchlist"}
            </span>
          </button>
        </div>
      )}

      {/* Copy Toast Notification */}
      {copiedSymbol && (
        <div className="fixed bottom-12 right-6 z-50 flex items-center gap-2 px-3 py-1.5 rounded-lg bg-emerald-950/90 border border-emerald-500/50 text-emerald-300 text-xs font-mono shadow-xl animate-in fade-in slide-in-from-bottom-2">
          <Check className="w-3.5 h-3.5 text-emerald-400" />
          <span>Copied {copiedSymbol} to clipboard!</span>
        </div>
      )}
    </div>
  );
}

export default React.memo(ScreenerWorkspaceComponent);
