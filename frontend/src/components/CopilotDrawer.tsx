"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  BrainCircuit,
  X,
  Send,
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
  Minimize2
} from "lucide-react";

interface CopilotDrawerProps {
  activeSymbol: string;
  activePrice?: number;
  activeVerdict?: string;
  isOpen?: boolean;
  onClose?: () => void;
  onToggle?: () => void;
}

interface DeliberationState {
  stage: "idle" | "telemetry" | "bull_analyst" | "bear_analyst" | "judge_synthesis" | "complete" | "error";
  statusText: string;
  progressPct: number;
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
  };
}

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";

export default function CopilotDrawer({
  activeSymbol = "SUZLON",
  activePrice = 36.85,
  activeVerdict = "TACTICAL_SWING_LONG",
  isOpen: controlledIsOpen,
  onClose,
  onToggle
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

  const bullElapsed = "00:03";
  const bearElapsed = "00:05";

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

  // Start Multi-Agent Deliberation Stream
  const runDeliberation = async (customPrompt?: string) => {
    const userInstruction = customPrompt || prompt || "Debate Bull vs Bear Thesis";
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setState({
      stage: "telemetry",
      statusText: `Initializing deliberation engine for ${activeSymbol}...`,
      progressPct: 5,
      bullText: "",
      bearText: "",
      judgeText: ""
    });

    try {
      const response = await fetch(`${API_BASE}/copilot/stream`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "ngrok-skip-browser-warning": "true"
        },
        body: JSON.stringify({
          symbol: activeSymbol,
          prompt: userInstruction
        }),
        signal: controller.signal
      });

      if (!response.ok || !response.body) {
        throw new Error(`Failed to stream from copilot: HTTP ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (trimmed.startsWith("data: ")) {
            try {
              const data = JSON.parse(trimmed.slice(6));
              
              setState(prev => {
                const next = { ...prev };
                if (data.status) next.statusText = data.status;
                if (data.progress !== undefined) next.progressPct = data.progress;

                if (data.stage === "bull_analyst") {
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
                    if (data.result.bull_thesis) next.bullText = data.result.bull_thesis;
                    if (data.result.bear_thesis) next.bearText = data.result.bear_thesis;
                    if (data.result.judge_memo) next.judgeText = data.result.judge_memo;
                  }
                }
                return next;
              });

              // Auto-scroll
              if (scrollContainerRef.current) {
                scrollContainerRef.current.scrollTop = scrollContainerRef.current.scrollHeight;
              }
            } catch {
              // Ignore partial JSON
            }
          }
        }
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
    }
  };

  const toggleSection = (section: "bull" | "bear" | "judge") => {
    setExpandedSections(prev => ({ ...prev, [section]: !prev[section] }));
  };

  return (
    <>
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 1. FLOATING LAUNCH TRIGGER BUTTON (Always visible when drawer closed) */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {!isOpen && (
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
              className={`fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-[#050811] border-l border-white/[0.08] shadow-2xl backdrop-blur-xl ${
                isExpanded ? "w-full md:w-[720px]" : "w-full sm:w-[480px] lg:w-[520px]"
              }`}
            >
              {/* Header Bar */}
              <div className="h-14 px-4 border-b border-white/[0.08] flex items-center justify-between shrink-0 bg-slate-950/80">
                <div className="flex items-center space-x-2.5">
                  <div className="w-7 h-7 rounded-lg bg-cyan-950/80 border border-cyan-800/80 flex items-center justify-center text-cyan-400 shadow-sm">
                    <BrainCircuit className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold font-mono text-white tracking-wide">
                        QUANT COPILOT
                      </span>
                      <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950 text-cyan-300 border border-cyan-800/60 font-semibold">
                        Multi-Agent
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono block">
                      TradingAgents Architecture · Free Tier Engine
                    </span>
                  </div>
                </div>

                {/* Right controls */}
                <div className="flex items-center space-x-1.5">
                  <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    title={isExpanded ? "Restore width" : "Expand width"}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800/80 transition-colors hidden sm:block"
                  >
                    {isExpanded ? <Minimize2 className="w-3.5 h-3.5" /> : <Maximize2 className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    onClick={handleClose}
                    title="Close Drawer (Esc)"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-slate-800/80 transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Context-Aware Active Instrument Banner */}
              <div className="px-4 py-2 bg-slate-900/60 border-b border-white/[0.06] flex items-center justify-between font-mono text-xs shrink-0">
                <div className="flex items-center space-x-2">
                  <span className="text-slate-500 text-[11px]">Active Context:</span>
                  <span className="text-white font-bold tracking-tight px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700">
                    {activeSymbol}
                  </span>
                  <span className="text-slate-300 font-medium">₹{activePrice.toFixed(2)}</span>
                </div>
                <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-950 text-emerald-300 border border-emerald-800/80">
                  {activeVerdict.replace(/_/g, " ")}
                </span>
              </div>

              {/* Progress Indicator */}
              {state.stage !== "idle" && (
                <div className="w-full bg-slate-950 h-1 relative overflow-hidden">
                  <motion.div
                    className="h-full bg-gradient-to-r from-cyan-500 via-blue-500 to-emerald-400"
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
                className="flex-1 overflow-y-auto p-4 space-y-4 scrollbar-thin scrollbar-thumb-slate-800 scrollbar-track-transparent"
              >
                {/* Status Bar */}
                <div className="bg-slate-950/70 border border-white/[0.06] rounded-xl p-3 flex items-center space-x-2.5 font-mono text-xs">
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
                  <span className="text-[10px] text-slate-500 shrink-0">{state.progressPct}%</span>
                </div>

                {/* STAGE 1: BULL ANALYST */}
                {(state.bullText || state.stage === "bull_analyst" || state.stage === "bear_analyst" || state.stage === "judge_synthesis" || state.stage === "complete") && (
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
                      <div className="p-3.5 text-xs text-slate-200 font-sans leading-relaxed whitespace-pre-line space-y-2">
                        {state.bullText || <span className="text-slate-500 font-mono italic animate-pulse">Deliberating growth catalysts...</span>}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 2: BEAR ANALYST */}
                {(state.bearText || state.stage === "bear_analyst" || state.stage === "judge_synthesis" || state.stage === "complete") && (
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
                      <div className="p-3.5 text-xs text-slate-200 font-sans leading-relaxed whitespace-pre-line space-y-2">
                        {state.bearText || <span className="text-slate-500 font-mono italic animate-pulse">Scrutinizing leverage and tail risks...</span>}
                      </div>
                    )}
                  </div>
                )}

                {/* STAGE 3: PORTFOLIO MANAGER JUDGE */}
                {(state.judgeText || state.stage === "judge_synthesis" || state.stage === "complete") && (
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
                        {state.decisionResult && (
                          <div className="grid grid-cols-3 gap-2 bg-slate-950/80 p-2.5 rounded-lg border border-cyan-800/40 font-mono text-center">
                            <div>
                              <span className="text-[10px] text-slate-500 block">ENTRY ANCHOR</span>
                              <span className="text-xs font-bold text-white">₹{state.decisionResult.entry_price.toFixed(2)}</span>
                            </div>
                            <div>
                              <span className="text-[10px] text-emerald-400 block">TARGET (80% CI)</span>
                              <span className="text-xs font-bold text-emerald-300">₹{state.decisionResult.target_price.toFixed(2)}</span>
                            </div>
                            <div>
                              <span className="text-[10px] text-rose-400 block">STOP LOSS</span>
                              <span className="text-xs font-bold text-rose-300">₹{state.decisionResult.stop_loss.toFixed(2)}</span>
                            </div>
                          </div>
                        )}

                        <div className="text-xs text-slate-200 font-sans leading-relaxed whitespace-pre-line">
                          {state.judgeText || <span className="text-slate-500 font-mono italic animate-pulse">Adjudicating trade parameters...</span>}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* ───────────────────────────────────────────────────────────── */}
              {/* 4. ACTIONABLE PROMPT CHIPS & INPUT BOX                        */}
              {/* ───────────────────────────────────────────────────────────── */}
              <div className="p-3.5 border-t border-white/[0.08] bg-slate-950/90 space-y-2.5 shrink-0">
                {/* 1-Click Action Chips */}
                <div className="flex flex-wrap items-center gap-1.5">
                  <button
                    onClick={() => runDeliberation("Debate Bull vs Bear Thesis")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-cyan-950/60 border border-slate-800 hover:border-cyan-600/50 text-[11px] font-mono text-cyan-300 transition-colors flex items-center space-x-1"
                  >
                    <Sparkles className="w-3 h-3 text-cyan-400" />
                    <span>Debate Bull vs Bear Thesis</span>
                  </button>

                  <button
                    onClick={() => runDeliberation("Check Corporate Actions & Shareholding Filings")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-[11px] font-mono text-slate-300 transition-colors flex items-center space-x-1"
                  >
                    <Layers className="w-3 h-3 text-indigo-400" />
                    <span>Corporate Actions</span>
                  </button>

                  <button
                    onClick={() => runDeliberation("Evaluate GARCH Cone & Risk/Reward Profile")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-2.5 py-1 rounded-lg bg-slate-900 hover:bg-slate-800 border border-slate-800 hover:border-slate-700 text-[11px] font-mono text-slate-300 transition-colors flex items-center space-x-1"
                  >
                    <Activity className="w-3 h-3 text-emerald-400" />
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
                  className="flex items-center space-x-2"
                >
                  <div className="relative flex-1">
                    <input
                      type="text"
                      value={prompt}
                      onChange={e => setPrompt(e.target.value)}
                      placeholder={`Ask Quant Copilot about ${activeSymbol}...`}
                      className="w-full bg-slate-900/90 border border-slate-800 rounded-xl px-3.5 py-2 text-xs font-mono text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors"
                    />
                  </div>
                  <button
                    type="submit"
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="p-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white transition-colors shrink-0 shadow-md shadow-cyan-950/40"
                    title="Send Prompt"
                  >
                    <Send className="w-4 h-4" />
                  </button>
                </form>
              </div>
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </>
  );
}
