"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Radio,
  FileText,
  Newspaper,
  Zap,
  RefreshCw,
  ExternalLink,
  ShieldCheck,
  Clock,
  Loader2,
  ChevronRight,
  Sparkles,
} from "lucide-react";
import {
  CausalCatalyst,
  fetchLiveCatalysts,
  fetchSymbolCatalyst,
  apiFetch,
} from "@/lib/api";
import NewsImpactCard, { NewsArticle } from "./NewsImpactCard";
import { cn } from "@/lib/utils";

export interface Disclosure {
  disclosure_id: string;
  broadcast_timestamp: string;
  effective_session_date: string;
  category: string;
  subject: string;
  details_summary: string | null;
  source_url: string | null;
  verification_status: string;
  audit_status: string | null;
  dividend_declared: number | null;
  operating_margin_pct: number | null;
}

interface UnifiedIntelligenceHubProps {
  symbol?: string | null;
  initialDisclosures?: Disclosure[];
  initialNews?: NewsArticle[];
  compact?: boolean;
  className?: string;
}

type TabType = "all" | "catalysts" | "disclosures" | "news";

function formatISTTime(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return (
      d.toLocaleString("en-IN", {
        month: "short",
        day: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Kolkata",
      }) + " IST"
    );
  } catch {
    return isoString;
  }
}

