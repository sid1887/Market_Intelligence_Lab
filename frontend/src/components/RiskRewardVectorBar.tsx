"use client";

import React from "react";
import { motion } from "framer-motion";
import { ShieldAlert, Target, Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface RiskRewardProps {
  currentPrice: number;
  stopPrice: number;   // Lower 95% VaR / GARCH tail risk floor
  targetPrice: number; // Upper 80% trajectory objective
  className?: string;
}

export const RiskRewardVectorBar: React.FC<RiskRewardProps> = ({
  currentPrice,
  stopPrice,
  targetPrice,
  className,
}) => {
  const floor = Math.min(stopPrice, currentPrice * 0.92);
  const ceiling = Math.max(targetPrice, currentPrice * 1.08);
  const span = Math.max(ceiling - floor, 0.01);

  const currentPct = Math.min(Math.max(((currentPrice - floor) / span) * 100, 5), 95);
  const upsidePct = ((ceiling - currentPrice) / currentPrice) * 100;
  const downsidePct = ((currentPrice - floor) / currentPrice) * 100;
  const rrRatio = downsidePct > 0 ? (upsidePct / downsidePct).toFixed(2) : "2.50";

  return (
    <div className={cn("glass-panel rounded-xl p-3 flex flex-col gap-2.5 select-none font-mono", className)}>
      {/* Row 1: Top Bar & Telemetry Header */}
      <div className="flex items-center justify-between text-xs">
        <div className="flex items-center gap-1.5 text-slate-300">
          <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 shadow-[0_0_6px_rgba(6,182,212,0.8)]" />
          <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-300">Statistical Bounds</span>
          <span className="text-[10px] text-slate-500 hidden sm:inline">(GARCH 1,1)</span>
        </div>
        <div className="px-2 py-0.5 rounded-md bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-bold text-[11px] tracking-wide shadow-[0_0_10px_rgba(6,182,212,0.25)] flex items-center gap-1 shrink-0">
          <Zap className="w-3 h-3 text-cyan-400" />
          <span>{rrRatio}x R:R</span>
        </div>
      </div>

      {/* Visual Slider Bar with Pulse Ring Marker */}
      <div
        role="meter"
        aria-label={`Risk Reward Profile: Current ₹${currentPrice.toFixed(2)}, Stop Loss ₹${floor.toFixed(2)}, Target ₹${ceiling.toFixed(2)}, Risk Reward Ratio ${rrRatio} to 1`}
        aria-valuenow={currentPrice}
        aria-valuemin={floor}
        aria-valuemax={ceiling}
        className="relative h-2.5 w-full rounded-full bg-black/60 p-[1px] border border-white/[0.08] flex items-center overflow-visible"
      >
        {/* Risk Zone (Downside) */}
        <div
          style={{ width: `${currentPct}%` }}
          className="h-full rounded-l-full bg-gradient-to-r from-rose-500/60 via-rose-500/30 to-slate-700/40"
        />

        {/* Reward Zone (Upside) */}
        <div
          style={{ width: `${100 - currentPct}%` }}
          className="h-full rounded-r-full bg-gradient-to-r from-slate-700/40 via-cyan-500/40 to-emerald-500/70"
        />

        {/* Current Spot Indicator with Pulse Ring */}
        <motion.div
          layout
          initial={false}
          animate={{ left: `${currentPct}%` }}
          transition={{ type: "spring", stiffness: 300, damping: 28 }}
          className="absolute -top-1 -bottom-1 -ml-1.5 w-3 flex items-center justify-center z-10 pointer-events-none"
        >
          <span className="absolute w-4 h-4 rounded-full bg-cyan-400 opacity-75 animate-ping" />
          <span className="w-2.5 h-4.5 rounded-full bg-white shadow-[0_0_12px_#38bdf8] border border-cyan-300" />
        </motion.div>
      </div>

      {/* Row 2: Bottom Metrics (Floor on left, Target on right) */}
      <div className="flex items-center justify-between text-[11px] pt-0.5">
        <div className="flex items-center gap-1 text-rose-400 whitespace-nowrap">
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400 shrink-0" />
          <span className="text-slate-400 text-[10px]">Floor (95%):</span>
          <strong className="text-white font-mono tabular-nums">₹{floor.toFixed(2)}</strong>
          <span className="text-rose-400 text-[10px] tabular-nums font-semibold">(-{downsidePct.toFixed(1)}%)</span>
        </div>

        <div className="flex items-center gap-1 text-emerald-400 whitespace-nowrap">
          <Target className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
          <span className="text-slate-400 text-[10px]">Target (80%):</span>
          <strong className="text-white font-mono tabular-nums">₹{ceiling.toFixed(2)}</strong>
          <span className="text-emerald-400 text-[10px] tabular-nums font-semibold">(+{upsidePct.toFixed(1)}%)</span>
        </div>
      </div>
    </div>
  );
};

export default RiskRewardVectorBar;
