"use client";

import React from "react";
import Link from "next/link";
import { TrendingUp, TrendingDown, ArrowUpRight, Compass } from "lucide-react";
import { motion } from "framer-motion";

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
}

interface WatchlistPanelProps {
  items: WatchlistItem[];
  loading?: boolean;
}

function WatchlistSparkline({ isUp, distSma }: { isUp: boolean; distSma: number }) {
  // Deterministic 10-point smooth sparkline path based on return & distance to SMA
  const upwardPoints = distSma > 0
    ? "0,16 7,15 14,12 21,14 28,9 35,11 42,6 49,8 56,3 64,2"
    : "0,18 7,16 14,14 21,15 28,11 35,12 42,9 49,7 56,5 64,3";

  const downwardPoints = distSma < 0
    ? "0,3 7,5 14,7 21,5 28,10 35,8 42,13 49,12 56,17 64,19"
    : "0,2 7,4 14,6 21,8 28,7 35,11 42,13 49,14 56,16 64,18";

  const pts = isUp ? upwardPoints : downwardPoints;
  const strokeColor = isUp ? "#34d399" : "#fb7185";

  return (
    <svg className="w-16 h-6 overflow-visible shrink-0" viewBox="0 0 64 20">
      <defs>
        <filter id={`sparkline-glow-${isUp ? "up" : "down"}`} x="-20%" y="-20%" width="140%" height="140%">
          <feDropShadow
            dx="0"
            dy="0"
            stdDeviation="1.5"
            floodColor={isUp ? "#10b981" : "#f43f5e"}
            floodOpacity="0.5"
          />
        </filter>
      </defs>
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={pts}
        filter={`url(#sparkline-glow-${isUp ? "up" : "down"})`}
      />
    </svg>
  );
}

export default function WatchlistPanel({ items, loading }: WatchlistPanelProps) {
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
              <Link
                href={`/stocks/${stock.symbol}`}
                className="group relative h-[82px] bg-[#06090f]/75 hover:bg-[#09101c]/90 border border-white/[0.08] hover:border-cyan-500/40 rounded-xl px-3.5 py-2.5 transition-all duration-200 shadow-lg hover:shadow-[0_0_24px_rgba(6,182,212,0.14)] flex items-center justify-between overflow-hidden block"
              >
                {/* Top specular highlight line on hover */}
                <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300" />

                {/* Subtle radial glow corner */}
                <div className="absolute -top-12 -left-12 w-24 h-24 bg-cyan-500/10 rounded-full blur-xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

                {/* Left Column: Ticker, Sector, and Price */}
                <div className="flex flex-col justify-between h-full z-10 min-w-0 pr-2">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-[13px] font-bold text-white font-mono group-hover:text-cyan-300 transition-colors tracking-tight flex items-center gap-1">
                      {stock.symbol}
                      <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity text-cyan-400" />
                    </span>
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/[0.04] border border-white/[0.06] text-slate-400 font-mono truncate max-w-[80px]">
                      {stock.sector}
                    </span>
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

                  <WatchlistSparkline isUp={isUp} distSma={dist} />
                </div>
              </Link>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
