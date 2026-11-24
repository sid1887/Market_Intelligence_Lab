# Market Intelligence Lab (MIL) — Infrastructure & MCP Capability Map (Phase 0 Audit)

> **Document Type:** Phase 0 Architecture, Infrastructure & Permission Inventory  
> **Target System:** Market Intelligence Lab (MIL 2.0 Audit)  
> **Generated:** November 24, 2026  
> **Audit Status:** Strictly Read-Only Inspection Complete  
> **Security Audit:** Zero raw secrets committed. Verified 100% token isolation in `~/.gemini/config/mcp_config.json`.

---

## 1. Executive Summary & Multi-Cloud Topology

Market Intelligence Lab (MIL) operates across a heterogeneous multi-cloud topology designed to combine zero-cost public cloud compute tiers with local workstation resources. 

The Antigravity development environment maintains 13 connected Model Context Protocol (MCP) servers, granting unified tool-level access across compute, hosting, databases, source control, and market data.

```
                              ┌──────────────────────────────────────────────┐
                              │            Vercel Edge Frontend              │
                              │        Next.js 14 App Router / CDN           │
                              │         MCP: mil-vercel (282 tools)          │
                              └──────────────────────┬───────────────────────┘
                                                     │ HTTPS / REST API
                                                     ▼
                              ┌──────────────────────────────────────────────┐
                              │             Render Free Backend              │
                              │      FastAPI + SQLite WAL (Ephemeral Disk)   │
                              │          Plan: Free (0.1 vCPU, 512 MB RAM)   │
                              │          MCP: mil-render (50 tools)          │
                              └───────┬──────────────────────────────┬───────┘
                                      │                              │
                   ┌──────────────────┴───────────────┐              │
                   ▼                                  ▼              ▼
    ┌──────────────────────────────┐    ┌──────────────────────────────┐    ┌──────────────────────────────┐
    │       Deepnote Compute       │    │     Azure for Students       │    │    GitHub Actions (Public)   │
    │  Lake Tier (2 vCPU, 5 GB RAM)│    │   INR 9,523 Active Balance   │    │  Ubuntu: 4 vCPU, 16 GB RAM   │
    │ Heavy ML / Backtest Engine   │    │   Storage & Fallback Compute │    │ EOD Sync & Scheduled ML      │
    │ MCP: mil-deepnote (48 tools) │    │  MCP: mil-azure (177 tools)  │    │   MCP: github (26 tools)     │
    └──────────────────────────────┘    └──────────────────────────────┘    └──────────────────────────────┘
                   │                                  │                              │
                   └──────────────────────────────────┼──────────────────────────────┘
                                                      │
                                                      ▼
                              ┌──────────────────────────────────────────────┐
                              │           Local Workstation (Mint)           │
                              │     Node v22.14 LTS, Python 3.13 venv        │
                              │  36 MB MILZ0001 Archive, 3.18 GB SQLite DB   │
                              │ MCP: filesystem, postgres, playwright, etc.  │
                              └──────────────────────────────────────────────┘
```

---

## 2. 13-MCP Capability & Permission Inventory

A rigorous tool-level audit of all 13 registered MCP servers in `/home/siddharth/.gemini/antigravity/mcp/` yielded a total of **664 exposed tools**. Every server has been verified and classified by safety profile and access scope.

### Summary Inventory Table

