"use client";

import React from "react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

export interface TabItem<T extends string = string> {
  id: T;
  label: string;
  badge?: string;
  desc?: string;
  icon?: React.ReactNode;
}

export interface AnimatedTabsProps<T extends string = string> {
  tabs: TabItem<T>[];
  activeTab: T;
  setActiveTab: (tabId: T) => void;
  className?: string;
  layoutId?: string;
  variant?: "pill" | "card";
}

export function AnimatedTabs<T extends string = string>({
  tabs,
  activeTab,
  setActiveTab,
  className,
  layoutId = "active-tab-indicator",
  variant = "pill",
}: AnimatedTabsProps<T>) {
  if (variant === "card") {
    return (
      <div className={cn("grid grid-cols-1 md:grid-cols-3 gap-3 w-full", className)}>
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "relative group overflow-hidden p-4 sm:p-5 rounded-2xl text-left border transition-all duration-200 active:scale-[0.98] flex flex-col justify-between min-h-[105px]",
                isActive
                  ? "bg-[#091122]/90 border-cyan-500/70 shadow-lg shadow-cyan-950/30 ring-1 ring-cyan-500/40"
                  : "bg-[#06090f]/75 border-white/[0.08] hover:border-cyan-500/30 hover:bg-[#09101d]/90 hover:-translate-y-0.5 hover:shadow-[0_4px_24px_rgba(0,0,0,0.5)]"
              )}
            >
              {/* Active motion indicator background glow */}
              {isActive && (
                <motion.div
                  layoutId={layoutId}
                  className="absolute inset-0 bg-cyan-500/[0.06] rounded-2xl pointer-events-none"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}

              {/* Ambient gradient hover backlight */}
              <div className="absolute -inset-px rounded-2xl bg-gradient-to-b from-cyan-500/10 to-transparent opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none" />

              <div className="relative z-10 flex items-center justify-between w-full">
                <div className="flex items-center gap-2">
                  {tab.icon && <span className="text-cyan-400">{tab.icon}</span>}
                  <span className="font-bold text-sm text-white tracking-tight">{tab.label}</span>
                  <span
                    className={cn(
                      "text-[10px] px-2 py-0.5 rounded-full font-mono font-bold tabular-nums",
                      isActive
                        ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40"
                        : "bg-white/[0.05] text-slate-400 border border-white/[0.06]"
                    )}
                  >
                    {tab.id}
                  </span>
                </div>
                {tab.badge && (
                  <span className="text-[10px] font-mono tabular-nums text-slate-400 font-semibold">{tab.badge}</span>
                )}
              </div>
              {tab.desc && (
                <p className="relative z-10 text-[11px] text-slate-400 mt-2 line-clamp-2 leading-relaxed">
                  {tab.desc}
                </p>
              )}
            </button>
          );
        })}
      </div>
    );
  }

  return (
    <div
      className={cn(
        "flex space-x-1 p-1 bg-[#06090f] rounded-xl border border-white/[0.08] w-fit shadow-lg",
        className
      )}
    >
      {tabs.map((tab) => {
        const isActive = activeTab === tab.id;
        return (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={cn(
              "relative rounded-lg px-3.5 py-1.5 text-xs font-mono transition-colors duration-200 flex items-center gap-2",
              isActive ? "text-cyan-200 font-bold" : "text-slate-400 hover:text-slate-200"
            )}
          >
            {isActive && (
              <motion.div
                layoutId={layoutId}
                className="absolute inset-0 bg-cyan-500/15 border border-cyan-500/50 rounded-lg shadow-[0_0_15px_rgba(6,182,212,0.25)]"
                transition={{ type: "spring", stiffness: 450, damping: 32 }}
              />
            )}
            {tab.icon && <span className="relative z-10 text-cyan-400">{tab.icon}</span>}
            <span className="relative z-10 tracking-tight">{tab.label}</span>
            {tab.badge && (
              <span
                className={cn(
                  "relative z-10 text-[10px] px-1.5 py-0.2 rounded font-mono font-bold tabular-nums",
                  isActive
                    ? "bg-cyan-500/25 text-cyan-200 border border-cyan-500/40"
                    : "bg-white/[0.05] text-slate-400"
                )}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export default AnimatedTabs;
