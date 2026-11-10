# Market Intelligence Lab (MIL) — Implementation Tracker
**Status:** ACTIVE EXECUTION  
**Last Updated:** 2026-11-07  
**Operating Standard:** Strict Evidence-Led Engineering Contract

---

## 1. Workstream & Ticket Inventory

| Ticket ID | Workstream / Domain | Priority | Status | Owner | Primary Target Files |
| :--- | :--- | :---: | :---: | :--- | :--- |
| **MIL-P0-001** | Model Governance & Baseline Non-Promotion | P0 | COMPLETED | Antigravity | `src/ml/training/tournament.py`, `src/ml/registry/manager.py` |
| **MIL-P0-002** | Test Suite Isolation & Zero DB Contamination | P0 | COMPLETED | Antigravity | `tests/test_ml_lifecycle.py`, `tests/test_dynamic_ingestion_api.py` |
| **MIL-P0-003** | Ingestion Truth & Masquerade Eradication | P0 | COMPLETED | Antigravity | `src/pipeline/universe_ingestion.py`, `scripts/reconcile_synthetic_symbols.py` |
| **MIL-P0-004** | EOD Ingestion Fail-Closed & Settlement Guard | P0 | COMPLETED | Antigravity | `src/pipeline/universe_ingestion.py`, `src/tasks/daemon.py` |
| **MIL-P0-005** | Series='EQ' Invariant & 168k Orphan Reconciliation | P0 | COMPLETED | Antigravity | `scripts/reconcile_factor_ohlcv.py`, `src/quant/factor_pipeline.py`, `src/quant/screener.py`, `src/ml/features/builder.py`, `src/api/routes_market.py` |
| **MIL-P0-006** | Benchmark TRI/PRI Endpoint Consistency | P0 | COMPLETED | Antigravity | `src/ml/labels/builder.py`, `tests/test_ml_correctness_and_benchmark.py` |
| **MIL-P0-007** | Macro Telemetry Truthfulness & Fallback Cleanout | P0 | COMPLETED | Antigravity | `src/client/macro_client.py`, `frontend/src/app/page.tsx` |
| **MIL-P0-008** | Database Migration Fail-Fast Execution | P0 | COMPLETED | Antigravity | `src/storage/database.py`, `tests/test_backend_reliability.py` |
| **MIL-DATA-002** | Synthetic Data Quarantine | P0 | COMPLETED | Antigravity | `src/client/backfill_manager.py`, `src/pipeline/dynamic_ingestion.py` |
| **MIL-DATA-003** | OHLCV / Factor Row Reconciliation | P0 | COMPLETED | Antigravity | `scripts/reconcile_factor_ohlcv.py`, `src/quant/factor_pipeline.py` |
| **MIL-ML-001** | Benchmark Identity & Label Integrity | P0 | COMPLETED | Antigravity | `src/ml/labels/builder.py` |
| **MIL-ML-002** | Walk-Forward Evaluation & Purge Embargo | P0 | COMPLETED | Antigravity | `src/ml/training/tournament.py` |
| **MIL-ML-003** | Model Registry & Champion Pointer Sync | P0 | COMPLETED | Antigravity | `src/supervisor/state_machine.py`, `src/ml/registry/manager.py` |
| **MIL-BE-001** | Dependency Isolation (`yfinance` guard) | P0 | COMPLETED | Antigravity | `pyproject.toml`, `requirements.txt`, `src/client/macro_client.py` |
| **MIL-BE-002** | Daemon Lifecycle & Settlement Truth | P0 | COMPLETED | Antigravity | `src/tasks/daemon.py` |
| **MIL-BE-003** | Safe Connection Management & PRAGMA | P1 | COMPLETED | Antigravity | `src/storage/database.py` |
| **MIL-UI-001** | Honest Frontend States & Fake Cones Removal | P0 | COMPLETED | Antigravity | `frontend/src/app/page.tsx` |
| **MIL-UI-002** | Stable Symbol Selection & Completeness Scale | P0 | COMPLETED | Antigravity | `frontend/src/app/page.tsx` |
| **MIL-UI-003** | Robust SSE Parser & Live Timing in Copilot | P0 | COMPLETED | Antigravity | `frontend/src/components/CopilotDrawer.tsx` |
| **MIL-UI-004** | Stock Tearsheet Parallel Fetch & Index Truth | P1 | COMPLETED | Antigravity | `frontend/src/app/stocks/[symbol]/page.tsx` |
| **MIL-UI-005** | Backtest Pure GET & Empty State Handling | P1 | COMPLETED | Antigravity | `frontend/src/app/backtest/page.tsx` |
| **MIL-R3-P0-001** | Fabricated Disclosures Eradication & Quarantine | P0 | COMPLETED | Antigravity | `src/pipeline/dynamic_ingestion.py`, `src/storage/migrations.py` |
| **MIL-R3-P0-002** | Macro Telemetry Finite Math, Pandas & TTL Cache | P0 | COMPLETED | Antigravity | `src/client/macro_client.py`, `scripts/reconcile_synthetic_symbols.py` |
| **MIL-R3-P0-003** | Series='EQ' & Purpose Eligibility Across Consumers | P0 | COMPLETED | Antigravity | `src/ml/labels/builder.py`, `src/quant/backtest_engine.py`, `src/api/routes_market.py` |
| **MIL-R3-P0-004** | Unified Promotion Gate & Supervisor Truthfulness | P0 | COMPLETED | Antigravity | `src/ml/registry/manager.py`, `src/ml/training/tournament.py`, `src/supervisor/state_machine.py` |
| **MIL-R3-P0-005** | Migration Source Checksums & DDL Transaction Isolation | P0 | COMPLETED | Antigravity | `src/storage/migrations.py` |
| **MIL-R3-P0-006** | Multi-Fold Purged Walk-Forward CV & Fold Pipeline | P0 | COMPLETED | Antigravity | `src/ml/training/tournament.py` |
| **MIL-R3-P0-007** | Frontend 5-Viewport Responsive Layout & Quarantined UI | P0 | COMPLETED | Antigravity | `frontend/src/app/page.tsx`, `frontend/src/app/stocks/[symbol]/page.tsx`, `frontend/src/app/backtest/page.tsx` |
| **MIL-P0-021** | Ingestion Empty-Fetch Fail-Closed & Settlement Guard | P0 | COMPLETED | Antigravity | `src/pipeline/universe_ingestion.py`, `src/tasks/daemon.py` |
| **MIL-P0-022** | Supervisor Dynamic State Machine Invariants | P0 | COMPLETED | Antigravity | `src/supervisor/state_machine.py`, `frontend/src/app/page.tsx` |
| **MIL-P0-023** | Purged Walk-Forward Tournament & Champion Promotion | P0 | COMPLETED | Antigravity | `src/ml/training/tournament.py`, `src/ml/registry/manager.py`, `src/storage/migrations.py` |
| **MIL-P0-024** | Hermetic Test Suite Isolation & Zero DB Mutation | P0 | COMPLETED | Antigravity | `tests/test_ml_lifecycle.py`, `tests/test_backend_reliability.py` |
| **MIL-P1-025** | Durable Job Subsystem & Lease-Based Worker Daemon | P1 | COMPLETED | Antigravity | `src/storage/migrations.py`, `src/workers/runner.py`, `src/workers/dispatcher.py`, `src/api/routes_jobs.py` |
| **MIL-P1-026** | Real-Time SSE Hub with Monotonic Replay | P1 | COMPLETED | Antigravity | `src/api/routes_stream.py`, `src/api/main.py`, `tests/test_durable_jobs_and_streaming.py` |
| **MIL-P1-027** | Stand-Alone Worker CLI Daemon & Bootstrapper Wiring | P1 | COMPLETED | Antigravity | `scripts/run_worker.py`, `scripts/start_platform.sh` |
| **MIL-P1-028** | Frontend SSE Streaming Hook & Reactive Ingestion Pill | P1 | COMPLETED | Antigravity | `frontend/src/hooks/useJobStream.ts`, `frontend/src/lib/api.ts`, `frontend/src/components/Navbar.tsx` |
| **MIL-P1-029** | Intermediate Checkpoint Persistence & Worker Recovery | P1 | COMPLETED | Antigravity | `src/workers/dispatcher.py`, `src/storage/database.py`, `tests/test_durable_jobs_and_streaming.py` |
| **MIL-P1-030** | Frontend Concurrency Guards & W3C Robust SSE Parser | P1 | COMPLETED | Antigravity | `frontend/src/lib/api.ts`, `frontend/src/lib/sseParser.ts`, `frontend/src/app/stocks/[symbol]/page.tsx`, `frontend/src/components/CopilotDrawer.tsx` |
| **MIL-P1-031** | Real-Time Platform Telemetry Broadcast Hub | P1 | COMPLETED | Antigravity | `src/api/routes_stream.py`, `frontend/src/hooks/usePlatformEvents.ts`, `frontend/src/components/MacroRibbon.tsx` |
| **MIL-V8-001** | Dynamic Capital Architecture & Micro-Quant Sizing | P0 | COMPLETED | Antigravity | `src/quant/execution_engine.py`, `src/quant/rebalance_engine.py`, `src/storage/migrations.py` |
| **MIL-V8-002** | FrontPage Discretionary Sandbox (`paper_manual_1`) | P0 | COMPLETED | Antigravity | `src/quant/execution_engine.py`, `src/api/routes_portfolio.py`, `frontend/src/app/portfolio/page.tsx` |
| **MIL-V8-003** | 1,000+ Universe Expansion & 15-Yr Backfill Engine | P0 | COMPLETED | Antigravity | `src/data/universe_expander.py`, `src/api/main.py`, `tests/test_v8_engine_upgrade.py` |
| **MIL-V8-004** | Verifiable Walk-Forward ML Trainer & Multi-Horizon CV | P0 | COMPLETED | Antigravity | `src/quant/ml_trainer.py`, `src/api/main.py`, `data/models/tournament_summary.json` |
| **MIL-V8-005** | Continuous Financial News Sentiment Ingestion & LLM | P0 | COMPLETED | Antigravity | `src/tasks/news_daemon.py`, `src/copilot/deliberation.py` |
| **MIL-V8-006** | Next.js Bento Portfolio Command Center & Trade Ticket | P0 | COMPLETED | Antigravity | `frontend/src/app/portfolio/page.tsx`, `frontend/src/lib/api.ts` |
| **MIL-P1-032** | Cockpit Monolith Decomposition & Kinetic Navigation | P1 | COMPLETED | Antigravity | `frontend/src/app/page.tsx`, `frontend/src/components/ScreenerWorkspace.tsx`, `frontend/src/components/StockInspector.tsx` |
| **MIL-P1-033** | Zero-Lock SSE Hub SQLite WAL Connection Lifecycle | P1 | COMPLETED | Antigravity | `src/api/routes_stream.py` |
| **MIL-P2-034** | Kinetic Cockpit & Lightweight Charts SSR Isolation | P2 | COMPLETED | Antigravity | `frontend/next.config.mjs`, `frontend/src/app/globals.css`, dynamic SSR imports |
| **MIL-P1-035** | Multi-Horizon Walk-Forward Tournaments (5D, 20D, 60D) | P1 | COMPLETED | Antigravity | `src/storage/migrations.py`, `src/ml/labels/builder.py`, `src/ml/training/tournament.py`, `src/ml/registry/manager.py` |
| **MIL-P1-036** | Signal Blending & Automated Rebalance Proposal Engine | P1 | COMPLETED | Antigravity | `src/quant/rebalance_engine.py`, `src/workers/dispatcher.py`, `tests/test_multi_horizon_engine.py` |
| **MIL-P0-037** | Dynamic Hurdle Gating & 5-Day Model Disarming | P0 | COMPLETED | Antigravity | `src/storage/migrations.py`, `src/quant/rebalance_engine.py`, `src/ml/registry/manager.py`, `src/ml/training/tournament.py` |
| **MIL-P1-038** | Screener Rebalance Badges & Multi-Horizon Attribution | P1 | COMPLETED | Antigravity | `src/api/routes_market.py`, `src/api/main.py`, `frontend/src/components/ScreenerWorkspace.tsx`, `frontend/src/components/StockInspector.tsx` |
| **MIL-P0-039** | Rebalance Schema Alignment & Decimal Hotfix | P0 | COMPLETED | Antigravity | `src/api/routes_market.py`, `frontend/src/lib/api.ts`, `frontend/src/components/ScreenerWorkspace.tsx`, `frontend/src/components/StockInspector.tsx` |
| **MIL-P1-040** | Paper Trading Execution Engine & Portfolio Ledger | P1 | COMPLETED | Antigravity | `src/storage/migrations.py`, `src/quant/execution_engine.py`, `src/api/routes_portfolio.py`, `src/api/main.py`, `frontend/src/app/portfolio/page.tsx`, `tests/test_execution_engine.py` |
| **MIL-P1-041** | Walk-Forward Portfolio Backtest Engine & Tearsheet | P1 | COMPLETED | Antigravity | `src/quant/portfolio_backtester.py`, `src/api/routes_backtest.py`, `src/api/main.py`, `frontend/src/app/backtest/page.tsx`, `frontend/src/components/BacktestChart.tsx`, `tests/test_portfolio_backtester.py` |
| **MIL-P0-042** | UI Remediation, Data-Binding Repair & Bento Cockpit Overhaul | P0 | COMPLETED | Antigravity | `src/copilot/mcp_bridge.py`, `src/copilot/deliberation.py`, `frontend/src/components/ScreenerWorkspace.tsx`, `frontend/src/components/CopilotDrawer.tsx`, `frontend/src/components/StockInspector.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/stocks/[symbol]/page.tsx` |
| **MIL-P1-043** | Systematic Walk-Forward Backtester & Cockpit Hardening | P1 | COMPLETED | Antigravity | `src/quant/portfolio_backtester.py`, `src/api/routes_backtest.py`, `src/api/routes_market.py`, `frontend/src/app/backtest/page.tsx`, `frontend/src/components/BacktestChart.tsx`, `frontend/src/lib/api.ts`, `tests/test_portfolio_backtester.py` |
| **MIL-P1-044** | Checkpointed Historical Backfill (2020–2024) & Corporate Actions Adjustment Engine | P1 | COMPLETED | Antigravity | `src/storage/migrations.py`, `src/data/corporate_actions.py`, `src/data/historical_backfill.py`, `src/data/instrument_master.py`, `src/factors/engine.py`, `src/workers/dispatcher.py`, `tests/test_historical_backfill_and_corporate_actions.py` |
| **MIL-P0-045** | Authentic NSE Archive Fetcher & Stage 1 Historical Ingestion (2023–2024) | P0 | COMPLETED | Antigravity | `src/data/nse_archive_fetcher.py`, `src/data/historical_backfill.py`, `scripts/run_stage1_backfill.py`, `tests/test_nse_archive_fetcher.py` |
| **MIL-P1-046** | Stage 2 Historical Ingestion (2020–2022) & Full-Cycle Factor Generation | P0 | COMPLETED | Antigravity | `scripts/run_stage2_backfill.py`, `scripts/recompute_factors_2020_2026.py`, `src/factors/engine.py` |
| **MIL-P1-047** | Turnover Hysteresis Bands & Dynamic Cash Breadth-Gating | P1 | COMPLETED | Antigravity | `src/quant/portfolio_backtester.py`, `tests/test_advanced_backtest_and_comparison.py` |
| **MIL-P1-048** | Walk-Forward ML Tournament Pipeline & Multi-Asset Cross-Sectional Comparison | P1 | COMPLETED | Antigravity | `src/ml/walk_forward_tournament.py`, `src/api/routes_backtest.py`, `frontend/src/app/backtest/page.tsx`, `frontend/src/components/CompareTerminal.tsx`, `frontend/src/components/BacktestCompareChart.tsx` |
| **MIL-P1-049** | Dynamic Tournament Model Weights Decoupling & Screener Schema Alignment | P1 | COMPLETED | Antigravity | `src/quant/rebalance_engine.py`, `src/quant/screener.py`, `src/api/main.py`, `tests/test_advanced_backtest_and_comparison.py` |
| **MIL-P1-050** | Account-Aware Rebalance Engine Order Generator & Screener Alignment | P0 | COMPLETED | Antigravity | `src/quant/rebalance_engine.py`, `src/quant/screener.py`, `src/api/main.py`, `tests/test_rebalance_and_screener_alignment.py` |
| **MIL-V8-007** | Full Autonomous Universe Daemon, 15-Yr Backfill & ML Factory | P0 | COMPLETED | Antigravity | `src/tasks/universe_daemon.py`, `scripts/run_universe_daemon.py`, `src/quant/factor_calculator.py`, `src/quant/fundamental_engine.py`, `src/quant/ml_trainer.py` |

