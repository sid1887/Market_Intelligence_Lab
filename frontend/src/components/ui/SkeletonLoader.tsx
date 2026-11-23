"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface SkeletonLineProps {
  width?: string;
  height?: string;
  className?: string;
  delay?: number;
}

export function SkeletonLine({
  width = "w-full",
  height = "h-4",
  className,
  delay = 0,
}: SkeletonLineProps) {
  return (
    <div
      className={cn(
        "rounded-md overflow-hidden relative bg-slate-800/80",
        width,
        height,
        className
      )}
    >
      <motion.div
        className="absolute inset-0 bg-gradient-to-r from-transparent via-slate-600/25 to-transparent"
        animate={{ x: ["-100%", "100%"] }}
        transition={{
          duration: 1.6,
          repeat: Infinity,
          ease: "linear",
          delay,
        }}
      />
    </div>
  );
}

export function SkeletonStockInspector() {
  return (
    <div className="p-4 space-y-4 animate-in fade-in duration-200">
      {/* Header */}
      <div className="space-y-2">
        <SkeletonLine width="w-20" height="h-3" delay={0} />
        <SkeletonLine width="w-48" height="h-9" delay={0.05} />
        <SkeletonLine width="w-28" height="h-4" delay={0.1} />
      </div>
      {/* Verdict badge */}
      <SkeletonLine width="w-24" height="h-7" className="rounded-full" delay={0.15} />
      {/* Chart placeholder */}
      <SkeletonLine width="w-full" height="h-[220px]" className="rounded-xl" delay={0.2} />
      {/* Metrics grid */}
      <div className="grid grid-cols-2 gap-2">
        {[0, 1, 2, 3].map((i) => (
          <div key={i} className="rounded-xl bg-slate-800/60 p-3 space-y-1.5 border border-white/[0.04]">
            <SkeletonLine width="w-16" height="h-2.5" delay={0.25 + i * 0.03} />
            <SkeletonLine width="w-20" height="h-5" delay={0.28 + i * 0.03} />
          </div>
        ))}
      </div>
    </div>
  );
}

export function SkeletonBentoCard() {
  return (
    <div className="rounded-2xl bg-[#06090f]/75 border border-white/[0.08] p-4 space-y-2">
      <SkeletonLine width="w-20" height="h-3" />
      <SkeletonLine width="w-28" height="h-7" delay={0.05} />
      <SkeletonLine width="w-16" height="h-3" delay={0.1} />
    </div>
  );
}
