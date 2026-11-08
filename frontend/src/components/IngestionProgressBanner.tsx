"use client";

import React from "react";
import { Loader2, CheckCircle2, AlertCircle, X } from "lucide-react";
import { ActivePlatformJob } from "@/hooks/usePlatformEvents";

interface IngestionProgressBannerProps {
  activeJob: ActivePlatformJob | null;
  onDismiss: () => void;
}

export default function IngestionProgressBanner({
  activeJob,
  onDismiss,
}: IngestionProgressBannerProps) {
  if (!activeJob) return null;

  const isRunning = activeJob.status === "RUNNING" || activeJob.status === "QUEUED";
  const isSucceeded = activeJob.status === "SUCCEEDED";
  const isFailed = activeJob.status === "FAILED";

  const stageLabel = (activeJob.stage || "PROCESSING").replace(/_/g, " ").toUpperCase();
  const progressPct = Math.min(100, Math.max(0, activeJob.progress_pct || 0));

  return (
    <div
      className={`shrink-0 w-full px-4 py-2 border-b flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-mono transition-colors ${
        isFailed
          ? "bg-rose-950/40 border-rose-800/40 text-rose-300"
          : isSucceeded
          ? "bg-emerald-950/40 border-emerald-800/40 text-emerald-300"
          : "bg-cyan-950/30 border-cyan-800/40 text-cyan-200"
      }`}
    >
      {/* Left: Status Icon + Stage + Symbol Details */}
      <div className="flex items-center gap-2.5 flex-1 min-w-0">
        {isRunning && (
          <Loader2 className="w-4 h-4 animate-spin text-cyan-400 shrink-0" />
        )}
        {isSucceeded && (
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
        )}
        {isFailed && (
          <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
        )}

        <div className="flex items-center gap-2 flex-wrap min-w-0">
          <span className="font-bold tracking-wide uppercase px-2 py-0.5 rounded bg-black/40 border border-white/[0.08]">
            {stageLabel}
          </span>

          {activeJob.symbol && (
            <span className="font-semibold text-white bg-cyan-900/40 px-2 py-0.5 rounded border border-cyan-500/30">
              [{activeJob.symbol}]
            </span>
          )}

          {activeJob.records_total !== undefined && activeJob.records_total > 0 && (
            <span className="text-slate-400 text-[11px]">
              {activeJob.records_processed ?? 0} / {activeJob.records_total} processed
            </span>
          )}

          {activeJob.message && (
            <span className="text-slate-300 text-[11px] truncate max-w-md">
              {activeJob.message}
            </span>
          )}

          {activeJob.error && (
            <span className="text-rose-400 text-[11px] font-medium truncate max-w-md">
              Error: {activeJob.error}
            </span>
          )}
        </div>
      </div>

      {/* Right: Progress percentage & bar or dismiss button */}
      <div className="flex items-center gap-3 shrink-0 w-full sm:w-auto justify-end">
        {isRunning && (
          <div className="flex items-center gap-2.5 w-full sm:w-48">
            <div className="flex-1 h-2 bg-slate-900/80 rounded-full overflow-hidden border border-white/[0.08] relative">
              <div
                className="h-full relative overflow-hidden rounded-full transition-all duration-300"
                style={{ width: `${progressPct}%` }}
              >
                <div className="absolute inset-0 bg-gradient-to-r from-emerald-500 via-teal-300 to-emerald-500 animate-shimmer" />
              </div>
            </div>
            <span className="text-[11px] font-bold text-slate-200 shrink-0 min-w-[32px] text-right">
              {progressPct.toFixed(0)}%
            </span>
          </div>
        )}

        <button
          onClick={onDismiss}
          className="p-1 rounded hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
          title="Dismiss banner"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
