"use client";

import React, { useState, useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import CopilotDrawer from "@/components/CopilotDrawer";
import { milEvents } from "@/lib/store";

export default function GlobalCopilotHost() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [activeSymbol, setActiveSymbol] = useState<string>("RELIANCE");

  // Derive initial or changed symbol from URL routes (e.g. /stocks/BSE or ?symbol=BSE)
  useEffect(() => {
    if (pathname && pathname.startsWith("/stocks/")) {
      const parts = pathname.split("/stocks/");
      const sym = parts[1]?.split("/")[0]?.trim()?.toUpperCase();
      if (sym && sym.length >= 2) {
        setActiveSymbol(sym);
      }
    } else if (searchParams && searchParams.get("symbol")) {
      const sym = searchParams.get("symbol")?.trim()?.toUpperCase();
      if (sym && sym.length >= 2) {
        setActiveSymbol(sym);
      }
    }
  }, [pathname, searchParams]);

  // Listen to mil:open-copilot events with explicit symbol payloads
  useEffect(() => {
    const unsub = milEvents.on("mil:open-copilot", (payload) => {
      if (payload?.symbol) {
        setActiveSymbol(payload.symbol.trim().toUpperCase());
      }
    });
    return () => unsub();
  }, []);

  return (
    <CopilotDrawer
      activeSymbol={activeSymbol}
      showFloatingTrigger={false}
    />
  );
}
