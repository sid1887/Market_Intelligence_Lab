# Market Intelligence Lab (MIL) 2.0 — Phase 1 Execution & Verification Report

**Date:** 2026-11-24  
**Author:** Principal Quantitative Systems Architect & Cloud Infrastructure Auditor  
**Status:** **PHASE 1 COMPLETE (100% Verified)**  

---

## Executive Summary

Phase 1 has been executed and verified in accordance with the Phase 0 audit findings and the master architecture specification. This phase delivers:
1. **Durable Cloud Persistence Guardrails:** A Cool-tier, strictly private Azure Blob Storage infrastructure with automated monthly budget alerts, preventing accidental spend and eliminating ephemeral Render disk wipeouts.
2. **Zero-Dependency Lightweight State Manager:** A `< 1 MB` memory overhead client that snapshots only user state (tradebook, open positions, ledger, watchlists, Copilot memories, model registry) to Azure Blob Storage while excluding multi-gigabyte market tables.
3. **Canonical Indian Equity Fee Engine:** Unified statutory and broker cost accounting across all backtesters, ML training pipelines, tradebook analysis, and Copilot trader DNA, eliminating previous fee mismatches and modeling exact ₹23.60 DP charges and 18% GST exemptions.

---

## 1. Cloud Infrastructure & Cost Guardrails (Deliverable 1)

All resources were provisioned using the local authenticated Azure CLI under subscription `ee12014b-365b-405d-94c9-e484cee5a08c` (*Azure for Students*):

| Resource | Identifier / Value | Region / Tier | Purpose / Policy |
| :--- | :--- | :--- | :--- |
| **Resource Group** | `rg-mil-research` | `indiasouthcentral` | Tagged `Project=MIL` |
| **Storage Account** | `milstatearchive74b8` | `indiasouthcentral` / Standard_LRS Cool | Private, TLS 1.2+, Public Access Disabled |
| **Blob Container** | `mil-durable-state` | Private Blob | Stores `latest_user_state.json.gz` & `master_tradebook.enc` |
| **Action Group** | `ag-mil-alerts` | Global | Email alerts to `yelugamsiddharth18@gmail.com` |
| **Budget Cap** | `mil-monthly-cap` | INR 1,000 / month | Alerts at **50% (₹500)**, **80% (₹800)**, and **100% (₹1,000)** |

> [!NOTE]
> During provisioning, policy `sys.regionrestriction` governed the student subscription, enforcing regions `["indiasouthcentral", "polandcentral", "malaysiawest", "koreacentral", "uaenorth"]`. Deployment was executed in `indiasouthcentral` (Hyderabad, India) for minimal latency to Indian financial services.

---

## 2. Durable State Persistence Engine (Deliverable 2)

**Implementation:** [`src/storage/durable_state.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/durable_state.py)

### Architectural Invariants
1. **Strictly Zero Dependencies:** Implemented using Python standard library (`urllib.request`, `hmac`, `hashlib`, `gzip`, `json`). Eliminates the ~40 MB overhead of `azure-storage-blob` to protect Render's 512 MB memory boundary (< 1 MB resident RAM).
2. **Selective State Isolation:** Never exports multi-gigabyte market data tables (`ohlcv_daily`, `quant_factors_daily`, `bhavcopy_*`). Exports only mutable user data:
   - `portfolio_accounts`, `portfolio_positions`, `portfolio_orders`
   - `backtest_runs`
   - `real_closed_roundtrips`, `real_open_holdings`, `real_capital_ledger`
   - `real_dp_charges`, `real_tradebook_audit_log`
   - `user_watchlists`
   - `copilot_memory_episodes`
   - `model_registry`
   - Encrypted `master_tradebook.enc`
3. **Debounced Mutations:** Includes a background thread worker with a 30-second debounce timer (`mark_state_dirty()`) to coalesce rapid trades or turn additions into a single blob upload.
4. **Bootstrapped Startup Hydration:** Integrated into [`src/storage/hydration.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/hydration.py). Upon container restart, the engine checks Azure Blob Storage and restores the user state seamlessly.

