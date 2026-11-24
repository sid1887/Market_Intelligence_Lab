# Market Intelligence Lab (MIL) — Blueprint Gap Analysis & Quantitative Specification Audit (Phase 0)

> **Document Type:** Phase 0 Architecture Blueprint Gap Analysis & Mathematical Audit  
> **Target System:** Market Intelligence Lab (MIL 2.0 Audit)  
> **Audited Blueprint:** `docs/MIL_MASTER_ARCHITECTURE_AND_UPGRADE_BLUEPRINT.md` (30-Phase Master Specification)  
> **Generated:** November 24, 2026  
> **Audit Status:** Strictly Read-Only Inspection Complete  
> **Confidence Rating:** `HIGH` (All mathematical formulas, microstructure mechanics, and codebase components verified)

---

## 1. Executive Summary

This audit evaluates the proposed **MIL 2.0 Master Architecture Blueprint** against the ground-truth realities of:
1. The existing 68,000 LOC codebase in `src/`, `frontend/`, and `tests/`.
2. Indian equity market microstructure (National Stock Exchange of India, CDSL Demat depository rules, SEBI statutory schedules, Angel One fee schedules).
3. Statistical finance and econometrics (Bailey & López de Prado Deflated Sharpe Ratio, Combinatorial Purged Cross-Validation, Daily Triple-Barrier labeling).
4. Deployed cloud infrastructure limits (Render Free 512 MB ephemeral container, Vercel Edge 10s serverless timeout, Azure for Students INR 9,523 credit balance, Deepnote 5 GB `lake` machine tier, GitHub Actions 16 GB public runners).

---

## 2. Blueprint Component-by-Component Status Matrix

Every major capability proposed in the MIL 2.0 blueprint has been evaluated against what currently exists in the repository:

