"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Terminal,
  X,
  Play,
  Pause,
  Copy,
  Check,
  Trash2,
  Search,
  Cpu,
} from "lucide-react";
import { API_BASE, DEFAULT_HEADERS } from "@/lib/api";
import { telemetry, LogEntry } from "@/lib/telemetry";
import { milEvents } from "@/lib/store";

interface SystemLogsResponse {
  rss_mb: number;
  total_buffered: number;
  count: number;
  logs: LogEntry[];
}

export default function SystemLogsDrawer() {
  const [isOpen, setIsOpen] = useState(false);
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [rssMb, setRssMb] = useState<number>(0);
  const [autoTail, setAutoTail] = useState<boolean>(true);
  const [levelFilter, setLevelFilter] = useState<string>("ALL");
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [copied, setCopied] = useState<boolean>(false);
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Toggle on Alt+L keybinding
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.altKey && (e.key === "l" || e.key === "L")) {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      } else if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen]);

  // Listen to mil:open-system-logs event
  useEffect(() => {
    const unsub = milEvents.on("mil:open-system-logs", () => {
      setIsOpen(true);
    });
    return () => unsub();
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/system/logs?limit=250&level=DEBUG`, {
        headers: DEFAULT_HEADERS,
        cache: "no-store",
      });
      if (!res.ok) return;
      const data: SystemLogsResponse = await res.json();
      setRssMb(data.rss_mb || 0);

      // Merge server logs and client logs
      const clientLogs = telemetry.getBuffer();
      const combined = [...clientLogs, ...(data.logs || [])];
      // Sort descending by timestamp
      combined.sort((a, b) => new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime());

      setLogs(combined);
    } catch {
      // Offline or network error
    }
  }, []);

  useEffect(() => {
    if (isOpen) {
      void fetchLogs();
      if (autoTail) {
        pollIntervalRef.current = setInterval(fetchLogs, 2500);
      }
    } else {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [isOpen, autoTail, fetchLogs]);

  // Scroll to bottom when auto-tailing on new logs
  useEffect(() => {
    if (autoTail && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs, autoTail]);

  const handleCopyDiagnostics = () => {
    const diagnosticBundle = {
      timestamp: new Date().toISOString(),
      url: typeof window !== "undefined" ? window.location.href : "",
      userAgent: typeof window !== "undefined" ? navigator.userAgent : "",
      rss_memory_mb: rssMb,
      total_logs_analyzed: logs.length,
      recent_errors: logs.filter((l) => l.level === "ERROR").slice(0, 5),
      recent_warnings: logs.filter((l) => l.level === "WARNING").slice(0, 5),
    };

    const text = "```json\n" + JSON.stringify(diagnosticBundle, null, 2) + "\n```";
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  const handleClear = () => {
    telemetry.clear();
    setLogs([]);
  };

  const filteredLogs = logs.filter((entry) => {
    if (levelFilter !== "ALL" && entry.level !== levelFilter) return false;
    if (sourceFilter !== "ALL" && entry.source.toUpperCase() !== sourceFilter) return false;
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      const matchMsg = entry.message.toLowerCase().includes(q);
      const matchLogger = entry.logger.toLowerCase().includes(q);
      const matchReq = entry.request_id?.toLowerCase().includes(q);
      if (!matchMsg && !matchLogger && !matchReq) return false;
    }
    return true;
  });

  const getRssColor = (mb: number) => {
    if (mb < 350) return "text-emerald-400 bg-emerald-950/40 border-emerald-500/30";
    if (mb < 480) return "text-amber-400 bg-amber-950/40 border-amber-500/30";
    return "text-rose-400 bg-rose-950/40 border-rose-500/30";
  };

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setIsOpen(false)}
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 transition-opacity"
          />

          {/* Drawer Console */}
          <motion.aside
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 350, damping: 35 }}
            className="fixed top-0 right-0 bottom-0 w-full sm:w-[680px] lg:w-[820px] bg-[#03060c] border-l border-white/[0.08] z-50 flex flex-col shadow-[0_0_50px_rgba(0,0,0,0.8)] font-mono select-none"
          >
            {/* Header */}
            <div className="p-4 border-b border-white/[0.06] bg-[#060a14] flex items-center justify-between shrink-0">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-cyan-950/60 border border-cyan-500/30 text-cyan-400">
                  <Terminal className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-bold text-white tracking-wide">
                      SYSTEM OBSERVABILITY CONSOLE
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400 border border-white/[0.1]">
                      Alt+L
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-400">
                    <span>Live Telemetry & Diagnostics</span>
                    <span>•</span>
                    <span className="text-slate-500">{filteredLogs.length} events</span>
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-2">
                {/* Process RSS Badge */}
                <div
                  className={`px-2.5 py-1 rounded-lg border text-xs font-semibold flex items-center gap-1.5 tabular-nums ${getRssColor(
                    rssMb
                  )}`}
                  title="Process Resident Set Size (RSS) memory consumption in container"
                >
                  <Cpu className="w-3.5 h-3.5" />
                  <span>RSS: {rssMb > 0 ? `${rssMb.toFixed(1)} MB` : "—"} / 512 MB</span>
                </div>

                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
                  aria-label="Close observability console"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Filter & Control Bar */}
            <div className="p-3 border-b border-white/[0.06] bg-[#040812] flex flex-wrap items-center justify-between gap-2.5 text-xs shrink-0">
              <div className="flex items-center gap-2 flex-wrap">
                {/* Level Filter */}
                <div className="flex items-center rounded-lg bg-[#080d1a] border border-white/[0.08] p-0.5">
                  {(["ALL", "INFO", "WARNING", "ERROR"] as const).map((lvl) => (
                    <button
                      key={lvl}
                      onClick={() => setLevelFilter(lvl)}
                      className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                        levelFilter === lvl
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {lvl === "WARNING" ? "WARN" : lvl}
                    </button>
                  ))}
                </div>

                {/* Source Filter */}
                <div className="flex items-center rounded-lg bg-[#080d1a] border border-white/[0.08] p-0.5">
                  {(["ALL", "SERVER", "CLIENT"] as const).map((src) => (
                    <button
                      key={src}
                      onClick={() => setSourceFilter(src)}
                      className={`px-2 py-1 rounded text-[10px] font-semibold transition-all ${
                        sourceFilter === src
                          ? "bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 shadow-sm"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      {src}
                    </button>
                  ))}
                </div>

                {/* Search */}
                <div className="relative">
                  <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    placeholder="Search logs / req ID..."
                    className="w-36 sm:w-44 pl-8 pr-2.5 py-1 rounded-lg bg-[#080d1a] border border-white/[0.08] text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500/50"
                  />
                </div>
              </div>

              {/* Actions */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setAutoTail(!autoTail)}
                  title={autoTail ? "Pause auto-tail stream" : "Resume auto-tail stream"}
                  className={`px-2.5 py-1 rounded-lg border text-[11px] font-semibold flex items-center gap-1.5 transition-all ${
                    autoTail
                      ? "bg-emerald-950/40 text-emerald-300 border-emerald-500/30"
                      : "bg-slate-900 text-slate-400 border-white/[0.08]"
                  }`}
                >
                  {autoTail ? <Pause className="w-3 h-3" /> : <Play className="w-3 h-3" />}
                  <span>{autoTail ? "Tail On" : "Paused"}</span>
                </button>

                <button
                  onClick={handleCopyDiagnostics}
                  title="Copy complete diagnostic JSON bundle to clipboard"
                  className="px-2.5 py-1 rounded-lg bg-[#080d1a] hover:bg-slate-800 text-slate-300 border border-white/[0.08] text-[11px] font-semibold flex items-center gap-1.5 transition-all"
                >
                  {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3 text-cyan-400" />}
                  <span>{copied ? "Copied" : "Bundle"}</span>
                </button>

                <button
                  onClick={handleClear}
                  title="Clear in-memory buffer"
                  className="p-1 rounded-lg hover:bg-rose-950/40 hover:text-rose-400 text-slate-500 border border-transparent hover:border-rose-500/30 transition-all"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>

            {/* Log Terminal Window */}
            <div
              ref={scrollRef}
              className="flex-1 p-3 overflow-y-auto space-y-1.5 text-[11px] bg-[#020409] font-mono leading-relaxed select-text"
            >
              {filteredLogs.length === 0 ? (
                <div className="h-full flex flex-col items-center justify-center text-slate-500 gap-2">
                  <Terminal className="w-8 h-8 opacity-40" />
                  <span>No telemetry logs match the current filters.</span>
                </div>
              ) : (
                filteredLogs.map((entry) => {
                  const isExpanded = expandedLogId === entry.id;
                  const timeFormatted = new Date(entry.timestamp).toLocaleTimeString("en-IN", {
                    hour12: false,
                    hour: "2-digit",
                    minute: "2-digit",
                    second: "2-digit",
                  });

                  const lvlColor =
                    entry.level === "ERROR"
                      ? "text-rose-400 bg-rose-950/30 border-rose-500/30"
                      : entry.level === "WARNING"
                      ? "text-amber-400 bg-amber-950/30 border-amber-500/30"
                      : "text-cyan-400 bg-cyan-950/30 border-cyan-500/30";

                  return (
                    <div
                      key={entry.id}
                      onClick={() => setExpandedLogId(isExpanded ? null : entry.id)}
                      className={`p-2 rounded-lg border transition-all cursor-pointer ${
                        entry.level === "ERROR"
                          ? "bg-rose-950/10 border-rose-500/20 hover:border-rose-500/40"
                          : entry.level === "WARNING"
                          ? "bg-amber-950/10 border-amber-500/20 hover:border-amber-500/40"
                          : "bg-white/[0.01] border-white/[0.04] hover:border-white/[0.1] hover:bg-white/[0.03]"
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-slate-500 tabular-nums text-[10px]">{timeFormatted}</span>
                          <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold border ${lvlColor}`}>
                            {entry.level}
                          </span>
                          <span className="text-slate-400 text-[10px]">[{entry.source}]</span>
                          <span className="text-slate-400 font-semibold">{entry.logger}</span>
                          {entry.request_id && (
                            <span className="text-[10px] px-1.5 py-0.2 rounded bg-purple-950/40 text-purple-300 border border-purple-500/30">
                              {entry.request_id}
                            </span>
                          )}
                        </div>
                      </div>

                      <div className="mt-1 text-slate-200 break-words font-mono">{entry.message}</div>

                      {/* Expanded Details / Stack / Meta */}
                      {isExpanded && entry.meta && Object.keys(entry.meta).length > 0 && (
                        <div className="mt-2 p-2 rounded bg-black/60 border border-white/[0.06] text-[10px] text-slate-400 overflow-x-auto">
                          <pre>{JSON.stringify(entry.meta, null, 2)}</pre>
                        </div>
                      )}
                    </div>
                  );
                })
              )}
            </div>
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
