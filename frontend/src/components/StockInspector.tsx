"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  ExternalLink,
  PanelRightClose,
  BrainCircuit,
  Loader2,
  FileText,
  Newspaper,
} from "lucide-react";
import dynamic from "next/dynamic";
import {
  apiFetch,
  requestLifecycle,
  ScreenerCandidate,
  CandleData,
  ForecastData,
  InvestmentMemo,
  NewsArticle,
  NewsResponse,
  VerdictType,
} from "@/lib/api";

const StockChart = dynamic(() => import("./StockChart"), {
  ssr: false,
  loading: () => (
    <div className="h-[280px] w-full flex items-center justify-center bg-[#050811] rounded-xl border border-white/[0.06] text-xs font-mono text-slate-500">
      Loading chart engine...
    </div>
  ),
});
import { FactorPentagonRadar } from "./FactorPentagonRadar";
import { RiskRewardVectorBar } from "./RiskRewardVectorBar";
import { RadialConvictionGauge } from "./RadialConvictionGauge";
import InvestmentMemoCard from "./InvestmentMemoCard";
import NewsImpactCard from "./NewsImpactCard";

interface StockInspectorProps {
  symbol: string | null;
  activeCandidate?: ScreenerCandidate | null;
  onClose?: () => void;
  onOpenCopilot?: (symbol: string) => void;
}

const VERDICT_CONFIG: Record<
  VerdictType,
  { label: string; badge: string; horizonLabel: string }
> = {
  STRONG_BUY_COMPOUNDER: {
    label: "STRONG BUY",
    badge: "bg-emerald-950/80 border-emerald-500/50 text-emerald-300 shadow-[0_0_12px_rgba(16,185,129,0.2)]",
    horizonLabel: "12–24 Months",
  },
  TACTICAL_SWING_LONG: {
    label: "SWING LONG",
    badge: "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 shadow-[0_0_12px_rgba(6,182,212,0.2)]",
    horizonLabel: "2–8 Weeks",
  },
  HOLD_FAIRLY_VALUED: {
    label: "HOLD",
    badge: "bg-amber-950/80 border-amber-500/50 text-amber-300 shadow-[0_0_12px_rgba(245,158,11,0.15)]",
    horizonLabel: "3–6 Months",
  },
  AVOID_CAPITAL_PRESERVATION: {
    label: "AVOID",
    badge: "bg-rose-950/80 border-rose-500/50 text-rose-300 shadow-[0_0_12px_rgba(239,68,68,0.2)]",
    horizonLabel: "Capital Preservation",
  },
};

const DEFAULT_VERDICT_CFG = VERDICT_CONFIG["HOLD_FAIRLY_VALUED"];