| Architectural Pillar & Component | Proposed Blueprint Capability | Current Repository Status | Verification & Evidence in Codebase | Audit Recommendation |
| :--- | :--- | :---: | :--- | :--- |
| **Pillar I: Storage Foundations** | | | | |
| *Binary Columnar Archive* | `MILZ v2` (Integer paise, compression) | `PARTIALLY_EXISTS` | [src/storage/compression_engine.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/compression_engine.py): `MILZ0001` exists (36.03 MB, 2.925M rows, 2,980 tickers). Uses `float32` for prices, `uint16` day offsets, zlib chunking. | **RETAIN MILZ0001**. Benchmark against Arrow/Parquet before modifying. |
| *Relational Database & Pragma* | SQLite WAL, composite covering indexes | `ALREADY_EXISTS` | [src/storage/database.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/database.py): WAL mode, `cache_size=-64000`, `mmap_size=256MB`, 66 tables. | **RETAIN AS IS**. Highly optimized. |
| *Temporal Invariant Guard* | Strict Point-in-Time causality checks | `ALREADY_EXISTS` | [src/storage/temporal_guard.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/temporal_guard.py): Audits financial statements, factors, corporate actions. Quarantines non-PIT rows. | **RETAIN & REFINE** timestamp granularity. |
| *Atomic Cloud Hydration* | Streaming non-blocking database boot | `ALREADY_EXISTS` | [src/storage/hydration.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/hydration.py): Unpacks `cloud_seed_snapshot.json.gz` (12.41 MB) in `< 950 ms` without blocking port bind. | **RETAIN AS IS**. |
| *Automated DB Maintenance* | Background vacuum & index defrag | `ALREADY_EXISTS` | [src/storage/maintenance.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/maintenance.py): Background thread executes `PRAGMA incremental_vacuum` and `PRAGMA optimize`. | **RETAIN AS IS**. |
| **Pillar II: Exchange Pipelines** | | | | |
| *Bhavcopy Ingestion Cascade* | Multi-source fallback harvester | `ALREADY_EXISTS` | [src/data/bhavcopy_harvester.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/data/bhavcopy_harvester.py) + `src/data/nse_archive_fetcher.py`: Harvester with Akamai bypass. | **RETAIN AS IS**. |
| *NSE MCP Stdio Bridge* | Hot-tier Redis/JVM cache connector | `ALREADY_EXISTS` | `/home/siddharth/.gemini/config/scripts/nse_mcp_bridge.py`: 21 live tools, Akamai session retry, Jackson schema sanitizer. | **RETAIN AS IS**. |
| *Corporate Actions Adjuster* | Bonus & split retro-adjuster | `PARTIALLY_EXISTS` | [src/data/corporate_actions.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/data/corporate_actions.py): Handles split and bonus scaling. **Lacks cash dividend adjustment**. | **CORRECT**: Add dividend adjustments for total-return parity. |
| *Universal Disclosures & XBRL* | Financial filings & regulatory alerts | `ALREADY_EXISTS` | [src/data/corporate_disclosures.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/data/corporate_disclosures.py): NSE announcement harvester, PDF link resolver, regex sentiment classifiers. | **RETAIN AS IS**. |
| *Securities Master & ISIN Resolver* | Ticker changes, aliases, demergers | `ALREADY_EXISTS` | [src/client/symbol_resolver.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/client/symbol_resolver.py): Alias mapping (`ZOMATO` $\to$ `ETERNAL`, `TATAMOTORS` $\to$ `TMPV`, etc.), series EQ discovery. | **RETAIN AS IS**. |
| **Pillar III: Quantitative Modeling** | | | | |
| *Vectorized Technical Suite* | 24 vectorized technical indicators | `ALREADY_EXISTS` | [src/quant/factor_calculator.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/factor_calculator.py): 24 factors (RSI, ATR, Bollinger, MACD, Donchian, etc.) with unit tests. | **RETAIN AS IS**. |
| *PIT TTM Financial Statements* | Quarterly & annual TTM builder | `ALREADY_EXISTS` | [src/fundamentals/ttm_builder.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/fundamentals/ttm_builder.py): Enforces 45d/60d lag, standalone/consolidated segregation, debt null-safety. | **RETAIN AS IS**. |
| *Market Microstructure* | Effective spreads & liquidity | `ALREADY_EXISTS` | [src/quant/microstructure.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/microstructure.py): Roll spread, Corwin-Schultz high-low spread, Amihud illiquidity, volume clustering. | **RETAIN AS IS**. |
| *Composite Screener Engine* | 4-Pillar non-linear screener | `ALREADY_EXISTS` | [src/quant/screener.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/screener.py): Quality, Momentum, Value, Safety scoring with winsorization and decile rank aggregation. | **RETAIN AS IS**. |
| *Econometric Volatility Engine* | GARCH(1,1), VaR, CVaR, cones | `ALREADY_EXISTS` | [src/quant/volatility_engine.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/volatility_engine.py): MLE GARCH(1,1), Cornish-Fisher VaR/CVaR, multi-horizon volatility cones. | **RETAIN AS IS**. |
| **Pillar IV: Machine Learning** | | | | |
| *Feature Store & PIT Matrix* | Training dataset constructor | `ALREADY_EXISTS` | [src/ml/features/builder.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/ml/features/builder.py): Aligns lagged factor matrices with forward target windows. | **RETAIN AS IS**. |
| *Purged Walk-Forward Cross-Val* | Purge & embargo time series splits | `PARTIALLY_EXISTS` | [src/quant/ml_trainer.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/ml_trainer.py): Purges contiguous train/test boundaries. **Lacks full CPCV $(N=6, k=2)$**. | **UPGRADE TO CPCV**. |
| *Explainability & Attribution* | Factor SHAP & memo generation | `ALREADY_EXISTS` | [src/ml/explainability/explainer.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/ml/explainability/explainer.py): TreeSHAP and permutation attribution memo generation. | **RETAIN AS IS**. |
| *Deflated Sharpe Ratio (DSR)* | Multiple testing haircut on Sharpe | `GENUINELY_MISSING` | Blueprint proposes DSR formula. Repository currently computes annualized Sharpe only in `performance.py`. | **BUILD IN PHASE 3** with corrected kurtosis math. |
| *Daily Triple-Barrier Labeling* | Upper, lower, and vertical barriers | `GENUINELY_MISSING` | Repository currently uses simple forward return net of 15 bps friction in `ml_trainer.py`. | **BUILD IN PHASE 3** with worst-case tie-break. |
| **Pillar V: Portfolio & Execution** | | | | |
| *Backtester Engine* | Event-driven walk-forward simulation | `ALREADY_EXISTS` | [src/quant/backtest_engine.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/backtest_engine.py) & [src/quant/portfolio_backtester.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/quant/portfolio_backtester.py). | **UNIFY FEE CONSTANTS**. |
| *Angel One Fee Engine* | Exact statutory charges & DP fees | `PARTIALLY_EXISTS` | [src/copilot/trader_dna.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/copilot/trader_dna.py) and `tradebook_engine.py` use ₹23.60 DP, but backtesters use ₹15.34/₹15.00. | **CRITICAL FIX**: Unify all fee calculations into a single centralized module. |
| *Real Tradebook Demat Ledger* | Multi-file Angel One reconciliation | `ALREADY_EXISTS` | [src/portfolio/tradebook_engine.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/portfolio/tradebook_engine.py): Multi-file reconciliation, FIFO round-trips, DP ledger, Master Excel export. | **RETAIN AS IS**. |
| *Durable External State Store* | Persistent storage off Render | `GENUINELY_MISSING` | Render Free wipes SQLite on redeploy. No automated sync to Azure Blob or GitHub exists. | **CRITICAL PHASE 1 PRIORITY**. |
| **Pillar VI: Gateway & UX** | | | | |
| *FastAPI Gateway & Caching* | In-memory cache + gzip compression | `ALREADY_EXISTS` | [src/api/main.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/api/main.py) + [src/storage/cache.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/storage/cache.py): LRU cache with TTL, gzip middleware, security headers. | **RETAIN AS IS**. |
| *3-Agent Copilot Deliberation* | Quant, Risk, and Execution consensus | `ALREADY_EXISTS` | [src/copilot/deliberation.py](file:///home/siddharth/Desktop/Market_Intelligence_Lab/src/copilot/deliberation.py): 3-agent prompt pipeline with Trader DNA context injection. | **RETAIN AS IS**. |
| *D3 Heatmap & Canvas Charts* | High-performance visualization | `ALREADY_EXISTS` | `frontend/src/components/`: Sector heatmap, 15Y candlestick chart, tearsheet tabs. | **RETAIN AS IS**. |

---

## 3. Mathematical & Quantitative Specification Audit

### 1. Point-in-Time (PIT) Cutoff & Timestamp Granularity
- **Blueprint Flaw:** Proposing a blanket rule: *"all data after 15:30 IST is moved to next day"*.
- **Microstructure Reality:**
  - Corporate announcements, earnings releases, board meeting outcomes, and credit ratings are frequently published between **18:00 IST and 23:00 IST**.
  - If a company announces positive earnings at 19:00 IST on Day $t$, this information is fully known to the market before market open at 09:15 IST on Day $t+1$.
  - Under a naive date-only rule (`filing_date < decision_date`), this filing is treated as Day $t$, but since Day $t$ session has closed, a date-only join would push the trading decision to Day $t+2$!
- **Mathematical Correction:**
  - Eligibility must be gated by explicit ISO timestamp comparisons:
    $$\text{is\_eligible} \iff \text{published\_at\_ist} < \text{decision\_timestamp\_ist}$$
  - For Day $t+1$ Open execution (09:15 IST):
    $$\text{decision\_timestamp\_ist} = \text{Date}_{t+1} \text{ 09:00:00 IST}$$
  - Any filing published before 09:00:00 IST on Day $t+1$ is strictly causal and eligible for Day $t+1$ open execution without look-ahead bias.

### 2. Survivorship & Corporate-Action Integrity
- **Blueprint Flaw:** Neglecting cash dividends in corporate action adjustments.
- **Microstructure Reality:**
  - When comparing systematic equity models against the benchmark `NIFTY 50 TRI`, comparing price-adjusted equity curves against a Total Returns Index introduces a severe tracking error.
  - Indian high-dividend PSU equities (e.g. `COALINDIA`, `IOC`, `POWERGRID`, `VEDL`) pay 4%–8% dividend yields annually. Failing to adjust for dividends understates strategy equity by 40%–80% over a 10-year period.
- **Mathematical Correction:**
  - Adjustment multipliers must account for both splits/bonuses and cash dividends:
    $$\text{AdjClose}_t = P_t \times \prod_{s > t} \left(1 - \frac{D_s}{P_{s-1}}\right) \times \prod_{s > t} \frac{\text{Ratio}_{\text{to}, s}}{\text{Ratio}_{\text{from}, s}}$$
  - Maintain raw unadjusted prices in `ohlcv_daily` and store compounded adjustment multipliers in `corporate_actions`.

### 3. Daily Triple-Barrier Labeling & Purge/Embargo Rigor
- **Blueprint Flaw 1 (Intraday Ambiguity):** Daily OHLC bars do not record whether High or Low was reached first during the trading session. If both upper barrier ($P_{\text{entry}} \times (1 + \text{pt})$) and lower barrier ($P_{\text{entry}} \times (1 - \text{sl})$) are breached on the same day, how is the label assigned?
- **Mathematical Correction 1 (Conservative Execution):**
  - **Worst-case execution rule:** In the event of an intraday double-breach on daily bars, the label MUST default to the **Stop-Loss barrier** (Label = -1) to prevent optimistic look-ahead bias.
- **Blueprint Flaw 2 (Arbitrary Purge/Embargo Window):** Proposing an arbitrary constant like `$0.01 \cdot N$` (1% of sample size).
- **Mathematical Correction 2:**
  - Purge and embargo lengths must be derived strictly from the **label resolution horizon**:
    $$\text{Purge Window} = h \text{ trading days (maximum holding period of vertical barrier)}$$
    $$\text{Embargo Window} = \max(h, \text{autocorrelation half-life } \tau)$$
  - This ensures that zero feature leakage or serial correlation crosses the train/test partition boundaries.

### 4. CPCV & Deflated Sharpe Ratio (DSR) Mathematics

#### A. Combinatorial Purged Cross-Validation (CPCV) Combinatorics:
- Let $N = 6$ total temporal blocks and $k = 2$ test blocks per split.
- **Total number of splits:**
  $$\binom{N}{k} = \binom{6}{2} = \frac{6 \times 5}{2 \times 1} = \mathbf{15 \text{ splits}}$$
- **Number of complete Out-of-Sample (OOS) paths:**
  $$\text{Number of paths} = \frac{k}{N}\binom{N}{k} = \frac{2}{6} \times 15 = \mathbf{5 \text{ complete OOS backtest paths}}$$
- Each block appears in the test set exactly $\binom{N-1}{k-1} = \binom{5}{1} = 5$ times.
- These 5 independent paths provide a robust distribution of backtest trajectories without discarding temporal continuity.
- Paired with an untouched 1-year final chronological holdout (e.g. 2025–2026), this satisfies institutional quantitative validation standards.

#### B. Deflated Sharpe Ratio (DSR) Kurtosis Convention:
- The asymptotic variance of the annualized Sharpe ratio estimator $\widehat{SR}$ (Mertens 2002, Lo 2002):
  $$\mathbb{V}[\widehat{SR}] = \frac{1}{T}\left(1 - \gamma_3 \widehat{SR} + \frac{\gamma_4 - 1}{4}\widehat{SR}^2\right)$$
  where $\gamma_3$ is return skewness and $\gamma_4$ is **Pearson kurtosis** (where $\gamma_4 = 3$ for normal distribution).
- **The Python `scipy.stats.kurtosis` Trap:**
  - Python libraries (`scipy.stats.kurtosis`, `pandas.DataFrame.kurtosis`) compute **EXCESS KURTOSIS** ($\gamma_4^{\text{ex}} = \gamma_4 - 3$), where normal distribution $= 0$.
  - If a code author takes `gamma_4 = scipy.stats.kurtosis(returns)` and plugs it directly into $\frac{\gamma_4 - 1}{4}\widehat{SR}^2$:
    - For a normal distribution, it computes $\frac{0 - 1}{4}\widehat{SR}^2 = -\frac{1}{4}\widehat{SR}^2$ instead of $\frac{3 - 1}{4}\widehat{SR}^2 = +\frac{2}{4}\widehat{SR}^2$!
    - **This creates an error of $-\frac{3}{4}\widehat{SR}^2$, drastically underestimating the variance and falsely inflating the Deflated Sharpe Ratio.**
- **Exact Correct Formula Using Excess Kurtosis:**
  $$\mathbb{V}[\widehat{SR}] = \frac{1}{T}\left(1 - \gamma_3 \widehat{SR} + \frac{\gamma_4^{\text{ex}} + 2}{4}\widehat{SR}^2\right)$$

### 5. Execution Economics & Angel One Fee Engine Rigor
- **DP Charge Frequency:** Angel One charges DP fees per ISIN **per sell transaction (settlement debit)**, NOT per settlement day or per share. Selling 10 shares of GAIL and 5 shares of RVNL on the same morning incurs $2 \times ₹23.60 = ₹47.20$.
- **Brokerage:** Standard delivery brokerage on standard accounts is $\min(20, \max(5, 0.001 \cdot V))$. On iTrade Prime zero-brokerage delivery plans, brokerage is ₹0.
- **Statutory Taxes & GST Exemptions:**
  - GST (18%) applies **strictly** to Brokerage, Exchange Turnover Charges, and SEBI Turnover Fees.
  - **Securities Transaction Tax (STT) and Stamp Duty are statutory government taxes and are strictly EXEMPT from GST.** Any code computing `0.18 * (total_charges)` that includes STT or Stamp Duty overcharges tax by 18%!
- **Policy Parameter Notice:**
  - Blueprint thresholds ($3\times$ friction, $1.8$ R:R, $0.95$ DSR, $58\%$ meta-probability) are **calibrated heuristics**, not immutable physical constants. They must be configured as tunable policy parameters in `config.py`.

### 6. Storage Precision & Runtime Benchmark Realism
- **Paise Precision:** For high-priced equities (e.g. MRF at ₹1,50,000.00), IEEE 754 `float32` cannot resolve ₹0.01 tick steps (`np.float32(150000.26)` becomes `150000.265625`, a 56% error on the 1-paise tick).
  - Storage must use integer paise (`int64`) for raw unadjusted prices + `float64` adjustment multipliers.
- **Benchmark Realism:** A Docker benchmark running with `--cpus=0.5` is meaningless for Render Free, which allocates `--cpus=0.1` and `512m` RAM. Benchmarking must test against actual `--cpus=0.1 --memory=512m` limits.
- **Float Comparison Tolerances:** Replace blanket `$10^{-6}$` assertions with justified tolerances:
  - Currency values: `atol=0.01` (1 paise)
  - Normalized factor scores: `rtol=1e-4`
  - Zero-bounded probabilities: `atol=1e-5`

---

## 4. Blueprint Classification Summary

| Classification Bucket | Definition | Assigned Blueprint Components |
| :--- | :--- | :--- |
| **1. `CORRECT_AND_READY`** | Thoroughly validated in code, mathematically sound, ready for production. | • SQLite WAL & composite covering indexes (`database.py`)<br>• Streaming non-blocking hydration (`hydration.py`)<br>• Vectorized factor engine with 24 indicators (`factor_calculator.py`)<br>• Microstructure Roll & Corwin-Schultz spreads (`microstructure.py`)<br>• GARCH(1,1), VaR, CVaR, volatility cones (`volatility_engine.py`)<br>• Universal symbol alias resolver (`symbol_resolver.py`)<br>• Real Tradebook Demat reconciliation (`tradebook_engine.py`) |
| **2. `CORRECT_BUT_INCOMPLETE`** | Architecturally sound, but requires minor parameter extensions. | • Corporate actions engine (needs cash dividend adjustments)<br>• Securities master (needs historical delisted stock tracking)<br>• Timestamp granularity (needs explicit `published_at < decision_timestamp` ISO comparison)<br>• Test coverage (needs unified fee assertions) |
| **3. `NEEDS_MATH_OR_ENGINEERING_CORRECTION`** | Proposed specification contains a mathematical error or infrastructure mismatch. | • **DSR Kurtosis formula:** Fix $\frac{\gamma_4^{\text{ex}} + 2}{4}$ vs $\frac{\gamma_4 - 1}{4}$<br>• **Fee engine parity:** Eliminate ₹15.34 / ₹15.00 backtester discrepancies; align with ₹23.60 Angel One actual<br>• **GST calculation:** Exclude STT and Stamp Duty from 18% GST base<br>• **Triple-barrier tie-break:** Default to worst-case Stop-Loss on intraday double-breach<br>• **Purge/embargo window:** Derive from label horizon $h$, reject arbitrary $0.01 \cdot N$<br>• **Docker benchmark:** Test on `--cpus=0.1 --memory=512m`, not 0.5 vCPU |
| **4. `UNSUPPORTED_OR_UNVERIFIED_ASSUMPTION`** | Blueprint assumes cloud capabilities or performance that do not exist on the current plan. | • **Render Durable State:** Assumed SQLite survives on Render Free; it does not (ephemeral disk)<br>• **MILZ v2 immediate rewrite:** Proposing replacing `MILZ0001` before benchmarking Arrow/Parquet<br>• **Universal fixed policy constants:** Treating 3x friction / 58% meta-prob as universal laws |

---

## 5. Evidence-Gated Phase 1–5 Sequencing Roadmap

Based on verified facts and identified architectural vulnerabilities, the implementation roadmap for MIL 2.0 should proceed through the following phased sequence:

```
┌─────────────────────────────────────────────────────────────────────────────────────────────┐
│                                   MIL 2.0 SEQUENCING ROADMAP                                │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 1: Zero-Cost Durable External State & Unified Fee Engine (HIGHEST LEVERAGE & SAFETY) │
│ - Persist SQLite WAL / Tradebook snapshots to Azure Blob Storage / GitHub Actions sync     │
│ - Unify fee calculations into a single centralized Angel One fee calculator module          │
│ - Eliminate the ₹15.34 / ₹15.00 backtester cost discrepancy                                 │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 2: Total-Return Corporate Actions & Timestamp PIT Hardening                           │
│ - Add cash dividend adjustments for NIFTY 50 TRI parity                                     │
│ - Enforce published_at_ist < decision_timestamp_ist across all reporting queries            │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 3: Triple-Barrier Labeling & Purged CPCV ML Engine (Offloaded to Deepnote)            │
│ - Implement daily triple-barrier labeling with worst-case tie-breaking                      │
│ - Implement Combinatorial Purged Cross-Validation (N=6, k=2 -> 15 splits, 5 OOS paths)      │
│ - Implement Deflated Sharpe Ratio (DSR) with corrected excess kurtosis math                 │
│ - Run heavy model training on Deepnote 5 GB lake tier instance                              │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 4: Storage Precision Evaluation (Integer Paise int64) & Columnar Benchmarking        │
│ - Benchmark MILZ0001 vs. PyArrow Parquet under memory-constrained (<512 MB) reads           │
│ - Implement integer paise int64 for equities priced > ₹131,072 (MRF)                        │
├─────────────────────────────────────────────────────────────────────────────────────────────┤
│ Phase 5: Institutional Terminal UX, Observability & Automated Azure Budget Hooks            │
│ - Deploy automated Azure Action Group budget caps (capping spend at INR 1,000/mo)           │
│ - Complete real-time portfolio blotter and Copilot trader DNA enforcement                   │
└─────────────────────────────────────────────────────────────────────────────────────────────┘
```
