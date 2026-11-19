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
  BarChart3,
  Download,
  RotateCcw,
  Copy,
  Check,
} from "lucide-react";
import { RobustSSEParser, ServerSentEvent } from "@/lib/sseParser";
import { useFocusTrap } from "@/hooks/useFocusTrap";
import { useBackButtonClose } from "@/hooks/useBackButtonClose";
import { milEvents } from "@/lib/store";
import { Database, Gauge, Zap } from "lucide-react";

interface ExternalApiTelemetry {
  usage_date: string;
  service_name: string;
  endpoint_or_model: string;
  calls_succeeded: number;
  calls_failed: number;
  rate_limit_hits: number;
  units_processed: number;
  remaining_quota_header?: number | null;
  quota_limit?: number | null;
  quota_source?: string;
  last_called_at?: string | null;
  last_error?: string | null;
}

interface ModelQuotaStatus {
  model_id: string;
  provider: string;
  requests_used: number;
  daily_request_limit: number;
  requests_remaining: number;
  requests_pct_used: number;
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  daily_token_limit: number;
  tokens_remaining: number;
  tokens_pct_used: number;
  remaining_requests_header?: number;
  remaining_tokens_header?: number;
  last_used_at?: string;
}

interface DistillationStats {
  corpus_size: number;
  trace_count?: number;
  vocabulary_size: number;
  model_status: string;
  last_trained_at?: string;
}

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  timestamp?: string;
  modelUsed?: string;
  tokenUsage?: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null;
}

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

export function cleanLatexToPlainText(raw: string): string {
  if (!raw) return "";
  let clean = raw;
  // Block math delimiters \[ ... \] and display math $$ ... $$
  clean = clean.replace(/\\\[([\s\S]*?)\\\]/g, "$1");
  clean = clean.replace(/\$\$([\s\S]*?)\$\$/g, "$1");
  // Inline math delimiters \( ... \)
  clean = clean.replace(/\\\(([\s\S]*?)\\\)/g, "$1");
  // Fractions \frac{a}{b} -> (a ÷ b)
  clean = clean.replace(/\\frac\{([^}]+)\}\{([^}]+)\}/g, "($1 ÷ $2)");
  // Common math symbols
  clean = clean.replace(/\\times\b/g, "×");
  clean = clean.replace(/\\approx\b/g, "≈");
  clean = clean.replace(/\\le\b/g, "≤");
  clean = clean.replace(/\\ge\b/g, "≥");
  clean = clean.replace(/\\pm\b/g, "±");
  clean = clean.replace(/\\cdot\b/g, "·");
  // Text formatting inside math: \text{...}, \mathbf{...}, \mathit{...}
  clean = clean.replace(/\\mathbf\{([^}]+)\}/g, "**$1**");
  clean = clean.replace(/\\text\{([^}]+)\}/g, "$1");
  clean = clean.replace(/\\mathit\{([^}]+)\}/g, "*$1*");
  // Remove leftover backslashes before common tokens
  clean = clean.replace(/\\%/g, "%");
  return clean;
}

