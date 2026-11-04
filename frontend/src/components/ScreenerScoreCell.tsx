import React from "react";
import { motion } from "framer-motion";

export const ScreenerScoreCell: React.FC<{ score: number }> = ({ score }) => {
  const normalized = Math.min(Math.max(score, 0), 100);
  
  const getTextColor = (val: number) => {
    if (val >= 80) return "text-emerald-400";
    if (val >= 60) return "text-cyan-400";
    if (val >= 40) return "text-slate-300";
    return "text-rose-400";
  };

  const getBarGradient = (val: number) => {
    if (val >= 80) return "from-emerald-500/80 to-teal-400/80";
    if (val >= 60) return "from-cyan-500/80 to-blue-500/80";
    return "from-slate-600 to-slate-500";
  };

  return (
    <div className="flex items-center space-x-2 min-w-[95px] justify-end select-none">
      <span className={`font-mono text-xs font-semibold tabular-nums ${getTextColor(normalized)}`}>
        {normalized.toFixed(1)}
      </span>
      <div className="w-12 h-1 bg-slate-800/60 rounded-full overflow-hidden">
        <motion.div
          className={`h-full rounded-full bg-gradient-to-r ${getBarGradient(normalized)}`}
          initial={{ width: 0 }}
          animate={{ width: `${normalized}%` }}
          transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>
    </div>
  );
};
