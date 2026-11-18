"""
Unit and integration tests for Dual-Channel Telegram Bot & Pocket Terminal (@sidraj_1887).
Verifies security pairing, command router, outbound push alerts, and FastAPI webhook handling.
"""

import pytest
import sqlite3
from unittest.mock import patch, MagicMock, AsyncMock

from fastapi.testclient import TestClient
from src.api.main import app
from src.notifications.telegram_bot import (
    init_telegram_tables,
    get_telegram_config,
    set_telegram_config,
    is_user_authorized,
    pair_chat_id,
    send_telegram_alert,
    send_telegram_message,
)
from src.notifications.web_push import broadcast_push


@pytest.fixture(autouse=True)
def setup_telegram_test_env(monkeypatch):
    """Sets standard testing environment variables."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST_TELEGRAM_TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")
    monkeypatch.setenv("INTERNAL_SYNC_TOKEN", "test-token")
    init_telegram_tables()


def test_telegram_config_table_crud():
    """Verifies SQLite telegram_config key-value store."""
    set_telegram_config("test_key", "test_val")
    assert get_telegram_config("test_key") == "test_val"


def test_telegram_authorization_security(monkeypatch):
    """Verifies that only @sidraj_1887 (or matching chat_id) is authorized."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")

    # Valid username
    assert is_user_authorized("sidraj_1887", 987654321) is True
    assert is_user_authorized("@sidraj_1887", 111111111) is True
    assert is_user_authorized("SIDRAJ_1887", 222222222) is True

    # Valid chat_id even without username
    assert is_user_authorized(None, 987654321) is True
    assert is_user_authorized("", "987654321") is True

    # Unauthorized username & chat_id
    assert is_user_authorized("attacker_hacker", 444444444) is False
    assert is_user_authorized("random_user", None) is False


def test_telegram_pairing_handshake(monkeypatch):
    """Verifies the /start pairing handshake logic."""
    monkeypatch.setenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887")
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)

    # Unauthorized pairing attempt must fail
    assert pair_chat_id("intruder", 555555) is False

    # Authorized user pairing must succeed and persist to SQLite
    assert pair_chat_id("sidraj_1887", 888888888) is True
    assert get_telegram_config("chat_id") == "888888888"


def test_telegram_outbound_alert_formatting():
    """Verifies that send_telegram_alert formats HTML correctly and includes chart links."""
    with patch("src.notifications.telegram_bot.send_telegram_message") as mock_send:
        mock_send.return_value = True

        # Alert with stock symbol
        success = send_telegram_alert(
            title="⚡ RELIANCE Intraday Anomaly",
            body="RVOL 3.4x spike with bullish momentum breakout.",
            url="/stocks/RELIANCE"
        )
        assert success is True
        assert mock_send.called
        msg_text = mock_send.call_args[0][0]
        assert "<b>⚡ RELIANCE Intraday Anomaly</b>" in msg_text
        assert "RVOL 3.4x spike" in msg_text
        assert "https://market-intelligence-lab-vert.vercel.app/stocks/RELIANCE" in msg_text


def test_broadcast_push_triggers_telegram_alert_when_subs_empty(monkeypatch):
    """Verifies Telegram alert is dispatched even if browser Web Push has 0 subscriptions."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "123456:TEST_TOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "987654321")

    with patch("src.notifications.web_push.get_all_subscriptions", return_value=[]), \
         patch("src.notifications.web_push.send_telegram_alert") as mock_tg_alert:
        mock_tg_alert.return_value = True

        result = broadcast_push(
            title="⚡ BREAKING: TATA MOTORS Anomaly",
            body="Strong volume expansion detected.",
            url="/stocks/TATAMOTORS"
        )
        # Even though web push subscriptions were 0, telegram alert was dispatched!
        assert mock_tg_alert.called
        assert mock_tg_alert.call_args.kwargs.get("title") == "⚡ BREAKING: TATA MOTORS Anomaly"
        assert result["total"] == 0
        assert result["sent"] == 0


def test_telegram_api_routes_status():
    """Verifies GET /api/v1/telegram/status returns healthy telemetry."""
    client = TestClient(app)
    response = client.get("/api/v1/telegram/status")
    assert response.status_code == 200
    data = response.json()
    assert data["bot_token_configured"] is True
    assert data["allowed_username"] == "sidraj_1887"
    assert "/api/v1/telegram/webhook" in data["webhook_url"]


def test_telegram_webhook_unauthorized_rejection():
    """Verifies unauthorized updates sent to webhook are flagged as unauthorized."""
    client = TestClient(app)
    fake_update = {
        "update_id": 1001,
        "message": {
            "message_id": 1,
            "from": {"id": 99999, "username": "bad_actor", "first_name": "Bad"},
            "chat": {"id": 99999, "type": "private"},
            "text": "/forecast RELIANCE"
        }
    }
    with patch("src.api.routes_telegram.send_telegram_message") as mock_msg:
        response = client.post("/api/v1/telegram/webhook", json=fake_update)
        assert response.status_code == 200
        assert response.json()["status"] == "unauthorized"
        assert mock_msg.called


def test_telegram_webhook_secret_mismatch(monkeypatch):
    """Verifies webhook rejects requests with 403 when secret token does not match."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", "super-secret-123")
    client = TestClient(app)
    response = client.post(
        "/api/v1/telegram/webhook",
        json={"update_id": 1},
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"}
    )
    assert response.status_code == 403


def test_telegram_webhook_authorized_start_pairing():
    """Verifies that /start from @sidraj_1887 triggers chat_id pairing."""
    client = TestClient(app)
    fake_update = {
        "update_id": 1002,
        "message": {
            "message_id": 2,
            "from": {"id": 777666555, "username": "sidraj_1887", "first_name": "Siddharth"},
            "chat": {"id": 777666555, "type": "private"},
            "text": "/start"
        }
    }
    with patch("src.api.routes_telegram.send_telegram_message_async", new_callable=AsyncMock) as mock_send:
        response = client.post("/api/v1/telegram/webhook", json=fake_update)
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["action"] == "paired"
        assert get_telegram_config("chat_id") == "777666555"


def test_telegram_webhook_command_dispatch():
    """Verifies background command dispatch for /forecast, /scan, /top, and free-text."""
    client = TestClient(app)
    
    commands = [
        "/forecast RELIANCE",
        "/scan",
        "/watchlist",
        "/top",
        "What is the outlook for TCS?"
    ]

    for idx, cmd in enumerate(commands, start=10):
        update = {
            "update_id": 2000 + idx,
            "message": {
                "message_id": idx,
                "from": {"id": 777666555, "username": "sidraj_1887", "first_name": "Siddharth"},
                "chat": {"id": 777666555, "type": "private"},
                "text": cmd
            }
        }
        with patch("src.api.routes_telegram.send_telegram_message_async", new_callable=AsyncMock) as mock_send:
            response = client.post("/api/v1/telegram/webhook", json=update)
            assert response.status_code == 200
            assert response.json()["status"] == "ok"
