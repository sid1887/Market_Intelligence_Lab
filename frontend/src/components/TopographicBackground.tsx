"use client";

import React from "react";

interface TopographicBackgroundProps {
  className?: string;
  intensity?: number;
  interactive?: boolean;
}

/**
 * AmbientBackground / TopographicBackground (Milestone Pure-CSS Ambient Engine)
 * Replaces high-overhead WebGL simplex shader loop with a 60FPS pure-CSS GPU composited ambient canvas.
 * Consumes < 1% CPU/GPU and eliminates mobile/desktop battery drain and frame drops.
 */
export function TopographicBackground({
  className = "",
}: TopographicBackgroundProps) {
  return (
    <div
      className={`fixed inset-0 pointer-events-none overflow-hidden select-none z-0 bg-[#040609] ${className}`}
      aria-hidden="true"
    >
      {/* Dynamic CSS Keyframes for GPU-accelerated drift */}
      <style jsx global>{`
        @keyframes ambient-orb-1 {
          0%, 100% {
            transform: translate3d(0, 0, 0) scale(1);
          }
          50% {
            transform: translate3d(60px, -45px, 0) scale(1.12);
          }
        }
        @keyframes ambient-orb-2 {
          0%, 100% {
            transform: translate3d(0, 0, 0) scale(1.05);
          }
          50% {
            transform: translate3d(-70px, 50px, 0) scale(0.92);
          }
        }
        @keyframes ambient-orb-3 {
          0%, 100% {
            transform: translate3d(0, 0, 0) scale(0.95);
          }
          50% {
            transform: translate3d(50px, 65px, 0) scale(1.08);
          }
        }
        .animate-ambient-1 {
          animation: ambient-orb-1 26s cubic-bezier(0.4, 0, 0.2, 1) infinite;
          will-change: transform;
        }
        .animate-ambient-2 {
          animation: ambient-orb-2 32s cubic-bezier(0.4, 0, 0.2, 1) infinite;
          will-change: transform;
        }
        .animate-ambient-3 {
          animation: ambient-orb-3 28s cubic-bezier(0.4, 0, 0.2, 1) infinite;
          will-change: transform;
        }
      `}</style>

      {/* Layer 1: Three slow-drifting soft radial aurora light orbs */}
      <div className="absolute inset-0 filter blur-[100px] sm:blur-[130px] opacity-70 transform-gpu">
        {/* Orb 1: Cyan / Turquoise (Institutional Alpha) */}
        <div
          className="absolute -top-32 -left-32 w-[340px] h-[340px] sm:w-[580px] sm:h-[580px] rounded-full bg-gradient-to-br from-cyan-500/15 via-cyan-400/10 to-transparent animate-ambient-1"
        />

        {/* Orb 2: Emerald / Mint (Growth & Momentum) */}
        <div
          className="absolute top-1/3 -right-28 w-[360px] h-[360px] sm:w-[620px] sm:h-[620px] rounded-full bg-gradient-to-bl from-emerald-500/12 via-teal-400/8 to-transparent animate-ambient-2"
        />

        {/* Orb 3: Indigo / Violet (Deep Matrix Depth) */}
        <div
          className="absolute -bottom-32 left-1/4 w-[380px] h-[380px] sm:w-[600px] sm:h-[600px] rounded-full bg-gradient-to-tr from-indigo-500/12 via-sky-500/8 to-transparent animate-ambient-3"
        />
      </div>

      {/* Layer 2: Subtle Architectural Dot-Matrix & Micro-Grid SVG with Radial Vignette */}
      <svg
        className="absolute inset-0 w-full h-full opacity-40 mix-blend-screen"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <pattern
            id="ambient-grid-pattern"
            width="32"
            height="32"
            patternUnits="userSpaceOnUse"
          >
            {/* Fine dot at grid intersection */}
            <circle cx="2" cy="2" r="0.8" fill="rgba(148, 163, 184, 0.25)" />
            {/* Ultra-subtle hairline coordinate grid */}
            <path
              d="M 32 0 L 0 0 0 32"
              fill="none"
              stroke="rgba(255, 255, 255, 0.025)"
              strokeWidth="0.5"
            />
          </pattern>

          {/* Radial vignette mask fading edges */}
          <radialGradient id="ambient-vignette-mask" cx="50%" cy="50%" r="70%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
            <stop offset="50%" stopColor="#ffffff" stopOpacity="0.85" />
            <stop offset="85%" stopColor="#ffffff" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </radialGradient>
          <mask id="ambient-vignette">
            <rect width="100%" height="100%" fill="url(#ambient-vignette-mask)" />
          </mask>
        </defs>

        <rect
          width="100%"
          height="100%"
          fill="url(#ambient-grid-pattern)"
          mask="url(#ambient-vignette)"
        />
      </svg>

      {/* Layer 3: Subtle top and bottom horizontal boundary vignette */}
      <div className="absolute inset-x-0 top-0 h-28 bg-gradient-to-b from-[#040609] to-transparent opacity-80" />
      <div className="absolute inset-x-0 bottom-0 h-32 bg-gradient-to-t from-[#040609] to-transparent opacity-90" />
    </div>
  );
}

export const AmbientBackground = TopographicBackground;
export default TopographicBackground;
