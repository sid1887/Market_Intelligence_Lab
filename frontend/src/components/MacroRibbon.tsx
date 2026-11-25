"use client";

import React, { useState, useEffect, useRef } from "react";
import { TrendingUp, TrendingDown, Minus, ShieldCheck, AlertTriangle, AlertCircle, WifiOff, Terminal, Activity, Network } from "lucide-react";
import { API_BASE, MacroResponse, SupervisorStatus } from "@/lib/api";
import { milEvents } from "@/lib/store";

interface RegimeRibbonState {
  active_regime: string;
  probabilities?: Record<string, number>;
  policy?: {
    position_scale?: number;
    max_portfolio_exposure?: number;
    min_meta_prob_delta?: number;
    veto_high_beta_breakouts?: boolean;
  };
}

interface SpilloverRibbonState {
  systemic_contagion_index: number;
  contagion_regime: string;
  top_spillover_alert?: {
    leader: string;
    follower: string;
    granger_f: number;
    lag_corr: number;
    signal_type: string;
  } | null;
  directed_lead_lag_edges?: Array<{
    leader: string;
    follower: string;
    granger_f: number;
    lag_corr: number;
    signal_type: string;
  }>;
}

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
  const [mounted, setMounted] = useState<boolean>(false);
  const [now, setNow] = useState<number>(0);
  const prevValuesRef = useRef<Map<string, number | null>>(new Map());
  const [flashingKeys, setFlashingKeys] = useState<Record<string, "tick-up" | "tick-down">>({});
  const [regimeData, setRegimeData] = useState<RegimeRibbonState | null>(null);
  const [spilloverData, setSpilloverData] = useState<SpilloverRibbonState | null>(null);
  const [showRegimePopover, setShowRegimePopover] = useState<boolean>(false);

  // Fetch Live HMM Regime & Spillover Contagion HUD every 60s
  useEffect(() => {
    let cancelled = false;
    const loadHud = async () => {
      try {
        const [rRes, sRes] = await Promise.all([
          fetch(`${API_BASE}/regime/status`),
          fetch(`${API_BASE}/regime/spillover`),
        ]);
        if (!cancelled && rRes.ok) {
          const rJson = await rRes.json();
          if (rJson?.active_regime) setRegimeData(rJson);
        }
        if (!cancelled && sRes.ok) {
          const sJson = await sRes.json();
          if (typeof sJson?.systemic_contagion_index === "number") setSpilloverData(sJson);
        }
      } catch {
        // non-blocking
      }
    };
    loadHud();
    const timer = setInterval(loadHud, 60_000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, []);

  const isStale = lastTickAt !== null && now > 0 && now - lastTickAt > 30_000;

  // Keep now updated every 5s for staleness detection (M7)
  useEffect(() => {
    setMounted(true);
    setNow(Date.now());
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
    <div className="h-full w-full flex items-center overflow-hidden px-2 font-mono text-[11px] select-none relative">
      {/* Live SSE Pulse Pill */}
      <div
        className="h-full flex items-center gap-1.5 px-3 text-slate-300 whitespace-nowrap shrink-0 border-r border-white/[0.06] bg-[#020306] z-10"
        title={
          mounted && effectiveIngestTime
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
                <span className="text-emerald-400 font-bold flex items-center gap-1">
                  <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                  LIVE NSE
                </span>
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
      <div className="marquee-wrapper flex-1 overflow-x-auto overflow-y-hidden thin-scrollbar h-full flex items-center min-w-0">
        <div className="flex items-center divide-x divide-white/[0.06] shrink-0">
          {indicators.map((ind) => {
            const hasVal = ind.value !== null && ind.value !== undefined;
            const change = ind.change_pct;
            const isPositive = typeof change === "number" && change > 0;
            const isNegative = typeof change === "number" && change < 0;
            const isFlashing = Boolean(flashingKeys[ind.symbol]);
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
                <span className={`font-bold text-slate-200 tabular-nums ${isFlashing ? "animate-tick-pop" : ""}`}>{formattedVal}</span>

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
        </div>
      </div>

      {/* Live HMM Regime & Systemic Contagion HUD */}
      {regimeData && (
        <div className="relative h-full flex items-center border-l border-white/[0.06] bg-[#020306] z-20 shrink-0">
          <button
            type="button"
            onClick={() => setShowRegimePopover((p) => !p)}
            className="h-full flex items-center gap-1.5 px-2.5 text-[10px] font-mono whitespace-nowrap hover:bg-white/[0.04] transition-colors cursor-pointer"
            title="Live 3-State HMM Regime & Cross-Asset Spillover Contagion — Click for breakdown"
          >
            <Activity className={`w-3 h-3 ${
              regimeData.active_regime === "STRESS_DRAWDOWN"
                ? "text-rose-400"
                : regimeData.active_regime === "HIGH_VOL_CHOP"
                ? "text-amber-400"
                : "text-emerald-400"
            }`} />
            <span className={`px-1.5 py-0.5 rounded font-bold border ${
              regimeData.active_regime === "STRESS_DRAWDOWN"
                ? "bg-rose-950/70 border-rose-500/40 text-rose-300"
                : regimeData.active_regime === "HIGH_VOL_CHOP"
                ? "bg-amber-950/70 border-amber-500/40 text-amber-300"
                : "bg-emerald-950/70 border-emerald-500/30 text-emerald-300"
            }`}>
              {regimeData.active_regime}
            </span>
            <span className="text-slate-400 hidden lg:inline">
              {regimeData.active_regime === "LOW_VOL_TREND"
                ? "100% Cap"
                : regimeData.active_regime === "HIGH_VOL_CHOP"
                ? "70% Cap · +0.05 Meta Hurdle"
                : "25% Cap · Breakouts Vetoed"}
            </span>
            {spilloverData && (
              <span className={`hidden md:inline-flex items-center gap-1 ml-1 px-1.5 py-0.5 rounded border ${
                spilloverData.systemic_contagion_index >= 70
                  ? "bg-rose-950/60 border-rose-500/30 text-rose-300"
                  : spilloverData.systemic_contagion_index >= 50
                  ? "bg-amber-950/60 border-amber-500/30 text-amber-300"
                  : "bg-cyan-950/50 border-cyan-500/25 text-cyan-300"
              }`}>
                <Network className="w-2.5 h-2.5" />
                Contagion {spilloverData.systemic_contagion_index.toFixed(0)}
              </span>
            )}
          </button>

          {showRegimePopover && (
            <div className="absolute right-0 top-full mt-1 w-80 rounded-lg border border-white/10 bg-[#070b14]/95 backdrop-blur-xl shadow-2xl p-3 text-[11px] font-mono text-slate-200 z-50">
              <div className="flex items-center justify-between border-b border-white/10 pb-1.5 mb-2">
                <span className="font-bold text-cyan-300">HMM REGIME &amp; SPILLOVER HUD</span>
                <button
                  type="button"
                  onClick={() => setShowRegimePopover(false)}
                  className="text-slate-400 hover:text-white text-xs"
                >
                  ✕
                </button>
              </div>
              <div className="space-y-1 mb-2">
                <div className="text-[10px] text-slate-400 uppercase">Causal State Probabilities</div>
                {["LOW_VOL_TREND", "HIGH_VOL_CHOP", "STRESS_DRAWDOWN"].map((k) => {
                  const p = (regimeData.probabilities?.[k] ?? 0) * 100;
                  return (
                    <div key={k} className="flex items-center justify-between">
                      <span className="text-slate-300">{k}</span>
                      <span className="tabular-nums font-semibold">{p.toFixed(1)}%</span>
                    </div>
                  );
                })}
              </div>
              {spilloverData && (
                <div className="border-t border-white/10 pt-2 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] text-slate-400 uppercase">Systemic Contagion</span>
                    <span className="font-bold text-cyan-300">
                      {spilloverData.systemic_contagion_index.toFixed(1)} / 100
                    </span>
                  </div>
                  {spilloverData.top_spillover_alert && (
                    <div className="text-[10px] text-slate-300 bg-white/[0.03] rounded p-1.5 border border-white/[0.06]">
                      Leader: <span className="text-amber-300 font-semibold">{spilloverData.top_spillover_alert.leader}</span> →{" "}
                      <span className="text-cyan-300 font-semibold">{spilloverData.top_spillover_alert.follower}</span>{" "}
                      (F={spilloverData.top_spillover_alert.granger_f.toFixed(1)}, r={spilloverData.top_spillover_alert.lag_corr.toFixed(2)})
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      )}

      {/* Supervisor Health State & Observability Trigger */}
      <button
        onClick={() => milEvents.emit("mil:open-system-logs")}
        className="h-full flex items-center gap-1.5 px-3 text-[10px] font-mono whitespace-nowrap shrink-0 ml-auto border-l border-white/[0.06] bg-[#020306] z-10 hover:bg-white/[0.04] transition-colors cursor-pointer group"
        title={`Supervisor: ${supervisorInfo.label} | Click or press Alt+L for Live Diagnostics`}
      >
        <Terminal className="w-3 h-3 text-slate-500 group-hover:text-cyan-400 transition-colors" />
        {supervisorInfo.icon}
        <span className={`font-bold ${supervisorInfo.badgeClass} ${supervisorState.includes("QUARANTINE") ? "animate-pulse" : ""}`}>
          {supervisorInfo.label}
        </span>
        <span className="text-slate-500 hidden xl:inline">· {supervisorInfo.modelText}</span>
      </button>
    </div>
  );
}

const MacroRibbon = React.memo(MacroRibbonComponent);
export default MacroRibbon;
