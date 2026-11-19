"use client";

import React from "react";

export function TopographicBackground() {
  return (
    <div
      aria-hidden="true"
      className="fixed inset-0 pointer-events-none z-0 overflow-hidden select-none"
    >
      {/* Ambient Cyber Luminous Gradients */}
      <div
        className="absolute inset-0 opacity-[0.035] transition-opacity duration-1000"
        style={{
          backgroundImage: `
            radial-gradient(ellipse 60% 50% at 15% 20%, rgba(6, 182, 212, 0.5) 0%, transparent 70%),
            radial-gradient(ellipse 50% 50% at 85% 15%, rgba(99, 102, 241, 0.45) 0%, transparent 70%),
            radial-gradient(ellipse 60% 40% at 50% 90%, rgba(16, 185, 129, 0.3) 0%, transparent 70%)
          `,
        }}
      />

      {/* Subtle Quant Grid Texture with Vignette Falloff */}
      <div
        className="absolute inset-0 opacity-[0.025]"
        style={{
          backgroundImage: `
            linear-gradient(to right, rgba(255, 255, 255, 0.15) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.15) 1px, transparent 1px)
          `,
          backgroundSize: "48px 48px",
          maskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 40%, transparent 100%)",
          WebkitMaskImage: "radial-gradient(ellipse 70% 60% at 50% 40%, black 40%, transparent 100%)",
        }}
      />
    </div>
  );
}

export const AmbientBackground = TopographicBackground;
export default TopographicBackground;