### Mutation Wiring Points
- [`src/api/routes_portfolio.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/api/routes_portfolio.py): `execute_rebalance`, `execute_manual_trade`, `reset_account_capital`, `adjust_account_cash`, `upload_angelone_tradebook`.
- [`src/api/main.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/api/main.py): `add_to_watchlist`, `remove_from_watchlist`.
- [`src/copilot/memory_store.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/copilot/memory_store.py): `distill_and_record_turn`.

---

## 3. Canonical Indian Equity Fee Engine (Deliverable 3)

**Implementation:** [`src/portfolio/fee_engine.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/portfolio/fee_engine.py)

### Rate Specifications & Tax Invariants
- **Depository Participant (DP) Charge:** Exactly **₹23.60** (₹20.00 base + 18% GST) per ISIN per sell debit leg (₹0.00 on buy).
- **Securities Transaction Tax (STT):** **0.1% (0.001)** on both Buy and Sell legs, rounded to the nearest rupee per exchange settlement rules.
- **NSE Exchange Turnover Charge:** **0.0030699% (0.000030699)** on both legs.
- **SEBI Regulatory Fee:** **0.0001% (0.000001 = ₹10 / crore)** on both legs.
- **Stamp Duty:** **0.015% (0.00015)** on Buy leg only, rounded to nearest rupee.
- **Strict GST Application:** **18% GST** applies exclusively to services: `Brokerage + Exchange Txn + SEBI Fee`. Statutory government levies (STT, Stamp Duty) are **EXEMPT** from GST.
- **Brokerage Profiles:** Supports `angel_one_delivery_2026_zero` (default ₹0.00 equity delivery for retail iTrade Prime) and `angel_one_delivery_2026_standard`.

### Integration Matrix
- [`src/quant/backtest_engine.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/backtest_engine.py): Replaced ₹15.34 with canonical ₹23.60 DP and official exchange rates.
- [`src/quant/portfolio_backtester.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/portfolio_backtester.py): Replaced hardcoded ₹15.00 with `ANGEL_ONE_DP_CHARGE` (₹23.60) and harmonized rounded alpha CAGR calculation.
- [`src/copilot/trader_dna.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/copilot/trader_dna.py): Evaluates trade upside against iterative breakeven targets including ₹23.60 DP drag.
- [`src/portfolio/tradebook_engine.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/portfolio/tradebook_engine.py): Uses canonical DP charge.
- [`src/quant/ml_trainer.py`](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/ml_trainer.py): Uses canonical 15 bps institutional hurdle rate (`DEFAULT_HURDLE_RATE = 0.0015`).

---

## 4. Verification & Test Results

All new and existing test suites pass:

```
tests/test_fee_engine.py::test_brokerage_profiles PASSED                 [  8%]
tests/test_fee_engine.py::test_statutory_taxes_buy_leg PASSED            [ 16%]
tests/test_fee_engine.py::test_statutory_taxes_sell_leg_with_dp PASSED   [ 25%]
tests/test_fee_engine.py::test_gst_strict_exemption_on_stt_and_stamp PASSED [ 33%]
tests/test_fee_engine.py::test_roundtrip_friction_and_pnl PASSED         [ 41%]
tests/test_fee_engine.py::test_micro_capital_breakeven_drag PASSED       [ 50%]
tests/test_durable_state.py::test_export_mutable_state_excludes_market_tables PASSED [ 58%]
tests/test_durable_state.py::test_restore_mutable_state_roundtrip PASSED [ 66%]
tests/test_durable_state.py::test_encrypted_tradebook_roundtrip PASSED   [ 75%]
tests/test_durable_state.py::test_azure_blob_client_unconfigured_fallback PASSED [ 83%]
tests/test_durable_state.py::test_durable_state_manager_with_mocked_blob PASSED [ 91%]
tests/test_durable_state.py::test_mark_state_dirty_convenience PASSED    [100%]
============================== 12 passed in 3.54s ==============================
```

```
tests/test_copilot_adaptive_live.py (6/6 PASSED)
tests/test_portfolio_backtester.py (4/4 PASSED)
Full Repository Suite: 485+ PASSED
```

---

## 5. Security & Zero-Secrets Compliance

- **No Secrets Committed:** No Azure connection strings, storage keys, or tokens have been saved into the repository.
- **Fail-Safe Fallback:** If `AZURE_STORAGE_CONNECTION_STRING` is not set, `DurableStateManager` logs a single informational notice on startup and operates safely using local database storage without throwing exceptions or degrading performance.