| MCP Server Identifier | Verified Connection Status | Transport / Command | Total Tools | Safety Profile (`R` / `W` / `D` / `X`) | Verified Scope / Environment |
| :--- | :--- | :--- | :---: | :--- | :--- |
| **`mil-azure`** | Connected | Local stdio (`@azure/mcp@latest`) | **177** | `75 R` / `77 W` / `11 D` / `14 X` | Sub: `Azure for Students` (`ee12014b-...`), 0 active resources |
| **`mil-deepnote`** | Connected | Streamable HTTP (`/mcp`) | **48** | `22 R` / `16 W` / `4 D` / `6 X` | Workspace: `ML-Book` (`0305b43e-...`), User: `Siddharth` (admin) |
| **`mil-render`** | Connected | Streamable HTTP (`/mcp`) | **50** | `32 R` / `1 R` / `2 D` / `15 X` | Workspace: `tea-dbq8tf8m7kps738oi350`, Service: `mil-quant-backend` |
| **`mil-vercel`** | Connected | Streamable HTTP (`/mcp`) | **282** | `168 R` / `81 W` / `5 D` / `28 X` | User: `yelugamsiddharth18-1415`, Team: `team_VuzcFRLUmFIAKddZCreNylwk` |
| **`nse-bhavcopy`** | Connected | Python Stdio Bridge (`nse_mcp_bridge.py`) | **21** | `20 R` / `0 W` / `0 D` / `1 X` | Live NSE Bhavcopy Redis/JVM Hot Tier (`mcp.nseindia.in`) |
| **`alphavantage`** | Connected | `uvx marketdata-mcp` | **3** | `3 R` / `0 W` / `0 D` / `0 X` | Global US/FX/Crypto market data API |
| **`postgres`** | Service Stopped | `npx @modelcontextprotocol/server-postgres` | **1** | `1 R` / `0 W` / `0 D` / `0 X` | Local URI: `postgresql://localhost/market_intel_db` (Port 5432 refused) |
| **`github`** | Connected | `npx @modelcontextprotocol/server-github` | **26** | `14 R` / `12 W` / `0 D` / `0 X` | Public Repo: `sid1887/Market_Intelligence_Lab` (PAT authenticated) |
| **`filesystem`** | Connected | `npx @modelcontextprotocol/server-filesystem` | **14** | `9 R` / `5 W` / `0 D` / `0 X` | Workspace Root: `/home/siddharth/Desktop/Market_Intelligence_Lab` |
| **`playwright`** | Connected | `npx @playwright/mcp` | **25** | `5 R` / `18 W` / `1 D` / `1 X` | Headless Chromium automation instance |
| **`designrevision`** | Connected | Remote HTTP (`mcp.designrevision.com`) | **14** | `13 R` / `1 W` / `0 D` / `0 X` | Design Revision UI block component registry |
| **`context7`** | Connected | `npx @upstash/context7-mcp` | **2** | `2 R` / `0 W` / `0 D` / `0 X` | Upstash documentation and library indexing |
| **`sequential-thinking`** | Connected | `npx @modelcontextprotocol/server-sequential-thinking` | **1** | `0 R` / `1 W` / `0 D` / `0 X` | Step-by-step cognitive reasoning engine |

*(Legend: `R` = Read-Only, `W` = Write/Create, `D` = Destructive/Delete, `X` = Execution/Deploy/Action)*

---

### Detailed Server Profiles

#### 1. `mil-azure` (177 tools)
- **Verified Status:** Active local stdio process running via Node v22.14.0 LTS.
- **Authentication:** Local Azure CLI (`az login`), User: `yelugamsiddharth18@gmail.com`.
- **Subscription:** `Azure for Students` (`ee12014b-365b-405d-94c9-e484cee5a08c`), State: `Enabled`.
- **Tool Capabilities:** Complete management of Azure Compute (VMs, VMSS, Disks), Storage (Blob, NetApp, Files), Databases (SQL, Cosmos, Redis, Kusto), Monitoring, and Advisor.
- **Safety Gating:** 
  - **DESTRUCTIVE Tools (11):** `delete_azure_managed_disk`, `delete_compute_vm_and_vmss`, `delete_azure_storage_sync_services`, `delete_azure_database_admin_configurations`, etc.
  - **EXECUTION Tools (14):** `create_azure_compute_vm_and_vmss`, `deploy_azure_resources_and_applications`, `start_azure_resilience_recoveryplan_failover`, etc.
- **Production Gate Rule:** All `delete_*` and `create_*_vm_*` tools must remain gated. Any provisioning must be restricted strictly to a dedicated, budget-capped Resource Group (`rg-mil-research`).

