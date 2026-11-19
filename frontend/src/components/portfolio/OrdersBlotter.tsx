"use client";

import React from "react";
import Link from "next/link";
import { Clock } from "lucide-react";
import { PortfolioOrder } from "@/lib/api";

interface OrdersBlotterProps {
  orders: PortfolioOrder[];
  activeAccount: string;
  formatINR: (val: number) => string;
}

export const OrdersBlotter: React.FC<OrdersBlotterProps> = ({
  orders,
  activeAccount,
  formatINR,
}) => {
  return (
    <div className="bg-[#080c14] border border-white/[0.08] rounded-2xl overflow-hidden shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
      <div className="p-5 border-b border-white/[0.08] flex items-center justify-between">
        <div className="flex items-center space-x-2.5">
          <Clock className="w-4 h-4 text-amber-400" />
          <h2 className="text-sm font-semibold text-white tracking-wide">
            Execution Blotter ({orders.length} Fills on {activeAccount})
          </h2>
        </div>
        <span className="text-xs font-mono text-slate-400">
          Audit-Ready Execution Log
        </span>
      </div>

      {orders.length === 0 ? (
        <div className="p-8 text-center text-xs text-slate-500 font-mono">
          No executions logged yet for this account.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[700px] text-left text-xs">
            <thead className="bg-[#050810]/80 border-b border-white/[0.08] font-mono text-slate-400 text-[11px] uppercase tracking-wider">
              <tr>
                <th className="py-3 px-5">Timestamp</th>
                <th className="py-3 px-5">Action</th>
                <th className="py-3 px-5">Symbol</th>
                <th className="py-3 px-5 text-right">Quantity</th>
                <th className="py-3 px-5 text-right">Fill Price</th>
                <th className="py-3 px-5 text-right">Gross Value</th>
                <th className="py-3 px-5 text-right">Friction Paid</th>
                <th className="py-3 px-5">Thesis Note</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] font-mono">
              {orders.map((ord) => {
                const isBuy = ord.action === "BUY";
                const gross = ord.quantity * ord.fill_price;
                return (
                  <tr key={ord.order_id} className="hover:bg-white/[0.03] transition-colors">
                    <td className="py-3 px-5 text-slate-400 tabular-nums">
                      {ord.executed_at ? ord.executed_at.slice(0, 19).replace("T", " ") : "—"}
                    </td>
                    <td className="py-3 px-5">
                      <span
                        className={`px-2.5 py-0.5 rounded-full text-[10px] font-bold border ${
                          isBuy
                            ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-400"
                            : "bg-rose-500/10 border-rose-500/30 text-rose-400"
                        }`}
                      >
                        {ord.action}
                      </span>
                    </td>
                    <td className="py-3 px-5 font-bold text-slate-200">
                      <Link href={`/stocks/${ord.symbol}`} className="hover:text-cyan-400">
                        {ord.symbol}
                      </Link>
                    </td>
                    <td className="py-3 px-5 text-right text-slate-300 tabular-nums">
                      {ord.quantity.toLocaleString("en-IN")}
                    </td>
                    <td className="py-3 px-5 text-right text-slate-300 tabular-nums">
                      ₹{ord.fill_price.toFixed(2)}
                    </td>
                    <td className="py-3 px-5 text-right text-slate-100 font-medium tabular-nums">
                      {formatINR(gross)}
                    </td>
                    <td className="py-3 px-5 text-right text-amber-400 font-medium tabular-nums">
                      {formatINR(ord.friction_paid)}
                    </td>
                    <td className="py-3 px-5 text-slate-400 text-[11px] truncate max-w-[200px]">
                      {ord.thesis_note || "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
