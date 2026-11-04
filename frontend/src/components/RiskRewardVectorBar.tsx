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
    <div className="glass-panel rounded-lg p-2.5 flex flex-col gap-1.5 select-none">
      <div className="flex items-center justify-between text-[10px] font-mono">
        <span className="text-rose-400">
          TAIL FLOOR ₹{floor.toFixed(2)} (-{downsidePct.toFixed(1)}%)
        </span>
        <span className="px-2 py-0.5 rounded bg-cyan-500/10 border border-cyan-500/20 text-cyan-300 font-semibold tracking-wide">
          {rrRatio}x R:R PROFILE
        </span>
        <span className="text-emerald-400">
          TARGET ₹{ceiling.toFixed(2)} (+{upsidePct.toFixed(1)}%)
        </span>
      </div>

      <div className="relative h-2 w-full rounded-full bg-slate-900 overflow-hidden flex">
        <div
          style={{ width: `${currentPct}%` }}
          className="h-full bg-gradient-to-r from-rose-500/40 to-slate-600/40"
        />
        <div
          style={{ width: `${100 - currentPct}%` }}
          className="h-full bg-gradient-to-r from-cyan-500/40 to-emerald-500/60"
        />
        <motion.div
          layout
          initial={false}
          animate={{ left: `${currentPct}%` }}
          transition={{ type: "spring", stiffness: 260, damping: 24 }}
          className="absolute top-0 bottom-0 w-1.5 -ml-0.5 bg-white rounded-full shadow-[0_0_10px_#fff]"
        />
      </div>
    </div>
  );
};
