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
    <div className={cn("glass-panel rounded-xl p-3 flex flex-col gap-2 select-none font-mono", className)}>
      {/* Header Telemetry */}
      <div className="flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-1.5 text-rose-400">
          <ShieldAlert className="w-3 h-3 text-rose-400 shrink-0" />
          <span>95% TAIL FLOOR:</span>
          <strong className="text-white tabular-nums">₹{floor.toFixed(2)}</strong>
          <span className="text-rose-400 tabular-nums">(-{downsidePct.toFixed(1)}%)</span>
        </div>

        <div className="px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-bold tracking-wide shadow-[0_0_10px_rgba(6,182,212,0.25)] flex items-center gap-1">
          <Zap className="w-2.5 h-2.5 text-cyan-400" />
          <span>{rrRatio}x R:R</span>
        </div>

        <div className="flex items-center gap-1.5 text-emerald-400">
          <Target className="w-3 h-3 text-emerald-400 shrink-0" />
          <span>80% TARGET:</span>
          <strong className="text-white tabular-nums">₹{ceiling.toFixed(2)}</strong>
          <span className="text-emerald-400 tabular-nums">(+{upsidePct.toFixed(1)}%)</span>
        </div>
      </div>

      {/* Vector Bar with Pulse Ring Marker */}
      <div className="relative h-3 w-full rounded-full bg-black/60 p-[1px] border border-white/[0.08] flex items-center overflow-visible">
        {/* Risk Zone (Downside) */}
        <div
          style={{ width: `${currentPct}%` }}
          className="h-full rounded-l-full bg-gradient-to-r from-rose-500/50 via-rose-500/25 to-slate-700/40"
        />

        {/* Reward Zone (Upside) */}
        <div
          style={{ width: `${100 - currentPct}%` }}
          className="h-full rounded-r-full bg-gradient-to-r from-slate-700/40 via-cyan-500/30 to-emerald-500/60"
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
          <span className="w-2.5 h-5 rounded-full bg-white shadow-[0_0_12px_#38bdf8] border border-cyan-300" />
        </motion.div>
      </div>

      {/* Footnote */}
      <div className="flex items-center justify-between text-[9px] text-slate-500">
        <span>GARCH(1,1) Volatility Tail Envelope</span>
        <span className="text-slate-400">Current Spot: ₹{currentPrice.toFixed(2)}</span>
      </div>
    </div>
  );
};

export default RiskRewardVectorBar;
