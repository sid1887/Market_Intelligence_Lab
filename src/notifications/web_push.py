"""
Market Intelligence Lab — Native Web Push Dispatcher (Milestone PWA Push).

Manages VAPID key lifecycle, device push subscription persistence in SQLite,
and encrypted Web Push delivery via pywebpush with RFC 8292 compliance.
"""

import os
import json
import base64
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from py_vapid import Vapid
from pywebpush import webpush, WebPushException
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger("notifications.web_push")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "market_lab.db")
VAPID_FILE = os.path.join(DATA_DIR, "vapid.json")
VAPID_PEM_PATH = os.path.join(DATA_DIR, "vapid_private.pem")
DEFAULT_CLAIMS_EMAIL = "mailto:support@marketintelligencelab.com"


def _get_db() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_push_tables():
    """Initializes the push_subscriptions table in SQLite."""
    with _get_db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS push_subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                endpoint TEXT UNIQUE NOT NULL,
                p256dh TEXT NOT NULL,
                auth TEXT NOT NULL,
                user_agent TEXT,
                created_at TEXT NOT NULL
            );
        """)
        conn.commit()


def get_or_create_vapid_keys() -> Dict[str, str]:
    """
    Retrieves persistent VAPID keys from environment or data/vapid.json.
    Generates and persists a fresh EC P-256 keypair if none exist.
    """
    # 1. Check environment variables first (deterministic cloud deployments)
    env_pub = os.getenv("VAPID_PUBLIC_KEY")
    env_priv = os.getenv("VAPID_PRIVATE_KEY")
    if env_pub and env_priv:
        cleaned_pub = env_pub.strip().strip('"').strip("'")
        raw_priv = env_priv.strip().strip('"').strip("'")
        cleaned_priv = raw_priv.replace("\\n", "\n")
        # Ensure newline at end of PEM
        if not cleaned_priv.endswith("\n"):
            cleaned_priv += "\n"
        claims_email = os.getenv("VAPID_CLAIMS_EMAIL", DEFAULT_CLAIMS_EMAIL).strip()

        # Cache to VAPID_PEM_PATH for pywebpush / py_vapid file deserialization
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(VAPID_PEM_PATH, "w", encoding="utf-8") as pf:
                pf.write(cleaned_priv)
        except Exception as e:
            logger.warning(f"Could not write VAPID_PEM_PATH from environment: {e}")

        return {
            "public_key": cleaned_pub,
            "private_pem": cleaned_priv,
            "claims_email": claims_email,
        }

    # 2. Check local data/vapid.json
    if os.path.exists(VAPID_FILE):
        try:
            with open(VAPID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("public_key") and data.get("private_pem"):
                    if not os.path.exists(VAPID_PEM_PATH):
                        with open(VAPID_PEM_PATH, "w", encoding="utf-8") as pf:
                            pf.write(data["private_pem"])
                    return data
        except Exception as e:
            logger.warning(f"Error reading existing vapid.json: {e}")

    # 3. Generate fresh pair
    logger.info("Generating new persistent VAPID EC P-256 keypair for Web Push...")
    vapid = Vapid()
    vapid.generate_keys()

    priv_pem = vapid.private_pem().decode("utf-8")

    raw_pub = vapid.public_key.public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint
    )
    pub_b64 = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode("utf-8")

    keys = {
        "public_key": pub_b64,
        "private_pem": priv_pem,
        "claims_email": DEFAULT_CLAIMS_EMAIL,
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(VAPID_FILE, "w", encoding="utf-8") as f:
        json.dump(keys, f, indent=2)

    with open(VAPID_PEM_PATH, "w", encoding="utf-8") as pf:
        pf.write(priv_pem)

    # Also append to root .env if present or create it
    env_path = os.path.join(ROOT_DIR, ".env")
    try:
        env_lines = []
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as ef:
                env_lines = [l for l in ef.readlines() if not l.startswith("VAPID_")]
        env_lines.append(f"VAPID_PUBLIC_KEY={pub_b64}\n")
        env_lines.append(f"VAPID_CLAIMS_EMAIL={DEFAULT_CLAIMS_EMAIL}\n")
        with open(env_path, "w", encoding="utf-8") as ef:
            ef.writelines(env_lines)
    except Exception as e:
        logger.warning(f"Could not update .env with VAPID keys: {e}")

    return keys


def get_vapid_public_key() -> str:
    """Returns the base64url-encoded uncompressed public key for browser pushManager subscription."""
    keys = get_or_create_vapid_keys()
    return keys["public_key"]


def save_subscription(endpoint: str, p256dh: str, auth: str, user_agent: Optional[str] = None) -> bool:
    """Saves or updates a device push subscription."""
    init_push_tables()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with _get_db() as conn:
            conn.execute("""
                INSERT INTO push_subscriptions (endpoint, p256dh, auth, user_agent, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(endpoint) DO UPDATE SET
                    p256dh=excluded.p256dh,
                    auth=excluded.auth,
                    user_agent=excluded.user_agent,
                    created_at=excluded.created_at;
            """, (endpoint, p256dh, auth, user_agent, now_iso))
            conn.commit()
        logger.info(f"Successfully registered push subscription for endpoint: {endpoint[:32]}...")
        return True
    except Exception as e:
        logger.error(f"Failed to persist push subscription: {e}")
        return False


def get_all_subscriptions() -> List[Dict[str, Any]]:
    """Retrieves all active push subscriptions."""
    init_push_tables()
    try:
        with _get_db() as conn:
            rows = conn.execute("SELECT id, endpoint, p256dh, auth, user_agent, created_at FROM push_subscriptions").fetchall()
            return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error querying subscriptions: {e}")
        return []


def remove_subscription(endpoint: str):
    """Deletes an invalid or expired push subscription."""
    try:
        with _get_db() as conn:
            conn.execute("DELETE FROM push_subscriptions WHERE endpoint = ?", (endpoint,))
            conn.commit()
        logger.info(f"Removed dead subscription endpoint: {endpoint[:32]}...")
    except Exception as e:
        logger.error(f"Failed to remove subscription: {e}")


def send_push_notification(
    subscription: Dict[str, Any],
    title: str,
    body: str,
    url: str = "/",
    tag: Optional[str] = None,
    badge: str = "/icons/icon-192x192.png",
    icon: str = "/icons/icon-192x192.png",
    error_collector: Optional[List[str]] = None,
) -> bool:
    """
    Delivers an encrypted Web Push message to a single subscription.
    Handles automatic cleanup if endpoint has expired (HTTP 404/410).
    """
    keys = get_or_create_vapid_keys()
    sub_info = {
        "endpoint": subscription["endpoint"],
        "keys": {
            "p256dh": subscription["p256dh"],
            "auth": subscription["auth"],
        }
    }

    payload = {
        "title": title,
        "body": body,
        "url": url,
        "tag": tag or f"mil-push-{int(datetime.now().timestamp())}",
        "icon": icon,
        "badge": badge,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
    }

    claims = {
        "sub": keys.get("claims_email", DEFAULT_CLAIMS_EMAIL),
    }

    private_key_param = VAPID_PEM_PATH if os.path.exists(VAPID_PEM_PATH) else keys["private_pem"]

    try:
        webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=private_key_param,
            vapid_claims=claims,
            ttl=86400  # 24 hours
        )
        logger.info(f"Web Push delivered successfully to {subscription['endpoint'][:30]}...")
        return True
    except WebPushException as ex:
        status_code = getattr(ex.response, "status_code", None) if hasattr(ex, "response") else None
        err_msg = f"WebPushException (HTTP {status_code}): {ex}"
        logger.warning(f"{err_msg} on {subscription['endpoint'][:30]}")
        if error_collector is not None:
            error_collector.append(err_msg)
        if status_code in (404, 410):
            logger.info("Endpoint is gone or unregistered. Cleaning up.")
            remove_subscription(subscription["endpoint"])
        return False
    except Exception as ex:
        err_msg = f"Unexpected push error: {ex}"
        logger.error(err_msg)
        if error_collector is not None:
            error_collector.append(err_msg)
        return False


def broadcast_push(
    title: str,
    body: str,
    url: str = "/",
    tag: Optional[str] = None
) -> Dict[str, Any]:
    """
    Broadcasts a push notification to all subscribed mobile/desktop clients.
    Returns delivery statistics and any encountered errors.
    """
    subs = get_all_subscriptions()
    if not subs:
        logger.info("No active push subscriptions registered.")
        return {"total": 0, "sent": 0, "failed": 0, "errors": []}

    sent_count = 0
    fail_count = 0
    errors: List[str] = []

    for sub in subs:
        err_list: List[str] = []
        ok = send_push_notification(
            subscription=sub,
            title=title,
            body=body,
            url=url,
            tag=tag,
            error_collector=err_list,
        )
        if ok:
            sent_count += 1
        else:
            fail_count += 1
            for e in err_list:
                if e not in errors:
                    errors.append(e)

    return {"total": len(subs), "sent": sent_count, "failed": fail_count, "errors": errors}