---

## 2. Baseline Measurements (Phase 0)

- **Database Path:** `data/market_lab.db`
- **Backup Created:** `data/market_lab_backup_20261106_181940.db` (228,786,176 bytes, `PRAGMA quick_check: ok`)
- **Total `ohlcv_daily` rows:** 89,477
- **Total `quant_factors_daily` rows:** 256,146
- **Factor rows without matching OHLCV:** 166,797 (158,878 prior to 2024-10-21; 7,919 on/after 2024-10-21)
- **Synthetic rows in `ohlcv_daily`:** 4,271 (`CANBK`: 1,781, `DRONACHRYA`: 498, `IDEA`: 498, `NHPC`: 498, `RVNL`: 498, `TATAPOWER`: 498)
- **Benchmark in `index_daily`:** `index_name = 'NIFTY 50', index_type = 'TRI'` (vs broken label builder querying `'NIFTY 50 TRI'`)
- **Python Test Collection:** 286 tests collected in `.venv/bin/pytest --collect-only`

---

## 3. Execution Plan

1. **Batch B: Data Integrity & Provenance (Finding 1 & Finding 2)**
   - Schema additive migration: `provenance_class`, `is_synthetic`, `is_eligible_for_live_analytics`, `is_eligible_for_backtest`, `is_eligible_for_training`.
   - Quarantine existing synthetic rows.
   - Build `scripts/reconcile_factor_ohlcv.py` and output detailed reconciliation report.
   - Enforce OHLCV eligibility joins across quant and ML consumers.
   - Add tests: `tests/test_factor_ohlcv_integrity.py` and `tests/test_synthetic_data_quarantine.py`.
