"use client";

import React, { useState, useEffect, useRef } from "react";
import { TrendingUp, TrendingDown, Minus, ShieldCheck, AlertTriangle, AlertCircle, WifiOff } from "lucide-react";
import { MacroResponse, SupervisorStatus } from "@/lib/api";

interface MacroRibbonProps {
  macroData: MacroResponse | null;
  supervisorStatus: SupervisorStatus | null;
  isConnected: boolean;
  lastTickAt: number | null;
}

export default function MacroRibbon({
  macroData,
  supervisorStatus,
  isConnected,
  lastTickAt,
}: MacroRibbonProps) {
  const [secondsAgo, setSecondsAgo] = useState<number | null>(null);
  const prevValuesRef = useRef<Map<string, number | null>>(new Map());
  const [flashingKeys, setFlashingKeys] = useState<Record<string, "tick-up" | "tick-down">>({});

  // 1. Elapsed Time Ticker
  useEffect(() => {
    if (!lastTickAt) {
      setSecondsAgo(null);
      return;
    }

    const updateAge = () => {
      const diffSec = Math.floor((Date.now() - lastTickAt) / 1000);
      setSecondsAgo(Math.max(0, diffSec));
    };

    updateAge();
    const interval = setInterval(updateAge, 1000);
    return () => clearInterval(interval);
  }, [lastTickAt]);

  // 2. Kinetic Flash Detection on SSE Ticks
  useEffect(() => {
    if (!macroData?.indicators) return;

    const newFlashes: Record<string, "tick-up" | "tick-down"> = {};
    let hasChanges = false;

    macroData.indicators.forEach((ind) => {
      const prevVal = prevValuesRef.current.get(ind.symbol);
      if (prevVal !== undefined && ind.value !== null && prevVal !== null && ind.value !== prevVal) {
        newFlashes[ind.symbol] = ind.value > prevVal ? "tick-up" : "tick-down";
        hasChanges = true;
      }
      prevValuesRef.current.set(ind.symbol, ind.value);
    });

    if (hasChanges) {
      setFlashingKeys(newFlashes);
      const timer = setTimeout(() => setFlashingKeys({}), 800);
      return () => clearTimeout(timer);
    }
  }, [macroData, lastTickAt]);

  const indicators = macroData?.indicators || [];
  const supervisorState = supervisorStatus?.supervisor_state || "NORMAL";

  const getSupervisorBadge = () => {
    switch (supervisorState) {
      case "NORMAL":
        return {
          icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />,
          label: "NORMAL",
          badgeClass: "bg-emerald-950/70 border-emerald-500/40 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.4)] ring-1 ring-emerald-500/30",
          modelText: supervisorStatus?.model_name || "Champion Model Active",
        };
      case "NO_ACTIVE_MODEL":
        return {
          icon: <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />,
          label: "NO ACTIVE MODEL",
          badgeClass: "bg-amber-950/70 border-amber-500/40 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.25)]",
          modelText: "Tournament Pending",
        };
      default:
        return {
          icon: <AlertCircle className="w-3.5 h-3.5 text-rose-400" />,
          label: supervisorState,
          badgeClass: "bg-rose-950/70 border-rose-500/40 text-rose-300 shadow-[0_0_10px_rgba(244,63,94,0.3)]",
          modelText: "Degraded Invariant",
        };
    }
  };

  const supervisorInfo = getSupervisorBadge();

  return (
    <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-0.5 font-mono text-[11px]">
      {/* Live SSE Pulse Pill */}
      <div
        className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#050811] border border-white/[0.08] text-slate-300 whitespace-nowrap shadow-sm shrink-0"
        title={
          isConnected
            ? `Live SSE stream active. Last tick: ${secondsAgo !== null ? `${secondsAgo}s ago` : "just now"}`
            : "Stream reconnecting..."
        }
      >
        <span className="relative flex h-2 w-2">
          {isConnected && (
            <span
              className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${
                secondsAgo !== null && secondsAgo < 15 ? "bg-emerald-400" : "bg-amber-400"
              }`}
            />
          )}
          <span
            className={`relative inline-flex rounded-full h-2 w-2 ${
              isConnected
                ? secondsAgo !== null && secondsAgo < 15
                  ? "bg-emerald-500"
                  : "bg-amber-500"
                : "bg-rose-500"
            }`}
          />
        </span>
        <span className="font-semibold tracking-wider text-[10px] text-slate-400">
          {isConnected ? (
            <>
              LIVE SSE
              {secondsAgo !== null && (
                <span className="text-slate-500 font-normal ml-1">· {secondsAgo}s ago</span>
              )}
            </>
          ) : (
            <span className="text-rose-400 flex items-center gap-1">
              <WifiOff className="w-3 h-3" /> RECONNECTING
            </span>
          )}
        </span>
      </div>

      {/* Macro Indicators with Decaying Flash Keyframes */}
      {indicators.map((ind) => {
        const hasVal = ind.value !== null && ind.value !== undefined;
        const change = ind.change_pct;
        const isPositive = typeof change === "number" && change > 0;
        const isNegative = typeof change === "number" && change < 0;
        const flashClass = flashingKeys[ind.symbol] === "tick-up"
          ? "animate-tick-up"
          : flashingKeys[ind.symbol] === "tick-down"
          ? "animate-tick-down"
          : "";

        let formattedVal = "—";
        if (hasVal) {
          if (ind.unit === "₹") {
            formattedVal = `₹${ind.value!.toFixed(2)}`;
          } else if (ind.unit === "$/bbl") {
            formattedVal = `$${ind.value!.toFixed(2)}`;
          } else if (ind.unit === "%") {
            formattedVal = `${ind.value!.toFixed(2)}%`;
          } else {
            formattedVal = `${ind.value!.toFixed(2)} ${ind.unit}`;
          }
        }

        return (
          <div
            key={ind.symbol}
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-[#050811] border border-white/[0.06] text-slate-300 whitespace-nowrap shadow-sm shrink-0 transition-colors ${flashClass}`}
            title={`${ind.label} (${ind.source}) - ${ind.freshness_status || "LIVE"}`}
          >
            <span className="text-slate-500 font-medium">{ind.label}:</span>
            <span className="font-bold text-slate-200">{formattedVal}</span>

            {hasVal && typeof change === "number" && (
              <span
                className={`flex items-center text-[10px] font-semibold ${
                  isPositive
                    ? "text-emerald-400"
                    : isNegative
                    ? "text-rose-400"
                    : "text-slate-500"
                }`}
              >
                {isPositive ? (
                  <TrendingUp className="w-2.5 h-2.5 mr-0.5 inline" />
                ) : isNegative ? (
                  <TrendingDown className="w-2.5 h-2.5 mr-0.5 inline" />
                ) : (
                  <Minus className="w-2.5 h-2.5 mr-0.5 inline" />
                )}
                {isPositive ? "+" : ""}
                {change.toFixed(2)}%
              </span>
            )}

            {!hasVal && ind.freshness_status === "NOT_CONFIGURED" && (
              <span className="text-[9px] text-slate-500 italic">unconfigured</span>
            )}
          </div>
        );
      })}

      {/* Supervisor Health State */}
      <div
        className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full border text-[10px] font-mono whitespace-nowrap shrink-0 ${supervisorInfo.badgeClass}`}
        title={`Autonomous Supervisor State: ${supervisorInfo.label} | ${supervisorInfo.modelText}`}
      >
        {supervisorInfo.icon}
        <span className="font-bold">{supervisorInfo.label}</span>
        <span className="text-slate-400">· {supervisorInfo.modelText}</span>
      </div>
    </div>
  );
}
