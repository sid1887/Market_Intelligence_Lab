"use client";

import React, { useEffect, useState } from "react";
import {
  CheckCircle2,
  AlertTriangle,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  Sparkles,
  Globe,
  Building2,
  Loader2
} from "lucide-react";
import { motion } from "framer-motion";
import { RadialConvictionGauge } from "./RadialConvictionGauge";

export interface DiagnosticItem {
  id: string;
  name: string;
  status: "PASS" | "CAUTION" | "FAIL";
  detail: string;
}

export interface InvestmentMemo {
  symbol: string;
  company_name: string;
  as_of_date: string;
  verdict: "STRONG_BUY_COMPOUNDER" | "TACTICAL_SWING_LONG" | "HOLD_FAIRLY_VALUED" | "AVOID_CAPITAL_PRESERVATION";
  target_horizon: string;
  institutional_conviction_score: number;
  conviction_breakdown?: {
    institutional_conviction_score: number;
    weights: {
      fundamentals: number;
      technicals: number;
      forecast_cone: number;
      news_catalysts: number;
    };
    calibration_status: string;
  };
  business_profile: {
    sector: string;
    industry: string;
    macro_sector: string;
    operating_segments: string;
    core_revenue_drivers: string;
    geographic_concentration: string;
  };
  bull_case: string[];
  bear_case: string[];
  health_checklist: DiagnosticItem[];
  key_metrics: {
    current_price: number;
    sma_20: number | null;
    sma_50: number | null;
    sma_200: number | null;
    ttm_pe: number | null;
    roe_pct: number | null;
    debt_to_equity: number | null;
    opm_pct: number | null;
    beta_60d_nifty: number | null;
    volatility_annualized: number | null;
  };
  forecast_cone_summary?: {
    expected_20d_price: number;
    upper_80: number;
    lower_80: number;
    upper_95: number;
    lower_95: number;
    upside_pct: number;
  };
  recent_news_count?: number;
  generated_at: string;
}

import { apiFetch } from "@/lib/api";

interface InvestmentMemoCardProps {
  symbol: string;
  initialMemo?: InvestmentMemo | null;
}

