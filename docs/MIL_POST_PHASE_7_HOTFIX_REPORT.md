# MIL 2.0 — Post-Phase 7 Hotfix Report: Data Dedup, Quarterly Bars, Tournament Sync & Supervisor Cache

**Execution Timestamp:** 2026-11-24T21:21:00+05:30  
**Target Environment:** Render Free (0.1 vCPU / 512 MB RAM, Target Peak < 390 MB)  
**Status:** PASS & ALL 51 TESTS VERIFIED

---

## 1. Executive Summary & Root Cause Analysis

Following the Phase 7 Alpha Research Track 1 upgrade, this hotfix addresses 4 production edge cases across telemetry, UI rendering, tradebook consistency, and supervisor latency:

1. **Tournament Summary Deployment & `/api/v1/health` Synchronization:**
   - **Root Cause:** Stale `model_registry` database rows were prioritized ahead of the definitive `data/models/tournament_summary.json` file. Additionally, `.gitignore` previously ignored the entire `data/models/` directory, preventing the compact 4.8 KB `tournament_summary.json` from being shipped to Render.
   - **Fix:** Explicitly whitelisted `!data/models/tournament_summary.json` in `.gitignore` and `.dockerignore` while keeping heavy `.joblib` / `.pkl` binaries excluded. Updated `/api/v1/health` to authoritatively query `tournament_summary.json` first, accurately reflecting `Deterministic Baseline (Momentum+LowVol+PIT)` when ML candidates receive `REJECTED_BELOW_BASELINE`.

2. **Elimination of `576 MB` RSS Spike on `GET /api/v1/supervisor/status`:**
   - **Root Cause:** Two unindexed full-table scans across 2,930,136 rows of `ohlcv_daily`:
     - `SELECT MAX(retrieval_timestamp) FROM ohlcv_daily;` (1,868 ms).
     - `SELECT COUNT(*) FROM ohlcv_daily WHERE is_synthetic = 1 ...` in `get_current_state()` (290 ms).
     - These full-table scans flooded SQLite page cache and bloated process RSS up to 576 MB.
   - **Fix:**
     - Created covering index `idx_ohlcv_status_date ON ohlcv_daily(data_status, trading_date DESC)`.
     - Created partial index `idx_ohlcv_synthetic ON ohlcv_daily(is_synthetic, provenance_class) WHERE is_synthetic = 1`.
     - Replaced `ohlcv_daily` scan for ingestion timestamp with sub-millisecond metadata lookup on `ingestion_audit_log` (`MAX(created_at)`) and `job_runs`.
     - Wrapped `/api/v1/supervisor/status` and `/supervisor/status` in a 30-second TTL cache.
   - **Result:** Latency dropped from `2,370 ms` to **`9.19 ms` (p50)** and **`35.21 ms` (p95)**; peak workload memory remained constrained to **`381.52 MB`** (well below the 390 MB threshold and Render's 512 MB ceiling).

3. **Deduplication of `real_closed_roundtrips`:**
   - **Root Cause:** Historical legacy imports had inserted 32 incomplete duplicate records with empty ISIN and `None` sell dates, matching 4 complete roundtrips (SUZLON, M&MFIN, RVNL, ASHOKLEY). This multiplied trade counts 8x and distorted hold-day and Trader DNA metrics.
   - **Fix:** Implemented an idempotent deduplication pass in `DatabaseManager._migrate_schema()` and `EncryptedTradebookEngine.deduplicate_closed_roundtrips()` that deletes incomplete records where `(symbol, qty, round(avg_buy, 2), round(avg_sell, 2))` matches a complete record with non-empty `isin` and `sell_date`. Implemented `is_state_dirty()` and invoked `mark_state_dirty()` to trigger Azure Blob synchronization (`mil-durable-state`).
   - **Result:** Purged 32 phantom rows; exactly 4 verified closed trades remain.

4. **Zero-Variance Bar Scaling & Carry-Forward Duplicate Protection:**
   - **Quarterly Financials Bar Scaling (`QuarterlyFinancialsCard.tsx`):**
     - When all displayed quarters have identical positive values (`max === min > 0`, e.g. ₹225 Cr across 4 quarters), bars now render at `65%` height inside an explicit `h-24` bar track within the `h-36` container, preventing collapse to 0%. Value labels are now visible above every bar.
   - **Carry-Forward Duplicate Quarantine (`ttm_builder.py` & `pead_engine.py`):**
     - Consecutive quarters on the same symbol with identical `(revenue, pat, eps_diluted)` tuples are tagged as `CARRY_FORWARD_DUPLICATE`.
     - `pead_engine.py` explicitly ignores `CARRY_FORWARD_DUPLICATE` filings, preventing artificial post-earnings drift spikes on repeated annual/period numbers.

---

## 2. Benchmark Verification (`scripts/benchmark_runtime.py`)

```
================================================================================
RENDER PRODUCTION BENCHMARK REPORT (0.1 vCPU / 512 MB CEILING)
================================================================================
Port Bind Latency:         2628.43 ms
Hydration Latency:         6457.95 ms
Idle Process RSS:          364.40 MB
Peak Observed Memory:      381.52 MB (Ceiling Target: < 390.0 MB / Limit: 512.0 MB)
Available OOM Headroom:    130.48 MB (> 100 MB safety buffer)
--------------------------------------------------------------------------------
Workload Latency (p50):    35.21 ms
Workload Latency (p95):    1376.20 ms
Workload Latency (p99):    1641.15 ms
Benchmark Status:          PASS (VERIFIED SAFE)
================================================================================

Endpoint Breakdown:
- GET /api/v1/supervisor/status:       p50: 9.19 ms   | p95: 35.21 ms  (Target: < 100 ms)
- GET /api/v1/health:                  p50: 200.09 ms | p95: 270.22 ms
- GET /api/v1/screener?limit=50:       p50: 20.51 ms  | p95: 38.73 ms
- GET /api/v1/stocks/RELIANCE/status:  p50: 14.31 ms  | p95: 41.48 ms
- POST /api/v1/copilot/deliberate:     p50: 1342.32 ms| p95: 1641.15 ms
```

---

## 3. Test Suite & Verification Matrix

- **Unit Tests:** `tests/test_post_phase7_hotfix.py` (4 tests passing).
- **Full Regression Suite:** 51 passing tests across Phases 2–7 + Hotfix:
  - `tests/test_phase2_data_truth.py` (7 tests)
  - `tests/test_phase3_validation.py` (14 tests)
  - `tests/test_phase4_execution_and_copilot.py` (9 tests)
  - `tests/test_phase5_hardening.py` (5 tests)
  - `tests/test_phase6_ui_endpoints.py` (3 tests)
  - `tests/test_phase7_flow_and_pead.py` (9 tests)
  - `tests/test_post_phase7_hotfix.py` (4 tests)
- **Frontend Build:** `npm --prefix frontend run build` exited with code 0 across all 8 routes.
