"use client";

import React, { useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Command, X, Keyboard } from "lucide-react";
import { useFocusTrap } from "@/hooks/useFocusTrap";

interface KeyboardShortcutModalProps {
  isOpen: boolean;
  onClose: () => void;
}

const SHORTCUT_GROUPS = [
  {
    category: "Global Terminal Navigation",
    items: [
      { keys: ["⌘", "K"], desc: "Open Command Palette / Universe Search" },
      { keys: ["⌘", "J"], desc: "Toggle Quant Copilot Committee Drawer" },
      { keys: ["?"], desc: "Toggle this Keyboard Shortcuts Cheatsheet" },
      { keys: ["Esc"], desc: "Close active drawer, modal, or overlay" },
    ],
  },
  {
    category: "Screener & Workspace",
    items: [
      { keys: ["W"], desc: "Toggle Personal Wishlist View" },
      { keys: ["V"], desc: "Cycle View Mode (Screener / Wishlist / Heatmap / Cards)" },
      { keys: ["Q"], desc: "Quick Inspect for active selected equity" },
      { keys: ["T"], desc: "Open full detailed tearsheet page" },
      { keys: ["↑", "↓"], desc: "Navigate through equities table rows" },
    ],
  },
];

export function KeyboardShortcutModal({ isOpen, onClose }: KeyboardShortcutModalProps) {
  const containerRef = useFocusTrap<HTMLDivElement>(isOpen, onClose);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black/75 backdrop-blur-xs"
          />

          {/* Modal Card */}
          <motion.div
            ref={containerRef}
            role="dialog"
            aria-modal="true"
            aria-label="Terminal Keyboard Shortcuts"
            tabIndex={-1}
            initial={{ scale: 0.95, opacity: 0, y: 10 }}
            animate={{ scale: 1, opacity: 1, y: 0 }}
            exit={{ scale: 0.95, opacity: 0, y: 10 }}
            transition={{ type: "spring", stiffness: 350, damping: 28 }}
            className="relative w-full max-w-lg bg-[#06090f] border border-white/[0.1] rounded-2xl shadow-[0_20px_60px_rgba(0,0,0,0.85)] p-5 overflow-hidden z-10 font-mono text-xs"
          >
            {/* Header */}
            <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
              <div className="flex items-center gap-2 text-slate-200">
                <Keyboard className="w-4 h-4 text-cyan-400" />
                <span className="font-bold text-sm tracking-tight">Terminal Keyboard Shortcuts</span>
              </div>
              <button
                onClick={onClose}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/[0.05] transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Shortcut Categories */}
            <div className="py-3 space-y-4 max-h-[65vh] overflow-y-auto">
              {SHORTCUT_GROUPS.map((group) => (
                <div key={group.category} className="space-y-1.5">
                  <span className="text-[10px] uppercase font-bold tracking-wider text-slate-400 block px-1">
                    {group.category}
                  </span>
                  <div className="bg-[#030508]/80 rounded-xl border border-white/[0.04] divide-y divide-white/[0.03]">
                    {group.items.map((item, idx) => (
                      <div key={idx} className="flex items-center justify-between p-2.5">
                        <span className="text-slate-300 font-sans">{item.desc}</span>
                        <div className="flex items-center gap-1 shrink-0">
                          {item.keys.map((k, kIdx) => (
                            <kbd
                              key={kIdx}
                              className="px-2 py-0.5 rounded bg-black/60 border border-white/[0.12] text-cyan-300 font-mono text-[11px] font-bold shadow-xs"
                            >
                              {k}
                            </kbd>
                          ))}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>

            {/* Footer */}
            <div className="pt-3 border-t border-white/[0.06] flex items-center justify-between text-[11px] text-slate-400">
              <span className="flex items-center gap-1">
                <Command className="w-3 h-3 text-cyan-400" />
                <span>Market Intelligence Lab Hotkeys</span>
              </span>
              <span>Press <kbd className="text-[10px] px-1 py-0.2 rounded bg-black/40 border border-white/[0.08]">Esc</kbd> to close</span>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}

export default KeyboardShortcutModal;
