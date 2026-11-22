"use client";

import React, { Component, ErrorInfo, ReactNode } from "react";
import { AlertTriangle, RefreshCw } from "lucide-react";

interface Props {
  children: ReactNode;
  panelName?: string;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class PanelErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
  };

  public static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error(`[PanelErrorBoundary: ${this.props.panelName || "Panel"}]`, error, errorInfo);
  }

  private handleReset = () => {
    const errMsg = String(this.state.error?.message || "");
    const isChunkError =
      this.state.error?.name === "ChunkLoadError" ||
      errMsg.includes("Loading chunk") ||
      errMsg.includes("Failed to fetch") ||
      errMsg.includes("ERR_HTTP2") ||
      errMsg.includes("net::");

    if (isChunkError && typeof window !== "undefined") {
      window.location.reload();
      return;
    }
    this.setState({ hasError: false, error: null });
  };

  public render() {
    if (this.state.hasError) {
      const errMsg = String(this.state.error?.message || "");
      const isChunkError =
        this.state.error?.name === "ChunkLoadError" ||
        errMsg.includes("Loading chunk") ||
        errMsg.includes("Failed to fetch") ||
        errMsg.includes("ERR_HTTP2") ||
        errMsg.includes("net::");

      return (
        <div className="flex-1 flex flex-col items-center justify-center p-6 text-center font-mono text-xs bg-[#040609] border border-rose-500/20 rounded-xl space-y-3 m-3">
          <div className="w-10 h-10 rounded-full bg-rose-950/40 border border-rose-500/30 flex items-center justify-center text-rose-400 shadow-[0_0_12px_rgba(244,63,94,0.2)]">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div>
            <h3 className="font-bold text-slate-200">
              {this.props.panelName || "Panel"} Encountered an Error
            </h3>
            <p className="text-slate-400 text-[11px] max-w-sm mt-1">
              {isChunkError
                ? "New build deployment or network update detected. Please reload to refresh components."
                : (this.state.error?.message || "An unhandled error occurred while rendering.")}
            </p>
          </div>
          <button
            onClick={this.handleReset}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-cyan-950/70 hover:bg-cyan-900 border border-cyan-500/40 text-cyan-300 font-semibold transition-colors shadow-sm"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            <span>{isChunkError ? "Reload to Update" : "Reload Component"}</span>
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

export default PanelErrorBoundary;
