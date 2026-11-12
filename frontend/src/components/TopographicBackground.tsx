"use client";

import React from "react";

interface TopographicBackgroundProps {
  className?: string;
  intensity?: number;
  interactive?: boolean;
}

/**
 * AmbientBackground / TopographicBackground (Zero-GPU-Overhead Ambient Engine)
 * Replaces high-overhead WebGL and heavy blur filters with a static CSS radial gradient canvas.
 * Consumes 0% CPU/GPU and eliminates compositor layer repaints and desktop/mobile freezing.
 */
export function TopographicBackground({
  className = "",
}: TopographicBackgroundProps) {
  return (
    <div
      className={`fixed inset-0 pointer-events-none overflow-hidden select-none z-0 ${className}`}
      style={{
        background: "radial-gradient(circle at 50% 0%, #0d1527 0%, #040609 70%)",
      }}
      aria-hidden="true"
    >
      {/* Subtle Architectural Dot-Matrix & Micro-Grid SVG */}
      <svg
        className="absolute inset-0 w-full h-full opacity-30"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern
            id="ambient-grid-pattern"
            width="32"
            height="32"
            patternUnits="userSpaceOnUse"
          >
            <circle cx="2" cy="2" r="0.8" fill="rgba(148, 163, 184, 0.2)" />
            <path
              d="M 32 0 L 0 0 0 32"
              fill="none"
              stroke="rgba(255, 255, 255, 0.02)"
              strokeWidth="0.5"
            />
          </pattern>
        </defs>

        <rect width="100%" height="100%" fill="url(#ambient-grid-pattern)" />
      </svg>

      {/* Subtle edge vignettes */}
      <div className="absolute inset-x-0 top-0 h-24 bg-gradient-to-b from-[#040609] to-transparent opacity-80" />
      <div className="absolute inset-x-0 bottom-0 h-28 bg-gradient-to-t from-[#040609] to-transparent opacity-90" />
    </div>
  );
}

export const AmbientBackground = TopographicBackground;
export default TopographicBackground;
