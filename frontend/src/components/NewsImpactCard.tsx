"use client";

import React, { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Newspaper,
  TrendingUp,
  TrendingDown,
  Minus,
  ExternalLink,
  Clock,
  ShieldCheck,
  Zap,
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
    return (
      d.toLocaleString("en-IN", {
        month: "short",
        day: "numeric",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: "Asia/Kolkata",
      }) + " IST"
    );
  } catch {
    return isoString;
  }
}

export default function NewsImpactCard({
  symbol,
  articles = [],
  loading = false,
}: NewsImpactCardProps) {
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
    const reset: Record<string, "summary" | "impact"> = {};
    articles.forEach((a) => {
      reset[a.id] = tab;
    });
    setActiveTabs(reset);
  };

  return (
    <section className="relative overflow-hidden bg-[#080c14]/80 backdrop-blur-2xl border border-white/[0.08] rounded-2xl p-6 shadow-[0_12px_40px_rgba(0,0,0,0.6)] space-y-5">
      {/* Top subtle ambient light line */}
      <div className="absolute top-0 left-0 right-0 h-[1px] bg-gradient-to-r from-transparent via-cyan-500/30 to-transparent pointer-events-none" />

      {/* Section Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-4 border-b border-white/[0.07] gap-4">
        <div className="flex items-center space-x-3">
          <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400 shadow-[0_0_15px_rgba(6,182,212,0.15)]">
            <Newspaper className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h2 className="text-base font-bold text-white tracking-tight font-mono">
                Real-Time News & Sentiment Engine
              </h2>
              <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full font-mono bg-cyan-950/60 text-cyan-400 border border-cyan-500/30 shadow-[0_0_10px_rgba(6,182,212,0.15)]">
                Exchange Wire
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Automated NLP sentiment tagging & institutional catalyst mapping for {symbol}
            </p>
          </div>
        </div>

        {/* Global Tab Switcher */}
        <div className="flex items-center space-x-3">
          <div className="flex items-center bg-[#050810]/90 p-1 rounded-xl border border-white/[0.08] text-xs font-mono">
            <button
              onClick={() => handleGlobalTabSwitch("summary")}
              className={`px-3 py-1.5 rounded-lg transition-all duration-200 ${
                globalTab === "summary"
                  ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/30 shadow-[0_0_12px_rgba(6,182,212,0.25)]"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Summary View
            </button>
            <button
              onClick={() => handleGlobalTabSwitch("impact")}
              className={`px-3 py-1.5 rounded-lg transition-all duration-200 ${
                globalTab === "impact"
                  ? "bg-cyan-500/20 text-cyan-300 font-semibold border border-cyan-500/30 shadow-[0_0_12px_rgba(6,182,212,0.25)]"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              Impact View
            </button>
          </div>
          <span className="text-xs text-slate-400 font-mono hidden md:inline px-2.5 py-1 rounded-lg bg-white/[0.03] border border-white/[0.06] tabular-nums">
            {articles.length} Disclosures
          </span>
        </div>
      </div>

      {/* Loading Skeleton */}
      {loading && (
        <div className="space-y-3 py-4">
          {[1, 2, 3].map((i) => (
            <div
              key={i}
              className="animate-pulse bg-white/[0.02] rounded-xl p-4 border border-white/[0.05] space-y-3"
            >
              <div className="flex justify-between items-center">
                <div className="h-4 bg-white/[0.08] rounded w-1/4" />
                <div className="h-4 bg-white/[0.08] rounded w-20" />
              </div>
              <div className="h-4 bg-white/[0.05] rounded w-3/4" />
              <div className="h-3 bg-white/[0.03] rounded w-1/2" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State */}
      {!loading && articles.length === 0 && (
        <div className="text-center py-12 bg-white/[0.01] rounded-xl border border-dashed border-white/[0.08]">
          <Newspaper className="w-10 h-10 text-slate-600 mx-auto mb-3 opacity-60" />
          <p className="text-sm font-mono text-slate-300 font-medium">
            No recent financial media coverage or regulatory filings captured for {symbol}.
          </p>
          <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
            Universal feed actively monitors Google News RSS, BSE corporate disclosures, and SEBI filings.
          </p>
        </div>
      )}

      {/* Articles Feed */}
      {!loading && articles.length > 0 && (
        <div className="space-y-4">
          {articles.map((article, idx) => {
            const currentTab = getActiveTab(article.id);
            const isBullish = article.impact?.direction === "BULLISH";
            const isBearish = article.impact?.direction === "BEARISH";

            const borderAccent = isBullish
              ? "border-l-emerald-500 hover:border-l-emerald-400 shadow-[inset_4px_0_12px_rgba(16,185,129,0.12)]"
              : isBearish
              ? "border-l-rose-500 hover:border-l-rose-400 shadow-[inset_4px_0_12px_rgba(244,63,94,0.12)]"
              : "border-l-cyan-500/50 hover:border-l-cyan-400 shadow-[inset_4px_0_12px_rgba(6,182,212,0.08)]";

            return (
              <motion.div
                key={article.id || idx}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.25, delay: idx * 0.04 }}
                className={`group relative bg-[#0b101c]/70 hover:bg-[#0e1424]/90 border border-white/[0.07] hover:border-white/[0.14] border-l-4 ${borderAccent} rounded-xl p-4 transition-all duration-300 space-y-3.5`}
              >
                {/* Article Top Meta */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5">
                  <div className="flex flex-wrap items-center gap-2 text-xs font-mono">
                    <span className="px-2.5 py-0.5 bg-white/[0.05] text-slate-200 border border-white/[0.08] rounded-md font-semibold tracking-wide">
                      {article.source}
                    </span>
                    <span className="flex items-center text-slate-400 tabular-nums">
                      <Clock className="w-3.5 h-3.5 mr-1 text-slate-500" />
                      {formatDate(article.published_at)}
                    </span>
                  </div>

                  {/* Directional Badges */}
                  <div className="flex items-center space-x-2">
                    {isBullish ? (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-mono text-[11px] font-bold bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.25)]">
                        <TrendingUp className="w-3.5 h-3.5 mr-1 text-emerald-400" />
                        BULLISH CATALYST
                      </span>
                    ) : isBearish ? (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-mono text-[11px] font-bold bg-rose-500/10 text-rose-400 border border-rose-500/30 shadow-[0_0_12px_rgba(244,63,94,0.25)]">
                        <TrendingDown className="w-3.5 h-3.5 mr-1 text-rose-400" />
                        BEARISH HEADWIND
                      </span>
                    ) : (
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full font-mono text-[11px] font-bold bg-white/[0.05] text-slate-300 border border-white/[0.1]">
                        <Minus className="w-3.5 h-3.5 mr-1 text-slate-400" />
                        NEUTRAL FLOW
                      </span>
                    )}

                    {article.impact?.horizon && (
                      <span className="px-2 py-0.5 rounded-full font-mono text-[10px] uppercase tracking-wider bg-white/[0.03] text-slate-400 border border-white/[0.06]">
                        {article.impact.horizon === "MEDIUM_TERM" ? "1-3 Mo" : "1-5 Days"}
                      </span>
                    )}
                  </div>
                </div>

                {/* Article Headline */}
                <div>
                  <a
                    href={article.article_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-sm font-semibold text-slate-100 group-hover:text-cyan-300 transition-colors inline-flex items-baseline gap-1.5 leading-snug"
                  >
                    <span>{article.title}</span>
                    <ExternalLink className="w-3.5 h-3.5 opacity-50 group-hover:opacity-100 group-hover:translate-x-0.5 transition-all flex-shrink-0" />
                  </a>
                </div>

                {/* Sub-Card Tab Bar */}
                <div className="flex items-center justify-between pt-2 border-t border-white/[0.06]">
                  <div className="flex space-x-1.5 text-xs font-mono">
                    <button
                      onClick={() => setArticleTab(article.id, "summary")}
                      className={`px-2.5 py-1 rounded-md transition-all ${
                        currentTab === "summary"
                          ? "bg-white/[0.08] text-cyan-300 font-semibold border border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.2)]"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Executive Summary
                    </button>
                    <button
                      onClick={() => setArticleTab(article.id, "impact")}
                      className={`px-2.5 py-1 rounded-md transition-all ${
                        currentTab === "impact"
                          ? "bg-white/[0.08] text-cyan-300 font-semibold border border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.2)]"
                          : "text-slate-400 hover:text-slate-200"
                      }`}
                    >
                      Impact Vector
                    </button>
                  </div>

                  {article.impact?.confidence_score && (
                    <span className="text-[11px] font-mono text-slate-400 flex items-center tabular-nums">
                      <ShieldCheck className="w-3.5 h-3.5 mr-1 text-emerald-400" />
                      {(article.impact.confidence_score * 100).toFixed(0)}% Confidence
                    </span>
                  )}
                </div>

                {/* Tab Content */}
                <div className="bg-[#050810]/70 rounded-xl p-3.5 border border-white/[0.05]">
                  <AnimatePresence mode="wait">
                    {currentTab === "summary" ? (
                      <motion.ul
                        key="summary"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="space-y-2 text-xs text-slate-300"
                      >
                        {article.summary && article.summary.length > 0 ? (
                          article.summary.map((bullet, idx) => (
                            <li key={idx} className="flex items-start space-x-2">
                              <span className="text-cyan-400 mt-0.5 leading-none font-bold">›</span>
                              <span className="leading-relaxed">{bullet}</span>
                            </li>
                          ))
                        ) : (
                          <li className="text-slate-500 italic">No structured summary generated.</li>
                        )}
                      </motion.ul>
                    ) : (
                      <motion.div
                        key="impact"
                        initial={{ opacity: 0 }}
                        animate={{ opacity: 1 }}
                        exit={{ opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="space-y-3 text-xs"
                      >
                        {/* Metrics Grid */}
                        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pb-2.5 border-b border-white/[0.06]">
                          <div>
                            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-0.5">
                              Directional Vector
                            </span>
                            <span
                              className={`font-mono font-bold ${
                                isBullish
                                  ? "text-emerald-400"
                                  : isBearish
                                  ? "text-rose-400"
                                  : "text-slate-300"
                              }`}
                            >
                              {article.impact?.direction || "NEUTRAL"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-0.5">
                              Expected Duration
                            </span>
                            <span className="font-mono text-slate-200">
                              {article.impact?.horizon === "MEDIUM_TERM"
                                ? "MEDIUM_TERM (1–3 Months)"
                                : "SHORT_TERM (1–5 Days)"}
                            </span>
                          </div>
                          <div>
                            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-0.5">
                              Factor Exposure
                            </span>
                            <div className="flex flex-wrap gap-1 mt-0.5">
                              {article.impact?.affected_drivers &&
                              article.impact.affected_drivers.length > 0 ? (
                                article.impact.affected_drivers.map((drv, idx) => (
                                  <span
                                    key={idx}
                                    className="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-950/60 text-cyan-300 border border-cyan-800/40"
                                  >
                                    {drv}
                                  </span>
                                ))
                              ) : (
                                <span className="text-slate-500 text-[11px] font-mono">
                                  Systemic
                                </span>
                              )}
                            </div>
                          </div>
                        </div>

                        {/* Rationale */}
                        <div>
                          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-400 block mb-1 flex items-center">
                            <Zap className="w-3 h-3 mr-1 text-cyan-400" /> Quantitative Rationale
                          </span>
                          <p className="text-slate-300 italic leading-relaxed bg-black/30 p-2.5 rounded-lg border border-white/[0.04]">
                            &ldquo;{article.impact?.rationale || "Balanced operational and market coverage."}&rdquo;
                          </p>
                        </div>
                      </motion.div>
                    )}
                  </AnimatePresence>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </section>
  );
}
