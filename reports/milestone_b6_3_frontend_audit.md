# Milestone B6.3 Verification & Frontend Terminal Audit Report

**Date:** 2026-11-04  
**Milestone:** B6.3 (FastAPI Bridge & Next.js Interactive Dashboard)  
**System Status:** Full-Stack Stabilized  
**Repository:** `https://github.com/sid1887/Market_Intelligence_Lab.git`  
**Working Directory:** `/home/siddharth/Desktop/Market_Intelligence_Lab`  

---

## 1. Executive Summary

Milestone B6.3 transitions the **Market Intelligence Lab** from a headless, CLI-driven quantitative engine into an interactive, full-stack analytical platform. 

All core quantitative factor metrics, event studies, historical OHLCV data, corporate disclosures, and active watchlists are now exposed through high-performance REST APIs and rendered in a production-grade web terminal built with **Next.js 14 (App Router)**, **TypeScript**, **Tailwind CSS**, and TradingView's **`lightweight-charts`** canvas rendering engine.

### Key Deliverables Completed:
1. **FastAPI REST Bridge (`src/api/`):**
   - High-throughput asynchronous REST backend reading from `data/market_lab.db` in SQLite WAL mode.
   - Secure Cross-Origin Resource Sharing (CORS) configured for `http://localhost:3000`, `http://127.0.0.1:3000`, and `https://*.vercel.app` (regex).
   - Dedicated endpoints for health checks, screener queries, watchlist performance, individual company tearsheets, and high-density candlestick series.
2. **Next.js Interactive Web Terminal (`frontend/`):**
   - Modern dark-palette terminal UI (`#090d16` background, cyan/emerald accents) inspired by institutional financial systems.
   - Real-time **Watchlist Monitor** tracking active positions (`SUZLON`, `TRIDENT`, `DRONACHRYA`, `MOREPENLAB`) with 200 SMA proximity alerts.
   - Comprehensive **Factor Screener Table** with multi-factor threshold filters (Min ROE, Max D/E, Above 200 SMA, Exclude Financials, Watchlist-only) and interactive search.
   - Dynamic **Company Tearsheets** (`/stocks/[symbol]`) featuring interactive TradingView Candlestick & Volume charts (timeframe filtering: 3M, 6M, 1Y, ALL), 4-card metric summaries, and corporate filing audit logs.
3. **Bootstrapping & Deployment Orchestration:**
   - Platform launch script `scripts/start_platform.sh` enabling single-command startup of backend and frontend processes with signal handling (`SIGINT`/`SIGTERM`).
   - Clean Next.js production build (`npm run build`) passing 100% of TypeScript type checks, ESLint rules, and static route generation.

---

## 2. Architecture & Concurrency Safety

### 2.1 SQLite WAL Concurrency
To ensure the web server never encounters `sqlite3.OperationalError: database is locked` while background data ingestion or factor calculation jobs execute, the FastAPI bridge enforces:
- **Read-Only URI Connections:** `file:data/market_lab.db?mode=ro`.
- **WAL Pragma:** Inherits WAL journal mode configured in schema v3 (`PRAGMA journal_mode=WAL;`).
- **Connection Isolation:** Each request acquires an isolated read-only connection with a 15-second busy timeout (`timeout=15.0`) and `check_same_thread=False`.

