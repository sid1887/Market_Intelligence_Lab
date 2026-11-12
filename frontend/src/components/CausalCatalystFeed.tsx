"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  TrendingUp,
  FileText,
  Newspaper,
  Compass,
  Zap,
  Loader2,
} from "lucide-react";
import { CausalCatalyst, fetchLiveCatalysts, apiFetch } from "@/lib/api";
import { cn } from "@/lib/utils";

interface CausalCatalystFeedProps {
  currentSymbol?: string | null;
  compact?: boolean;
  className?: string;
}

export default function CausalCatalystFeed({
  currentSymbol,
  compact = false,
  className,
}: CausalCatalystFeedProps) {
  const [catalysts, setCatalysts] = useState<CausalCatalyst[]>([]);
  const [loading, setLoading] = useState(true);
  const [scanning, setScanning] = useState(false);
  const [selectedCatalyst, setSelectedCatalyst] = useState<CausalCatalyst | null>(null);

  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      const data = await fetchLiveCatalysts(15);
      setCatalysts(data);
      if (currentSymbol) {
        const found = data.find((c) => c.symbol.toUpperCase() === currentSymbol.toUpperCase());
        setSelectedCatalyst(found || null);
      } else if (data.length > 0) {
        setSelectedCatalyst(data[0]);
      }
    } catch (err) {
      console.warn("Failed to load catalysts:", err);
    } finally {
      setLoading(false);
    }
  }, [currentSymbol]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleScanAnomalies = async () => {
    setScanning(true);
    try {
      await apiFetch("/catalysts/scan", { method: "POST" });
      await loadData();
    } catch (err) {
      console.error("Catalyst scan error:", err);
    } finally {
      setScanning(false);
    }
  };

  // If a stock is currently inspected, find its catalyst
  const activeStockCatalyst = currentSymbol
    ? catalysts.find((c) => c.symbol.toUpperCase() === currentSymbol.toUpperCase())
    : selectedCatalyst;

  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.08] bg-[#06090f] font-mono text-xs relative overflow-hidden",
        compact ? "p-3.5 space-y-3" : "p-5 shadow-2xl space-y-4",
        className
      )}
    >
      {/* Top subtle specular edge */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent pointer-events-none" />

      {/* Header Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.07]">
        <div className="flex items-center space-x-2.5">
          <span className="relative flex h-2.5 w-2.5">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500" />
          </span>
          <div>
            <h3 className="text-sm font-bold text-white tracking-wide flex items-center gap-2">
              <span>Market Pulse &amp; Causal Catalysts</span>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-bold">
                4-Pillar Radar
              </span>
            </h3>
            {!compact && (
              <p className="text-[11px] text-slate-400 mt-0.5">
                Intraday Anomaly Detection (&ge; 3.0% move or &ge; 2.5x RVOL) with Causal Attribution
              </p>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-2">
          <button
            onClick={handleScanAnomalies}
            disabled={scanning}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-cyan-950/50 border border-white/[0.08] hover:border-cyan-500/40 text-cyan-300 font-semibold text-[11px] transition-all shadow-sm disabled:opacity-50"
          >
            {scanning ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
            ) : (
              <Zap className="w-3.5 h-3.5 text-cyan-400" />
            )}
            <span>Scan Universe</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="py-8 flex items-center justify-center space-x-2 text-slate-400">
          <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
          <span>Polling institutional causal catalysts...</span>
        </div>
      ) : activeStockCatalyst ? (
        /* Primary Highlight Card */
        <div className="space-y-3">
          <div className="p-4 rounded-xl bg-[#090f1e]/90 border border-cyan-500/30 shadow-[0_0_20px_rgba(6,182,212,0.12)] space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex items-center space-x-2">
                <Link
                  href={`/stocks/${activeStockCatalyst.symbol}`}
                  className="text-base font-black text-white hover:text-cyan-300 transition-colors tracking-tight flex items-center gap-1"
                >
                  <span>{activeStockCatalyst.symbol}</span>
                  <span className="text-xs font-normal text-slate-400">
                    ({activeStockCatalyst.company_name})
                  </span>
                </Link>
                <span
                  className={cn(
                    "px-2 py-0.5 rounded text-[11px] font-bold tabular-nums border",
                    activeStockCatalyst.move_pct >= 0
                      ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
                      : "bg-rose-950/80 text-rose-300 border-rose-500/40"
                  )}
                >
                  {activeStockCatalyst.move_pct >= 0 ? "+" : ""}
                  {activeStockCatalyst.move_pct.toFixed(1)}%
                </span>
                <span className="px-2 py-0.5 rounded text-[10px] bg-white/[0.04] text-slate-300 border border-white/[0.08] tabular-nums">
                  {activeStockCatalyst.rvol.toFixed(1)}x RVOL
                </span>
              </div>

              {/* Classification Tag */}
              <span
                className={cn(
                  "px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border",
                  activeStockCatalyst.classification.includes("Idiosyncratic")
                    ? "bg-cyan-950/90 text-cyan-300 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                    : "bg-purple-950/90 text-purple-300 border-purple-500/50 shadow-[0_0_10px_rgba(168,85,247,0.2)]"
                )}
              >
                {activeStockCatalyst.classification}
              </span>
            </div>

            {/* Causal Headline */}
            <p className="text-xs font-bold text-slate-100 leading-relaxed bg-black/30 p-2.5 rounded-lg border border-white/[0.05]">
              {activeStockCatalyst.causal_headline}
            </p>

            {/* 4 Pillars Breakdown Grid */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-2.5 pt-1">
              {/* Pillar 1 */}
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1">
                <span className="text-[10px] text-cyan-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
                  <TrendingUp className="w-3.5 h-3.5" />
                  <span>Pillar 1: Structural Velocity &amp; Levels</span>
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  {activeStockCatalyst.causal_bullets?.[0] || "Structural memory within bounds."}
                </p>
              </div>

              {/* Pillar 2 */}
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1">
                <span className="text-[10px] text-purple-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
                  <Compass className="w-3.5 h-3.5" />
                  <span>Pillar 2: Sector &amp; Macro Breadth</span>
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  {activeStockCatalyst.causal_bullets?.[1] || "Sector dispersion analysis complete."}
                </p>
              </div>

              {/* Pillar 3 */}
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1">
                <span className="text-[10px] text-emerald-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5" />
                  <span>Pillar 3: Corporate Actions &amp; Filings</span>
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  {activeStockCatalyst.causal_bullets?.[2] || "Exchange disclosures inspected."}
                </p>
              </div>

              {/* Pillar 4 */}
              <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.05] space-y-1">
                <span className="text-[10px] text-amber-400 font-bold uppercase tracking-wider flex items-center gap-1.5">
                  <Newspaper className="w-3.5 h-3.5" />
                  <span>Pillar 4: Catalyst Wire &amp; News</span>
                </span>
                <p className="text-[11px] text-slate-300 leading-relaxed">
                  {activeStockCatalyst.causal_bullets?.[3] || "Wire developments scanned."}
                </p>
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="p-5 text-center text-slate-500">
          <p>No active anomalies triggered for {currentSymbol || "current watch"}.</p>
          <p className="text-[11px] text-slate-600 mt-1">
            Engine evaluates &ge; 3.0% price displacement or &ge; 2.5x RVOL relative volume surges.
          </p>
        </div>
      )}

      {/* Universe Stream Rail */}
      {catalysts.length > 1 && (
        <div className="pt-2 border-t border-white/[0.06] space-y-2">
          <span className="text-[10px] font-bold uppercase tracking-widest text-slate-500 block">
            Recent Market-Wide Catalyst Stream ({catalysts.length})
          </span>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {catalysts.map((cat) => (
              <div
                key={cat.id}
                onClick={() => setSelectedCatalyst(cat)}
                className={cn(
                  "p-2.5 rounded-xl border cursor-pointer transition-all flex items-center justify-between text-[11px]",
                  selectedCatalyst?.id === cat.id
                    ? "bg-cyan-950/40 border-cyan-500/50 shadow-[0_0_12px_rgba(6,182,212,0.15)]"
                    : "bg-white/[0.02] hover:bg-white/[0.05] border-white/[0.05] hover:border-cyan-500/30"
                )}
              >
                <div className="flex items-center space-x-2">
                  <span className="font-bold text-white font-mono">{cat.symbol}</span>
                  <span
                    className={cn(
                      "tabular-nums font-bold text-[10px]",
                      cat.move_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                    )}
                  >
                    {cat.move_pct >= 0 ? "+" : ""}
                    {cat.move_pct.toFixed(1)}%
                  </span>
                </div>
                <span className="text-[9px] text-slate-400 truncate max-w-[110px]">
                  {cat.classification.replace("Single-Stock", "").replace("Sector-Wide", "").trim()}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
