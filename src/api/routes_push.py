"""
Market Intelligence Lab — Native Web Push & Causal Catalyst API Routes.

Exposes endpoints for:
- VAPID public key retrieval
- Mobile PWA push subscription persistence
- Instant test push dispatch
- Live Causal Catalysts market feed & manual anomaly investigation
"""

import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Request, Body
from pydantic import BaseModel, Field

from src.notifications.web_push import (
    get_vapid_public_key,
    save_subscription,
    get_all_subscriptions,
    broadcast_push,
)
from src.tasks.catalyst_engine import catalyst_engine, CausalCatalystEngine

logger = logging.getLogger("api.routes_push")
router = APIRouter(tags=["Push Notifications & Causal Catalysts"])


class PushSubscriptionKeys(BaseModel):
    p256dh: str
    auth: str


class PushSubscriptionRequest(BaseModel):
    endpoint: str
    keys: PushSubscriptionKeys
    user_agent: Optional[str] = None


class PushTestRequest(BaseModel):
    title: Optional[str] = "MIL Quant · Push Verification"
    body: Optional[str] = "Real-time causal catalyst notifications active. Institutional market radar connected."
    url: Optional[str] = "/"


class CatalystInvestigateRequest(BaseModel):
    symbol: str
    force: bool = True


@router.get("/push/vapid-public-key")
def get_vapid_key():
    """Returns the base64url-encoded VAPID public key for browser pushManager registration."""
    try:
        key = get_vapid_public_key()
        return {"public_key": key}
    except Exception as e:
        logger.error(f"Error retrieving VAPID public key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


MAX_PUSH_SUBSCRIPTIONS = 100


@router.post("/push/subscribe")
def register_push_subscription(payload: PushSubscriptionRequest, request: Request):
    """Registers or updates a browser/mobile Web Push subscription endpoint."""
    all_subs = get_all_subscriptions()
    existing_endpoints = {s["endpoint"] for s in all_subs}
    if payload.endpoint not in existing_endpoints and len(all_subs) >= MAX_PUSH_SUBSCRIPTIONS:
        raise HTTPException(
            status_code=429,
            detail="Maximum push subscriptions limit reached on server."
        )

    ua = payload.user_agent or request.headers.get("user-agent", "Unknown")
    success = save_subscription(
        endpoint=payload.endpoint,
        p256dh=payload.keys.p256dh,
        auth=payload.keys.auth,
        user_agent=ua
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save push subscription")

    return {
        "status": "subscribed",
        "endpoint": payload.endpoint[:40] + "...",
        "total_active_subscriptions": len(get_all_subscriptions())
    }


@router.post("/push/test")
def test_push_dispatch(payload: Optional[PushTestRequest] = None):
    """Sends an immediate test push notification to all subscribed mobile and desktop clients."""
    req = payload or PushTestRequest()
    result = broadcast_push(
        title=req.title or "MIL Quant · Push Verification",
        body=req.body or "Mobile Web Push verified! Real-time causal market intelligence active.",
        url=req.url or "/",
        tag="test-push-verification"
    )
    if result["total"] == 0:
        return {
            "status": "warning",
            "message": "No active push subscriptions registered on server. Tap 'Enable Mobile Push Notifications' to register this device.",
            "result": result
        }
    if result["sent"] == 0:
        err_msg = "; ".join(result.get("errors", [])) or "Push delivery failed for all registered endpoints."
        return {
            "status": "error",
            "message": f"Push delivery failed: {err_msg}",
            "result": result
        }
    return {
        "status": "dispatched",
        "message": f"Successfully delivered test alert to {result['sent']} of {result['total']} device(s).",
        "result": result
    }


@router.get("/catalysts/live")
def get_live_catalysts(limit: int = 20):
    """Fetches real-time institutional causal catalyst events from SQLite."""
    try:
        data = CausalCatalystEngine.get_live_catalysts(limit=limit)
        return {
            "count": len(data),
            "catalysts": data
        }
    except Exception as e:
        logger.error(f"Error fetching live catalysts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/catalysts/symbol/{symbol}")
def get_symbol_catalysts(symbol: str, limit: int = 5, fallback: bool = True):
    """
    Fetches the latest institutional causal catalysts for a specific equity symbol.
    If none exists in the database and fallback is true, checks for active price anomalies.
    """
    sym = symbol.strip().upper()
    try:
        data = CausalCatalystEngine.get_live_catalysts(limit=limit, symbol=sym)
        if data:
            return {
                "status": "ok",
                "symbol": sym,
                "count": len(data),
                "catalysts": data,
                "latest": data[0]
            }

        if fallback:
            # On-demand lightweight check without spamming web push
            res = catalyst_engine.investigate_symbol(sym, force=False, dispatch_push=False)
            if res:
                return {
                    "status": "synthesized",
                    "symbol": sym,
                    "count": 1,
                    "catalysts": [res],
                    "latest": res
                }

        return {
            "status": "not_found",
            "symbol": sym,
            "count": 0,
            "catalysts": [],
            "latest": None
        }
    except Exception as e:
        logger.error(f"Error fetching catalysts for symbol {sym}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/catalysts/investigate")
def investigate_catalyst(payload: CatalystInvestigateRequest):
    """
    Triggers an on-demand 4-pillar causal investigation on a symbol.
    Persists to SQLite and dispatches a Web Push alert if an anomaly is confirmed.
    """
    sym = payload.symbol.strip().upper()
    try:
        res = catalyst_engine.investigate_symbol(sym, force=payload.force)
        if not res:
            return {
                "symbol": sym,
                "status": "no_anomaly_detected",
                "message": f"{sym} did not breach the >= 3.0% move or >= 2.5x RVOL threshold."
            }
        return {
            "status": "catalyst_synthesized",
            "catalyst": res
        }
    except Exception as e:
        logger.error(f"Error investigating {sym}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/catalysts/scan")
def trigger_catalyst_scan():
    """Scans all watchlist and priority equities for intraday causal anomalies."""
    try:
        results = catalyst_engine.run_intraday_scan()
        return {
            "status": "scan_complete",
            "anomalies_detected": len(results),
            "catalysts": results
        }
    except Exception as e:
        logger.error(f"Error during catalyst scan: {e}")
        raise HTTPException(status_code=500, detail=str(e))
