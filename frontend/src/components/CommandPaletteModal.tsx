"use client";

import React, { useEffect, useRef, useState, useMemo } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, ArrowRight, Command, History } from "lucide-react";
import { ScreenerCandidate } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CommandPaletteModalProps {
  candidates: ScreenerCandidate[];
  watchlistSymbols?: string[];
  onSelect: (symbol: string) => void;
  onClose: () => void;
}

export const CommandPaletteModal: React.FC<CommandPaletteModalProps> = ({
  candidates,
  watchlistSymbols = [],
  onSelect,
  onClose,
}) => {
  const [query, setQuery] = useState("");
  const [cursorIndex, setCursorIndex] = useState(0);
  const [recentSearches, setRecentSearches] = useState<string[]>(() => {
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem("mil:recent-searches");
        if (stored) return JSON.parse(stored);
      } catch {}
    }
    return [];
  });

  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = useMemo(() => {
    if (query.trim()) {
      const q = query.toLowerCase();
      return candidates
        .filter(
          (c) =>
            c.symbol.toLowerCase().includes(q) ||
            c.company_name.toLowerCase().includes(q) ||
            (c.sector || "").toLowerCase().includes(q)
        )
        .slice(0, 10);
    }
    // No query: show top 10 quant picks sorted by blended score
    return [...candidates]
      .sort((a, b) => (b.blended_score ?? 0) - (a.blended_score ?? 0))
      .slice(0, 10);
  }, [candidates, query]);

  // Auto-focus input
  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  // Reset cursor on query change
  useEffect(() => {
    setCursorIndex(0);
  }, [query]);

  const handleSelect = (symbol: string) => {
    try {
      const updated = [symbol, ...recentSearches.filter((s) => s !== symbol)].slice(0, 5);
      setRecentSearches(updated);
      localStorage.setItem("mil:recent-searches", JSON.stringify(updated));
    } catch {}
    onSelect(symbol);
    onClose();
  };

  return (
    <AnimatePresence>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.15 }}
        className="fixed inset-0 z-50 bg-black/85 flex items-start justify-center pt-[12vh] px-4"
        onClick={onClose}
      >
        {/* Spotlight Modal Box */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: -10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -10 }}
          transition={{ type: "spring", stiffness: 450, damping: 32 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-[580px] rounded-2xl overflow-hidden bg-[#080c14] border border-white/[0.12] shadow-[0_25px_70px_-15px_rgba(0,0,0,0.9)]"
        >
          {/* Search bar */}
          <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/[0.08] bg-white/[0.02]">
            <Search className="w-4 h-4 text-cyan-400 shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search ticker, company, or sector (e.g. INFY, Pharma)..."
              className="flex-1 bg-transparent text-sm font-mono text-slate-100 placeholder-slate-500 outline-none"
            />
            <kbd className="text-[10px] font-mono text-slate-400 bg-white/[0.05] border border-white/[0.08] rounded px-1.5 py-0.5">
              ESC
            </kbd>
          </div>

          {/* Recent Searches Quick Access */}
          {recentSearches.length > 0 && (
            <div className="flex items-center gap-1.5 px-4 py-1.5 bg-white/[0.01] border-b border-white/[0.04] overflow-x-auto no-scrollbar">
              <span className="flex items-center gap-1 text-[10px] font-mono uppercase tracking-wider text-slate-500 shrink-0 mr-1">
                <History className="w-3 h-3 text-slate-500" />
                Recent:
              </span>
              {recentSearches.map((sym) => (
                <button
                  key={sym}
                  onClick={() => handleSelect(sym)}
                  className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-slate-800/60 border border-slate-700/50 text-slate-300 hover:bg-slate-700/60 hover:text-white hover:border-slate-500 transition-colors shrink-0"
                >
                  {sym}
                </button>
              ))}
              <button
                onClick={() => {
                  setRecentSearches([]);
                  try {
                    localStorage.removeItem("mil:recent-searches");
                  } catch {}
                }}
                className="ml-auto text-[10px] font-mono text-slate-600 hover:text-slate-400 transition-colors shrink-0"
                title="Clear recent searches"
              >
                Clear
              </button>
            </div>
          )}

          {/* Focus Watchlist Quick Access */}
          {watchlistSymbols.length > 0 && (
            <div className="flex items-center gap-1.5 px-4 py-2 bg-white/[0.015] border-b border-white/[0.06] overflow-x-auto no-scrollbar">
              <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 shrink-0 mr-1">
                Watchlist:
              </span>
              {watchlistSymbols.map((sym) => (
                <button
                  key={sym}
                  onClick={() => handleSelect(sym)}
                  className="px-2 py-0.5 rounded-md text-[11px] font-mono bg-cyan-950/40 border border-cyan-500/20 text-cyan-300 hover:bg-cyan-500/20 hover:border-cyan-500/40 transition-colors shrink-0"
                >
                  {sym}
                </button>
              ))}
            </div>
          )}

          {/* Results List */}
          <div ref={listRef} className="max-h-[380px] overflow-y-auto py-1.5 scrollbar-thin scrollbar-thumb-slate-800">
            {filtered.length === 0 && (
              <div className="px-4 py-8 text-center text-xs font-mono text-slate-500">
                No matching equities found for &ldquo;{query}&rdquo;
              </div>
            )}
            {filtered.map((item, idx) => {
              const isActive = idx === cursorIndex;
              const score = item.blended_score ?? item.composite_score ?? 0;
              const scoreColor =
                score >= 80
                  ? "text-emerald-400"
                  : score >= 60
                  ? "text-cyan-400"
                  : "text-amber-400";

              return (
                <div
                  key={item.symbol}
                  data-idx={idx}
                  onMouseEnter={() => setCursorIndex(idx)}
                  onClick={() => handleSelect(item.symbol)}
                  className={cn(
                    "flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors border-l-2",
                    isActive
                      ? "bg-cyan-500/10 border-cyan-400 text-white"
                      : "border-transparent text-slate-300 hover:bg-white/[0.03]"
                  )}
                >
                  {/* Rank pill */}
                  <span className="text-[10px] font-mono text-slate-500 w-5 text-right shrink-0 tabular-nums">
                    {item.rank || idx + 1}
                  </span>

                  {/* Symbol + name */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono font-bold text-slate-100 tracking-tight">
                        {item.symbol}
                      </span>
                      <span className="text-xs text-slate-400 truncate font-mono">{item.company_name}</span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono">{item.sector}</span>
                  </div>

                  {/* Score + price */}
                  <div className="flex items-center gap-3 shrink-0 font-mono">
                    <div className="text-right">
                      <div className={`text-xs font-bold tabular-nums ${scoreColor}`}>
                        Score {score.toFixed(1)}
                      </div>
                      {item.close !== null && (
                        <div className="text-[10px] text-slate-400 tabular-nums">
                          ₹{item.close.toFixed(2)}
                        </div>
                      )}
                    </div>
                    {isActive && <ArrowRight className="w-4 h-4 text-cyan-400 animate-pulse" />}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer Navigation Hints */}
          <div className="flex items-center gap-4 px-4 py-2.5 border-t border-white/[0.06] bg-white/[0.02] text-[10px] font-mono text-slate-500">
            <span className="flex items-center gap-1.5">
              <Command className="w-3 h-3 text-cyan-400" /> K to search
            </span>
            <span>↑↓ to navigate</span>
            <span>↵ to select</span>
            <span className="ml-auto tabular-nums">{filtered.length} candidates</span>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};

export default CommandPaletteModal;