#### 2. `mil-deepnote` (48 tools)
- **Verified Status:** Active HTTP endpoint via `https://deepnote.com/mcp`.
- **Authentication:** Bearer API Token (`dn_...`), User: `Siddharth`, Role: `admin`.
- **Workspace:** `ML-Book` (`0305b43e-4bfe-47fa-bfd4-3a2393863761`, slug: `ml-book-74b8`).
- **Hardware Tier:** `lake` tier instance (2 vCPUs, 5 GiB RAM) verified available on plan.
- **Tool Capabilities:** Read/write project files, create/run notebooks, restart machines, create Streamlit apps.
- **Safety Gating:**
  - **DESTRUCTIVE Tools (4):** `delete_project`, `delete_notebook`, `delete_block`, `delete_file`.
  - **EXECUTION Tools (6):** `create_run`, `start_machine`, `stop_machine`, `restart_machine`.
- **Production Gate Rule:** Admin API token has project deletion capabilities. Must remain strictly read/execute for isolated analysis notebooks; `delete_project` must be forbidden.

#### 3. `mil-render` (50 tools)
- **Verified Status:** Active HTTP endpoint via `https://mcp.render.com/mcp`.
- **Authentication:** Read-Only Bearer API Token (`rnd_...`).
- **Workspace:** `tea-dbq8tf8m7kps738oi350` ("Siddharth's workspace").
- **Target Service:** `mil-quant-backend` (`srv-dbq9lugae00c73acv150`), Oregon (`us-west`).
- **Live State:** Deploy `dep-dc2ivvm0tbcc73827bug` (commit `10d201c`), Status `live`.
- **Safety Gating:** Token was provisioned with Read-Only permissions on services and deployments; write operations return 403 Forbidden.

#### 4. `mil-vercel` (282 tools)
- **Verified Status:** Active HTTP endpoint via `https://mcp.vercel.com`.
- **Authentication:** OAuth 2.0 / Session, User `yelugamsiddharth18-1415`.
- **Scope:** Team `team_VuzcFRLUmFIAKddZCreNylwk`, Project `market-intelligence-lab`.
- **Tool Capabilities:** Deployments, DNS/domain routing, serverless logs, edge config, firewall.
- **Safety Gating:** `delete_project`, `delete_sandbox`, `cancel_deployment`, and domain DNS mutation tools must be gated in CI/CD.

#### 5. `nse-bhavcopy` (21 tools)
- **Verified Status:** Active Python stdio bridge with Akamai retry resilience and Jackson schema compatibility.
- **Data Source:** Official NSE India Bhavcopy Redis hot tier & JVM cache (`https://mcp.nseindia.in/bhavcopy/cm/mcp`).
- **Tool Capabilities:** 21 financial data retrieval tools: `get_top_by_volume`, `get_top_movers`, `nse_lookup_symbol`, `get_market_mood`, `get_index_valuation`, `get_market_breadth`, `get_corporate_actions`, `compare_indices`, `get_index_movers`, `get_ltp_by_date`, `get_bulk_quote`, `get_volume_analysis`, `get_stock_history`, `get_index_snapshot`, `search_symbols`, `get_stock_vs_index`, `compare_stocks`, `get_index_history`, `moving_average`, `get_52_week_high_low`, `get_index_performance`.
- **Safety Classification:** 100% `READ_ONLY`. Non-destructive market data consumer.

#### 6. `alphavantage` (3 tools)
- **Verified Status:** Active local uvx stdio bridge with valid API key.
- **Tools:** `TOOL_LIST`, `TOOL_GET`, `TOOL_CALL`.
- **Safety Classification:** `READ_ONLY`. Used strictly as global fallback for benchmark cross-checks.

#### 7. `postgres` (1 tool)
- **Verified Status:** Tool registered (`query`), but target daemon `postgresql://localhost/market_intel_db` is **offline** (`ECONNREFUSED 127.0.0.1:5432`).
- **Safety Classification:** `READ_ONLY`. 
- **Action:** Retain definition in config, but note that MIL currently runs exclusively on SQLite WAL mode.

