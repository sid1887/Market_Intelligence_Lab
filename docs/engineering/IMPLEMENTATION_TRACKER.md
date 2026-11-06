# Market Intelligence Lab (MIL) — Implementation Tracker
**Status:** ACTIVE EXECUTION  
**Last Updated:** 2026-11-06  
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

### Test Suite Execution Summary
- **P0 Remediation Test Suite:** 34 / 34 tests PASSED (`tests/test_factor_ohlcv_integrity.py`, `tests/test_synthetic_data_quarantine.py`, `tests/test_ml_correctness_and_benchmark.py`, `tests/test_backend_reliability.py`, `tests/test_ml_lifecycle.py`, `tests/test_migration_0005_and_tamper.py`, `tests/test_dynamic_ingestion.py`).
- **Targeted Quantitative Suite:** 45 / 45 tests PASSED (`test_milestone_b4.py`, `test_milestone_b7_forecasting.py`, `test_dynamic_ingestion.py`, `test_migration_0005_and_tamper.py`, `test_ml_lifecycle.py`, `test_ml_correctness_and_benchmark.py`).
- **Frontend Production Build:** `next build` compiled 100% cleanly (6/6 static and dynamic routes compiled, 0 errors, 0 lint warnings).
- **Playwright Visual Verification:** 8 full-page viewport screenshots rendered and validated across 1366×768, 1024×768, 768×1024, 390×844, and 320×740.
- **Database Backup & Integrity:** Verified intact at `data/market_lab.db` (SHA256: `570684779ac1338bf68adeeb3dd22fa494c144468cf916841a35e4803c7cff86`, WAL truncated, PRAGMA quick_check: ok).

