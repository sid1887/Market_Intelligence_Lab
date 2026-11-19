"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import {
  Bell,
  BellRing,
  ExternalLink,
  CheckCheck,
  Settings,
  Sparkles,
  TrendingUp,
  TrendingDown,
  Clock,
  X,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { fetchLiveCatalysts, CausalCatalyst } from "@/lib/api";

interface NotificationCenterPopoverProps {
  isPushSubscribed: boolean;
  onOpenPushSettings: () => void;
}

export default function NotificationCenterPopover({
  isPushSubscribed,
  onOpenPushSettings,
}: NotificationCenterPopoverProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [catalysts, setCatalysts] = useState<CausalCatalyst[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [filter, setFilter] = useState<"ALL" | "BULLISH" | "BEARISH">("ALL");
  const [readIds, setReadIds] = useState<Set<number>>(new Set());
  const popoverRef = useRef<HTMLDivElement>(null);

  // Load read IDs from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem("mil:read-catalyst-ids");
      if (stored) {
        setReadIds(new Set(JSON.parse(stored)));
      }
    } catch {
      // ignore
    }
  }, []);

  // Fetch live catalysts
  const loadCatalysts = async () => {
    try {
      setIsLoading(true);
      const data = await fetchLiveCatalysts(15);
      setCatalysts(data);
    } catch (err) {
      console.warn("Failed to fetch notification center catalysts:", err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    loadCatalysts();
    const interval = setInterval(loadCatalysts, 45000);
    return () => clearInterval(interval);
  }, []);

  // Handle outside click & escape
  useEffect(() => {
    if (!isOpen) return;
    const handleDown = (e: MouseEvent) => {
      if (popoverRef.current && !popoverRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    const handleKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    document.addEventListener("mousedown", handleDown);
    document.addEventListener("keydown", handleKey);
    return () => {
      document.removeEventListener("mousedown", handleDown);
      document.removeEventListener("keydown", handleKey);
    };
  }, [isOpen]);

  const unreadCount = catalysts.filter((c) => !readIds.has(c.id)).length;

  const markAllAsRead = () => {
    const allIds = new Set(catalysts.map((c) => c.id));
    setReadIds(allIds);
    try {
      localStorage.setItem("mil:read-catalyst-ids", JSON.stringify(Array.from(allIds)));
    } catch {
      // ignore
    }
  };

  const markAsRead = (id: number) => {
    setReadIds((prev) => {
      const next = new Set(prev).add(id);
      try {
        localStorage.setItem("mil:read-catalyst-ids", JSON.stringify(Array.from(next)));
      } catch {
        // ignore
      }
      return next;
    });
  };

  const filteredCatalysts = catalysts.filter((c) => {
    if (filter === "BULLISH") return c.move_pct > 0;
    if (filter === "BEARISH") return c.move_pct < 0;
    return true;
  });

  const formatRelativeTime = (isoString?: string) => {
    if (!isoString) return "just now";
    try {
      const diffSec = Math.floor((Date.now() - new Date(isoString).getTime()) / 1000);
      if (diffSec < 60) return `${Math.max(1, diffSec)}s ago`;
      if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
      if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
      return `${Math.floor(diffSec / 86400)}d ago`;
    } catch {
      return "recently";
    }
  };

  return (
    <div className="relative" ref={popoverRef}>
      {/* Bell Trigger Button */}
      <button
        onClick={() => {
          setIsOpen(!isOpen);
          if (!isOpen) loadCatalysts();
        }}
        title={
          unreadCount > 0
            ? `${unreadCount} unread market catalyst alerts`
            : "Market Catalyst Alerts & Radar"
        }
        aria-label="Toggle notifications center"
        className={cn(
          "relative flex items-center justify-center p-2 rounded-xl transition-all shadow-sm",
          isOpen
            ? "bg-cyan-950/60 border border-cyan-500/50 text-cyan-300"
            : "bg-white/[0.04] hover:bg-cyan-950/40 border border-white/[0.08] hover:border-cyan-500/40 text-slate-300 hover:text-cyan-300"
        )}
      >
        {isPushSubscribed ? (
          <BellRing className="w-4 h-4 text-cyan-400" />
        ) : (
          <Bell className="w-4 h-4 text-slate-400" />
        )}

        {/* Unread Counter Badge */}
        {unreadCount > 0 ? (
          <span className="absolute -top-1 -right-1 flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full bg-rose-500 text-[10px] font-mono font-bold text-white shadow-md animate-in fade-in zoom-in-75">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        ) : (
          /* Subscribed / Active Radar Status Dot */
          <span className="absolute top-1 right-1 flex h-2 w-2">
            {isPushSubscribed ? (
              <>
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
              </>
            ) : (
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400/60" />
            )}
          </span>
        )}
      </button>

      {/* Dropdown Popover */}
      {isOpen && (
        <div className="fixed inset-x-2 top-14 sm:absolute sm:inset-x-auto sm:right-0 sm:top-full sm:mt-2 w-auto sm:w-[400px] max-w-[calc(100vw-1rem)] max-h-[520px] bg-[#070b12] border border-cyan-500/30 rounded-2xl shadow-[0_10px_40px_rgba(0,0,0,0.8),0_0_20px_rgba(6,182,212,0.15)] flex flex-col z-50 overflow-hidden backdrop-blur-xl animate-in fade-in slide-in-from-top-2 duration-150">
          {/* Header */}
          <div className="p-3.5 border-b border-white/[0.08] bg-gradient-to-r from-cyan-950/40 to-slate-900/60 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <div className="w-6 h-6 rounded-lg bg-cyan-500/20 border border-cyan-500/40 flex items-center justify-center">
                <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
              </div>
              <div>
                <h3 className="text-xs font-mono font-bold text-slate-100 flex items-center gap-1.5">
                  Catalyst Alerts
                  {unreadCount > 0 && (
                    <span className="text-[10px] px-1.5 py-0.2 bg-rose-500/20 text-rose-400 border border-rose-500/30 rounded font-mono">
                      {unreadCount} new
                    </span>
                  )}
                </h3>
                <p className="text-[10px] text-slate-400 font-mono">
                  Real-time Causal Anomaly Feed
                </p>
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  title="Mark all as read"
                  className="p-1 rounded text-slate-400 hover:text-cyan-300 hover:bg-white/[0.05] transition-colors"
                >
                  <CheckCheck className="w-4 h-4" />
                </button>
              )}
              <button
                onClick={() => {
                  setIsOpen(false);
                  onOpenPushSettings();
                }}
                title="Push Notification Settings"
                className="p-1 rounded text-slate-400 hover:text-cyan-300 hover:bg-white/[0.05] transition-colors"
              >
                <Settings className="w-4 h-4" />
              </button>
              <button
                onClick={() => setIsOpen(false)}
                className="p-1 rounded text-slate-400 hover:text-slate-200 hover:bg-white/[0.05] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* Filter Bar */}
          <div className="px-3 py-1.5 border-b border-white/[0.06] bg-black/30 flex items-center justify-between text-[11px] font-mono gap-2">
            <div className="flex items-center gap-1 overflow-x-auto thin-scrollbar flex-nowrap pb-0.5 min-w-0">
              {(["ALL", "BULLISH", "BEARISH"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setFilter(mode)}
                  className={cn(
                    "px-2 py-0.5 rounded text-[10px] transition-colors whitespace-nowrap shrink-0",
                    filter === mode
                      ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/30"
                      : "text-slate-400 hover:text-slate-200"
                  )}
                >
                  {mode}
                </button>
              ))}
            </div>
            <span className="text-[10px] text-slate-500 shrink-0">
              {filteredCatalysts.length} events
            </span>
          </div>

          {/* Alert List */}
          <div className="flex-1 overflow-y-auto divide-y divide-white/[0.04] p-1 max-h-[340px]">
            {isLoading && catalysts.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500 font-mono flex flex-col items-center gap-2">
                <div className="w-5 h-5 border-2 border-cyan-500/40 border-t-cyan-400 rounded-full animate-spin" />
                <span>Scanning causal radar...</span>
              </div>
            ) : filteredCatalysts.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500 font-mono">
                No catalyst alerts match this filter.
              </div>
            ) : (
              filteredCatalysts.map((cat) => {
                const isUnread = !readIds.has(cat.id);
                const isBullish = cat.move_pct >= 0;
                return (
                  <div
                    key={cat.id}
                    onClick={() => markAsRead(cat.id)}
                    className={cn(
                      "p-2.5 rounded-xl transition-all cursor-pointer group flex flex-col gap-1.5",
                      isUnread
                        ? "bg-white/[0.03] hover:bg-white/[0.06] border-l-2 border-l-cyan-400"
                        : "hover:bg-white/[0.02] opacity-75 hover:opacity-100"
                    )}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <Link
                          href={`/stocks/${cat.symbol}`}
                          onClick={(e) => {
                            e.stopPropagation();
                            markAsRead(cat.id);
                            setIsOpen(false);
                          }}
                          className="font-mono font-bold text-xs text-slate-200 group-hover:text-cyan-300 flex items-center gap-1 hover:underline"
                        >
                          {cat.symbol}
                          <ExternalLink className="w-2.5 h-2.5 opacity-60" />
                        </Link>
                        {cat.sector && (
                          <span className="text-[9px] px-1 py-0.2 rounded bg-white/[0.04] text-slate-400 font-mono">
                            {cat.sector}
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5">
                        <span
                          className={cn(
                            "text-[10px] font-mono font-bold px-1.5 py-0.2 rounded flex items-center gap-0.5",
                            isBullish
                              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
                              : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
                          )}
                        >
                          {isBullish ? (
                            <TrendingUp className="w-2.5 h-2.5" />
                          ) : (
                            <TrendingDown className="w-2.5 h-2.5" />
                          )}
                          {cat.move_pct >= 0 ? "+" : ""}
                          {cat.move_pct.toFixed(1)}%
                        </span>
                        {cat.rvol && (
                          <span className="text-[9px] font-mono text-cyan-400 bg-cyan-950/40 px-1 py-0.2 rounded border border-cyan-800/40">
                            {cat.rvol.toFixed(1)}x
                          </span>
                        )}
                      </div>
                    </div>

                    <p className="text-[11px] text-slate-300 line-clamp-2 leading-relaxed">
                      {cat.causal_headline || (cat.causal_bullets && cat.causal_bullets[0])}
                    </p>

                    <div className="flex items-center justify-between text-[9px] font-mono text-slate-500 pt-0.5">
                      <span className="flex items-center gap-1">
                        <Clock className="w-2.5 h-2.5" />
                        {formatRelativeTime(cat.triggered_at)}
                      </span>
                      <span className="truncate max-w-[180px] text-slate-500">
                        {cat.classification || "Anomaly Spike"}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Footer */}
          <div className="p-2.5 bg-black/40 border-t border-white/[0.06] flex items-center justify-between text-[11px] font-mono">
            <button
              onClick={() => {
                setIsOpen(false);
                onOpenPushSettings();
              }}
              className="text-cyan-400 hover:text-cyan-300 hover:underline flex items-center gap-1 text-[10px]"
            >
              <Settings className="w-3 h-3" />
              {isPushSubscribed ? "Push Radar Connected" : "Enable Push Notifications"}
            </button>
            <span className="text-[9px] text-slate-500">Auto-refreshed 45s</span>
          </div>
        </div>
      )}
    </div>
  );
}