### 2.2 CORS Policy
The API server explicitly enables cross-origin requests from both local development ports and future cloud deployments:
```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8000",
    ],
    allow_origin_regex=r"^https:\/\/.*\.vercel\.app$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 3. API Endpoints Specification

| Endpoint | Method | Description | Key Parameters |
| :--- | :--- | :--- | :--- |
| `/health` | `GET` | System heartbeat & database connectivity | None |
| `/api/v1/health` | `GET` | API v1 status, active universe count, latest settled session date | None |
| `/api/v1/watchlist` | `GET` | Active user watchlists with real-time technicals & fundamentals | None |
| `/api/v1/screener` | `GET` | Multi-factor quantitative screener across 54 instruments | `min_roe`, `max_de`, `price_above_sma200`, `exclude_financials`, `limit` |
| `/api/v1/stocks/{symbol}/tearsheet` | `GET` | Unified company profile, latest quote, fundamentals, technicals, recent 5 disclosures, and 498-bar history | `symbol` (e.g. `SUZLON`) |
| `/api/v1/stocks/{symbol}/history` | `GET` | High-density candlestick & volume series for charting | `symbol`, `limit` (default: 500) |

---

## 4. Next.js Web Terminal Structure

The frontend application is structured inside `frontend/` using Next.js 14 App Router:

```
frontend/
├── .env.example
├── .env.local
├── package.json
├── tsconfig.json
├── tailwind.config.ts
├── src/
│   ├── app/
│   │   ├── globals.css          # Dark terminal theme & custom scrollbars
│   │   ├── layout.tsx           # Institutional layout wrapper with Navbar & Footer
│   │   ├── page.tsx             # Main dashboard (Watchlist + Screener)
│   │   └── stocks/
│   │       └── [symbol]/
│   │           └── page.tsx     # Dynamic Stock Tearsheet
│   └── components/
│       ├── Navbar.tsx           # Global navigation & live status pill
│       ├── WatchlistPanel.tsx   # Active watchlist monitor card grid
│       ├── ScreenerTable.tsx    # Multi-factor filterable ranking table
│       └── StockChart.tsx       # TradingView lightweight-charts canvas wrapper
```

### 4.1 Key Visual Components
- **TradingView Canvas Chart:** Renders dual-series HTML5 Canvas (candlestick OHLC + semi-transparent volume histogram). Automatically resizes with window geometry, displays crosshair inspection HUD, and offers range buttons (`3M`, `6M`, `1Y`, `ALL`).
- **Watchlist Quick Monitor:** Displays active positions (`SUZLON`, `TRIDENT`, `DRONACHRYA`, `MOREPENLAB`), highlighting daily percentage movement, SMA 200 distance badges, and target/stop-loss price targets.
- **Institutional Screener Table:** Interactive table with composite score progress bars, dynamic column sorting, and responsive search filtering.

---

## 5. Build & Verification Audit

### 5.1 Next.js Build Output
```
> frontend@0.1.0 build
> next build

  ▲ Next.js 14.2.35
  - Environments: .env.local

   Creating an optimized production build ...
 ✓ Compiled successfully
   Linting and checking validity of types     ✓ Linting and checking validity of types 
   Collecting page data                       ✓ Collecting page data 
 ✓ Generating static pages (5/5)
   Collecting build traces                    ✓ Collecting build traces 
   Finalizing page optimization               ✓ Finalizing page optimization 

Route (app)                              Size     First Load JS
┌ ○ /                                    5.12 kB         103 kB
├ ○ /_not-found                          873 B          88.1 kB
└ ƒ /stocks/[symbol]                     58.5 kB         156 kB
+ First Load JS shared by all            87.3 kB
  ├ chunks/117-52ef03870e8eb683.js       31.7 kB
  ├ chunks/fd9d1056-e070525407d48905.js  53.6 kB
  └ other shared chunks (total)          1.89 kB

○  (Static)   prerendered as static content
ƒ  (Dynamic)  server-rendered on demand
```

### 5.2 Test Verification Results

#### Dedicated API Test Suite (`tests/test_milestone_b6_3_api.py`)
```
test_candlestick_history (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_candlestick_history) ... ok
test_health_endpoints (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_health_endpoints) ... ok
test_screener_endpoint (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_screener_endpoint) ... ok
test_screener_filters (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_screener_filters) ... ok
test_stock_tearsheet_404 (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_stock_tearsheet_404) ... ok
test_stock_tearsheet_infy (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_stock_tearsheet_infy) ... ok
test_stock_tearsheet_suzlon (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_stock_tearsheet_suzlon) ... ok
test_watchlist_endpoint (tests.test_milestone_b6_3_api.TestMilestoneB63API.test_watchlist_endpoint) ... ok

----------------------------------------------------------------------
Ran 8 tests in 0.210s

OK
```

#### Full Regression Suite (`python3 -m unittest discover tests -p "test_*.py"`)
```
Ran 234 tests in 103.422s

OK (skipped=1)
```
- Total test modules discovered across all milestones (B1 through B6.3): 24 test suites.
- 233 Passed, 1 Skipped (known external mock placeholder), 0 Failed, 0 Errors.
- Offline governance and database WAL integrity preserved.

---

## 6. How to Launch Platform

### Local Execution:
```bash
# Execute concurrent bootstrapper
./scripts/start_platform.sh
```

- **Backend API:** `http://localhost:8000`
- **Swagger Documentation:** `http://localhost:8000/docs`
- **Frontend Dashboard:** `http://localhost:3000`
- **SUZLON Tearsheet:** `http://localhost:3000/stocks/SUZLON`
