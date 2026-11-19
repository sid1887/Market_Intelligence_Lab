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


def test_internal_sync_news_field_mapping_and_push(monkeypatch):
    """
    Verifies that NewsClient fields ('title', 'impact_direction', 'summary_bullets', 'article_url')
    are properly mapped in /api/v1/internal/sync and trigger push alerts for BSE filings and watchlist assets.
    """
    from unittest.mock import patch
    monkeypatch.setenv("INTERNAL_SYNC_TOKEN", "test-secret-token")

    test_payload = {
        "news_articles": [
            {
                "id": "bse_filing_test_1",
                "symbol": "INFY",
                "title": "Infosys Secures Major AI Contract with European Banking Consortium",
                "source": "BSE Filing",
                "published_at": "2026-11-18T10:00:00Z",
                "article_url": "https://bseindia.com/xml-data/corpfiling/test1.pdf",
                "summary_bullets": ["Won multi-year €350M AI transformation contract.", "Revenue accretion begins Q4 FY27."],
                "impact_direction": "BULLISH",
                "impact_horizon": "MEDIUM_TERM",
                "confidence_score": 0.95
            }
        ],
        "dispatch_push": True
    }

    with patch("src.api.routes_internal.broadcast_push") as mock_broadcast:
        mock_broadcast.return_value = {"sent": 1, "failed": 0, "total": 1}
        # Clear ledger for test key to allow dispatch
        with patch("src.api.routes_internal.is_alert_dispatched", return_value=False):
            res = client.post(
                "/api/v1/internal/sync",
                json=test_payload,
                headers={"X-Internal-Token": "test-secret-token"}
            )
            assert res.status_code == 200
            data = res.json()
            assert data["status"] == "synced"
            assert data["counts"]["news_articles"] >= 1
            assert data["counts"]["news_push_sent"] >= 1

            # Check that mock_broadcast was called with human-readable title and body
            mock_broadcast.assert_called()
            call_kwargs = mock_broadcast.call_args.kwargs
            assert "🟢 INFY · BSE Filing" in call_kwargs["title"]
            assert "Infosys Secures Major AI Contract" in call_kwargs["body"]
            assert "Price & Structural Velocity" not in call_kwargs["body"]


def test_catalyst_copy_formatting():
    """
    Verifies that catalyst anomaly alerts are formatted with actionable intelligence
    (emoji, clean move %, volume multiple, and top story/filing) rather than raw 200-SMA stats.
    """
    from src.tasks.catalyst_engine import CausalCatalystEngine

    engine = CausalCatalystEngine(auto_push=False)
    p1 = {
        "move_pct": 5.4,
        "rvol": 3.2,
        "volume": 2500000,
        "avg_vol_20d": 780000,
        "dist_52w_high_pct": -4.2,
        "dist_sma200_pct": 12.8,
        "round_level_desc": "Trading above ₹1,500 psychological level"
    }
    p2 = {
        "classification": "SYSTEMATIC_SURGE",
        "alpha_narrative": "IT sector advancing broadly",
        "advances": 8,
        "declines": 2
    }
    p3 = {
        "summary": "Won ₹420 Cr order from Indian Railways.",
        "events": ["Order Win ₹420 Cr"]
    }
    p4 = {
        "top_story": "Railways awards signal modernization contract.",
        "headlines": ["Railways awards signal modernization contract (ET)"]
    }

    synth = engine.synthesize_catalyst(
        symbol="TCS",
        company_name="Tata Consultancy Services Ltd.",
        sector="IT",
        p1=p1, p2=p2, p3=p3, p4=p4
    )

    assert "push_title" in synth
    assert "push_body" in synth
    assert "🚀 TCS +5.4% (3.2x Vol)" in synth["push_title"]
    assert "Railways awards signal modernization contract" in synth["push_body"]
    assert "Price & Structural Velocity" not in synth["push_body"]
    assert "200-SMA" not in synth["push_body"]


