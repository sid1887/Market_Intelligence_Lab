"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

export interface FactorRadarMetrics {
  roe?: number | null;          // e.g. 0 to 40+
  debtToEquity?: number | null; // e.g. 0 to 2.0 (inverted: lower is better)
  opm?: number | null;          // e.g. 0 to 35+
  momentum20d?: number | null;  // e.g. -15 to +15 (excess_ret_20d * 100)
  conviction?: number | null;   // 0 to 100
}

export interface FactorRadarProps extends FactorRadarMetrics {
  comparison?: FactorRadarMetrics & { label?: string };
  enableBenchmarkToggle?: boolean;
  className?: string;
}

// Default NSE 500 Median Baseline for comparison
const DEFAULT_BASELINE: FactorRadarMetrics & { label: string } = {
  roe: 15.0,
  debtToEquity: 0.65,
  opm: 16.5,
  momentum20d: 0.0,
  conviction: 50.0,
  label: "NSE 500 Benchmark",
};

export const FactorPentagonRadar: React.FC<FactorRadarProps> = ({
  roe,
  debtToEquity,
  opm,
  momentum20d,
  conviction,
  comparison,
  enableBenchmarkToggle = true,
  className,
}) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);
  const [showComparison, setShowComparison] = useState<boolean>(Boolean(comparison));

  const size = 220;
  const center = size / 2;
  const radius = 68;

  // Active baseline target (custom prop or default NSE 500 median)
  const activeComp = comparison || (enableBenchmarkToggle && showComparison ? DEFAULT_BASELINE : undefined);

  // Normalize metrics to 0.15 - 1.0 scale
  const normRoe = Math.min(Math.max((roe || 0) / 35, 0.15), 1);
  const normSafety = Math.min(Math.max(1 - (debtToEquity || 0) / 1.8, 0.15), 1);
  const normOpm = Math.min(Math.max((opm || 0) / 30, 0.15), 1);
  const normMom = Math.min(Math.max(((momentum20d || 0) + 12) / 24, 0.15), 1);
  const normConv = Math.min(Math.max((conviction || 50) / 100, 0.15), 1);

  const values = [normRoe, normSafety, normOpm, normMom, normConv];
  const labels = ["ROE", "SAFETY", "OPM", "MOMENTUM", "CONVICTION"];
  const rawValues = [
    roe !== null && roe !== undefined ? `${roe.toFixed(1)}%` : "—",
    debtToEquity !== null && debtToEquity !== undefined ? `${debtToEquity.toFixed(2)} D/E` : "—",
    opm !== null && opm !== undefined ? `${opm.toFixed(1)}%` : "—",
    momentum20d !== null && momentum20d !== undefined ? `${momentum20d > 0 ? "+" : ""}${momentum20d.toFixed(1)}%` : "—",
    conviction !== null && conviction !== undefined ? `${conviction.toFixed(0)}/100` : "—",
  ];

  // Comparison normalization
  const normCompRoe = activeComp ? Math.min(Math.max((activeComp.roe || 0) / 35, 0.15), 1) : 0.5;
  const normCompSafety = activeComp ? Math.min(Math.max(1 - (activeComp.debtToEquity || 0) / 1.8, 0.15), 1) : 0.5;
  const normCompOpm = activeComp ? Math.min(Math.max((activeComp.opm || 0) / 30, 0.15), 1) : 0.5;
  const normCompMom = activeComp ? Math.min(Math.max(((activeComp.momentum20d || 0) + 12) / 24, 0.15), 1) : 0.5;
  const normCompConv = activeComp ? Math.min(Math.max((activeComp.conviction || 50) / 100, 0.15), 1) : 0.5;

  const compValues = [normCompRoe, normCompSafety, normCompOpm, normCompMom, normCompConv];
  const rawCompValues = activeComp ? [
    activeComp.roe !== null && activeComp.roe !== undefined ? `${activeComp.roe.toFixed(1)}%` : "—",
    activeComp.debtToEquity !== null && activeComp.debtToEquity !== undefined ? `${activeComp.debtToEquity.toFixed(2)} D/E` : "—",
    activeComp.opm !== null && activeComp.opm !== undefined ? `${activeComp.opm.toFixed(1)}%` : "—",
    activeComp.momentum20d !== null && activeComp.momentum20d !== undefined ? `${activeComp.momentum20d > 0 ? "+" : ""}${activeComp.momentum20d.toFixed(1)}%` : "—",
    activeComp.conviction !== null && activeComp.conviction !== undefined ? `${activeComp.conviction.toFixed(0)}/100` : "—",
  ] : [];

  const getPoint = (index: number, scale: number): [number, number] => {
    const angle = (Math.PI * 2 * index) / 5 - Math.PI / 2;
    const x = center + radius * scale * Math.cos(angle);
    const y = center + radius * scale * Math.sin(angle);
    return [x, y];
  };

  const getPointStr = (index: number, scale: number): string => {
    const [x, y] = getPoint(index, scale);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  };

  const polygonPoints = values.map((v, i) => getPointStr(i, v)).join(" ");
  const comparisonPolygonPoints = compValues.map((v, i) => getPointStr(i, v)).join(" ");

  return (
    <div className={cn("relative flex flex-col items-center justify-center select-none w-full", className)}>
      <svg
        role="img"
        aria-label="Factor Quality Radar: ROE, Safety, OPM, Momentum, Conviction"
        viewBox={`0 0 ${size} ${size}`}
        className="w-[195px] h-[195px] overflow-visible"
      >
        <title>Factor Quality Radar</title>
        <desc>{`ROE: ${rawValues[0]}, Safety: ${rawValues[1]}, OPM: ${rawValues[2]}, Momentum: ${rawValues[3]}, Conviction: ${rawValues[4]}`}</desc>
        <defs>
          <radialGradient id="radarPentagonGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.35" />
            <stop offset="70%" stopColor="#10b981" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.05" />
          </radialGradient>
        </defs>

        {/* Concentric Web Rings (5-axis polygon spiderweb with spring entrance) */}
        {[0.25, 0.5, 0.75, 1.0].map((ring, i) => (
          <motion.polygon
            key={ring}
            points={[0, 1, 2, 3, 4].map((idx) => getPointStr(idx, ring)).join(" ")}
            fill="none"
            stroke="rgba(255, 255, 255, 0.08)"
            strokeWidth="1"
            strokeDasharray={ring < 1.0 ? "2 3" : undefined}
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            style={{ transformOrigin: `${center}px ${center}px` }}
            transition={{ delay: i * 0.06, type: "spring", stiffness: 220, damping: 22 }}
          />
        ))}

        {/* Axis Spokes & Typographic Labels */}
        {[0, 1, 2, 3, 4].map((i) => {
          const [endX, endY] = getPoint(i, 1);
          const [labelX, labelY] = getPoint(i, 1.28);
          const isHovered = hoveredIdx === i;

          return (
            <g key={i}>
              <line
                x1={center}
                y1={center}
                x2={endX}
                y2={endY}
                stroke={isHovered ? "rgba(6, 182, 212, 0.5)" : "rgba(255, 255, 255, 0.08)"}
                strokeWidth={isHovered ? "1.5" : "1"}
                className="transition-colors duration-200"
              />
              <text
                x={labelX}
                y={labelY}
                textAnchor="middle"
                dominantBaseline="central"
                className={cn(
                  "font-mono text-[9px] tracking-wider select-none transition-colors duration-200 font-bold",
                  isHovered ? "fill-cyan-300" : "fill-slate-400"
                )}
              >
                {labels[i]}
              </text>
            </g>
          );
        })}

        {/* Historical / Benchmark Comparison Polygon Overlay (L8) */}
        {showComparison && activeComp && (
          <motion.polygon
            initial={false}
            animate={{ points: comparisonPolygonPoints }}
            transition={{ type: "spring", stiffness: 240, damping: 24 }}
            fill="rgba(245, 158, 11, 0.08)"
            stroke="rgba(245, 158, 11, 0.75)"
            strokeWidth="1.5"
            strokeDasharray="4 3"
          />
        )}

        {/* Morphing Primary Data Pentagon Polygon */}
        <motion.polygon
          initial={{ scale: 0.85, opacity: 0 }}
          animate={{
            points: polygonPoints,
            scale: 1,
            opacity: 1,
            fillOpacity: (conviction ?? 0) >= 70 ? [0.65, 0.9, 0.65] : 0.75,
          }}
          transition={{
            type: "spring",
            stiffness: 240,
            damping: 24,
            fillOpacity: (conviction ?? 0) >= 70 ? { duration: 2.5, repeat: Infinity, ease: "easeInOut" } : undefined,
          }}
          style={{ transformOrigin: `${center}px ${center}px` }}
          fill="url(#radarPentagonGlow)"
          stroke="#22d3ee"
          strokeWidth="2"
        />

        {/* Comparison Vertex Nodes */}
        {showComparison && activeComp && compValues.map((v, i) => {
          const [vx, vy] = getPoint(i, v);
          return (
            <circle
              key={`comp-${i}`}
              cx={vx}
              cy={vy}
              r={2.5}
              fill="#f59e0b"
              stroke="#040609"
              strokeWidth="1"
            />
          );
        })}

        {/* Interactive Primary Vertex Nodes */}
        {values.map((v, i) => {
          const [vx, vy] = getPoint(i, v);
          const isHovered = hoveredIdx === i;

          return (
            <g
              key={i}
              role="button"
              tabIndex={0}
              aria-label={`${labels[i]}: ${rawValues[i]}`}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              onFocus={() => setHoveredIdx(i)}
              onBlur={() => setHoveredIdx(null)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setHoveredIdx(i);
                }
              }}
              className="cursor-pointer focus:outline-none"
            >
              <circle cx={vx} cy={vy} r={8} fill="transparent" />
              <motion.circle
                initial={false}
                animate={{ cx: vx, cy: vy, r: isHovered ? 4.5 : 3 }}
                transition={{ type: "spring", stiffness: 240, damping: 24 }}
                fill={isHovered ? "#38bdf8" : "#22d3ee"}
                stroke="#040609"
                strokeWidth="1.5"
                className="drop-shadow-[0_0_6px_#22d3ee]"
              />
            </g>
          );
        })}
      </svg>

      {/* Floating Vertex Tooltip */}
      <div className="h-5 flex items-center justify-center my-0.5">
        <AnimatePresence mode="wait">
          {hoveredIdx !== null ? (
            <motion.div
              key={hoveredIdx}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              className="flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-cyan-950/90 border border-cyan-500/40 text-[10px] font-mono text-cyan-200 shadow-[0_0_10px_rgba(6,182,212,0.3)]"
            >
              <span className="font-bold text-white">{labels[hoveredIdx]}:</span>
              <span className="tabular-nums text-cyan-300 font-semibold">{rawValues[hoveredIdx]}</span>
              {showComparison && activeComp && (
                <span className="text-amber-400 font-normal">
                  vs {rawCompValues[hoveredIdx]}
                </span>
              )}
            </motion.div>
          ) : (
            <span className="text-[10px] font-mono text-slate-500">
              Hover axis for factor telemetry
            </span>
          )}
        </AnimatePresence>
      </div>

      {/* Benchmark Overlay Toggle & Legend (L8) */}
      <div className="flex items-center justify-center gap-3 pt-1 border-t border-white/[0.04] w-full text-[9px] font-mono">
        <div className="flex items-center gap-1.5 text-cyan-400">
          <span className="w-2.5 h-1 bg-cyan-400 rounded-full" />
          <span>Active Stock</span>
        </div>

        <button
          onClick={() => setShowComparison(!showComparison)}
          title="Toggle Benchmark Overlay on Radar"
          className={cn(
            "flex items-center gap-1.5 px-1.5 py-0.5 rounded border transition-colors",
            showComparison
              ? "bg-amber-950/60 border-amber-500/40 text-amber-300 font-bold"
              : "border-white/[0.06] text-slate-500 hover:text-slate-300"
          )}
        >
          <span className="w-2.5 h-0.5 border-t border-amber-400 border-dashed" />
          <span>{activeComp?.label || "Benchmark"}</span>
        </button>
      </div>
    </div>
  );
};

export default FactorPentagonRadar;
