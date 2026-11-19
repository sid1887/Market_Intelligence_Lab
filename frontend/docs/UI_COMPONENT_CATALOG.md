# Market Intelligence Lab (MIL) — UI Component Catalog & Design System

> **Version:** 8.0.0-PROD  
> **Target Framework:** Next.js 14 (App Router) + React 18 + Tailwind CSS + Framer Motion  
> **Status:** Production Ready  

---

## 1. Design System Tokens & Theming Specification

The Market Intelligence Lab interface employs a high-contrast institutional trading terminal aesthetic ("Cockpit Dark") with full support for light mode via semantic CSS variables and tokens (`[data-theme="light"]`).

### 1.1 Color Tokens (`frontend/src/app/globals.css`)

| Token Variable | Dark Mode (Default) | Light Mode | Semantic Purpose |
| :--- | :--- | :--- | :--- |
| `--background` | `rgb(10, 14, 23)` (#0A0E17) | `rgb(248, 250, 252)` (#F8FAFC) | Primary viewport canvas |
| `--foreground` | `rgb(241, 245, 249)` (#F1F5F9) | `rgb(15, 23, 42)` (#0F172A) | Primary typography |
| `--card` | `rgb(15, 23, 42)` (#0F172A) | `rgb(255, 255, 255)` (#FFFFFF) | Component surface background |
| `--card-border` | `rgba(255, 255, 255, 0.08)` | `rgba(0, 0, 0, 0.1)` | Subtle structural separators |
| `--accent-cyan` | `#00F0FF` | `#0284C7` | High-conviction alpha / quant telemetry |
| `--accent-emerald` | `#10B981` | `#059669` | Bullish drift / positive P&L / long signals |
| `--accent-rose` | `#F43F5E` | `#DC2626` | Bearish risk / negative drawdown / short signals |
| `--accent-amber` | `#F59E0B` | `#D97706` | Cautionary state / macro alerts / volatility |
| `--accent-purple` | `#A855F7` | `#7C3AED` | ML ensemble / transformer attributions |

### 1.2 Glassmorphism & Elevation Classes

- `glass-panel`: `bg-[#0F172A]/70 backdrop-blur-md border border-white/10 shadow-2xl`
- `glass-panel-subtle`: `bg-slate-900/40 backdrop-blur-sm border border-white/5`
- `glass-input`: `bg-slate-950/60 border border-slate-700/60 text-slate-100 focus:border-cyan-500/60`

### 1.3 Motion Variants (`frontend/src/lib/motion.ts`)

- `cockpitFadeIn`: Subtle opacity entry for high-density tables (`opacity: 0 -> 1`, 180ms easeOut).
- `slideOverDrawer`: Spring physics for inspector & Copilot drawers (`x: '100%' -> 0`, stiffness 320, damping 32).
- `staggerContainer`: Coordinated cascade for telemetry tiles and factor radars (staggerChildren 0.04s).
- `pulseGlow`: Micro-interaction badge animation for real-time live ingestion and P&L sync.

---

## 2. Global State Bus & Reactive Store (`frontend/src/lib/store.ts`)

MIL employs a lightweight, zero-dependency, concurrent-safe event bus and reactive store built on React 18's native `useSyncExternalStore`.

```typescript
import { useMilStore, milEvents } from "@/lib/store";

// Emitting cross-component platform events
milEvents.emit("STOCK_INSPECTED", { symbol: "TCS", origin: "screener_table" });
milEvents.emit("WATCHLIST_CHANGED", { symbol: "RELIANCE", action: "added" });
milEvents.emit("TRIGGER_SYNC", { mode: "cloud_safe" });

// Subscribing within any component with zero prop drilling
const activeSymbol = useMilStore((state) => state.activeSymbol);
const watchlist = useMilStore((state) => state.watchlist);
```

---

## 3. Global Navigation & Cockpit Overlays

### 3.1 `Navbar.tsx`
- **Location:** `frontend/src/components/Navbar.tsx`
- **Description:** Global high-density navigation header displaying market pulse, live telemetry latency, ingestion status trigger, notifications, and navigation tabs.
- **Props:** None (Self-contained, integrates with router and global stores).
- **Key Features:**
  - Dynamic route highlighting (`/`, `/portfolio`, `/backtest`).
  - Integrated `NotificationCenterPopover` trigger with live unread badge.
  - One-click trigger for `PushNotificationModal` preferences.
  - Active market regime status badge (NSE Open/Closed, Index Beta).

### 3.2 `NotificationCenterPopover.tsx`
- **Location:** `frontend/src/components/NotificationCenterPopover.tsx`
- **Description:** Interactive notification drawer popover with categorization, priority levels, audio toggles, and direct tearsheet links.
- **Props:**
  ```typescript
  interface NotificationCenterPopoverProps {
    isOpen: boolean;
    onClose: () => void;
    anchorRef?: React.RefObject<HTMLElement>;
  }
  ```
- **Filter Categories:** `ALL`, `PRICE_CATALYST`, `EARNINGS_FILINGS`, `ML_ALPHA`, `SYSTEM`.

### 3.3 `CommandPaletteModal.tsx`
- **Location:** `frontend/src/components/CommandPaletteModal.tsx`
- **Description:** Quick-action Command-K terminal modal for instant navigation, symbol search, action dispatch, and keyboard shortcuts.
- **Trigger:** `Cmd+K` / `Ctrl+K`.
- **Keyboard Traps:** Full WAI-ARIA combobox implementation with arrow-key navigation and Escape dismissal.

### 3.4 `KeyboardShortcutModal.tsx`
- **Location:** `frontend/src/components/KeyboardShortcutModal.tsx`
- **Description:** Modal cheatsheet of all institutional keyboard hotkeys across screener, inspector, charts, and drawers.
- **Trigger:** `?` keypress or clicking footer shortcut trigger.

### 3.5 `PushNotificationModal.tsx`
- **Location:** `frontend/src/components/PushNotificationModal.tsx`
- **Description:** WebPush preference configuration modal allowing users to configure min conviction thresholds, max alerts/day, market-hours-only toggles, and Telegram bot linking.
- **Props:**
  ```typescript
  interface PushNotificationModalProps {
    isOpen: boolean;
    onClose: () => void;
  }
  ```

---

## 4. Market Discovery & Screener Components

### 4.1 `ScreenerWorkspace.tsx`
- **Location:** `frontend/src/components/ScreenerWorkspace.tsx`
- **Description:** Primary workspace container for the institutional factor screener with multi-mode view switching (`table`, `heatmap`, `cards`).
- **Props:**
  ```typescript
  interface ScreenerWorkspaceProps {
    initialStocks: ScreenerStock[];
    totalEquities: number;
    lastUpdated: string;
    onInspectStock: (stock: ScreenerStock) => void;
  }
  ```
- **Key Features:**
  - View mode toggling: Table view, Sector Treemap Heatmap, Card Grid.
  - Debounced Hover Quick-Preview Popover with 350ms dwell timer (`L2`).
  - Right-click institutional context menu for fast symbol action dispatch (`L3`).
  - Multi-column sorting across 15+ quant factors (Composite Score, Momentum, Quality, Volatility).

### 4.2 `ScreenerTable.tsx`
- **Location:** `frontend/src/components/ScreenerTable.tsx`
- **Description:** High-density virtualized table rendering 1,140+ equities with color-coded score cells, sparklines, and liquidity vectors.
- **Props:**
  ```typescript
  interface ScreenerTableProps {
    data: ScreenerStock[];
    sortField: string;
    sortAsc: boolean;
    onSort: (field: string) => void;
    onSelectRow: (stock: ScreenerStock) => void;
  }
  ```

### 4.3 `ScreenerScoreCell.tsx`
- **Location:** `frontend/src/components/ScreenerScoreCell.tsx`
- **Description:** Micro-gauge cell displaying factor percentiles (0–100) with color gradients from deep slate to electric cyan/emerald.

### 4.4 `SectorHeatmap.tsx`
- **Location:** `frontend/src/components/SectorHeatmap.tsx`
- **Description:** Hierarchical squarified treemap visualizer weighting sector market capitalization, composite alpha score, and daily momentum.
- **Props:**
  ```typescript
  interface SectorHeatmapProps {
    stocks: ScreenerStock[];
    metric?: "composite_score" | "momentum" | "pnl" | "volume";
    onSelectSector?: (sector: string) => void;
    onSelectStock?: (symbol: string) => void;
  }
  ```

### 4.5 `WatchlistPanel.tsx`
- **Location:** `frontend/src/components/WatchlistPanel.tsx`
- **Description:** Compact drawer/sidebar displaying bookmarked symbols, rapid 1-click removal, price updates, and multi-symbol compare launch.

---

## 5. Tearsheet & Stock Intelligence Components

### 5.1 `StockChart.tsx`
- **Location:** `frontend/src/components/StockChart.tsx`
- **Description:** Institutional TradingView `lightweight-charts` implementation featuring dual-pane OHLCV candlesticks + Volume + SMA overlays (20/50/200).
- **Props:**
  ```typescript
  interface StockChartProps {
    symbol: string;
    history: OHLCVBar[];
    supportResistanceLevels?: number[];
    showAthAtlMarkers?: boolean;
    timeframe: "1M" | "3M" | "6M" | "1Y" | "5Y" | "ALL";
    onTimeframeChange: (tf: string) => void;
  }
  ```
- **Key Enhancements (Phase 4):**
  - Horizontal support/resistance drawing tool with local storage persistence (`L6`).
  - Dynamic ATH / ATL marker overlays across the visible timeframe slice (`L7`).
  - Dynamic price line memory management preventing ghost lines on timeframe re-slices.

### 5.2 `FactorPentagonRadar.tsx`
- **Location:** `frontend/src/components/FactorPentagonRadar.tsx`
- **Description:** 5-axis SVG radar polygon visualizing fundamental and quantitative factor profiles (Momentum, Value, Quality, Growth, Low Volatility).
- **Props:**
  ```typescript
  interface FactorPentagonRadarProps {
    momentum: number;
    value: number;
    quality: number;
    growth: number;
    lowVolatility: number;
    benchmarkComparison?: {
      momentum: number;
      value: number;
      quality: number;
      growth: number;
      lowVolatility: number;
    };
    showBenchmarkToggle?: boolean;
  }
  ```
- **Key Enhancements (Phase 4):**
  - Benchmark polygon overlay (Nifty 50 / Sector Median) with comparative telemetry tooltips (`L8`).

### 5.3 `RadialConvictionGauge.tsx`
- **Location:** `frontend/src/components/RadialConvictionGauge.tsx`
- **Description:** High-impact SVG radial arc displaying ML Alpha ensemble conviction score (0–100%) and drift forecast.

### 5.4 `RiskRewardVectorBar.tsx`
- **Location:** `frontend/src/components/RiskRewardVectorBar.tsx`
- **Description:** Visual stop-loss vs target expectation bar showing R:R ratios (e.g. 1:3.2), VaR (Value at Risk 95%), and maximum historical drawdown.

### 5.5 `StockInspector.tsx`
- **Location:** `frontend/src/components/StockInspector.tsx`
- **Description:** Slide-over detail drawer for rapid equity inspection from the screener table with factor pentagon, catalysts, and watchlist bookmarking (`L9`).

### 5.6 `CopilotDrawer.tsx`
- **Location:** `frontend/src/components/CopilotDrawer.tsx`
- **Description:** Multi-turn interactive quantitative analyst drawer powered by Gemini/Groq LLMs with grounded live SQLite factor telemetry.
- **Props:**
  ```typescript
  interface CopilotDrawerProps {
    isOpen: boolean;
    onClose: () => void;
    activeSymbol?: string;
  }
  ```
- **Key Enhancements (Phase 4):**
  - Formatted Markdown Deliberation Report export & download button (`L11`).

---

## 6. Portfolio & Execution Blotter (`frontend/src/components/portfolio/`)

### 6.1 `PositionsTable.tsx`
- **Location:** `frontend/src/components/portfolio/PositionsTable.tsx`
- **Description:** Comprehensive holdings blotter with live P&L streaming, average entry price, market value, unrealized returns, and 1-click tearsheet links.

### 6.2 `OrdersBlotter.tsx`
- **Location:** `frontend/src/components/portfolio/OrdersBlotter.tsx`
- **Description:** Audit blotter of historical simulation executions with timestamps, order sides (BUY/SELL), filled quantities, and realized slippage.

### 6.3 `CapitalSeedModal.tsx`
- **Location:** `frontend/src/components/portfolio/CapitalSeedModal.tsx`
- **Description:** Modal for depositing capital, re-anchoring simulation balances, or resetting paper trading state with transaction confirmations.

---

## 7. Backtesting & Comparison Analytics

### 7.1 `BacktestChart.tsx`
- **Location:** `frontend/src/components/BacktestChart.tsx`
- **Description:** High-precision cumulative equity curve vs benchmark (Nifty 50) with underwater drawdown plot.

### 7.2 `BacktestCompareChart.tsx`
- **Location:** `frontend/src/components/BacktestCompareChart.tsx`
- **Description:** Multi-strategy comparative equity visualizer allowing simultaneous evaluation of Momentum vs Multi-Factor vs Value tilts.

### 7.3 `CompareTerminal.tsx`
- **Location:** `frontend/src/components/CompareTerminal.tsx`
- **Description:** Side-by-side terminal comparing up to 4 equities across financial ratios, Sharpe ratios, factor pentagons, and ML convictions.

---

## 8. Keyboard Navigation & Accessibility Specifications

MIL strictly adheres to **WAI-ARIA 1.2** and **WCAG 2.1 Level AA** standards:

| Key Combination | Scope | Action |
| :--- | :--- | :--- |
| `Cmd + K` / `Ctrl + K` | Global | Opens Command Palette search |
| `Cmd + J` / `Ctrl + J` | Global | Toggles Quant Copilot Drawer |
| `?` | Global | Opens Keyboard Shortcuts modal |
| `Escape` | Global | Dismisses any active modal, drawer, or popover |
| `Arrow Up` / `Arrow Down` | Tables / Command Palette | Navigates focused rows or list items |
| `Enter` | Screener Table | Opens Stock Tearsheet for focused row |
| `Space` | Screener Table | Toggles Quick Inspect drawer for focused row |
| `W` | Inspector / Tearsheet | Toggles symbol in/out of Watchlist |

---

## 9. Verification & Testing

Every component in this catalog is verified via automated suites:
1. **TypeScript strict mode:** `tsc --noEmit` zero type regressions.
2. **Next.js Production Build:** `npm run build` validating all dynamic routes and static prerenders.
3. **Playwright E2E Test Suite:** `npx playwright test` (`frontend/e2e/cockpit.spec.ts`) validating render, drawer triggers, hotkey responsiveness, and contrast ratios.
