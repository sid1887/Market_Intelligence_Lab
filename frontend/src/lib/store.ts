"use client";

import { useSyncExternalStore } from "react";

/**
 * Strongly-typed event payloads across Market Intelligence Lab
 */
export interface MilEventMap {
  "mil:screener-refresh": { source?: string; timestamp?: number } | undefined;
  "mil:watchlist-change": { symbol: string; is_watchlist: boolean };
  "mil:tearsheet-refresh": { symbol: string } | undefined;
  "mil:ingest-progress": { progress_pct: number; stage?: string; message?: string };
  "mil:open-copilot": { symbol?: string; initialPrompt?: string } | undefined;
  "mil:open-command-palette": undefined;
  "mil:context-update": { symbol?: string; price?: number | null; verdict?: string | null };
  "mil:open-system-logs": undefined;
}

export type MilEventName = keyof MilEventMap;

type MilEventListener<K extends MilEventName> = (payload: MilEventMap[K]) => void;

class MilEventBus {
  /**
   * Dispatch a typed platform event across components and window listeners.
   */
  emit<K extends MilEventName>(event: K, payload?: MilEventMap[K]): void {
    if (typeof window === "undefined") return;
    const customEvent = new CustomEvent(event, { detail: payload });
    window.dispatchEvent(customEvent);
  }

  /**
   * Subscribe to a typed platform event with automatic cleanup return.
   */
  on<K extends MilEventName>(event: K, listener: MilEventListener<K>): () => void {
    if (typeof window === "undefined") return () => {};

    const handler = (e: Event) => {
      const customEvent = e as CustomEvent<MilEventMap[K]>;
      listener(customEvent.detail);
    };

    window.addEventListener(event, handler);
    return () => window.removeEventListener(event, handler);
  }
}

export const milEvents = new MilEventBus();

// ─── Reactive State Store via React 18 useSyncExternalStore (No External Dep) ─

interface MilStoreState {
  lastScreenerRefresh: number;
  lastWatchlistChange: { symbol: string; is_watchlist: boolean; timestamp: number } | null;
  lastTearsheetRefresh: { symbol: string; timestamp: number } | null;
}

let storeState: MilStoreState = {
  lastScreenerRefresh: Date.now(),
  lastWatchlistChange: null,
  lastTearsheetRefresh: null,
};

const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

if (typeof window !== "undefined") {
  window.addEventListener("mil:screener-refresh", () => {
    storeState = { ...storeState, lastScreenerRefresh: Date.now() };
    notify();
  });

  window.addEventListener("mil:watchlist-change", (e: Event) => {
    const detail = (e as CustomEvent<{ symbol: string; is_watchlist: boolean }>).detail;
    if (detail) {
      storeState = {
        ...storeState,
        lastWatchlistChange: { ...detail, timestamp: Date.now() },
      };
      notify();
    }
  });

  window.addEventListener("mil:tearsheet-refresh", (e: Event) => {
    const detail = (e as CustomEvent<{ symbol: string }>).detail;
    if (detail) {
      storeState = {
        ...storeState,
        lastTearsheetRefresh: { ...detail, timestamp: Date.now() },
      };
      notify();
    }
  });
}

function subscribe(callback: () => void) {
  listeners.add(callback);
  return () => {
    listeners.delete(callback);
  };
}

function getSnapshot() {
  return storeState;
}

function getServerSnapshot() {
  return storeState;
}

/**
 * Lightweight reactive hook to track platform events without manual useEffect boilerplate.
 */
export function useMilStore(): MilStoreState {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
