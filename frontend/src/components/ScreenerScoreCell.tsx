import React from "react";
import { motion } from "framer-motion";

export const ScreenerScoreCell: React.FC<{ score: number }> = ({ score }) => {
  const normalized = Math.min(Math.max(score, 0), 100);
  
  const getBadgeColor = (val: number) => {
    if (val >= 80) return "text-emerald-400 bg-emerald-500/10 border-emerald-500/20";
    if (val >= 60) return "text-cyan-400 bg-cyan-500/10 border-cyan-500/20";
    if (val >= 40) return "text-slate-300 bg-slate-800 border-slate-700";
    return "text-rose-400 bg-rose-500/10 border-rose-500/20";
  };

  const getBarGradient = (val: number) => {
    if (val >= 80) return "from-emerald-500 to-teal-400";
    if (val >= 60) return "from-cyan-500 to-blue-500";
    return "from-slate-600 to-slate-400";
  };

  return (
    <div className="flex items-center space-x-2.5 min-w-[120px] justify-end">
      <span className={`font-mono text-xs font-semibold px-1.5 py-0.5 rounded border tabular-nums ${getBadgeColor(normalized)}`}>{normalized.toFixed(1)}</span>
      <div className="w-16 h-1.5 bg-slate-800/80 rounded-full overflow-hidden p-[1px]">
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
