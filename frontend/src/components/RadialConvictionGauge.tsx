"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface RadialConvictionGaugeProps {
  score?: number | null;
  radius?: number;
  strokeWidth?: number;
  className?: string;
  label?: string;
}

export const RadialConvictionGauge: React.FC<RadialConvictionGaugeProps> = ({
  score,
  radius = 44,
  strokeWidth = 6,
  className,
  label,
}) => {
  const normalizedRadius = radius - strokeWidth * 2;
  const circumference = normalizedRadius * 2 * Math.PI;
  const numericScore =
    typeof score === "number" && !isNaN(score)
      ? Math.max(0, Math.min(100, Math.round(score * 10) / 10))
      : null;
  const strokeDashoffset =
    numericScore !== null
      ? circumference - (numericScore / 100) * circumference
      : circumference;

  // Dynamic color thresholds
  const getColorScheme = (val: number | null) => {
    if (val === null) return { text: "text-slate-400", gradFrom: "#475569", gradTo: "#334155", glow: "none" };
    if (val >= 80) return { text: "text-emerald-400", gradFrom: "#10b981", gradTo: "#34d399", glow: "rgba(16,185,129,0.5)" };
    if (val >= 65) return { text: "text-cyan-400", gradFrom: "#06b6d4", gradTo: "#38bdf8", glow: "rgba(6,182,212,0.5)" };
    if (val >= 45) return { text: "text-amber-400", gradFrom: "#f59e0b", gradTo: "#fbbf24", glow: "rgba(245,158,11,0.4)" };
    return { text: "text-rose-400", gradFrom: "#f43f5e", gradTo: "#fb7185", glow: "rgba(244,63,94,0.45)" };
  };

  const scheme = getColorScheme(numericScore);
  const gradId = `radial-conviction-${radius}-${Math.floor(numericScore ?? 0)}`;

  return (
    <div className={cn("relative flex items-center justify-center select-none", className)}>
      <svg
        height={radius * 2}
        width={radius * 2}
        className="transform -rotate-90"
        style={{
          filter: numericScore !== null && scheme.glow !== "none" ? `drop-shadow(0 0 10px ${scheme.glow})` : "none",
        }}
      >
        <defs>
          <linearGradient id={gradId} x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor={scheme.gradFrom} />
            <stop offset="100%" stopColor={scheme.gradTo} />
          </linearGradient>
        </defs>

        {/* Background Track */}
        <circle
          stroke="rgba(255, 255, 255, 0.08)"
          fill="transparent"
          strokeWidth={strokeWidth}
          r={normalizedRadius}
          cx={radius}
          cy={radius}
        />

        {/* Animated Progress Arc */}
        {numericScore !== null && (
          <motion.circle
            stroke={`url(#${gradId})`}
            fill="transparent"
            strokeWidth={strokeWidth}
            strokeDasharray={`${circumference} ${circumference}`}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset }}
            transition={{ duration: 1.0, ease: [0.16, 1, 0.3, 1] }}
            strokeLinecap="round"
            r={normalizedRadius}
            cx={radius}
            cy={radius}
          />
        )}
      </svg>

      <div className="absolute flex flex-col items-center justify-center text-center font-mono">
        <span className={cn("text-lg font-bold tabular-nums tracking-tighter drop-shadow-sm", scheme.text)}>
          {numericScore !== null ? numericScore.toFixed(0) : "—"}
        </span>
        <span className="text-[9px] uppercase font-bold text-slate-500 tracking-wider -mt-1">
          {label || (numericScore !== null ? "/100" : "N/A")}
        </span>
      </div>
    </div>
  );
};

export default RadialConvictionGauge;
