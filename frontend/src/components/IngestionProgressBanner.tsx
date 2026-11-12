"use client";

import React from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Loader2, CheckCircle2, AlertCircle, X } from "lucide-react";
import { ActivePlatformJob } from "@/hooks/usePlatformEvents";
import { cn } from "@/lib/utils";

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
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.25, ease: "easeOut" }}
        className={cn(
          "shrink-0 w-full px-4 py-2 border-b flex flex-col sm:flex-row items-center justify-between gap-3 text-xs font-mono transition-all shadow-md",
          isFailed
            ? "bg-rose-950/80 border-rose-500/40 text-rose-200"
            : isSucceeded
            ? "bg-emerald-950/80 border-emerald-500/40 text-emerald-200"
            : "bg-[#060c18] border-cyan-500/30 text-cyan-200"
        )}
      >
        {/* Left: Status Icon + Stage + Symbol Details */}
        <div className="flex items-center gap-2.5 flex-1 min-w-0">
          {isRunning && (
            <div className="relative flex items-center justify-center">
              <Loader2 className="w-4 h-4 animate-spin text-cyan-400 shrink-0" />
            </div>
          )}
          {isSucceeded && (
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          )}
          {isFailed && (
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
          )}

          <div className="flex items-center gap-2 flex-wrap min-w-0">
            <span className="font-bold tracking-wide uppercase px-2 py-0.5 rounded bg-black/50 border border-white/[0.1] text-white">
              {stageLabel}
            </span>

            {activeJob.symbol && (
              <span className="font-semibold text-cyan-300 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-500/40">
                [{activeJob.symbol}]
              </span>
            )}

            {activeJob.records_total !== undefined && activeJob.records_total > 0 && (
              <span className="text-slate-400 text-[11px] tabular-nums">
                {activeJob.records_processed ?? 0} / {activeJob.records_total} bars
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
            <div className="flex items-center gap-2.5 w-full sm:w-56">
              <div className="flex-1 h-2 bg-black/60 rounded-full overflow-hidden border border-white/[0.1] relative">
                <div
                  className="h-full relative overflow-hidden rounded-full transition-all duration-300 bg-gradient-to-r from-cyan-500 via-teal-400 to-emerald-400"
                  style={{ width: `${progressPct}%` }}
                >
                  <div className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer" />
                </div>
              </div>
              <span className="text-[11px] font-bold text-slate-100 shrink-0 min-w-[36px] text-right tabular-nums">
                {progressPct.toFixed(0)}%
              </span>
            </div>
          )}

          <button
            onClick={onDismiss}
            className="p-1 rounded-lg hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
            title="Dismiss banner"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}
