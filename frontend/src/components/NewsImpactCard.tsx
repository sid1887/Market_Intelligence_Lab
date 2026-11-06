"use client";

import React, { useState } from "react";
import {
  Newspaper,
  TrendingUp,
  TrendingDown,
  Minus,
  ExternalLink,
  Clock,
  ShieldCheck,
} from "lucide-react";

export interface NewsImpact {
  direction: "BULLISH" | "BEARISH" | "NEUTRAL" | string;
  horizon: "SHORT_TERM" | "MEDIUM_TERM" | string;
  affected_drivers: string[];
  rationale: string;
  confidence_score?: number;
}

export interface NewsArticle {
  id: string;
  title: string;
  source: string;
  published_at: string;
  article_url: string;
  summary: string[];
  impact: NewsImpact;
}

interface NewsImpactCardProps {
  symbol: string;
  articles?: NewsArticle[];
  loading?: boolean;
}

function formatDate(isoString: string): string {
  try {
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return isoString;
    return d.toLocaleString("en-IN", {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      timeZone: "Asia/Kolkata",
    }) + " IST";
  } catch {
    return isoString;
  }
}

export default function NewsImpactCard({ symbol, articles = [], loading = false }: NewsImpactCardProps) {
  // Map article ID -> "summary" | "impact" tab state
  const [activeTabs, setActiveTabs] = useState<Record<string, "summary" | "impact">>({});
  // Global view toggle default
  const [globalTab, setGlobalTab] = useState<"summary" | "impact">("summary");

  const getActiveTab = (id: string): "summary" | "impact" => {
    return activeTabs[id] || globalTab;
  };

  const setArticleTab = (id: string, tab: "summary" | "impact") => {
    setActiveTabs((prev) => ({ ...prev, [id]: tab }));
  };

  const handleGlobalTabSwitch = (tab: "summary" | "impact") => {
    setGlobalTab(tab);
    // Reset individual overrides to match global
    const reset: Record<string, "summary" | "impact"> = {};
    articles.forEach((a) => {
      reset[a.id] = tab;
    });
    setActiveTabs(reset);
  };

  return (
    <section className="bg-slate-900/80 border border-slate-800 rounded-xl p-5 shadow-xl space-y-4">
      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-3">
        <div className="flex items-center space-x-2">
          <Newspaper className="w-5 h-5 text-cyan-400" />
          <h2 className="text-base font-bold text-slate-100 font-mono tracking-tight">
            Real-Time News & Directional Impact Engine
          </h2>
          <span className="text-xs px-2 py-0.5 rounded-full font-mono bg-cyan-950/60 text-cyan-400 border border-cyan-800/50">
            Exchange Regulatory Wire (RSS)
          </span>
        </div>

        {/* Global Tab Switcher */}
        <div className="flex items-center space-x-2">
          <div className="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs font-mono">
            <button
              onClick={() => handleGlobalTabSwitch("summary")}
              className={`px-3 py-1 rounded transition-colors ${
                globalTab === "summary"
                  ? "bg-cyan-500/20 text-cyan-400 font-semibold border border-cyan-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Summary View
            </button>
            <button
              onClick={() => handleGlobalTabSwitch("impact")}
              className={`px-3 py-1 rounded transition-colors ${
                globalTab === "impact"
                  ? "bg-cyan-500/20 text-cyan-400 font-semibold border border-cyan-500/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Impact View
            </button>
          </div>
          <span className="text-xs text-slate-400 font-mono hidden md:inline">
            {articles.length} Aggregated
          </span>
        </div>
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-3 py-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="animate-pulse bg-slate-800/40 rounded-lg p-4 border border-slate-800/60 space-y-2">
              <div className="h-4 bg-slate-700/50 rounded w-3/4" />
              <div className="h-3 bg-slate-700/30 rounded w-1/2" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && articles.length === 0 && (
        <div className="text-center py-8 bg-slate-950/40 rounded-lg border border-slate-800/50">
          <Newspaper className="w-8 h-8 text-slate-600 mx-auto mb-2" />
          <p className="text-sm font-mono text-slate-400">
            No recent financial media coverage or regulatory news captured for {symbol}.
          </p>
          <p className="text-xs text-slate-500 mt-1">
            Feed continuously monitors Google News RSS and Indian corporate disclosure channels.
          </p>
        </div>
      )}

      {/* Articles Feed */}
      {!loading && articles.length > 0 && (
        <div className="space-y-4">
          {articles.map((article) => {
            const currentTab = getActiveTab(article.id);
            const isBullish = article.impact?.direction === "BULLISH";
            const isBearish = article.impact?.direction === "BEARISH";

            return (
              <div
                key={article.id}
                className="bg-slate-950/70 border border-slate-800 hover:border-slate-700/80 rounded-lg p-4 transition-all space-y-3"
              >
                {/* Article Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
                    <span className="px-2 py-0.5 bg-slate-800 text-slate-300 rounded font-semibold">
                      {article.source}
                    </span>
                    <span className="flex items-center text-slate-400">
                      <Clock className="w-3 h-3 mr-1" />
                      {formatDate(article.published_at)}
                    </span>
                  </div>

                  {/* Directional Badge */}
                  <div className="flex items-center space-x-2">
                    {isBullish ? (
                      <span className="flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
                        <TrendingUp className="w-3.5 h-3.5 mr-1" />
                        BULLISH
                      </span>
                    ) : isBearish ? (
                      <span className="flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30">
                        <TrendingDown className="w-3.5 h-3.5 mr-1" />
                        BEARISH
                      </span>
                    ) : (
                      <span className="flex items-center px-2 py-0.5 rounded font-mono text-xs font-bold bg-slate-800 text-slate-300 border border-slate-700">
                        <Minus className="w-3.5 h-3.5 mr-1" />
                        NEUTRAL
                      </span>
                    )}

                    {article.impact?.horizon && (
                      <span className="px-2 py-0.5 rounded font-mono text-[11px] bg-slate-900 text-slate-400 border border-slate-800">
                        {article.impact.horizon === "MEDIUM_TERM" ? "1-3 Mo" : "1-5 Days"}
                      </span>
                    )}
                  </div>
                </div>

                {/* Article Title */}
                <div>
                  <a
                    href={article.article_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-semibold text-slate-100 hover:text-cyan-400 transition-colors inline-flex items-center group leading-snug"
                  >
                    <span>{article.title}</span>
                    <ExternalLink className="w-3.5 h-3.5 ml-1.5 opacity-60 group-hover:opacity-100 transition-opacity flex-shrink-0" />
                  </a>
                </div>

                {/* Sub-Card Tab Bar */}
                <div className="flex items-center justify-between pt-1 border-t border-slate-800/80">
                  <div className="flex space-x-2 text-xs font-mono">
                    <button
                      onClick={() => setArticleTab(article.id, "summary")}
                      className={`px-2.5 py-1 rounded transition-colors ${
                        currentTab === "summary"
                          ? "bg-slate-800 text-cyan-300 font-semibold border border-cyan-800/40"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Summary
                    </button>
                    <button
                      onClick={() => setArticleTab(article.id, "impact")}
                      className={`px-2.5 py-1 rounded transition-colors ${
                        currentTab === "impact"
                          ? "bg-slate-800 text-cyan-300 font-semibold border border-cyan-800/40"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Directional Impact
                    </button>
                  </div>

                  {article.impact?.confidence_score && (
                    <span className="text-[11px] font-mono text-slate-500 flex items-center">
                      <ShieldCheck className="w-3 h-3 mr-1 text-slate-400" />
                      {(article.impact.confidence_score * 100).toFixed(0)}% Rule Match (Heuristic)
                    </span>
                  )}
                </div>

                {/* Tab Content */}
                <div className="bg-slate-900/60 rounded-md p-3 border border-slate-800/60">
                  {currentTab === "summary" ? (
                    /* Summary Tab Content */
                    <ul className="space-y-2 text-xs text-slate-300">
                      {article.summary && article.summary.length > 0 ? (
                        article.summary.map((bullet, idx) => (
                          <li key={idx} className="flex items-start space-x-2">
                            <span className="text-cyan-400 mt-0.5">•</span>
                            <span className="leading-relaxed">{bullet}</span>
                          </li>
                        ))
                      ) : (
                        <li className="text-slate-500 italic">No structured bullets available.</li>
                      )}
                    </ul>
                  ) : (
                    /* Impact Tab Content */
                    <div className="space-y-2.5 text-xs">
                      {/* Grid: Direction, Horizon, Drivers */}
                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 pb-2 border-b border-slate-800/60">
                        <div>
                          <span className="text-[11px] font-mono text-slate-500 block">Assessment</span>
                          <span
                            className={`font-mono font-bold ${
                              isBullish ? "text-emerald-400" : isBearish ? "text-rose-400" : "text-slate-300"
                            }`}
                          >
                            {article.impact?.direction || "NEUTRAL"}
                          </span>
                        </div>
                        <div>
                          <span className="text-[11px] font-mono text-slate-500 block">Horizon</span>
                          <span className="font-mono text-slate-300">
                            {article.impact?.horizon === "MEDIUM_TERM"
                              ? "MEDIUM_TERM (1–3 Months)"
                              : "SHORT_TERM (1–5 Days)"}
                          </span>
                        </div>
                        <div>
                          <span className="text-[11px] font-mono text-slate-500 block">Affected Drivers</span>
                          <div className="flex flex-wrap gap-1 mt-0.5">
                            {article.impact?.affected_drivers && article.impact.affected_drivers.length > 0 ? (
                              article.impact.affected_drivers.map((drv, idx) => (
                                <span
                                  key={idx}
                                  className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-cyan-950/70 text-cyan-300 border border-cyan-800/50"
                                >
                                  {drv}
                                </span>
                              ))
                            ) : (
                              <span className="text-slate-500 text-[11px] font-mono">None</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* Rationale */}
                      <div>
                        <span className="text-[11px] font-mono text-slate-500 block mb-1">
                          Directional Rationale
                        </span>
                        <p className="text-slate-300 italic leading-relaxed bg-slate-950/50 p-2 rounded border border-slate-800/40">
                          &ldquo;{article.impact?.rationale || "Balanced operational and market coverage."}&rdquo;
                        </p>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
