# Milestone B3.2: Corporate Actions & Disclosures Ingestion Architecture & Data Provenance

**Document Version:** 1.0.0  
**Milestone:** B3.2 (Corporate Actions & Official Board Disclosures)  
**System:** Market Intelligence Lab (Local-First Quantitative Equity Engine)  
**Author:** Quantitative Architecture & Ingestion Engineering  
**Scope:** Active 50-Stock Universe (`securities_master`) across the National Stock Exchange of India (NSE)

---

## 1. Executive Summary & Design Invariants

Milestone B3.2 delivers an automated, source-verified ingestion architecture for official corporate actions (cash dividends, bonus issues, stock splits, rights issues) and official board disclosures across the 50-stock active universe defined in `securities_master`.

### Architectural Invariants:
1. **Source Authenticity:** All corporate actions and disclosures are sourced directly from the official National Stock Exchange of India (NSE) structured API endpoints. Raw HTML scraping with BeautifulSoup and unverified third-party aggregators are strictly prohibited.
2. **Defensive API Session Management:** NSE's edge gateways (Akamai WAF/GHost) enforce cookie validation, browser header checks, and strict rate limits. All requests are managed through `src/client/corporate_client.py` using automated cookie initialization, standard browser headers, and exponential backoff with jitter on HTTP 403/429 responses.
3. **Idempotency & Re-entrancy:** Database persistence is guaranteed idempotent. All database writes utilize SQLite `INSERT ... ON CONFLICT(id) DO UPDATE` to ensure failure recovery and pipeline restarts without duplicating records.
4. **Data Layer Isolation & Zero Lookahead:** Corporate disclosures strictly default to `PENDING_VERIFICATION` status to prevent unverified material narratives from contaminating downstream quantitative models. Corporate actions store raw parameters (face value, ex-date, record date, purpose, adjustment ratio) without modifying historical price series in this milestone.
5. **Traceability & Audit Logging:** Every ingestion attempt (including stocks with zero events) generates an immutable entry in `ingestion_audit_log` with exact retrieved, accepted, and rejected counts, payload checksums, and execution status (`SUCCESS`, `NO_ACTIONS_FOUND`, `PARTIAL`, `FAILED`).

---

## 2. Source Identification & Endpoint Architecture

The ingestion pipeline communicates directly with the primary structured JSON endpoints exposed by the official NSE portal:

| Data Class | Official NSE Endpoint | Query Parameters | Format | Description |
| :--- | :--- | :--- | :--- | :--- |
| **Corporate Actions** | `https://www.nseindia.com/api/corporates-corporateActions` | `index=equities&symbol={symbol}` | JSON Array | Official declared cash dividends, stock splits, bonus share issues, and rights offerings. |
| **Corporate Disclosures** | `https://www.nseindia.com/api/corporate-announcements` | `index=equities&symbol={symbol}` | JSON Array | Official regulatory filings, board meeting outcomes, quarterly earnings, contract awards, and executive movements. |
| **Filing Attachments** | `https://nsearchives.nseindia.com/corporate/{filename}` | N/A | PDF / XBRL | Primary official regulatory PDF documents submitted to the exchange. |

### Rationale Against HTML Scraping & Aggregators:
- **No HTML Scraping:** Scraping public HTML pages via BeautifulSoup is fragile, vulnerable to CSS/DOM alterations, strips structured timestamps, and fails to capture exact exchange broadcast metadata.
- **No Unofficial Third Parties:** Third-party aggregators introduce data licensing risks, survivorship bias, undocumented corporate action adjustment logic, and timestamp rounding errors.

---

## 3. Session Management, Rate Limiting & Gateway Resilience

The edge architecture of NSE utilizes Akamai Enterprise Security and DDoS mitigation filters. Requests without valid session state or mimicking headless bots are blocked with HTTP 403 Forbidden or HTTP 429 Too Many Requests.

### Session Lifecycle in `src/client/corporate_client.py`:
1. **Cookie Warm-Up:** Prior to invoking API endpoints, the client executes an initial GET request to the NSE portal base URL (`https://www.nseindia.com`) using standard browser headers. This populates necessary session cookies (`AKA_A2`, `bm_sz`, `nsit`).
2. **Standard Browser Headers:**
   - `User-Agent`: Realistic modern desktop browser user-agent (`Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36`).
   - `Accept`: `application/json, text/plain, */*`.
   - `Accept-Language`: `en-US,en;q=0.9`.
   - `Accept-Encoding`: `gzip, deflate, br`.
   - `Referer`: `https://www.nseindia.com/companies-listing/corporate-filings-actions` (for actions) and `https://www.nseindia.com/companies-listing/corporate-filings-announcements` (for announcements).