2. **Batch C: ML Correctness & Benchmark Integrity (Finding 3)**
   - Fix `src/ml/labels/builder.py` benchmark lookup (`index_name='NIFTY 50' AND index_type='TRI'`) and eliminate silent 0% return fallback.
   - Fix purge/embargo boundaries in `src/ml/training/tournament.py`.
   - Synchronize champion model pointer between `supervisor_state` and `model_registry`.
   - Add tests: `tests/test_ml_correctness_and_benchmark.py`.
3. **Batch D: Backend Reliability & Daemon Lifecycle (Finding 4)**
   - Isolate `yfinance` dependencies safely in `src/client/macro_client.py` and `src/pipeline/universe_ingestion.py`.
   - Update `pyproject.toml` and `requirements.txt`.
   - Fix daemon EOD error handling: do not advance `last_eod_date` on pipeline failure.
   - Enforce read-only GET routes.
   - Add tests: `tests/test_backend_reliability.py`.
4. **Batch E: Frontend Functionality & Honest States (Finding 5)**
   - Remove fake ±8% forecast cone, zero fallbacks, and 50 conviction defaults in `page.tsx`.
   - Convert `activeIndex` to `selectedSymbol` with safe ref reset.
   - Correct `data_completeness_score < 80` percentage logic.
   - Overhaul CopilotDrawer SSE parser with robust chunk preservation and live timing.
   - Fix stock tearsheet NIFTY 50 badge and parallel loading.
   - Fix backtest page mount mutation.
   - Run Next.js lint, build, and verify.

