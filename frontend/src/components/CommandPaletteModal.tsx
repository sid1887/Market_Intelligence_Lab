"use client";

import React, { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Search, ArrowRight, Command } from "lucide-react";
import { ScreenerCandidate, prefetchStockBundle } from "@/lib/api";

interface CommandPaletteModalProps {
  candidates: ScreenerCandidate[];
  onSelect: (symbol: string) => void;
  onClose: () => void;
}

export const CommandPaletteModal: React.FC<CommandPaletteModalProps> = ({
  candidates,
  onSelect,
  onClose,
}) => {
  const [query, setQuery] = useState("");
  const [cursorIndex, setCursorIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  const filtered = query.trim()
    ? candidates
        .filter(
          (c) =>
            c.symbol.toLowerCase().includes(query.toLowerCase()) ||
            c.company_name.toLowerCase().includes(query.toLowerCase()) ||
            c.sector.toLowerCase().includes(query.toLowerCase())
        )
        .slice(0, 8)
    : candidates.slice(0, 8);

  // Auto-focus input
  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 50);
  }, []);

  // Reset cursor on query change
  useEffect(() => {
    setCursorIndex(0);
  }, [query]);

  // Keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setCursorIndex((i) => Math.min(i + 1, filtered.length - 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setCursorIndex((i) => Math.max(i - 1, 0));
      } else if (e.key === "Enter" && filtered[cursorIndex]) {
        e.preventDefault();
        onSelect(filtered[cursorIndex].symbol);
        onClose();
      } else if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [filtered, cursorIndex, onSelect, onClose]);

  // Scroll active item into view
  useEffect(() => {
    const el = listRef.current?.querySelector(`[data-idx="${cursorIndex}"]`);
    el?.scrollIntoView({ block: "nearest" });
  }, [cursorIndex]);

  const handleSelect = (symbol: string) => {
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
        className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-start justify-center pt-[15vh]"
        onClick={onClose}
      >
        {/* Modal */}
        <motion.div
          initial={{ opacity: 0, scale: 0.96, y: -8 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.96, y: -8 }}
          transition={{ type: "spring", stiffness: 400, damping: 30 }}
          onClick={(e) => e.stopPropagation()}
          className="w-full max-w-[560px] glass-elevated rounded-2xl overflow-hidden shadow-2xl shadow-black/70"
          style={{ border: "1px solid rgba(255,255,255,0.09)" }}
        >
          {/* Search bar */}
          <div className="flex items-center gap-3 px-4 py-3.5 border-b border-white/[0.06]">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symbol, company, or sector…"
              className="flex-1 bg-transparent text-sm font-mono text-slate-100 placeholder-slate-500 outline-none"
            />
            <kbd className="text-[10px] font-mono text-slate-500 bg-slate-800/60 border border-white/[0.06] rounded px-1.5 py-0.5">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div ref={listRef} className="max-h-[400px] overflow-y-auto py-1.5">
            {filtered.length === 0 && (
              <div className="px-4 py-8 text-center text-sm font-mono text-slate-500">
                No matches for &ldquo;{query}&rdquo;
              </div>
            )}
            {filtered.map((item, idx) => {
              const isActive = idx === cursorIndex;
              const score = item.composite_score ?? 0;
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
                  onMouseEnter={() => {
                    setCursorIndex(idx);
                    prefetchStockBundle(item.symbol);
                  }}
                  onClick={() => handleSelect(item.symbol)}
                  className={`flex items-center gap-3 px-4 py-2.5 cursor-pointer transition-colors ${
                    isActive
                      ? "bg-cyan-500/10"
                      : "hover:bg-white/[0.03]"
                  }`}
                >
                  {/* Rank pill */}
                  <span className="text-[10px] font-mono text-slate-500 w-5 text-right shrink-0">
                    {item.rank}
                  </span>

                  {/* Symbol + name */}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-mono font-bold text-white tracking-tight">
                        {item.symbol}
                      </span>
                      <span className="text-xs text-slate-400 truncate">{item.company_name}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">{item.sector}</span>
                  </div>

                  {/* Score + price */}
                  <div className="flex items-center gap-3 shrink-0">
                    <span className={`text-xs font-mono font-bold ${scoreColor}`}>
                      {score.toFixed(0)}
                    </span>
                    {item.close && (
                      <span className="text-xs font-mono text-slate-300">
                        ₹{item.close.toFixed(2)}
                      </span>
                    )}
                    {isActive && <ArrowRight className="w-3.5 h-3.5 text-cyan-400" />}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Footer hint */}
          <div className="flex items-center gap-4 px-4 py-2 border-t border-white/[0.05] text-[10px] font-mono text-slate-500">
            <span className="flex items-center gap-1.5">
              <Command className="w-3 h-3" /> K to open
            </span>
            <span>↑↓ navigate</span>
            <span>↵ select</span>
            <span className="ml-auto">{filtered.length} results</span>
          </div>
        </motion.div>
      </motion.div>
    </AnimatePresence>
  );
};