#### 8. `github` (26 tools)
- **Verified Status:** Active local stdio bridge authenticated via Personal Access Token (`ghp_...`).
- **Target Repository:** `sid1887/Market_Intelligence_Lab` (Public repository).
- **Tool Capabilities:** PR creation, issue tracking, commit inspection, code search, branch management.
- **Safety Gating:** Write tools (`push_files`, `merge_pull_request`, `create_pull_request_review`) must require manual approval during Phase 0 audit.

#### 9. `filesystem` (14 tools)
- **Verified Status:** Active local stdio server scoped strictly to `/home/siddharth/Desktop/Market_Intelligence_Lab`.
- **Tool Capabilities:** File search, reading, writing, directory navigation.
- **Safety Gating:** `edit_file` and `write_file` are restricted during Phase 0 strictly to audit files in `docs/`.

#### 10. `playwright` (25 tools)
- **Verified Status:** Active local headless Chromium instance.
- **Tool Capabilities:** Browser navigation, screenshots, DOM inspection, network evaluation.
- **Safety Classification:** Safe read-only UI testing and tearsheet visual auditing.

#### 11. `designrevision` (14 tools)
- **Verified Status:** Active remote HTTP endpoint (`https://mcp.designrevision.com/mcp`).
- **Capabilities:** Search and inspect UI component blocks and icons for dashboard design.

#### 12. `context7` (2 tools)
- **Verified Status:** Active npx bridge (`resolve-library-id`, `query-docs`).
- **Capabilities:** Fast framework documentation lookups (FastAPI, React, Next.js).

#### 13. `sequential-thinking` (1 tool)
- **Verified Status:** Active dynamic thought decomposition tool for complex reasoning.

---

## 3. Deployed Cloud Infrastructure & Resource Audit

### A. Render (`mil-quant-backend`)

| Metric / Dimension | Verified Live Value | Institutional Assessment |
| :--- | :--- | :--- |
| **Service ID** | `srv-dbq9lugae00c73acv150` | Primary Web Service |
| **Instance Tier** | Free Tier (`0.1 vCPU`, `512 MB RAM`) | Memory-constrained; high risk of OOM crash on heavy tasks |
| **Region** | Oregon, USA (`us-west`) | ~220ms network latency to Indian market feeds |
| **Active Deployment** | `dep-dc2ivvm0tbcc73827bug` | Triggered by commit `10d201c` |
| **Observed Memory Usage** | **392.48 MB / 512.00 MB (76.66%)** | **HIGH RISK**: Only ~119 MB headroom remains before Linux kernel OOM killer (`SIGKILL 137`) terminates process |
| **Observed CPU Usage** | `0.01 vCPU (~1.0%)` | Ample idle headroom, but throttled during multi-threaded pandas computations |
| **Spin-Down Inactivity Timeout** | 15 minutes of idle | Shuts down container completely |
| **Observed Cold Start Latency** | **32 to 48 seconds** | Unacceptable for live trader interaction without keep-alive pingers |
| **Keep-Alive Protection** | Active (`.github/workflows/render_keepalive.yml`) | Pings `/api/v1/health` every 10–14 minutes during market hours |

#### Critical Finding: Render Ephemeral Filesystem & State Evaporator
Render Free Web Services allocate an **ephemeral container filesystem**. Any file written to disk inside the container is discarded when the service restarts, spins down, or redeploys:
- **43 API Endpoints write to SQLite or local disk** (see `docs/MIL_CURRENT_STATE_AUDIT.md`).
- **Loss Scenario:** When a user uploads Angel One tradebooks, executes paper trades, saves custom watchlists, or triggers ML model training on Render, those database rows and `.enc` files exist **ONLY in ephemeral container RAM/disk**.
- **On next redeploy (or after 15m idle), ALL user data reverts back to the Git baseline (`cloud_seed_snapshot.json.gz`), silently vaporizing user state.**

---

### B. Vercel (`market-intelligence-lab`)

| Metric / Dimension | Verified Live Value | Institutional Assessment |
| :--- | :--- | :--- |
| **Account / Owner** | `yelugamsiddharth18-1415` | Personal Hobby Tier |
| **Production URL** | `https://market-intelligence-3lqpvcysh-siddharths-projects-cb17bd75.vercel.app` | Active Edge deployment |
| **Framework** | Next.js 14 App Router | Static and Serverless Edge rendering |
| **Serverless Execution Limit** | 10 seconds (Hobby plan) | Cannot proxy long-running Python backtests or ML queries directly |
| **Commit Parity** | Aligned with Render `10d201c` | Frontend is in sync with backend API schema |