def test_clean_notification_headline():
    """Verifies that scraper suffixes, tickers and boilerplate are stripped."""
    from src.tasks.catalyst_engine import clean_notification_headline

    assert clean_notification_headline("Voltas (NSEI:VOLTAS) (Simply Wall St).") == "Voltas"
    assert clean_notification_headline("RVNL Share Price Today (scanx.trade)") == "RVNL"
    assert clean_notification_headline("MARUTI - Simply Wall St") == "MARUTI"
    assert "Simply Wall St" not in clean_notification_headline("🚀 TVSHMOTOR +8.5% (Simply Wall St)")


def test_run_intraday_scan_burst_capping(monkeypatch):
    """
    Verifies that when multiple anomalies occur, run_intraday_scan(max_push_alerts=2)
    sends at most 2 individual alerts + 1 consolidated digest.
    """
    from unittest.mock import patch, MagicMock
    from src.tasks.catalyst_engine import CausalCatalystEngine

    engine = CausalCatalystEngine(auto_push=True)
    engine.get_watchlist_and_priority_symbols = lambda: ["VOLTAS", "TVSHMOTOR", "TMPV", "RVNL", "PNB", "PAYTM", "MARUTI"]

    mock_cats = [
        {"symbol": "VOLTAS", "move_pct": 8.7, "rvol": 4.5, "causal_headline": "Surges on heavy volume", "causal_bullets": ["Volume surge"]},
        {"symbol": "TVSHMOTOR", "move_pct": 8.5, "rvol": 4.0, "causal_headline": "Auto sales breakout", "causal_bullets": ["Sales surge"]},
        {"symbol": "TMPV", "move_pct": 6.2, "rvol": 3.5, "causal_headline": "Strong institutional flow", "causal_bullets": ["Block trade"]},
        {"symbol": "RVNL", "move_pct": 3.3, "rvol": 2.8, "causal_headline": "Railway order inflow", "causal_bullets": ["Contract win"]},
        {"symbol": "PNB", "move_pct": 4.3, "rvol": 2.5, "causal_headline": "PSU bank momentum", "causal_bullets": ["Credit growth"]},
        {"symbol": "PAYTM", "move_pct": 5.1, "rvol": 2.2, "causal_headline": "Fintech turnaround", "causal_bullets": ["Operating profit"]},
        {"symbol": "MARUTI", "move_pct": 3.8, "rvol": 2.1, "causal_headline": "Export volumes up", "causal_bullets": ["Export surge"]},
    ]

    cat_map = {c["symbol"]: c for c in mock_cats}
    engine.investigate_symbol = MagicMock(side_effect=lambda sym, force=False, dispatch_push=None: cat_map.get(sym))

    with patch("src.tasks.catalyst_engine.broadcast_push") as mock_push:
        mock_push.return_value = {"sent": 1, "failed": 0, "total": 1}
        # Run scan with sleep mocked to 0 for fast test
        with patch("time.sleep", return_value=None):
            results = engine.run_intraday_scan(dispatch_push=True, max_push_alerts=2)

        assert len(results) == 7
        # At most 2 individual pushes + 1 digest push = 3 total calls
        assert mock_push.call_count == 3
        # First call is highest move * rvol: VOLTAS
        assert "VOLTAS" in mock_push.call_args_list[0].kwargs["title"]
        # Second call is TVSHMOTOR
        assert "TVSHMOTOR" in mock_push.call_args_list[1].kwargs["title"]
        # Third call is digest
        assert "More Market Movers" in mock_push.call_args_list[2].kwargs["title"]


def test_internal_sync_secret_header_and_env(monkeypatch):
    """Verifies that X-Internal-Sync-Secret header with MIL_INTERNAL_SYNC_SECRET is accepted."""
    monkeypatch.delenv("INTERNAL_SYNC_TOKEN", raising=False)
    monkeypatch.setenv("MIL_INTERNAL_SYNC_SECRET", "custom-secret-99")

    test_payload = {
        "news_articles": [],
        "catalysts": [],
        "dispatch_push": False
    }

    res = client.post(
        "/api/v1/internal/sync",
        json=test_payload,
        headers={"X-Internal-Sync-Secret": "custom-secret-99"}
    )
    assert res.status_code == 200
    assert res.json()["status"] == "synced"


