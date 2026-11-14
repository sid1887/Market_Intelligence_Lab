"""
Market Intelligence Lab — Native Web Push Dispatcher (Milestone PWA Push).

Manages VAPID key lifecycle, device push subscription persistence in SQLite,
and encrypted Web Push delivery via pywebpush with RFC 8292 compliance.
"""

import os
import re
import json
import base64
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

from py_vapid import Vapid
from pywebpush import webpush, WebPushException
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_pem_private_key, load_der_private_key
from cryptography.hazmat.primitives.asymmetric import ec

logger = logging.getLogger("notifications.web_push")

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "market_lab.db")
VAPID_FILE = os.path.join(DATA_DIR, "vapid.json")
VAPID_PEM_PATH = os.path.join(DATA_DIR, "vapid_private.pem")
DEFAULT_CLAIMS_EMAIL = "mailto:support@marketintelligencelab.com"

_CACHED_VAPID: Optional[Vapid] = None
_CACHED_KEYS: Optional[Dict[str, str]] = None


def _get_db() -> sqlite3.Connection:
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=25.0)
    conn.row_factory = sqlite3.Row
    return conn


def init_push_tables():
    """Initializes the push_subscriptions and push_dispatch_ledger tables in SQLite."""
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
        conn.execute("""
            CREATE TABLE IF NOT EXISTS push_dispatch_ledger (
                alert_key TEXT PRIMARY KEY,
                dispatched_at TEXT NOT NULL
            );
        """)
        conn.commit()


def is_alert_dispatched(alert_key: str) -> bool:
    """Checks if an alert key has already been dispatched via Web Push."""
    init_push_tables()
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT 1 FROM push_dispatch_ledger WHERE alert_key = ?", (alert_key,)).fetchone()
            return row is not None
    except Exception as e:
        logger.error(f"Error checking push_dispatch_ledger: {e}")
        return False


def record_dispatched_alert(alert_key: str):
    """Records an alert key in push_dispatch_ledger to prevent duplicate push notifications."""
    init_push_tables()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with _get_db() as conn:
            conn.execute("""
                INSERT OR IGNORE INTO push_dispatch_ledger (alert_key, dispatched_at)
                VALUES (?, ?)
            """, (alert_key, now_iso))
            conn.commit()
    except Exception as e:
        logger.error(f"Error recording alert in push_dispatch_ledger: {e}")


def load_vapid_instance(raw_input: Optional[str]) -> Optional[Vapid]:
    """
    Robust multi-format VAPID private key loader.
    Parses any valid format without throwing unhandled deserialization or ASN.1 errors:
    1. PEM with headers (-----BEGIN [EC ]PRIVATE KEY-----) containing \n, literal \\n, or spaces
    2. Base64 DER PKCS#8 or SEC1 binary bytes
    3. 32-byte raw private key scalar (base64 or base64url encoded)
    Returns a valid Vapid instance, or None if invalid/corrupt.
    """
    if not raw_input:
        return None
    s = raw_input.strip().strip('"').strip("'")
    s = s.replace("\\n", "\n")

    # 1. Direct PEM if BEGIN in string
    if "-----BEGIN" in s:
        header_match = re.search(r"-----BEGIN [A-Z0-9 ]+-----", s)
        footer_match = re.search(r"-----END [A-Z0-9 ]+-----", s)
        if header_match and footer_match:
            header = header_match.group(0)
            footer = footer_match.group(0)
            body = (
                s[header_match.end() : footer_match.start()]
                .strip()
                .replace(" ", "")
                .replace("\n", "")
                .replace("\r", "")
            )
            clean_pem = f"{header}\n{body}\n{footer}\n"
            try:
                return Vapid.from_pem(clean_pem.encode("utf-8"))
            except Exception as e:
                logger.debug(f"Failed loading parsed PEM: {e}")

    # 2. Try raw base64 / base64url decode
    clean_b64 = re.sub(r"[^A-Za-z0-9+/=_-]", "", s)
    if clean_b64:
        pad = "=" * ((4 - len(clean_b64) % 4) % 4)
        raw_bytes = None
        try:
            raw_bytes = base64.urlsafe_b64decode(clean_b64 + pad)
        except Exception:
            try:
                raw_bytes = base64.b64decode(clean_b64 + pad)
            except Exception:
                pass

        if raw_bytes:
            # 32-byte raw EC scalar
            if len(raw_bytes) == 32:
                try:
                    priv_num = int.from_bytes(raw_bytes, "big")
                    ec_key = ec.derive_private_key(priv_num, ec.SECP256R1())
                    return Vapid(ec_key)
                except Exception as e:
                    logger.debug(f"Failed deriving EC private key from 32-byte scalar: {e}")
            # DER bytes
            try:
                return Vapid(load_der_private_key(raw_bytes, password=None))
            except Exception as e:
                logger.debug(f"Failed loading DER private key: {e}")

    return None


