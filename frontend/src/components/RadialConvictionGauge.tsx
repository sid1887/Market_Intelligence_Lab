import React from "react";
import { motion } from "framer-motion";

export const RadialConvictionGauge: React.FC<{ score?: number | null }> = ({ score }) => {
  const radius = 38, stroke = 6;
  const normalizedRadius = radius - stroke * 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const numericScore = typeof score === "number" && !isNaN(score) ? Math.max(0, Math.min(100, score)) : null;
  const strokeDashoffset = numericScore !== null ? circumference - (numericScore / 100) * circumference : circumference;

  return (
    <div className="relative flex items-center justify-center">
      <svg height={radius * 2} width={radius * 2} className="transform -rotate-90">
        <circle stroke="rgba(51, 65, 85, 0.4)" fill="transparent" strokeWidth={stroke} r={normalizedRadius} cx={radius} cy={radius} />
        {numericScore !== null && (
          <motion.circle
            stroke="url(#cyanEmeraldGrad)" fill="transparent" strokeWidth={stroke} strokeDasharray={`${circumference} ${circumference}`}
            initial={{ strokeDashoffset: circumference }} animate={{ strokeDashoffset }} transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
            strokeLinecap="round" r={normalizedRadius} cx={radius} cy={radius}
          />
        )}
        <defs>
          <linearGradient id="cyanEmeraldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#06b6d4" /><stop offset="100%" stopColor="#10b981" />
          </linearGradient>
        </defs>
      </svg>
      <div className="absolute flex flex-col items-center justify-center text-center">
        <span className="font-mono text-base font-bold text-white tabular-nums tracking-tight">
          {numericScore !== null ? numericScore : "—"}
        </span>
        <span className="text-[9px] uppercase font-mono text-slate-400 -mt-1">
          {numericScore !== null ? "/100" : "N/A"}
        </span>
      </div>
    </div>
  );
};