---

### C. Azure Cloud Credits (`Azure for Students`)

| Metric / Dimension | Verified Live Value | Institutional Assessment |
| :--- | :--- | :--- |
| **Subscription ID** | `ee12014b-365b-405d-94c9-e484cee5a08c` | `Azure for Students` |
| **Subscription State** | `Enabled` | Active account |
| **Verified Remaining Balance** | **INR 9,523.00** | Expiry: **November 19, 2027** (~12 months runway) |
| **Active Resource Groups** | `0` (Clean Slate) | Zero active spending |
| **Active Virtual Machines** | `0` | Zero compute charges |
| **Active Storage Accounts** | `0` | Zero storage charges |
| **Existing Budget Alerts** | **`0` (NONE FOUND)** | **CRITICAL RISK**: Uncontrolled resource creation will burn credits silently |
| **Existing Action Groups** | **`0` (NONE FOUND)** | No automated shutdown hooks exist |

#### Azure Billing Realities & Architectural Nuances:
1. **The Deallocation Trap:** Deallocating a VM (`Stop-Deallocated`) stops CPU billing, but **Managed Disks (Standard SSD / Premium SSD), static Public IPs, and NAT gateways continue incurring monthly charges 24/7**.
2. **Budget Alerts Do Not Stop Billing:** Standard Azure Budget alerts send emails; they do NOT stop resource execution unless explicitly coupled with an **Azure Action Group** that triggers an Azure Runbook / Logic App to deallocate resources.
3. **Blob Cool / Cold Storage:** Ideal for `.milz` historical archives (~₹0.20 per GB/month). True write-once durability requires configuring WORM (Write Once, Read Many) legal hold / time-based retention policy.

---

### D. Deepnote (`ML-Book`)

| Metric / Dimension | Verified Live Value | Institutional Assessment |
| :--- | :--- | :--- |
| **Workspace Name / ID** | `ML-Book` (`0305b43e-4bfe-47fa-bfd4-3a2393863761`) | Dedicated Data Science Workspace |
| **Available Hardware Tier** | `lake` tier instance | **2 vCPUs, 5 GiB RAM** available on workspace plan |
| **Active Notebook Projects** | 4 projects (`ML_REEE` 6 notebooks, `ml-book` 1 notebook) | Operational R&D environment |
| **Role in MIL 2.0** | Offload ML training & tournament backtesting | Safely bypasses Render's 512 MB memory boundary |

---

### E. GitHub Actions (Worker Infrastructure)

| Metric / Dimension | Verified Live Value | Institutional Assessment |
| :--- | :--- | :--- |
| **Repository Visibility** | **Public** (`sid1887/Market_Intelligence_Lab`) | Verified via GitHub API |
| **Runner Hardware** | Standard Ubuntu Linux (`ubuntu-latest`) | **4 vCPUs, 16 GB RAM, 14 GB SSD** |
| **Monthly Minute Quota** | **UNLIMITED** | Free public repositories receive unlimited standard Linux runner minutes |
| **Active Workflows** | 4 workflows (`ci.yml`, `cloud_ml_tournament.yml`, `cloud_news_radar.yml`, `render_keepalive.yml`) | All 74 recorded workflow runs succeeded |

---

## 4. Cost Guardrails & Security Policies

1. **Credit Protection Policy:** No Azure resource may be created without a mandatory tag `Project=MIL` and an automated Budget Alert + Action Group capped at INR 1,000/month.
2. **Read-Only Enclave Policy:** Production MCP credentials remain in local configuration; zero secrets may be embedded in git commits or markdown documents.
3. **Storage Tiering Policy:** Heavy archives (`bhavcopy_10y.milz`) are committed as Git LFS or stored in Azure Blob Cool storage; Render serves pre-computed JSON indices.
