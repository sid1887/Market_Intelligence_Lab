"use client";

import React, { useState } from "react";
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
  BrainCircuit,
  Bell,
  BellRing,
} from "lucide-react";
import { cn } from "@/lib/utils";
import IngestStatusButton from "./IngestStatusButton";
import PushNotificationModal from "./PushNotificationModal";
import { checkPushSubscription, autoSyncPushSubscription } from "@/lib/pushNotifications";

const NAV_LINKS = [
  { href: "/", label: "Screener", icon: LayoutDashboard },
  { href: "/portfolio", label: "Portfolio", icon: Briefcase },
  { href: "/backtest", label: "Backtester", icon: LineChart },
];

export default function Navbar() {
  const router = useRouter();
  const pathname = usePathname();
  const [searchQuery, setSearchQuery] = useState("");
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [isPushSubscribed, setIsPushSubscribed] = useState(false);

  React.useEffect(() => {
    if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
      autoSyncPushSubscription().then((res) => {
        setIsPushSubscribed(res.isSubscribed);
      });
    } else {
      checkPushSubscription().then((res) => {
        setIsPushSubscribed(res.isSubscribed);
      });
    }
  }, []);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    const sym = searchQuery.trim().toUpperCase();
    if (sym) {
      router.push(`/stocks/${sym}`);
      setSearchQuery("");
    }
  };

  return (
    <header className="sticky top-0 z-40 border-b border-white/[0.08] bg-[#040609] transition-all">
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

        {/* Navigation Tabs with Framer Motion Spring Layout Indicator (Desktop) */}
        <nav className="hidden md:flex items-center space-x-1 sm:space-x-1.5 bg-[#080c14] border border-white/[0.06] p-1 rounded-xl">
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

          {/* Real-time Durable Job Engine Status / Action Button (Isolated) */}
          <IngestStatusButton />
        </div>
      </div>

      {/* Native Web Push & Causal Radar Modal */}
      <PushNotificationModal
        isOpen={isPushModalOpen}
        onClose={() => setIsPushModalOpen(false)}
        onSubscriptionChange={(sub) => setIsPushSubscribed(sub)}
      />

      {/* ──────────────── FIXED MOBILE BOTTOM NAVIGATION BAR (< 768px) ──────────────── */}
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-40 bg-[#040609] border-t border-white/[0.08] px-2 py-1.5 flex items-center justify-around pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        {NAV_LINKS.map(({ href, label, icon: Icon }) => {
          const isActive = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={cn(
                "flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono transition-colors",
                isActive
                  ? "text-cyan-300 font-bold bg-cyan-950/40"
                  : "text-slate-400 hover:text-slate-200"
              )}
            >
              <Icon className={cn("w-4 h-4 mb-0.5", isActive ? "text-cyan-400" : "text-slate-400")} />
              <span>{label}</span>
            </Link>
          );
        })}

        {/* Dynamic Ingest Quick Action in Bottom Bar */}
        <IngestStatusButton compact />
      </nav>
    </header>
  );
}
