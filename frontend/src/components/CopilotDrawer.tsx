"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BrainCircuit,
  X,
  Send,
  Square,
  Sparkles,
  TrendingUp,
  ShieldAlert,
  Gavel,
  ChevronDown,
  ChevronRight,
  Loader2,
  CheckCircle2,
  Activity,
  Layers,
  Maximize2,
  Minimize2,
  Cpu,
  BarChart3
} from "lucide-react";
import { RobustSSEParser, ServerSentEvent } from "@/lib/sseParser";

export interface MLForecastData {
  symbol?: string;
  champion_model?: string;
  overall_rank_ic?: number;
  conviction_score?: number;
  conviction_tier?: string;
  forecasts?: Record<string, {
    expected_excess_bps?: number;
    expected_return_pct?: number;
    model?: string;
    rank_ic?: number;
  }>;
  feature_attributions?: Array<{
    feature: string;
    weight_pct: number;
    signal: string;
  }>;
  error?: string;
}

interface CopilotDrawerProps {
  activeSymbol?: string;
  activePrice?: number;
  activeVerdict?: string;
  isOpen?: boolean;
  onClose?: () => void;
  onToggle?: () => void;
  showFloatingTrigger?: boolean;
}

interface DeliberationState {
  stage: "idle" | "telemetry" | "conversational" | "bull_analyst" | "bear_analyst" | "judge_synthesis" | "complete" | "error";
  statusText: string;
  progressPct: number;
  conversationalText?: string;
  bullText: string;
  bearText: string;
  judgeText: string;
  decisionResult?: {
    symbol: string;
    verdict: string;
    conviction_score: number;
    entry_price: number;
    target_price: number;
    stop_loss: number;
    ml_forecast?: MLForecastData;
  };
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "/api/v1";

export function FormattedMarkdown({
  content,
  role,
}: {
  content: string;
  role?: "bull" | "bear" | "judge" | "general";
}) {
  if (!content) return null;

  const lines = content.split("\n");

  const parseInline = (text: string) => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let keyIdx = 0;
    const tokenRegex = /(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/;

    while (remaining.length > 0) {
      const match = remaining.match(tokenRegex);
      if (!match || match.index === undefined) {
        parts.push(remaining);
        break;
      }

      if (match.index > 0) {
        parts.push(remaining.substring(0, match.index));
      }

      const rawToken = match[0];
      if (rawToken.startsWith("**") && rawToken.endsWith("**")) {
        parts.push(
          <strong key={keyIdx++} className="font-semibold text-slate-100">
            {rawToken.slice(2, -2)}
          </strong>
        );
      } else if (rawToken.startsWith("`") && rawToken.endsWith("`")) {
        parts.push(
          <code
            key={keyIdx++}
            className="px-1.5 py-0.5 rounded font-mono text-[11px] bg-slate-900 border border-slate-700/60 text-cyan-300"
          >
            {rawToken.slice(1, -1)}
          </code>
        );
      } else if (rawToken.startsWith("*") && rawToken.endsWith("*")) {
        parts.push(
          <em key={keyIdx++} className="italic text-slate-300">
            {rawToken.slice(1, -1)}
          </em>
        );
      }

      remaining = remaining.substring(match.index + rawToken.length);
    }

    return parts;
  };

  return (
    <div className="space-y-1.5 text-xs leading-relaxed font-sans text-slate-200">
      {lines.map((line, idx) => {
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={idx} className="h-1" />;
        }

        // Horizontal rule
        if (trimmed === "---" || trimmed === "***") {
          return <hr key={idx} className="border-t border-white/[0.08] my-2" />;
        }

        // H3 Header (### Title)
        if (trimmed.startsWith("### ")) {
          const headerText = trimmed.replace(/^###\s+/, "");
          const headerBorder =
            role === "bull"
              ? "border-emerald-500/40 text-emerald-300"
              : role === "bear"
              ? "border-rose-500/40 text-rose-300"
              : role === "judge"
              ? "border-cyan-500/40 text-cyan-200"
              : "border-white/[0.1] text-white";
          return (
            <div
              key={idx}
              className={`font-mono font-bold text-xs pt-1.5 pb-1 border-b ${headerBorder} tracking-wide uppercase flex items-center gap-1.5 mt-2`}
            >
              <span>{headerText}</span>
            </div>
          );
        }

        // H2 Header (## Title)
        if (trimmed.startsWith("## ")) {
          const headerText = trimmed.replace(/^##\s+/, "");
          return (
            <div
              key={idx}
              className="font-mono font-bold text-sm pt-2 pb-1 border-b border-white/[0.1] text-white tracking-wide mt-2"
            >
              {headerText}
            </div>
          );
        }

        // Numbered list item: e.g. "1. **Moat:**" or "1. Item"
        const numMatch = trimmed.match(/^(\d+)\.\s+(.*)/);
        if (numMatch) {
          const num = numMatch[1];
          const text = numMatch[2];
          return (
            <div key={idx} className="flex items-start gap-2 pt-1">
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-900 border border-slate-800 text-slate-400 shrink-0 font-bold">
                {num}
              </span>
              <div className="flex-1 min-w-0">{parseInline(text)}</div>
            </div>
          );
        }

        // Sub-bullet (indented): "   - ..." or "  - ..."
        if (
          line.startsWith("   - ") ||
          line.startsWith("  - ") ||
          line.startsWith("    - ")
        ) {
          const text = trimmed.replace(/^-\s+/, "");
          return (
            <div key={idx} className="flex items-start gap-2 pl-5 text-slate-300">
              <span className="w-1 h-1 rounded-full bg-slate-500 shrink-0 mt-2" />
              <div className="flex-1 min-w-0">{parseInline(text)}</div>
            </div>
          );
        }

        // Top bullet item: "- ..." or "* ..."
        if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
          const text = trimmed.substring(2);
          const dotColor =
            role === "bull"
              ? "bg-emerald-400"
              : role === "bear"
              ? "bg-rose-400"
              : role === "judge"
              ? "bg-cyan-400"
              : "bg-slate-400";
          return (
            <div key={idx} className="flex items-start gap-2 pl-2">
              <span
                className={`w-1.5 h-1.5 rounded-full ${dotColor} shrink-0 mt-1.5 opacity-80`}
              />
              <div className="flex-1 min-w-0">{parseInline(text)}</div>
            </div>
          );
        }

        // Standard paragraph line
        return (
          <p key={idx} className="text-slate-200">
            {parseInline(line)}
          </p>
        );
      })}
    </div>
  );
}

export default function CopilotDrawer({
  activeSymbol,
  activePrice,
  activeVerdict,
  isOpen: controlledIsOpen,
  onClose,
  onToggle,
  showFloatingTrigger = false,
}: CopilotDrawerProps) {
  const [internalIsOpen, setInternalIsOpen] = useState(false);
  const isOpen = controlledIsOpen !== undefined ? controlledIsOpen : internalIsOpen;

  const [prompt, setPrompt] = useState("");
  const [isExpanded, setIsExpanded] = useState(false);
  const [expandedSections, setExpandedSections] = useState<{ bull: boolean; bear: boolean; judge: boolean }>({
    bull: true,
    bear: true,
    judge: true
  });

  const [state, setState] = useState<DeliberationState>({
    stage: "idle",
    statusText: "Ready for multi-agent quantitative deliberation.",
    progressPct: 0,
    bullText: "",
    bearText: "",
    judgeText: ""
  });

  const [mlForecast, setMlForecast] = useState<MLForecastData | null>(null);
  const [mlExpanded, setMlExpanded] = useState(true);

  // Eagerly fetch ML Alpha Forecast when context symbol changes and drawer is open
  useEffect(() => {
    if (!activeSymbol || !isOpen) return;
    let isCancelled = false;
    const fetchMlForecast = async () => {
      try {
        const res = await fetch(`${API_BASE}/ml/forecast/${encodeURIComponent(activeSymbol)}`);
        if (res.ok) {
          const data = await res.json();
          if (!isCancelled && !data.error) {
            setMlForecast(data);
          }
        }
      } catch {
        // non-blocking
      }
    };
    fetchMlForecast();
    return () => {
      isCancelled = true;
    };
  }, [activeSymbol, isOpen]);

  const [bullElapsed, setBullElapsed] = useState("00:00");
  const [bearElapsed, setBearElapsed] = useState("00:00");
  const bullStartTimeRef = useRef<number | null>(null);
  const bearStartTimeRef = useRef<number | null>(null);

  const formatSeconds = (sec: number) => {
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return `${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
  };

  const abortControllerRef = useRef<AbortController | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);

  // Toggle open state
  const handleToggle = useCallback(() => {
    if (onToggle) {
      onToggle();
    } else {
      setInternalIsOpen(prev => !prev);
    }
  }, [onToggle]);

  const handleClose = useCallback(() => {
    if (onClose) {
      onClose();
    } else {
      setInternalIsOpen(false);
    }
  }, [onClose]);

  // Global Keyboard Shortcut: ⌘J / Ctrl+J
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        handleToggle();
      } else if (e.key === "Escape" && isOpen) {
        handleClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleToggle, handleClose, isOpen]);

  const stopDeliberation = useCallback(() => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    setState(prev => ({
      ...prev,
      stage: prev.stage === "idle" || prev.stage === "complete" ? prev.stage : "complete",
      statusText: "Deliberation halted by user."
    }));
  }, []);

  // Start Multi-Agent Deliberation Stream
  const runDeliberation = async (customPrompt?: string) => {
    const userInstruction = customPrompt || prompt || "Debate Bull vs Bear Thesis";
    const targetSymbol = activeSymbol || "NIFTY 50";
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setState({
      stage: "telemetry",
      statusText: activeSymbol 
        ? `Initializing deliberation engine for ${activeSymbol}...`
        : "Initializing quantitative deliberation engine...",
      progressPct: 5,
      conversationalText: "",
      bullText: "",
      bearText: "",
      judgeText: ""
    });

    try {
      const response = await fetch(`${API_BASE}/copilot/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
          "ngrok-skip-browser-warning": "true"
        },
        body: JSON.stringify({
          symbol: targetSymbol,
          prompt: userInstruction
        }),
        signal: controller.signal
      });

      if (!response.ok || !response.body) {
        throw new Error(`Failed to stream from copilot: HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      const parser = new RobustSSEParser();

      bullStartTimeRef.current = null;
      bearStartTimeRef.current = null;
      setBullElapsed("00:00");
      setBearElapsed("00:00");

      const handleParsedEvent = (ev: ServerSentEvent) => {
        try {
          const data = JSON.parse(ev.data);

          if (data.stage === "bull_analyst") {
            if (!bullStartTimeRef.current) bullStartTimeRef.current = Date.now();
            setBullElapsed(formatSeconds((Date.now() - bullStartTimeRef.current) / 1000));
          } else if (data.stage === "bear_analyst") {
            if (!bearStartTimeRef.current) bearStartTimeRef.current = Date.now();
            setBearElapsed(formatSeconds((Date.now() - bearStartTimeRef.current) / 1000));
          }

          setState(prev => {
            const next = { ...prev };
            if (data.status) next.statusText = data.status;
            if (data.progress !== undefined) next.progressPct = data.progress;

            if (data.stage === "conversational") {
              next.stage = "conversational";
              if (data.delta) next.conversationalText = (prev.conversationalText || "") + data.delta;
            } else if (data.stage === "bull_analyst") {
              next.stage = "bull_analyst";
              if (data.delta) next.bullText = prev.bullText + data.delta;
            } else if (data.stage === "bear_analyst") {
              next.stage = "bear_analyst";
              if (data.delta) next.bearText = prev.bearText + data.delta;
            } else if (data.stage === "judge_synthesis") {
              next.stage = "judge_synthesis";
              if (data.delta) next.judgeText = prev.judgeText + data.delta;
            } else if (data.stage === "complete") {
              next.stage = "complete";
              next.progressPct = 100;
              if (data.result) {
                next.decisionResult = data.result;
                if (data.result.ml_forecast && !data.result.ml_forecast.error) {
                  setMlForecast(data.result.ml_forecast);
                }
                if (data.result.bull_thesis) next.bullText = data.result.bull_thesis;
                if (data.result.bear_thesis) next.bearText = data.result.bear_thesis;
                if (data.result.judge_memo) next.judgeText = data.result.judge_memo;
                if (data.result.conversational_response) next.conversationalText = data.result.conversational_response;
              }
            }
            return next;
          });

          // Auto-scroll
          if (scrollContainerRef.current) {
            scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
          }
        } catch {
          // Ignore partial or non-JSON frames
        }
      };

      while (true) {
        const { value, done } = await reader.read();
        if (done) {
          parser.flush(handleParsedEvent);
          break;
        }
        const textChunk = decoder.decode(value, { stream: true });
        parser.feed(textChunk, handleParsedEvent);
      }
    } catch (err: unknown) {
      if ((err as Error)?.name === "AbortError") {
        return;
      }
      setState(prev => ({
        ...prev,
        stage: "error",
        statusText: `Deliberation interrupted: ${(err as Error)?.message || "Unknown error"}`
      }));
    } finally {
      abortControllerRef.current = null;
    }
  };

  const toggleSection = (section: "bull" | "bear" | "judge") => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  return (
    <>
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 1. FLOATING LAUNCH TRIGGER BUTTON (Optional, off by default)         */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {showFloatingTrigger && !isOpen && (
        <button
          onClick={handleToggle}
          title="Open Quant Copilot Multi-Agent Drawer (⌘J / Ctrl+J)"
          className="fixed bottom-4 right-4 z-40 flex items-center space-x-2.5 px-3.5 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800 text-slate-100 border border-cyan-500/30 hover:border-cyan-400 shadow-[0_4px_24px_rgba(6,182,212,0.18)] backdrop-blur-md transition-all font-mono text-xs group"
        >
          <div className="relative flex items-center justify-center">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping absolute" />
            <span className="w-2 h-2 rounded-full bg-emerald-500 relative" />
          </div>
          <BrainCircuit className="w-4 h-4 text-cyan-400 group-hover:rotate-12 transition-transform" />
          <span className="font-semibold tracking-tight text-white">Quant Copilot</span>
          <span className="px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700 text-[10px] text-slate-400">
            ⌘J
          </span>
        </button>
      )}

      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 2. SLIDING MULTI-AGENT COPILOT DRAWER                               */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      <AnimatePresence>
        {isOpen && (
          <>
            {/* Backdrop Overlay */}
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={handleClose}
              className="fixed inset-0 bg-black/60 backdrop-blur-[2px] z-50 lg:bg-black/40"
            />

            {/* Slide-in Drawer Container */}
            <motion.aside
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className={`fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-[#06090f]/95 border-l border-white/[0.1] shadow-[-20px_0_60px_rgba(0,0,0,0.85)] backdrop-blur-3xl ${
                isExpanded ? "w-full md:w-[720px]" : "w-full sm:w-[480px] lg:w-[520px]"
              }`}
            >
              {/* Header Bar */}
              <div className="h-14 px-5 border-b border-white/[0.08] flex items-center justify-between shrink-0 bg-[#080c14]/90 backdrop-blur-2xl">
                <div className="flex items-center space-x-3">
                  <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.2)]">
                    <BrainCircuit className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold font-mono text-white tracking-wider">
                        QUANT COPILOT
                      </span>
                      <span className="text-[10px] px-2 py-0.5 rounded-full font-mono bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-semibold shadow-[0_0_8px_rgba(6,182,212,0.2)]">
                        Multi-Agent Committee
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono block">
                      TradingAgents Architecture · Free Tier Engine
                    </span>
                  </div>
                </div>

                {/* Right controls */}
                <div className="flex items-center space-x-2">
                  <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    title={isExpanded ? "Restore width" : "Expand width"}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors hidden sm:block"
                  >
                    {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                  </button>
                  <button
                    onClick={handleClose}
                    title="Close Drawer (Esc)"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Context-Aware Active Instrument Banner */}
              <div className="px-5 py-2.5 bg-[#050810]/80 border-b border-white/[0.06] flex items-center justify-between font-mono text-xs shrink-0">
                <div className="flex items-center space-x-2.5">
                  <span className="text-slate-400 text-[11px] uppercase tracking-wider">Active Context:</span>
                  {activeSymbol ? (
                    <span className="text-white font-bold tracking-tight px-2 py-0.5 rounded-md bg-white/[0.06] border border-white/[0.1] shadow-sm">
                      {activeSymbol}
                    </span>
                  ) : (
                    <span className="text-slate-400 italic text-[11px]">Market Overview</span>
                  )}
                  {activePrice !== undefined ? (
                    <span className="text-slate-200 font-semibold tabular-nums">₹{activePrice.toFixed(2)}</span>
                  ) : activeSymbol ? (
                    <span className="text-slate-500 text-[11px] flex items-center space-x-1">
                      <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />
                      <span>Syncing...</span>
                    </span>
                  ) : null}
                </div>
                {activeVerdict ? (
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.2)]">
                    {activeVerdict.replace(/_/g, " ")}
                  </span>
                ) : (
                  <span className="text-[10px] px-2.5 py-0.5 rounded-full font-mono text-slate-400 border border-white/[0.08]">
                    {activeSymbol ? "Pending Verdict" : "NIFTY 50 Active"}
                  </span>
                )}
              </div>

              {/* Progress Indicator */}
              {state.stage !== "idle" && (
                <div className="w-full bg-[#050810] h-1 relative overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-emerald-400 shadow-[0_0_8px_rgba(6,182,212,0.8)]"
                    initial={{ width: "0%" }}
                    animate={{ width: `${state.progressPct}%` }}
                    transition={{ ease: "easeInOut", duration: 0.3 }}
                  />
                </div>
              )}

              {/* ───────────────────────────────────────────────────────────── */}
              {/* 3. MULTI-AGENT STAGE ACCORDION BODY                           */}
              {/* ───────────────────────────────────────────────────────────── */}
              <div
                ref={scrollContainerRef}
                className="flex-1 overflow-y-auto p-5 space-y-4 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent"
              >
                {/* Status Bar */}
                <div className="bg-[#050810]/70 border border-white/[0.06] rounded-xl p-3.5 flex items-center space-x-2.5 font-mono text-xs">
                  {state.stage === "complete" ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  ) : state.stage === "error" ? (
                    <ShieldAlert className="w-4 h-4 text-rose-400 shrink-0" />
                  ) : state.stage !== "idle" ? (
                    <Loader2 className="w-4 h-4 text-cyan-400 animate-spin shrink-0" />
                  ) : (
                    <Activity className="w-4 h-4 text-slate-500 shrink-0" />
                  )}
                  <span className="text-slate-300 flex-1 truncate">{state.statusText}</span>
                  <span className="text-[10px] text-cyan-400 font-semibold tabular-nums shrink-0">{state.progressPct}%</span>
                </div>

                {/* ───────────────────────────────────────────────────────────── */}
                {/* MACHINE LEARNING ALPHA FORECAST CARD                         */}
                {/* ───────────────────────────────────────────────────────────── */}
                {mlForecast && !mlForecast.error && (
                  <div className="border border-indigo-500/30 bg-gradient-to-br from-indigo-950/40 via-slate-900/70 to-slate-950/90 rounded-xl overflow-hidden shadow-lg backdrop-blur-sm">
                    <button
                      onClick={() => setMlExpanded(prev => !prev)}
                      className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-indigo-950/40 transition-colors font-mono text-xs border-b border-indigo-500/20"
                    >
                      <div className="flex items-center space-x-2">
                        {mlExpanded ? <ChevronDown className="w-3.5 h-3.5 text-indigo-400" /> : <ChevronRight className="w-3.5 h-3.5 text-indigo-400" />}
                        <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                        <span className="font-bold text-indigo-200">ML Multi-Horizon Alpha Forecast</span>
                        <span className="text-[10px] text-indigo-400/70 hidden sm:inline">
                          ({mlForecast.champion_model || "Champion Model"})
                        </span>
                      </div>
                      <div className="flex items-center space-x-1.5">
                        <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-indigo-950 text-indigo-300 border border-indigo-800">
                          Rank IC +{(mlForecast.overall_rank_ic ?? 0.035).toFixed(4)}
                        </span>
                        <span className={`text-[10px] px-2 py-0.5 rounded-full font-bold ${
                          mlForecast.conviction_tier === "STRONG_ALPHA"
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-800"
                            : mlForecast.conviction_tier === "MODERATE_ALPHA"
                            ? "bg-cyan-950 text-cyan-300 border border-cyan-800"
                            : mlForecast.conviction_tier === "NEUTRAL_ALPHA"
                            ? "bg-amber-950 text-amber-300 border border-amber-800"
                            : "bg-rose-950 text-rose-300 border border-rose-800"
                        }`}>
                          {mlForecast.conviction_tier?.replace(/_/g, " ") || "ALPHA"} ({mlForecast.conviction_score ?? 70}/100)
                        </span>
                      </div>
                    </button>

                    {mlExpanded && (
                      <div className="p-3.5 space-y-3 font-mono text-xs">
                        {/* Multi-Horizon Return Grid */}
                        <div className="grid grid-cols-3 gap-2">
                          {(["5D", "20D", "60D"] as const).map(horizon => {
                            const fc = mlForecast.forecasts?.[horizon];
                            if (!fc) return null;
                            const isPos = (fc.expected_return_pct ?? 0) >= 0;
                            return (
                              <div
                                key={horizon}
                                className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col items-center justify-between text-center relative overflow-hidden"
                              >
                                <div className="flex items-center justify-between w-full text-[10px] text-slate-400 mb-1">
                                  <span className="font-semibold text-slate-300">{horizon} Horizon</span>
                                  <span className="text-[9px] text-indigo-400/80">{fc.model}</span>
                                </div>
                                <div className={`text-sm font-bold my-0.5 ${isPos ? "text-emerald-400" : "text-rose-400"}`}>
                                  {isPos ? "+" : ""}{(fc.expected_return_pct ?? 0).toFixed(2)}%
                                </div>
                                <div className="text-[10px] text-slate-500">
                                  {isPos ? "+" : ""}{(fc.expected_excess_bps ?? 0).toFixed(1)} bps
                                </div>
                              </div>
                            );
                          })}
                        </div>

                        {/* Top Feature Attributions */}
                        {mlForecast.feature_attributions && mlForecast.feature_attributions.length > 0 && (
                          <div className="space-y-1.5 pt-1 border-t border-indigo-900/30">
                            <div className="flex items-center justify-between text-[10px] text-slate-400">
                              <span className="flex items-center space-x-1">
                                <BarChart3 className="w-3 h-3 text-indigo-400" />
                                <span>Primary Walk-Forward Factor Drivers</span>
                              </span>
                              <span className="text-[9px] text-slate-500">Normalized Weight</span>
                            </div>
                            <div className="space-y-1">
                              {mlForecast.feature_attributions.slice(0, 3).map((item, idx) => (
                                <div key={idx} className="flex items-center justify-between text-[11px] bg-slate-900/70 px-2 py-1 rounded border border-white/[0.04]">
                                  <span className="text-slate-300 capitalize">
                                    {item.feature.replace(/_/g, " ")}
                                  </span>
                                  <div className="flex items-center space-x-2">
                                    <div className="w-16 bg-slate-800 h-1.5 rounded-full overflow-hidden">
                                      <div
                                        className="bg-indigo-400 h-full rounded-full"
                                        style={{ width: `${Math.min(100, Math.max(5, item.weight_pct))}%` }}
                                      />
                                    </div>
                                    <span className="text-indigo-300 font-bold text-[10px] w-9 text-right">
                                      {item.weight_pct.toFixed(1)}%
                                    </span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* CONVERSATIONAL ASSISTANT GUIDANCE */}
                {state.conversationalText && (
                  <div className="border border-cyan-500/30 bg-slate-900/80 rounded-xl p-4 space-y-3 shadow-md animate-in fade-in duration-300">
                    <div className="flex items-center space-x-2 pb-2 border-b border-white/[0.08]">
                      <div className="w-6 h-6 rounded-md bg-cyan-950 flex items-center justify-center text-cyan-400">
                        <BrainCircuit className="w-3.5 h-3.5" />
                      </div>
                      <span className="font-bold text-xs text-white font-mono">
                        Quant Copilot · Verified Telemetry Context
                      </span>
                    </div>
                    <div className="text-xs text-slate-200 font-sans leading-relaxed">
                      <FormattedMarkdown content={state.conversationalText} role="general" />
                    </div>
                    <div className="pt-2 flex flex-wrap gap-1.5 border-t border-white/[0.06]">
                      <button
                        onClick={() => runDeliberation("Debate Bull vs Bear Thesis")}
                        className="px-2.5 py-1 rounded-lg bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-800/60 text-[10px] font-mono text-cyan-300 transition-colors flex items-center space-x-1"
                      >
                        <Sparkles className="w-3 h-3 text-cyan-400" />
                        <span>Launch 3-Agent Committee Debate</span>
                      </button>
                    </div>
                  </div>
                )}

                {/* STAGE 1: BULL ANALYST */}
                {!state.conversationalText && (state.bullText || state.stage === "bull_analyst" || state.stage === "bear_analyst" || state.stage === "judge_synthesis" || (state.stage === "complete" && !state.conversationalText)) && (
                  <div className="border border-emerald-500/20 bg-emerald-950/20 rounded-xl overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("bull")}
                      className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-emerald-950/40 transition-colors font-mono text-xs border-b border-emerald-500/10"
                    >
                      <div className="flex items-center space-x-2">
                        {expandedSections.bull ? <ChevronDown className="w-3.5 h-3.5 text-emerald-400" /> : <ChevronRight className="w-3.5 h-3.5 text-emerald-400" />}
                        <TrendingUp className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="font-bold text-emerald-300">Bull Analyst</span>
                        <span className="text-[10px] text-slate-400">(Momentum & Growth Moats)</span>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                        ▼ {bullElapsed}
                      </span>
                    </button>
                    {expandedSections.bull && (
                      <div className="p-3.5 text-xs text-slate-200 font-sans leading-relaxed space-y-2">
                        {state.bullText ? (
                          <FormattedMarkdown content={state.bullText} role="bull" />
                        ) : (
                          <span className="text-slate-500 font-mono italic animate-pulse">Deliberating growth catalysts...</span>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 2: BEAR ANALYST */}
                {!state.conversationalText && (state.bearText || state.stage === "bear_analyst" || state.stage === "judge_synthesis" || (state.stage === "complete" && !state.conversationalText)) && (
                  <div className="border border-rose-500/20 bg-rose-950/20 rounded-xl overflow-hidden shadow-sm">
                    <button
                      onClick={() => toggleSection("bear")}
                      className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-rose-950/40 transition-colors font-mono text-xs border-b border-rose-500/10"
                    >
                      <div className="flex items-center space-x-2">
                        {expandedSections.bear ? <ChevronDown className="w-3.5 h-3.5 text-rose-400" /> : <ChevronRight className="w-3.5 h-3.5 text-rose-400" />}
                        <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
                        <span className="font-bold text-rose-300">Bear Analyst</span>
                        <span className="text-[10px] text-slate-400">(Downside & Multiple Trap)</span>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-rose-950/80 text-rose-400 border border-rose-800">
                        ▼ {bearElapsed}
                      </span>
                    </button>
                    {expandedSections.bear && (
                      <div className="p-3.5 text-xs text-slate-200 font-sans leading-relaxed space-y-2">
                        {state.bearText ? (
                          <FormattedMarkdown content={state.bearText} role="bear" />
                        ) : (
                          <span className="text-slate-500 font-mono italic animate-pulse">Scrutinizing leverage and tail risks...</span>
                        )}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 3: PORTFOLIO MANAGER JUDGE */}
                {!state.conversationalText && (state.judgeText || state.stage === "judge_synthesis" || (state.stage === "complete" && !state.conversationalText)) && (
                  <div className="border border-cyan-500/30 bg-cyan-950/20 rounded-xl overflow-hidden shadow-md">
                    <button
                      onClick={() => toggleSection("judge")}
                      className="w-full px-3.5 py-2.5 flex items-center justify-between text-left hover:bg-cyan-950/40 transition-colors font-mono text-xs border-b border-cyan-500/20"
                    >
                      <div className="flex items-center space-x-2">
                        {expandedSections.judge ? <ChevronDown className="w-3.5 h-3.5 text-cyan-400" /> : <ChevronRight className="w-3.5 h-3.5 text-cyan-400" />}
                        <Gavel className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="font-bold text-cyan-200">Portfolio Manager Debate Judge</span>
                        <span className="text-[10px] text-cyan-400/80">(Decision Memo)</span>
                      </div>
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-cyan-950/80 text-cyan-300 border border-cyan-800">
                        SYNTHESIS
                      </span>
                    </button>

                    {expandedSections.judge && (
                      <div className="p-3.5 space-y-3.5">
                        {/* Quick Execution Parameters Pill Box */}
                        {state.decisionResult && state.decisionResult.target_price !== undefined && (
                          <div className="grid grid-cols-3 gap-2 bg-slate-950/80 p-2.5 rounded-lg border border-cyan-800/40 font-mono text-center">
                            <div>
                              <span className="text-[10px] text-slate-500 block">ENTRY ANCHOR</span>
                              <span className="text-xs font-bold text-white">₹{(state.decisionResult.entry_price ?? activePrice ?? 0).toFixed(2)}</span>
                            </div>
                            <div>
                              <span className="text-[10px] text-emerald-400 block">TARGET (80% CI)</span>
                              <span className="text-xs font-bold text-emerald-300">₹{(state.decisionResult.target_price ?? 0).toFixed(2)}</span>
                            </div>
                            <div>
                              <span className="text-[10px] text-rose-400 block">STOP LOSS</span>
                              <span className="text-xs font-bold text-rose-300">₹{(state.decisionResult.stop_loss ?? 0).toFixed(2)}</span>
                            </div>
                          </div>
                        )}

                        <div className="text-xs text-slate-200 font-sans leading-relaxed">
                          {state.judgeText ? (
                            <FormattedMarkdown content={state.judgeText} role="judge" />
                          ) : (
                            <span className="text-slate-500 font-mono italic animate-pulse">Adjudicating trade parameters...</span>
                          )}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* ───────────────────────────────────────────────────────────── */}
              {/* 4. ACTIONABLE PROMPT CHIPS & INPUT BOX                        */}
              {/* ───────────────────────────────────────────────────────────── */}
              <div className="p-4 border-t border-white/[0.08] bg-[#06090f]/95 space-y-3 shrink-0">
                {/* 1-Click Action Chips */}
                <div className="flex flex-wrap items-center gap-2">
                  <button
                    onClick={() => runDeliberation("Debate Bull vs Bear Thesis")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-cyan-500/10 border border-white/[0.08] hover:border-cyan-500/40 text-[11px] font-mono text-cyan-300 transition-all flex items-center space-x-1.5"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Debate Bull vs Bear Thesis</span>
                  </button>

                  <button
                    onClick={() => runDeliberation("Check Corporate Actions & Shareholding Filings")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-[11px] font-mono text-slate-300 transition-all flex items-center space-x-1.5"
                  >
                    <Layers className="w-3.5 h-3.5 text-indigo-400" />
                    <span>Corporate Actions</span>
                  </button>

                  <button
                    onClick={() => runDeliberation("Evaluate GARCH Cone & Risk/Reward Profile")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-[11px] font-mono text-slate-300 transition-all flex items-center space-x-1.5"
                  >
                    <Activity className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Risk/Reward Profile</span>
                  </button>
                </div>

                {/* Custom Prompt Input */}
                <form
                  onSubmit={e => {
                    e.preventDefault();
                    if (prompt.trim()) {
                      runDeliberation(prompt);
                      setPrompt("");
                    }
                  }}
                  className="flex items-center space-x-2.5"
                >
                  <div className="relative flex-1">
                    <input
                      type="text"
                      value={prompt}
                      onChange={e => setPrompt(e.target.value)}
                      placeholder={
                        activeSymbol
                          ? `Ask Quant Copilot about ${activeSymbol}...`
                          : "Ask Quant Copilot about NIFTY 50, sector rotations, or backtests..."
                      }
                      className="w-full bg-[#050810] border border-white/[0.1] rounded-xl px-4 py-2.5 text-xs font-mono text-white placeholder-slate-500 focus:outline-none focus:border-cyan-400 focus:shadow-[0_0_15px_rgba(6,182,212,0.2)] transition-all"
                    />
                  </div>
                  {state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error" ? (
                    <button
                      type="button"
                      onClick={stopDeliberation}
                      className="px-3.5 py-2.5 rounded-xl bg-rose-500/20 hover:bg-rose-500/30 border border-rose-500/40 text-rose-300 text-xs font-mono transition-all flex items-center space-x-1.5 shadow-[0_0_12px_rgba(244,63,94,0.2)] shrink-0"
                      title="Stop Generating (Abort Stream)"
                    >
                      <Square className="w-3.5 h-3.5 fill-rose-400 text-rose-400" />
                      <span className="hidden sm:inline">Stop</span>
                    </button>
                  ) : (
                    <button
                      type="submit"
                      disabled={!prompt.trim()}
                      className="p-2.5 rounded-xl bg-gradient-to-r from-cyan-600 to-blue-600 hover:from-cyan-500 hover:to-blue-500 disabled:opacity-40 text-white transition-all shrink-0 shadow-[0_0_15px_rgba(6,182,212,0.3)]"
                      title="Send Prompt"
                    >
                      <Send className="w-4 h-4" />
                    </button>
                  )}
                </form>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