3. **Pacing & Inter-Request Delay:** An intentional rate-limiting delay ($\Delta t \ge 0.5$ seconds) is enforced between consecutive symbol requests to remain within polite threshold limits.
4. **Exponential Backoff with Jitter:**
   When encountering HTTP 403, 429, or network connection timeouts, the client executes up to $N = 5$ exponential backoff retries:
   $$t_{\text{backoff}} = \text{base\_delay} \times 2^{\text{attempt}} + \text{uniform}(0, 0.5)$$
   If an HTTP 403 persists, the client invalidates the session cookies, re-executes the warm-up handshake, and resumes.

---

## 4. Corporate Actions Processing Pipeline (`src/quant/corporate_actions.py`)

### Schema Alignment:
The `corporate_actions` table maintains the following attributes:
- `id` (TEXT UNIQUE): Deterministic surrogate key: `{symbol}_{action_type}_{ex_date}_{hash(purpose)}`.
- `symbol` (TEXT NOT NULL): Equity ticker symbol (e.g. `INFY`, `RELIANCE`).
- `action_type` (TEXT NOT NULL): Standardized category (`DIVIDEND`, `SPLIT`, `BONUS`, `RIGHTS`, `OTHER`).
- `ex_date` (TEXT NOT NULL): First trading session without entitlement (`YYYY-MM-DD`).
- `record_date` (TEXT DEFAULT NULL): Company book closure record date (`YYYY-MM-DD`).
- `face_value` (REAL DEFAULT NULL): Pre-event or nominal share face value in INR.
- `adjustment_ratio` (REAL DEFAULT 1.0): Historical price scaling multiplier ($M_{\text{hist}} \le 1.0$).
- `adjustment_factor` (REAL DEFAULT 1.0): Synonymous multiplier preserved for legacy module compatibility.
- `purpose` (TEXT NOT NULL): Verbatim exchange declaration text.
- `source` (TEXT NOT NULL): `nse_corp_actions`.
- `retrieval_timestamp` (TEXT NOT NULL): ISO-8601 UTC retrieval timestamp.

### Action Classification & Adjustment Ratio Logic:
1. **Cash Dividends:** Classified when `purpose` contains `DIVIDEND`. In accordance with standard financial accounting, cash dividends do not mechanically compress raw historical share prices; `adjustment_ratio` is set to `1.0`.
2. **Bonus Issues:** Classified when `purpose` contains `BONUS`. Ratio parsed from purpose string (e.g. `Bonus 1:1` $\rightarrow 0.5$, `Bonus 1:2` $\rightarrow 0.6667$, `Bonus 2:1` $\rightarrow 0.3333$):
   $$M_{\text{hist}} = \frac{N_{\text{existing}}}{N_{\text{existing}} + N_{\text{bonus}}}$$
3. **Stock Splits:** Classified when `purpose` contains `SPLIT` or `SUB-DIVISION`. Ratio parsed from nominal face value compression (e.g. split from ₹10 to ₹2 $\rightarrow 0.2$):
   $$M_{\text{hist}} = \frac{\text{FaceValue}_{\text{post}}}{\text{FaceValue}_{\text{pre}}}$$
4. **Rights Issues:** Classified when `purpose` contains `RIGHTS`. Stored with raw terms.

### Missing Data vs. Ingestion Failure:
Certain mature or capital-conserving securities (e.g., newly listed or non-dividend paying firms like `ETERNAL` / `ZOMATO`) may genuinely have zero actions declared over the benchmark window.
- The pipeline explicitly tests `len(actions) == 0`.
- It records an entry in `ingestion_audit_log` with `status = 'NO_ACTIONS_FOUND'`, `records_retrieved = 0`, `records_accepted = 0`, and `records_rejected = 0`.
- The execution is marked successful; zero corporate actions is a valid financial state, not an infrastructure exception.

---

## 5. Corporate Disclosures Processing Pipeline (`src/quant/disclosures.py`)

### Schema Alignment:
The `corporate_disclosures` table maintains the following attributes:
- `id` (TEXT UNIQUE): Surrogate identifier: `DISC_{symbol}_{seq_id}`.
- `disclosure_id` (TEXT PRIMARY KEY): Equivalent exchange sequence identifier.
- `symbol` (TEXT NOT NULL): Equity ticker symbol.
- `broadcast_timestamp` (TEXT NOT NULL): Exact exchange broadcast timestamp (e.g. `2026-10-30T18:50:50+05:30`).
- `effective_session_date` (TEXT NOT NULL): Point-in-time aligned trading session ($t=0$).
- `category` (TEXT NOT NULL): Taxonomical metadata tag.
- `subject` (TEXT NOT NULL): High-level title/summary of disclosure.
- `details_summary` (TEXT): Full exchange notification text.
- `source_url` (TEXT): Direct URL to official PDF filing on `nsearchives.nseindia.com`.
- `retrieval_timestamp` (TEXT NOT NULL): ISO-8601 UTC timestamp.
- `verification_status` (TEXT NOT NULL DEFAULT 'PENDING_VERIFICATION'): Governance status.

