"use client";

import React from "react";
import Link from "next/link";
import { TrendingUp, TrendingDown } from "lucide-react";

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
      <polyline
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        points={pts}
      />
    </svg>
  );
}

export default function WatchlistPanel({ items, loading }: WatchlistPanelProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-[76px] bg-[#080d1a]/80 border border-white/[0.04] rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400" />
          <h2 className="text-xs font-mono font-bold uppercase tracking-wider text-slate-300">
            Active Watchlist Rail
          </h2>
          <span className="text-[10px] px-1.5 py-0.2 rounded font-mono font-semibold bg-cyan-950/80 border border-cyan-800/60 text-cyan-400">
            {items.length}
          </span>
        </div>
        <span className="text-[11px] text-slate-500 font-mono">Primary Conviction Equities</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
        {items.map(stock => {
          const isUp = stock.ret_1d >= 0;
          const dist = stock.dist_sma200_pct || 0;

          return (
            <Link
              key={stock.symbol}
              href={`/stocks/${stock.symbol}`}
              className="group h-[76px] bg-[#080d1a]/90 hover:bg-[#0c1427] border border-white/[0.05] hover:border-cyan-500/30 rounded-xl px-3.5 py-2.5 transition-all duration-200 shadow-md hover:shadow-[0_0_15px_-3px_rgba(6,182,212,0.12)] flex items-center justify-between overflow-hidden relative"
            >
              {/* Subtle hover gradient wash */}
              <div className="absolute inset-0 bg-gradient-to-r from-cyan-500/[0.03] to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

              {/* Left Column: Ticker, Sector, and Price */}
              <div className="flex flex-col justify-between h-full z-10">
                <div className="flex items-center space-x-1.5">
                  <span className="text-[13px] font-bold text-white font-mono group-hover:text-cyan-400 transition-colors tracking-tight">
                    {stock.symbol}
                  </span>
                  <span className="text-[9px] px-1 py-0.2 rounded bg-slate-800/80 text-slate-400 font-mono truncate max-w-[80px]">
                    {stock.sector}
                  </span>
                </div>
                <div className="text-[15px] font-black text-slate-100 font-mono tracking-tight leading-none">
                  {stock.close !== null ? `₹${stock.close.toFixed(2)}` : "—"}
                </div>
              </div>

              {/* Right Column: Sparkline & 1D Change Pill */}
              <div className="flex flex-col items-end justify-between h-full z-10">
                <div
                  className={`flex items-center space-x-0.5 px-1.5 py-0.5 rounded font-mono text-[11px] font-bold ${
                    isUp
                      ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"
                      : "bg-rose-500/10 text-rose-400 border border-rose-500/20"
                  }`}
                >
                  {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  <span>{stock.ret_1d_pct >= 0 ? "+" : ""}{stock.ret_1d_pct.toFixed(2)}%</span>
                </div>

                <WatchlistSparkline isUp={isUp} distSma={dist} />
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
