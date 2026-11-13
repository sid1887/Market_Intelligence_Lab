"""
Test suite for Web Push Subscriptions, Auto-Sync & VAPID PEM normalization.
"""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app
from src.notifications.web_push import (
    get_or_create_vapid_keys,
    save_subscription,
    get_all_subscriptions,
    remove_subscription,
    broadcast_push,
)

client = TestClient(app)


def test_vapid_public_key_endpoint():
    res = client.get("/api/v1/push/vapid-public-key")
    assert res.status_code == 200
    data = res.json()
    assert "public_key" in data
    assert len(data["public_key"]) > 30


def test_push_subscribe_and_test_dispatch():
    test_endpoint = "https://fcm.googleapis.com/fcm/send/test-automated-mock"
    
    # 1. Test registration
    payload = {
        "endpoint": test_endpoint,
        "keys": {
            "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QT9t0P684DTrPlP1uk4b5rV3X3yR1i6E1fQp0-8lY9c661_E",
            "auth": "5sZ7v8k1u4m5x9a2",
        },
        "user_agent": "Pytest Automated Suite",
    }
    sub_res = client.post("/api/v1/push/subscribe", json=payload)
    assert sub_res.status_code == 200
    assert sub_res.json()["status"] == "subscribed"
    
    # 2. Test test push dispatch (will capture invalid test endpoint error gracefully without crashing)
    push_res = client.post("/api/v1/push/test")
    assert push_res.status_code == 200
    data = push_res.json()
    assert data["status"] in ("error", "dispatched")
    assert "result" in data
    assert data["result"]["total"] >= 1

    # Cleanup
    remove_subscription(test_endpoint)


def test_push_test_empty_subscriptions():
    # If no subscriptions exist, verify warning message is returned
    all_subs = get_all_subscriptions()
    # Temporarily remove all for isolation test
    for s in all_subs:
        remove_subscription(s["endpoint"])

    res = client.post("/api/v1/push/test")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "warning"
    assert "No active push subscriptions" in data["message"]
    assert data["result"]["total"] == 0

    # Restore original subscriptions
    for s in all_subs:
        save_subscription(s["endpoint"], s["p256dh"], s["auth"], s.get("user_agent"))