export default function StockInspector({
  symbol,
  activeCandidate,
  onClose,
  onOpenCopilot,
}: StockInspectorProps) {
  const [candles, setCandles] = useState<CandleData[]>([]);
  const [forecast, setForecast] = useState<ForecastData | null>(null);
  const [memo, setMemo] = useState<InvestmentMemo | null>(null);
  const [news, setNews] = useState<NewsArticle[]>([]);
  const [isSyncing, setIsSyncing] = useState<boolean>(false);
  const [inspectorTab, setInspectorTab] = useState<"thesis" | "news">("thesis");

  // Load bundle with monotonic lifecycle cancellation
  useEffect(() => {
    if (!symbol) {
      setCandles([]);
      setForecast(null);
      setMemo(null);
      setNews([]);
      setIsSyncing(false);
      return;
    }

    const { signal, generation } = requestLifecycle.prepareRequest(`inspector-${symbol}`);
    setIsSyncing(true);

    Promise.allSettled([
      apiFetch<CandleData[]>(`/stocks/${symbol}/history`, { signal, useCache: true }),
      apiFetch<ForecastData>(`/stocks/${symbol}/forecast`, { signal, useCache: true }),
      apiFetch<InvestmentMemo>(`/stocks/${symbol}/memo`, { signal, useCache: true }),
      apiFetch<NewsResponse>(`/stocks/${symbol}/news`, { signal, useCache: true }),
    ]).then(([candlesRes, forecastRes, memoRes, newsRes]) => {
      if (!requestLifecycle.isLatest(`inspector-${symbol}`, generation)) {
        return; // Stale request, discarded
      }

      setCandles(candlesRes.status === "fulfilled" ? candlesRes.value : []);
      setForecast(forecastRes.status === "fulfilled" ? forecastRes.value : null);
      setMemo(memoRes.status === "fulfilled" ? memoRes.value : null);
      setNews(newsRes.status === "fulfilled" ? newsRes.value.articles || [] : []);
      setIsSyncing(false);
    });

    return () => {
      requestLifecycle.cleanup(`inspector-${symbol}`);
    };
  }, [symbol]);

  if (!symbol) {
    return (
      <div className="flex-1 flex items-center justify-center p-8 text-center text-slate-500 font-mono text-xs">
        Select an equity from the screener to view deep quantitative inspection.
      </div>
    );
  }

  const currentPrice =
    activeCandidate?.close || memo?.key_metrics?.current_price || 0;
  const sma200 = activeCandidate?.sma_200 || memo?.key_metrics?.sma_200 || null;
  const smaDist =
    sma200 && currentPrice ? ((currentPrice - sma200) / sma200) * 100 : null;

  // Active verdict
  const activeVerdict: VerdictType =
    memo?.verdict ||
    (activeCandidate?.composite_score && activeCandidate.composite_score >= 80
      ? "STRONG_BUY_COMPOUNDER"
      : activeCandidate?.composite_score && activeCandidate.composite_score >= 60
      ? "TACTICAL_SWING_LONG"
      : activeCandidate?.composite_score && activeCandidate.composite_score >= 40
      ? "HOLD_FAIRLY_VALUED"
      : "AVOID_CAPITAL_PRESERVATION");

  const verdictCfg = VERDICT_CONFIG[activeVerdict] || DEFAULT_VERDICT_CFG;

  // Forecast bounds for RiskRewardVectorBar
  const lastProjection =
    forecast?.projections?.[forecast.projections.length - 1];
  const hasValidForecast = Boolean(
    lastProjection &&
      typeof lastProjection.lower_95 === "number" &&
      typeof lastProjection.upper_80 === "number" &&
      currentPrice > 0
  );
  const forecastLower95 = hasValidForecast ? lastProjection!.lower_95 : null;
  const forecastUpper80 = hasValidForecast ? lastProjection!.upper_80 : null;

  // Factor Pentagon metrics
  const factorRoe = activeCandidate?.roe_pct ?? memo?.key_metrics?.roe_pct ?? null;
  const factorDe =
    activeCandidate?.debt_to_equity ?? memo?.key_metrics?.debt_to_equity ?? null;
  const factorOpm = activeCandidate?.opm_pct ?? memo?.key_metrics?.opm_pct ?? null;
  const factorMom =
    activeCandidate?.excess_ret_20d !== null &&
    activeCandidate?.excess_ret_20d !== undefined
      ? activeCandidate.excess_ret_20d * 100
      : null;
  const factorConv =
    memo?.institutional_conviction_score ??
    activeCandidate?.composite_score ??
    null;

  return (
    <div className="flex-1 flex flex-col h-full overflow-hidden bg-[#030508] border-l border-white/[0.06] text-slate-100 select-none">
      {/* 1. Header Toolbar */}
      <div className="shrink-0 border-b border-white/[0.06] px-4 py-3 flex items-center justify-between gap-3 bg-[#030508]/95 backdrop-blur-sm">
        <div className="flex items-center gap-3 min-w-0">
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold font-mono tracking-tight text-white">
                {symbol}
              </h2>
              {isSyncing && (
                <Loader2 className="w-3.5 h-3.5 animate-spin text-cyan-400" />
              )}
              {activeCandidate?.sector && (
                <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-slate-900 border border-white/[0.08] text-slate-400">
                  {activeCandidate.sector}
                </span>
              )}
            </div>
            <div className="text-xs text-slate-400 truncate max-w-xs">
              {activeCandidate?.company_name || memo?.company_name || symbol}
            </div>
          </div>
        </div>

        {/* Right Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {/* Verdict Badge */}
          <span
            className={`px-2.5 py-1 rounded-full border text-[10px] font-mono font-bold tracking-wider ${verdictCfg.badge}`}
          >
            {verdictCfg.label}
          </span>

          {/* Copilot Committee Trigger */}
          {onOpenCopilot && (
            <button
              onClick={() => onOpenCopilot(symbol)}
              title="Launch Quant Copilot Committee"
              className="flex items-center gap-1 px-2.5 py-1 text-xs font-mono text-cyan-300 bg-cyan-950/60 hover:bg-cyan-900/80 border border-cyan-800/60 rounded-md transition-colors"
            >
              <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
              <span className="hidden sm:inline">Copilot</span>
            </button>
          )}

          {/* Full Tearsheet Link */}
          <Link
            href={`/stocks/${symbol}`}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-mono text-slate-300 bg-slate-900/60 hover:bg-slate-800/80 border border-white/[0.08] hover:border-cyan-500/40 rounded-md transition-colors"
            title="Open Deep Institutional Tearsheet"
          >
            <span>Tearsheet</span>
            <ExternalLink className="w-3 h-3 text-cyan-400" />
          </Link>

          {/* Close Panel Button */}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded text-slate-500 hover:text-slate-300 hover:bg-slate-800/60 transition-colors"
              title="Collapse Inspector"
            >
              <PanelRightClose className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* 2. Secondary Tab Switcher */}
      <div className="shrink-0 border-b border-white/[0.04] px-4 py-1.5 flex items-center justify-between bg-[#020406]">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setInspectorTab("thesis")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-mono transition-colors ${
              inspectorTab === "thesis"
                ? "bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 font-semibold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            <span>Thesis & Valuation</span>
          </button>

          <button
            onClick={() => setInspectorTab("news")}
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-mono transition-colors ${
              inspectorTab === "news"
                ? "bg-cyan-950/70 text-cyan-300 border border-cyan-500/30 font-semibold"
                : "text-slate-400 hover:text-slate-200"
            }`}
          >
            <Newspaper className="w-3.5 h-3.5" />
            <span>News Wire & Disclosures ({news.length})</span>
          </button>
        </div>

        {/* Current Price Banner */}
        <div className="flex items-center gap-2 text-xs font-mono">
          <span className="text-slate-400">Price:</span>
          <strong className="text-white text-sm">
            {currentPrice ? `₹${currentPrice.toFixed(2)}` : "—"}
          </strong>
          {smaDist !== null && (
            <span
              className={`text-[10px] px-1.5 py-0.5 rounded ${
                smaDist >= 0
                  ? "bg-emerald-950/60 text-emerald-400 border border-emerald-500/20"
                  : "bg-rose-950/60 text-rose-400 border border-rose-500/20"
              }`}
            >
              {smaDist >= 0 ? "+" : ""}
              {smaDist.toFixed(1)}% vs 200 SMA
            </span>
          )}
        </div>
      </div>

      {/* 3. Tab Body Container */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {inspectorTab === "thesis" ? (
          <>
            {/* Above-the-Fold 2-Column Bento Grid: Chart (60%) + Multi-Horizon Consensus (40%) */}
            <div className="grid grid-cols-1 xl:grid-cols-12 gap-4">
              {/* Left Column (xl:col-span-7): Price Chart */}
              <div className="xl:col-span-7 rounded-xl border border-white/[0.06] bg-[#050811] p-3 shadow-md flex flex-col justify-between">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-xs font-mono font-semibold text-slate-300 uppercase tracking-wide">
                    Historical Price & 20D Forecast Cone
                  </span>
                  <span className="text-[10px] font-mono text-slate-500">
                    {candles.length} Candles Loaded
                  </span>
                </div>
                <StockChart
                  symbol={symbol}
                  data={candles}
                  sma200={sma200}
                  forecast={forecast}
                  compact={true}
                  height={280}
                />
              </div>

              {/* Right Column (xl:col-span-5): Multi-Horizon Factor Consensus & Rebalance Attribution */}
              <div className="xl:col-span-5 rounded-xl border border-white/[0.08] bg-[#050811] p-4 shadow-md flex flex-col justify-between space-y-3">
                <div>
                  <div className="flex items-center justify-between border-b border-white/[0.06] pb-2">
                    <div className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-cyan-400 shadow-[0_0_8px_rgba(6,182,212,0.8)]" />
                      <span className="text-xs font-mono font-semibold text-slate-200 uppercase tracking-wide">
                        Multi-Horizon Consensus
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <span className="text-[10px] font-mono text-slate-400">Blended:</span>
                      <span className="text-xs font-mono font-bold text-cyan-300 px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/40">
                        {activeCandidate?.blended_score !== undefined && activeCandidate?.blended_score !== null
                          ? `${activeCandidate.blended_score.toFixed(1)}/100`
                          : activeCandidate?.composite_score !== undefined && activeCandidate?.composite_score !== null
                          ? `${activeCandidate.composite_score.toFixed(1)}/100`
                          : "—"}
                      </span>
                    </div>
                  </div>

                  {/* Horizon Attribution Breakdown Bars */}
                  <div className="space-y-2.5 pt-2.5">
                    {/* 20D Tactical Horizon */}
                    <div>
                      <div className="flex items-center justify-between text-xs font-mono mb-1">
                        <span className="text-slate-300 flex items-center gap-1.5">
                          <span className="px-1.5 py-0.5 rounded text-[9px] bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-bold">20D Tactical</span>
                          <span className="text-slate-500">(Weight: 62.5%)</span>
                        </span>
                        <span className="text-cyan-300 font-semibold tabular-nums">
                          Score: {activeCandidate?.score_20d !== undefined && activeCandidate.score_20d !== null ? `${activeCandidate.score_20d.toFixed(1)}` : "—"}
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden border border-white/[0.04]">
                        <div
                          className="h-full bg-gradient-to-r from-cyan-600 to-cyan-400 rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(100, Math.max(0, activeCandidate?.score_20d ?? 50))}%` }}
                        />
                      </div>
                    </div>

                    {/* 60D Trend Drift Horizon */}
                    <div>
                      <div className="flex items-center justify-between text-xs font-mono mb-1">
                        <span className="text-slate-300 flex items-center gap-1.5">
                          <span className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-950/80 text-emerald-300 border border-emerald-500/40 font-bold">60D Trend</span>
                          <span className="text-slate-500">(Weight: 37.5%)</span>
                        </span>
                        <span className="text-emerald-300 font-semibold tabular-nums">
                          Score: {activeCandidate?.score_60d !== undefined && activeCandidate.score_60d !== null ? `${activeCandidate.score_60d.toFixed(1)}` : "—"}
                        </span>
                      </div>
                      <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden border border-white/[0.04]">
                        <div
                          className="h-full bg-gradient-to-r from-emerald-600 to-emerald-400 rounded-full transition-all duration-500"
                          style={{ width: `${Math.min(100, Math.max(0, activeCandidate?.score_60d ?? 50))}%` }}
                        />
                      </div>
                    </div>

                    {/* 5D Swing Horizon: Disarmed Noise Gate */}
                    <div className="pt-1 flex items-center justify-between text-[11px] font-mono text-slate-400 bg-slate-900/40 p-2 rounded-lg border border-white/[0.04]">
                      <div className="flex items-center gap-1.5">
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-rose-950/60 text-rose-400 border border-rose-500/30 font-bold">5D Swing</span>
                        <span>Status:</span>
                      </div>
                      <span className="text-rose-400/90 font-medium">
                        Disarmed (Noise Filter)
                      </span>
                    </div>
                  </div>
                </div>

                {/* Portfolio Rebalance Target & Projected Delta */}
                <div className="pt-2 border-t border-white/[0.04] flex items-center justify-between text-xs font-mono">
                  <span className="text-slate-400">Target Allocation:</span>
                  {activeCandidate?.target_allocation_pct !== undefined && activeCandidate.target_allocation_pct !== null && activeCandidate.target_allocation_pct > 0 ? (
                    <span className="px-2 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-500/50 shadow-[0_0_10px_rgba(16,185,129,0.3)]">
                      {activeCandidate.target_allocation_pct.toFixed(2)}% (Maintain)
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 rounded text-slate-500 bg-slate-900 border border-white/[0.06]">
                      Unallocated (Cash Guard)
                    </span>
                  )}
                </div>
              </div>
            </div>

            {/* Row 2: Factor Radar & Risk/Reward Gauge */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Factor Radar Card */}
              <div className="rounded-xl border border-white/[0.06] bg-[#050811] p-3 flex flex-col items-center justify-center">
                <span className="text-xs font-mono font-semibold text-slate-300 mb-2 self-start uppercase tracking-wide">
                  Quantitative Factor Pentagon
                </span>
                <FactorPentagonRadar
                  roe={factorRoe}
                  debtToEquity={factorDe}
                  opm={factorOpm}
                  momentum20d={factorMom}
                  conviction={factorConv}
                />
              </div>

              {/* Conviction Gauge and Risk/Reward Vector Card */}
              <div className="rounded-xl border border-white/[0.06] bg-[#050811] p-4 flex flex-col justify-between">
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-mono font-semibold text-slate-300 uppercase tracking-wide">
                      Institutional Conviction
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">
                      Target: {verdictCfg.horizonLabel}
                    </span>
                  </div>

                  <div className="flex items-center justify-center py-2">
                    <RadialConvictionGauge score={factorConv} />
                  </div>
                </div>

                {/* Risk Reward Vector Bar */}
                <div className="mt-4 pt-3 border-t border-white/[0.04]">
                  <span className="text-[11px] font-mono text-slate-400 block mb-1">
                    Statistical Bounds (95% CI vs 80% CI)
                  </span>
                  {hasValidForecast && forecastLower95 && forecastUpper80 ? (
                    <RiskRewardVectorBar
                      currentPrice={currentPrice}
                      stopPrice={forecastLower95}
                      targetPrice={forecastUpper80}
                    />
                  ) : (
                    <div className="text-xs font-mono text-slate-500 py-1 italic">
                      Forecast bounds pending active model evaluation
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Row 3: Investment Memo Component */}
            <div className="rounded-xl border border-white/[0.06] bg-[#050811] p-4 shadow-md">
              <InvestmentMemoCard symbol={symbol} initialMemo={memo} />
            </div>
          </>
        ) : (
          /* News & Exchange Disclosures Tab */
          <div className="space-y-3">
            <NewsImpactCard symbol={symbol} articles={news} loading={isSyncing} />
          </div>
        )}
      </div>
    </div>
  );
}
