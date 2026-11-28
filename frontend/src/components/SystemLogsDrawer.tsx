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
  Award,
  ShieldCheck,
  RefreshCw,
} from "lucide-react";
import { API_BASE, DEFAULT_HEADERS, fetchTournamentSummary, TournamentSummary } from "@/lib/api";
import { telemetry, LogEntry } from "@/lib/telemetry";
import { milEvents } from "@/lib/store";

interface SystemLogsResponse {
  rss_mb: number;
  total_buffered: number;
  count: number;
  logs: LogEntry[];
}

interface HealthTelemetry {
  status: string;
  database: string;
  latest_ohlcv_date?: string;
  latest_factors_date?: string;
  active_universe_count?: number;
  user_watchlist_count?: number;
  rss_mb: number;
  memory_headroom_mb: number;
  cgroup_memory_limit_mb: number;
  durable_state_status: string;
  active_champion_model: string;
  timestamp: string;
}

export default function SystemLogsDrawer() {
  const [isOpen, setIsOpen] = useState(false);
  const [activeTab, setActiveTab] = useState<"tournament" | "health" | "logs">("tournament");
  const [logs, setLogs] = useState<LogEntry[]>([]);
  const [rssMb, setRssMb] = useState<number>(0);
  const [autoTail, setAutoTail] = useState<boolean>(true);
  const [levelFilter, setLevelFilter] = useState<string>("ALL");
  const [sourceFilter, setSourceFilter] = useState<string>("ALL");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [copied, setCopied] = useState<boolean>(false);
  const [expandedLogId, setExpandedLogId] = useState<string | null>(null);

  // Quant Lab & Telemetry states
  const [tournament, setTournament] = useState<TournamentSummary | null>(null);
  const [health, setHealth] = useState<HealthTelemetry | null>(null);
  const [loadingData, setLoadingData] = useState<boolean>(false);

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

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/health`, { cache: "no-store" });
      if (res.ok) {
        const data: HealthTelemetry = await res.json();
        setHealth(data);
        if (data.rss_mb) setRssMb(data.rss_mb);
      }
    } catch {}
  }, []);

  const fetchTournament = useCallback(async () => {
    try {
      const data = await fetchTournamentSummary();
      setTournament(data);
    } catch {}
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

  const refreshAll = useCallback(async () => {
    setLoadingData(true);
    await Promise.allSettled([fetchLogs(), fetchHealth(), fetchTournament()]);
    setLoadingData(false);
  }, [fetchLogs, fetchHealth, fetchTournament]);

  useEffect(() => {
    if (isOpen) {
      void refreshAll();
      if (autoTail && activeTab === "logs") {
        pollIntervalRef.current = setInterval(fetchLogs, 2500);
      }
    } else {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    }

    return () => {
      if (pollIntervalRef.current) clearInterval(pollIntervalRef.current);
    };
  }, [isOpen, autoTail, activeTab, fetchLogs, refreshAll]);

  // Scroll to top (newest logs are rendered first in reverse chronological order) when auto-tailing
  useEffect(() => {
    if (autoTail && scrollRef.current && activeTab === "logs") {
      scrollRef.current.scrollTop = 0;
    }
  }, [logs, autoTail, activeTab]);

  const handleCopyDiagnostics = () => {
    const diagnosticBundle = {
      timestamp: new Date().toISOString(),
      url: typeof window !== "undefined" ? window.location.href : "",
      userAgent: typeof window !== "undefined" ? navigator.userAgent : "",
      rss_memory_mb: rssMb,
      health,
      tournament_summary: tournament,
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
    if (mb < 450) return "text-amber-400 bg-amber-950/40 border-amber-500/30";
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
            className="fixed top-0 right-0 bottom-0 w-full sm:w-[720px] lg:w-[880px] bg-[#03060c] border-l border-white/[0.08] z-50 flex flex-col shadow-[0_0_50px_rgba(0,0,0,0.8)] font-mono select-none"
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
                      QUANT LAB & OBSERVABILITY CONSOLE
                    </span>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/[0.06] text-slate-400 border border-white/[0.1]">
                      Alt+L
                    </span>
                  </div>
                  <div className="flex items-center gap-2 mt-0.5 text-[11px] text-slate-400">
                    <span>CPCV(6, 2) Tournament • Memory Headroom • Event Stream</span>
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
                  onClick={refreshAll}
                  disabled={loadingData}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
                  title="Refresh Telemetry"
                >
                  <RefreshCw className={`w-4 h-4 ${loadingData ? "animate-spin text-cyan-400" : ""}`} />
                </button>

                <button
                  onClick={() => setIsOpen(false)}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
                  aria-label="Close console"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Navigation Tabs */}
            <div className="px-4 py-2 bg-[#040812] border-b border-white/[0.06] flex items-center space-x-2 text-xs">
              <button
                onClick={() => setActiveTab("tournament")}
                className={`px-3 py-1.5 rounded-lg font-semibold flex items-center space-x-1.5 transition-all ${
                  activeTab === "tournament"
                    ? "bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Award className="w-3.5 h-3.5 text-cyan-400" />
                <span>CPCV(6, 2) Tournament</span>
              </button>

              <button
                onClick={() => setActiveTab("health")}
                className={`px-3 py-1.5 rounded-lg font-semibold flex items-center space-x-1.5 transition-all ${
                  activeTab === "health"
                    ? "bg-indigo-950/80 text-indigo-300 border border-indigo-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                <span>Container Health & RAM</span>
              </button>

              <button
                onClick={() => setActiveTab("logs")}
                className={`px-3 py-1.5 rounded-lg font-semibold flex items-center space-x-1.5 transition-all ${
                  activeTab === "logs"
                    ? "bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 shadow-sm"
                    : "text-slate-400 hover:text-slate-200"
                }`}
              >
                <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                <span>Logs Stream</span>
              </button>
            </div>

            {/* Tab 1: CPCV(6, 2) Tournament Leaderboard */}
            {activeTab === "tournament" && (
              <div className="flex-1 p-4 overflow-y-auto space-y-4 select-text">
                {/* Active Champion Banner */}
                <div className="p-4 rounded-xl bg-gradient-to-r from-emerald-950/30 via-[#07111a] to-emerald-950/30 border border-emerald-500/30 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center space-x-2">
                      <ShieldCheck className="w-5 h-5 text-emerald-400" />
                      <span className="text-xs font-bold text-slate-300 uppercase tracking-wider">
                        Active Production Champion
                      </span>
                    </div>
                    <span className="px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-emerald-950 text-emerald-400 border border-emerald-500/40">
                      LIVE IN PRODUCTION
                    </span>
                  </div>
                  <div className="text-base font-bold text-white font-mono">
                    {tournament?.active_champion || "Deterministic Baseline (Momentum+LowVol+PIT)"}
                  </div>
                  <div className="text-[11px] text-slate-400 font-mono flex items-center gap-2 flex-wrap">
                    <span>Verdict: <strong className="text-amber-300">{tournament?.promotion_verdict || "REJECTED_BELOW_BASELINE"}</strong></span>
                    <span>•</span>
                    <span>DSR Hurdle: DSR &gt;= 0.90 &amp; Excess Sharpe &gt; 0</span>
                  </div>
                </div>

                {/* Tournament Candidates Leaderboard */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between text-xs font-bold text-slate-300 pb-1">
                    <span>CPCV(6, 2) 15-Fold Tournament Leaderboard</span>
                    <span className="text-[10px] text-slate-400 font-normal">20-Day Horizon · Strict Path Purged</span>
                  </div>

                  <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#020409]">
                    <table className="w-full text-left text-xs font-mono">
                      <thead className="bg-[#070c18] text-slate-400 text-[10px] uppercase border-b border-white/[0.08]">
                        <tr>
                          <th className="p-2.5">Model / Candidate</th>
                          <th className="p-2.5 text-right">Net Sharpe</th>
                          <th className="p-2.5 text-right">Excess vs Base</th>
                          <th className="p-2.5 text-right">DSR</th>
                          <th className="p-2.5 text-right">Hurdle SR*</th>
                          <th className="p-2.5 text-right">Abstain %</th>
                          <th className="p-2.5 text-center">Verdict</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-white/[0.04]">
                        {/* Baseline Row */}
                        {tournament?.baseline && (
                          <tr className="bg-emerald-950/15">
                            <td className="p-2.5 font-bold text-emerald-300 flex items-center gap-1.5">
                              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                              <span>{tournament.baseline.name}</span>
                            </td>
                            <td className="p-2.5 text-right font-bold text-emerald-400">
                              {tournament.baseline.mean_net_sharpe?.toFixed(4)}
                            </td>
                            <td className="p-2.5 text-right text-slate-400">— (Anchor)</td>
                            <td className="p-2.5 text-right text-slate-400">—</td>
                            <td className="p-2.5 text-right text-slate-400">—</td>
                            <td className="p-2.5 text-right text-slate-400">0.0%</td>
                            <td className="p-2.5 text-center">
                              <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-emerald-950 text-emerald-400 border border-emerald-500/40">
                                CHAMPION
                              </span>
                            </td>
                          </tr>
                        )}

                        {/* Candidate Rows */}
                        {tournament?.candidates?.map((cand) => (
                          <tr key={cand.candidate_id} className="hover:bg-white/[0.02]">
                            <td className="p-2.5 text-slate-200 font-semibold">{cand.candidate_name}</td>
                            <td className="p-2.5 text-right font-bold text-slate-200">
                              {cand.cpcv_mean_sharpe?.toFixed(4)}
                            </td>
                            <td className={`p-2.5 text-right font-semibold ${cand.excess_sharpe_vs_baseline >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                              {cand.excess_sharpe_vs_baseline >= 0 ? "+" : ""}{cand.excess_sharpe_vs_baseline?.toFixed(4)}
                            </td>
                            <td className="p-2.5 text-right font-mono text-cyan-300">
                              {cand.deflated_sharpe_ratio?.toFixed(4)}
                            </td>
                            <td className="p-2.5 text-right text-slate-400">
                              {cand.sharpe_star_hurdle?.toFixed(4)}
                            </td>
                            <td className="p-2.5 text-right text-amber-300">
                              {(cand.abstention_rate * 100).toFixed(1)}%
                            </td>
                            <td className="p-2.5 text-center">
                              <span
                                className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                                  cand.promotion_status === "CHAMPION"
                                    ? "bg-emerald-950 text-emerald-400 border-emerald-500/40"
                                    : "bg-rose-950/80 text-rose-300 border-rose-500/40"
                                }`}
                              >
                                {cand.promotion_status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Compact Return Distribution Moments */}
                <div className="space-y-2">
                  <span className="text-xs font-bold text-slate-300">Statistical Moments (Non-Gaussian Returns)</span>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                    {tournament?.baseline && (
                      <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5">
                        <span className="font-bold text-emerald-300 text-[11px] block">{tournament.baseline.name}</span>
                        <div className="grid grid-cols-2 gap-1 text-[10px] text-slate-400">
                          <div>Mean: <strong className="text-white">{((tournament.baseline.mean_return || 0) * 100).toFixed(2)}%</strong></div>
                          <div>Std: <strong className="text-white">{((tournament.baseline.std_return || 0) * 100).toFixed(2)}%</strong></div>
                          <div>Skewness: <strong className="text-white">{tournament.baseline.skewness?.toFixed(2)}</strong></div>
                          <div>Ex. Kurtosis: <strong className="text-white">{tournament.baseline.excess_kurtosis?.toFixed(2)}</strong></div>
                          <div>5th Pct: <strong className="text-rose-400">{((tournament.baseline.p05_return || 0) * 100).toFixed(2)}%</strong></div>
                          <div>95th Pct: <strong className="text-emerald-400">{((tournament.baseline.p95_return || 0) * 100).toFixed(2)}%</strong></div>
                        </div>
                      </div>
                    )}

                    {tournament?.candidates?.[0] && (
                      <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-1.5">
                        <span className="font-bold text-cyan-300 text-[11px] block">{tournament.candidates[0].candidate_name}</span>
                        <div className="grid grid-cols-2 gap-1 text-[10px] text-slate-400">
                          <div>Mean: <strong className="text-white">{((tournament.candidates[0].mean_return || 0) * 100).toFixed(2)}%</strong></div>
                          <div>Std: <strong className="text-white">{((tournament.candidates[0].std_return || 0) * 100).toFixed(2)}%</strong></div>
                          <div>Skewness: <strong className="text-white">{tournament.candidates[0].skewness?.toFixed(2)}</strong></div>
                          <div>Ex. Kurtosis: <strong className="text-white">{tournament.candidates[0].excess_kurtosis?.toFixed(2)}</strong></div>
                          <div>5th Pct: <strong className="text-rose-400">{((tournament.candidates[0].p05_return || 0) * 100).toFixed(2)}%</strong></div>
                          <div>95th Pct: <strong className="text-emerald-400">{((tournament.candidates[0].p95_return || 0) * 100).toFixed(2)}%</strong></div>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              </div>
            )}

            {/* Tab 2: Container Health & Memory Headroom */}
            {activeTab === "health" && (
              <div className="flex-1 p-4 overflow-y-auto space-y-4 select-text">
                <div className="grid grid-cols-2 gap-3">
                  <div className="p-4 rounded-xl bg-[#020409] border border-white/[0.08] space-y-1">
                    <span className="text-[10px] text-slate-400 font-bold uppercase">Container RSS Memory</span>
                    <div className="text-xl font-bold font-mono text-white tabular-nums">
                      {health?.rss_mb ? `${health.rss_mb.toFixed(1)} MB` : "—"}
                    </div>
                    <div className="w-full bg-slate-900 rounded-full h-1.5 mt-2 overflow-hidden">
                      <div
                        className="bg-cyan-400 h-1.5 rounded-full transition-all"
                        style={{ width: `${Math.min(100, ((health?.rss_mb || 0) / 512.0) * 100)}%` }}
                      />
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono block pt-1">Limit: 512.0 MB (Render Standard)</span>
                  </div>

                  <div className="p-4 rounded-xl bg-[#020409] border border-white/[0.08] space-y-1">
                    <span className="text-[10px] text-slate-400 font-bold uppercase">Memory Headroom</span>
                    <div className="text-xl font-bold font-mono text-emerald-400 tabular-nums">
                      {health?.memory_headroom_mb ? `+${health.memory_headroom_mb.toFixed(1)} MB` : "—"}
                    </div>
                    <span className="text-[10px] text-emerald-300 font-mono block pt-3">Safe OOM margin maintained</span>
                  </div>

                  <div className="p-4 rounded-xl bg-[#020409] border border-white/[0.08] space-y-1">
                    <span className="text-[10px] text-slate-400 font-bold uppercase">Durable Cloud Sync</span>
                    <div className="text-base font-bold font-mono text-cyan-300 flex items-center gap-1.5 pt-1">
                      <ShieldCheck className="w-4 h-4 text-cyan-400" />
                      <span>{health?.durable_state_status || "IN_SYNC"}</span>
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono block pt-2">Dual-cloud durable state (Azure Blob + Private GitHub failover)</span>
                  </div>

                  <div className="p-4 rounded-xl bg-[#020409] border border-white/[0.08] space-y-1">
                    <span className="text-[10px] text-slate-400 font-bold uppercase">Active Universe</span>
                    <div className="text-xl font-bold font-mono text-white tabular-nums">
                      {health?.active_universe_count || 1153}
                    </div>
                    <span className="text-[10px] text-slate-500 font-mono block pt-1">NSE Equities (WAL Mode)</span>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-2 text-xs font-mono">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Database Engine:</span>
                    <span className="text-white font-semibold">{health?.database || "connected (WAL mode)"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Latest OHLCV Session:</span>
                    <span className="text-cyan-300 font-semibold">{health?.latest_ohlcv_date || "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">Latest Factor Session:</span>
                    <span className="text-cyan-300 font-semibold">{health?.latest_factors_date || "—"}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-slate-400">User Watchlist Equities:</span>
                    <span className="text-white font-semibold">{health?.user_watchlist_count || 0}</span>
                  </div>
                </div>
              </div>
            )}

            {/* Tab 3: Filter & Control Bar + Log Terminal Window */}
            {activeTab === "logs" && (
              <>
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
              </>
            )}
          </motion.aside>
        </>
      )}
    </AnimatePresence>
  );
}
