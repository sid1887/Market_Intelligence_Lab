"use client";

import React, { useState, useCallback } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  LayoutDashboard,
  BookmarkCheck,
  Search,
  LineChart,
  Briefcase,
  Loader2,
  CheckCircle2,
  AlertCircle,
  Zap,
  BrainCircuit,
  Bell,
  BellRing,
} from "lucide-react";
import { submitJob, clearMemoryCache } from "@/lib/api";
import { useJobStream } from "@/hooks/useJobStream";
import { cn } from "@/lib/utils";
import PushNotificationModal from "./PushNotificationModal";
import { checkPushSubscription } from "@/lib/pushNotifications";

const NAV_LINKS = [
  { href: "/", label: "Screener", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/backtest", label: "Backtester", icon: LineChart },
];

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [searchQuery, setSearchQuery] = useState("");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [isPushSubscribed, setIsPushSubscribed] = useState(false);

  React.useEffect(() => {
    checkPushSubscription().then((res) => {
      setIsPushSubscribed(res.isSubscribed);
    });
  }, []);

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

  const { status, progress } = useJobStream(activeJobId, {
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
    <header className="sticky top-0 z-40 border-b border-white/[0.08] bg-[#040609]/85 backdrop-blur-2xl transition-all">
      <div className="max-w-[1600px] mx-auto px-3 sm:px-6 h-14 flex items-center justify-between gap-3 sm:gap-4">
        {/* Brand Terminal Identity */}
        <div className="flex items-center space-x-3 shrink-0">
          <Link href="/" className="flex items-center space-x-2.5 group">
            <div className="w-8 h-8 rounded-lg bg-gradient-to-tr from-cyan-500 via-teal-500 to-indigo-600 flex items-center justify-center shadow-[0_0_15px_rgba(6,182,212,0.35)] group-hover:scale-105 transition-transform duration-200">
              <Activity className="w-4 h-4 text-white" />
            </div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-sm sm:text-base text-slate-100 tracking-tight font-mono">
                MIL<span className="text-cyan-400 font-sans hidden md:inline">.QUANT</span>
              </span>
              <span className="text-[10px] px-1.5 py-0.2 rounded font-mono bg-cyan-950/80 text-cyan-400 border border-cyan-800/60 hidden sm:inline">
                V8
              </span>
            </div>
          </Link>
        </div>

        {/* Global Search Bar (Obsidian Glass) */}
        <form onSubmit={handleSearch} className="flex-1 max-w-sm relative hidden md:block">
          <div className="relative flex items-center">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search ticker (e.g. TATAPOWER, RVNL)..."
              className="w-full bg-white/[0.03] hover:bg-white/[0.05] focus:bg-[#070b12] border border-white/[0.08] focus:border-cyan-500/50 rounded-xl pl-9 pr-14 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none transition-all font-mono"
            />
            <div className="absolute right-2 flex items-center gap-1">
              <kbd className="text-[9px] font-mono text-slate-500 bg-white/[0.04] px-1 py-0.5 rounded border border-white/[0.06]">
                ↵
              </kbd>
            </div>
          </div>
        </form>

        {/* Navigation Tabs with Framer Motion Spring Layout Indicator */}
        <nav className="flex items-center space-x-1 sm:space-x-1.5 bg-white/[0.02] border border-white/[0.06] p-1 rounded-xl backdrop-blur-md">
          {NAV_LINKS.map(({ href, label, icon: Icon }) => {
            const isActive = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                className={cn(
                  "relative px-3 py-1.5 text-xs font-mono font-medium rounded-lg transition-colors flex items-center gap-1.5",
                  isActive ? "text-cyan-300 font-semibold" : "text-slate-400 hover:text-slate-200"
                )}
              >
                {isActive && (
                  <motion.div
                    layoutId="navbar-tab-indicator"
                    className="absolute inset-0 bg-cyan-950/60 border border-cyan-500/40 rounded-lg shadow-[0_0_15px_rgba(6,182,212,0.25)]"
                    transition={{ type: "spring", stiffness: 400, damping: 30 }}
                  />
                )}
                <Icon className="w-3.5 h-3.5 relative z-10" />
                <span className="relative z-10 hidden sm:inline">{label}</span>
              </Link>
            );
          })}
        </nav>

        {/* Action Buttons: Copilot ⌘J & Ingestion Status */}
        <div className="flex items-center space-x-2 shrink-0">
          {/* Quick Tickers */}
          <Link
            href="/stocks/SUZLON"
            className="hidden xl:flex items-center gap-1 px-2.5 py-1 text-xs font-mono text-slate-400 hover:text-emerald-300 bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.06] rounded-lg transition-colors"
          >
            <BookmarkCheck className="w-3 h-3 text-emerald-400" />
            <span>SUZLON</span>
          </Link>

          {/* Copilot ⌘J Trigger */}
          <button
            onClick={() => {
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "j", metaKey: true }));
            }}
            title="Open Quant Copilot Committee (⌘J)"
            className="flex items-center gap-1.5 text-xs font-mono text-cyan-300 px-2.5 py-1.5 rounded-xl bg-white/[0.04] hover:bg-cyan-950/40 border border-white/[0.08] hover:border-cyan-500/40 transition-all shadow-sm"
          >
            <BrainCircuit className="w-3.5 h-3.5 text-cyan-400" />
            <span className="hidden sm:inline">Copilot</span>
            <kbd className="text-[10px] text-cyan-400/80 bg-slate-900/80 px-1 rounded border border-cyan-500/20">
              ⌘J
            </kbd>
          </button>

          {/* Mobile Web Push & Causal Radar Notification Bell */}
          <button
            onClick={() => setIsPushModalOpen(true)}
            title={
              isPushSubscribed
                ? "Mobile Web Push Connected (Causal Radar Active)"
                : "Enable Mobile Web Push & Causal Catalyst Alerts"
            }
            className="relative flex items-center justify-center p-2 rounded-xl bg-white/[0.04] hover:bg-cyan-950/40 border border-white/[0.08] hover:border-cyan-500/40 text-slate-300 hover:text-cyan-300 transition-all shadow-sm"
          >
            {isPushSubscribed ? (
              <BellRing className="w-4 h-4 text-cyan-400" />
            ) : (
              <Bell className="w-4 h-4 text-slate-400" />
            )}

            {/* Active Indicator Pulse Dot */}
            <span className="absolute top-1 right-1 flex h-2 w-2">
              {isPushSubscribed ? (
                <>
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                  <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                </>
              ) : (
                <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400/60" />
              )}
            </span>
          </button>

          {/* Real-time Durable Job Engine Status / Action Button */}
          <button
            onClick={handleIngest}
            disabled={isSubmitting || (activeJobId !== null && (status === "RUNNING" || status === "QUEUED"))}
            title={
              activeJobId
                ? `Job ${activeJobId}: ${status} (${progress}%)`
                : "Execute Universal Dynamic Ingestion via V8 Durable Asynchronous Engine"
            }
            className={cn(
              "flex items-center space-x-1.5 px-3 py-1.5 rounded-xl text-xs font-mono font-medium transition-all border",
              status === "SUCCEEDED"
                ? "bg-emerald-950/60 border-emerald-500/60 text-emerald-300 shadow-[0_0_15px_rgba(16,185,129,0.2)]"
                : status === "FAILED"
                ? "bg-rose-950/60 border-rose-500/60 text-rose-300 shadow-[0_0_15px_rgba(244,63,94,0.2)]"
                : activeJobId && (status === "RUNNING" || status === "QUEUED")
                ? "bg-cyan-950/60 border-cyan-500/60 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.2)]"
                : "bg-white/[0.04] hover:bg-emerald-950/30 text-emerald-300 hover:text-emerald-200 border-white/[0.08] hover:border-emerald-500/40"
            )}
          >
            {isSubmitting ? (
              <>
                <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                <span className="hidden sm:inline">Dispatching...</span>
              </>
            ) : status === "SUCCEEDED" ? (
              <>
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                <span>Settled 100%</span>
              </>
            ) : status === "FAILED" ? (
              <>
                <AlertCircle className="w-3.5 h-3.5 text-rose-400" />
                <span>Failed</span>
              </>
            ) : activeJobId && (status === "RUNNING" || status === "QUEUED") ? (
              <>
                <Loader2 className="w-3.5 h-3.5 text-cyan-400 animate-spin" />
                <span>{progress}%</span>
              </>
            ) : (
              <>
                <Zap className="w-3.5 h-3.5 text-emerald-400" />
                <span className="hidden sm:inline">Dynamic Ingest</span>
                <span className="sm:hidden">Ingest</span>
              </>
            )}
          </button>
        </div>
      </div>

      {/* Native Web Push & Causal Radar Modal */}
      <PushNotificationModal
        isOpen={isPushModalOpen}
        onClose={() => setIsPushModalOpen(false)}
        onSubscriptionChange={(sub) => setIsPushSubscribed(sub)}
      />
    </header>
  );
}