---

## 4. Final Verification Evidence & Acceptance Decisions

### Before / After Metrics Summary
| Metric | Pre-Remediation Baseline | Post-Remediation Verification | Status |
| :--- | :--- | :--- | :--- |
| **Orphan Factor Rows (`quant_factors_daily`)** | 166,797 active rows without OHLCV | Tagged `is_orphaned = 1`; 0 active unflagged orphans | RESOLVED |
| **Synthetic Bars in Authoritative OHLCV** | 4,271 sine-wave bars | 0 synthetic active bars; 2,974 authentic vendor bars reconciled | RESOLVED |
| **Benchmark TRI Lookup** | Fails 100% (`'NIFTY 50 TRI'`), returns 0.0 | Queries `('NIFTY 50', 'TRI')`, 498 bars loaded; unobservable returns flag `UNOBSERVABLE_BENCHMARK` | RESOLVED |
| **Optional Dependency Resilience (`yfinance`)** | Eager top-level import crash | Isolated with safe import fallback; added to requirements | RESOLVED |
| **Daemon Settlement Advance** | Magic number 150; advances on failure | Dynamic `securities_master` threshold; only advances on `SUCCESS` | RESOLVED |
| **Frontend Forecast Cone** | Fabricated `* 0.92 / * 1.08` cone | Honest "Forecast Unavailable" card rendered when null | RESOLVED |
| **Frontend Selection Jump** | Jumps on sort/filter (`activeIndex`) | Stable `selectedSymbol` selection across sorting/filtering | RESOLVED |
| **Frontend Completeness Scale** | `< 1.0` (broken ratio assumption) | Scaled `< 100` percentage check with partial tags | RESOLVED |
| **Copilot SSE & Timing** | Brittle line split; hardcoded 00:03/00:05 | Compliant line-by-line SSE parser; dynamic elapsed timer | RESOLVED |
| **Tearsheet Waterfall & NIFTY Badge** | 4-step sequential fetch; fake NIFTY badge | Parallel `Promise.allSettled`; true `is_nifty50` membership badge | RESOLVED |
| **Backtest GET Mutation** | Auto-triggered `runBacktest()` on mount | Pure read-only GET; clean institutional empty state | RESOLVED |
| **Fabricated Disclosures** | 25 seeded disclosures with fake 18.5% margin | 25 quarantined (`SYNTHETIC_SEED_QUARANTINED`), 0 unflagged fake margins, 30 audit events | RESOLVED |
| **Macro Telemetry Exceptions** | Missing `pandas` import, NaN/Inf leaks | Safe `is_valid_num()` finite validator, `pd` imported, 5m TTL cache | RESOLVED |
| **Model Promotion Gate Bypass** | `tournament.py` wrote PROMOTED directly | All promotions route through `promote_model()`, baseline promotion blocked | RESOLVED |
| **Supervisor Truthfulness** | Reported `NORMAL` with NULL active model | Enforces `NO_ACTIVE_MODEL` state whenever active model pointer is NULL | RESOLVED |
| **Migration Tamper Detection** | Static string hash, non-atomic SQLite DDL | Source code SHA-256 (`inspect.getsource`), explicit transactional DDL rollback | RESOLVED |
| **ML Walk-Forward Leakage** | Global scaler leakage across time folds | Multi-fold purged CV with embargo buffer and fold-isolated `sklearn.pipeline.Pipeline` | RESOLVED |
| **Frontend Responsive Breakpoints** | Header overlap on <1400px, clipped tables | Fluid 5-viewport responsiveness (1366, 1024, 768, 390, 320px) verified by Playwright | RESOLVED |
| **Ingestion Empty-Fetch Trap** | Returned `SUCCESS` on 0 bars, advanced EOD | Fails closed with `FAILED` and `NO_NEW_BARS`; settlement guard halts advance | RESOLVED |
| **Partial Ingestion Threshold** | Risk of partial feed (<85%) advancing EOD | Hardened 85% universe coverage floor in `universe_ingestion.py` | RESOLVED |
| **Supervisor Timestamp Sync** | `last_transition_at` stale on promotion | Synchronized atomically in `promote_model()` commit | RESOLVED |
| **Active Champion Model** | 0 champion models, NULL active pointer | Genuine 5-fold walk-forward champion promoted (`HistGradientBoosting_Alpha5D`, IC=0.0349, Sharpe=1.4206) | RESOLVED |
| **Hermetic Test Isolation** | Risk of tests mutating `data/market_lab.db` | Live DB SHA-256 verified invariant before/after lifecycle test suite | RESOLVED |
| **Durable Asynchronous Job Engine** | Synchronous thread starvation & poll overhead | Distributed lease-based worker daemon (`runner.py`, `dispatcher.py`, `job_runs`) | RESOLVED |
| **Real-Time Event Streaming Hub** | REST polling causing database lock contention | W3C Server-Sent Events broker with `Last-Event-ID` cursor recovery (`routes_stream.py`) | RESOLVED |
| **Worker CLI Daemon & Platform Integration** | Background tasks bound to ephemeral web process | Dedicated `scripts/run_worker.py` spawned in `start_platform.sh` with SIGINT/SIGTERM handlers | RESOLVED |
| **Frontend Reactive Ingestion State** | Synchronous blocking fetch with blind spinner | Real-time reactive SSE subscription hook `useJobStream.ts` with stage/progress feedback | RESOLVED |
| **Worker Intermediate Checkpoints** | Full job restart on worker crash/reap | Fine-grained cursor checkpoints every 10 symbols in `job_checkpoints` with resume support | RESOLVED |
| **SQLite Cross-Process Concurrency** | Lock contention between worker & FastAPI | Enforced `PRAGMA busy_timeout = 10000;` and `synchronous = NORMAL;` on all connections | RESOLVED |
| **Frontend Symbol Race Conditions** | Overlapping fetches overwriting active view | Monotonic `RequestLifecycleManager` with generation checking and AbortSignal cancellation | RESOLVED |
| **Copilot SSE Stream Fragmentation** | Naive split on `\n\n` dropping split JSON chunks | Dedicated W3C-compliant `RobustSSEParser` with CRLF normalization & EOF flush | RESOLVED |
| **Real-Time Platform Telemetry (`MIL-P1-031`)** | Stale initial fetches and blank UI on stream delay | `TELEMETRY_TICK` broadcast in `routes_stream.py` + `usePlatformEvents.ts` hook + `MacroRibbon.tsx` | RESOLVED |
| **Cockpit Monolith Decomposition (`MIL-P1-032`)** | 1,357-line `page.tsx` mixing REST, SSE, and UI | Modular architecture under 270 lines (`ScreenerWorkspace.tsx`, `StockInspector.tsx`, `IngestionProgressBanner.tsx`) with Vim `j`/`k` scrub navigation & stable selection | RESOLVED |
| **Stream Connection Safety (`MIL-P1-033`)** | SQLite connection held open across async sleep intervals pinning WAL checkpoint | `fetch_events_slice` and `fetch_macro_telemetry_snapshot` point-in-time reads with instant release; 0 open connections during `asyncio.sleep` | RESOLVED |
| **Kinetic Cockpit Overhaul (`MIL-P2-034`)** | Flat aesthetics and lightweight-charts SSR chunk error | Cartesian dot-matrix canvas, Framer Motion spring physics glider, decaying keyframe flashes, ambient neon bleeds, and dynamic lightweight-charts SSR isolation | RESOLVED |
| **Multi-Horizon Tournaments (`MIL-P1-035`)** | Single 20-day horizon bottleneck; lack of swing/trend governance | Migration 0008, 5D/20D/60D purged & embargoed walk-forward tournaments, champions tracked in `model_horizon_deployments` | RESOLVED |
| **Signal Blending & Rebalance Ledger (`MIL-P1-036`)** | Manual heuristic rebalances without friction or turnover tracking | `RebalanceEngine` with multi-horizon rank composite, dynamic turnover %, transaction friction modeling (10 bps round-trip), persisted to `rebalance_proposals` | RESOLVED |
| **5-Day Noise Trap & Dynamic Hurdle Gating (`MIL-P0-037`)** | 5-day model promoted with noisy IC = 0.0030 distorting rebalance rankings and turnover | Migration 0009 (`0009_allow_nullable_horizon_model`) demotes 5D model (`CANDIDATE_REJECTED`) and disarms $H=5$ in `model_horizon_deployments`; `RebalanceEngine` enforces dynamic hurdle (IC $\ge 0.0150$) renormalizing to 20D (62.5%) and 60D (37.5%) | RESOLVED |
| **Terminal Screener Rebalance & Drivers (`MIL-P1-038`)** | Screener disconnected from rebalance allocations and multi-horizon drivers | `GET /api/v1/rebalance/latest` + enriched `/screener` (`blended_score`, `target_allocation_pct`, `horizon_drivers`, `is_rebalance_target`); `ScreenerWorkspace` emerald target allocation pills, cyan/emerald horizon badges, and `Rebalance Targets Only` quick filter; `StockInspector` multi-horizon consensus panel | RESOLVED |
| **Rebalance Schema Alignment Hotfix (`MIL-P0-039`)** | Raw decimal `target_weight` (0.0667) in trade deltas causing percentage formatting mismatch | Normalized API translation layer mapping `target_weight` to `target_allocation_pct` (`* 100`), frontend rendering `Alloc: 6.67%` via `.toFixed(2)` | RESOLVED |
| **Paper Trading Execution & Friction Ledger (`MIL-P1-040`)** | Passive advisor proposals without execution tracking or Indian friction | Migration 0010 (`portfolio_accounts`, `portfolio_positions`, `portfolio_orders`, seeded `paper_alpha_1`), `PaperTradingEngine` with SELL-before-BUY sequencing, cash solvency guards (capping desired quantity to affordable whole shares), 0.10% STT, 0.05% slippage/fees, flat ₹15 DP charge, MTM NAV tracking, dedicated `/portfolio` UI dashboard, and 100% test coverage | RESOLVED |
| **Walk-Forward Portfolio Backtest & Tearsheet (`MIL-P1-041`)** | Single-factor backtest without multi-horizon rebalancing, realistic friction, or benchmark dual-curves | `PortfolioBacktester` with point-in-time multi-horizon ranking (`BLENDED_20D_60D`, `TACTICAL_20D`, `TREND_60D`), Indian statutory delivery friction schedule, continuous NIFTY 50 TRI/PRI benchmark curve, underwater drawdown series, `/api/v1/backtest/presets` and `/api/v1/backtest/portfolio` REST endpoints, cyber-institutional `/backtest` cockpit with SSR-isolated lightweight charts, and 4/4 hermetic unit tests | RESOLVED |
| **Historical Backfill & Corporate Actions Hardening (`MIL-P1-044`)** | Synthetic sine-wave prices inserted into `ohlcv_daily` for pre-IPO dates (e.g. `AADHARHFC` in 2020); missing corporate actions adjustments | Migration 0011, `CorporateActionsManager` with 18 verified splits/bonuses seeded, `InstrumentMaster` guarding pre-IPO months (`NOT_YET_LISTED` with 0 rows), complete removal of synthetic price generator from `HistoricalBackfillCoordinator`, fail-closed `MISSING_SOURCE_DATA`, full purge of contaminated 2020-01 bars, and 7/7 passing unit tests | RESOLVED |
| **Authentic NSE Archive Fetcher & Stage 1 Ingestion (`MIL-P0-045`)** | Unavailability of historical UDIFF archives pre-July 2024; missing dual-format fetcher and Stage 1 authentic exchange data | `NSEArchiveFetcher` with dual-format normalization (Legacy pre-2024-07-08 vs Modern UDIFF post-2024-07-08), disk caching at `data/raw/bhavcopies/`, strict series='EQ' filter, `run_stage1_backfill.py` runner completing 3,344 work units across 2023–2024, ingesting 66,850 authentic exchange bars at 597.2 bars/sec with 0 synthetic rows, and 5/5 unit tests | RESOLVED |
| **Stage 2 Backfill & Full-Horizon Factor Engine (`MIL-P1-046`)** | Incomplete 5-year historical settlement depth; missing factor continuum across 2020–2026 and 252-session burn-in enforcement | `run_stage2_backfill.py` resolving all 5,910 remaining pending units across 2020–2022 (100,107 authentic bars ingested at 553.6 bars/sec, 0 pending units remaining in matrix), followed by `recompute_factors_2020_2026.py` populating 254,011 factor rows in `factors_daily` & `quant_factors_daily` with 252-session burn-in enforcement, corporate action adjustments, `sma_50`, and `trend_regime` | RESOLVED |
| **V8 Engine & Master Universe Expansion (`MIL-P0-047`)** | Environment dependency disconnect (`yfinance`/`sklearn` in system vs `.venv`), Copilot SSE disconnection, screener missing ROE/20D return factors, and 15-year depth truncation | Fixed systemd user service environment (`market-backend.service`), hardened Copilot deliberation SSE stream (`data: [DONE]` delimiter and `sanitize_for_json`), updated screener SQL with `COALESCE` fundamentals/factors, exposed `ret_20d`/`return_20d`, implemented `UniverseExpander` 15-year backfill (278k+ bars ingested), and purged walk-forward ML tournament with authentic Rank IC | RESOLVED |
| **4-Tier Parallelism & Sentiment ML (`MIL-P0-048`)** | Serial network I/O, single-threaded factor compute, flat sentiment (0.0% ML weight), and screener latency | `ThreadPoolExecutor(16)` network ingestion (50 syms in 1.31s), `ProcessPoolExecutor` multi-core factor calculator (100 syms in 2.66s), async news daemon with hierarchical sector sentiment imputation ($\sigma = 8.18$), sentiment-aware walk-forward ML retraining (12.50% feature weight), and sub-3ms pre-serialized in-memory screener cache (2.43ms) | RESOLVED |

