"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export const ScreenerScoreCell: React.FC<{ score: number; className?: string }> = ({
  score,
  className,
}) => {
  const normalized = Math.min(Math.max(score, 0), 100);

  const getTextColor = (val: number) => {
    if (val >= 80) return "text-emerald-400";
    if (val >= 60) return "text-cyan-300";
    if (val >= 40) return "text-slate-300";
    return "text-rose-400";
  };

  const getBarGradient = (val: number) => {
    if (val >= 80) {
      return "from-cyan-400 via-teal-400 to-emerald-400 shadow-[0_0_10px_rgba(16,185,129,0.45)]";
    }
    if (val >= 60) {
      return "from-cyan-500 to-blue-400 shadow-[0_0_10px_rgba(6,182,212,0.45)]";
    }
    if (val >= 40) {
      return "from-slate-600 to-slate-400";
    }
    return "from-rose-600 to-rose-400 shadow-[0_0_8px_rgba(244,63,94,0.35)]";
  };

  return (
    <div className={cn("flex items-center space-x-2 min-w-[95px] justify-end select-none font-mono", className)}>
      <span className={cn("text-xs font-bold tabular-nums tracking-tight", getTextColor(normalized))}>
        {normalized.toFixed(1)}
      </span>
      <div className="w-14 h-1.5 bg-black/60 rounded-full overflow-hidden border border-white/[0.08] p-[1px]">
        <motion.div
          className={cn("h-full rounded-full bg-gradient-to-r transition-all", getBarGradient(normalized))}
          initial={{ width: 0 }}
          animate={{ width: `${normalized}%` }}
          transition={{ duration: 0.5, ease: "easeOut" }}
        />
      </div>
    </div>
  );
};

export default ScreenerScoreCell;
