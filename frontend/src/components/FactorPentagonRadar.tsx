"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";

interface FactorRadarProps {
  roe?: number | null;          // e.g. 0 to 40+
  debtToEquity?: number | null; // e.g. 0 to 2.0 (inverted: lower is better)
  opm?: number | null;          // e.g. 0 to 35+
  momentum20d?: number | null;  // e.g. -15 to +15 (excess_ret_20d * 100)
  conviction?: number | null;   // 0 to 100
  className?: string;
}

export const FactorPentagonRadar: React.FC<FactorRadarProps> = ({
  roe,
  debtToEquity,
  opm,
  momentum20d,
  conviction,
  className,
}) => {
  const [hoveredIdx, setHoveredIdx] = useState<number | null>(null);

  const size = 220;
  const center = size / 2;
  const radius = 68;

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

  return (
    <div className={cn("relative flex flex-col items-center justify-center select-none w-full", className)}>
      <svg
        viewBox={`0 0 ${size} ${size}`}
        className="w-[195px] h-[195px] overflow-visible"
      >
        <defs>
          <radialGradient id="radarPentagonGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.35" />
            <stop offset="70%" stopColor="#10b981" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.05" />
          </radialGradient>

          <filter id="glowFilter" x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Concentric Web Rings (5-axis polygon spiderweb) */}
        {[0.25, 0.5, 0.75, 1.0].map((ring) => (
          <polygon
            key={ring}
            points={[0, 1, 2, 3, 4].map((i) => getPointStr(i, ring)).join(" ")}
            fill="none"
            stroke="rgba(255, 255, 255, 0.08)"
            strokeWidth="1"
            strokeDasharray={ring < 1.0 ? "2 3" : undefined}
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

        {/* Morphing Data Pentagon Polygon */}
        <motion.polygon
          initial={false}
          animate={{ points: polygonPoints }}
          transition={{ type: "spring", stiffness: 240, damping: 24 }}
          fill="url(#radarPentagonGlow)"
          stroke="#22d3ee"
          strokeWidth="1.75"
          filter="url(#glowFilter)"
        />

        {/* Interactive Vertex Nodes */}
        {values.map((v, i) => {
          const [vx, vy] = getPoint(i, v);
          const isHovered = hoveredIdx === i;

          return (
            <g
              key={i}
              onMouseEnter={() => setHoveredIdx(i)}
              onMouseLeave={() => setHoveredIdx(null)}
              className="cursor-pointer"
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
      <div className="h-5 flex items-center justify-center">
        <AnimatePresence mode="wait">
          {hoveredIdx !== null ? (
            <motion.div
              key={hoveredIdx}
              initial={{ opacity: 0, y: 3 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -3 }}
              className="flex items-center gap-1.5 px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-[10px] font-mono text-cyan-200 shadow-[0_0_10px_rgba(6,182,212,0.3)]"
            >
              <span className="font-bold text-white">{labels[hoveredIdx]}:</span>
              <span className="tabular-nums text-cyan-300 font-semibold">{rawValues[hoveredIdx]}</span>
            </motion.div>
          ) : (
            <span className="text-[10px] font-mono text-slate-500">
              Hover axis for factor telemetry
            </span>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
};

export default FactorPentagonRadar;
