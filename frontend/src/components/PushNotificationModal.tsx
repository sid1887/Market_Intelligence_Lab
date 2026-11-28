"use client";

import React, { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import {
  Bell,
  BellRing,
  CheckCircle2,
  AlertCircle,
  X,
  Smartphone,
  Zap,
  Radio,
  Send,
  Loader2,
  ShieldCheck,
  SlidersHorizontal,
} from "lucide-react";
import {
  checkPushSubscription,
  autoSyncPushSubscription,
  subscribeToWebPush,
  sendTestPushAlert,
  PushPermissionStatus,
} from "@/lib/pushNotifications";
import { cn } from "@/lib/utils";

export interface NotificationPreferences {
  minMovePct: number;
  minRvol: number;
  scope: "all" | "holdings_only";
}

export const DEFAULT_PUSH_PREFS: NotificationPreferences = {
  minMovePct: 3.0,
  minRvol: 2.5,
  scope: "all",
};

interface PushNotificationModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubscriptionChange?: (isSubscribed: boolean) => void;
}

export default function PushNotificationModal({
  isOpen,
  onClose,
  onSubscriptionChange,
}: PushNotificationModalProps) {
  const [permission, setPermission] = useState<PushPermissionStatus>("default");
  const [isSubscribed, setIsSubscribed] = useState(false);
  const [supported, setSupported] = useState(true);
  const [loading, setLoading] = useState(false);
  const [testLoading, setTestLoading] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error" | "info"; text: string } | null>(null);
  const [prefs, setPrefs] = useState<NotificationPreferences>(() => {
    if (typeof window !== "undefined") {
      try {
        const stored = localStorage.getItem("mil:push-preferences");
        if (stored) return JSON.parse(stored);
      } catch {}
    }
    return DEFAULT_PUSH_PREFS;
  });

  const updatePref = <K extends keyof NotificationPreferences>(key: K, value: NotificationPreferences[K]) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      try {
        localStorage.setItem("mil:push-preferences", JSON.stringify(next));
      } catch {}
      return next;
    });
  };

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  useEffect(() => {
    if (isOpen) {
      if (typeof window !== "undefined" && "Notification" in window && Notification.permission === "granted") {
        autoSyncPushSubscription().then((res) => {
          setSupported(true);
          setPermission(res.permission);
          setIsSubscribed(res.isSubscribed);
          onSubscriptionChange?.(res.isSubscribed);
        });
      } else {
        checkPushSubscription().then((res) => {
          setSupported(res.supported);
          setPermission(res.permission);
          setIsSubscribed(res.isSubscribed);
        });
      }
    }
  }, [isOpen, onSubscriptionChange]);

  const handleSubscribe = async () => {
    setLoading(true);
    setFeedback(null);
    try {
      const res = await subscribeToWebPush();
      if (res.success) {
        setIsSubscribed(true);
        setPermission("granted");
        setFeedback({
          type: "success",
          text: "Mobile Web Push successfully activated! Real-time causal market intelligence connected.",
        });
        onSubscriptionChange?.(true);
      } else {
        setFeedback({
          type: "error",
          text: res.error || "Subscription failed. Please check browser permissions.",
        });
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setFeedback({ type: "error", text: msg });
    } finally {
      setLoading(false);
    }
  };

  const handleTestAlert = async () => {
    setTestLoading(true);
    setFeedback(null);
    try {
      const res = await sendTestPushAlert();
      if (res.success) {
        setFeedback({
          type: "success",
          text: res.message || "Test alert dispatched! Check your notification tray.",
        });
      } else {
        setFeedback({
          type: "error",
          text: res.message || "Failed to deliver test alert.",
        });
      }
    } finally {
      setTestLoading(false);
    }
  };

  if (!isOpen) return null;

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        {/* Backdrop */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/80"
        />

        {/* Modal Window */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.2 }}
          className="relative w-full max-w-lg bg-[#06090f] border border-white/[0.1] rounded-2xl p-6 shadow-2xl text-slate-100 font-mono space-y-5 overflow-hidden"
        >
          {/* Top specular highlight edge */}
          <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-cyan-400/50 to-transparent" />

          {/* Header */}
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
            <div className="flex items-center space-x-3">
              <div className="p-2 rounded-xl bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.25)]">
                {isSubscribed ? <BellRing className="w-5 h-5" /> : <Bell className="w-5 h-5" />}
              </div>
              <div>
                <h2 className="text-sm font-bold text-white tracking-wide">
                  Mobile Push &amp; Causal Catalyst Radar
                </h2>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Native Web Push · RFC 8292 Encrypted Delivery
                </p>
              </div>
            </div>

            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.05] transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Connection Status Banner */}
          <div className="flex items-center justify-between p-3.5 rounded-xl bg-[#090f1d]/90 border border-white/[0.08]">
            <div className="flex items-center space-x-2.5">
              <span className="relative flex h-2.5 w-2.5">
                {isSubscribed ? (
                  <>
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500" />
                  </>
                ) : (
                  <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-amber-400" />
                )}
              </span>
              <span className="text-xs font-semibold text-slate-200">
                {isSubscribed
                  ? "Connected & Receiving Causal Market Pulse"
                  : permission === "denied"
                  ? "Notifications Blocked in Browser"
                  : "Notifications Standby"}
              </span>
            </div>

            <span
              className={`text-[10px] px-2 py-0.5 rounded-full font-bold uppercase tracking-wider border ${
                isSubscribed
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-500/50 shadow-[0_0_10px_rgba(16,185,129,0.2)]"
                  : "bg-amber-950/80 text-amber-300 border-amber-500/50"
              }`}
            >
              {isSubscribed ? "Active" : permission}
            </span>
          </div>

          {/* Feature Pillars */}
          <div className="space-y-2.5 text-xs">
            <div className="flex items-start space-x-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <Radio className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
              <div>
                <span className="text-white font-bold block">Intraday Anomaly Detection</span>
                <span className="text-[11px] text-slate-400 leading-relaxed block mt-0.5">
                  Instant push delivery when a priority equity moves &ge; 3.0% or exhibits &ge; 2.5x relative volume surge.
                </span>
              </div>
            </div>

            <div className="flex items-start space-x-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="text-white font-bold block">4-Pillar Causal Synthesis</span>
                <span className="text-[11px] text-slate-400 leading-relaxed block mt-0.5">
                  Synthesizes Price Velocity, Sector Basket Topology, SEBI Corporate Filings, and Live News Wire.
                </span>
              </div>
            </div>

            <div className="flex items-start space-x-3 p-2.5 rounded-xl bg-white/[0.02] border border-white/[0.04]">
              <Smartphone className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
              <div>
                <span className="text-white font-bold block">Zero-Cache Host Pass-Through</span>
                <span className="text-[11px] text-slate-400 leading-relaxed block mt-0.5">
                  Host PC updates reflect immediately on phone without stale PWA cache conflicts.
                </span>
              </div>
            </div>
          </div>

          {/* Feedback Alert */}
          {feedback && (
            <motion.div
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className={`p-3 rounded-xl border text-xs flex items-center space-x-2 ${
                feedback.type === "success"
                  ? "bg-emerald-950/60 border-emerald-500/50 text-emerald-300"
                  : "bg-rose-950/60 border-rose-500/50 text-rose-300"
              }`}
            >
              {feedback.type === "success" ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
              )}
              <span>{feedback.text}</span>
            </motion.div>
          )}

          {/* Notification Threshold Preferences (L12) */}
          <div className="p-3.5 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-3 font-mono text-xs">
            <div className="flex items-center justify-between pb-2 border-b border-white/[0.04]">
              <span className="flex items-center gap-1.5 text-slate-300 font-bold">
                <SlidersHorizontal className="w-3.5 h-3.5 text-cyan-400" />
                Alert Thresholds &amp; Channel Scope
              </span>
              <span className="text-[10px] text-cyan-400">Auto-saved</span>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[11px]">
              <div>
                <label className="text-slate-400 block mb-1">Price Anomaly Trigger</label>
                <div className="grid grid-cols-3 gap-1">
                  {[2.0, 3.0, 5.0].map((val) => (
                    <button
                      key={val}
                      onClick={() => updatePref("minMovePct", val)}
                      className={cn(
                        "py-1 px-1.5 rounded-lg border text-center transition-colors",
                        prefs.minMovePct === val
                          ? "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 font-bold"
                          : "border-white/[0.06] text-slate-400 hover:bg-white/[0.03]"
                      )}
                    >
                      &ge; {val.toFixed(1)}%
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label className="text-slate-400 block mb-1">RVOL Surge Trigger</label>
                <div className="grid grid-cols-3 gap-1">
                  {[1.5, 2.5, 4.0].map((val) => (
                    <button
                      key={val}
                      onClick={() => updatePref("minRvol", val)}
                      className={cn(
                        "py-1 px-1.5 rounded-lg border text-center transition-colors",
                        prefs.minRvol === val
                          ? "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 font-bold"
                          : "border-white/[0.06] text-slate-400 hover:bg-white/[0.03]"
                      )}
                    >
                      &ge; {val.toFixed(1)}x
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div>
              <label className="text-slate-400 block mb-1 text-[11px]">Universe Alert Scope</label>
              <div className="grid grid-cols-2 gap-1.5 text-[11px]">
                <button
                  onClick={() => updatePref("scope", "all")}
                  className={cn(
                    "py-1.5 px-2 rounded-lg border text-left transition-colors",
                    prefs.scope === "all"
                      ? "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 font-bold"
                      : "border-white/[0.06] text-slate-400 hover:bg-white/[0.03]"
                  )}
                >
                  All 1,143 Equities
                </button>
                <button
                  onClick={() => updatePref("scope", "holdings_only")}
                  className={cn(
                    "py-1.5 px-2 rounded-lg border text-left transition-colors",
                    prefs.scope === "holdings_only"
                      ? "bg-cyan-950/80 border-cyan-500/50 text-cyan-300 font-bold"
                      : "border-white/[0.06] text-slate-400 hover:bg-white/[0.03]"
                  )}
                >
                  Watchlist &amp; Portfolio Only
                </button>
              </div>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center justify-end space-x-3 pt-2 border-t border-white/[0.08]">
            {isSubscribed ? (
              <button
                onClick={handleTestAlert}
                disabled={testLoading}
                className="flex items-center space-x-2 px-4 py-2.5 rounded-xl bg-cyan-950/80 hover:bg-cyan-900 border border-cyan-500/50 text-cyan-200 text-xs font-bold transition-all shadow-[0_0_15px_rgba(6,182,212,0.2)]"
              >
                {testLoading ? (
                  <Loader2 className="w-4 h-4 animate-spin text-cyan-400" />
                ) : (
                  <Send className="w-4 h-4 text-cyan-400" />
                )}
                <span>Send Test Alert to Phone</span>
              </button>
            ) : (
              <button
                onClick={handleSubscribe}
                disabled={loading || !supported}
                className="flex items-center space-x-2 px-5 py-2.5 rounded-xl bg-gradient-to-r from-cyan-600 via-cyan-500 to-emerald-500 hover:from-cyan-500 hover:to-emerald-400 text-black text-xs font-bold transition-all shadow-[0_0_20px_rgba(6,182,212,0.3)] disabled:opacity-50"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <Zap className="w-4 h-4" />
                )}
                <span>Enable Mobile Push Notifications</span>
              </button>
            )}

            <button
              onClick={onClose}
              className="px-4 py-2.5 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] text-slate-300 text-xs font-medium border border-white/[0.06] transition-colors"
            >
              Close
            </button>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  );
}
