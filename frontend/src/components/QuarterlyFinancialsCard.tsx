"use client";

import React, { useState } from "react";
import { motion } from "framer-motion";
import { BarChart3, TrendingUp, TrendingDown, ShieldCheck, FileText } from "lucide-react";
import { cn } from "@/lib/utils";

export interface QuarterlyStatement {
  period_end_date: string;
  filing_date?: string;
  is_audited?: boolean;
  revenue: number | null;
  ebitda: number | null;
  net_profit: number | null;
  eps: number | null;
  total_debt?: number | null;
  total_equity?: number | null;
  cash_flow_from_ops?: number | null;
  data_status?: "OBSERVED_TIMESTAMP" | "STATUTORY_FALLBACK_LAG" | "SECTOR_ESTIMATE" | string;
  observed_timestamp?: string;
}

interface QuarterlyFinancialsCardProps {
  symbol: string;
  statements?: QuarterlyStatement[];
}

export function QuarterlyFinancialsCard({ symbol, statements = [] }: QuarterlyFinancialsCardProps) {
  const [activeMetric, setActiveMetric] = useState<"revenue" | "net_profit" | "ebitda">("revenue");

  // Sort chronological for charts (oldest -> newest)
  const chronological = [...statements].sort((a, b) => (a.period_end_date > b.period_end_date ? 1 : -1));
  // Reverse chronological for table (newest -> oldest)
  const recentFirst = [...statements].sort((a, b) => (a.period_end_date < b.period_end_date ? 1 : -1));

  if (!statements || statements.length === 0) {
    return (
      <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-6 text-center space-y-3">
        <div className="w-10 h-10 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 flex items-center justify-center mx-auto">
          <FileText className="w-5 h-5" />
        </div>
        <h3 className="text-sm font-mono font-bold text-slate-200">
          Quarterly Filings Pending Ingestion
        </h3>
        <p className="text-xs font-mono text-slate-400 max-w-md mx-auto">
          Discrete quarterly financial statements (revenue, EBITDA, net profit) for {symbol} are queued for automated pipeline hydration from exchange archives.
        </p>
      </div>
    );
  }

  // Calculate highest value for relative bar heights
  const maxMetricVal = Math.max(
    ...chronological.map((s) => Math.abs(s[activeMetric] || 0)),
    1
  );

  const formatPeriod = (dt: string) => {
    try {
      const d = new Date(dt);
      const m = d.toLocaleString("default", { month: "short" });
      const y = d.getFullYear().toString().slice(-2);
      return `${m} '${y}`;
    } catch {
      return dt;
    }
  };

  const formatCr = (val: number | null | undefined) => {
    if (val === null || val === undefined) return "—";
    return `₹${val.toLocaleString("en-IN", { maximumFractionDigits: 1 })} Cr`;
  };

  // Latest quarter summary
  const latestQ = recentFirst[0];
  const prevQ = recentFirst[1];

  let qoqRevGrowth: number | null = null;
  if (latestQ && prevQ && latestQ.revenue && prevQ.revenue && prevQ.revenue > 0) {
    qoqRevGrowth = ((latestQ.revenue - prevQ.revenue) / prevQ.revenue) * 100.0;
  }

  let latestNetMargin: number | null = null;
  if (latestQ && latestQ.revenue && latestQ.net_profit && latestQ.revenue > 0) {
    latestNetMargin = (latestQ.net_profit / latestQ.revenue) * 100.0;
  }

  return (
    <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl p-5 sm:p-6 shadow-[0_12px_40px_rgba(0,0,0,0.6)] relative overflow-hidden space-y-5">
      {/* Top Specular Hairline */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent pointer-events-none" />

      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-white/[0.06]">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.15)]">
            <BarChart3 className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-base font-bold text-white font-mono tracking-tight flex items-center gap-2">
              Quarterly Financial Performance
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 font-mono">
                {statements.length} Quarters
              </span>
            </h3>
            <p className="text-[11px] text-slate-400 font-mono">
              Reported Revenue, EBITDA, Net Profit &amp; Operating Margins (SEBI Discrete Filings)
            </p>
          </div>
        </div>

        {/* Metric Selector Pills */}
        <div className="flex items-center space-x-1 bg-black/50 p-1 rounded-xl border border-white/[0.08] text-[10px] font-mono self-start sm:self-auto">
          {(
            [
              { id: "revenue", label: "Revenue" },
              { id: "net_profit", label: "Net Profit" },
              { id: "ebitda", label: "EBITDA" },
            ] as const
          ).map((m) => (
            <button
              key={m.id}
              onClick={() => setActiveMetric(m.id)}
              className={cn(
                "px-2.5 py-1 rounded-lg transition-all",
                activeMetric === m.id
                  ? "bg-cyan-950/70 border border-cyan-500/50 text-cyan-300 font-bold shadow-[0_0_10px_rgba(6,182,212,0.3)]"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.03]"
              )}
            >
              {m.label}
            </button>
          ))}
        </div>
      </div>

      {/* KPI Highlights Strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
          <span className="text-[10px] font-mono uppercase text-slate-400 block">Latest Revenue</span>
          <span className="text-sm sm:text-base font-bold text-slate-100 font-mono tabular-nums block mt-0.5">
            {formatCr(latestQ?.revenue)}
          </span>
          {qoqRevGrowth !== null && (
            <span
              className={cn(
                "text-[10px] font-mono font-medium flex items-center gap-0.5 mt-0.5",
                qoqRevGrowth >= 0 ? "text-emerald-400" : "text-rose-400"
              )}
            >
              {qoqRevGrowth >= 0 ? <TrendingUp className="w-3 h-3" /> : <TrendingDown className="w-3 h-3" />}
              {qoqRevGrowth >= 0 ? "+" : ""}
              {qoqRevGrowth.toFixed(1)}% QoQ
            </span>
          )}
        </div>

        <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
          <span className="text-[10px] font-mono uppercase text-slate-400 block">Latest Net Profit</span>
          <span
            className={cn(
              "text-sm sm:text-base font-bold font-mono tabular-nums block mt-0.5",
              (latestQ?.net_profit || 0) >= 0 ? "text-emerald-400" : "text-rose-400"
            )}
          >
            {formatCr(latestQ?.net_profit)}
          </span>
          {latestNetMargin !== null && (
            <span className="text-[10px] font-mono text-slate-400 block mt-0.5">
              Margin: <strong className="text-slate-200">{latestNetMargin.toFixed(1)}%</strong>
            </span>
          )}
        </div>

        <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
          <span className="text-[10px] font-mono uppercase text-slate-400 block">Latest EBITDA</span>
          <span className="text-sm sm:text-base font-bold text-slate-100 font-mono tabular-nums block mt-0.5">
            {formatCr(latestQ?.ebitda)}
          </span>
          <span className="text-[10px] font-mono text-cyan-400 block mt-0.5">Core Operating Profit</span>
        </div>

        <div className="bg-[#050810]/70 p-3 rounded-xl border border-white/[0.06]">
          <span className="text-[10px] font-mono uppercase text-slate-400 block">Assurance Status</span>
          <span className="text-xs font-bold text-slate-200 font-mono flex items-center gap-1.5 mt-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
            {latestQ?.is_audited ? "Audited Official" : "SEBI Reviewed"}
          </span>
          <span className="text-[10px] font-mono text-slate-500 block mt-0.5">
            Period: {latestQ?.period_end_date}
          </span>
        </div>
      </div>

      {/* Visual Bar Chart Comparison */}
      <div className="bg-[#050810]/50 p-4 rounded-xl border border-white/[0.05] space-y-2">
        <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 pb-1">
          <span>Quarterly {activeMetric === "revenue" ? "Revenue" : activeMetric === "net_profit" ? "Net Profit" : "EBITDA"} Progression</span>
          <span className="text-[10px] text-slate-500">Values in ₹ Crores</span>
        </div>

        <div className="grid grid-cols-4 sm:grid-cols-8 gap-2 pt-2 items-end h-36">
          {chronological.map((s, idx) => {
            const val = s[activeMetric] || 0;
            const heightPct = Math.max(8, Math.round((Math.abs(val) / maxMetricVal) * 100));
            const isPos = val >= 0;

            return (
              <div key={s.period_end_date || idx} className="flex flex-col items-center h-full justify-end group">
                {/* Tooltip value */}
                <span className="text-[9px] font-mono text-slate-400 opacity-0 group-hover:opacity-100 transition-opacity mb-1 tabular-nums whitespace-nowrap">
                  ₹{val.toFixed(0)}Cr
                </span>

                {/* Animated bar */}
                <div className="w-full max-w-[32px] bg-white/[0.04] rounded-t-md overflow-hidden relative flex items-end">
                  <motion.div
                    initial={{ height: 0 }}
                    animate={{ height: `${heightPct}%` }}
                    transition={{ duration: 0.45, delay: idx * 0.04 }}
                    className={cn(
                      "w-full rounded-t-md transition-colors",
                      activeMetric === "revenue"
                        ? "bg-gradient-to-t from-cyan-600/50 to-cyan-400 group-hover:to-cyan-300"
                        : isPos
                        ? "bg-gradient-to-t from-emerald-600/50 to-emerald-400 group-hover:to-emerald-300"
                        : "bg-gradient-to-t from-rose-600/50 to-rose-400 group-hover:to-rose-300"
                    )}
                  />
                </div>

                {/* Period label */}
                <span className="text-[9px] font-mono text-slate-400 mt-2 truncate w-full text-center">
                  {formatPeriod(s.period_end_date)}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Detailed Table (Collapsible / Scrollable) */}
      <div className="overflow-x-auto rounded-xl border border-white/[0.06] bg-[#050810]/40">
        <table className="w-full text-left border-collapse text-[11px] font-mono">
          <thead>
            <tr className="border-b border-white/[0.06] bg-white/[0.02] text-slate-400 text-[10px] uppercase tracking-wider">
              <th className="py-2.5 px-3">Period End</th>
              <th className="py-2.5 px-3 text-right">Revenue</th>
              <th className="py-2.5 px-3 text-right">EBITDA</th>
              <th className="py-2.5 px-3 text-right">Net Profit</th>
              <th className="py-2.5 px-3 text-right">Margin %</th>
              <th className="py-2.5 px-3 text-right">EPS (₹)</th>
              <th className="py-2.5 px-3 text-center">Audited</th>
              <th className="py-2.5 px-3 text-center">PIT Provenance</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.03]">
            {recentFirst.map((s, idx) => {
              const margin = s.revenue && s.net_profit && s.revenue > 0 ? (s.net_profit / s.revenue) * 100.0 : null;
              const provenanceLabel = s.data_status === "STATUTORY_FALLBACK_LAG"
                ? "STATUTORY_FALLBACK_LAG (45D)"
                : s.data_status === "SECTOR_ESTIMATE"
                ? "SECTOR_ESTIMATE (IMPUTED)"
                : s.filing_date
                ? `OBSERVED (${s.filing_date})`
                : "OBSERVED_TIMESTAMP";
              const isFallback = s.data_status === "STATUTORY_FALLBACK_LAG" || s.data_status === "SECTOR_ESTIMATE";

              return (
                <tr key={s.period_end_date || idx} className="hover:bg-white/[0.02] transition-colors">
                  <td className="py-2 px-3 text-slate-200 font-medium whitespace-nowrap">
                    {s.period_end_date}
                  </td>
                  <td className="py-2 px-3 text-right text-slate-100 tabular-nums">
                    {formatCr(s.revenue)}
                  </td>
                  <td className="py-2 px-3 text-right text-slate-300 tabular-nums">
                    {formatCr(s.ebitda)}
                  </td>
                  <td
                    className={cn(
                      "py-2 px-3 text-right font-semibold tabular-nums",
                      (s.net_profit || 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                    )}
                  >
                    {formatCr(s.net_profit)}
                  </td>
                  <td className="py-2 px-3 text-right text-slate-300 tabular-nums">
                    {margin !== null ? `${margin.toFixed(1)}%` : "—"}
                  </td>
                  <td className="py-2 px-3 text-right text-cyan-300 tabular-nums">
                    {s.eps !== null && s.eps !== undefined && s.eps > 0 ? `₹${s.eps.toFixed(2)}` : "—"}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className={cn(
                        "text-[9px] px-1.5 py-0.5 rounded font-mono",
                        s.is_audited
                          ? "bg-emerald-950/60 border border-emerald-500/30 text-emerald-300"
                          : "bg-slate-800/60 border border-slate-700/40 text-slate-400"
                      )}
                    >
                      {s.is_audited ? "Audited" : "Reviewed"}
                    </span>
                  </td>
                  <td className="py-2 px-3 text-center">
                    <span
                      className={cn(
                        "text-[9px] px-2 py-0.5 rounded font-mono tracking-tight inline-block",
                        isFallback
                          ? "bg-amber-950/70 border border-amber-500/40 text-amber-300"
                          : "bg-emerald-950/70 border border-emerald-500/40 text-emerald-300"
                      )}
                    >
                      {provenanceLabel}
                    </span>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default QuarterlyFinancialsCard;
