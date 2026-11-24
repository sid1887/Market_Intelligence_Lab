"""
tests/test_durable_state.py
Unit & Integration Tests for Zero-Cost Durable State Persistence Engine.
Phase 1 Deliverable — Tests SQLite mutable state export/restore and Azure Blob mocking.
"""

import os
import gzip
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path
from unittest.mock import MagicMock

from src.storage.database import DatabaseManager
from src.storage.durable_state import (
    AzureBlobClient,
    DurableStateManager,
    mark_state_dirty,
    MUTABLE_USER_TABLES,
    CONTAINER_NAME,
    STATE_BLOB_NAME,
    TRADEBOOK_ENC_BLOB_NAME
)


@pytest.fixture
def temp_db():
    """Creates a temporary in-memory/file SQLite database with initialized schema."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        db_path = tf.name
    db = DatabaseManager(db_path)
    db.init_schema()

    # Populate a test user watchlist and a portfolio account
    with db.get_connection() as conn:
        conn.execute("""
            INSERT INTO user_watchlists (symbol, company_name, sector, added_date, notes)
            VALUES ('GAIL', 'GAIL (India) Ltd', 'Energy', '2026-11-20', 'Phase 1 Test')
        """)
        conn.execute("""
            INSERT OR REPLACE INTO portfolio_accounts (account_id, cash_balance, total_nav, updated_at)
            VALUES ('test_acc_1', 50000.0, 60000.0, '2026-11-24T10:00:00Z')
        """)
        # Ensure ohlcv_daily has a row to verify it is NOT exported
        conn.execute("""
            INSERT INTO ohlcv_daily (symbol, trading_date, series, open, high, low, close, volume, source, retrieval_timestamp)
            VALUES ('GAIL', '2026-11-20', 'EQ', 190.0, 195.0, 189.0, 193.0, 1000000, 'BHAVCOPY', '2026-11-20T18:00:00Z')
        """)
        conn.commit()

    yield db

    try:
        os.remove(db_path)
    except OSError:
        pass


def test_export_mutable_state_excludes_market_tables(temp_db):
    mgr = DurableStateManager(db=temp_db)
    gz_bytes = mgr.export_mutable_state()
    assert gz_bytes is not None
    assert len(gz_bytes) > 0

    # Decompress and inspect JSON
    with gzip.GzipFile(fileobj=tempfile.SpooledTemporaryFile(), mode="wb") as f:
        pass  # test decomp
    json_str = gzip.decompress(gz_bytes).decode("utf-8")
    payload = json.loads(json_str)

    assert "tables" in payload
    tables = payload["tables"]
    # User tables must be present
    assert "user_watchlists" in tables
    assert "portfolio_accounts" in tables
    # Market OHLCV table must NEVER be exported
    assert "ohlcv_daily" not in tables
    assert "index_daily" not in tables

    # Check row data
    wl_rows = tables["user_watchlists"]["rows"]
    assert any("GAIL" in str(r) for r in wl_rows)


def test_restore_mutable_state_roundtrip(temp_db):
    mgr = DurableStateManager(db=temp_db)
    gz_bytes = mgr.export_mutable_state()

    # Create a fresh secondary DB
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tf:
        second_path = tf.name
    second_db = DatabaseManager(second_path)
    second_db.init_schema()

    second_mgr = DurableStateManager(db=second_db)
    restored = second_mgr.restore_mutable_state(gz_bytes)

    assert restored.get("user_watchlists", 0) >= 1
    assert restored.get("portfolio_accounts", 0) >= 1

    # Verify rows in secondary DB
    with second_db.get_connection() as conn:
        sec = conn.execute("SELECT symbol FROM user_watchlists WHERE symbol = 'GAIL'").fetchone()
        assert sec is not None
        assert sec[0] == "GAIL"

        acc = conn.execute("SELECT account_id, cash_balance FROM portfolio_accounts WHERE account_id = 'test_acc_1'").fetchone()
        assert acc is not None
        assert acc[1] == 50000.0

    try:
        os.remove(second_path)
    except OSError:
        pass


def test_encrypted_tradebook_roundtrip(tmp_path):
    enc_file = tmp_path / "master_tradebook.enc"
    enc_content = b"TEST_ENCRYPTED_FERNET_PAYLOAD_V1"
    enc_file.write_bytes(enc_content)

    mgr = DurableStateManager()
    # Test reading
    assert mgr.restore_tradebook_enc(enc_content) is True


def test_azure_blob_client_unconfigured_fallback():
    client = AzureBlobClient(connection_string="")
    assert client.is_configured is False
    # Upload and download must return False / None gracefully without crashing
    assert client.upload_blob(CONTAINER_NAME, STATE_BLOB_NAME, b"test") is False
    assert client.download_blob(CONTAINER_NAME, STATE_BLOB_NAME) is None


def test_durable_state_manager_with_mocked_blob(temp_db):
    mock_client = MagicMock(spec=AzureBlobClient)
    mock_client.is_configured = True
    mock_client.upload_blob.return_value = True
    mock_client.download_blob.return_value = None

    mgr = DurableStateManager(db=temp_db, client=mock_client)
    # Test sync flush
    assert mgr.flush_sync() is True
    assert mock_client.upload_blob.called
    uploaded_blobs = [call[0][1] for call in mock_client.upload_blob.call_args_list]
    assert STATE_BLOB_NAME in uploaded_blobs


def test_mark_state_dirty_convenience():
    # Calling mark_state_dirty must never raise exceptions
    mark_state_dirty()