function timeAgo(date: Date): string {
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
  if (seconds < 20) return "just now";
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export default function UnifiedIntelligenceHub({
  symbol,
  initialDisclosures = [],
  initialNews = [],
  compact = false,
  className,
}: UnifiedIntelligenceHubProps) {
  const [activeTab, setActiveTab] = useState<TabType>("all");
  const [catalysts, setCatalysts] = useState<CausalCatalyst[]>([]);
  const [symbolCatalyst, setSymbolCatalyst] = useState<CausalCatalyst | null>(null);
  const [disclosures, setDisclosures] = useState<Disclosure[]>(initialDisclosures);
  const [news, setNews] = useState<NewsArticle[]>(initialNews);
  const [loading, setLoading] = useState<boolean>(false);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  const [scanning, setScanning] = useState<boolean>(false);
  const [cooldownRemaining, setCooldownRemaining] = useState<number>(0);
  const [lastUpdated, setLastUpdated] = useState<Date>(new Date());
  const [timeAgoText, setTimeAgoText] = useState<string>("just now");

  // Keep disclosures & news in sync with initial props if provided
  useEffect(() => {
    if (initialDisclosures && initialDisclosures.length > 0) {
      setDisclosures(initialDisclosures);
    }
  }, [initialDisclosures]);

  useEffect(() => {
    if (initialNews && initialNews.length > 0) {
      setNews(initialNews);
    }
  }, [initialNews]);

  // Relative time counter tick
  useEffect(() => {
    const timer = setInterval(() => {
      setTimeAgoText(timeAgo(lastUpdated));
    }, 10000);
    return () => clearInterval(timer);
  }, [lastUpdated]);

  // Cooldown countdown
  useEffect(() => {
    if (cooldownRemaining <= 0) return;
    const interval = setInterval(() => {
      setCooldownRemaining((prev) => Math.max(0, prev - 1));
    }, 1000);
    return () => clearInterval(interval);
  }, [cooldownRemaining]);

  // Fetch intelligence data
  const loadIntelligence = useCallback(
    async (isBackground = false) => {
      if (!isBackground) {
        setIsRefreshing(true);
      }
      try {
        const promises: Promise<unknown>[] = [fetchLiveCatalysts(12)];

        if (symbol) {
          promises.push(
            fetchSymbolCatalyst(symbol, { fallback: true }).catch(() => ({
              catalysts: [],
              latest: null,
            }))
          );
          // If no initial disclosures or background refresh, query tearsheet
          promises.push(
            apiFetch<{ recent_disclosures?: Disclosure[] }>(
              `/stocks/${symbol}/tearsheet`
            ).catch(() => ({ recent_disclosures: [] }))
          );
          // Query news
          promises.push(
            apiFetch<{ articles?: NewsArticle[] }>(`/stocks/${symbol}/news`).catch(
              () => ({ articles: [] })
            )
          );
        }

        const results = await Promise.allSettled(promises);

        // 1. Live Catalysts
        if (results[0].status === "fulfilled" && Array.isArray(results[0].value)) {
          setCatalysts(results[0].value);
        }

        // 2. Symbol Catalyst
        if (symbol && results[1]?.status === "fulfilled") {
          const symCatRes = results[1].value as { latest?: CausalCatalyst | null };
          if (symCatRes?.latest) {
            setSymbolCatalyst(symCatRes.latest);
          } else {
            // Find in general list
            const found = (results[0].status === "fulfilled" && Array.isArray(results[0].value))
              ? (results[0].value as CausalCatalyst[]).find(
                  (c: CausalCatalyst) => c.symbol.toUpperCase() === symbol.toUpperCase()
                )
              : null;
            setSymbolCatalyst(found || null);
          }
        }

        // 3. Disclosures
        if (symbol && results[2]?.status === "fulfilled") {
          const tearsheetRes = results[2].value as { recent_disclosures?: Disclosure[] };
          if (Array.isArray(tearsheetRes?.recent_disclosures) && tearsheetRes.recent_disclosures.length > 0) {
            setDisclosures(tearsheetRes.recent_disclosures);
          }
        }

        // 4. News
        if (symbol && results[3]?.status === "fulfilled") {
          const newsRes = results[3].value as { articles?: NewsArticle[] };
          if (Array.isArray(newsRes?.articles) && newsRes.articles.length > 0) {
            setNews(newsRes.articles);
          }
        }

        setLastUpdated(new Date());
        setTimeAgoText("just now");
      } catch (err) {
        console.warn("UnifiedIntelligenceHub load error:", err);
      } finally {
        setIsRefreshing(false);
        setLoading(false);
      }
    },
    [symbol]
  );

  // Initial fetch
  useEffect(() => {
    loadIntelligence(false);
  }, [loadIntelligence]);

  // Auto-refresh every 60s & event subscriptions
  useEffect(() => {
    const interval = setInterval(() => {
      loadIntelligence(true);
    }, 60000);

    const handleExternalRefresh = () => {
      loadIntelligence(false);
    };

    window.addEventListener("mil:screener-refresh", handleExternalRefresh);
    window.addEventListener("mil:tearsheet-refresh", handleExternalRefresh);
    window.addEventListener("mil:ingest-progress", handleExternalRefresh);

    return () => {
      clearInterval(interval);
      window.removeEventListener("mil:screener-refresh", handleExternalRefresh);
      window.removeEventListener("mil:tearsheet-refresh", handleExternalRefresh);
      window.removeEventListener("mil:ingest-progress", handleExternalRefresh);
    };
  }, [loadIntelligence]);

  // Scan anomalies action
  const handleScanAnomalies = async () => {
    if (scanning || cooldownRemaining > 0) return;
    setScanning(true);
    try {
      await apiFetch("/catalysts/scan", { method: "POST" });
      setCooldownRemaining(60);
      await loadIntelligence(false);
    } catch (err) {
      console.error("Catalyst scan error:", err);
    } finally {
      setScanning(false);
    }
  };

  const tabs: { id: TabType; label: string; count?: number; icon: React.ReactNode }[] = [
    { id: "all", label: "All Intelligence", icon: <Sparkles className="w-3.5 h-3.5" /> },
    {
      id: "catalysts",
      label: "Catalysts",
      count: symbolCatalyst ? 1 : catalysts.length,
      icon: <Radio className="w-3.5 h-3.5" />,
    },
    {
      id: "disclosures",
      label: "Disclosures",
      count: disclosures.length,
      icon: <FileText className="w-3.5 h-3.5" />,
    },
    {
      id: "news",
      label: "News Wire",
      count: news.length,
      icon: <Newspaper className="w-3.5 h-3.5" />,
    },
  ];

  const primaryCatalyst = symbolCatalyst || (catalysts.length > 0 ? catalysts[0] : null);

  return (
    <div
      className={cn(
        "rounded-2xl border border-white/[0.08] bg-[#070b13] font-mono relative overflow-hidden shadow-2xl flex flex-col space-y-4",
        compact ? "p-3.5" : "p-5",
        className
      )}
    >
      {/* Top subtle specular edge */}
      <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/40 to-transparent pointer-events-none" />

      {/* 1. Header Toolbar */}
      <div className="flex flex-wrap items-center justify-between gap-3 pb-3 border-b border-white/[0.07]">
        <div className="flex items-center space-x-2.5 min-w-0">
          <span className="relative flex h-2.5 w-2.5 shrink-0">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-cyan-500" />
          </span>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-sm font-bold text-white tracking-wide flex items-center gap-1.5">
                <span>Unified Live Intelligence</span>
              </h3>
              <span className="text-[10px] px-2 py-0.5 rounded-full bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 font-bold uppercase tracking-wider">
                LIVE WIRE
              </span>
              {symbol && (
                <span className="text-[10px] px-2 py-0.5 rounded-full bg-white/[0.04] border border-white/[0.08] text-slate-300 font-bold">
                  {symbol}
                </span>
              )}
            </div>
            <p className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-1.5">
              <Clock className="w-3 h-3 text-slate-500 shrink-0" />
              <span>Updated {timeAgoText}</span>
              <span className="text-slate-600">•</span>
              <span className="text-slate-500">60s Auto-Sync</span>
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center space-x-2 shrink-0">
          <button
            onClick={() => loadIntelligence(false)}
            disabled={isRefreshing}
            className="p-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] hover:border-cyan-500/30 text-slate-300 hover:text-cyan-300 transition-all shadow-sm disabled:opacity-50"
            title="Refresh Live Wire"
          >
            <RefreshCw
              className={cn("w-3.5 h-3.5", isRefreshing && "animate-spin text-cyan-400")}
            />
          </button>

          <button
            onClick={handleScanAnomalies}
            disabled={scanning || cooldownRemaining > 0}
            className="flex items-center space-x-1.5 px-3 py-1.5 rounded-xl bg-cyan-950/40 hover:bg-cyan-900/60 border border-cyan-500/30 hover:border-cyan-400/60 text-cyan-300 font-semibold text-[11px] transition-all shadow-sm disabled:opacity-50 disabled:cursor-not-allowed"
            title={
              cooldownRemaining > 0
                ? `Scan cooldown active (${cooldownRemaining}s)`
                : "Trigger intraday anomaly scan across universe"
            }
          >
            {scanning ? (
              <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
            ) : (
              <Zap className="w-3.5 h-3.5 text-cyan-400" />
            )}
            <span className="hidden sm:inline">
              {scanning
                ? "Scanning..."
                : cooldownRemaining > 0
                ? `Cooldown (${cooldownRemaining}s)`
                : "Scan Anomalies"}
            </span>
            <span className="sm:hidden">
              {scanning ? "Scan..." : cooldownRemaining > 0 ? `${cooldownRemaining}s` : "Scan"}
            </span>
          </button>
        </div>
      </div>

      {/* 2. Sub-Filter Tabs */}
      <div className="flex space-x-1 p-1 bg-[#050810] rounded-xl border border-white/[0.06] overflow-x-auto thin-scrollbar">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={cn(
                "relative flex items-center space-x-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-medium transition-colors shrink-0",
                isActive
                  ? "text-cyan-300 font-bold"
                  : "text-slate-400 hover:text-slate-200 hover:bg-white/[0.03]"
              )}
            >
              {isActive && (
                <motion.div
                  layoutId="intelligence-hub-tab-indicator"
                  className="absolute inset-0 bg-cyan-950/70 border border-cyan-500/40 rounded-lg shadow-[0_0_12px_rgba(6,182,212,0.2)]"
                  transition={{ type: "spring", stiffness: 450, damping: 35 }}
                />
              )}
              <span className="relative z-10 flex items-center space-x-1.5">
                {tab.icon}
                <span>{tab.label}</span>
                {typeof tab.count === "number" && tab.count > 0 && (
                  <span
                    className={cn(
                      "text-[10px] px-1.5 py-0.2 rounded-full font-bold tabular-nums",
                      isActive
                        ? "bg-cyan-500/30 text-cyan-200 border border-cyan-400/40"
                        : "bg-white/[0.06] text-slate-400 border border-white/[0.08]"
                    )}
                  >
                    {tab.count}
                  </span>
                )}
              </span>
            </button>
          );
        })}
      </div>

      {/* 3. Tab Content */}
      <div className="space-y-4">
        {/* --- TAB: ALL --- */}
        {activeTab === "all" && (
          <div className="space-y-4">
            {/* Primary Catalyst Card if available */}
            {primaryCatalyst && (
              <div className="p-4 rounded-xl bg-[#090f1e]/90 border border-cyan-500/30 shadow-[0_0_20px_rgba(6,182,212,0.12)] space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <Link
                      href={`/stocks/${primaryCatalyst.symbol}`}
                      className="text-sm font-black text-white hover:text-cyan-300 transition-colors tracking-tight flex items-center gap-1"
                    >
                      <span>{primaryCatalyst.symbol}</span>
                      <span className="text-xs font-normal text-slate-400">
                        ({primaryCatalyst.company_name})
                      </span>
                    </Link>
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-[11px] font-bold tabular-nums border",
                        primaryCatalyst.move_pct >= 0
                          ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
                          : "bg-rose-950/80 text-rose-300 border-rose-500/40"
                      )}
                    >
                      {primaryCatalyst.move_pct >= 0 ? "+" : ""}
                      {primaryCatalyst.move_pct.toFixed(1)}%
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-white/[0.04] text-slate-300 border border-white/[0.08] tabular-nums">
                      {primaryCatalyst.rvol.toFixed(1)}x RVOL
                    </span>
                  </div>

                  <span
                    className={cn(
                      "px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border",
                      primaryCatalyst.classification.includes("Idiosyncratic")
                        ? "bg-cyan-950/90 text-cyan-300 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                        : "bg-purple-950/90 text-purple-300 border-purple-500/50 shadow-[0_0_10px_rgba(168,85,247,0.2)]"
                    )}
                  >
                    {primaryCatalyst.classification}
                  </span>
                </div>

                <p className="text-xs text-slate-100 font-bold leading-relaxed bg-black/40 p-2.5 rounded-lg border border-white/[0.05]">
                  {primaryCatalyst.causal_headline}
                </p>

                {/* 4-Pillar Radar Indicators */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1">
                  <div className="p-2 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                    <div className="text-[10px] text-slate-400">PRICE &amp; VOL</div>
                    <div className="text-xs font-bold text-white mt-0.5 tabular-nums">
                      {primaryCatalyst.move_pct >= 0 ? "+" : ""}
                      {primaryCatalyst.move_pct.toFixed(1)}% / {primaryCatalyst.rvol.toFixed(1)}x
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                    <div className="text-[10px] text-slate-400">SECTOR CONTEXT</div>
                    <div className="text-xs font-bold text-white mt-0.5 truncate">
                      {primaryCatalyst.pillar2?.sector || primaryCatalyst.sector || "Broad Index"}
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                    <div className="text-[10px] text-slate-400">FILING / EVENT</div>
                    <div className="text-xs font-bold text-slate-200 mt-0.5 truncate">
                      {primaryCatalyst.pillar3?.summary || primaryCatalyst.causal_bullets?.[2] || "Exchange Disclosures"}
                    </div>
                  </div>
                  <div className="p-2 rounded-lg bg-white/[0.02] border border-white/[0.05]">
                    <div className="text-[10px] text-slate-400">DETECTED AT</div>
                    <div className="text-xs font-bold text-slate-300 mt-0.5 tabular-nums truncate">
                      {formatISTTime(primaryCatalyst.triggered_at)}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Live Movers Strip (if universe view or other movers exist) */}
            {catalysts.length > 1 && (
              <div className="space-y-1.5">
                <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                  Active Movers Radar ({catalysts.length})
                </span>
                <div className="flex gap-2 overflow-x-auto pb-1 thin-scrollbar">
                  {catalysts.slice(0, 8).map((cat) => (
                    <Link
                      key={cat.symbol}
                      href={`/stocks/${cat.symbol}`}
                      className="shrink-0 p-2 rounded-xl bg-white/[0.02] hover:bg-white/[0.06] border border-white/[0.06] hover:border-cyan-500/30 transition-all flex items-center space-x-2"
                    >
                      <span className="font-bold text-xs text-white">{cat.symbol}</span>
                      <span
                        className={cn(
                          "text-[10px] font-bold tabular-nums",
                          cat.move_pct >= 0 ? "text-emerald-400" : "text-rose-400"
                        )}
                      >
                        {cat.move_pct >= 0 ? "+" : ""}
                        {cat.move_pct.toFixed(1)}%
                      </span>
                    </Link>
                  ))}
                </div>
              </div>
            )}

            {/* Stacked sections: Recent Disclosures & Recent News */}
            <div className="grid grid-cols-1 gap-4 pt-1">
              {/* Disclosures Preview */}
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 text-xs font-bold text-slate-300">
                    <FileText className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Official Exchange Filings ({disclosures.length})</span>
                  </div>
                  {disclosures.length > 2 && (
                    <button
                      onClick={() => setActiveTab("disclosures")}
                      className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-0.5"
                    >
                      <span>View All</span>
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {disclosures.length === 0 ? (
                  <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-slate-500 text-xs text-center">
                    No corporate filings recorded in current session window.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {disclosures.slice(0, 3).map((d) => (
                      <div
                        key={d.disclosure_id}
                        className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-cyan-500/30 transition-colors space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2 text-[10px]">
                          <span className="px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 font-bold uppercase truncate max-w-[180px]">
                            {d.category || "General"}
                          </span>
                          <span className="text-slate-400 tabular-nums">
                            {formatISTTime(d.broadcast_timestamp || d.effective_session_date)}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-white line-clamp-2 leading-relaxed">
                          {d.subject}
                        </p>
                        {d.source_url && (
                          <a
                            href={d.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="inline-flex items-center space-x-1 text-[10px] text-cyan-400 hover:text-cyan-300 pt-0.5"
                          >
                            <span>Official Filing Document</span>
                            <ExternalLink className="w-2.5 h-2.5" />
                          </a>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* News Preview */}
              <div className="space-y-2 pt-2">
                <div className="flex items-center justify-between">
                  <div className="flex items-center space-x-2 text-xs font-bold text-slate-300">
                    <Newspaper className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Live News Wire ({news.length})</span>
                  </div>
                  {news.length > 2 && (
                    <button
                      onClick={() => setActiveTab("news")}
                      className="text-[10px] text-cyan-400 hover:text-cyan-300 flex items-center gap-0.5"
                    >
                      <span>View All</span>
                      <ChevronRight className="w-3 h-3" />
                    </button>
                  )}
                </div>

                {news.length === 0 ? (
                  <div className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.04] text-slate-500 text-xs text-center">
                    No recent news articles ingested. Click refresh to query Google News RSS.
                  </div>
                ) : (
                  <div className="space-y-2">
                    {news.slice(0, 3).map((a) => (
                      <div
                        key={a.id}
                        className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-cyan-500/30 transition-colors space-y-1.5"
                      >
                        <div className="flex items-center justify-between gap-2 text-[10px]">
                          <span className="text-slate-400 font-bold truncate max-w-[150px]">
                            {a.source}
                          </span>
                          <span
                            className={cn(
                              "px-2 py-0.5 rounded font-bold uppercase text-[9px] border",
                              a.impact?.direction === "BULLISH"
                                ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
                                : a.impact?.direction === "BEARISH"
                                ? "bg-rose-950/80 text-rose-300 border-rose-500/40"
                                : "bg-slate-900 text-slate-300 border-white/[0.08]"
                            )}
                          >
                            {a.impact?.direction || "NEUTRAL"}
                          </span>
                        </div>
                        <p className="text-xs font-semibold text-white line-clamp-2 leading-relaxed">
                          {a.title}
                        </p>
                        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-0.5">
                          <span className="tabular-nums">{formatISTTime(a.published_at)}</span>
                          {a.article_url && (
                            <a
                              href={a.article_url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="text-cyan-400 hover:text-cyan-300 inline-flex items-center gap-1"
                            >
                              <span>Read Source</span>
                              <ExternalLink className="w-2.5 h-2.5" />
                            </a>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* --- TAB: CATALYSTS --- */}
        {activeTab === "catalysts" && (
          <div className="space-y-4">
            {primaryCatalyst && (
              <div className="p-4 rounded-xl bg-[#090f1e]/90 border border-cyan-500/30 shadow-[0_0_20px_rgba(6,182,212,0.12)] space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center space-x-2">
                    <span className="text-base font-black text-white">
                      {primaryCatalyst.symbol}
                    </span>
                    <span
                      className={cn(
                        "px-2 py-0.5 rounded text-[11px] font-bold tabular-nums border",
                        primaryCatalyst.move_pct >= 0
                          ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
                          : "bg-rose-950/80 text-rose-300 border-rose-500/40"
                      )}
                    >
                      {primaryCatalyst.move_pct >= 0 ? "+" : ""}
                      {primaryCatalyst.move_pct.toFixed(1)}%
                    </span>
                    <span className="px-2 py-0.5 rounded text-[10px] bg-white/[0.04] text-slate-300 border border-white/[0.08] tabular-nums">
                      {primaryCatalyst.rvol.toFixed(1)}x RVOL
                    </span>
                  </div>

                  <span
                    className={cn(
                      "px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider border",
                      primaryCatalyst.classification.includes("Idiosyncratic")
                        ? "bg-cyan-950/90 text-cyan-300 border-cyan-500/50 shadow-[0_0_10px_rgba(6,182,212,0.2)]"
                        : "bg-purple-950/90 text-purple-300 border-purple-500/50 shadow-[0_0_10px_rgba(168,85,247,0.2)]"
                    )}
                  >
                    {primaryCatalyst.classification}
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                    Causal Diagnosis &amp; Rationale
                  </div>
                  <p className="text-xs text-slate-100 font-bold leading-relaxed bg-black/40 p-3 rounded-lg border border-white/[0.05]">
                    {primaryCatalyst.causal_headline}
                  </p>
                  {primaryCatalyst.causal_bullets && primaryCatalyst.causal_bullets.length > 0 && (
                    <div className="space-y-1.5 pt-1">
                      {primaryCatalyst.causal_bullets.map((bullet, idx) => (
                        <div
                          key={idx}
                          className="p-2.5 rounded-lg bg-white/[0.02] border border-white/[0.04] text-[11px] text-slate-300 leading-relaxed"
                        >
                          {bullet}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Full list of universe anomalies */}
            <div className="space-y-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Universe Intraday Anomalies ({catalysts.length})
              </span>
              {catalysts.length === 0 ? (
                <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.04] text-slate-500 text-xs text-center">
                  No active anomalies detected across universe. Trigger a scan above.
                </div>
              ) : (
                <div className="space-y-2">
                  {catalysts.map((cat) => (
                    <div
                      key={cat.symbol}
                      className="p-3 rounded-xl bg-white/[0.02] border border-white/[0.06] hover:border-cyan-500/30 transition-colors flex items-center justify-between gap-3"
                    >
                      <div className="flex items-center space-x-2.5 min-w-0">
                        <Link
                          href={`/stocks/${cat.symbol}`}
                          className="font-bold text-xs text-white hover:text-cyan-300 transition-colors shrink-0"
                        >
                          {cat.symbol}
                        </Link>
                        <span
                          className={cn(
                            "text-[10px] font-bold tabular-nums px-1.5 py-0.5 rounded border shrink-0",
                            cat.move_pct >= 0
                              ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/40"
                              : "bg-rose-950/80 text-rose-300 border-rose-500/40"
                          )}
                        >
                          {cat.move_pct >= 0 ? "+" : ""}
                          {cat.move_pct.toFixed(1)}%
                        </span>
                        <span className="text-[11px] text-slate-300 truncate hidden sm:inline">
                          {cat.company_name}
                        </span>
                      </div>
                      <div className="flex items-center space-x-2 shrink-0">
                        <span className="text-[10px] text-slate-400 tabular-nums">
                          {cat.rvol.toFixed(1)}x RVOL
                        </span>
                        <span className="text-[9px] px-2 py-0.5 rounded-full bg-slate-900 border border-white/[0.08] text-slate-300 font-bold uppercase hidden md:inline">
                          {cat.classification}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {/* --- TAB: DISCLOSURES --- */}
        {activeTab === "disclosures" && (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold uppercase tracking-wider text-slate-400">
                Official Regulatory Broadcasts ({disclosures.length})
              </span>
              <span className="text-[10px] text-slate-500">
                Exchange Feed &bull; Verified Filings
              </span>
            </div>

            {disclosures.length === 0 ? (
              <div className="p-8 rounded-xl bg-white/[0.02] border border-white/[0.04] text-slate-500 text-xs text-center space-y-2">
                <FileText className="w-8 h-8 text-slate-600 mx-auto" />
                <p>No regulatory disclosures recorded in current audit window.</p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {disclosures.map((d) => (
                  <div
                    key={d.disclosure_id}
                    className="p-3.5 rounded-xl bg-[#090d16] border border-white/[0.07] hover:border-cyan-500/30 transition-all space-y-2"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2 text-[10px]">
                      <div className="flex items-center space-x-2">
                        <span className="px-2 py-0.5 rounded-md bg-cyan-950/80 border border-cyan-500/30 text-cyan-300 font-bold uppercase tracking-wider">
                          {d.category || "General"}
                        </span>
                        {d.verification_status && (
                          <span className="flex items-center space-x-1 text-emerald-400 font-bold">
                            <ShieldCheck className="w-3 h-3" />
                            <span>{d.verification_status}</span>
                          </span>
                        )}
                      </div>
                      <span className="text-slate-400 tabular-nums">
                        {formatISTTime(d.broadcast_timestamp || d.effective_session_date)}
                      </span>
                    </div>

                    <h4 className="text-xs font-bold text-white leading-snug">
                      {d.subject}
                    </h4>

                    {d.details_summary && (
                      <p className="text-[11px] text-slate-300 leading-relaxed bg-black/30 p-2.5 rounded-lg border border-white/[0.04]">
                        {d.details_summary}
                      </p>
                    )}

                    <div className="flex items-center justify-between pt-1">
                      {d.dividend_declared !== null && (
                        <span className="text-[10px] text-emerald-300 font-mono">
                          Dividend: ₹{d.dividend_declared.toFixed(2)}/sh
                        </span>
                      )}
                      {d.source_url && (
                        <a
                          href={d.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center space-x-1.5 text-xs font-semibold text-cyan-400 hover:text-cyan-300 transition-colors ml-auto"
                        >
                          <span>View Official Exchange PDF</span>
                          <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* --- TAB: NEWS --- */}
        {activeTab === "news" && (
          <div className="space-y-4">
            <NewsImpactCard
              symbol={symbol || "MARKET"}
              articles={news}
              loading={loading || isRefreshing}
            />
          </div>
        )}
      </div>
    </div>
  );
}
