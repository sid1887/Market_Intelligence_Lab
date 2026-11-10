"use client";

import React, { useState, useCallback } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import {
  Activity,
  LayoutDashboard,
  BookmarkCheck,
  Search,
  ArrowRight,
  LineChart,
  Briefcase,
  Loader2,
  CheckCircle2,
  AlertCircle
} from "lucide-react";
import { submitJob, clearMemoryCache } from "@/lib/api";
import { useJobStream } from "@/hooks/useJobStream";

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleJobComplete = useCallback(() => {
    clearMemoryCache();
    router.refresh();
    setTimeout(() => {
      setActiveJobId(null);
    }, 4000);
  }, [router]);

  const handleJobError = useCallback(() => {
    setTimeout(() => {
      setActiveJobId(null);
    }, 6000);
  }, []);

  const { status, progress, stage, error } = useJobStream(activeJobId, {
    onComplete: handleJobComplete,
    onError: handleJobError,
    autoCloseOnTerminal: true,
  });

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = searchQuery.trim().toUpperCase();
    if (sym) {
      router.push(`/stocks/${sym}`);
      setSearchQuery("");
    }
  };

  const handleIngest = async () => {
    if (isSubmitting || (activeJobId && (status === "RUNNING" || status === "QUEUED"))) {
      return;
    }
    setIsSubmitting(true);
    try {
      const todayIso = new Date().toISOString().slice(0, 10);
      const idempotencyKey = `universe-eod-${todayIso}-${Date.now()}`;
      const res = await submitJob({
        job_type: "UNIVERSE_EOD",
        payload: { date: todayIso, run_factors: true },
        idempotency_key: idempotencyKey,
      });
      setActiveJobId(res.job_id);
    } catch (err) {
      console.error("Failed to enqueue ingestion job:", err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/80 backdrop-blur-md sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between gap-4">
        <div className="flex items-center space-x-3 shrink-0">
          <Link href="/" className="flex items-center space-x-3 group">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-cyan-600 via-blue-600 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-900/30 group-hover:scale-105 transition-transform">
              <Activity className="w-5 h-5 text-white" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="font-bold text-lg text-slate-100 tracking-tight">Market Intelligence Lab</span>
                <span className="text-xs px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-400 border border-cyan-800/60 font-mono">
                  v2.0
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden lg:block">Universal NSE Quantitative Equity Terminal</p>
            </div>
          </Link>
        </div>

        {/* Global Universal Ticker Search */}
        <form onSubmit={handleSearch} className="flex-1 max-w-md relative hidden md:block">
          <div className="relative flex items-center">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search any NSE ticker (e.g. TATAPOWER, RVNL, NHPC)..."
              className="w-full bg-slate-900/90 border border-slate-700/80 rounded-lg pl-9 pr-10 py-1.5 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-cyan-500 focus:border-cyan-500 transition-all font-mono"
            />
            <button
              type="submit"
              className="absolute right-1.5 p-1 text-slate-400 hover:text-cyan-400 hover:bg-slate-800 rounded transition-colors"
              title="Search and Ingest"
            >
              <ArrowRight className="w-4 h-4" />
            </button>
          </div>
        </form>

        <nav className="flex items-center space-x-1.5 sm:space-x-2 shrink-0">
          <Link
            href="/"
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-sm font-medium transition-all duration-150 active:scale-[0.98] ${
              pathname === "/"
                ? "bg-slate-800 text-white shadow-sm border border-cyan-500/40"
                : "text-slate-300 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <LayoutDashboard className="w-4 h-4 text-cyan-400" />
            <span className="hidden sm:inline">Dashboard</span>
          </Link>
          <Link
            href="/backtest"
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-sm font-medium transition-all duration-150 active:scale-[0.98] ${
              pathname === "/backtest"
                ? "bg-slate-800 text-white shadow-sm border border-emerald-500/40"
                : "text-slate-300 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <LineChart className="w-4 h-4 text-emerald-400" />
            <span className="hidden sm:inline">Backtester</span>
          </Link>
          <Link
            href="/portfolio"
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-sm font-medium transition-all duration-150 active:scale-[0.98] ${
              pathname === "/portfolio"
                ? "bg-slate-800 text-white shadow-sm border border-amber-500/40"
                : "text-slate-300 hover:text-white hover:bg-slate-800/60"
            }`}
          >
            <Briefcase className="w-4 h-4 text-amber-400" />
            <span className="hidden sm:inline">Portfolio</span>
          </Link>
          <Link
            href="/stocks/SUZLON"
            className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors font-mono"
          >
            <BookmarkCheck className="w-4 h-4 text-emerald-400" />
            <span>SUZLON</span>
          </Link>
          <Link
            href="/stocks/INFY"
            className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium text-slate-300 hover:text-white hover:bg-slate-800/60 transition-colors font-mono hidden sm:flex"
          >
            <span>INFY</span>
          </Link>

          <div className="h-4 w-px bg-slate-800 hidden lg:block" />

          {/* Real-time Durable Job Engine Status / Action Pill */}
          <button
            onClick={handleIngest}
            disabled={isSubmitting || (activeJobId !== null && (status === "RUNNING" || status === "QUEUED"))}
            title={
              activeJobId
                ? `Job ${activeJobId}: ${status} (${progress}%)`
                : "Execute Universal Dynamic Ingestion via V8 Durable Asynchronous Engine"
            }
            className={`hidden lg:flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-mono transition-all border ${
              status === "SUCCEEDED"
                ? "bg-emerald-950/60 border-emerald-500/80 text-emerald-300 shadow-sm shadow-emerald-900/40"
                : status === "FAILED"
                ? "bg-rose-950/60 border-rose-500/80 text-rose-300 shadow-sm shadow-rose-900/40"
                : activeJobId && (status === "RUNNING" || status === "QUEUED")
                ? "bg-cyan-950/60 border-cyan-500/80 text-cyan-300 shadow-sm shadow-cyan-900/40"
                : "bg-emerald-950/40 hover:bg-emerald-900/60 border-emerald-800/40 hover:border-emerald-600/60 text-emerald-400"
            } disabled:cursor-not-allowed`}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                <span>Dispatching Job...</span>
              </>
            ) : status === "SUCCEEDED" ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Settlement Complete (100%)</span>
              </>
            ) : status === "FAILED" ? (
              <>
                <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
                <span className="truncate max-w-[140px]" title={error || "Job failed"}>
                  {error || "Ingestion Failed"}
                </span>
              </>
            ) : activeJobId && (status === "RUNNING" || status === "QUEUED") ? (
              <>
                <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                <span className="truncate max-w-[180px]">
                  {stage ? `${stage.replace(/_/g, " ")} (${progress}%)` : `Processing (${progress}%)`}
                </span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span>Universal Dynamic Ingestion</span>
              </>
            )}
          </button>
        </nav>
      </div>
    </header>
  );
}
