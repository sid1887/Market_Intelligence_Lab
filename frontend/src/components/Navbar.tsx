"use client";

import React, { useState } from "react";
import Link from "next/link";
import { useRouter, usePathname } from "next/navigation";
import { motion } from "framer-motion";
import {
  Activity,
  LayoutDashboard,
  Search,
  LineChart,
  Briefcase,
  BrainCircuit,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { milEvents } from "@/lib/store";
import IngestStatusButton from "./IngestStatusButton";
import PushNotificationModal from "./PushNotificationModal";
import NotificationCenterPopover from "./NotificationCenterPopover";
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
    const sym = searchQuery.trim().toUpperCase().replace(/[^A-Z0-9_-]/g, "");
    if (sym && sym.length >= 2) {
      router.push(`/stocks/${sym}`);
      setSearchQuery("");
    } else {
      // Trigger Command Palette for universe search
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
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
          {/* Command Palette ⌘K Quick Access */}
          <button
            onClick={() => {
              window.dispatchEvent(new KeyboardEvent("keydown", { key: "k", metaKey: true }));
            }}
            title="Open Command Palette (⌘K)"
            className="hidden xl:flex items-center gap-1.5 px-2.5 py-1 text-xs font-mono text-slate-400 hover:text-cyan-300 bg-white/[0.02] hover:bg-white/[0.05] border border-white/[0.06] rounded-lg transition-colors"
          >
            <Search className="w-3 h-3 text-cyan-400" />
            <span>Search</span>
            <kbd className="text-[9px] text-slate-500 bg-black/40 px-1 py-0.2 rounded border border-white/[0.08]">
              ⌘K
            </kbd>
          </button>

          {/* Copilot ⌘J Trigger */}
          <button
            onClick={() => {
              milEvents.emit("mil:open-copilot");
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

          {/* Mobile Web Push & Causal Radar Notification Center */}
          <NotificationCenterPopover
            isPushSubscribed={isPushSubscribed}
            onOpenPushSettings={() => setIsPushModalOpen(true)}
          />

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

        {/* Mobile Copilot Trigger Button (H1) */}
        <button
          onClick={() => milEvents.emit("mil:open-copilot")}
          className="flex flex-col items-center justify-center py-1 px-3 rounded-lg text-[10px] font-mono transition-colors text-slate-400 hover:text-cyan-300 active:scale-95"
          aria-label="Toggle Quant Copilot Drawer"
        >
          <BrainCircuit className="w-4 h-4 mb-0.5 text-cyan-400" />
          <span>Copilot</span>
        </button>

        {/* Dynamic Ingest Quick Action in Bottom Bar */}
        <IngestStatusButton compact />
      </nav>
    </header>
  );
}
