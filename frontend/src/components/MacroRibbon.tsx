"use client";

import React, { useState, useEffect, useRef } from "react";
import { TrendingUp, TrendingDown, Minus, ShieldCheck, AlertTriangle, AlertCircle, WifiOff } from "lucide-react";
import { MacroResponse, SupervisorStatus } from "@/lib/api";

interface MacroRibbonProps {
  macroData: MacroResponse | null;
  supervisorStatus: SupervisorStatus | null;
  isConnected: boolean;
  lastTickAt: number | null;
  lastIngestTimestamp?: string | null;
}

function MacroRibbonComponent({
  macroData,
  supervisorStatus,
  isConnected,
  lastTickAt,
  lastIngestTimestamp,
}: MacroRibbonProps) {
  const [ingestElapsed, setIngestElapsed] = useState<string>("just now");
  const [now, setNow] = useState<number>(Date.now());
  const prevValuesRef = useRef<Map<string, number | null>>(new Map());
  const [flashingKeys, setFlashingKeys] = useState<Record<string, "tick-up" | "tick-down">>({});

  const isStale = lastTickAt !== null && now - lastTickAt > 30_000;

  // Keep now updated every 5s for staleness detection (M7)
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 5000);
    return () => clearInterval(timer);
  }, []);

  const effectiveIngestTime = lastIngestTimestamp || supervisorStatus?.last_ingestion_timestamp;

  // Elapsed Time Ticker since last dynamic ingest (30s timer with minute granularity)
  useEffect(() => {
    if (!effectiveIngestTime) {
      setIngestElapsed("just now");
      return;
    }

    const targetMs = Date.parse(effectiveIngestTime);
    if (isNaN(targetMs)) {
      setIngestElapsed("just now");
      return;
    }

    const updateTimer = () => {
      const diffSec = Math.max(0, Math.floor((Date.now() - targetMs) / 1000));
      if (diffSec < 60) {
        setIngestElapsed("just now");
      } else if (diffSec < 3600) {
        const m = Math.floor(diffSec / 60);
        setIngestElapsed(`${m}m ago`);
      } else if (diffSec < 86400) {
        const h = Math.floor(diffSec / 3600);
        setIngestElapsed(`${h}h ago`);
      } else {
        const d = Math.floor(diffSec / 86400);
        setIngestElapsed(`${d}d ago`);
      }
    };

    updateTimer();
    const interval = setInterval(updateTimer, 30000);
    return () => clearInterval(interval);
  }, [effectiveIngestTime]);

  // Kinetic Flash Detection on SSE Ticks
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
          icon: <ShieldCheck className="w-3 h-3 text-emerald-400" />,
          label: "NORMAL",
          badgeClass: "text-emerald-300",
          modelText: supervisorStatus?.model_name || "Champion ML Active",
        };
      case "NO_ACTIVE_MODEL":
        return {
          icon: <AlertTriangle className="w-3 h-3 text-amber-400" />,
          label: "TOURNAMENT_PENDING",
          badgeClass: "text-amber-300",
          modelText: "Tournament Pending",
        };
      default:
        return {
          icon: <AlertCircle className="w-3 h-3 text-rose-400" />,
          label: supervisorState,
          badgeClass: "text-rose-300",
          modelText: "Degraded Invariant",
        };
    }
  };

  const supervisorInfo = getSupervisorBadge();

  return (
    <div className="h-full w-full flex items-center overflow-x-auto overflow-y-hidden thin-scrollbar px-2 font-mono text-[11px] divide-x divide-white/[0.06] select-none relative">
      {/* Live SSE Pulse Pill */}
      <div
        className="h-full flex items-center gap-1.5 px-3 text-slate-300 whitespace-nowrap shrink-0"
        title={
          effectiveIngestTime
            ? `Last Dynamic Ingestion: ${new Date(effectiveIngestTime).toLocaleString()} (Continuous feed)`
            : "NSE Dynamic Ingestion Stream"
        }
      >
        <span className="relative flex h-2 w-2">
          {isConnected && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 bg-emerald-400" />
          )}
          <span
            className={`relative inline-flex rounded-full h-2 w-2 ${
              isConnected ? "bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.8)]" : "bg-rose-500"
            }`}
          />
        </span>
        <span className="font-semibold tracking-wider text-[10px] text-slate-400 flex items-center gap-1.5">
          {isConnected ? (
            <>
              {isStale ? (
                <span className="text-amber-400 font-bold flex items-center gap-1" title="Data stream has not received a tick in >30s">
                  <AlertTriangle className="w-3 h-3 text-amber-400" />
                  <span>STALE</span>
                </span>
              ) : (
                <span className="text-emerald-400 font-bold">LIVE NSE</span>
              )}
              <span className="text-slate-500 font-normal">· {ingestElapsed}</span>
            </>
          ) : (
            <span className="text-rose-400 flex items-center gap-1">
              <WifiOff className="w-3 h-3" /> RECONNECTING
            </span>
          )}
        </span>
      </div>

      {/* Macro Indicators with Decaying Flash Keyframes & Tabular Numerals */}
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
            className={`h-full flex items-center gap-1.5 px-3 text-slate-300 whitespace-nowrap shrink-0 transition-colors ${flashClass}`}
            title={`${ind.label} (${ind.source}) - ${ind.freshness_status || "LIVE"}`}
          >
            <span className="text-slate-500 font-medium text-[10px] uppercase tracking-wider">{ind.label}:</span>
            <span className="font-bold text-slate-200 tabular-nums">{formattedVal}</span>

            {hasVal && typeof change === "number" && (
              <span
                className={`flex items-center text-[10px] font-semibold tabular-nums ${
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
        className="h-full flex items-center gap-1.5 px-3 text-[10px] font-mono whitespace-nowrap shrink-0 ml-auto"
        title={`Autonomous Supervisor State: ${supervisorInfo.label} | ${supervisorInfo.modelText}`}
      >
        {supervisorInfo.icon}
        <span className={`font-bold ${supervisorInfo.badgeClass}`}>{supervisorInfo.label}</span>
        <span className="text-slate-500 hidden xl:inline">· {supervisorInfo.modelText}</span>
      </div>
    </div>
  );
}

const MacroRibbon = React.memo(MacroRibbonComponent);
export default MacroRibbon;
