"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { getJob, getEventStreamUrl, JobRun, JobEventPayload } from "@/lib/api";

export interface JobStreamOptions {
  onComplete?: (result: Record<string, unknown> | null) => void;
  onError?: (error: string) => void;
  autoCloseOnTerminal?: boolean;
}

export interface JobStreamState {
  job: JobRun | null;
  status: "IDLE" | "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  progress: number;
  stage: string | null;
  stageMessage: string | null;
  error: string | null;
  isStreaming: boolean;
}

export function useJobStream(jobId: string | null, options: JobStreamOptions = {}) {
  const { onComplete, onError, autoCloseOnTerminal = true } = options;

  const [state, setState] = useState<JobStreamState>({
    job: null,
    status: "IDLE",
    progress: 0,
    stage: null,
    stageMessage: null,
    error: null,
    isStreaming: false,
  });

  const eventSourceRef = useRef<EventSource | null>(null);
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
  }, [onComplete, onError]);

  const closeStream = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
      setState((prev) => ({ ...prev, isStreaming: false }));
    }
  }, []);

  useEffect(() => {
    if (!jobId) {
      closeStream();
      setState({
        job: null,
        status: "IDLE",
        progress: 0,
        stage: null,
        stageMessage: null,
        error: null,
        isStreaming: false,
      });
      return;
    }

    // 1. Initial snapshot fetch to avoid missing fast-completing jobs
    let isCancelled = false;
    getJob(jobId)
      .then((job) => {
        if (isCancelled) return;
        setState((prev) => ({
          ...prev,
          job,
          status: job.status,
          progress: job.progress_pct,
          stage: job.current_stage,
          stageMessage: job.stage_message,
          error: job.error_detail,
        }));

        if (job.status === "SUCCEEDED") {
          onCompleteRef.current?.(job.result_payload);
          return;
        }
        if (job.status === "FAILED") {
          onErrorRef.current?.(job.error_detail || "Job failed");
          return;
        }
      })
      .catch((err) => {
        if (!isCancelled) {
          console.error("Failed to query initial job snapshot:", err);
        }
      });

    // 2. Connect to Server-Sent Events stream
    const streamUrl = getEventStreamUrl(jobId);
    const source = new EventSource(streamUrl);
    eventSourceRef.current = source;
    setState((prev) => ({ ...prev, isStreaming: true }));

    const handlePayload = (eventType: string, dataStr: string) => {
      try {
        const payload: JobEventPayload = JSON.parse(dataStr);
        const newStatus = (payload.status || eventType) as JobStreamState["status"];
        const newProgress = typeof payload.progress_pct === "number" ? payload.progress_pct : undefined;
        const newStage = payload.stage || null;
        const newMessage = payload.message || null;
        const errorDetail = payload.error || null;

        setState((prev) => ({
          ...prev,
          status: newStatus || prev.status,
          progress: newProgress !== undefined ? newProgress : prev.progress,
          stage: newStage || prev.stage,
          stageMessage: newMessage || prev.stageMessage,
          error: errorDetail || prev.error,
        }));

        if (newStatus === "SUCCEEDED" || eventType === "SUCCEEDED") {
          onCompleteRef.current?.(payload.result || payload);
          if (autoCloseOnTerminal) {
            closeStream();
          }
        } else if (newStatus === "FAILED" || eventType === "FAILED") {
          onErrorRef.current?.(errorDetail || "Job execution failed");
          if (autoCloseOnTerminal) {
            closeStream();
          }
        }
      } catch (e) {
        console.warn("Failed to parse SSE job payload:", e, dataStr);
      }
    };

    source.onmessage = (event) => {
      handlePayload("message", event.data);
    };

    const eventNames = ["QUEUED", "RUNNING", "PROGRESS", "STAGE_UPDATE", "SUCCEEDED", "FAILED", "HEARTBEAT"];
    eventNames.forEach((evName) => {
      source.addEventListener(evName, (e: MessageEvent) => {
        handlePayload(evName, e.data);
      });
    });

    source.onerror = (e) => {
      // EventSource automatically retries on connection error
      console.warn("SSE connection error or reconnecting:", e);
    };

    return () => {
      isCancelled = true;
      source.close();
      eventSourceRef.current = null;
    };
  }, [jobId, autoCloseOnTerminal, closeStream]);

  return {
    ...state,
    closeStream,
  };
}