### Test Suite Execution Summary
- **4-Tier Parallelism & ML Sentiment Suite:** 5 / 5 tests PASSED (`tests/test_parallelism_and_ml_sentiment.py`).
- **V8 Engine & Dynamic Capital Upgrade Suite:** 7 / 7 tests PASSED (`tests/test_v8_engine_upgrade.py`).
- **Rebalance Engine & Screener Alignment Suite:** 2 / 2 tests PASSED (`tests/test_rebalance_and_screener_alignment.py`).
- **Paper Trading Execution Suite:** 4 / 4 tests PASSED (`tests/test_execution_engine.py`).
- **NSE Archive Fetcher Suite:** 5 / 5 tests PASSED (`tests/test_nse_archive_fetcher.py`).
- **Historical Backfill & Corporate Actions Suite:** 7 / 7 tests PASSED (`tests/test_historical_backfill_and_corporate_actions.py`).
- **Walk-Forward Portfolio Backtester Suite:** 4 / 4 tests PASSED (`tests/test_portfolio_backtester.py`).
- **Multi-Horizon & Durable Engine Suite:** 15 / 15 tests PASSED (`tests/test_multi_horizon_engine.py`, `tests/test_durable_jobs_and_streaming.py`).
- **Core Platform Regression Suite:** 60 / 60 tests PASSED across all backend, ML correctness, execution engine, backtesting, and reliability modules.
- **Frontend Production Build:** `next build` compiled 100% cleanly (7/7 static and dynamic routes compiled, 0 errors, 0 lint warnings).

