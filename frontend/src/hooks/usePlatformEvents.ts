"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import {
  getApiBase,
  fetchMacroTelemetry,
  fetchSupervisorStatus,
  MacroResponse,
  SupervisorStatus,
} from "@/lib/api";
import { RobustSSEParser, ServerSentEvent } from "@/lib/sseParser";

export interface ActivePlatformJob {
  job_id: string;
  stage: string;
  progress_pct: number;
  symbol?: string;
  records_processed?: number;
  records_total?: number;
  status: "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED" | "CANCELLED";
  message?: string;
  result?: Record<string, unknown>;
  error?: string;
}

export interface PlatformEventsState {
  macroData: MacroResponse | null;
  supervisorStatus: SupervisorStatus | null;
  activeJob: ActivePlatformJob | null;
  lastTickAt: number | null;
  lastIngestTimestamp: string | null;
  isConnected: boolean;
  error: string | null;
}

export function usePlatformEvents() {
  const [macroData, setMacroData] = useState<MacroResponse | null>(null);
  const [supervisorStatus, setSupervisorStatus] = useState<SupervisorStatus | null>(null);
  const [activeJob, setActiveJob] = useState<ActivePlatformJob | null>(null);
  const [lastTickAt, setLastTickAt] = useState<number | null>(null);
  const [lastIngestTimestamp, setLastIngestTimestamp] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const lastEventIdRef = useRef<string | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  const dismissActiveJob = useCallback(() => {
    setActiveJob(null);
  }, []);

  // 1. Initial snapshot on mount
  useEffect(() => {
    let active = true;

    fetchMacroTelemetry()
      .then((data) => {
        if (active && data) {
          setMacroData(data);
          setLastTickAt(Date.now());
        }
      })
      .catch((err) => {
        console.warn("Initial macro telemetry fetch error:", err);
      });

    fetchSupervisorStatus()
      .then((status) => {
        if (active && status) {
          setSupervisorStatus(status);
          if (status.last_ingestion_timestamp) {
            setLastIngestTimestamp(status.last_ingestion_timestamp);
          }
        }
      })
      .catch((err) => {
        console.warn("Initial supervisor status fetch error:", err);
      });

    return () => {
      active = false;
    };
  }, []);

  // 2. Continuous platform event streaming with recovery (or calm 20s polling on remote cloud / Vercel)
  useEffect(() => {
    let isDisposed = false;
    let reconnectDelay = 1000;

    const isRemote =
      typeof window !== "undefined" &&
      !window.location.hostname.includes("localhost") &&
      !window.location.hostname.includes("127.0.0.1");

    if (isRemote) {
      // Remote / Vercel deployment: Use periodic 20s polling instead of aggressive EventSource reconnect loops
      setIsConnected(true);
      setError(null);

      const pollRemote = () => {
        if (isDisposed) return;
        Promise.allSettled([fetchMacroTelemetry(), fetchSupervisorStatus()]).then(
          ([macroRes, supRes]) => {
            if (isDisposed) return;
            if (macroRes.status === "fulfilled" && macroRes.value) {
              setMacroData(macroRes.value);
              setLastTickAt(Date.now());
            }
            if (supRes.status === "fulfilled" && supRes.value) {
              setSupervisorStatus(supRes.value);
              if (supRes.value.last_ingestion_timestamp) {
                setLastIngestTimestamp(supRes.value.last_ingestion_timestamp);
              }
            }
            setIsConnected(true);
            setError(null);
          }
        );
      };

      const pollInterval = setInterval(pollRemote, 20000);
      return () => {
        isDisposed = true;
        clearInterval(pollInterval);
      };
    }

    const connectStream = () => {
      if (isDisposed) return;

      abortControllerRef.current?.abort();
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const base = getApiBase();
      const url = new URL(`${base}/events/stream`, typeof window !== "undefined" ? window.location.origin : "http://localhost:3000");
      if (lastEventIdRef.current) {
        url.searchParams.set("Last-Event-ID", lastEventIdRef.current);
      }

      const parser = new RobustSSEParser();

      fetch(url.toString(), {
        method: "GET",
        headers: {
          Accept: "text/event-stream",
          ...(lastEventIdRef.current ? { "Last-Event-ID": lastEventIdRef.current } : {}),
        },
        signal: controller.signal,
      })
        .then(async (response) => {
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: Failed to connect to event stream`);
          }
          if (!response.body) {
            throw new Error("No readable stream response body");
          }

          setIsConnected(true);
          setError(null);
          reconnectDelay = 1000; // Reset backoff on successful connect

          const reader = response.body.getReader();
          const decoder = new TextDecoder();

          while (!isDisposed) {
            const { done, value } = await reader.read();
            if (done) {
              parser.flush(handleEvent);
              break;
            }
            const chunk = decoder.decode(value, { stream: true });
            parser.feed(chunk, handleEvent);
          }
        })
        .catch((err) => {
          if (controller.signal.aborted || isDisposed) return;
          console.warn("Platform SSE Stream error:", err.message);
          setIsConnected(false);
          setError(err.message || "Disconnected");

          // Schedule reconnection with backoff
          reconnectTimeoutRef.current = setTimeout(() => {
            reconnectDelay = Math.min(reconnectDelay * 2, 10000);
            connectStream();
          }, reconnectDelay);
        });
    };

    const handleEvent = (sse: ServerSentEvent) => {
      if (sse.id) {
        lastEventIdRef.current = sse.id;
      }

      if (sse.event === "TELEMETRY_TICK") {
        try {
          const payload = JSON.parse(sse.data);
          if (payload.macro) {
            setMacroData(payload.macro);
          }
          if (payload.supervisor) {
            setSupervisorStatus((prev) =>
              prev ? { ...prev, supervisor_state: payload.supervisor } : null
            );
          }
          if (payload.last_ingestion_timestamp) {
            setLastIngestTimestamp(payload.last_ingestion_timestamp);
          }
          setLastTickAt(Date.now());
        } catch (e) {
          console.error("Malformed TELEMETRY_TICK payload:", e);
        }
      } else if (sse.event === "PROGRESS") {
        try {
          const data = JSON.parse(sse.data);
          const p = data.payload || {};
          setActiveJob({
            job_id: data.job_id,
            stage: data.stage || p.stage || "RUNNING",
            progress_pct: typeof p.progress_pct === "number" ? p.progress_pct : 0,
            symbol: p.current_symbol || p.symbol,
            records_processed: p.records_processed ?? p.processed,
            records_total: p.records_total ?? p.total,
            status: "RUNNING",
            message: p.message,
          });
        } catch (e) {
          console.error("Malformed PROGRESS payload:", e);
        }
      } else if (sse.event === "TERMINAL") {
        try {
          const data = JSON.parse(sse.data);
          const p = data.payload || {};
          setActiveJob((prev) => ({
            job_id: data.job_id,
            stage: data.stage || "COMPLETED",
            progress_pct: 100,
            symbol: undefined,
            records_processed: p.processed ?? prev?.records_processed,
            records_total: p.total ?? prev?.records_total,
            status: (p.status as ActivePlatformJob["status"]) || "SUCCEEDED",
            message: p.message || "Job completed successfully",
            result: p.result,
            error: p.error,
          }));
        } catch (e) {
          console.error("Malformed TERMINAL payload:", e);
        }
      } else if (sse.event === "SUPERVISOR_ALERT") {
        try {
          const data = JSON.parse(sse.data);
          if (data.status) {
            setSupervisorStatus((prev) =>
              prev ? { ...prev, supervisor_state: data.status } : null
            );
          }
        } catch (e) {
          console.error("Malformed SUPERVISOR_ALERT payload:", e);
        }
      }
    };

    connectStream();

    return () => {
      isDisposed = true;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      abortControllerRef.current?.abort();
      setIsConnected(false);
    };
  }, []);

  return {
    macroData,
    supervisorStatus,
    activeJob,
    lastTickAt,
    lastIngestTimestamp,
    isConnected,
    error,
    dismissActiveJob,
    setActiveJob,
    setLastIngestTimestamp,
  };
}
