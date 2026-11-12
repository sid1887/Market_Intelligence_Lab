"use client";

import React, { useRef, useState } from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface BentoCardProps {
  title: string;
  value: string | number;
  delta?: string;
  isPositive?: boolean;
  subLabel?: string;
  badge?: string;
  icon?: React.ReactNode;
  delay?: number;
  className?: string;
  onClick?: () => void;
}

export function BentoCard({
  title,
  value,
  delta,
  isPositive,
  subLabel,
  badge,
  icon,
  delay = 0,
  className,
  onClick,
}: BentoCardProps) {
  const cardRef = useRef<HTMLDivElement>(null);
  const [mousePos, setMousePos] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [isHovered, setIsHovered] = useState(false);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    setMousePos({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
    });
  };

  // Semantic color scheme based on isPositive
  const semanticTheme =
    isPositive === true
      ? {
          spotlightBg: "rgba(16, 185, 129, 0.16)",
          spotlightBorder: "rgba(16, 185, 129, 0.6)",
          hoverBorder: "hover:border-emerald-500/50",
          hoverShadow: "hover:shadow-[0_12px_40px_rgba(16,185,129,0.15)]",
          specular: "via-emerald-400/40",
          ambientGlow: "from-emerald-500/5",
          iconHover: "group-hover:text-emerald-400 group-hover:drop-shadow-[0_0_8px_rgba(16,185,129,0.7)]",
        }
      : isPositive === false
      ? {
          spotlightBg: "rgba(244, 63, 94, 0.16)",
          spotlightBorder: "rgba(244, 63, 94, 0.6)",
          hoverBorder: "hover:border-rose-500/50",
          hoverShadow: "hover:shadow-[0_12px_40px_rgba(244,63,94,0.15)]",
          specular: "via-rose-400/40",
          ambientGlow: "from-rose-500/5",
          iconHover: "group-hover:text-rose-400 group-hover:drop-shadow-[0_0_8px_rgba(244,63,94,0.7)]",
        }
      : {
          spotlightBg: "rgba(6, 182, 212, 0.13)",
          spotlightBorder: "rgba(6, 182, 212, 0.5)",
          hoverBorder: "hover:border-cyan-500/40",
          hoverShadow: "hover:shadow-[0_12px_40px_rgba(6,182,212,0.12)]",
          specular: "via-cyan-400/30",
          ambientGlow: "from-cyan-500/5",
          iconHover: "group-hover:text-cyan-400 group-hover:drop-shadow-[0_0_8px_rgba(6,182,212,0.6)]",
        };

  return (
    <motion.div
      ref={cardRef}
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.35, delay, ease: "easeOut" }}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      onClick={onClick}
      className={cn(
        "relative group overflow-hidden rounded-2xl border border-white/[0.08] bg-[#080c14] p-5 sm:p-6 transition-all duration-300 hover:-translate-y-1",
        semanticTheme.hoverBorder,
        semanticTheme.hoverShadow,
        onClick && "cursor-pointer",
        className
      )}
    >
      {/* Top subtle specular edge */}
      <div
        className={cn(
          "absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent to-transparent pointer-events-none transition-colors duration-300",
          semanticTheme.specular
        )}
      />

      {/* Masked 1px Interactive Border Highlight */}
      <div
        className="pointer-events-none absolute -inset-[1px] rounded-2xl transition-opacity duration-300 z-10"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `radial-gradient(280px circle at ${mousePos.x}px ${mousePos.y}px, ${semanticTheme.spotlightBorder}, transparent 70%)`,
          mask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
          maskComposite: "exclude",
          WebkitMask: "linear-gradient(#fff 0 0) content-box, linear-gradient(#fff 0 0)",
          WebkitMaskComposite: "xor",
          padding: "1px",
        }}
      />

      {/* Dynamic Cursor Spotlight Radial Glow */}
      <div
        className="pointer-events-none absolute -inset-px rounded-2xl transition-opacity duration-300"
        style={{
          opacity: isHovered ? 1 : 0,
          background: `radial-gradient(400px circle at ${mousePos.x}px ${mousePos.y}px, ${semanticTheme.spotlightBg}, transparent 70%)`,
        }}
      />

      {/* Ambient Corner Glow */}
      <div
        className={cn(
          "absolute -inset-px rounded-2xl bg-gradient-to-b to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-500 pointer-events-none",
          semanticTheme.ambientGlow
        )}
      />

      <div className="relative z-10 flex flex-col h-full justify-between gap-3">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold tracking-widest text-slate-400 uppercase font-mono">
            {title}
          </span>
          <span
            className={cn(
              "text-slate-500 transition-all duration-300",
              semanticTheme.iconHover
            )}
          >
            {icon}
          </span>
        </div>

        <div>
          <div className="font-mono text-2xl sm:text-3xl lg:text-4xl font-bold tracking-tighter text-white tabular-nums drop-shadow-sm">
            {value}
          </div>

          {(delta || subLabel || badge) && (
            <div className="mt-2.5 flex items-center flex-wrap gap-1.5 font-mono text-xs">
              {delta && (
                <span
                  className={cn(
                    "inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold font-mono border tabular-nums",
                    isPositive === true
                      ? "bg-emerald-500/10 text-emerald-400 border-emerald-500/30 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                      : isPositive === false
                      ? "bg-rose-500/10 text-rose-400 border-rose-500/30 shadow-[0_0_10px_rgba(244,63,94,0.2)]"
                      : "bg-white/[0.04] text-slate-300 border-white/[0.08]"
                  )}
                >
                  {isPositive === true ? "↑ " : isPositive === false ? "↓ " : ""}
                  {delta}
                </span>
              )}
              {badge && (
                <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium font-mono border bg-cyan-950/70 border-cyan-800 text-cyan-300">
                  {badge}
                </span>
              )}
              {subLabel && (
                <span className="text-slate-400 text-[11px] truncate">
                  {subLabel}
                </span>
              )}
            </div>
          )}
        </div>
      </div>
    </motion.div>
  );
}

export default BentoCard;
