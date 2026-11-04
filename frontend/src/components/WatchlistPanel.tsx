"use client";

import React from "react";
import Link from "next/link";
import { TrendingUp, TrendingDown, Target, ShieldAlert } from "lucide-react";

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

export default function WatchlistPanel({ items, loading }: WatchlistPanelProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {[1, 2, 3, 4].map(i => (
          <div key={i} className="h-44 bg-slate-900/60 border border-slate-800 rounded-xl animate-pulse" />
        ))}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <h2 className="text-lg font-bold text-slate-100 tracking-tight">Active User Watchlist</h2>
          <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-800/60 text-cyan-400 font-mono">
            {items.length} Instruments
          </span>
        </div>
        <span className="text-xs text-slate-400 font-mono">Primary Focus Positions</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {items.map(stock => {
          const isUp = stock.ret_1d >= 0;
          return (
            <Link
              key={stock.symbol}
              href={`/stocks/${stock.symbol}`}
              className="group block bg-slate-900/80 hover:bg-slate-900 border border-slate-800 hover:border-cyan-500/50 rounded-xl p-4 transition-all duration-200 shadow-lg hover:shadow-cyan-950/20 relative overflow-hidden"
            >
              {/* Top Accent Gradient Border */}
              <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-500 to-indigo-500 opacity-0 group-hover:opacity-100 transition-opacity" />

              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-base font-bold text-white font-mono group-hover:text-cyan-400 transition-colors">
                      {stock.symbol}
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-medium truncate max-w-[100px]">
                      {stock.sector}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 truncate max-w-[180px] mt-0.5" title={stock.company_name}>
                    {stock.company_name}
                  </p>
                </div>

                {/* 1D Return Pill */}
                <div
                  className={`flex items-center space-x-1 px-2 py-0.5 rounded-full text-xs font-mono font-semibold ${
                    isUp
                      ? "bg-emerald-950/70 border border-emerald-800/60 text-emerald-400"
                      : "bg-red-950/70 border border-red-800/60 text-red-400"
                  }`}
                >
                  {isUp ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
                  <span>{stock.ret_1d_pct >= 0 ? "+" : ""}{stock.ret_1d_pct.toFixed(2)}%</span>
                </div>
              </div>

              {/* Price Display */}
              <div className="mt-4 flex items-baseline justify-between">
                <div>
                  <span className="text-xs text-slate-500 font-mono">Close</span>
                  <div className="text-2xl font-extrabold text-slate-100 font-mono tracking-tight">
                    {stock.close !== null ? `₹${stock.close.toFixed(2)}` : "—"}
                  </div>
                </div>

                {stock.sma_200 !== null && (
                  <div className="text-right">
                    <span className="text-[10px] text-slate-500 font-mono">200 SMA</span>
                    <div className="text-xs font-mono text-slate-300">
                      ₹{stock.sma_200.toFixed(2)}
                    </div>
                  </div>
                )}
              </div>

              {/* Target / Stop Loss Levels & Status Badges */}
              <div className="mt-3 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs font-mono">
                {stock.target_price || stock.stop_loss ? (
                  <div className="flex items-center space-x-3 text-[11px]">
                    {stock.target_price && (
                      <span className="flex items-center space-x-1 text-emerald-400" title="Target Price">
                        <Target className="w-3 h-3" />
                        <span>₹{stock.target_price}</span>
                      </span>
                    )}
                    {stock.stop_loss && (
                      <span className="flex items-center space-x-1 text-red-400" title="Stop Loss">
                        <ShieldAlert className="w-3 h-3" />
                        <span>₹{stock.stop_loss}</span>
                      </span>
                    )}
                  </div>
                ) : (
                  <span className="text-[11px] text-slate-500">
                    {stock.roe_pct ? `ROE: ${stock.roe_pct.toFixed(1)}%` : "Trend Tracking"}
                  </span>
                )}

                <span
                  className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                    stock.price_above_sma200
                      ? "bg-emerald-950/60 text-emerald-400 border border-emerald-900"
                      : "bg-amber-950/60 text-amber-400 border border-amber-900"
                  }`}
                >
                  {stock.price_above_sma200 ? "> 200 SMA" : "< 200 SMA"}
                </span>
              </div>
            </Link>
          );
        })}
      </div>
    </div>
  );
}