export default function InvestmentMemoCard({ symbol, initialMemo }: InvestmentMemoCardProps) {
  const [memo, setMemo] = useState<InvestmentMemo | null>(initialMemo || null);
  const [loading, setLoading] = useState<boolean>(!initialMemo);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initialMemo) {
      setMemo(initialMemo);
      setLoading(false);
      return;
    }

    let isMounted = true;
    async function fetchMemo() {
      try {
        setLoading(true);
        setError(null);
        const data = await apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`);
        if (isMounted) {
          setMemo(data);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Error loading memo");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    }

    if (symbol) {
      fetchMemo();
    }

    return () => {
      isMounted = false;
    };
  }, [symbol, initialMemo]);

  if (loading) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-xl backdrop-blur-md flex items-center justify-center space-x-3 py-10 font-mono text-sm text-slate-400">
        <Loader2 className="w-5 h-5 animate-spin text-cyan-400" />
        <span>Synthesizing Institutional Investment Decision Memo for {symbol}...</span>
      </div>
    );
  }

  if (error || !memo) {
    return (
      <div className="bg-slate-900/90 border border-slate-800 rounded-2xl p-5 text-center font-mono text-xs text-slate-400">
        <p className="text-amber-400 font-semibold mb-1">Investment Decision Memo Deferred</p>
        <p>{error || "Insufficient factor depth to render institutional memo."}</p>
      </div>
    );
  }

  // Formatting helpers
  const verdictConfig = {
    STRONG_BUY_COMPOUNDER: {
      label: "STRONG BUY (COMPOUNDER)",
      bg: "bg-emerald-950/80 border-emerald-500/60 text-emerald-300 shadow-emerald-950/50",
      glow: "border-emerald-500/50 shadow-emerald-900/30",
      horizonLabel: "12 to 24 Months"
    },
    TACTICAL_SWING_LONG: {
      label: "TACTICAL SWING LONG",
      bg: "bg-cyan-950/80 border-cyan-500/60 text-cyan-300 shadow-cyan-950/50",
      glow: "border-cyan-500/50 shadow-cyan-900/30",
      horizonLabel: "2 to 8 Weeks"
    },
    HOLD_FAIRLY_VALUED: {
      label: "HOLD (FAIRLY VALUED)",
      bg: "bg-amber-950/80 border-amber-500/60 text-amber-300 shadow-amber-950/50",
      glow: "border-amber-500/50 shadow-amber-900/30",
      horizonLabel: "3 to 6 Months"
    },
    AVOID_CAPITAL_PRESERVATION: {
      label: "AVOID (CAPITAL PRESERVATION)",
      bg: "bg-rose-950/80 border-rose-500/60 text-rose-300 shadow-rose-950/50",
      glow: "border-rose-500/50 shadow-rose-900/30",
      horizonLabel: "Immediate Capital Protection"
    }
  }[memo.verdict] || {
    label: memo.verdict.replace(/_/g, " "),
    bg: "bg-slate-800 border-slate-700 text-slate-300",
    glow: "border-slate-700",
    horizonLabel: memo.target_horizon.replace(/_/g, " ")
  };

  const score = memo.institutional_conviction_score;

  return (
    <div className={`bg-slate-900/90 border border-slate-800 rounded-2xl p-6 shadow-2xl backdrop-blur-md space-y-6 ${verdictConfig.glow}`}>
      {/* 1. Header Banner & Conviction Metric */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-5 border-b border-slate-800/80">
        <div className="space-y-1.5">
          <div className="flex items-center space-x-2.5">
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold tracking-wider uppercase bg-cyan-950 border border-cyan-800 text-cyan-300">
              Institutional Memo
            </span>
            <span className="text-xs font-mono text-slate-400 flex items-center space-x-1">
              <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
              <span>Multi-Factor Synthesis &middot; As of {memo.as_of_date}</span>
            </span>
          </div>
          <h2 className="text-xl sm:text-2xl font-black text-white font-mono tracking-tight flex items-center space-x-2">
            <span>{memo.company_name}</span>
            <span className="text-cyan-400 font-normal">({memo.symbol})</span>
          </h2>
        </div>

        {/* Verdict Badge & Conviction Score */}
        <div className="flex flex-wrap items-center gap-4">
          {/* Institutional Conviction Meter */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-3 flex items-center space-x-3.5 font-mono shadow-inner">
            <RadialConvictionGauge score={score} />
            <div>
              <span className="text-xs font-bold text-white uppercase tracking-wider block">
                Conviction Score
              </span>
              <span className="text-[10px] text-slate-400 block max-w-[120px] leading-tight">
                Empirically weighted multi-factor gauge
              </span>
            </div>
          </div>

          {/* Verdict Card */}
          <div className={`px-4 py-2.5 rounded-xl border flex flex-col items-center justify-center font-mono ${verdictConfig.bg}`}>
            <span className="text-[10px] uppercase font-bold tracking-widest text-slate-400">
              Deterministic Verdict
            </span>
            <span className="text-sm font-black tracking-tight">{verdictConfig.label}</span>
            <span className="text-[11px] text-slate-300 mt-0.5 opacity-90">
              Horizon: {verdictConfig.horizonLabel}
            </span>
          </div>
        </div>
      </div>

      {/* 2. Business Profile Card */}
      <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4.5 space-y-3 font-mono text-xs">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/60 pb-2 text-slate-400">
          <div className="flex items-center space-x-2">
            <Building2 className="w-4 h-4 text-cyan-400" />
            <span className="font-bold text-slate-200">Business Profile & Operating Architecture</span>
          </div>
          <div className="flex items-center space-x-3 text-[11px] text-slate-400">
            <span>Sector: <strong className="text-slate-200">{memo.business_profile.sector}</strong></span>
            <span>&bull;</span>
            <span>Industry: <strong className="text-slate-200">{memo.business_profile.industry}</strong></span>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3.5 pt-1">
          <div className="space-y-1">
            <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider block">Operating Segments</span>
            <p className="text-slate-300 leading-relaxed text-[11px]">{memo.business_profile.operating_segments}</p>
          </div>
          <div className="space-y-1">
            <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider block">Core Revenue Drivers</span>
            <p className="text-slate-300 leading-relaxed text-[11px]">{memo.business_profile.core_revenue_drivers}</p>
          </div>
          <div className="space-y-1">
            <span className="text-[11px] text-slate-500 font-semibold uppercase tracking-wider block flex items-center space-x-1">
              <Globe className="w-3 h-3 text-cyan-400" />
              <span>Geographic Concentration</span>
            </span>
            <p className="text-slate-300 leading-relaxed text-[11px]">{memo.business_profile.geographic_concentration}</p>
          </div>
        </div>
      </div>

      {/* 3. Health Checklist & Red Flags (4 diagnostics) */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between font-mono text-xs">
          <span className="font-bold text-slate-200 flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
            <span>Institutional Health Checklist &amp; Red Flag Diagnostics</span>
          </span>
          <span className="text-[11px] text-slate-500">4 Core Prudence Diagnostics</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {memo.health_checklist.map((diag) => {
            const isPass = diag.status === "PASS";
            const isCaution = diag.status === "CAUTION";
            const borderCol = isPass
              ? "border-emerald-800/60 bg-emerald-950/20"
              : isCaution
              ? "border-amber-800/60 bg-amber-950/20"
              : "border-rose-800/60 bg-rose-950/20";

            return (
              <div
                key={diag.id}
                className={`p-3.5 rounded-xl border ${borderCol} font-mono space-y-1.5 flex flex-col justify-between`}
              >
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-bold text-slate-200">{diag.name}</span>
                    <span className={`text-[10px] font-black px-2 py-0.5 rounded-full border ${
                      isPass
                        ? "bg-emerald-950 text-emerald-300 border-emerald-700"
                        : isCaution
                        ? "bg-amber-950 text-amber-300 border-amber-700"
                        : "bg-rose-950 text-rose-300 border-rose-700"
                    }`}>
                      {diag.status}
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-400 leading-relaxed">{diag.detail}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. Two-Column Synthesis: Bull Case vs Bear Risks */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 font-mono">
        {/* Bull Case */}
        <div className="bg-emerald-950/20 border-l-4 border-l-emerald-500 border border-emerald-900/50 rounded-xl p-4.5 space-y-3">
          <div className="flex items-center space-x-2 text-emerald-400 font-bold text-xs pb-2 border-b border-emerald-900/40">
            <TrendingUp className="w-4 h-4" />
            <span>Bull Case: Quantified Growth Catalysts</span>
          </div>
          <motion.ul
            initial="hidden"
            animate="visible"
            variants={{
              hidden: { opacity: 0 },
              visible: { opacity: 1, transition: { staggerChildren: 0.12 } },
            }}
            className="space-y-2 text-[11px] text-slate-300"
          >
            {memo.bull_case.map((point, idx) => (
              <motion.li
                key={idx}
                variants={{
                  hidden: { opacity: 0, x: -10 },
                  visible: { opacity: 1, x: 0, transition: { duration: 0.3 } },
                }}
                className="flex items-start space-x-2.5"
              >
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <span className="leading-relaxed">{point}</span>
              </motion.li>
            ))}
          </motion.ul>
        </div>

        {/* Bear Case */}
        <div className="bg-rose-950/20 border-l-4 border-l-rose-500 border border-rose-900/50 rounded-xl p-4.5 space-y-3">
          <div className="flex items-center space-x-2 text-rose-400 font-bold text-xs pb-2 border-b border-rose-900/40">
            <TrendingDown className="w-4 h-4" />
            <span>Bear Case: Structural Headwinds &amp; Tail Risks</span>
          </div>
          <motion.ul
            initial="hidden"
            animate="visible"
            variants={{
              hidden: { opacity: 0 },
              visible: { opacity: 1, transition: { staggerChildren: 0.12 } },
            }}
            className="space-y-2 text-[11px] text-slate-300"
          >
            {memo.bear_case.map((point, idx) => (
              <motion.li
                key={idx}
                variants={{
                  hidden: { opacity: 0, x: 10 },
                  visible: { opacity: 1, x: 0, transition: { duration: 0.3 } },
                }}
                className="flex items-start space-x-2.5"
              >
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span className="leading-relaxed">{point}</span>
              </motion.li>
            ))}
          </motion.ul>
        </div>
      </div>

      {/* 5. Key Valuation & Factor Metrics Strip */}
      <div className="bg-slate-950/70 border border-slate-800/80 rounded-xl p-3 flex flex-wrap items-center justify-between gap-3 text-xs font-mono">
        <div className="flex items-center space-x-4">
          <span className="text-slate-400">Current: <strong className="text-white">₹{memo.key_metrics.current_price?.toFixed(2)}</strong></span>
          <span className="text-slate-400">TTM P/E: <strong className="text-cyan-300">{memo.key_metrics.ttm_pe ? `${memo.key_metrics.ttm_pe.toFixed(1)}x` : "N/A"}</strong></span>
          <span className="text-slate-400">ROE: <strong className="text-emerald-300">{memo.key_metrics.roe_pct ? `${memo.key_metrics.roe_pct.toFixed(1)}%` : "N/A"}</strong></span>
          <span className="text-slate-400">D/E: <strong className="text-slate-200">{memo.key_metrics.debt_to_equity !== null ? `${memo.key_metrics.debt_to_equity.toFixed(2)}x` : "0.00x"}</strong></span>
          <span className="text-slate-400">OPM: <strong className="text-slate-200">{memo.key_metrics.opm_pct ? `${memo.key_metrics.opm_pct.toFixed(1)}%` : "N/A"}</strong></span>
        </div>

        {memo.forecast_cone_summary && (
          <div className="flex items-center space-x-3 text-[11px]">
            <span className="text-slate-400">20D Expected: <strong className="text-cyan-300">₹{memo.forecast_cone_summary.expected_20d_price.toFixed(2)}</strong></span>
            <span className={memo.forecast_cone_summary.upside_pct >= 0 ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
              ({memo.forecast_cone_summary.upside_pct >= 0 ? "+" : ""}{memo.forecast_cone_summary.upside_pct.toFixed(1)}%)
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