### Metadata Categorization Taxonomy:
A deterministic regular expression and keyword classification engine maps unstructured notification texts into canonical disclosure categories:

| Category | Regex / Keyword Pattern |
| :--- | :--- |
| `EARNINGS` | `financial result|quarterly|un-audited|audited|financials|\bq[1-4]\b|balance sheet` |
| `BOARD_MEETING` | `board meeting|outcome of board` |
| `CONTRACT_AWARD` | `order|contract|award|agreement|deal|procurement|bagged|commercial agreement` |
| `RESIGNATION` | `resignation|cessation|relinquish` |
| `APPOINTMENT` | `appointment|re-appointment|designated` |
| `INVESTOR_PRESENTATION`| `investor presentation|analyst meet|conference call` |
| `DIVIDEND` | `dividend|record date for dividend` |
| `GENERAL_ANNOUNCEMENT` | Catch-all default for general regulatory compliance notices. |

### Exchange Broadcast Timestamp Accuracy:
- Ingestion extracts the exact timestamp logged by the NSE electronic filing platform (`an_dt`, `sort_date`, or `exchdisstime`).
- File creation timestamps (metadata inside the PDF) are strictly rejected because PDF compilation dates reflect internal corporate authoring rather than public market dissemination.
- **Effective Session Date ($t=0$):**
  If `broadcast_timestamp` is disseminated after market close (15:30:00 IST) or on a non-trading weekend/holiday, the effective session date is deterministically advanced to the next official NSE trading day. Disseminations during active market hours (09:15 to 15:30 IST) map to the current session.

---

## 6. Database Idempotency & Upsert Specification

To ensure failure resilience, re-running the ingestion pipeline must never cause primary key collisions or duplicate rows:

### Corporate Actions Upsert Query:
```sql
INSERT INTO corporate_actions (
    id, symbol, action_type, ex_date, record_date, face_value,
    adjustment_ratio, adjustment_factor, purpose, source,
    retrieval_timestamp, announcement_date, effective_date
) VALUES (
    :id, :symbol, :action_type, :ex_date, :record_date, :face_value,
    :adjustment_ratio, :adjustment_factor, :purpose, :source,
    :retrieval_timestamp, :announcement_date, :effective_date
)
ON CONFLICT(id) DO UPDATE SET
    record_date = excluded.record_date,
    face_value = excluded.face_value,
    adjustment_ratio = excluded.adjustment_ratio,
    adjustment_factor = excluded.adjustment_factor,
    purpose = excluded.purpose,
    source = excluded.source,
    retrieval_timestamp = excluded.retrieval_timestamp,
    announcement_date = excluded.announcement_date,
    effective_date = excluded.effective_date;
```

### Corporate Disclosures Upsert Query:
```sql
INSERT INTO corporate_disclosures (
    id, disclosure_id, symbol, broadcast_timestamp, effective_session_date,
    category, subject, details_summary, source_url, retrieval_timestamp,
    verification_status
) VALUES (
    :id, :disclosure_id, :symbol, :broadcast_timestamp, :effective_session_date,
    :category, :subject, :details_summary, :source_url, :retrieval_timestamp,
    :verification_status
)
ON CONFLICT(id) DO UPDATE SET
    broadcast_timestamp = excluded.broadcast_timestamp,
    effective_session_date = excluded.effective_session_date,
    category = excluded.category,
    subject = excluded.subject,
    details_summary = excluded.details_summary,
    source_url = excluded.source_url,
    retrieval_timestamp = excluded.retrieval_timestamp;
```

---

## 7. Execution Runner & Verification Plan

1. **Client Implementation (`src/client/corporate_client.py`):**
   Robust session management, cookie acquisition, header rotation, and exponential backoff.
2. **Quant Processing Modules:**
   - `src/quant/corporate_actions.py`: Parsing, classification, ratio calculation, and database persistence.
   - `src/quant/disclosures.py`: Metadata tagging, PDF URL extraction, broadcast time alignment, and pending status enforcement.
3. **Offline Unit Tests (`tests/test_milestone_b3_2.py`):**
   - Mocked HTTP responses proving duplicate IDs trigger non-destructive UPSERTs.
   - Proof that newly inserted disclosures strictly receive `'PENDING_VERIFICATION'`.
   - Proof that stocks with zero actions log `'NO_ACTIONS_FOUND'` without errors.
   - Validation of PDF URL extraction, categorization regex, and timestamp parsing.
4. **Live Execution Runner (`scripts/ingest_b3_2_corporate_data.py`):**
   - Runs against live NSE endpoints across all 50 active constituents in `securities_master`.
   - Records raw payloads under `data/raw/corporate_actions/` and `data/raw/corporate_disclosures/`.
   - Outputs comprehensive execution summary markdown report: `reports/milestone_b3_2_live_ingestion_report.md`.
