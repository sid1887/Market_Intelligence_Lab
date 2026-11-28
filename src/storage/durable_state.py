"""
src/storage/durable_state.py
Zero-Cost Durable State Persistence Engine for Render Free / Cloud Workloads.
Phase 1 Deliverable — Eliminates ephemeral container data loss on Render.

Scope:
- Exports and restores strictly MUTABLE USER STATE (never multi-GB market OHLCV data).
- Compact gzip JSON snapshots of:
    portfolio_accounts, portfolio_positions, portfolio_orders, backtest_runs,
    real_closed_roundtrips, real_open_holdings, real_capital_ledger, real_dp_charges,
    real_tradebook_audit_log, user_watchlists, copilot_memory_episodes, model_registry.
- Encrypted master tradebook file (data/secure/master_tradebook.enc).
- Uses lightweight stdlib HMAC-SHA256 REST client (< 1 MB RAM overhead).
- Debounced asynchronous background uploader (flushing every 30 seconds after mutation).
- Graceful local fallback (no-op when AZURE_STORAGE_CONNECTION_STRING is unset).
"""

import os
import io
import re
import gzip
import json
import time
import hmac
import base64
import hashlib
import logging
import datetime
import threading
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional, Tuple
from pathlib import Path

import httpx

from src.storage.database import DatabaseManager

logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("MIL.DurableState")

CONTAINER_NAME = "mil-durable-state"
STATE_BLOB_NAME = "latest_user_state.json.gz"
TRADEBOOK_ENC_BLOB_NAME = "master_tradebook.enc"

MUTABLE_USER_TABLES: List[str] = [
    "portfolio_accounts",
    "portfolio_positions",
    "portfolio_orders",
    "rebalance_proposals",
    "backtest_runs",
    "backtest_equity_curve",
    "real_closed_roundtrips",
    "real_open_holdings",
    "real_capital_ledger",
    "real_dp_charges",
    "real_trade_executions",
    "real_tradebook_audit_log",
    "user_watchlists",
    "push_subscriptions",
    "copilot_memory_episodes",
    "copilot_distillation_corpus",
    "llm_usage_telemetry",
    "model_registry",
    "model_horizon_deployments",
]

DEFAULT_TRADEBOOK_ENC_PATHS = [
    Path("data/secure/master_tradebook.enc"),
    Path("data/master_tradebook.enc"),
    Path("master_tradebook.enc")
]


