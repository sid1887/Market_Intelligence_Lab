"use client";

import React, { useState, useEffect } from "react";
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
  const [liveBatchJob, setLiveBatchJob] = useState<ActivePlatformJob | null>(null);

  useEffect(() => {
    const handleProgress = (e: CustomEvent) => {
      const data = e.detail;
      if (!data) return;
      if (data.status === "running") {
        setLiveBatchJob({
          job_id: "cloud-ingest",
          status: "RUNNING",
          stage: data.stage || "CLOUD_INCREMENTAL_SYNC",
          progress_pct: data.total > 0 ? Math.round((data.progress / data.total) * 100) : 0,
          records_processed: data.progress,
          records_total: data.total,
          symbol: data.last_symbol || undefined,
          message: `Batch ${data.current_batch || 1}/${data.total_batches || 6} • ${data.progress}/${data.total} equities (${data.elapsed_sec?.toFixed(1) || 0}s)`,
        });
      } else if (data.status === "completed") {
        setLiveBatchJob({
          job_id: "cloud-ingest",
          status: "SUCCEEDED",
          stage: "COMPLETED",
          progress_pct: 100,
          records_processed: data.total,
          records_total: data.total,
          message: data.message || "Cloud market ingestion completed successfully.",
        });
        setTimeout(() => setLiveBatchJob(null), 5000);
      } else if (data.status === "error") {
        setLiveBatchJob({
          job_id: "cloud-ingest",
          status: "FAILED",
          stage: "ERROR",
          progress_pct: 0,
          error: data.message || "Ingestion error",
        });
        setTimeout(() => setLiveBatchJob(null), 6000);
      }
    };

    window.addEventListener("mil:ingest-progress", handleProgress as EventListener);
    return () => window.removeEventListener("mil:ingest-progress", handleProgress as EventListener);
  }, []);

  const currentJob = liveBatchJob || activeJob;
  if (!currentJob) return null;

  const isRunning = currentJob.status === "RUNNING" || currentJob.status === "QUEUED";
  const isSucceeded = currentJob.status === "SUCCEEDED";
  const isFailed = currentJob.status === "FAILED";

  const stageLabel = (currentJob.stage || "PROCESSING").replace(/_/g, " ").toUpperCase();
  const progressPct = Math.min(100, Math.max(0, currentJob.progress_pct || 0));

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

            {currentJob.symbol && (
              <span className="font-semibold text-cyan-300 bg-cyan-950/60 px-2 py-0.5 rounded border border-cyan-500/40">
                [{currentJob.symbol}]
              </span>
            )}

            {currentJob.records_total !== undefined && currentJob.records_total > 0 && (
              <span className="text-slate-400 text-[11px] tabular-nums">
                {currentJob.records_processed ?? 0} / {currentJob.records_total} bars
              </span>
            )}

            {currentJob.message && (
              <span className="text-slate-300 text-[11px] truncate max-w-md">
                {currentJob.message}
              </span>
            )}

            {currentJob.error && (
              <span className="text-rose-400 text-[11px] font-medium truncate max-w-md">
                Error: {currentJob.error}
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
            onClick={() => {
              setLiveBatchJob(null);
              onDismiss();
            }}
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
