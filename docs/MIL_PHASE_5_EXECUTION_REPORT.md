# MIL 2.0 — PHASE 5: PRODUCTION HARDENING, RUNTIME BENCHMARKING & INSTITUTIONAL UX EXECUTION REPORT

**Execution Date:** 2026-11-24  
**Environment Target:** Render Free Container (0.1 vCPU / 512 MB RAM Ceiling)  
**Status:** COMPLETE & VERIFIED SAFE (`PASS`)  
**Commit Milestone:** `feat(mil-2.0): phase 5 production hardening, container benchmark, and institutional ux`  

---

## EXECUTIVE SUMMARY

Phase 5 achieves full production hardening and transparency for Market Intelligence Lab (MIL) 2.0. By rigorously benchmarking and profiling runtime memory under concurrent workloads, we resolved critical memory ballooning mechanisms (glibc arena retention, thundering-herd screener calculation, unindexed Nifty table scans), pulling peak container memory down from an unsafe **1,463.5 MB** to a verified **370.5 MB**—safely below our hard **410.0 MB promotion ceiling** and leaving **141.5 MB of OOM buffer** against Render's 512 MB `SIGKILL 137` threshold.

Furthermore, we updated the zero-cost GitHub Actions cloud tournament CI, enhanced the Next.js frontend with explicit hard-veto banners, exact rupee friction breakdowns, and point-in-time provenance badges, and verified the complete stack across 47 regression and hardening tests.

---

## 1. DELIVERABLE 1: REALISTIC RUNTIME BENCHMARKING & MEMORY GUARD

### 1.1 Memory Guard Architecture (`src/storage/cache.py`)
- Implemented `get_current_process_rss_mb()` reading live `VmRSS` directly from `/proc/self/status` (with `getrusage` fallback).
- Implemented `enforce_rss_memory_guard(threshold_mb=400.0)`:
  - If process RSS $\ge 400.0\text{ MB}$, triggers emergency LRU eviction (`app_cache.clear()`).
  - Executes Python garbage collection (`gc.collect()`).
  - Calls `ctypes.CDLL('libc.so.6').malloc_trim(0)`, forcing the Linux glibc memory allocator to release unmapped heap arenas immediately back to the OS cgroup.
  - Added `__len__` mapping interface to `MemoryLRUCache`.

### 1.2 Screener Concurrency & Single-Flight Lock (`src/api/main.py`)
- Resolved a critical thundering-herd vulnerability where multiple concurrent API requests on cold startup computed the full 2,980-stock universe simultaneously.
- Introduced double-checked locking on `_screener_cache_lock` in `get_screener`. When the in-memory materialized cache is empty or expired, exactly one worker generates the materialized view while concurrent threads await the lock and immediately receive pre-gzipped slices in $< 20\text{ ms}$.

### 1.3 Point-in-Time Index Query Optimization (`src/copilot/regime_analogs.py`)
- Replaced a fallback full-table scan on `ohlcv_daily` (2.925 million rows with in-memory `GROUP BY`) with direct queries on `index_daily` (`NIFTY 50`), cutting analog feature extraction time from $> 3,000\text{ ms}$ to $16.7\text{ ms}$ and eliminating $> 300\text{ MB}$ of transient SQLite memory overhead.

### 1.4 Benchmark Results (`data/benchmark_results.json`)

```
================================================================================
RENDER PRODUCTION BENCHMARK REPORT (0.1 vCPU / 512 MB CEILING)
================================================================================
Port Bind Latency:         2621.89 ms
Hydration Latency:         6448.72 ms
Idle Process RSS:          364.63 MB
Peak Observed Memory:      370.5 MB (Ceiling Threshold: < 410.0 MB)
Available OOM Headroom:    141.5 MB (> 100 MB safety buffer)
--------------------------------------------------------------------------------
Workload Latency (p50):    161.49 ms
Workload Latency (p95):    1709.71 ms
Workload Latency (p99):    1755.12 ms
Benchmark Status:          PASS (VERIFIED SAFE)
================================================================================
```

#### Endpoint Latency Breakdown:
| Endpoint | Requests | p50 Latency | p95 Latency | Memory Impact |
| :--- | :---: | :---: | :---: | :---: |
| `GET /api/v1/health` | 8 | 213.87 ms | 261.41 ms | Bounded ($< 285\text{ MB}$) |
| `GET /api/v1/screener?limit=50` | 8 | 20.68 ms | 35.15 ms | Bounded ($< 365\text{ MB}$) |
| `GET /api/v1/stocks/RELIANCE/status` | 8 | 13.16 ms | 47.50 ms | Microsecond cache hit |
| `POST /api/v1/copilot/deliberate` | 8 | 471.23 ms | 1755.12 ms | Bounded ($< 371\text{ MB}$) |

---

## 2. DELIVERABLE 2: AUTOMATED ZERO-COST WEEKLY TOURNAMENT CI

