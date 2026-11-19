"use client";

import React from "react";
import Link from "next/link";
import { TrendingUp, TrendingDown, ArrowUpRight, Compass } from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface WatchlistItem {
  symbol: string;
  company_name: string;
  sector: string;
  target_price?: number | null;
  stop_loss?: number | null;
  notes?: string | null;
  close: number | null;
  ret_1d: number;
  ret_1d_pct: number;
  sma_200: number | null;
  dist_sma200_pct: number | null;
  price_above_sma200: boolean;
  roe_pct?: number | null;
  debt_to_equity?: number | null;
  volume?: number | null;
  sparkline?: number[] | null;
}

interface WatchlistPanelProps {
  items: WatchlistItem[];
  loading?: boolean;
  onSelectSymbol?: (symbol: string) => void;
}

function WatchlistSparkline({
  prices,
  isUp,
  distSma,
}: {
  prices?: number[] | null;
  isUp: boolean;
  distSma: number;
}) {
  const strokeColor = isUp ? "#34d399" : "#fb7185";

  let pts = "";
  if (prices && prices.length >= 2) {
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const range = max - min || (max > 0 ? max * 0.01 : 1);
    pts = prices
      .map((p, i) => {
        const x = ((i / (prices.length - 1)) * 62 + 1).toFixed(1);
        const y = (18 - ((p - min) / range) * 15).toFixed(1);
        return `${x},${y}`;
      })
      .join(" ");
  } else {
    // Graceful trend slope based on real return direction and distance to 200 SMA
    pts = isUp
      ? distSma > 0
        ? "1,17 15,14 30,12 45,8 63,3"
        : "1,18 15,16 30,13 45,9 63,4"
      : distSma < 0
      ? "1,3 15,7 30,11 45,15 63,18"
      : "1,2 15,6 30,10 45,14 63,17";
  }

  return (
    <svg
      className="w-16 h-6 overflow-visible shrink-0"
      viewBox="0 0 64 20"
      aria-hidden="true"
    >
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={pts}
      />
    </svg>
  );
}

export default function WatchlistPanel({ items, loading, onSelectSymbol }: WatchlistPanelProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map(i => (
          <div
            key={i}
            className="h-[82px] bg-[#06090f]/80 border border-white/[0.05] rounded-xl animate-pulse relative overflow-hidden"
          >
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/[0.02] to-transparent animate-shimmer" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-500" />
          </span>
          <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-200">
            Active Watchlist Rail
          </h2>
          <span className="text-[10px] px-1.5 py-0.5 rounded font-mono font-bold tabular-nums bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 shadow-[0_0_10px_rgba(6,182,212,0.2)]">
            {items.length}
          </span>
        </div>
        <div className="flex items-center space-x-1.5 text-[11px] text-slate-400 font-mono">
          <Compass className="w-3 h-3 text-cyan-400" />
          <span>Primary Conviction Equities</span>
        </div>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {items.map(stock => {
          const isUp = stock.ret_1d >= 0;
          const dist = stock.dist_sma200_pct || 0;
          const distAboveSma = dist >= 0;

          return (
            <motion.div
              key={stock.symbol}
              whileHover={{ y: -2, transition: { duration: 0.15 } }}
              whileTap={{ scale: 0.99 }}
            >
              <div
                onClick={() => onSelectSymbol?.(stock.symbol)}
                className={cn(
                  "group relative h-[82px] bg-[#06090f]/75 hover:bg-[#09101c]/90 border border-white/[0.08] hover:border-cyan-500/40 rounded-xl px-3.5 py-2.5 transition-all duration-200 shadow-lg hover:shadow-[0_0_24px_rgba(6,182,212,0.14)] flex items-center justify-between overflow-hidden cursor-pointer",
                  onSelectSymbol ? "select-none" : ""
                )}
              >
                {/* Top specular highlight line on hover */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

                {/* Subtle radial glow corner */}
                <div
                  className="absolute -top-12 -left-12 w-24 h-24 rounded-full opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                  style={{
                    background: "radial-gradient(circle, rgba(6, 182, 212, 0.15) 0%, transparent 70%)",
                  }}
                />

                {/* Left Column: Ticker, Sector, and Price */}
                <div className="flex flex-col justify-between h-full z-10 min-w-0 pr-2">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-[13px] font-bold text-white font-mono group-hover:text-cyan-300 transition-colors tracking-tight flex items-center gap-1">
                      {stock.symbol}
                    </span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-slate-400 font-mono truncate max-w-[80px]">
                      {stock.sector}
                    </span>
                    <Link
                      href={`/stocks/${stock.symbol}`}
                      onClick={(e) => e.stopPropagation()}
                      title={`Open full tearsheet for ${stock.symbol}`}
                      className="opacity-0 group-hover:opacity-100 transition-opacity text-slate-500 hover:text-cyan-300 p-0.5"
                    >
                      <ArrowUpRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                  <div className="flex items-baseline space-x-2">
                    <div className="text-[16px] font-black text-slate-100 font-mono tabular-nums tracking-tight leading-none">
                      {stock.close !== null ? `₹${stock.close.toFixed(2)}` : "—"}
                    </div>
                    {stock.dist_sma200_pct !== null && (
                      <span
                        className={`text-[9px] font-mono tabular-nums font-semibold ${
                          distAboveSma ? "text-emerald-400/80" : "text-slate-500"
                        }`}
                        title="Distance to 200-day Simple Moving Average"
                      >
                        {distAboveSma ? "+" : ""}{dist.toFixed(1)}% 200D
                      </span>
                    )}
                  </div>
                </div>

                {/* Right Column: Sparkline & 1D Change Pill */}
                <div className="flex flex-col items-end justify-between h-full z-10 shrink-0">
                  <div
                    className={`flex items-center space-x-0.5 px-2 py-0.5 rounded font-mono tabular-nums text-[11px] font-bold shadow-sm ${
                      isUp
                        ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.15)]"
                        : "bg-rose-500/15 text-rose-300 border border-rose-500/30 shadow-[0_0_8px_rgba(244,63,94,0.15)]"
                    }`}
                  >
                    {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                    <span>{stock.ret_1d_pct >= 0 ? "+" : ""}{stock.ret_1d_pct.toFixed(2)}%</span>
                  </div>

                  <WatchlistSparkline prices={stock.sparkline} isUp={isUp} distSma={dist} />
                </div>
              </div>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
