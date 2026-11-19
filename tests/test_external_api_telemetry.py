import os
import pytest
from fastapi.testclient import TestClient
from src.storage.database import DatabaseManager, record_external_api_metric
from src.api.main import app

def test_external_api_telemetry_recording(tmp_path):
    db_file = str(tmp_path / "test_telemetry.db")
    db = DatabaseManager(db_file)

    # Record Telegram metric
    record_external_api_metric(
        service_name="telegram",
        endpoint_or_model="sendMessage",
        success=True,
        units=1,
        db_manager=db
    )

    # Record yfinance metric
    record_external_api_metric(
        service_name="yfinance",
        endpoint_or_model="batch_ohlcv",
        success=True,
        units=50,
        quota_source="free_unmetered",
        db_manager=db
    )

    # Record Web Push metric
    record_external_api_metric(
        service_name="web_push",
        endpoint_or_model="vapid_push",
        success=True,
        units=2,
        db_manager=db
    )

    # Verify rows in DB
    with db.get_connection() as conn:
        rows = conn.execute("SELECT * FROM external_api_telemetry ORDER BY service_name").fetchall()
        assert len(rows) == 3
        services = {r["service_name"]: dict(r) for r in rows}
        assert "telegram" in services
        assert services["telegram"]["calls_succeeded"] == 1
        assert services["telegram"]["units_processed"] == 1

        assert "yfinance" in services
        assert services["yfinance"]["calls_succeeded"] == 1
        assert services["yfinance"]["units_processed"] == 50

        assert "web_push" in services
        assert services["web_push"]["calls_succeeded"] == 1
        assert services["web_push"]["units_processed"] == 2

def test_copilot_usage_endpoint_includes_external_apis():
    client = TestClient(app)
    response = client.get("/api/v1/copilot/usage")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "success"
    assert "models" in data
    assert "distillation" in data
    assert "external_apis" in data
    assert isinstance(data["external_apis"], list)
