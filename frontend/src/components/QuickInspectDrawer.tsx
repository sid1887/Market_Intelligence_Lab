"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  X,
  ExternalLink,
  ShieldCheck,
  TrendingUp,
  TrendingDown,
  AlertTriangle,
  Loader2,
  Sparkles
} from "lucide-react";
import { RadialConvictionGauge } from "./RadialConvictionGauge";

import { apiFetch } from "@/lib/api";

interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface DiagnosticItem {
  id: string;
  name: string;
  status: "PASS" | "CAUTION" | "FAIL";
  detail: string;
}

interface MemoData {
  symbol: string;
  company_name: string;
  verdict: string;
  institutional_conviction_score: number;
  health_checklist: DiagnosticItem[];
  bull_case: string[];
  bear_case: string[];
  key_metrics?: {
    current_price?: number;
    ttm_pe?: number | null;
    roe_pct?: number | null;
    debt_to_equity?: number | null;
    opm_pct?: number | null;
  };
}

interface QuickInspectDrawerProps {
  symbol: string | null;
  onClose: () => void;
}

export default function QuickInspectDrawer({ symbol, onClose }: QuickInspectDrawerProps) {
  const [memo, setMemo] = useState<MemoData | null>(null);
  const [candles, setCandles] = useState<Candle[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!symbol) return;

    let isMounted = true;
    setLoading(true);
    setError(null);

    const fetchData = async () => {
      try {
        // Fetch Memo and 30-day History in parallel
        const [memoJson, histJson] = await Promise.all([
          apiFetch<MemoData>(`/stocks/${symbol}/memo`),
          apiFetch<Candle[]>(`/stocks/${symbol}/history?limit=30`),
        ]);

        if (isMounted) {
          setMemo(memoJson);
          setCandles(histJson ?? []);
        }
      } catch (err: unknown) {
        if (isMounted) {
          setError(err instanceof Error ? err.message : "Failed to load stock data");
        }
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }
    };

    fetchData();

    // Close on Escape key
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => {
      isMounted = false;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [symbol, onClose]);

  // SVG Mini Candlestick geometry
  const chartGeometry = useMemo(() => {
    if (candles.length === 0) return null;
    const width = 420;
    const height = 140;
    const padding = { top: 12, bottom: 18, left: 10, right: 48 };

    const minPrice = Math.min(...candles.map(c => c.low));
    const maxPrice = Math.max(...candles.map(c => c.high));
    const priceRange = maxPrice - minPrice || 1;

    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    const candleWidth = Math.max(3, Math.min(8, (chartW / candles.length) * 0.65));

    const points = candles.map((c, i) => {
      const x = padding.left + (i / (candles.length - 1 || 1)) * chartW;
      const yOpen = padding.top + (1 - (c.open - minPrice) / priceRange) * chartH;
      const yClose = padding.top + (1 - (c.close - minPrice) / priceRange) * chartH;
      const yHigh = padding.top + (1 - (c.high - minPrice) / priceRange) * chartH;
      const yLow = padding.top + (1 - (c.low - minPrice) / priceRange) * chartH;
      const isUp = c.close >= c.open;

      return {
        x,
        yHigh,
        yLow,
        yTop: Math.min(yOpen, yClose),
        bodyHeight: Math.max(1.5, Math.abs(yClose - yOpen)),
        isUp,
        close: c.close
      };
    });

    return {
      width,
      height,
      padding,
      points,
      minPrice,
      maxPrice,
      candleWidth
    };
  }, [candles]);

  if (!symbol) return null;

  return (
    <>
      {/* Backdrop */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        onClick={onClose}
        className="fixed inset-0 bg-black/70 z-40 transition-opacity"
      />

      {/* Slide-over Drawer */}
      <motion.aside
        initial={{ x: "100%" }}
        animate={{ x: 0 }}
        exit={{ x: "100%" }}
        transition={{ type: "spring", stiffness: 300, damping: 30 }}
        className="fixed top-0 right-0 h-full w-[480px] max-w-full bg-[#06090f] border-l border-white/[0.1] z-50 shadow-[-20px_0_60px_rgba(0,0,0,0.85)] flex flex-col font-sans overflow-hidden"
      >
        {/* Drawer Header */}
        <div className="flex items-center justify-between p-5 border-b border-white/[0.08] bg-[#080c14]/90">
          <div className="flex items-center space-x-3">
            <span className="w-2.5 h-2.5 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.8)] animate-pulse" />
            <div>
              <div className="flex items-center space-x-2">
                <h2 className="text-lg font-black text-white font-mono tracking-tight">{symbol}</h2>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-mono font-semibold bg-white/[0.05] border border-white/[0.08] text-slate-300">
                  Quick Inspect
                </span>
              </div>
              <p className="text-xs text-slate-400 font-mono truncate max-w-[260px] mt-0.5">
                {memo?.company_name || "Deterministic Research Snapshot"}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors"
            title="Close Drawer (Esc)"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Drawer Content Scrollable Area */}
        <div className="flex-1 overflow-y-auto p-5 space-y-5">
          {loading ? (
            <div className="h-96 flex flex-col items-center justify-center space-y-3 text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-cyan-400" />
              <span className="text-xs font-mono">Synthesizing live factor memo...</span>
            </div>
          ) : error ? (
            <div className="p-4 bg-rose-950/40 border border-rose-500/40 rounded-xl text-rose-300 text-xs font-mono shadow-[0_4px_20px_rgba(244,63,94,0.15)]">
              <AlertTriangle className="w-4 h-4 mb-1 text-rose-400" />
              <span>{error}</span>
            </div>
          ) : memo ? (
            <>
              {/* Verdict Card & Radial Gauge */}
              <div className="bg-[#080c14]/80 border border-white/[0.08] rounded-2xl p-5 flex items-center justify-between shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
                <div className="space-y-1.5">
                  <div className="flex items-center space-x-1.5 text-xs font-mono text-cyan-400 font-semibold">
                    <Sparkles className="w-3.5 h-3.5" />
                    <span>Deterministic Verdict</span>
                  </div>
                  <div className="text-base font-black font-mono text-white tracking-tight">
                    {memo.verdict.replace(/_/g, " ")}
                  </div>
                  <div className="text-[11px] font-mono text-slate-400 tabular-nums">
                    Price: <strong className="text-white">₹{memo.key_metrics?.current_price?.toFixed(2) ?? "—"}</strong>
                    {memo.key_metrics?.roe_pct && (
                      <span className="ml-2">ROE: <strong className="text-emerald-400">{memo.key_metrics.roe_pct.toFixed(1)}%</strong></span>
                    )}
                  </div>
                </div>

                <div className="shrink-0">
                  <RadialConvictionGauge score={memo.institutional_conviction_score || 0} />
                </div>
              </div>

              {/* Mini Candlestick Chart (30 Days) */}
              <div className="bg-[#080c14]/80 border border-white/[0.08] rounded-2xl p-4 space-y-2.5 shadow-[0_8px_32px_rgba(0,0,0,0.5)]">
                <div className="flex items-center justify-between text-xs font-mono text-slate-400">
                  <span className="font-semibold text-slate-200">30-Session Price Action</span>
                  <span className="tabular-nums">High: ₹{chartGeometry?.maxPrice.toFixed(2)} | Low: ₹{chartGeometry?.minPrice.toFixed(2)}</span>
                </div>

                {chartGeometry ? (
                  <div className="w-full overflow-hidden flex justify-center pt-1">
                    <svg
                      width={chartGeometry.width}
                      height={chartGeometry.height}
                      className="overflow-visible"
                    >
                      {/* Grid lines */}
                      <line x1={0} y1={chartGeometry.padding.top} x2={chartGeometry.width - chartGeometry.padding.right} y2={chartGeometry.padding.top} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />
                      <line x1={0} y1={chartGeometry.height - chartGeometry.padding.bottom} x2={chartGeometry.width - chartGeometry.padding.right} y2={chartGeometry.height - chartGeometry.padding.bottom} stroke="rgba(255,255,255,0.05)" strokeDasharray="3 3" />

                      {/* Candlesticks */}
                      {chartGeometry.points.map((pt, i) => (
                        <g key={i}>
                          {/* Wick */}
                          <line
                            x1={pt.x}
                            y1={pt.yHigh}
                            x2={pt.x}
                            y2={pt.yLow}
                            stroke={pt.isUp ? "#10b981" : "#f43f5e"}
                            strokeWidth="1"
                          />
                          {/* Body */}
                          <rect
                            x={pt.x - chartGeometry.candleWidth / 2}
                            y={pt.yTop}
                            width={chartGeometry.candleWidth}
                            height={pt.bodyHeight}
                            fill={pt.isUp ? "#10b981" : "#f43f5e"}
                            rx="1"
                          />
                        </g>
                      ))}

                      {/* Latest price indicator */}
                      {chartGeometry.points.length > 0 && (
                        <text
                          x={chartGeometry.width - chartGeometry.padding.right + 4}
                          y={chartGeometry.points[chartGeometry.points.length - 1].yTop + 4}
                          fill="#06b6d4"
                          fontSize="10"
                          fontFamily="monospace"
                          fontWeight="bold"
                        >
                          ₹{chartGeometry.points[chartGeometry.points.length - 1].close.toFixed(0)}
                        </text>
                      )}
                    </svg>
                  </div>
                ) : (
                  <div className="h-28 flex items-center justify-center text-xs text-slate-500 font-mono">
                    No recent candlestick bars available.
                  </div>
                )}
              </div>

              {/* 4-point Red Flag Health Checklist */}
              <div className="space-y-2.5">
                <div className="flex items-center justify-between text-xs font-mono">
                  <span className="font-bold text-slate-200 flex items-center space-x-2">
                    <ShieldCheck className="w-4 h-4 text-emerald-400" />
                    <span>Prudence Diagnostics (Health Checklist)</span>
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2.5">
                  {memo.health_checklist?.map((item) => {
                    const isPass = item.status === "PASS";
                    const isCaution = item.status === "CAUTION";
                    return (
                      <div
                        key={item.id}
                        className={`p-3 rounded-xl border font-mono text-[11px] ${
                          isPass
                            ? "bg-emerald-500/10 border-emerald-500/25 text-slate-300"
                            : isCaution
                            ? "bg-amber-500/10 border-amber-500/25 text-slate-300"
                            : "bg-rose-500/10 border-rose-500/25 text-slate-300"
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1.5">
                          <span className="font-bold text-white truncate max-w-[120px]">{item.name}</span>
                          <span
                            className={`text-[9px] font-bold px-2 py-0.5 rounded-full border ${
                              isPass
                                ? "bg-emerald-500/20 text-emerald-300 border-emerald-500/40"
                                : isCaution
                                ? "bg-amber-500/20 text-amber-300 border-amber-500/40"
                                : "bg-rose-500/20 text-rose-300 border-rose-500/40"
                            }`}
                          >
                            {item.status}
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-400 line-clamp-2 leading-relaxed">{item.detail}</p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Bull Case & Bear Risks */}
              <div className="space-y-3 font-mono text-[11px]">
                {/* Bull Case */}
                <div className="bg-[#06140f]/60 border-l-4 border-l-emerald-500 border border-white/[0.06] rounded-xl p-3.5 space-y-2 shadow-[0_4px_16px_rgba(16,185,129,0.06)]">
                  <div className="flex items-center space-x-2 text-emerald-400 font-bold text-xs">
                    <TrendingUp className="w-3.5 h-3.5" />
                    <span>Bull Growth Catalysts</span>
                  </div>
                  <ul className="space-y-1.5 text-slate-300">
                    {memo.bull_case?.slice(0, 2).map((b, idx) => (
                      <li key={idx} className="flex items-start space-x-2 leading-relaxed">
                        <span className="text-emerald-400 font-bold">›</span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Bear Risks */}
                <div className="bg-[#16080c]/60 border-l-4 border-l-rose-500 border border-white/[0.06] rounded-xl p-3.5 space-y-2 shadow-[0_4px_16px_rgba(244,63,94,0.06)]">
                  <div className="flex items-center space-x-2 text-rose-400 font-bold text-xs">
                    <TrendingDown className="w-3.5 h-3.5" />
                    <span>Bear Headwinds &amp; Tail Risks</span>
                  </div>
                  <ul className="space-y-1.5 text-slate-300">
                    {memo.bear_case?.slice(0, 2).map((b, idx) => (
                      <li key={idx} className="flex items-start space-x-2 leading-relaxed">
                        <span className="text-rose-400 font-bold">›</span>
                        <span>{b}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </>
          ) : null}
        </div>

        {/* Drawer Footer with Full Tearsheet Link */}
        <div className="p-4 border-t border-white/[0.08] bg-[#080c14]/90">
          <Link
            href={`/stocks/${symbol}`}
            className="w-full flex items-center justify-center space-x-2 py-3 px-4 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 text-white font-mono font-bold text-xs uppercase tracking-wider shadow-[0_0_20px_rgba(6,182,212,0.3)] transition-all"
          >
            <span>Open Full Tearsheet</span>
            <ExternalLink className="w-4 h-4" />
          </Link>
        </div>
      </motion.aside>
    </>
  );
}
