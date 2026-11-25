"""
tests/test_phase12_dual_cloud_state.py
Verification suite for MIL 2.0 Phase 12:
1. Azure Blob primary restore & sync when healthy.
2. Automatic failover to Private GitHub Repo (mocked httpx GET/PUT with SHA handling)
   when Azure raises an exception or AZURE_STORAGE_CONNECTION_STRING is unset.
3. Dual-cloud mirroring (IN_SYNC_DUAL) and exception isolation per backend.
4. GET /api/v1/health telemetry across dual, Azure-only, GitHub-fallback, and local-only modes.
"""

import base64
from unittest.mock import MagicMock

import httpx
from starlette.testclient import TestClient

from src.api.main import app
from src.storage.database import DatabaseManager
from src.storage.hydration import ensure_core_tables_exist
from src.storage.durable_state import (
    AzureBlobClient,
    DurableStateManager,
    GitHubRepoStateClient,
)


def _make_seeded_db(tmp_path):
    db_path = tmp_path / "test_phase12.db"
    db = DatabaseManager(str(db_path))
    db.init_schema()
    with db.get_connection() as conn:
        ensure_core_tables_exist(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO user_watchlists (symbol, company_name, sector, added_date, notes)
            VALUES ('RELIANCE', 'Reliance Industries', 'ENERGY', '2026-01-01', 'Phase 12 test')
            """
        )
        conn.commit()
    return db


def test_azure_primary_and_dual_cloud_sync(tmp_path, monkeypatch):
    """Verifies primary Azure sync and dual-write mirroring to Private GitHub Repo."""
    db = _make_seeded_db(tmp_path)

    az = MagicMock(spec=AzureBlobClient)
    az.is_configured = True
    az.upload_blob.return_value = True

    gh = MagicMock(spec=GitHubRepoStateClient)
    gh.is_configured = True
    gh.state_path = "state/user_state_bundle.json.gz"
    gh.tradebook_path = "state/master_tradebook.enc"
    gh.upload_file.return_value = True

    mgr = DurableStateManager(db=db, client=az, github_client=gh)
    ok = mgr.sync_user_state()
    assert ok is True
    assert az.upload_blob.called
    assert gh.upload_file.called
    summary = mgr.get_status_summary()
    assert summary["durable_state_status"] == "IN_SYNC_DUAL"
    assert summary["durable_backends_active"] == ["azure_blob", "github_repo"]


def test_github_rest_contents_api_sha_failover_when_azure_fails(tmp_path, monkeypatch):
    """
    Verifies GitHubRepoStateClient handles httpx GET (SHA fetch) + PUT (base64 upload)
    and DurableStateManager fails over cleanly to IN_SYNC_GITHUB_FALLBACK when Azure raises.
    """
    db = _make_seeded_db(tmp_path)
    sample_gz = DurableStateManager(db=db).export_mutable_state()

    captured_puts = []

    def fake_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and "/contents/" in request.url.path:
            return httpx.Response(
                200,
                json={
                    "sha": "abc123sha",
                    "content": base64.b64encode(sample_gz).decode("ascii"),
                },
            )
        if request.method == "PUT" and "/contents/" in request.url.path:
            import json as _json
            body = _json.loads(request.content.decode("utf-8"))
            captured_puts.append(body)
            return httpx.Response(200, json={"content": {"sha": "new456sha"}})
        return httpx.Response(404)

    transport = httpx.MockTransport(fake_handler)
    orig_client_cls = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs["transport"] = transport
        return orig_client_cls(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)

    az = MagicMock(spec=AzureBlobClient)
    az.is_configured = True
    az.upload_blob.side_effect = RuntimeError("Azure quota expired")
    az.download_blob.side_effect = RuntimeError("Azure quota expired")

    gh = GitHubRepoStateClient(
        token="ghp_test_token_123",
        repo="sid1887/mil-user-state",
        state_path="state/user_state_bundle.json.gz",
    )
    mgr = DurableStateManager(db=db, client=az, github_client=gh)

    # 1. Failover sync
    assert mgr.sync_user_state() is True
    assert len(captured_puts) >= 1
    assert captured_puts[0]["sha"] == "abc123sha"
    assert mgr.get_status_summary()["durable_state_status"] == "IN_SYNC_GITHUB_FALLBACK"

    # 2. Failover restore
    restored = mgr.restore_user_state()
    assert restored["status"] == "IN_SYNC_GITHUB_FALLBACK"
    assert restored["provider"] == "github_repo"
    assert restored["tables"].get("user_watchlists", 0) >= 1


def test_health_endpoint_reports_durable_state_modes(tmp_path, monkeypatch):
    """Verifies /api/v1/health surfaces durable_state_status across all 4 modes."""
    db = _make_seeded_db(tmp_path)
    client = TestClient(app)

    cases = [
        (True, True, "IN_SYNC_DUAL", ["azure_blob", "github_repo"]),
        (True, False, "IN_SYNC_AZURE", ["azure_blob"]),
        (False, True, "IN_SYNC_GITHUB_FALLBACK", ["github_repo"]),
        (False, False, "LOCAL_ONLY", []),
    ]

    for az_on, gh_on, expected_status, expected_backends in cases:
        az = MagicMock(spec=AzureBlobClient)
        az.is_configured = az_on
        gh = MagicMock(spec=GitHubRepoStateClient)
        gh.is_configured = gh_on
        mgr = DurableStateManager(db=db, client=az, github_client=gh)
        monkeypatch.setattr(DurableStateManager, "get_instance", classmethod(lambda cls, db=None, m=mgr: m))

        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["durable_state_status"] == expected_status
        assert data["durable_backends_active"] == expected_backends