export function FormattedMarkdown({
  content,
  role,
}: {
  content: string;
  role?: "bull" | "bear" | "judge" | "general";
}) {
  if (!content) return null;

  const sanitizedContent = cleanLatexToPlainText(content);
  const rawLines = sanitizedContent.split("\n");

  const parseInline = (text: string) => {
    const parts: React.ReactNode[] = [];
    let remaining = text;
    let keyIdx = 0;
    const tokenRegex = /(\[[^\]]+\]\([^)]+\)|\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/;

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
      if (rawToken.startsWith("[") && rawToken.includes("](") && rawToken.endsWith(")")) {
        const linkMatch = rawToken.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (linkMatch) {
          const [, label, url] = linkMatch;
          parts.push(
            <a
              key={keyIdx++}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-cyan-400 hover:text-cyan-300 underline underline-offset-2"
            >
              {label}
            </a>
          );
        } else {
          parts.push(rawToken);
        }
      } else if (rawToken.startsWith("**") && rawToken.endsWith("**")) {
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

  // Group lines into blocks: table, code, or normal lines
  type Block =
    | { type: "table"; headers: string[]; rows: string[][] }
    | { type: "code"; lang: string; lines: string[] }
    | { type: "line"; line: string };

  const blocks: Block[] = [];
  let i = 0;

  while (i < rawLines.length) {
    const line = rawLines[i];
    const trimmed = line.trim();

    // Check code block
    if (trimmed.startsWith("```")) {
      const lang = trimmed.slice(3).trim();
      const codeLines: string[] = [];
      i++;
      while (i < rawLines.length && !rawLines[i].trim().startsWith("```")) {
        codeLines.push(rawLines[i]);
        i++;
      }
      i++; // skip closing ```
      blocks.push({ type: "code", lang, lines: codeLines });
      continue;
    }

    // Check table row (starts and ends with pipe, or contains | and has separator line next)
    if (
      trimmed.startsWith("|") &&
      trimmed.endsWith("|") &&
      i + 1 < rawLines.length &&
      rawLines[i + 1].trim().startsWith("|") &&
      /^[|\s-:]+$/.test(rawLines[i + 1].trim())
    ) {
      const parseRow = (r: string) => {
        const segs = r.trim().split("|");
        return segs.slice(1, segs.length - 1);
      };

      const headers = parseRow(trimmed);
      i += 2; // skip header and separator row
      const rows: string[][] = [];

      while (i < rawLines.length) {
        const rowLine = rawLines[i].trim();
        if (!rowLine.startsWith("|") || !rowLine.endsWith("|")) {
          break;
        }
        rows.push(parseRow(rowLine));
        i++;
      }

      blocks.push({ type: "table", headers, rows });
      continue;
    }

    blocks.push({ type: "line", line });
    i++;
  }

  return (
    <div className="space-y-1.5 text-xs leading-relaxed font-sans text-slate-200">
      {blocks.map((block, idx) => {
        if (block.type === "code") {
          return (
            <div key={idx} className="my-2 p-3 rounded-xl bg-[#030508] border border-white/[0.08] font-mono text-[11px] overflow-x-auto text-cyan-200">
              <pre>{block.lines.join("\n")}</pre>
            </div>
          );
        }

        if (block.type === "table") {
          return (
            <div key={idx} className="w-full overflow-x-auto my-3 rounded-xl border border-white/[0.08] bg-[#050811] shadow-md">
              <table className="w-full text-xs font-mono border-collapse my-0">
                <thead className="bg-[#080d1a] border-b border-white/[0.1] text-slate-300">
                  <tr>
                    {block.headers.map((h, hIdx) => (
                      <th
                        key={hIdx}
                        className="px-3 py-2 text-left font-semibold tracking-wider text-[11px] uppercase border-r border-white/[0.04] last:border-r-0 text-slate-300"
                      >
                        {parseInline(h.trim())}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.04]">
                  {block.rows.map((row, rIdx) => (
                    <tr key={rIdx} className="hover:bg-white/[0.02] transition-colors">
                      {row.map((cell, cIdx) => (
                        <td
                          key={cIdx}
                          className="px-3 py-2 text-slate-200 border-r border-white/[0.04] last:border-r-0"
                        >
                          {parseInline(cell.trim())}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }

        const line = block.line;
        const trimmed = line.trim();
        if (!trimmed) {
          return <div key={idx} className="h-1" />;
        }

        // Horizontal rule
        if (trimmed === "---" || trimmed === "***") {
          return <hr key={idx} className="border-t border-white/[0.08] my-2" />;
        }

        // H1 Header (# Title)
        if (trimmed.startsWith("# ")) {
          const headerText = trimmed.replace(/^#\s+/, "");
          return (
            <div
              key={idx}
              className="font-mono font-bold text-sm sm:text-base pt-2 pb-1 border-b border-white/[0.15] text-white tracking-wide mt-2"
            >
              {headerText}
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

        // H4-H6 Header (#### Title)
        if (/^#{4,6}\s+/.test(trimmed)) {
          const headerText = trimmed.replace(/^#{4,6}\s+/, "");
          return (
            <div
              key={idx}
              className="font-mono font-semibold text-xs text-slate-300 tracking-wide uppercase mt-1.5"
            >
              {headerText}
            </div>
          );
        }

        // Blockquote (> Quote)
        if (trimmed.startsWith("> ")) {
          const quoteText = trimmed.replace(/^>\s+/, "");
          return (
            <blockquote
              key={idx}
              className="border-l-2 border-cyan-500/60 pl-3 py-1 my-1.5 text-slate-300 italic bg-white/[0.02] rounded-r text-xs font-sans"
            >
              {parseInline(quoteText)}
            </blockquote>
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

  const [internalSymbol, setInternalSymbol] = useState<string>(activeSymbol || "RELIANCE");

  useEffect(() => {
    if (activeSymbol) {
      setInternalSymbol(activeSymbol);
    }
  }, [activeSymbol]);

  const effectiveSymbol = internalSymbol || activeSymbol || "RELIANCE";

  const [prompt, setPrompt] = useState("");
  const [isExpanded, setIsExpanded] = useState(false);
  const [chatHistory, setChatHistory] = useState<ChatMessage[]>([]);
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
  const [showMlPanel, setShowMlPanel] = useState(false);
  const [copiedIndex, setCopiedIndex] = useState<number | null>(null);
  const [isDebateActive, setIsDebateActive] = useState(false);
  const [showQuotaPanel, setShowQuotaPanel] = useState(false);
  const [quotaData, setQuotaData] = useState<{
    models: ModelQuotaStatus[];
    distillation: DistillationStats;
    external_apis?: ExternalApiTelemetry[];
  } | null>(null);
  const [quotaLoading, setQuotaLoading] = useState(false);
  const [isDistilling, setIsDistilling] = useState(false);
  const [distillSuccessMessage, setDistillSuccessMessage] = useState<string | null>(null);

  const toggleQuotaPanel = useCallback(() => {
    setShowQuotaPanel((prev) => {
      const next = !prev;
      if (next) setShowMlPanel(false);
      return next;
    });
  }, []);

  const toggleMlPanel = useCallback(() => {
    setShowMlPanel((prev) => {
      const next = !prev;
      if (next) setShowQuotaPanel(false);
      return next;
    });
  }, []);

  const runDeliberationRef = useRef<(customPrompt?: string) => Promise<void>>();

  // Subscribe to mil:open-copilot event
  useEffect(() => {
    const unsub = milEvents.on("mil:open-copilot", (payload) => {
      setInternalIsOpen(true);
      if (payload?.symbol) {
        setInternalSymbol(payload.symbol);
      }
      if (payload?.initialPrompt) {
        void runDeliberationRef.current?.(payload.initialPrompt);
      }
    });
    return unsub;
  }, []);

  const fetchQuotaTelemetry = useCallback(async () => {
    setQuotaLoading(true);
    try {
      const res = await fetch(`${API_BASE}/copilot/usage`);
      if (res.ok) {
        const json = await res.json();
        setQuotaData({
          models: json.models || [],
          distillation: json.distillation || { corpus_size: 0, vocabulary_size: 0, model_status: "untrained" },
          external_apis: json.external_apis || [],
        });
      }
    } catch (e) {
      console.error("Quota telemetry fetch error:", e);
    } finally {
      setQuotaLoading(false);
    }
  }, []);

  useEffect(() => {
    if (showQuotaPanel) {
      void fetchQuotaTelemetry();
    }
  }, [showQuotaPanel, fetchQuotaTelemetry]);

  const handleTriggerDistillation = async () => {
    setIsDistilling(true);
    setDistillSuccessMessage(null);
    try {
      const res = await fetch(`${API_BASE}/copilot/distill`, { method: "POST" });
      if (res.ok) {
        setDistillSuccessMessage("Distillation tournament trained successfully!");
        void fetchQuotaTelemetry();
        setTimeout(() => setDistillSuccessMessage(null), 3500);
      }
    } catch (e) {
      console.error("Distillation trigger error:", e);
    } finally {
      setIsDistilling(false);
    }
  };

  const handleCopyMessage = useCallback((content: string, idx: number) => {
    try {
      navigator.clipboard.writeText(content);
      setCopiedIndex(idx);
      setTimeout(() => setCopiedIndex(null), 2000);
    } catch (e) {
      console.error("Failed to copy message:", e);
    }
  }, []);

  // Eagerly fetch ML Alpha Forecast when context symbol changes and drawer is open
  useEffect(() => {
    if (!effectiveSymbol || !isOpen) return;
    let isCancelled = false;
    const fetchMlForecast = async () => {
      try {
        const res = await fetch(`${API_BASE}/ml/forecast/${encodeURIComponent(effectiveSymbol)}`);
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
  }, [effectiveSymbol, isOpen]);

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

  useBackButtonClose(isOpen, handleClose, "copilotDrawer");

  const handleExportMarkdown = useCallback(() => {
    const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
    const targetSymbol = effectiveSymbol || "NSE_UNIVERSE";
    let md = `# Market Intelligence Lab — Quant Copilot Deliberation\n`;
    md += `**Target Symbol:** ${targetSymbol}\n`;
    md += `**Generated Date:** ${new Date().toLocaleString("en-IN")}\n`;
    if (activePrice) md += `**Settled Price:** ₹${activePrice.toFixed(2)}\n`;
    if (activeVerdict) md += `**Institutional Verdict:** ${activeVerdict.replace(/_/g, " ")}\n`;
    md += `\n---\n\n`;

    if (state.judgeText) {
      md += `## Portfolio Manager Judge Synthesis\n\n${state.judgeText}\n\n`;
    }
    if (state.bullText) {
      md += `## Bullish Momentum Thesis\n\n${state.bullText}\n\n`;
    }
    if (state.bearText) {
      md += `## Bearish Risk Thesis\n\n${state.bearText}\n\n`;
    }

    if (chatHistory.length > 0) {
      md += `## Multi-Turn Deliberation Transcript\n\n`;
      chatHistory.forEach((msg) => {
        md += `### ${msg.role === "user" ? "User Inquiry" : "Quant Copilot"}\n\n${msg.content}\n\n`;
      });
    }

    const blob = new Blob([md], { type: "text/markdown;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `MIL_Deliberation_${targetSymbol}_${timestamp}.md`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }, [effectiveSymbol, activePrice, activeVerdict, state.judgeText, state.bullText, state.bearText, chatHistory]);

  const drawerRef = useFocusTrap<HTMLElement>(isOpen, handleClose);

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
    runDeliberationRef.current = runDeliberation;
    const userInstruction = customPrompt || prompt || "Debate Bull vs Bear Thesis";
    const targetSymbol = effectiveSymbol || "NIFTY 50";
    
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    setState({
      stage: "telemetry",
      statusText: effectiveSymbol 
        ? `Initializing deliberation engine for ${effectiveSymbol}...`
        : "Initializing quantitative deliberation engine...",
      progressPct: 5,
      conversationalText: "",
      bullText: "",
      bearText: "",
      judgeText: ""
    });

    let streamConversational = "";
    let streamJudge = "";
    let lastModelUsed = "";
    let lastTokenUsage: { prompt_tokens?: number; completion_tokens?: number; total_tokens?: number } | null = null;

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
          prompt: userInstruction,
          history: chatHistory.slice(-8)
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
            setIsDebateActive(true);
            if (!bullStartTimeRef.current) bullStartTimeRef.current = Date.now();
            setBullElapsed(formatSeconds((Date.now() - bullStartTimeRef.current) / 1000));
          } else if (data.stage === "bear_analyst") {
            setIsDebateActive(true);
            if (!bearStartTimeRef.current) bearStartTimeRef.current = Date.now();
            setBearElapsed(formatSeconds((Date.now() - bearStartTimeRef.current) / 1000));
          } else if (data.stage === "judge_synthesis") {
            setIsDebateActive(true);
          } else if (data.stage === "conversational") {
            setIsDebateActive(false);
          }

          if (data.stage === "complete") {
            if (data.model_used || data.result?.model_used) {
              lastModelUsed = data.model_used || data.result?.model_used;
            }
            if (data.token_usage || data.result?.token_usage) {
              lastTokenUsage = data.token_usage || data.result?.token_usage;
            }
          }

          setState(prev => {
            const next = { ...prev };
            if (data.status) next.statusText = data.status;
            if (data.progress !== undefined) next.progressPct = data.progress;

            if (data.stage === "conversational") {
              next.stage = "conversational";
              if (data.delta) {
                streamConversational += data.delta;
                next.conversationalText = (prev.conversationalText || "") + data.delta;
              }
            } else if (data.stage === "bull_analyst") {
              next.stage = "bull_analyst";
              if (data.delta) next.bullText = prev.bullText + data.delta;
            } else if (data.stage === "bear_analyst") {
              next.stage = "bear_analyst";
              if (data.delta) next.bearText = prev.bearText + data.delta;
            } else if (data.stage === "judge_synthesis") {
              next.stage = "judge_synthesis";
              if (data.delta) {
                streamJudge += data.delta;
                next.judgeText = prev.judgeText + data.delta;
              }
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
                if (data.result.judge_memo) {
                  next.judgeText = data.result.judge_memo;
                  streamJudge = data.result.judge_memo;
                }
                if (data.result.conversational_response) {
                  next.conversationalText = data.result.conversational_response;
                  streamConversational = data.result.conversational_response;
                }
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

      const nowStr = new Date().toLocaleTimeString("en-IN", { hour: "2-digit", minute: "2-digit" });
      if (streamConversational.trim()) {
        const reply = streamConversational.trim();
        setChatHistory(prev => [
          ...prev,
          { role: "user", content: userInstruction, timestamp: nowStr },
          {
            role: "assistant",
            content: reply,
            timestamp: nowStr,
            modelUsed: lastModelUsed,
            tokenUsage: lastTokenUsage
          }
        ]);
        // Clear conversationalText so completed turns render exclusively inside chatHistory (zero duplication)
        setState(prev => ({
          ...prev,
          conversationalText: "",
          stage: "complete",
          statusText: "Analysis complete."
        }));
      } else if (streamJudge.trim() || state.bullText || state.bearText) {
        // 3-Agent committee debate: kept in active accordion cards, not duplicated into chatHistory
        setState(prev => ({
          ...prev,
          stage: "complete",
          statusText: "Deliberation complete."
        }));
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

  // Auto-scroll whenever chat history or live streaming telemetry updates
  useEffect(() => {
    if (scrollContainerRef.current) {
      scrollContainerRef.current.scrollTo({
        top: scrollContainerRef.current.scrollHeight,
        behavior: "smooth"
      });
    }
  }, [chatHistory.length, state.conversationalText, state.judgeText, state.bullText, state.bearText, state.stage]);

  return (
    <>
      {/* ─────────────────────────────────────────────────────────────────── */}
      {/* 1. FLOATING LAUNCH TRIGGER BUTTON (Optional, off by default)         */}
      {/* ─────────────────────────────────────────────────────────────────── */}
      {showFloatingTrigger && !isOpen && (
        <button
          onClick={handleToggle}
          title="Open Quant Copilot Multi-Agent Drawer (⌘J / Ctrl+J)"
          className="fixed bottom-4 right-4 z-40 flex items-center space-x-2.5 px-3.5 py-2 rounded-xl bg-slate-900/90 hover:bg-slate-800 text-slate-100 border border-cyan-500/30 hover:border-cyan-400 shadow-[0_4px_24px_rgba(6,182,212,0.18)] transition-all font-mono text-xs group"
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
              className="fixed inset-0 bg-black/60 z-50 lg:bg-black/40"
            />

            {/* Slide-in Drawer Container */}
            <motion.aside
              ref={drawerRef}
              role="dialog"
              aria-modal="true"
              aria-label="Quantitative Copilot Deliberation Drawer"
              tabIndex={-1}
              initial={{ x: "100%" }}
              animate={{ x: 0 }}
              exit={{ x: "100%" }}
              drag="x"
              dragConstraints={{ left: 0, right: 0 }}
              dragElastic={{ left: 0, right: 0.5 }}
              onDragEnd={(_, info) => {
                if (info.offset.x > 100 || info.velocity.x > 300) {
                  handleClose();
                }
              }}
              transition={{ type: "spring", stiffness: 320, damping: 32 }}
              className={`fixed top-0 right-0 bottom-0 z-50 flex flex-col bg-[#06090f] border-l border-white/[0.1] shadow-[-20px_0_60px_rgba(0,0,0,0.85)] h-[100dvh] max-h-[100dvh] ${
                isExpanded ? "w-full md:w-[720px]" : "w-full sm:w-[480px] lg:w-[520px]"
              }`}
            >
              {/* Header Bar */}
              <div className="h-14 px-3 sm:px-5 border-b border-white/[0.08] flex items-center justify-between shrink-0 bg-[#080c14]">
                <div className="flex items-center space-x-2 sm:space-x-3 min-w-0">
                  <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.2)] shrink-0">
                    <BrainCircuit className="w-4 h-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="flex items-center space-x-2">
                      <span className="text-xs font-bold font-mono text-white tracking-wider truncate">
                        QUANT COPILOT
                      </span>
                      <span className="hidden sm:inline-flex text-[10px] px-2 py-0.5 rounded-full font-mono bg-cyan-950/80 text-cyan-300 border border-cyan-500/40 font-semibold shadow-[0_0_8px_rgba(6,182,212,0.2)]">
                        Multi-Agent Committee
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-400 font-mono block truncate">
                      TradingAgents Architecture · Free Tier Engine
                    </span>
                  </div>
                </div>

                {/* Right controls */}
                <div className="flex items-center space-x-1 shrink-0">
                  <button
                    onClick={() => {
                      setChatHistory([]);
                      setState({
                        stage: "idle",
                        statusText: "Ready for multi-agent quantitative deliberation.",
                        progressPct: 0,
                        bullText: "",
                        bearText: "",
                        judgeText: "",
                        conversationalText: "",
                      });
                    }}
                    title="Clear Chat Thread"
                    aria-label="Clear chat thread"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] transition-colors"
                  >
                    <RotateCcw className="w-4 h-4" />
                  </button>
                  <button
                    onClick={handleExportMarkdown}
                    title="Export deliberation transcript to Markdown (.md)"
                    aria-label="Export deliberation transcript"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-300 hover:bg-white/[0.06] transition-colors"
                  >
                    <Download className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => setIsExpanded(!isExpanded)}
                    title={isExpanded ? "Restore width" : "Expand width"}
                    aria-label={isExpanded ? "Restore width" : "Expand width"}
                    className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.06] transition-colors hidden sm:block"
                  >
                    {isExpanded ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
                  </button>
                  <button
                    onClick={handleClose}
                    title="Close Drawer (Esc)"
                    aria-label="Close drawer"
                    className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-white/[0.06] transition-colors"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              </div>

              {/* Context-Aware Active Instrument Banner */}
              <div className="px-3 sm:px-5 py-2 bg-[#050810]/80 border-b border-white/[0.06] flex items-center justify-between font-mono text-xs shrink-0 overflow-hidden">
                <div className="flex items-center space-x-2 min-w-0">
                  <span className="text-slate-400 text-[11px] uppercase tracking-wider whitespace-nowrap shrink-0">Context:</span>
                  {effectiveSymbol ? (
                    <span className="text-white font-bold tracking-tight px-1.5 py-0.5 rounded-md bg-white/[0.06] border border-white/[0.1] shadow-sm truncate">
                      {effectiveSymbol}
                    </span>
                  ) : (
                    <span className="text-slate-400 italic text-[11px] whitespace-nowrap">Market Overview</span>
                  )}
                  {activePrice !== undefined ? (
                    <span className="text-slate-200 font-semibold tabular-nums whitespace-nowrap">₹{activePrice.toFixed(2)}</span>
                  ) : effectiveSymbol ? (
                    <span className="text-slate-500 text-[11px] flex items-center space-x-1 whitespace-nowrap">
                      <Loader2 className="w-3 h-3 animate-spin text-cyan-400" />
                      <span>Syncing...</span>
                    </span>
                  ) : null}
                </div>
                {activeVerdict ? (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-bold bg-emerald-500/10 text-emerald-300 border border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.2)] max-w-[130px] sm:max-w-none truncate shrink-0">
                    {activeVerdict.replace(/_/g, " ")}
                  </span>
                ) : (
                  <span className="text-[10px] px-2 py-0.5 rounded-full font-mono text-slate-400 border border-white/[0.08] whitespace-nowrap shrink-0">
                    {effectiveSymbol ? "Pending Verdict" : "NIFTY 50"}
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

                {/* Empty State Welcome Card */}
                {chatHistory.length === 0 && state.stage === "idle" && !state.judgeText && (
                  <div className="p-4 rounded-2xl bg-gradient-to-b from-[#080d1a] to-[#04060c] border border-white/[0.08] space-y-3.5 shadow-lg">
                    <div className="flex items-center space-x-2.5">
                      <div className="w-8 h-8 rounded-xl bg-cyan-500/10 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-[0_0_10px_rgba(6,182,212,0.25)]">
                        <Sparkles className="w-4 h-4" />
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-white font-mono">Quant Copilot Ready</h4>
                        <p className="text-[11px] text-slate-400 font-sans">
                          Grounded multi-turn intelligence for {effectiveSymbol || "NSE Equities"}.
                        </p>
                      </div>
                    </div>
                    <div className="space-y-1.5 pt-1">
                      <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                        Suggested Inquiries
                      </span>
                      <div className="grid gap-1.5">
                        {[
                          `What was ${effectiveSymbol || "NIFTY 50"}'s last major dip?`,
                          `Compare ${effectiveSymbol || "NIFTY 50"} vs sector peers`,
                          `Summarize ${effectiveSymbol || "NIFTY 50"}'s 20D risk/reward profile`
                        ].map((q, idx) => (
                          <button
                            key={idx}
                            onClick={() => runDeliberation(q)}
                            className="text-left px-3 py-2 rounded-xl bg-white/[0.03] hover:bg-cyan-500/10 border border-white/[0.06] hover:border-cyan-500/30 text-xs font-mono text-slate-300 hover:text-cyan-200 transition-colors flex items-center justify-between group"
                          >
                            <span>{q}</span>
                            <ChevronRight className="w-3.5 h-3.5 text-slate-600 group-hover:text-cyan-400 transition-colors shrink-0" />
                          </button>
                        ))}
                      </div>
                    </div>
                  </div>
                )}

                {/* Conversation History Stream (Multi-turn Context) */}
                {chatHistory.length > 0 && (
                  <div className="space-y-3.5">
                    {chatHistory.map((msg, idx) => (
                      <div key={idx} className="space-y-1">
                        {msg.role === "user" ? (
                          <div className="flex flex-col items-end">
                            <div className="ml-auto max-w-[85%] bg-cyan-950/50 border border-cyan-500/30 rounded-2xl rounded-br-sm p-3 text-xs font-sans text-cyan-100 shadow-sm">
                              <p className="leading-relaxed whitespace-pre-wrap">{msg.content}</p>
                            </div>
                            {msg.timestamp && (
                              <span className="text-[9px] font-mono text-slate-500 mt-1 mr-1">
                                {msg.timestamp}
                              </span>
                            )}
                          </div>
                        ) : (
                          <div className="flex flex-col items-start w-full">
                            <div className="w-full bg-[#090e1a] border border-white/[0.08] rounded-2xl rounded-bl-sm p-4 text-xs font-sans text-slate-200 shadow-md space-y-2">
                              {/* Assistant Header */}
                              <div className="flex items-center justify-between pb-2 border-b border-white/[0.06]">
                                <div className="flex items-center space-x-2">
                                  <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
                                  <span className="font-bold font-mono text-[11px] text-white">Quant Copilot</span>
                                  {effectiveSymbol && (
                                    <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-semibold">
                                      {effectiveSymbol}
                                    </span>
                                  )}
                                </div>
                                <div className="flex items-center space-x-2">
                                  {msg.timestamp && (
                                    <span className="text-[9px] font-mono text-slate-500">
                                      {msg.timestamp}
                                    </span>
                                  )}
                                  <button
                                    type="button"
                                    onClick={() => handleCopyMessage(msg.content, idx)}
                                    title="Copy response to clipboard"
                                    className="p-1 rounded hover:bg-white/[0.06] text-slate-400 hover:text-white transition-colors"
                                  >
                                    {copiedIndex === idx ? (
                                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                                    ) : (
                                      <Copy className="w-3.5 h-3.5 text-slate-400" />
                                    )}
                                  </button>
                                </div>
                              </div>
                              <FormattedMarkdown content={msg.content} role="general" />
                              {msg.modelUsed && (
                                <div className="flex items-center gap-1.5 mt-2 pt-1.5 border-t border-white/[0.04] text-[10px] font-mono text-slate-400">
                                  <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20 font-semibold">
                                    ⚡ {msg.modelUsed.replace(/^groq:/, "").replace(/^gemini:/, "").replace(/^local:/, "")}
                                  </span>
                                  {msg.tokenUsage && msg.tokenUsage.total_tokens ? (
                                    <span className="text-slate-500">
                                      · {msg.tokenUsage.total_tokens.toLocaleString()} tok
                                    </span>
                                  ) : null}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}

                {/* Active Live Streaming Bubble (Only while streaming conversational response) */}
                {state.stage === "conversational" && state.conversationalText && (
                  <div className="w-full bg-[#090e1a] border border-cyan-500/30 rounded-2xl rounded-bl-sm p-4 text-xs font-sans text-slate-200 shadow-md space-y-2 animate-in fade-in">
                    <div className="flex items-center justify-between pb-2 border-b border-white/[0.08]">
                      <div className="flex items-center space-x-2">
                        <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
                        <span className="font-bold font-mono text-[11px] text-white">Quant Copilot</span>
                        {effectiveSymbol && (
                          <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950/80 text-cyan-300 border border-cyan-800/60 font-semibold">
                            {effectiveSymbol}
                          </span>
                        )}
                      </div>
                      <span className="flex items-center space-x-1 text-[10px] font-mono text-cyan-400">
                        <Loader2 className="w-3 h-3 animate-spin" />
                        <span>Streaming...</span>
                      </span>
                    </div>
                    <FormattedMarkdown content={state.conversationalText} role="general" />
                  </div>
                )}

                {/* STAGE 1: BULL ANALYST */}
                {isDebateActive && (state.bullText || state.stage === "bull_analyst" || state.stage === "bear_analyst" || state.stage === "judge_synthesis" || (state.stage === "complete" && !state.conversationalText)) && (
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
                {isDebateActive && (state.bearText || state.stage === "bear_analyst" || state.stage === "judge_synthesis" || (state.stage === "complete" && !state.conversationalText)) && (
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
                {isDebateActive && (state.judgeText || state.stage === "judge_synthesis" || (state.stage === "complete" && !state.conversationalText)) && (
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
              <div className="p-3 sm:p-4 border-t border-white/[0.08] bg-[#06090f]/95 space-y-2.5 shrink-0 pb-[max(1rem,env(safe-area-inset-bottom))]">
                {/* Expandable ML Forecast Card Docked Above Input Dock */}
                <AnimatePresence>
                  {showMlPanel && mlForecast && !mlForecast.error && (
                    <motion.div
                      initial={{ opacity: 0, y: 8, scale: 0.98 }}
                      animate={{ opacity: 1, y: 0, scale: 1 }}
                      exit={{ opacity: 0, y: 8, scale: 0.98 }}
                      transition={{ duration: 0.16 }}
                      className="border border-indigo-500/30 bg-[#070b16] rounded-xl p-3 shadow-2xl space-y-3 font-mono text-xs max-h-[46dvh] sm:max-h-[340px] overflow-y-auto thin-scrollbar"
                    >
                      <div className="flex items-center justify-between pb-2 border-b border-indigo-500/20">
                        <div className="flex items-center space-x-2">
                          <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                          <span className="font-bold text-indigo-200 text-xs">ML Multi-Horizon Alpha Forecast</span>
                          <span className="text-[10px] text-indigo-400/80">
                            ({mlForecast.champion_model || "Champion Model"})
                          </span>
                        </div>
                        <button
                          type="button"
                          onClick={() => setShowMlPanel(false)}
                          className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/[0.06]"
                        >
                          <X className="w-3.5 h-3.5" />
                        </button>
                      </div>

                      {/* Multi-Horizon Return Grid */}
                      <div className="grid grid-cols-3 gap-2">
                        {(["5D", "20D", "60D"] as const).map((horizon) => {
                          const fc = mlForecast.forecasts?.[horizon];
                          if (!fc) return null;
                          const isPos = (fc.expected_return_pct ?? 0) >= 0;
                          return (
                            <div
                              key={horizon}
                              className="bg-slate-950/80 border border-slate-800/80 rounded-lg p-2 flex flex-col items-center justify-between text-center"
                            >
                              <div className="flex items-center justify-between w-full text-[10px] text-slate-400 mb-0.5">
                                <span className="font-semibold text-slate-300">{horizon}</span>
                                <span className="text-[9px] text-indigo-400/80 truncate max-w-[60px]">{fc.model}</span>
                              </div>
                              <div className={`text-xs font-bold my-0.5 ${isPos ? "text-emerald-400" : "text-rose-400"}`}>
                                {isPos ? "+" : ""}{(fc.expected_return_pct ?? 0).toFixed(2)}%
                              </div>
                              <div className="text-[9px] text-slate-500">
                                {isPos ? "+" : ""}{(fc.expected_excess_bps ?? 0).toFixed(1)} bps
                              </div>
                            </div>
                          );
                        })}
                      </div>

                      <div className="flex items-center justify-between pt-1 text-[10px] border-t border-indigo-900/40">
                        <span className="text-slate-400">
                          Rank IC: <strong className="text-indigo-300">+{(mlForecast.overall_rank_ic ?? 0.035).toFixed(4)}</strong>
                        </span>
                        <span className={`px-2 py-0.5 rounded font-bold ${
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

                      {/* Top Feature Attributions */}
                      {mlForecast.feature_attributions && mlForecast.feature_attributions.length > 0 && (
                        <div className="space-y-1 pt-1 border-t border-indigo-900/30">
                          <div className="flex items-center justify-between text-[10px] text-slate-400">
                            <span className="flex items-center space-x-1">
                              <BarChart3 className="w-3.5 h-3.5 text-indigo-400" />
                              <span>Top Walk-Forward Factor Drivers</span>
                            </span>
                            <span className="text-[9px] text-slate-500">Weight</span>
                          </div>
                          <div className="space-y-1">
                            {mlForecast.feature_attributions.slice(0, 3).map((item, idx) => (
                              <div key={idx} className="flex items-center justify-between text-[10px] bg-slate-900/70 px-2 py-0.5 rounded border border-white/[0.04]">
                                <span className="text-slate-300 capitalize truncate max-w-[160px]">
                                  {item.feature.replace(/_/g, " ")}
                                </span>
                                <span className="text-indigo-300 font-bold">
                                  {item.weight_pct.toFixed(1)}%
                                </span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  )}

                  {/* Collapsible 📊 Engine & Quota Panel */}
                  {showQuotaPanel && (
                    <motion.div
                      initial={{ opacity: 0, height: 0 }}
                      animate={{ opacity: 1, height: "auto" }}
                      exit={{ opacity: 0, height: 0 }}
                      transition={{ duration: 0.2 }}
                      className="border border-cyan-500/30 bg-[#060b18] rounded-2xl p-3 sm:p-3.5 space-y-3 shadow-xl max-w-full max-h-[46dvh] sm:max-h-[340px] overflow-y-auto thin-scrollbar"
                    >
                      <div className="flex items-center justify-between border-b border-white/[0.06] pb-2 gap-2">
                        <div className="flex items-center space-x-2 min-w-0">
                          <Gauge className="w-4 h-4 text-cyan-400 shrink-0" />
                          <h4 className="text-xs font-bold text-white font-mono truncate">LLM Quota Metering & Distillation</h4>
                        </div>
                        <div className="flex items-center space-x-2 shrink-0">
                          <button
                            type="button"
                            onClick={() => void fetchQuotaTelemetry()}
                            disabled={quotaLoading}
                            className="text-[10px] font-mono text-cyan-400 hover:text-cyan-300 flex items-center gap-1"
                          >
                            <RotateCcw className={`w-3 h-3 ${quotaLoading ? "animate-spin" : ""}`} />
                            <span>Refresh</span>
                          </button>
                          <button
                            type="button"
                            onClick={() => setShowQuotaPanel(false)}
                            className="p-1 rounded text-slate-400 hover:text-white hover:bg-white/[0.08] transition-colors"
                            aria-label="Close panel"
                          >
                            <X className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>

                      {quotaLoading && !quotaData ? (
                        <div className="flex items-center justify-center py-4 text-xs font-mono text-slate-500">
                          <Loader2 className="w-4 h-4 animate-spin mr-2 text-cyan-400" />
                          <span>Loading quota telemetry...</span>
                        </div>
                      ) : (
                        <div className="space-y-3">
                          {/* Models Quota Table */}
                          <div className="space-y-1.5">
                            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                              Active Multi-Model Daily Free-Tier Quota (UTC)
                            </span>
                            <div className="grid gap-1.5">
                              {quotaData?.models.map((m) => {
                                const reqPct = Math.min(100, m.requests_pct_used || 0);
                                const tokPct = Math.min(100, m.tokens_pct_used || 0);
                                return (
                                  <div
                                    key={m.model_id}
                                    className="bg-slate-950/80 border border-white/[0.04] rounded-xl p-2.5 space-y-1.5 text-xs font-mono"
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center space-x-1.5">
                                        <span className={`text-[9px] px-1.5 py-0.2 rounded font-bold uppercase ${
                                          m.provider === "groq"
                                            ? "bg-orange-950/80 text-orange-400 border border-orange-800/60"
                                            : "bg-blue-950/80 text-blue-400 border border-blue-800/60"
                                        }`}>
                                          {m.provider}
                                        </span>
                                        <span className="text-slate-200 font-semibold">{m.model_id}</span>
                                      </div>
                                      <span className="text-[10px] text-slate-400">
                                        {m.requests_remaining} reqs left
                                      </span>
                                    </div>

                                    {/* Requests Progress */}
                                    <div className="space-y-0.5">
                                      <div className="flex justify-between text-[10px] text-slate-400">
                                        <span>Requests: {m.requests_used} / {m.daily_request_limit}</span>
                                        <span>{reqPct}%</span>
                                      </div>
                                      <div className="h-1.5 w-full bg-slate-900 rounded-full overflow-hidden">
                                        <div
                                          className={`h-full transition-all duration-300 ${
                                            reqPct > 80 ? "bg-rose-500" : reqPct > 50 ? "bg-amber-500" : "bg-cyan-500"
                                          }`}
                                          style={{ width: `${reqPct}%` }}
                                        />
                                      </div>
                                    </div>

                                    {/* Tokens */}
                                    <div className="flex justify-between text-[10px] text-slate-500">
                                      <span>Tokens: {m.total_tokens.toLocaleString()} / {m.daily_token_limit.toLocaleString()}</span>
                                      <span>{tokPct}%</span>
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          </div>

                          {/* Knowledge Distillation Engine Status */}
                          <div className="bg-cyan-950/30 border border-cyan-500/20 rounded-xl p-3 space-y-2">
                            <div className="flex items-center justify-between">
                              <div className="flex items-center space-x-1.5">
                                <Database className="w-3.5 h-3.5 text-cyan-400" />
                                <span className="text-xs font-mono font-bold text-cyan-200">
                                  Student Knowledge Distillation (Offline)
                                </span>
                              </div>
                              <span className="text-[9px] px-1.5 py-0.5 rounded font-mono bg-cyan-900/60 text-cyan-300 border border-cyan-700/50 uppercase font-semibold">
                                {quotaData?.distillation?.model_status || "ACTIVE"}
                              </span>
                            </div>

                            <div className="grid grid-cols-2 gap-2 text-[11px] font-mono">
                              <div className="bg-slate-950/70 p-2 rounded-lg border border-white/[0.04]">
                                <span className="text-slate-500 block text-[9px]">Corpus Size</span>
                                <span className="text-white font-bold">
                                  {quotaData?.distillation?.corpus_size ?? quotaData?.distillation?.trace_count ?? 0} Traces
                                </span>
                              </div>
                              <div className="bg-slate-950/70 p-2 rounded-lg border border-white/[0.04]">
                                <span className="text-slate-500 block text-[9px]">Vocabulary Size</span>
                                <span className="text-white font-bold">
                                  {quotaData?.distillation?.vocabulary_size ?? 0} Terms
                                </span>
                              </div>
                            </div>

                            {distillSuccessMessage && (
                              <div className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 border border-emerald-500/30 px-2 py-1 rounded-lg">
                                ✓ {distillSuccessMessage}
                              </div>
                            )}

                            <button
                              type="button"
                              onClick={handleTriggerDistillation}
                              disabled={isDistilling}
                              className="w-full py-1.5 px-3 rounded-lg bg-cyan-500/15 hover:bg-cyan-500/25 border border-cyan-500/40 text-cyan-300 font-mono text-[11px] font-bold flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
                            >
                              {isDistilling ? (
                                <>
                                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                                  <span>Training Student Tournament...</span>
                                </>
                              ) : (
                                <>
                                  <Zap className="w-3.5 h-3.5" />
                                  <span>Train Distillation Engine Now</span>
                                </>
                              )}
                            </button>
                          </div>

                          {/* Live External APIs & Alert Feeds */}
                          <div className="space-y-1.5">
                            <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500 block">
                              Live External APIs & Alert Feeds (Today UTC)
                            </span>
                            {(!quotaData?.external_apis || quotaData.external_apis.length === 0) ? (
                              <div className="bg-slate-950/60 border border-white/[0.04] rounded-xl p-2.5 text-center text-[11px] font-mono text-slate-500">
                                Monitored: Telegram Bot, Web Push, Yahoo Finance & News Feeds.
                              </div>
                            ) : (
                              <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
                                {quotaData.external_apis.map((ext, idx) => (
                                  <div
                                    key={`${ext.service_name}-${ext.endpoint_or_model}-${idx}`}
                                    className="bg-slate-950/80 border border-white/[0.04] rounded-xl p-2 space-y-1 text-xs font-mono"
                                  >
                                    <div className="flex items-center justify-between">
                                      <span className={`text-[9px] px-1.5 py-0.5 rounded font-bold uppercase ${
                                        ext.service_name === "telegram"
                                          ? "bg-sky-950 text-sky-400 border border-sky-800"
                                          : ext.service_name === "web_push"
                                          ? "bg-purple-950 text-purple-400 border border-purple-800"
                                          : ext.service_name === "yfinance"
                                          ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                                          : "bg-amber-950 text-amber-400 border border-amber-800"
                                      }`}>
                                        {ext.service_name}
                                      </span>
                                      <span className="text-[9px] text-slate-400 truncate max-w-[110px]" title={ext.endpoint_or_model}>
                                        {ext.endpoint_or_model}
                                      </span>
                                    </div>
                                    <div className="flex items-center justify-between text-[10px]">
                                      <span className="text-slate-300">
                                        ✓ {ext.calls_succeeded} ok
                                        {ext.calls_failed > 0 && (
                                          <span className="text-rose-400 ml-1">({ext.calls_failed} fail)</span>
                                        )}
                                      </span>
                                      <span className="text-slate-400">
                                        {ext.units_processed} {ext.service_name === "yfinance" ? "syms" : ext.service_name === "news_&_filings" ? "items" : "units"}
                                      </span>
                                    </div>
                                    {ext.rate_limit_hits > 0 && (
                                      <div className="text-[9px] text-rose-400 font-semibold">
                                        ⚠️ {ext.rate_limit_hits} rate limit hits
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            )}
                          </div>
                        </div>
                      )}
                    </motion.div>
                  )}
                </AnimatePresence>

                {/* 1-Click Action Chips (Single Horizontal Scrollable Row with Thin Scrollbar) */}
                <div className="overflow-x-auto thin-scrollbar pb-1.5 flex items-center gap-2 flex-nowrap">
                  {/* ML Forecast Dock Toggle Pill */}
                  {mlForecast && !mlForecast.error && (
                    <button
                      type="button"
                      onClick={toggleMlPanel}
                      className="px-2.5 py-1.5 rounded-xl bg-indigo-950/60 hover:bg-indigo-950/90 border border-indigo-500/40 hover:border-indigo-400/70 text-[11px] font-mono text-indigo-300 transition-all flex items-center space-x-1.5 whitespace-nowrap shrink-0 shadow-sm"
                    >
                      <Cpu className="w-3.5 h-3.5 text-indigo-400" />
                      <span className="font-bold">ML Forecast</span>
                      {(() => {
                        const fc20 = mlForecast.forecasts?.["20D"];
                        const ret20 = fc20?.expected_return_pct;
                        const retStr = ret20 !== undefined ? `${ret20 >= 0 ? "+" : ""}${ret20.toFixed(2)}%` : null;
                        return (
                          <span className="text-[10px] text-indigo-200 font-semibold px-1 py-0.2 rounded bg-indigo-900/50">
                            {retStr ? `20D: ${retStr}` : ""} · {mlForecast.conviction_score ?? 70}/100
                          </span>
                        );
                      })()}
                      {showMlPanel ? (
                        <ChevronDown className="w-3 h-3 text-indigo-400" />
                      ) : (
                        <ChevronRight className="w-3 h-3 text-indigo-400" />
                      )}
                    </button>
                  )}

                  {/* Quotas & Engine Dock Toggle Pill */}
                  <button
                    type="button"
                    onClick={toggleQuotaPanel}
                    className="px-2.5 py-1.5 rounded-xl bg-slate-900/80 hover:bg-slate-800 border border-white/[0.08] hover:border-cyan-500/40 text-[11px] font-mono text-slate-300 transition-all flex items-center space-x-1.5 whitespace-nowrap shrink-0 shadow-sm"
                  >
                    <Gauge className="w-3.5 h-3.5 text-cyan-400" />
                    <span className="font-bold">Quotas & Engine</span>
                    {showQuotaPanel ? (
                      <ChevronDown className="w-3 h-3 text-cyan-400" />
                    ) : (
                      <ChevronRight className="w-3 h-3 text-slate-400" />
                    )}
                  </button>

                  <button
                    onClick={() => runDeliberation(effectiveSymbol ? `Direct Alpha Brief for ${effectiveSymbol}` : "Direct Alpha Brief")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-cyan-500/10 border border-white/[0.08] hover:border-cyan-500/40 text-[11px] font-mono text-cyan-300 transition-all flex items-center space-x-1.5 whitespace-nowrap shrink-0"
                  >
                    <BarChart3 className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Direct Alpha Brief</span>
                  </button>

                  <button
                    onClick={() => runDeliberation("Debate Bull vs Bear Thesis")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-emerald-500/10 border border-white/[0.08] hover:border-emerald-500/40 text-[11px] font-mono text-emerald-300 transition-all flex items-center space-x-1.5 whitespace-nowrap shrink-0"
                  >
                    <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Bull vs Bear Debate</span>
                  </button>

                  <button
                    onClick={() => runDeliberation(effectiveSymbol ? `Compare ${effectiveSymbol} vs sector peer` : "Compare top market leaders")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-purple-500/10 border border-white/[0.08] hover:border-purple-500/40 text-[11px] font-mono text-purple-300 transition-all flex items-center space-x-1.5 whitespace-nowrap shrink-0"
                  >
                    <Layers className="w-3.5 h-3.5 text-purple-400" />
                    <span>Compare vs Sector Peer</span>
                  </button>

                  <button
                    onClick={() => runDeliberation("Review my watchlist")}
                    disabled={state.stage !== "idle" && state.stage !== "complete" && state.stage !== "error"}
                    className="px-3 py-1.5 rounded-xl bg-white/[0.04] hover:bg-amber-500/10 border border-white/[0.08] hover:border-amber-500/40 text-[11px] font-mono text-amber-300 transition-all flex items-center space-x-1.5 whitespace-nowrap shrink-0"
                  >
                    <Activity className="w-3.5 h-3.5 text-amber-400" />
                    <span>Review Watchlist</span>
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
                        effectiveSymbol
                          ? `Ask Quant Copilot about ${effectiveSymbol}...`
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