class AzureBlobClient:
    """
    Lightweight, zero-overhead Azure Blob Storage client using Python standard library.
    Eliminates heavy azure-storage-blob binary dependencies, preserving Render's 512 MB ceiling.
    """

    def __init__(self, connection_string: Optional[str] = None):
        self.connection_string = connection_string or os.environ.get("AZURE_STORAGE_CONNECTION_STRING", "")
        self.account_name: Optional[str] = None
        self.account_key: Optional[str] = None
        self.endpoint_suffix: str = "core.windows.net"
        self._parse_connection_string()

    def _parse_connection_string(self) -> None:
        if not self.connection_string:
            return
        m_name = re.search(r"AccountName=([^;]+)", self.connection_string)
        m_key = re.search(r"AccountKey=([^;]+)", self.connection_string)
        m_suffix = re.search(r"EndpointSuffix=([^;]+)", self.connection_string)
        if m_name and m_key:
            self.account_name = m_name.group(1).strip()
            self.account_key = m_key.group(1).strip()
            if m_suffix:
                self.endpoint_suffix = m_suffix.group(1).strip()

    @property
    def is_configured(self) -> bool:
        return bool(self.account_name and self.account_key)

    def _sign_request(self, verb: str, path: str, headers: Dict[str, str]) -> str:
        """Computes Azure Storage SharedKey HMAC-SHA256 authorization signature."""
        canonical_headers = ""
        ms_headers = sorted([(k.lower(), v) for k, v in headers.items() if k.lower().startswith("x-ms-")])
        for k, v in ms_headers:
            canonical_headers += f"{k}:{v}\n"
        canonical_resource = f"/{self.account_name}{path}"
        content_length = headers.get("Content-Length", "")
        content_type = headers.get("Content-Type", "")
        string_to_sign = f"{verb}\n\n\n{content_length}\n\n{content_type}\n\n\n\n\n\n\n{canonical_headers}{canonical_resource}"
        decoded_key = base64.b64decode(self.account_key)
        sig = base64.b64encode(hmac.new(decoded_key, string_to_sign.encode("utf-8"), hashlib.sha256).digest()).decode("utf-8")
        return f"SharedKey {self.account_name}:{sig}"

    def upload_blob(self, container: str, blob_name: str, data: bytes, content_type: str = "application/octet-stream") -> bool:
        """Uploads binary data to Azure Blob Storage as a BlockBlob."""
        if not self.is_configured:
            return False
        path = f"/{container}/{blob_name}"
        url = f"https://{self.account_name}.blob.{self.endpoint_suffix}{path}"
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers = {
            "x-ms-date": now_str,
            "x-ms-version": "2020-10-02",
            "x-ms-blob-type": "BlockBlob",
            "Content-Type": content_type,
            "Content-Length": str(len(data))
        }
        headers["Authorization"] = self._sign_request("PUT", path, headers)

        req = urllib.request.Request(url, data=data, headers=headers, method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                return resp.status in (200, 201)
        except Exception as e:
            logger.warning(f"[DURABLE-STATE-UPLOAD-FAIL] Failed to upload {blob_name} to {container}: {e}")
            return False

    def download_blob(self, container: str, blob_name: str) -> Optional[bytes]:
        """Downloads binary data from Azure Blob Storage."""
        if not self.is_configured:
            return None
        path = f"/{container}/{blob_name}"
        url = f"https://{self.account_name}.blob.{self.endpoint_suffix}{path}"
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        headers = {
            "x-ms-date": now_str,
            "x-ms-version": "2020-10-02"
        }
        headers["Authorization"] = self._sign_request("GET", path, headers)

        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                if resp.status == 200:
                    return resp.read()
        except urllib.error.HTTPError as he:
            if he.code == 404:
                logger.info(f"[DURABLE-STATE-404] Blob {blob_name} does not exist yet in {container}.")
            else:
                logger.warning(f"[DURABLE-STATE-DOWNLOAD-FAIL] HTTP {he.code} downloading {blob_name}: {he.reason}")
        except Exception as e:
            logger.warning(f"[DURABLE-STATE-DOWNLOAD-FAIL] Exception downloading {blob_name}: {e}")
        return None


class GitHubRepoStateClient:
    """
    Cardless, zero-cost durable state client using GitHub's REST Contents API
    against a private repository (e.g., sid1887/mil-user-state) via httpx.
    """

    def __init__(
        self,
        token: Optional[str] = None,
        repo: Optional[str] = None,
        state_path: Optional[str] = None,
    ):
        self.token = (token if token is not None else os.environ.get("MIL_STATE_GITHUB_TOKEN", "")).strip()
        self.repo = (repo if repo is not None else os.environ.get("MIL_STATE_GITHUB_REPO", "")).strip().strip("/")
        self.state_path = (
            state_path if state_path is not None else os.environ.get("MIL_STATE_GITHUB_PATH", "state/user_state_bundle.json.gz")
        ).strip().lstrip("/")
        self.tradebook_path = "state/master_tradebook.enc"
        self.api_base = "https://api.github.com"

    @property
    def is_configured(self) -> bool:
        return bool(self.token and self.repo)

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _get_file_meta(self, path: str) -> Optional[Dict[str, Any]]:
        if not self.is_configured:
            return None
        url = f"{self.api_base}/repos/{self.repo}/contents/{path.lstrip('/')}"
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=self._headers())
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()

    def download_file(self, path: Optional[str] = None) -> Optional[bytes]:
        """Downloads and base64-decodes a file from the private GitHub state repo."""
        if not self.is_configured:
            return None
        target = (path or self.state_path).lstrip("/")
        meta = self._get_file_meta(target)
        if not meta:
            return None

        content_b64 = meta.get("content")
        if content_b64:
            return base64.b64decode(content_b64)

        download_url = meta.get("download_url")
        if download_url:
            with httpx.Client(timeout=30.0) as client:
                dl_resp = client.get(download_url, headers=self._headers())
                dl_resp.raise_for_status()
                return dl_resp.content
        return None

    def upload_file(
        self,
        data: bytes,
        path: Optional[str] = None,
        commit_message: str = "chore(state): sync MIL durable user state",
    ) -> bool:
        """Uploads (creates or updates with SHA) a file to the private GitHub state repo."""
        if not self.is_configured:
            return False
        target = (path or self.state_path).lstrip("/")
        url = f"{self.api_base}/repos/{self.repo}/contents/{target}"

        sha: Optional[str] = None
        try:
            meta = self._get_file_meta(target)
            if meta:
                sha = meta.get("sha")
        except Exception as meta_err:
            logger.warning(f"[DURABLE-STATE-GH] Metadata check failed for {target}: {meta_err}")

        payload: Dict[str, Any] = {
            "message": commit_message,
            "content": base64.b64encode(data).decode("ascii"),
        }
        if sha:
            payload["sha"] = sha

        with httpx.Client(timeout=30.0) as client:
            resp = client.put(url, headers=self._headers(), json=payload)
            resp.raise_for_status()
            return resp.status_code in (200, 201)


