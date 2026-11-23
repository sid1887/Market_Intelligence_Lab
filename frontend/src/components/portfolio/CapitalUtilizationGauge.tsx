"use client";

import React from "react";
import { motion, useReducedMotion } from "framer-motion";

interface CapitalUtilizationGaugeProps {
  utilized: number;
  total: number;
  className?: string;
}

export function CapitalUtilizationGauge({
  utilized,
  total,
  className = "",
}: CapitalUtilizationGaugeProps) {
  const shouldReduceMotion = useReducedMotion();
  const pct = total > 0 ? Math.min(Math.max(utilized / total, 0), 1) : 0;
  const radius = 38;
  const circumference = 2 * Math.PI * radius;
  const strokeOffset = circumference * (1 - pct);

  return (
    <div className={`relative flex items-center justify-center ${className}`}>
      <svg width="88" height="88" viewBox="0 0 96 96" className="transform -rotate-90">
        {/* Background track */}
        <circle
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          stroke="rgba(255, 255, 255, 0.08)"
          strokeWidth="6"
        />
        {/* Animated fill circle */}
        <motion.circle
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          stroke={pct > 0.9 ? "rgba(244, 63, 94, 0.85)" : pct > 0.75 ? "rgba(245, 158, 11, 0.85)" : "rgba(6, 182, 212, 0.85)"}
          strokeWidth="6"
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: strokeOffset }}
          transition={
            shouldReduceMotion
              ? { duration: 0 }
              : { duration: 1.1, ease: [0.16, 1, 0.3, 1], delay: 0.2 }
          }
        />
      </svg>
      {/* Centered label */}
      <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
        <span className="font-mono text-sm font-bold text-white tabular-nums">
          {Math.round(pct * 100)}%
        </span>
        <span className="text-[9px] font-mono text-slate-400 uppercase tracking-tighter">
          Deployed
        </span>
      </div>
    </div>
  );
}
