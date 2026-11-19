"""
Unit and integration tests for LLM Quota Metering, Teacher-Student Distillation,
and Grounded Copilot Telemetry.
"""

import pytest
import sqlite3
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from src.storage.database import DatabaseManager
from src.copilot.llm_client import (
    record_llm_usage,
    set_last_call_telemetry,
    get_last_call_telemetry,
    MODEL_QUOTAS,
)
from src.copilot.distiller import (
    abstract_prompt_text,
    abstract_teacher_response,
    store_teacher_trace,
    CopilotKnowledgeDistiller,
)
from src.api.main import app


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_quota_distill.db")
    db = DatabaseManager(db_file)
    db.init_schema()
    return db


def test_llm_usage_telemetry_recording(test_db):
    """Verifies that LLM token and request usage accumulates atomically in SQLite."""
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    # Record first call
    record_llm_usage(
        db_manager=test_db,
        provider="groq",
        model_id="openai/gpt-oss-120b",
        prompt_tokens=150,
        completion_tokens=50,
        headers={"x-ratelimit-remaining-requests": "999", "x-ratelimit-remaining-tokens": "199800"}
    )

    with test_db.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM llm_usage_telemetry WHERE usage_date = ? AND model_id = ?",
            (today_utc, "openai/gpt-oss-120b")
        ).fetchone()

        assert row is not None
        assert row["requests_used"] == 1
        assert row["prompt_tokens"] == 150
        assert row["completion_tokens"] == 50
        assert row["total_tokens"] == 200
        assert row["remaining_requests_header"] == 999
        assert row["remaining_tokens_header"] == 199800

    # Record second call on same date - should accumulate
    record_llm_usage(
        db_manager=test_db,
        provider="groq",
        model_id="openai/gpt-oss-120b",
        prompt_tokens=100,
        completion_tokens=100,
        headers={"x-ratelimit-remaining-requests": "998", "x-ratelimit-remaining-tokens": "199600"}
    )

    with test_db.get_connection() as conn:
        row = conn.execute(
            "SELECT * FROM llm_usage_telemetry WHERE usage_date = ? AND model_id = ?",
            (today_utc, "openai/gpt-oss-120b")
        ).fetchone()

        assert row["requests_used"] == 2
        assert row["prompt_tokens"] == 250
        assert row["completion_tokens"] == 150
        assert row["total_tokens"] == 400
        assert row["remaining_requests_header"] == 998


def test_telemetry_contextvars():
    """Verifies request-scoped contextvar propagation for model attribution."""
    set_last_call_telemetry("groq:openai/gpt-oss-120b", {"prompt_tokens": 120, "completion_tokens": 45, "total_tokens": 165})
    tel = get_last_call_telemetry()
    assert tel["model_id"] == "groq:openai/gpt-oss-120b"
    assert tel["token_usage"]["total_tokens"] == 165


def test_distillation_prompt_and_response_abstraction():
    """Verifies parameterized abstraction of concrete symbols and numeric values into slots."""
    prompt = "What was COLPAL's last major dip?"
    abs_p = abstract_prompt_text(prompt, "COLPAL")
    assert "{{SYMBOL}}" in abs_p

    response = (
        "COLPAL is currently trading at ₹1744.50 with an ROE of 63.1% and P/E of 54.2. "
        "Its last major peak-to-trough drop was -12.4% over 15 sessions."
    )
    features = {
        "current_price": 1744.50,
        "fundamentals": {"roe_pct": 63.1, "pe_ratio": 54.2},
        "historical_drawdowns": {
            "last_major_dip": {"drop_pct": -12.4, "days_to_trough": 15}
        }
    }
    abs_resp = abstract_teacher_response(response, "COLPAL", features)
    assert "{{SYMBOL}}" in abs_resp
    assert "{{PRICE}}" in abs_resp
    assert "{{ROE}}" in abs_resp


def test_teacher_trace_storage_and_offline_hydration(test_db):
    """Verifies teacher response logging, index training, and offline template hydration."""
    features = {
        "company_name": "Colgate-Palmolive (India) Ltd",
        "current_price": 1744.50,
        "as_of_date": "2026-11-18",
        "fundamentals": {"roe_pct": 63.1, "pe_ratio": 54.2, "opm_pct": 32.5},
        "technicals": {"ret_20d_pct": 2.4},
        "historical_drawdowns": {
            "last_major_dip": {
                "peak_price": 1850.0,
                "peak_date": "2026-09-10",
                "trough_price": 1620.0,
                "trough_date": "2026-10-05",
                "drop_pct": -12.43,
                "days_to_trough": 18,
                "status": "Recovering"
            }
        }
    }

    teacher_resp = (
        "**COLPAL** (Colgate-Palmolive (India) Ltd) is trading at ₹1744.50 as of 2026-11-18. "
        "The company demonstrates high capital efficiency with an ROE of 63.1% and OPM of 32.5%."
    )

    # Store trace
    corpus_id = store_teacher_trace(
        db_manager=test_db,
        intent="DIRECT_QA",
        symbol="COLPAL",
        sector="FMCG",
        user_prompt="Give me a fundamental breakdown of COLPAL",
        teacher_model="groq:openai/gpt-oss-120b",
        teacher_response=teacher_resp,
        telemetry_features=features
    )
    assert corpus_id is not None

    # Train student model
    distiller = CopilotKnowledgeDistiller(test_db)
    train_res = distiller.train()
    assert train_res["trained"] is True
    assert train_res["corpus_size"] >= 1

    # Query with a similar prompt for another stock (e.g. RELIANCE)
    target_stock = {
        "company_name": "Reliance Industries Ltd",
        "current_price": 2450.00,
        "as_of_date": "2026-11-18",
        "fundamentals": {"roe_pct": 14.8, "pe_ratio": 24.1, "opm_pct": 18.2},
        "technicals": {"ret_20d_pct": 1.5}
    }

    hydrated = distiller.retrieve_and_hydrate(
        prompt="Give me a fundamental summary for RELIANCE",
        intent="DIRECT_QA",
        symbol="RELIANCE",
        stock_telemetry=target_stock
    )

    assert hydrated is not None
    # Verify that the hydrated output plugged in RELIANCE and its live metrics
    assert "RELIANCE" in hydrated
    assert "2450.00" in hydrated
    assert "14.8%" in hydrated


def test_copilot_usage_and_distill_endpoints():
    """Verifies /api/v1/copilot/usage and /api/v1/copilot/distill REST endpoints."""
    client = TestClient(app)

    # GET /api/v1/copilot/usage
    res_usage = client.get("/api/v1/copilot/usage")
    assert res_usage.status_code == 200
    data = res_usage.json()
    assert data["status"] == "success"
    assert "models" in data
    assert len(data["models"]) >= 4
    assert "distillation" in data

    # Check model schema
    gpt120 = next((m for m in data["models"] if "120b" in m["model_id"]), None)
    assert gpt120 is not None
    assert "daily_request_limit" in gpt120
    assert "daily_token_limit" in gpt120
    assert "requests_remaining" in gpt120

    # POST /api/v1/copilot/distill
    res_distill = client.post("/api/v1/copilot/distill")
    assert res_distill.status_code == 200
    distill_data = res_distill.json()
    assert distill_data["status"] == "success"
    assert "train_results" in distill_data