def get_or_create_vapid_keys() -> Dict[str, str]:
    """
    Retrieves persistent VAPID keys from environment or data/vapid.json.
    Generates and persists a fresh EC P-256 keypair if none exist or if existing is corrupt.
    Guarantees in-memory caching and valid PEM persistence.
    """
    global _CACHED_VAPID, _CACHED_KEYS

    if _CACHED_KEYS is not None and _CACHED_VAPID is not None:
        return _CACHED_KEYS

    claims_email = os.getenv("VAPID_CLAIMS_EMAIL", DEFAULT_CLAIMS_EMAIL).strip()

    # 1. Check environment variables first (deterministic cloud deployments)
    env_pub = os.getenv("VAPID_PUBLIC_KEY")
    env_priv = os.getenv("VAPID_PRIVATE_KEY")
    if env_priv:
        v_obj = load_vapid_instance(env_priv)
        if v_obj is not None:
            clean_pem = v_obj.private_pem().decode("utf-8")
            raw_pub = v_obj.public_key.public_bytes(
                encoding=serialization.Encoding.X962,
                format=serialization.PublicFormat.UncompressedPoint
            )
            derived_pub_b64 = base64.urlsafe_b64encode(raw_pub).rstrip(b"=").decode("utf-8")
            pub_key = env_pub.strip().strip('"').strip("'") if env_pub else derived_pub_b64

            # Ensure valid PEM on disk
            try:
                os.makedirs(DATA_DIR, exist_ok=True)
                with open(VAPID_PEM_PATH, "w", encoding="utf-8") as pf:
                    pf.write(clean_pem)
            except Exception as e:
                logger.warning(f"Could not cache VAPID_PEM_PATH: {e}")

            _CACHED_VAPID = v_obj
            _CACHED_KEYS = {
                "public_key": pub_key,
                "private_pem": clean_pem,
                "claims_email": claims_email,
            }
            logger.info("Loaded and verified VAPID keys from environment.")
            return _CACHED_KEYS
        else:
            logger.warning("VAPID_PRIVATE_KEY from environment could not be parsed. Checking persistent store...")

    # 2. Check local data/vapid.json
    if os.path.exists(VAPID_FILE):
        try:
            with open(VAPID_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if data.get("private_pem"):
                    v_obj = load_vapid_instance(data["private_pem"])
                    if v_obj is not None:
                        clean_pem = v_obj.private_pem().decode("utf-8")
                        if not os.path.exists(VAPID_PEM_PATH):
                            with open(VAPID_PEM_PATH, "w", encoding="utf-8") as pf:
                                pf.write(clean_pem)
                        _CACHED_VAPID = v_obj
                        _CACHED_KEYS = {
                            "public_key": data.get("public_key") or base64.urlsafe_b64encode(
                                v_obj.public_key.public_bytes(
                                    encoding=serialization.Encoding.X962,
                                    format=serialization.PublicFormat.UncompressedPoint
                                )
                            ).rstrip(b"=").decode("utf-8"),
                            "private_pem": clean_pem,
                            "claims_email": data.get("claims_email", DEFAULT_CLAIMS_EMAIL),
                        }
                        return _CACHED_KEYS
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
        "claims_email": claims_email,
    }

    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(VAPID_FILE, "w", encoding="utf-8") as f:
            json.dump(keys, f, indent=2)
        with open(VAPID_PEM_PATH, "w", encoding="utf-8") as pf:
            pf.write(priv_pem)
    except Exception as e:
        logger.warning(f"Could not persist fresh VAPID keys: {e}")

    _CACHED_VAPID = vapid
    _CACHED_KEYS = keys
    return keys


def get_vapid_instance() -> Vapid:
    """Returns a verified in-memory Vapid instance. Initializes keys if not cached."""
    global _CACHED_VAPID
    if _CACHED_VAPID is not None:
        return _CACHED_VAPID
    get_or_create_vapid_keys()
    return _CACHED_VAPID


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
    badge: str = "/icons/badge-96x96.png",
    icon: str = "/icons/icon-192x192.png",
    error_collector: Optional[List[str]] = None,
) -> bool:
    """
    Delivers an encrypted Web Push message to a single subscription.
    Handles automatic cleanup if endpoint has expired (HTTP 404/410).
    """
    keys = get_or_create_vapid_keys()
    vapid_instance = get_vapid_instance()
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
        "tag": tag or f"mil-push-{int(datetime.now(timezone.utc).timestamp() * 1000)}",
        "icon": icon,
        "badge": badge,
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000)
    }

    claims = {
        "sub": keys.get("claims_email", DEFAULT_CLAIMS_EMAIL),
    }

    try:
        webpush(
            subscription_info=sub_info,
            data=json.dumps(payload),
            vapid_private_key=vapid_instance,
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
    tag: Optional[str] = None,
    badge: str = "/icons/badge-96x96.png",
    icon: str = "/icons/icon-192x192.png",
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
            badge=badge,
            icon=icon,
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
