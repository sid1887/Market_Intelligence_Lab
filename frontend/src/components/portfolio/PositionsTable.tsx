"use client";

import React, { useState, useEffect, useRef } from "react";
import Link from "next/link";
import { ArrowUpRight, ArrowDownRight, Layers } from "lucide-react";
import { PortfolioPosition } from "@/lib/api";
import { cn } from "@/lib/utils";

interface PositionsTableProps {
  positions: PortfolioPosition[];
  formatINR: (val: number) => string;
  activeAccount: string;
}

const PositionRow = React.memo(function PositionRow({
  pos,
  formatINR,
}: {
  pos: PortfolioPosition;
  formatINR: (val: number) => string;
}) {
  const [flashClass, setFlashClass] = useState("");
  const prevPnlRef = useRef(pos.unrealized_pnl);
  const isProfit = pos.unrealized_pnl >= 0;

  useEffect(() => {
    if (pos.unrealized_pnl !== prevPnlRef.current) {
      const cls = pos.unrealized_pnl > prevPnlRef.current ? "animate-tick-up" : "animate-tick-down";
      setFlashClass(cls);
      prevPnlRef.current = pos.unrealized_pnl;
      const t = setTimeout(() => setFlashClass(""), 700);
      return () => clearTimeout(t);
    }
  }, [pos.unrealized_pnl]);

  return (
    <tr className="hover:bg-white/[0.03] transition-colors">
      <td className="py-3.5 px-5 font-bold">
        <Link
          href={`/stocks/${pos.symbol}`}
          className="text-cyan-400 hover:text-cyan-300 flex items-center gap-1 group"
        >
          <span>{pos.symbol}</span>
          <ArrowUpRight className="w-3 h-3 opacity-0 group-hover:opacity-100 transition-opacity" />
        </Link>
      </td>
      <td className="py-3.5 px-5 text-right text-slate-200 tabular-nums">
        {pos.quantity.toLocaleString("en-IN")}
      </td>
      <td className="py-3.5 px-5 text-right text-slate-400 tabular-nums">
        ₹{pos.average_entry_price.toFixed(2)}
      </td>
      <td className="py-3.5 px-5 text-right text-slate-200 font-semibold tabular-nums">
        ₹{pos.current_price.toFixed(2)}
      </td>
      <td className="py-3.5 px-5 text-right text-slate-100 tabular-nums">
        {formatINR(pos.market_value)}
      </td>
      <td className="py-3.5 px-5 text-right font-mono">
        <div className="flex flex-col items-end gap-1">
          <div className="flex items-center gap-1.5">
            <span
              className={cn(
                "tabular-nums font-semibold text-xs",
                pos.weight_pct > 35
                  ? "text-amber-400 drop-shadow-[0_0_8px_rgba(245,158,11,0.5)]"
                  : "text-cyan-300"
              )}
            >
              {pos.weight_pct.toFixed(2)}%
            </span>
            {pos.weight_pct > 35 && (
              <span
                className="text-[9px] px-1.5 py-0.2 rounded font-bold uppercase tracking-wider bg-amber-500/15 text-amber-300 border border-amber-500/35"
                title="Concentration Guard: Allocation exceeds 35% risk guardrail"
              >
                Concentrated
              </span>
            )}
          </div>
          {/* Inline horizontal allocation progress bar */}
          <div className="w-24 h-1.5 bg-slate-900/90 rounded-full overflow-hidden border border-white/[0.06] p-[1px] flex items-center">
            <div
              className={cn(
                "h-full rounded-full transition-all duration-300",
                pos.weight_pct > 35
                  ? "bg-gradient-to-r from-amber-500 to-amber-300 shadow-[0_0_8px_rgba(245,158,11,0.6)]"
                  : "bg-gradient-to-r from-cyan-600 via-cyan-400 to-emerald-400 shadow-[0_0_6px_rgba(6,182,212,0.4)]"
              )}
              style={{ width: `${Math.min(100, Math.max(0, (pos.weight_pct / 40) * 100))}%` }}
            />
          </div>
        </div>
      </td>
      <td className="py-3.5 px-5 text-right font-mono">
        <span
          className={cn(
            "px-2 py-0.5 rounded text-[11px] font-mono font-bold inline-flex items-center gap-0.5",
            isProfit
              ? "bg-emerald-500/15 text-emerald-400 border border-emerald-500/30"
              : "bg-rose-500/15 text-rose-400 border border-rose-500/30"
          )}
        >
          {isProfit ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
          {isProfit ? "+" : ""}
          {pos.unrealized_pnl_pct.toFixed(2)}%
        </span>
      </td>
      <td
        className={cn(
          "py-3.5 px-5 text-right font-semibold tabular-nums transition-colors duration-300",
          isProfit ? "text-emerald-400" : "text-rose-400",
          flashClass
        )}
      >
        {isProfit ? "+" : ""}
        {formatINR(pos.unrealized_pnl)}
        <span className="text-[11px] font-normal ml-1 text-slate-400 tabular-nums">
          ({isProfit ? "+" : ""}{pos.unrealized_pnl_pct.toFixed(2)}%)
        </span>
      </td>
    </tr>
  );
});

export const PositionsTable: React.FC<PositionsTableProps> = ({
  positions,
  formatINR,
  activeAccount,
}) => {
  return (
    <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
      <div className="p-5 border-b border-white/[0.08] flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <Layers className="w-4 h-4 text-cyan-400" />
          <h2 className="text-sm font-semibold text-white tracking-wide">
            Active Holdings ({positions.length} Equities)
          </h2>
        </div>
        <span className="text-xs font-mono text-slate-400">
          Whole-Share Positions · Friction Guard
        </span>
      </div>

      {positions.length === 0 ? (
        <div className="p-8 text-center text-xs text-slate-500 font-mono">
          <p>No active positions held currently in this account.</p>
          <p className="mt-1 text-slate-400">
            {activeAccount === "paper_manual_1"
              ? "Use the FrontPage Discretionary Trade Ticket above to execute a trade."
              : "Click 'Run Rebalance Cycle' to deploy capital across top-ranked factor compounders."}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-xs">
            <thead className="bg-[#050810]/80 border-b border-white/[0.08] font-mono text-slate-400 text-[11px] uppercase tracking-wider">
              <tr>
                <th className="py-3.5 px-5">Symbol</th>
                <th className="py-3.5 px-5 text-right">Shares</th>
                <th className="py-3.5 px-5 text-right">Avg Entry</th>
                <th className="py-3.5 px-5 text-right">LTP (Close)</th>
                <th className="py-3.5 px-5 text-right">Market Value</th>
                <th className="py-3.5 px-5 text-right">Alloc %</th>
                <th className="py-3.5 px-5 text-right">Return %</th>
                <th className="py-3.5 px-5 text-right">Unrealized P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] font-mono">
              {positions.map((pos) => (
                <PositionRow key={pos.position_id} pos={pos} formatINR={formatINR} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
