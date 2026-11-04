"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown } from "lucide-react";
import { ScreenerCandidate, prefetchStockBundle } from "@/lib/api";

interface SectorHeatmapProps {
  candidates: ScreenerCandidate[];
  activeSymbol: string;
  onSelect: (symbol: string) => void;
  onHover?: (symbol: string) => void;
}

export const SectorHeatmap: React.FC<SectorHeatmapProps> = ({
  candidates,
  activeSymbol,
  onSelect,
  onHover,
}) => {
  // Group stocks by sector
  const sectorGroups = useMemo(() => {
    const map = new Map<string, ScreenerCandidate[]>();

    candidates.forEach((c) => {
      const sec = c.sector || "Other";
      if (!map.has(sec)) {
        map.set(sec, []);
      }
      map.get(sec)!.push(c);
    });

    // Sort sectors by number of stocks descending
    const sorted = Array.from(map.entries()).sort(
      (a, b) => b[1].length - a[1].length
    );

    return sorted.map(([sector, stocks]) => {
      // Sort stocks inside sector by composite_score or excess return
      const sortedStocks = [...stocks].sort(
        (a, b) => (b.composite_score ?? 0) - (a.composite_score ?? 0)
      );

      // Average 20d return
      const validReturns = stocks
        .map((s) => s.excess_ret_20d)
        .filter((r): r is number => r !== null);
      const avgReturn =
        validReturns.length > 0
          ? validReturns.reduce((acc, v) => acc + v, 0) / validReturns.length
          : 0;

      return {
        sector,
        stocks: sortedStocks,
        avgReturn,
        count: stocks.length,
      };
    });
  }, [candidates]);

  return (
    <div className="flex-1 overflow-y-auto p-3 space-y-4 select-none">
      {sectorGroups.map(({ sector, stocks, avgReturn, count }) => {
        const isUp = avgReturn >= 0;
        const avgPct = (avgReturn * 100).toFixed(1);

        return (
          <div
            key={sector}
            className="rounded-xl border border-white/[0.05] bg-slate-950/40 p-3 space-y-2 backdrop-blur-sm shadow-sm"
          >
            {/* Sector Header */}
            <div className="flex items-center justify-between text-xs font-mono pb-1 border-b border-white/[0.04]">
              <div className="flex items-center gap-2">
                <span className="text-white font-bold tracking-tight text-[11px]">
                  {sector}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">
                  ({count} {count === 1 ? "constituent" : "constituents"})
                </span>
              </div>

              <div
                className={`flex items-center gap-1 text-[10px] font-semibold px-2 py-0.5 rounded ${
                  isUp
                    ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                    : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                }`}
              >
                {isUp ? (
                  <TrendingUp className="w-2.5 h-2.5" />
                ) : (
                  <TrendingDown className="w-2.5 h-2.5" />
                )}
                <span>
                  {isUp ? "+" : ""}
                  {avgPct}% avg 20d
                </span>
              </div>
            </div>

            {/* Treemap / Heatmap Tiles */}
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-1.5 pt-1">
              {stocks.map((stock) => {
                const isActive = stock.symbol === activeSymbol;
                const ret = stock.excess_ret_20d ?? 0;
                const retPct = (ret * 100).toFixed(1);
                const score = Math.round(stock.composite_score ?? 0);

                // Color tiering based on 20D excess return
                let colorClasses =
                  "bg-slate-900/60 border-white/[0.06] text-slate-300 hover:border-slate-500";
                if (ret >= 0.08) {
                  colorClasses =
                    "bg-emerald-500/20 border-emerald-500/40 text-emerald-200 shadow-[0_0_10px_rgba(16,185,129,0.15)]";
                } else if (ret >= 0.02) {
                  colorClasses =
                    "bg-emerald-950/45 border-emerald-600/30 text-emerald-300";
                } else if (ret <= -0.08) {
                  colorClasses =
                    "bg-rose-500/20 border-rose-500/40 text-rose-200 shadow-[0_0_10px_rgba(244,63,94,0.15)]";
                } else if (ret <= -0.02) {
                  colorClasses =
                    "bg-rose-950/45 border-rose-600/30 text-rose-300";
                }

                if (isActive) {
                  colorClasses =
                    "bg-cyan-500/25 border-cyan-400 text-white ring-1 ring-cyan-400 shadow-[0_0_14px_rgba(6,182,212,0.45)] scale-[1.02]";
                }

                return (
                  <motion.div
                    key={stock.symbol}
                    whileHover={{ scale: 1.03 }}
                    whileTap={{ scale: 0.98 }}
                    onClick={() => onSelect(stock.symbol)}
                    onMouseEnter={() => {
                      prefetchStockBundle(stock.symbol);
                      if (onHover) onHover(stock.symbol);
                    }}
                    className={`cursor-pointer rounded-lg border p-2 flex flex-col justify-between transition-all duration-150 min-h-[58px] ${colorClasses}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-mono font-bold text-xs tracking-tight text-white">
                        {stock.symbol}
                      </span>
                      <span className="text-[9px] font-mono font-semibold px-1 py-0.2 rounded bg-black/40 text-cyan-300">
                        {score}
                      </span>
                    </div>

                    <div className="flex items-center justify-between mt-1 text-[10px] font-mono">
                      <span className="text-slate-400 truncate text-[9px] max-w-[65%]">
                        ₹{stock.close?.toFixed(1) ?? "—"}
                      </span>
                      <span
                        className={`font-semibold text-[10px] ${
                          ret >= 0 ? "text-emerald-300" : "text-rose-300"
                        }`}
                      >
                        {ret >= 0 ? "+" : ""}
                        {retPct}%
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </div>
          </div>
        );
      })}
    </div>
  );
};
