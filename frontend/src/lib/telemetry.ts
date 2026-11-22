/**
 * Market Intelligence Lab — Client-side Telemetry & Log Aggregator
 * Ring buffer of recent client events, network fetches, and unhandled errors.
 * Automatically forwards WARN and ERROR events to /api/v1/system/client-logs.
 */

import { API_BASE, DEFAULT_HEADERS } from "./api";

export interface LogEntry {
  id: string;
  timestamp: string;
  level: "DEBUG" | "INFO" | "WARNING" | "ERROR";
  source: "client" | "server";
  logger: string;
  message: string;
  request_id?: string | null;
  module?: string;
  meta?: Record<string, unknown>;
}

class ClientTelemetryManager {
  private buffer: LogEntry[] = [];
  private maxBufferSize = 250;
  private isInitialized = false;

  public init() {
    if (this.isInitialized || typeof window === "undefined") return;
    this.isInitialized = true;

    // Capture uncaught exceptions
    window.addEventListener("error", (event) => {
      this.log("ERROR", `Uncaught: ${event.message}`, {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
        stack: event.error?.stack,
      });
    });

    // Capture unhandled promise rejections
    window.addEventListener("unhandledrejection", (event) => {
      const reason = event.reason;
      const msg = reason instanceof Error ? reason.message : String(reason);
      this.log("ERROR", `Unhandled Rejection: ${msg}`, {
        stack: reason instanceof Error ? reason.stack : undefined,
      });
    });

    this.log("INFO", "Client telemetry subsystem initialized", {
      userAgent: navigator.userAgent,
      screenWidth: window.innerWidth,
      screenHeight: window.innerHeight,
    });
  }

  public log(
    level: "DEBUG" | "INFO" | "WARNING" | "ERROR",
    message: string,
    meta?: Record<string, unknown>
  ) {
    const entry: LogEntry = {
      id: `cli-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      timestamp: new Date().toISOString(),
      level,
      source: "client",
      logger: "client.browser",
      message,
      meta,
    };

    this.buffer.push(entry);
    if (this.buffer.length > this.maxBufferSize) {
      this.buffer.shift();
    }

    // Auto-forward WARN and ERROR to backend
    if (level === "WARNING" || level === "ERROR") {
      this.forwardToBackend(entry);
    }
  }

  public getBuffer(): LogEntry[] {
    return [...this.buffer];
  }

  public clear() {
    this.buffer = [];
  }

  private async forwardToBackend(entry: LogEntry) {
    try {
      if (typeof window === "undefined") return;
      await fetch(`${API_BASE}/system/client-logs`, {
        method: "POST",
        headers: DEFAULT_HEADERS,
        body: JSON.stringify({
          level: entry.level,
          message: entry.message,
          meta: entry.meta,
        }),
      });
    } catch {
      // Avoid recursive failure
    }
  }
}

export const telemetry = new ClientTelemetryManager();

if (typeof window !== "undefined") {
  telemetry.init();
}
