"use client";

import React, { useState, useEffect, useCallback, useRef } from "react";
import { motion } from "framer-motion";
import {
  UploadCloud,
  FileSpreadsheet,
  Lock,
  Download,
  ShieldCheck,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Loader2,
} from "lucide-react";
import {
  fetchTradebookSummary,
  uploadTradebookFiles,
  getTradebookExportUrl,
  fetchWithColdStartRetry,
  TradebookSummary,
} from "@/lib/api";

export function RealTradebookPanel() {
  const [summary, setSummary] = useState<TradebookSummary | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [uploading, setUploading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);
  const [activeSubTab, setActiveSubTab] = useState<"closed" | "open" | "attribution" | "security">("closed");
  
  // Drag & drop state
  const [dragOver, setDragOver] = useState<boolean>(false);
  const [selectedFiles, setSelectedFiles] = useState<File[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadSummary = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await fetchTradebookSummary();
      setSummary(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadSummary();
  }, [loadSummary]);

  const handleFileDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const filesArr = Array.from(e.dataTransfer.files).filter((f) =>
        f.name.endsWith(".xlsx") || f.name.endsWith(".xls")
      );
      if (filesArr.length > 0) {
        setSelectedFiles((prev) => [...prev, ...filesArr]);
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const filesArr = Array.from(e.target.files).filter((f) =>
        f.name.endsWith(".xlsx") || f.name.endsWith(".xls")
      );
      setSelectedFiles((prev) => [...prev, ...filesArr]);
    }
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;
    try {
      setUploading(true);
      setError(null);
      setSuccessMsg(null);
      const res = await uploadTradebookFiles(selectedFiles);
      setSummary(res);
      setSelectedFiles([]);
      const stats = res.merge_stats;
      const countStr = stats
        ? `Reconciled ${stats.closed_roundtrips_merged} closed swings, ${stats.open_holdings_merged} open holdings, and ${stats.dp_charges_merged} DP charges.`
        : "Tradebook updated and encrypted successfully.";
      setSuccessMsg(`Merged ${selectedFiles.length} file(s) with Zero-PII sanitization. ${countStr}`);

      // Automatically switch to populated subtab
      if (res.closed_trades && res.closed_trades.length > 0) {
        setActiveSubTab("closed");
      } else if (res.open_holdings && res.open_holdings.length > 0) {
        setActiveSubTab("open");
      }

      // Synchronize with fresh backend summary
      try {
        const fresh = await fetchTradebookSummary();
        if (fresh && (fresh.total_trades > 0 || fresh.open_count > 0)) {
          setSummary(fresh);
        }
      } catch {
        // Fallback to res if fresh call errors
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg);
    } finally {
      setUploading(false);
    }
  };

  const handleDownloadExcel = async () => {
    try {
      const url = getTradebookExportUrl();
      const res = await fetchWithColdStartRetry(url, { method: "GET" });
      if (!res.ok) {
        throw new Error(`Export failed (HTTP ${res.status})`);
      }
      const blob = await res.blob();
      const blobUrl = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = "MIL_Master_Trading_Record.xlsx";
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(blobUrl), 5000);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to download Excel export");
    }
  };

  const formatInr = (val?: number) => {
    if (val === undefined || val === null) return "₹0.00";
    return (
      (val < 0 ? "-₹" : "₹") +
      Math.abs(val).toLocaleString("en-IN", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
    );
  };

  return (
    <div className="space-y-6">
      {/* Privacy & Security Header Banner */}
      <div className="p-6 rounded-2xl bg-gradient-to-r from-[#090d16] via-[#0b1220] to-[#090d16] border border-cyan-500/30 shadow-[0_12px_40px_rgba(0,0,0,0.6)]">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
                <FileSpreadsheet className="w-5 h-5" />
              </div>
              <div>
                <h2 className="text-base font-bold text-white tracking-wide flex items-center gap-2">
                  Angel One Encrypted Tradebook & All-Time Master Excel
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-400 border border-emerald-500/30">
                    AES-128 Fernet Encrypted
                  </span>
                </h2>
                <p className="text-xs text-slate-400 font-mono">
                  Multi-report ingestion · In-memory Zero-PII sanitization · Exact ₹23.60 Demat DP fee recovery
                </p>
              </div>
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={loadSummary}
              disabled={loading || uploading}
              className="px-3 py-2 rounded-xl bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.08] text-xs font-mono text-slate-300 flex items-center space-x-2 transition-all"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin text-cyan-400" : ""}`} />
              <span>Refresh Ledger</span>
            </button>

            <button
              type="button"
              onClick={() => {
                if (typeof window !== "undefined") {
                  const url = new URL(window.location.href);
                  url.searchParams.set("tab", "trader_dna");
                  window.history.replaceState(null, "", url.toString());
                  window.dispatchEvent(new PopStateEvent("popstate"));
                }
              }}
              className="px-3 py-2 rounded-xl bg-cyan-950/60 hover:bg-cyan-900/60 border border-cyan-500/40 text-xs font-mono text-cyan-300 flex items-center space-x-1.5 transition-all shadow-[0_0_12px_rgba(6,182,212,0.2)]"
            >
              <ShieldCheck className="w-3.5 h-3.5 text-cyan-400" />
              <span>Trader DNA Discipline</span>
            </button>

            <button
              type="button"
              onClick={handleDownloadExcel}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 text-xs font-mono font-bold text-white shadow-[0_0_20px_rgba(16,185,129,0.3)] flex items-center space-x-2 transition-all"
            >
              <Download className="w-4 h-4" />
              <span>Download Master .xlsx</span>
            </button>
          </div>
        </div>

        {/* Security Pillar Trust Badges */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mt-5 pt-4 border-t border-white/[0.08]">
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
            <span><strong className="text-white">Zero-PII Filter:</strong> Name, PAN & Client ID strictly wiped</span>
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <CheckCircle2 className="w-4 h-4 text-cyan-400 shrink-0" />
            <span><strong className="text-white">In-Memory RAM:</strong> Uploads processed in RAM, never saved to disk</span>
          </div>
          <div className="flex items-center space-x-2 text-xs text-slate-300">
            <Lock className="w-4 h-4 text-indigo-400 shrink-0" />
            <span><strong className="text-white">Encrypted at Rest:</strong> Saved at <code className="text-indigo-300 text-[11px]">master_tradebook.enc</code></span>
          </div>
        </div>
      </div>

      {/* Drag & Drop Multi-Report Ingestion Zone */}
      <div
        onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleFileDrop}
        className={`p-6 rounded-2xl border-2 border-dashed transition-all ${
          dragOver
            ? "border-cyan-400 bg-cyan-950/20 shadow-[0_0_30px_rgba(6,182,212,0.2)]"
            : "border-white/[0.12] bg-[#070b14]/70 hover:border-white/[0.25]"
        }`}
      >
        <input
          ref={fileInputRef}
          type="file"
          multiple
          accept=".xlsx,.xls"
          onChange={handleFileSelect}
          className="hidden"
        />

        <div className="flex flex-col items-center justify-center text-center space-y-3">
          <div className="p-3 rounded-2xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-400">
            <UploadCloud className="w-7 h-7" />
          </div>
          <div className="space-y-1">
            <h3 className="text-sm font-bold text-white">
              Drop Angel One Reports Here (Trades, Tax P&L, Profit & Loss, Ledger)
            </h3>
            <p className="text-xs text-slate-400 max-w-lg">
              Supports 1 to 4 files simultaneously. The engine automatically anchors to header rows, maps ISINs, matches DP fees (₹23.60), and deduplicates overlapping files.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3 pt-2">
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="px-4 py-2 rounded-xl bg-white/[0.08] hover:bg-white/[0.12] border border-white/[0.12] text-xs font-mono font-semibold text-white transition-all"
            >
              Browse Files...
            </button>

            {selectedFiles.length > 0 && (
              <button
                type="button"
                onClick={handleUpload}
                disabled={uploading}
                className="px-5 py-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-xs font-mono font-bold text-white shadow-[0_0_20px_rgba(6,182,212,0.35)] flex items-center space-x-2 transition-all"
              >
                {uploading ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    <span>Processing In-Memory...</span>
                  </>
                ) : (
                  <>
                    <Lock className="w-3.5 h-3.5" />
                    <span>Merge & Encrypt {selectedFiles.length} File(s)</span>
                  </>
                )}
              </button>
            )}
          </div>

          {/* Selected File Badges */}
          {selectedFiles.length > 0 && (
            <div className="flex flex-wrap gap-2 pt-2">
              {selectedFiles.map((f, i) => (
                <span
                  key={i}
                  className="px-2.5 py-1 rounded-lg bg-white/[0.05] border border-white/[0.1] text-xs font-mono text-slate-300 flex items-center space-x-1.5"
                >
                  <FileSpreadsheet className="w-3.5 h-3.5 text-cyan-400" />
                  <span>{f.name}</span>
                  <span className="text-[10px] text-slate-500">({(f.size / 1024).toFixed(1)} KB)</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Status Alerts */}
      {error && (
        <div className="p-4 rounded-xl bg-red-950/60 border border-red-500/30 text-xs text-red-300 flex items-start space-x-3">
          <AlertCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-bold text-red-200">Processing Error:</span>
            <p>{error}</p>
          </div>
        </div>
      )}

      {successMsg && (
        <div className="p-4 rounded-xl bg-emerald-950/60 border border-emerald-500/30 text-xs text-emerald-300 flex items-start space-x-3">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <div className="space-y-0.5">
            <span className="font-bold text-emerald-200">Reconciliation Succeeded:</span>
            <p>{successMsg}</p>
          </div>
        </div>
      )}

      {/* Executive KPI Metric Cards Strip */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Card 1: True Net P&L */}
          <div className="p-4 rounded-xl bg-[#080d18] border border-white/[0.08] space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">True Net Realized P&L</span>
            <div className={`text-lg font-bold font-mono ${summary.true_net_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {formatInr(summary.true_net_pnl)}
            </div>
            <span className="text-[10px] text-slate-500 font-mono block">
              After ₹23.60 DP & all taxes
            </span>
          </div>

          {/* Card 2: Total DP & Tax Friction */}
          <div className="p-4 rounded-xl bg-[#080d18] border border-white/[0.08] space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Total DP & Tax Drag</span>
            <div className="text-lg font-bold font-mono text-amber-400">
              {formatInr(summary.total_friction)}
            </div>
            <span className="text-[10px] text-slate-500 font-mono block">
              ₹{summary.total_dp_charges.toFixed(2)} DP + ₹{summary.total_trade_taxes.toFixed(2)} Taxes
            </span>
          </div>

          {/* Card 3: Win Rate */}
          <div className="p-4 rounded-xl bg-[#080d18] border border-white/[0.08] space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Win Rate %</span>
            <div className="text-lg font-bold font-mono text-white">
              {summary.win_rate_pct.toFixed(1)}%
            </div>
            <span className="text-[10px] text-slate-500 font-mono block">
              {summary.win_count}W / {summary.loss_count}L ({summary.total_trades} Swings)
            </span>
          </div>

          {/* Card 4: Open Holdings P&L */}
          <div className="p-4 rounded-xl bg-[#080d18] border border-white/[0.08] space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Unrealized Holdings</span>
            <div className={`text-lg font-bold font-mono ${summary.open_unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
              {formatInr(summary.open_unrealized_pnl)}
            </div>
            <span className="text-[10px] text-slate-500 font-mono block">
              {summary.open_count} Scrip ({summary.open_unrealized_pct >= 0 ? "+" : ""}{summary.open_unrealized_pct.toFixed(2)}%)
            </span>
          </div>

          {/* Card 5: Total Capital */}
          <div className="p-4 rounded-xl bg-[#080d18] border border-white/[0.08] space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Capital Deployed</span>
            <div className="text-lg font-bold font-mono text-slate-200">
              {formatInr(summary.total_capital)}
            </div>
            <span className="text-[10px] text-slate-500 font-mono block">
              Net ROI: {summary.net_roi_pct.toFixed(2)}%
            </span>
          </div>

          {/* Card 6: Average Hold Days */}
          <div className="p-4 rounded-xl bg-[#080d18] border border-white/[0.08] space-y-1">
            <span className="text-[11px] font-mono text-slate-400 block">Avg Holding Period</span>
            <div className="text-lg font-bold font-mono text-cyan-400">
              {summary.avg_hold_days.toFixed(1)}d
            </div>
            <span className="text-[10px] text-slate-500 font-mono block">
              Profit Factor: {summary.profit_factor.toFixed(2)}
            </span>
          </div>
        </div>
      )}

      {/* Sub-Tab Navigation */}
      <div className="flex border-b border-white/[0.08] space-x-6 text-xs font-mono">
        <button
          type="button"
          onClick={() => setActiveSubTab("closed")}
          className={`pb-3 font-semibold transition-all relative ${
            activeSubTab === "closed" ? "text-cyan-400" : "text-slate-400 hover:text-white"
          }`}
        >
          <span>Closed Round-Trips ({summary?.closed_trades?.length || 0})</span>
          {activeSubTab === "closed" && (
            <motion.div layoutId="tradebook_tab_glow" className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-400" />
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveSubTab("open")}
          className={`pb-3 font-semibold transition-all relative ${
            activeSubTab === "open" ? "text-cyan-400" : "text-slate-400 hover:text-white"
          }`}
        >
          <span>Open Holdings ({summary?.open_holdings?.length || 0})</span>
          {activeSubTab === "open" && (
            <motion.div layoutId="tradebook_tab_glow" className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-400" />
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveSubTab("attribution")}
          className={`pb-3 font-semibold transition-all relative ${
            activeSubTab === "attribution" ? "text-cyan-400" : "text-slate-400 hover:text-white"
          }`}
        >
          <span>Scrip Attribution ({summary?.scrip_attribution?.length || 0})</span>
          {activeSubTab === "attribution" && (
            <motion.div layoutId="tradebook_tab_glow" className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-400" />
          )}
        </button>

        <button
          type="button"
          onClick={() => setActiveSubTab("security")}
          className={`pb-3 font-semibold transition-all relative ${
            activeSubTab === "security" ? "text-cyan-400" : "text-slate-400 hover:text-white"
          }`}
        >
          <span>Zero-PII & Encryption Spec</span>
          {activeSubTab === "security" && (
            <motion.div layoutId="tradebook_tab_glow" className="absolute bottom-0 left-0 right-0 h-0.5 bg-cyan-400" />
          )}
        </button>
      </div>

      {/* TAB 1: CLOSED ROUND-TRIPS TABLE */}
      {activeSubTab === "closed" && (
        <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#070b14]/80">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-white/[0.08] bg-white/[0.02] text-slate-400 font-mono">
                <th className="py-3 px-4">Symbol</th>
                <th className="py-3 px-3">ISIN</th>
                <th className="py-3 px-3">Qty</th>
                <th className="py-3 px-3">Buy Date</th>
                <th className="py-3 px-3">Sell Date</th>
                <th className="py-3 px-3 text-right">Hold Days</th>
                <th className="py-3 px-3 text-right">Avg Buy (₹)</th>
                <th className="py-3 px-3 text-right">Avg Sell (₹)</th>
                <th className="py-3 px-3 text-right">Gross P&L</th>
                <th className="py-3 px-3 text-right">Taxes</th>
                <th className="py-3 px-3 text-right">DP Fee</th>
                <th className="py-3 px-3 text-right">True Net P&L</th>
                <th className="py-3 px-3 text-right">Return %</th>
                <th className="py-3 px-4 text-center">Outcome</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] font-mono">
              {summary?.closed_trades && summary.closed_trades.length > 0 ? (
                summary.closed_trades.map((t, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-4 font-bold text-white flex items-center gap-1.5">
                      <span>{t.symbol}</span>
                    </td>
                    <td className="py-3 px-3 text-slate-400 text-[11px]">{t.isin || "—"}</td>
                    <td className="py-3 px-3 text-slate-200">{t.qty}</td>
                    <td className="py-3 px-3 text-slate-400 text-[11px]">{t.buy_date}</td>
                    <td className="py-3 px-3 text-slate-400 text-[11px]">{t.sell_date}</td>
                    <td className="py-3 px-3 text-right text-slate-300">{t.hold_days}d</td>
                    <td className="py-3 px-3 text-right text-slate-300">₹{t.avg_buy_price.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right text-slate-300">₹{t.avg_sell_price.toFixed(2)}</td>
                    <td className={`py-3 px-3 text-right ${t.gross_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {formatInr(t.gross_pnl)}
                    </td>
                    <td className="py-3 px-3 text-right text-slate-400">₹{t.trade_charges.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right text-amber-400">₹{t.dp_charge.toFixed(2)}</td>
                    <td className={`py-3 px-3 text-right font-bold ${t.net_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {formatInr(t.net_pnl)}
                    </td>
                    <td className={`py-3 px-3 text-right font-semibold ${t.net_return_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {t.net_return_pct >= 0 ? "+" : ""}{t.net_return_pct.toFixed(2)}%
                    </td>
                    <td className="py-3 px-4 text-center">
                      <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                        t.outcome === "WIN"
                          ? "bg-emerald-950/80 text-emerald-400 border border-emerald-500/30"
                          : "bg-rose-950/80 text-rose-400 border border-rose-500/30"
                      }`}>
                        {t.outcome}
                      </span>
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={14} className="py-8 text-center text-slate-500">
                    No closed trades recorded. Upload an Angel One Tax P&L or Trades History file above.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 2: OPEN HOLDINGS TABLE */}
      {activeSubTab === "open" && (
        <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#070b14]/80">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-white/[0.08] bg-white/[0.02] text-slate-400 font-mono">
                <th className="py-3 px-4">Symbol</th>
                <th className="py-3 px-3">ISIN</th>
                <th className="py-3 px-3">Company Name</th>
                <th className="py-3 px-3 text-right">Quantity</th>
                <th className="py-3 px-3 text-right">Avg Buy Price</th>
                <th className="py-3 px-3 text-right">Invested Value</th>
                <th className="py-3 px-3 text-right">Live LTP</th>
                <th className="py-3 px-3 text-right">Current Value</th>
                <th className="py-3 px-3 text-right">Unrealized P&L</th>
                <th className="py-3 px-4 text-right">Return %</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] font-mono">
              {summary?.open_holdings && summary.open_holdings.length > 0 ? (
                summary.open_holdings.map((h, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-4 font-bold text-white">{h.symbol}</td>
                    <td className="py-3 px-3 text-slate-400 text-[11px]">{h.isin}</td>
                    <td className="py-3 px-3 text-slate-300">{h.scrip_name}</td>
                    <td className="py-3 px-3 text-right text-slate-200">{h.qty}</td>
                    <td className="py-3 px-3 text-right text-slate-300">₹{h.avg_buy_price.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right text-slate-300">₹{h.buy_value.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right text-cyan-300 font-bold">₹{h.closing_rate.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right text-slate-200">₹{h.current_value.toFixed(2)}</td>
                    <td className={`py-3 px-3 text-right font-bold ${h.unrealized_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {formatInr(h.unrealized_pnl)}
                    </td>
                    <td className={`py-3 px-4 text-right font-semibold ${h.unrealized_pnl_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {h.unrealized_pnl_pct >= 0 ? "+" : ""}{h.unrealized_pnl_pct.toFixed(2)}%
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500">
                    No active open holdings found.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 3: SCRIP ATTRIBUTION */}
      {activeSubTab === "attribution" && (
        <div className="overflow-x-auto rounded-xl border border-white/[0.08] bg-[#070b14]/80">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="border-b border-white/[0.08] bg-white/[0.02] text-slate-400 font-mono">
                <th className="py-3 px-4">Symbol</th>
                <th className="py-3 px-3">Company Name</th>
                <th className="py-3 px-3 text-right">Swings</th>
                <th className="py-3 px-3 text-right">Wins</th>
                <th className="py-3 px-3 text-right">Losses</th>
                <th className="py-3 px-3 text-right">Win Rate %</th>
                <th className="py-3 px-3 text-right">Gross P&L</th>
                <th className="py-3 px-3 text-right">Trade Taxes</th>
                <th className="py-3 px-3 text-right">DP Fees</th>
                <th className="py-3 px-4 text-right">True Net P&L</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] font-mono">
              {summary?.scrip_attribution && summary.scrip_attribution.length > 0 ? (
                summary.scrip_attribution.map((s, idx) => (
                  <tr key={idx} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-4 font-bold text-white">{s.symbol}</td>
                    <td className="py-3 px-3 text-slate-300">{s.company_name}</td>
                    <td className="py-3 px-3 text-right text-slate-200">{s.trades}</td>
                    <td className="py-3 px-3 text-right text-emerald-400">{s.wins}</td>
                    <td className="py-3 px-3 text-right text-rose-400">{s.losses}</td>
                    <td className="py-3 px-3 text-right text-slate-200">{s.win_rate_pct.toFixed(1)}%</td>
                    <td className={`py-3 px-3 text-right ${s.gross_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {formatInr(s.gross_pnl)}
                    </td>
                    <td className="py-3 px-3 text-right text-slate-400">₹{s.trade_charges.toFixed(2)}</td>
                    <td className="py-3 px-3 text-right text-amber-400">₹{s.dp_charges.toFixed(2)}</td>
                    <td className={`py-3 px-4 text-right font-bold ${s.net_pnl >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
                      {formatInr(s.net_pnl)}
                    </td>
                  </tr>
                ))
              ) : (
                <tr>
                  <td colSpan={10} className="py-8 text-center text-slate-500">
                    No scrip attribution data available.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* TAB 4: ZERO-PII & ENCRYPTION SPECIFICATION */}
      {activeSubTab === "security" && (
        <div className="p-6 rounded-xl border border-white/[0.08] bg-[#070b14]/80 space-y-5 text-xs text-slate-300">
          <div className="flex items-center space-x-3 pb-3 border-b border-white/[0.08]">
            <Lock className="w-5 h-5 text-cyan-400" />
            <div>
              <h3 className="text-sm font-bold text-white">Zero-PII & At-Rest Encryption Architecture</h3>
              <p className="text-[11px] text-slate-400 font-mono">Formal Privacy Guarantees for Angel One Trade Ingestion</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-2">
              <span className="text-xs font-bold text-emerald-400 font-mono">1. Header-Anchored In-Memory Parser</span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Angel One workbooks contain client name, client ID (UCC), PAN, address, mobile, email, and DP ID in rows 1–33.
                The engine uses dynamic cell-value anchor detection (e.g. <code>TradeBook And Charges</code>, <code>Delivery P&L</code>),
                strictly discarding every row prior to the table banner. Zero PII is ever accessed, parsed, or logged.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-2">
              <span className="text-xs font-bold text-cyan-400 font-mono">2. Ephemeral Upload Destruction</span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Files uploaded through this interface are received as raw bytes via <code>multipart/form-data</code> and loaded directly
                into an in-memory <code>io.BytesIO</code> buffer. Raw broker Excel files are never written to disk, leaving zero physical trace.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-2">
              <span className="text-xs font-bold text-indigo-400 font-mono">3. AES-128 Fernet Encryption at Rest</span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                The generated 5-tab Master Trading Record (<code>MIL_Master_Trading_Record.xlsx</code>) is encrypted at rest using
                <code>cryptography.fernet</code> (PBKDF2-HMAC-SHA256 derived from server-only secret <code>MIL_TRADEBOOK_KEY</code>)
                at <code>data/secure/master_tradebook.enc</code>. This path is strictly ignored by <code>.gitignore</code>.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-white/[0.02] border border-white/[0.06] space-y-2">
              <span className="text-xs font-bold text-amber-400 font-mono">4. Scrip-Level DP Friction Recovery</span>
              <p className="text-slate-400 leading-relaxed text-[11px]">
                Angel One deducts a fixed ₹23.60 DP charge (₹3.50 CDSL + ₹16.50 Angel One + ₹3.60 GST) on every delivery sell settlement.
                Because broker Tax P&L statements omit DP charges from scrip-level P&L, our engine automatically maps ₹23.60 to each
                closed sell trade to guarantee true net returns are never overstated.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
