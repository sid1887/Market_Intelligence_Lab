"use client";

import React, { useMemo } from "react";
import { motion } from "framer-motion";
import { TrendingUp, TrendingDown, Layers } from "lucide-react";
import { ScreenerCandidate } from "@/lib/api";
import { cn } from "@/lib/utils";

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
      // Sort stocks inside sector by blended / composite score
      const sortedStocks = [...stocks].sort(
        (a, b) => ((b.blended_score ?? b.composite_score) ?? 0) - ((a.blended_score ?? a.composite_score) ?? 0)
      );

      // Average 20d return
      const validReturns = stocks
        .map((s) => s.excess_ret_20d)
        .filter((r): r is number => r !== null);
      const avgReturn =
        validReturns.length > 0
          ? validReturns.reduce((acc, v) => acc + v, 0) / validReturns.length
          : 0;

      // Sector breadth (positive vs negative count)
      const positiveCount = validReturns.filter((r) => r > 0).length;
      const breadthPct = validReturns.length > 0 ? (positiveCount / validReturns.length) * 100 : 50;

      return {
        sector,
        stocks: sortedStocks,
        avgReturn,
        count: stocks.length,
        breadthPct,
      };
    });
  }, [candidates]);

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-4 select-none scrollbar-thin scrollbar-thumb-slate-800">
      {sectorGroups.map(({ sector, stocks, avgReturn, count, breadthPct }) => {
        const isUp = avgReturn >= 0;
        const avgPct = (avgReturn * 100).toFixed(1);

        return (
          <div
            key={sector}
            className="rounded-2xl border border-white/[0.08] bg-[#070b12] p-4 space-y-3 shadow-lg"
          >
            {/* Sector Header with Breadth Telemetry */}
            <div className="flex items-center justify-between text-xs font-mono pb-2 border-b border-white/[0.06]">
              <div className="flex items-center gap-2.5">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                <span className="text-white font-bold tracking-tight text-xs uppercase">
                  {sector}
                </span>
                <span className="text-[10px] text-slate-500 font-mono">
                  ({count} equities)
                </span>
                <div className="hidden sm:flex items-center gap-1.5 ml-2 text-[10px] text-slate-400">
                  <span>Breadth:</span>
                  <div className="w-16 h-1.5 bg-black/50 rounded-full overflow-hidden border border-white/[0.08]">
                    <div
                      className="h-full bg-gradient-to-r from-emerald-500 to-cyan-400 rounded-full"
                      style={{ width: `${breadthPct}%` }}
                    />
                  </div>
                  <span className="text-slate-300 font-bold tabular-nums">{breadthPct.toFixed(0)}%</span>
                </div>
              </div>

              <div
                className={cn(
                  "flex items-center gap-1 text-[11px] font-semibold px-2.5 py-0.5 rounded-full border tabular-nums",
                  isUp
                    ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                    : "bg-rose-500/10 text-rose-400 border-rose-500/30 shadow-[0_0_10px_rgba(244,63,94,0.2)]"
                )}
              >
                {isUp ? (
                  <TrendingUp className="w-3 h-3 text-emerald-400" />
                ) : (
                  <TrendingDown className="w-3 h-3 text-rose-400" />
                )}
                <span>
                  {isUp ? "+" : ""}
                  {avgPct}% avg 20D
                </span>
              </div>
            </div>

            {/* Weighted Treemap Heatmap Glass Tiles (A7) */}
            <motion.div
              variants={{
                hidden: { opacity: 0 },
                visible: { opacity: 1, transition: { staggerChildren: 0.02, delayChildren: 0.04 } },
              }}
              initial="hidden"
              animate="visible"
              className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-2 pt-1"
            >
              {stocks.map((stock) => {
                const isActive = stock.symbol === activeSymbol;
                const ret = stock.excess_ret_20d ?? 0;
                const retPct = (ret * 100).toFixed(1);
                const score = Math.round(stock.blended_score ?? stock.composite_score ?? 0);
                const isHero =
                  (stock.target_allocation_pct && stock.target_allocation_pct >= 2.5) ||
                  score >= 80;

                const returnIntensity = Math.abs(ret);
                const glowColor =
                  ret >= 0
                    ? `rgba(16, 185, 129, ${Math.min(Math.max(returnIntensity * 3, 0.15), 0.5)})`
                    : `rgba(244, 63, 94, ${Math.min(Math.max(returnIntensity * 3, 0.15), 0.5)})`;

                let colorClasses =
                  "bg-white/[0.02] border-white/[0.06] text-slate-300 hover:border-cyan-500/30";
                if (ret >= 0.08) {
                  colorClasses =
                    "bg-emerald-500/15 border-emerald-500/35 text-emerald-200 shadow-[0_0_12px_rgba(16,185,129,0.15)]";
                } else if (ret >= 0.02) {
                  colorClasses =
                    "bg-emerald-950/40 border-emerald-600/30 text-emerald-300";
                } else if (ret <= -0.08) {
                  colorClasses =
                    "bg-rose-500/15 border-rose-500/35 text-rose-200 shadow-[0_0_12px_rgba(244,63,94,0.15)]";
                } else if (ret <= -0.02) {
                  colorClasses =
                    "bg-rose-950/40 border-rose-600/30 text-rose-300";
                }

                if (isActive) {
                  colorClasses =
                    "bg-cyan-500/20 border-cyan-400 text-white ring-1 ring-cyan-400 shadow-[0_0_16px_rgba(6,182,212,0.4)]";
                }

                return (
                  <motion.div
                    key={stock.symbol}
                    variants={{
                      hidden: { opacity: 0, scale: 0.9 },
                      visible: { opacity: 1, scale: 1, transition: { type: "spring", stiffness: 350, damping: 25 } },
                    }}
                    whileHover={{ scale: 1.05, boxShadow: `0 0 18px ${glowColor}`, zIndex: 10 }}
                    whileTap={{ scale: 0.97 }}
                    onClick={() => onSelect(stock.symbol)}
                    onMouseEnter={() => {
                      if (onHover) onHover(stock.symbol);
                    }}
                    className={cn(
                      "cursor-pointer rounded-xl border p-2.5 flex flex-col justify-between transition-all duration-150 min-h-[68px] relative",
                      isHero ? "col-span-2 min-h-[76px] bg-gradient-to-br from-white/[0.04] to-transparent" : "col-span-1",
                      colorClasses
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono font-bold text-xs tracking-tight text-white">
                          {stock.symbol}
                        </span>
                        {isHero && stock.target_allocation_pct && (
                          <span className="text-[9px] px-1 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-mono">
                            {stock.target_allocation_pct.toFixed(1)}%
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-black/60 text-cyan-300 border border-white/[0.08] tabular-nums">
                        {score}
                      </span>
                    </div>

                    {isHero && stock.company_name && (
                      <div className="text-[10px] text-slate-400 truncate my-0.5 max-w-[190px]">
                        {stock.company_name}
                      </div>
                    )}

                    <div className="flex items-center justify-between mt-1 text-[10px] font-mono">
                      <span className="text-slate-400 truncate text-[10px] tabular-nums">
                        {stock.close !== null ? `₹${stock.close.toFixed(1)}` : "—"}
                      </span>
                      <span
                        className={cn(
                          "font-bold text-[10px] tabular-nums",
                          ret >= 0 ? "text-emerald-300" : "text-rose-300"
                        )}
                      >
                        {ret >= 0 ? "+" : ""}
                        {retPct}%
                      </span>
                    </div>
                  </motion.div>
                );
              })}
            </motion.div>
          </div>
        );
      })}
    </div>
  );
};

export default SectorHeatmap;
