"use client";

import React from "react";
import { motion } from "framer-motion";

interface RiskRewardProps {
  currentPrice: number;
  stopPrice: number;   // e.g. Lower 95% CI or 200 SMA floor
  targetPrice: number; // e.g. Upper 80% CI objective
}

export const RiskRewardVectorBar: React.FC<RiskRewardProps> = ({
  currentPrice,
  stopPrice,
  targetPrice,
}) => {
  const floor = Math.min(stopPrice, currentPrice * 0.92);
  const ceiling = Math.max(targetPrice, currentPrice * 1.08);
  const span = Math.max(ceiling - floor, 0.01);

  const currentPct = Math.min(Math.max(((currentPrice - floor) / span) * 100, 5), 95);
  const upsidePct = ((ceiling - currentPrice) / currentPrice) * 100;
  const downsidePct = ((currentPrice - floor) / currentPrice) * 100;
  const rrRatio = downsidePct > 0 ? (upsidePct / downsidePct).toFixed(2) : "2.50";

  return (
    <div className="glass-panel rounded-lg p-3 flex flex-col gap-2">
      <div className="flex items-center justify-between text-[10px] font-mono-tabular">
        <span className="text-rose-400">
          FLOOR ₹{floor.toFixed(2)}{" "}
          <span className="text-rose-500 opacity-80">(-{downsidePct.toFixed(1)}%)</span>
        </span>
        <span className="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 font-semibold tracking-wide">
          {rrRatio}× R:R
        </span>
        <span className="text-emerald-400">
          TARGET ₹{ceiling.toFixed(2)}{" "}
          <span className="text-emerald-500 opacity-80">(+{upsidePct.toFixed(1)}%)</span>
        </span>
      </div>

      {/* Track bar */}
      <div className="relative h-2 w-full rounded-full bg-slate-900/80 overflow-hidden">
        {/* Downside zone */}
        <div
          style={{ width: `${currentPct}%` }}
          className="absolute left-0 top-0 bottom-0 bg-gradient-to-r from-rose-600/50 to-slate-700/30 rounded-l-full"
        />
        {/* Upside zone */}
        <div
          style={{ left: `${currentPct}%`, right: 0 }}
          className="absolute top-0 bottom-0 bg-gradient-to-r from-cyan-600/40 to-emerald-500/60 rounded-r-full"
        />
        {/* Current price needle */}
        <motion.div
          layout
          initial={false}
          animate={{ left: `calc(${currentPct}% - 3px)` }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
          className="absolute top-0 bottom-0 w-1.5 bg-white rounded-full shadow-[0_0_8px_2px_rgba(255,255,255,0.6)]"
        />
      </div>

      <div className="flex items-center justify-between text-[9px] font-mono text-slate-500">
        <span>95% TAIL RISK FLOOR</span>
        <span>CURRENT ₹{currentPrice.toFixed(2)}</span>
        <span>80% CONE TARGET</span>
      </div>
    </div>
  );
};
