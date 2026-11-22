"use client";

import React, { useState, useEffect } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import CopilotDrawer from "@/components/CopilotDrawer";
import { milEvents } from "@/lib/store";

export default function GlobalCopilotHost() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const [activeSymbol, setActiveSymbol] = useState<string>("RELIANCE");
  const [activePrice, setActivePrice] = useState<number | undefined>(undefined);
  const [activeVerdict, setActiveVerdict] = useState<string | undefined>(undefined);

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

  // Listen to mil:open-copilot and mil:context-update events
  useEffect(() => {
    const unsubOpen = milEvents.on("mil:open-copilot", (payload) => {
      if (payload?.symbol) {
        setActiveSymbol(payload.symbol.trim().toUpperCase());
      }
    });

    const unsubContext = milEvents.on("mil:context-update", (payload) => {
      if (payload?.symbol) {
        setActiveSymbol(payload.symbol.trim().toUpperCase());
      }
      if (payload?.price !== undefined) {
        setActivePrice(payload.price ?? undefined);
      }
      if (payload?.verdict !== undefined) {
        setActiveVerdict(payload.verdict ?? undefined);
      }
    });

    return () => {
      unsubOpen();
      unsubContext();
    };
  }, []);

  return (
    <CopilotDrawer
      activeSymbol={activeSymbol}
      activePrice={activePrice}
      activeVerdict={activeVerdict}
      showFloatingTrigger={false}
    />
  );
}