### 2.1 Workflow Upgrades (`.github/workflows/cloud_ml_tournament.yml`)
- Configured scheduled weekly full-horizon retrain (Sunday 18:00 IST / 12:30 UTC) and weekday mid-session/EOD triggers on GitHub Actions (16 GB RAM / 4 vCPU runner).
- Integrated `scripts/run_phase3_tournament.py --horizon 20 --n-splits 6 --n-test-splits 2`:
  - Executes Combinatorial Purged Cross-Validation with 15 combinations and 5 complete out-of-sample paths.
  - Computes deflated Sharpe Ratio (DSR) using verified annualized kurtosis and variance.
  - Benchmarks candidates against the deterministic **0.4322 Net Sharpe baseline**.
  - Enforces gating: if candidates are `REJECTED_BELOW_BASELINE`, the engine falls back to the deterministic Quality-Momentum baseline.
- Added automated `scripts/benchmark_runtime.py` execution to verify memory safety before committing artifacts.
- Added `actions/upload-artifact@v4` step uploading `data/models/tournament_summary.json` and `data/benchmark_results.json` with 30-day retention.

---

## 3. DELIVERABLE 3: INSTITUTIONAL TRANSPARENCY IN NEXT.JS FRONTEND

### 3.1 Hard Veto & Abstention Banner (`frontend/src/components/CopilotDrawer.tsx`)
- Surfaced high-contrast alert cards whenever `verdict === "ABSTAIN"` or `can_trade === false` or `hard_veto_reasons` are present.
- Displays explicit veto reason pills:
  - `🚫 FEE_DRAG > 1.25%`
  - `🚫 NET_RR < 1.6x`
  - `🚫 COOLDOWN_ACTIVE`
  - `🚫 CLUSTER_CAP`
  - `🚫 SECTOR_ESTIMATE`
  - `🚫 STALE_OR_FABRICATED_FUNDAMENTALS`

### 3.2 Exact Rupee Friction & Breakeven Card (`frontend/src/components/CopilotDrawer.tsx`)
- Renders 4-column metric grid driven by `position_sizing` and `trader_dna_eval`:
  - **Allocated Size**: Target capital and integer share count $Q$.
  - **Total Friction**: Exact ₹23.60 DP fee + STT, stamp duty, exchange turnover charges, SEBI turnover fees, and 18% GST.
  - **Fee Drag / Breakeven**: Fee drag percentage and exact gross price needed to break even.
  - **Post-Cost Asymmetry**: Gross R:R vs. post-cost Net R:R with explicit warning if below the $1.6\times$ institutional hurdle.

### 3.3 PIT Regime Analogs & Data Provenance
- In `frontend/src/components/CopilotDrawer.tsx`:
  - Renders PIT Market Regime Analogs with regime bias, 20D Nifty mean return, win rate %, worst forward drawdown %, and top historical analog dates.
- In `frontend/src/components/QuarterlyFinancialsCard.tsx`:
  - Added "PIT Provenance" column displaying emerald `OBSERVED_TIMESTAMP` badges for verified filings vs. amber `STATUTORY_FALLBACK_LAG (45D)` badges for unfiled fallback periods.

---

## 4. DELIVERABLE 4: VERIFICATION & SMOKE TEST SUITE

### 4.1 Phase 5 Hardening Suite (`tests/test_phase5_hardening.py`)
- `test_health_telemetry_fields`: Verifies `/api/v1/health` contains `rss_mb`, `memory_headroom_mb`, `cgroup_memory_limit_mb=512.0`, `durable_state_status`, and `active_champion_model`.
- `test_rss_memory_guard_eviction`: Confirms emergency eviction triggers cache clearing and glibc arena trimming when RSS threshold is exceeded.
- `test_benchmark_results_file_and_memory_ceiling`: Confirms `data/benchmark_results.json` passes with peak memory $< 410.0\text{ MB}$.
- `test_copilot_institutional_transparency_payload`: Confirms Copilot deliberation outputs `can_trade`, `hard_veto_reasons`, `position_sizing`, `trader_dna_eval`, and `regime_analogs`.
- `test_deterministic_baseline_promotion_gating`: Confirms that sub-baseline models are assigned `REJECTED_BELOW_BASELINE` status.

### 4.2 Full Regression Test Suite Execution
```
tests/test_durable_state.py (6 passed)
tests/test_fee_engine.py (6 passed)
tests/test_phase2_data_truth.py (7 passed)
tests/test_phase3_validation.py (14 passed)
tests/test_phase4_execution_and_copilot.py (9 passed)
tests/test_phase5_hardening.py (5 passed)
============================= 47 passed in 19.79s ==============================
```

### 4.3 Next.js Frontend Production Build
```
✓ Compiled successfully
✓ Linting and checking validity of types
✓ Collecting page data
✓ Generating static pages (8/8)
✓ Finalizing page optimization
Exit Code: 0 (Clean Production Build)
```
