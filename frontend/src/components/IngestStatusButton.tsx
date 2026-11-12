"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { Zap, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { triggerSystemIngest, fetchIngestStatus, IngestStatusResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

interface IngestStatusButtonProps {
  compact?: boolean;
  className?: string;
}

export default function IngestStatusButton({
  compact = false,
  className = "",
}: IngestStatusButtonProps) {
  const [status, setStatus] = useState<"idle" | "running" | "completed" | "error">("idle");
  const [progress, setProgress] = useState(0);
  const [total, setTotal] = useState(0);
  const [currentBatch, setCurrentBatch] = useState(0);
  const [totalBatches, setTotalBatches] = useState(0);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);
  const revertTimerRef = useRef<NodeJS.Timeout | null>(null);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const startPolling = useCallback(() => {
    stopPolling();
    pollTimerRef.current = setInterval(async () => {
      try {
        const data: IngestStatusResponse = await fetchIngestStatus();
        if (typeof window !== "undefined") {
          window.dispatchEvent(new CustomEvent("mil:ingest-progress", { detail: data }));
        }

        if (data.status === "running") {
          setStatus("running");
          setProgress(data.progress || 0);
          setTotal(data.total || 130);
          setCurrentBatch(data.current_batch || 1);
          setTotalBatches(data.total_batches || 6);
        } else if (data.status === "completed") {
          setStatus("completed");
          setProgress(data.total || 130);
          setTotal(data.total || 130);
          stopPolling();
          // Dispatch single refresh event to let ScreenerWorkspace update cleanly once
          if (typeof window !== "undefined") {
            window.dispatchEvent(new CustomEvent("mil:screener-refresh"));
          }
          if (revertTimerRef.current) clearTimeout(revertTimerRef.current);
          revertTimerRef.current = setTimeout(() => {
            setStatus("idle");
          }, 5000);
        } else if (data.status === "error") {
          setStatus("error");
          stopPolling();
          if (revertTimerRef.current) clearTimeout(revertTimerRef.current);
          revertTimerRef.current = setTimeout(() => {
            setStatus("idle");
          }, 5000);
        }
      } catch (err) {
        console.warn("[IngestStatusButton] Poll error:", err);
      }
    }, 2000);
  }, [stopPolling]);

  // Initial check on mount in case an ingest is already running in background
  useEffect(() => {
    fetchIngestStatus()
      .then((data) => {
        if (data.status === "running") {
          setStatus("running");
          setProgress(data.progress || 0);
          setTotal(data.total || 130);
          setCurrentBatch(data.current_batch || 1);
          setTotalBatches(data.total_batches || 6);
          startPolling();
        }
      })
      .catch(() => {});

    return () => {
      stopPolling();
      if (revertTimerRef.current) clearTimeout(revertTimerRef.current);
    };
  }, [startPolling, stopPolling]);

  const handleClick = async () => {
    if (isSubmitting || status === "running") return;
    setIsSubmitting(true);
    try {
      await triggerSystemIngest();
      setStatus("running");
      setProgress(0);
      setTotal(130);
      setCurrentBatch(1);
      setTotalBatches(6);
      startPolling();
    } catch (err) {
      console.error("[IngestStatusButton] Ingest dispatch failed:", err);
      setStatus("error");
      if (revertTimerRef.current) clearTimeout(revertTimerRef.current);
      revertTimerRef.current = setTimeout(() => {
        setStatus("idle");
      }, 5000);
    } finally {
      setIsSubmitting(false);
    }
  };

  const isRunning = isSubmitting || status === "running";

  if (compact) {
    return (
      <button
        onClick={handleClick}
        disabled={isRunning}
        title={
          isRunning
            ? `Syncing ${progress}/${total || 130} (Batch ${currentBatch}/${totalBatches})`
            : status === "completed"
            ? "Cloud DB Synced"
            : "Execute Universal Dynamic Ingestion"
        }
        className={cn(
          "flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono transition-colors",
          isRunning
            ? "text-cyan-300 font-bold"
            : status === "completed"
            ? "text-emerald-400 font-bold"
            : status === "error"
            ? "text-rose-400 font-bold"
            : "text-emerald-400 hover:text-emerald-300",
          className
        )}
      >
        {isSubmitting ? (
          <Loader2 className="w-4 h-4 mb-0.5 animate-spin text-cyan-400" />
        ) : status === "running" ? (
          <Loader2 className="w-4 h-4 mb-0.5 animate-spin text-cyan-400" />
        ) : status === "completed" ? (
          <CheckCircle2 className="w-4 h-4 mb-0.5 text-emerald-400" />
        ) : status === "error" ? (
          <AlertCircle className="w-4 h-4 mb-0.5 text-rose-400" />
        ) : (
          <Zap className="w-4 h-4 mb-0.5 text-emerald-400" />
        )}
        <span>
          {isSubmitting
            ? "Wait..."
            : status === "running"
            ? `${total ? Math.round((progress / total) * 100) : 0}%`
            : status === "completed"
            ? "Synced"
            : status === "error"
            ? "Error"
            : "Ingest"}
        </span>
      </button>
    );
  }

  return (
    <button
      onClick={handleClick}
      disabled={isRunning}
      title={
        isRunning
          ? `Syncing ${progress}/${total || 130} (Batch ${currentBatch}/${totalBatches})...`
          : status === "completed"
          ? "Cloud DB Synced (2.7M Bars)"
          : "Execute Universal Dynamic Ingestion via Cloud Ingest Pipeline"
      }
      className={cn(
        "flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-mono font-medium transition-all border",
        status === "completed"
          ? "bg-emerald-950/60 border-emerald-500/60 text-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
          : status === "error"
          ? "bg-rose-950/60 border-rose-500/60 text-rose-300 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
          : isRunning
          ? "bg-cyan-950/60 border-cyan-500/60 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.25)] animate-pulse"
          : "bg-white/[0.04] hover:bg-emerald-950/30 text-emerald-300 hover:text-emerald-200 border-white/[0.08] hover:border-emerald-500/40",
        className
      )}
    >
      {isSubmitting ? (
        <>
          <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
          <span className="hidden sm:inline">Dispatching...</span>
        </>
      ) : status === "running" ? (
        <>
          <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
          <span className="hidden sm:inline">
            Syncing {progress}/{total || 130} (Batch {currentBatch}/{totalBatches || 6})...
          </span>
          <span className="sm:hidden">
            {total ? Math.round((progress / total) * 100) : 0}%
          </span>
        </>
      ) : status === "completed" ? (
        <>
          <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
          <span>Cloud DB Synced</span>
        </>
      ) : status === "error" ? (
        <>
          <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
          <span>Sync Failed</span>
        </>
      ) : (
        <>
          <Zap className="w-3.5 h-3.5 text-emerald-400" />
          <span className="hidden sm:inline">Dynamic Ingest</span>
          <span className="sm:hidden">Ingest</span>
        </>
      )}
    </button>
  );
}
