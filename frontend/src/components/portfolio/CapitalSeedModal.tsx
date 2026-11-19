"use client";

import React from "react";
import { Sliders, X, Loader2, RotateCcw } from "lucide-react";

interface CapitalSeedModalProps {
  isOpen: boolean;
  onClose: () => void;
  activeAccount: string;
  capitalInput: string;
  setCapitalInput: (val: string) => void;
  feeTierInput: "RETAIL_MICRO" | "INSTITUTIONAL";
  setFeeTierInput: (val: "RETAIL_MICRO" | "INSTITUTIONAL") => void;
  cashDeltaInput: string;
  setCashDeltaInput: (val: string) => void;
  capitalActionLoading: boolean;
  onResetCapital: (cap: number, feeTier: "RETAIL_MICRO" | "INSTITUTIONAL") => void;
  onAdjustCash: () => void;
  formatINR: (val: number) => string;
}

export const CapitalSeedModal: React.FC<CapitalSeedModalProps> = ({
  isOpen,
  onClose,
  activeAccount,
  capitalInput,
  setCapitalInput,
  feeTierInput,
  setFeeTierInput,
  cashDeltaInput,
  setCashDeltaInput,
  capitalActionLoading,
  onResetCapital,
  onAdjustCash,
  formatINR,
}) => {
  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4">
      <div className="bg-[#080c14]/95 border border-white/[0.12] rounded-3xl max-w-md w-full p-6 space-y-5 shadow-[0_25px_70px_rgba(0,0,0,0.9)] animate-in fade-in zoom-in-95">
        <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
          <div className="flex items-center gap-2.5">
            <Sliders className="w-5 h-5 text-amber-400" />
            <h3 className="font-bold text-white text-base">Capital Control: {activeAccount}</h3>
          </div>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white p-1 rounded-lg hover:bg-white/[0.06] transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="text-xs font-mono text-slate-400 block mb-1.5">
              Preset Initial Seeds:
            </label>
            <div className="grid grid-cols-4 gap-2">
              {[1600, 10000, 50000, 1000000].map((seed) => (
                <button
                  key={seed}
                  type="button"
                  onClick={() => setCapitalInput(seed.toString())}
                  className={`py-1.5 px-2 rounded-xl text-xs font-mono border transition-all tabular-nums ${
                    capitalInput === seed.toString()
                      ? "bg-amber-500/20 border-amber-500 text-amber-300 font-bold shadow-[0_0_10px_rgba(245,158,11,0.2)]"
                      : "bg-[#050810] border-white/[0.08] text-slate-300 hover:bg-white/[0.05]"
                  }`}
                >
                  {formatINR(seed)}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label className="text-xs font-mono text-slate-400 block mb-1.5">
              Custom Starting Capital (INR):
            </label>
            <input
              type="number"
              value={capitalInput}
              onChange={(e) => setCapitalInput(e.target.value)}
              className="w-full px-3.5 py-2.5 rounded-xl bg-[#050810] border border-white/[0.1] font-mono text-sm text-white focus:outline-none focus:border-amber-400 tabular-nums"
            />
          </div>

          <div>
            <label className="text-xs font-mono text-slate-400 block mb-1.5">
              Statutory Fee Tier:
            </label>
            <div className="grid grid-cols-2 gap-2">
              <button
                type="button"
                onClick={() => setFeeTierInput("RETAIL_MICRO")}
                className={`py-2.5 px-3.5 rounded-xl text-xs font-mono border text-left transition-all ${
                  feeTierInput === "RETAIL_MICRO"
                    ? "bg-cyan-950/80 border-cyan-500 text-cyan-300 font-bold shadow-[0_0_12px_rgba(6,182,212,0.2)]"
                    : "bg-[#050810] border-white/[0.08] text-slate-400"
                }`}
              >
                <div>RETAIL_MICRO</div>
                <div className="text-[10px] text-slate-500">12 bps + ₹15 DP fee</div>
              </button>
              <button
                type="button"
                onClick={() => setFeeTierInput("INSTITUTIONAL")}
                className={`py-2.5 px-3.5 rounded-xl text-xs font-mono border text-left transition-all ${
                  feeTierInput === "INSTITUTIONAL"
                    ? "bg-cyan-950/80 border-cyan-500 text-cyan-300 font-bold shadow-[0_0_12px_rgba(6,182,212,0.2)]"
                    : "bg-[#050810] border-white/[0.08] text-slate-400"
                }`}
              >
                <div>INSTITUTIONAL</div>
                <div className="text-[10px] text-slate-500">15 bps blended</div>
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={() => onResetCapital(parseFloat(capitalInput), feeTierInput)}
            disabled={capitalActionLoading || isNaN(parseFloat(capitalInput)) || parseFloat(capitalInput) <= 0}
            className="w-full py-2.5 rounded-xl bg-gradient-to-r from-amber-600 to-orange-600 hover:from-amber-500 hover:to-orange-500 text-white font-mono text-xs font-bold flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(245,158,11,0.25)] transition-all"
          >
            {capitalActionLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RotateCcw className="w-4 h-4" />}
            <span>Reset Capital & Clear Positions</span>
          </button>

          <div className="pt-3 border-t border-white/[0.08]">
            <label className="text-xs font-mono text-slate-400 block mb-1.5">
              Deposit / Withdraw Cash (Keeps active positions):
            </label>
            <div className="flex gap-2">
              <input
                type="number"
                value={cashDeltaInput}
                onChange={(e) => setCashDeltaInput(e.target.value)}
                placeholder="e.g. +500 or -200"
                className="flex-1 px-3.5 py-2 rounded-xl bg-[#050810] border border-white/[0.1] font-mono text-xs text-white focus:outline-none focus:border-cyan-400 tabular-nums"
              />
              <button
                type="button"
                onClick={onAdjustCash}
                disabled={capitalActionLoading || !cashDeltaInput}
                className="px-4 py-2 rounded-xl bg-white/[0.08] hover:bg-white/[0.12] text-white font-mono text-xs font-bold transition-all"
              >
                Apply Cash
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