class DurableStateManager:
    """
    Manages debounced asynchronous state backups and startup hydration
    for all mutable user state and encrypted tradebook files.
    """

    _instance: Optional["DurableStateManager"] = None
    _lock = threading.Lock()

    def __init__(
        self,
        db: Optional[DatabaseManager] = None,
        client: Optional[AzureBlobClient] = None,
        github_client: Optional[GitHubRepoStateClient] = None,
    ):
        self.db = db or DatabaseManager()
        self.client = client or AzureBlobClient()
        self.github_client = github_client or GitHubRepoStateClient()
        self.debounce_seconds: float = 30.0
        self.max_wait_seconds: float = 120.0
        self._is_dirty: bool = False
        self._last_dirty_time: float = 0.0
        self._last_flush_time: float = time.time()
        self._daemon_started: bool = False
        self._daemon_thread: Optional[threading.Thread] = None
        self._last_sync_status: str = self._compute_initial_status()

    def _compute_initial_status(self) -> str:
        az = self.client.is_configured
        gh = self.github_client.is_configured
        if az and gh:
            return "IN_SYNC_DUAL"
        if az:
            return "IN_SYNC_AZURE"
        if gh:
            return "IN_SYNC_GITHUB_FALLBACK"
        return "LOCAL_ONLY"

    @property
    def has_any_backend(self) -> bool:
        return self.client.is_configured or self.github_client.is_configured

    def get_active_backends(self) -> List[str]:
        backends: List[str] = []
        if self.client.is_configured:
            backends.append("azure_blob")
        if self.github_client.is_configured:
            backends.append("github_repo")
        return backends

    def get_status_summary(self) -> Dict[str, Any]:
        if self._is_dirty and self.has_any_backend:
            status = "DIRTY_SYNC_PENDING"
        else:
            status = self._last_sync_status
        return {
            "durable_state_status": status,
            "durable_backends_active": self.get_active_backends(),
        }

    @classmethod
    def get_instance(cls, db: Optional[DatabaseManager] = None) -> "DurableStateManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(db=db)
            return cls._instance

    def mark_state_dirty(self) -> None:
        """Flags that mutable state has changed; initiates debounced background sync timer."""
        self._is_dirty = True
        self._last_dirty_time = time.time()
        self._ensure_daemon()

    def _ensure_daemon(self) -> None:
        if self._daemon_started and self._daemon_thread and self._daemon_thread.is_alive():
            return
        if not self.has_any_backend:
            return  # No-op in local dev / unconfigured environments
        with self._lock:
            if not self._daemon_started or not (self._daemon_thread and self._daemon_thread.is_alive()):
                self._daemon_started = True
                self._daemon_thread = threading.Thread(target=self._debounce_worker, daemon=True, name="DurableStateUploader")
                self._daemon_thread.start()

    def _debounce_worker(self) -> None:
        """Background daemon polling debounced state writes."""
        while True:
            time.sleep(5.0)
            if not self._is_dirty:
                continue
            now = time.time()
            time_since_dirty = now - self._last_dirty_time
            time_since_flush = now - self._last_flush_time
            if (time_since_dirty >= self.debounce_seconds) or (time_since_flush >= self.max_wait_seconds):
                self.flush_sync()

    def export_mutable_state(self) -> bytes:
        """
        Exports all MUTABLE_USER_TABLES from SQLite into a compact gzip JSON stream.
        Strictly excludes multi-GB market tables (ohlcv_daily, index_daily).
        """
        state_dict: Dict[str, Any] = {
            "version": "1.0",
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "tables": {}
        }

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            for tbl in MUTABLE_USER_TABLES:
                # Check table existence
                exists = cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                ).fetchone()
                if not exists:
                    continue
                rows = cur.execute(f"SELECT * FROM {tbl}").fetchall()
                cols = [desc[0] for desc in cur.description] if cur.description else []
                state_dict["tables"][tbl] = {
                    "columns": cols,
                    "rows": [list(r) for r in rows]
                }

        json_bytes = json.dumps(state_dict, separators=(",", ":")).encode("utf-8")
        out_buf = io.BytesIO()
        with gzip.GzipFile(fileobj=out_buf, mode="wb", compresslevel=6) as gz:
            gz.write(json_bytes)
        return out_buf.getvalue()

    def restore_mutable_state(self, gz_data: bytes) -> Dict[str, int]:
        """
        Restores mutable tables from a gzip JSON stream into SQLite WAL using INSERT OR REPLACE.
        """
        if not gz_data:
            return {}

        with gzip.GzipFile(fileobj=io.BytesIO(gz_data), mode="rb") as gz:
            json_bytes = gz.read()
        payload = json.loads(json_bytes.decode("utf-8"))
        tables = payload.get("tables", {})
        restored_counts: Dict[str, int] = {}

        with self.db.get_connection() as conn:
            cur = conn.cursor()
            for tbl, data in tables.items():
                if tbl not in MUTABLE_USER_TABLES:
                    continue
                exists = cur.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (tbl,)
                ).fetchone()
                if not exists:
                    continue
                cols = data.get("columns", [])
                rows = data.get("rows", [])
                if not cols or not rows:
                    restored_counts[tbl] = 0
                    continue
                col_names = ", ".join([f'"{c}"' for c in cols])
                placeholders = ", ".join(["?"] * len(cols))
                query = f"INSERT OR REPLACE INTO {tbl} ({col_names}) VALUES ({placeholders})"
                cur.executemany(query, rows)
                restored_counts[tbl] = len(rows)
            conn.commit()

        logger.info(f"[DURABLE-STATE-RESTORE] Restored {sum(restored_counts.values())} rows across {len(restored_counts)} tables.")
        return restored_counts

    def export_tradebook_enc(self) -> Optional[bytes]:
        """Reads master_tradebook.enc if it exists on disk."""
        for p in DEFAULT_TRADEBOOK_ENC_PATHS:
            if p.exists() and p.is_file():
                try:
                    return p.read_bytes()
                except Exception as e:
                    logger.warning(f"[DURABLE-STATE] Could not read {p}: {e}")
        return None

    def restore_tradebook_enc(self, data: bytes) -> bool:
        """Writes master_tradebook.enc to disk."""
        if not data:
            return False
        for p in DEFAULT_TRADEBOOK_ENC_PATHS:
            try:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(data)
                logger.info(f"[DURABLE-STATE] Restored encrypted tradebook to {p} ({len(data)} bytes).")
                return True
            except Exception as e:
                logger.warning(f"[DURABLE-STATE] Failed writing to {p}: {e}")
        return False

    def flush_sync(self) -> bool:
        """
        Executes an immediate synchronous snapshot export and dual-cloud upload
        (Azure Blob primary + Private GitHub Repo secondary/failover).
        """
        if not self.has_any_backend:
            self._is_dirty = False
            self._last_sync_status = "LOCAL_ONLY"
            return False

        try:
            gz_bytes = self.export_mutable_state()
            enc_data = self.export_tradebook_enc()
        except Exception as exp_err:
            logger.error(f"[DURABLE-STATE-SYNC-ERROR] Snapshot export failed: {exp_err}")
            return False

        azure_ok = False
        if self.client.is_configured:
            try:
                s_ok = self.client.upload_blob(CONTAINER_NAME, STATE_BLOB_NAME, gz_bytes, "application/gzip")
                e_ok = True
                if enc_data:
                    e_ok = self.client.upload_blob(CONTAINER_NAME, TRADEBOOK_ENC_BLOB_NAME, enc_data, "application/octet-stream")
                azure_ok = bool(s_ok and e_ok)
            except Exception as az_err:
                logger.warning(f"[DURABLE-STATE-AZURE-FAIL] Azure upload failed (failing over if GitHub configured): {az_err}")
                azure_ok = False

        github_ok = False
        if self.github_client.is_configured:
            try:
                gh_s_ok = self.github_client.upload_file(
                    gz_bytes,
                    path=self.github_client.state_path,
                    commit_message="chore(state): sync user_state_bundle.json.gz",
                )
                gh_e_ok = True
                if enc_data:
                    gh_e_ok = self.github_client.upload_file(
                        enc_data,
                        path=self.github_client.tradebook_path,
                        commit_message="chore(state): sync master_tradebook.enc",
                    )
                github_ok = bool(gh_s_ok and gh_e_ok)
            except Exception as gh_err:
                logger.warning(f"[DURABLE-STATE-GH-FAIL] GitHub state upload failed: {gh_err}")
                github_ok = False

        if azure_ok and github_ok:
            self._last_sync_status = "IN_SYNC_DUAL"
        elif azure_ok:
            self._last_sync_status = "IN_SYNC_AZURE"
        elif github_ok:
            self._last_sync_status = "IN_SYNC_GITHUB_FALLBACK"
        else:
            return False

        self._is_dirty = False
        self._last_flush_time = time.time()
        logger.info(
            f"[DURABLE-STATE-SYNC-SUCCESS] Flushed user state ({len(gz_bytes)} bytes) -> status={self._last_sync_status}"
        )
        return True

    def sync_user_state(self) -> bool:
        """Alias for flush_sync() supporting dual-cloud sync."""
        return self.flush_sync()

    @staticmethod
    def _extract_bundle_exported_at(gz_data: Optional[bytes]) -> Optional[datetime.datetime]:
        if not gz_data:
            return None
        try:
            payload = json.loads(gzip.decompress(gz_data).decode("utf-8"))
            ts = payload.get("exported_at")
            if ts:
                dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                return dt if dt.tzinfo else dt.replace(tzinfo=datetime.timezone.utc)
        except Exception:
            pass
        return None

    def restore_on_startup(self) -> Dict[str, Any]:
        """
        Attempts restore from Azure Blob and Private GitHub Repo, comparing bundle
        exported_at timestamps when both are available so stale primary backups do
        not shadow fresher failover state.
        """
        if not self.has_any_backend:
            self._last_sync_status = "LOCAL_ONLY"
            logger.info("[DURABLE-STATE-BOOT] No cloud state backend configured. Using local SQLite state.")
            return {"status": "LOCAL_ONLY", "tables": {}, "tradebook_restored": False}

        results: Dict[str, Any] = {"status": "LOCAL_ONLY", "tables": {}, "tradebook_restored": False, "provider": None}
        az_gz: Optional[bytes] = None
        az_enc: Optional[bytes] = None
        gh_gz: Optional[bytes] = None
        gh_enc: Optional[bytes] = None

        # 1. Fetch from Primary: Azure Blob Storage
        if self.client.is_configured:
            try:
                logger.info("[DURABLE-STATE-BOOT] Checking for durable state in Azure Blob Storage...")
                az_gz = self.client.download_blob(CONTAINER_NAME, STATE_BLOB_NAME)
                az_enc = self.client.download_blob(CONTAINER_NAME, TRADEBOOK_ENC_BLOB_NAME)
            except Exception as az_err:
                logger.warning(f"[DURABLE-STATE-BOOT] Azure restore failed ({az_err}); checking GitHub failover...")

        # 2. Fetch from Secondary / Cardless Failover: Private GitHub Repo
        if self.github_client.is_configured:
            try:
                logger.info("[DURABLE-STATE-BOOT] Checking for durable state in Private GitHub Repo...")
                gh_gz = self.github_client.download_file(self.github_client.state_path)
                gh_enc = self.github_client.download_file(self.github_client.tradebook_path)
            except Exception as gh_err:
                logger.warning(f"[DURABLE-STATE-BOOT] GitHub failover restore error: {gh_err}")

        az_ts = self._extract_bundle_exported_at(az_gz)
        gh_ts = self._extract_bundle_exported_at(gh_gz)
        use_github = False
        if gh_gz is not None or gh_enc is not None:
            if az_gz is None and az_enc is None:
                use_github = True
            elif gh_ts is not None and (az_ts is None or gh_ts > az_ts):
                logger.info(
                    f"[DURABLE-STATE-BOOT] GitHub backup ({gh_ts.isoformat()}) is newer than Azure ({az_ts}); selecting GitHub."
                )
                use_github = True

        chosen_gz = gh_gz if use_github else az_gz
        chosen_enc = gh_enc if use_github else az_enc
        if chosen_gz is not None:
            results["tables"] = self.restore_mutable_state(chosen_gz)
        if chosen_enc is not None:
            results["tradebook_restored"] = self.restore_tradebook_enc(chosen_enc)

        if chosen_gz is not None or chosen_enc is not None:
            if use_github:
                self._last_sync_status = "IN_SYNC_GITHUB_FALLBACK"
                results["status"] = "IN_SYNC_GITHUB_FALLBACK"
                results["provider"] = "github_repo"
            else:
                self._last_sync_status = "IN_SYNC_DUAL" if self.github_client.is_configured else "IN_SYNC_AZURE"
                results["status"] = self._last_sync_status
                results["provider"] = "azure_blob"
            return results

        return results

    def restore_user_state(self) -> Dict[str, Any]:
        """Alias for restore_on_startup() supporting dual-cloud failover."""
        return self.restore_on_startup()


def is_state_dirty() -> bool:
    """Convenience helper to check if durable state has uncommitted mutations."""
    try:
        return bool(DurableStateManager.get_instance()._is_dirty)
    except Exception:
        return False


def mark_state_dirty() -> None:
    """Convenience helper to flag state mutation from API routes and background tasks."""
    try:
        DurableStateManager.get_instance().mark_state_dirty()
    except Exception as e:
        logger.debug(f"mark_state_dirty non-fatal failure: {e}")
