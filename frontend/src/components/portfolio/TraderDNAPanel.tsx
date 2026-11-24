"use client";

import React, { useState, useEffect, useCallback } from "react";
import {
  ShieldAlert,
  ShieldCheck,
  Clock,
  TrendingDown,
  TrendingUp,
  Percent,
  AlertTriangle,
  RefreshCw,
  Flame,
  CheckCircle2,
  Receipt,
  Crosshair,
} from "lucide-react";
import { fetchTraderDNAProfile, TraderDNAProfile } from "@/lib/api";

export function TraderDNAPanel() {
  const [profile, setProfile] = useState<TraderDNAProfile | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadProfile = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchTraderDNAProfile();
      setProfile(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProfile();
  }, [loadProfile]);

  const formatInr = (val?: number) => {
    if (val === undefined || val === null) return "₹0.00";
    return (
      (val < 0 ? "-₹" : "₹") +
      Math.abs(val).toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  };

  if (loading && !profile) {
    return (
      <div className="p-8 rounded-2xl bg-[#080c14] border border-white/[0.08] flex flex-col items-center justify-center space-y-4">
        <RefreshCw className="w-8 h-8 text-cyan-400 animate-spin" />
        <p className="text-xs font-mono text-slate-400">Loading Trader DNA behavioral profile...</p>
      </div>
    );
  }

  if (error && !profile) {
    return (
      <div className="p-6 rounded-2xl bg-rose-950/20 border border-rose-500/30 text-rose-300 space-y-3">
        <div className="flex items-center gap-2">
          <AlertTriangle className="w-5 h-5 text-rose-400" />
          <h3 className="text-sm font-bold">Failed to Load Trader DNA</h3>
        </div>
        <p className="text-xs font-mono text-slate-400">{error}</p>
        <button
          onClick={loadProfile}
          className="px-3 py-1.5 rounded-lg bg-rose-900/40 hover:bg-rose-900/60 border border-rose-500/40 text-xs font-mono text-white transition-colors"
        >
          Retry
        </button>
      </div>
    );
  }

  const p = profile!;
  const isCooldown = Boolean(p.cooldown_active || p.defensive_cooldown_active);
  const earlyExitAlert = p.early_exit_rate_pct > 30.0;

  return (
    <div className="space-y-6">
      {/* 1. Header & Discipline Status Banner */}
      <div
        className={`p-6 rounded-2xl border transition-all ${
          isCooldown
            ? "bg-gradient-to-r from-[#180d0d] via-[#1c1010] to-[#180d0d] border-amber-500/40 shadow-[0_12px_40px_rgba(245,158,11,0.15)]"
            : "bg-gradient-to-r from-[#081216] via-[#0b171c] to-[#081216] border-emerald-500/40 shadow-[0_12px_40px_rgba(16,185,129,0.15)]"
        }`}
      >
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-2">
            <div className="flex items-center space-x-2.5">
              <div
                className={`p-2.5 rounded-xl border ${
                  isCooldown
                    ? "bg-amber-500/10 border-amber-500/30 text-amber-400"
                    : "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                }`}
              >
                {isCooldown ? <ShieldAlert className="w-6 h-6" /> : <ShieldCheck className="w-6 h-6" />}
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="text-base font-bold text-white tracking-wide">
                    Trader DNA Discipline & Cooldown Engine
                  </h2>
                  <span
                    className={`text-[10px] font-mono font-bold px-2.5 py-0.5 rounded-full border ${
                      isCooldown
                        ? "bg-amber-950/90 text-amber-300 border-amber-500/50 animate-pulse"
                        : "bg-emerald-950/90 text-emerald-300 border-emerald-500/50"
                    }`}
                  >
                    {isCooldown ? "DEFENSIVE COOLDOWN ACTIVE" : "DISCIPLINE NORMAL"}
                  </span>
                </div>
                <p className="text-xs text-slate-400 font-mono mt-0.5">
                  {isCooldown
                    ? `Guard Triggered: ${p.cooldown_reasons.join(" • ") || "Defensive risk mitigation"} — Size multiplier: ${p.size_multiplier}x (Max ₹${p.max_ticket_allowed})`
                    : "No emotional churn detected. Full position sizing enabled (1.0x allocation budget)."}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <button
              onClick={loadProfile}
              disabled={loading}
              className="px-3.5 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs font-mono text-slate-300 flex items-center space-x-2 transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
              <span>Refresh Metrics</span>
            </button>
          </div>
        </div>

        {/* Cooldown & Streak Details Pill Strip */}
        <div className="grid grid-cols-1 sm:grid-cols-4 gap-3 mt-5 pt-4 border-t border-white/[0.08]">
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <Flame className={`w-4 h-4 shrink-0 ${p.consecutive_losses >= 2 ? "text-rose-400" : "text-slate-500"}`} />
            <span>
              Loss Streak: <strong className={p.consecutive_losses >= 2 ? "text-rose-300 font-bold" : "text-white"}>{p.consecutive_losses} in a row</strong>
            </span>
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <Crosshair className="w-4 h-4 text-cyan-400 shrink-0" />
            <span>
              Max Ticket: <strong className="text-white font-mono">{formatInr(p.max_ticket_allowed)}</strong>
            </span>
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <Percent className="w-4 h-4 text-indigo-400 shrink-0" />
            <span>
              Size Multiplier: <strong className="text-white font-mono">{p.size_multiplier}x</strong>
            </span>
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>
              Badge: <strong className="text-emerald-300 truncate">{p.coaching_badge}</strong>
            </span>
          </div>
        </div>
      </div>

      {/* 2. Core Behavioral Telemetry 4-Card Strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Realized Win Rate */}
        <div className="p-5 rounded-2xl bg-[#080c14] border border-white/[0.08] space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Realized Win Rate</span>
            <TrendingUp className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white tabular-nums">
            {p.win_rate_pct.toFixed(1)}%
          </div>
          <div className="text-[11px] font-mono text-slate-400">
            <span className="text-emerald-400">{p.win_count}W</span> / <span className="text-rose-400">{p.loss_count}L</span> ({p.total_trades} roundtrips)
          </div>
        </div>

        {/* Median Hold Horizon */}
        <div className="p-5 rounded-2xl bg-[#080c14] border border-white/[0.08] space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Median Hold Horizon</span>
            <Clock className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-white tabular-nums">
            {p.median_hold_days} <span className="text-sm font-normal text-slate-400">sessions</span>
          </div>
          <div className="text-[11px] font-mono text-cyan-400">
            {p.holding_window_bias}
          </div>
        </div>

        {/* Early Exit Rate */}
        <div className="p-5 rounded-2xl bg-[#080c14] border border-white/[0.08] space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Early Exit Rate (≤ 2d)</span>
            <AlertTriangle className={`w-4 h-4 ${earlyExitAlert ? "text-amber-400" : "text-slate-500"}`} />
          </div>
          <div className={`text-2xl font-bold font-mono tabular-nums ${earlyExitAlert ? "text-amber-400" : "text-white"}`}>
            {p.early_exit_rate_pct.toFixed(1)}%
          </div>
          <div className="text-[11px] font-mono text-slate-400">
            {earlyExitAlert ? (
              <span className="text-amber-300">Impatience alert: exiting too soon</span>
            ) : (
              <span className="text-emerald-400">Patient swing horizon maintained</span>
            )}
          </div>
        </div>

        {/* Peak Drawdown */}
        <div className="p-5 rounded-2xl bg-[#080c14] border border-white/[0.08] space-y-2">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>Peak Drawdown</span>
            <TrendingDown className="w-4 h-4 text-rose-400" />
          </div>
          <div className="text-2xl font-bold font-mono text-rose-400 tabular-nums">
            {formatInr(p.max_drawdown)}
          </div>
          <div className="text-[11px] font-mono text-slate-400">
            Avg Breakeven: {p.avg_breakeven_pct.toFixed(2)}%
          </div>
        </div>
      </div>

      {/* 3. Deep-Dive: Horizon Edge & Angel One ₹23.60 DP Friction */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left: Horizon Edge Comparison */}
        <div className="p-6 rounded-2xl bg-[#080c14] border border-white/[0.08] space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center space-x-2">
              <Clock className="w-4 h-4 text-cyan-400" />
              <h3 className="text-sm font-bold text-white tracking-wide">
                Holding Horizon Edge Comparison
              </h3>
            </div>
            <span className="text-[10px] font-mono text-slate-400">Empirical Trade Data</span>
          </div>

          <div className="space-y-3">
            <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04] flex items-center justify-between">
              <div>
                <span className="text-xs text-slate-300 font-semibold">Impulsive (&lt; 3 Days Hold)</span>
                <p className="text-[10px] text-slate-500 font-mono">Quick exits often overwhelmed by ₹23.60 DP drag</p>
              </div>
              <div className="text-right">
                <span className={`text-base font-bold font-mono tabular-nums ${p.win_rate_under_3d >= 50 ? "text-emerald-400" : "text-rose-400"}`}>
                  {p.win_rate_under_3d.toFixed(1)}%
                </span>
                <span className="text-[10px] text-slate-500 block">Win Rate</span>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-cyan-950/20 border border-cyan-500/20 flex items-center justify-between">
              <div>
                <span className="text-xs text-cyan-300 font-semibold">Micro-Swing (5–15 Days Hold)</span>
                <p className="text-[10px] text-slate-400 font-mono">Allows factor alpha and momentum continuation to materialize</p>
              </div>
              <div className="text-right">
                <span className="text-base font-bold font-mono text-emerald-400 tabular-nums">
                  {p.win_rate_5_to_15d.toFixed(1)}%
                </span>
                <span className="text-[10px] text-slate-500 block">Win Rate</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3 pt-2">
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-center">
                <span className="text-[11px] text-slate-400 block font-mono">Avg Winner Hold</span>
                <span className="text-sm font-bold font-mono text-emerald-400">{p.avg_hold_days_winners} sessions</span>
              </div>
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-center">
                <span className="text-[11px] text-slate-400 block font-mono">Avg Loser Hold</span>
                <span className="text-sm font-bold font-mono text-rose-400">{p.avg_hold_days_losers} sessions</span>
              </div>
            </div>
          </div>
        </div>

        {/* Right: Angel One ₹23.60 DP Friction Breakdown */}
        <div className="p-6 rounded-2xl bg-[#080c14] border border-white/[0.08] space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.06]">
            <div className="flex items-center space-x-2">
              <Receipt className="w-4 h-4 text-emerald-400" />
              <h3 className="text-sm font-bold text-white tracking-wide">
                Angel One ₹23.60 DP & Tax Reconciliation
              </h3>
            </div>
            <span className="text-[10px] font-mono text-emerald-400 font-semibold">
              Fee Drag: {p.fee_drag_pct.toFixed(2)}%
            </span>
          </div>

          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
                <span className="text-[10px] font-mono text-slate-400 block">Realized Gross P&L</span>
                <span className={`text-base font-bold font-mono tabular-nums ${p.realized_gross_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatInr(p.realized_gross_pnl)}
                </span>
              </div>
              <div className="p-3.5 rounded-xl bg-emerald-950/20 border border-emerald-500/20">
                <span className="text-[10px] font-mono text-emerald-300 block">True Net P&L (Post-Friction)</span>
                <span className={`text-base font-bold font-mono tabular-nums ${p.realized_net_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                  {formatInr(p.realized_net_pnl)}
                </span>
              </div>
            </div>

            <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.04] space-y-2">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400">CDSL + Angel One DP Charges (₹23.60/sell)</span>
                <span className="text-rose-400 font-semibold">{formatInr(p.total_dp_charges)}</span>
              </div>
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-400">Statutory Levies (STT, Stamp Duty, GST, SEBI)</span>
                <span className="text-slate-300 font-semibold">{formatInr(p.total_trade_taxes)}</span>
              </div>
              <div className="pt-2 border-t border-white/[0.06] flex items-center justify-between text-xs font-mono font-bold">
                <span className="text-slate-200">Total Capital Friction Sunk</span>
                <span className="text-rose-400">{formatInr(p.total_friction)}</span>
              </div>
            </div>

            <p className="text-[10px] text-slate-500 font-mono leading-relaxed">
              * On micro-capital tickets (₹1,500–₹5,000), the mandatory ₹23.60 Demat DP debit per sell order represents 0.47%–1.57% of your capital. Requiring minimum +3.5% swing targets completely offsets this drag.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
export default TraderDNAPanel;
