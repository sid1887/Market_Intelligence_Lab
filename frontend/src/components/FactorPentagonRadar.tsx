"use client";

import React from "react";
import { motion } from "framer-motion";

interface FactorRadarProps {
  roe: number;          // e.g. 0 to 40+
  debtToEquity: number; // e.g. 0 to 2.0 (inverted: lower is better)
  opm: number;          // e.g. 0 to 35+
  momentum20d: number;  // e.g. -15 to +15 (as percent: excess_ret_20d * 100)
  conviction: number;   // 0 to 100
}

export const FactorPentagonRadar: React.FC<FactorRadarProps> = ({
  roe,
  debtToEquity,
  opm,
  momentum20d,
  conviction,
}) => {
  const size = 180;
  const center = size / 2;
  const radius = 64;

  // Normalize metrics to 0.15–1.0 scale
  const normRoe = Math.min(Math.max((roe || 0) / 35, 0.15), 1);
  const normSafety = Math.min(Math.max(1 - (debtToEquity || 0) / 1.8, 0.15), 1);
  const normOpm = Math.min(Math.max((opm || 0) / 30, 0.15), 1);
  const normMom = Math.min(Math.max(((momentum20d || 0) + 12) / 24, 0.15), 1);
  const normConv = Math.min(Math.max((conviction || 50) / 100, 0.15), 1);

  const values = [normRoe, normSafety, normOpm, normMom, normConv];
  const labels = ["ROE", "SAFETY", "OPM", "TREND", "SCORE"];

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
    <div className="relative flex items-center justify-center select-none">
      <svg width={size} height={size} className="overflow-visible">
        <defs>
          <radialGradient id="radarGlow" cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.45" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.1" />
          </radialGradient>
          <filter id="radarBloom">
            <feGaussianBlur stdDeviation="3" result="blur" />
            <feComposite in="SourceGraphic" in2="blur" operator="over" />
          </filter>
        </defs>

        {/* Reference concentric pentagons */}
        {[0.33, 0.66, 1].map((ring) => (
          <polygon
            key={ring}
            points={[0, 1, 2, 3, 4].map((i) => getPointStr(i, ring)).join(" ")}
            fill="none"
            stroke="rgba(148, 163, 184, 0.10)"
            strokeWidth="1"
          />
        ))}

        {/* Axis spokes & labels */}
        {[0, 1, 2, 3, 4].map((i) => {
          const [ex, ey] = getPoint(i, 1);
          const [lx, ly] = getPoint(i, 1.28);
          return (
            <g key={i}>
              <line
                x1={center}
                y1={center}
                x2={ex}
                y2={ey}
                stroke="rgba(148, 163, 184, 0.09)"
                strokeWidth="1"
              />
              <text
                x={lx}
                y={ly}
                textAnchor="middle"
                dominantBaseline="middle"
                fontSize="8"
                fontFamily="var(--font-jetbrains-mono), monospace"
                letterSpacing="0.08em"
                fill="rgba(148, 163, 184, 0.55)"
              >
                {labels[i]}
              </text>
            </g>
          );
        })}

        {/* Glow duplicate (bloom effect) */}
        <motion.polygon
          initial={false}
          animate={{ points: polygonPoints }}
          transition={{ type: "spring", stiffness: 220, damping: 22 }}
          fill="url(#radarGlow)"
          stroke="#22d3ee"
          strokeWidth="4"
          opacity="0.15"
          filter="url(#radarBloom)"
        />

        {/* Main morphing data polygon */}
        <motion.polygon
          initial={false}
          animate={{ points: polygonPoints }}
          transition={{ type: "spring", stiffness: 220, damping: 22 }}
          fill="url(#radarGlow)"
          stroke="#22d3ee"
          strokeWidth="1.75"
        />

        {/* Vertex dots */}
        {values.map((v, i) => {
          const [px, py] = getPoint(i, v);
          return (
            <motion.circle
              key={i}
              animate={{ cx: px, cy: py }}
              transition={{ type: "spring", stiffness: 220, damping: 22 }}
              r="2.5"
              fill="#06b6d4"
              opacity="0.9"
            />
          );
        })}
      </svg>
    </div>
  );
};
