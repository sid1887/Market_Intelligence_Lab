"""
Market Intelligence Lab — Dual-Channel Telegram Bot & Interactive Pocket Terminal.
Supports 24/7 outbound alert broadcasting and an interactive pocket terminal for @sidraj_1887.
Uses lightweight httpx client to guarantee Render free-tier container memory remains < 200MB.
"""

import os
import re
import html
import time
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List

import httpx

# Silence noisy HTTP client loggers to prevent leaking Telegram bot tokens in request URLs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("notifications.telegram_bot")

def mask_token(token: Optional[str]) -> str:
    """Masks a Telegram bot token for safe logging."""
    if not token:
        return "<not-set>"
    if len(token) <= 8:
        return "***"
    return f"{token[:4]}...{token[-4:]}"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(ROOT_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "market_lab.db")

from src.storage.database import DatabaseManager

TELEGRAM_API_BASE = "https://api.telegram.org"
TELEGRAM_ALLOWED_USERNAME = os.getenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887").strip().lower().lstrip("@")
WEB_BASE_URL = (os.getenv("NEXT_PUBLIC_APP_URL") or os.getenv("WEB_BASE_URL") or "https://market-intelligence-lab-vert.vercel.app").rstrip("/")

_last_send_time: float = 0.0


def _get_db():
    os.makedirs(DATA_DIR, exist_ok=True)
    return DatabaseManager(DB_PATH).get_connection()


def init_telegram_tables():
    """Initializes the telegram_config table in SQLite."""
    try:
        with _get_db() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS telegram_config (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
            conn.commit()
    except Exception as e:
        logger.error(f"Error initializing telegram_config table: {e}")


def get_telegram_config(key: str) -> Optional[str]:
    """Retrieves a configuration value from telegram_config."""
    init_telegram_tables()
    try:
        with _get_db() as conn:
            row = conn.execute("SELECT value FROM telegram_config WHERE key = ?", (key,)).fetchone()
            return row["value"] if row else None
    except Exception as e:
        logger.error(f"Error reading telegram_config for key '{key}': {e}")
        return None


def set_telegram_config(key: str, value: str):
    """Sets a configuration value in telegram_config."""
    init_telegram_tables()
    now_iso = datetime.now(timezone.utc).isoformat()
    try:
        with _get_db() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO telegram_config (key, value, updated_at)
                VALUES (?, ?, ?)
            """, (key, str(value), now_iso))
            conn.commit()
    except Exception as e:
        logger.error(f"Error writing telegram_config for key '{key}': {e}")


def get_bot_token() -> Optional[str]:
    """Returns the configured Telegram Bot Token."""
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip() or get_telegram_config("bot_token")


def get_authorized_chat_id() -> Optional[str]:
    """Returns the authorized numeric chat_id from env or SQLite telegram_config."""
    env_chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if env_chat_id:
        return env_chat_id
    return get_telegram_config("chat_id")


def is_user_authorized(username: Optional[str], chat_id: Optional[int | str]) -> bool:
    """Verifies that an incoming update is from the authorized user (@sidraj_1887)."""
    allowed_user = os.getenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887").strip().lower().lstrip("@")
    if username and username.strip().lower().lstrip("@") == allowed_user:
        return True
    
    stored_chat_id = get_authorized_chat_id()
    if stored_chat_id and chat_id and str(chat_id).strip() == str(stored_chat_id).strip():
        return True

    return False


def pair_chat_id(username: str, chat_id: int | str) -> bool:
    """Pairs and stores the numeric chat_id when @sidraj_1887 initiates /start."""
    clean_user = username.strip().lower().lstrip("@")
    allowed_user = os.getenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887").strip().lower().lstrip("@")
    if clean_user != allowed_user:
        logger.warning(f"[TELEGRAM] Unauthorized pairing attempt from @{username} (chat_id={chat_id}) rejected.")
        return False

    chat_id_str = str(chat_id).strip()
    set_telegram_config("chat_id", chat_id_str)
    set_telegram_config("username", clean_user)
    logger.info(f"[TELEGRAM] Successfully paired chat_id={chat_id_str} for @{clean_user}")
    return True


def _pace_send():
    """Enforces a 1.1s inter-message gap to prevent hitting Telegram rate limits."""
    global _last_send_time
    now = time.time()
    elapsed = now - _last_send_time
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    _last_send_time = time.time()


def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True
) -> bool:
    """
    Synchronous Telegram message dispatch using httpx.
    Non-blocking, exception-safe. Returns True on success, False otherwise.
    """
    token = get_bot_token()
    target_chat = chat_id or get_authorized_chat_id()
    if not token or not target_chat:
        return False

    _pace_send()
    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text[:4000],  # Telegram message length limit
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            if resp.status_code == 200:
                try:
                    from src.storage.database import record_external_api_metric
                    record_external_api_metric("telegram", "sendMessage", success=True, units=1)
                except Exception:
                    pass
                return True
            is_429 = (resp.status_code == 429)
            try:
                from src.storage.database import record_external_api_metric
                record_external_api_metric(
                    "telegram", "sendMessage", success=False, rate_limited=is_429,
                    units=1, error_msg=f"HTTP {resp.status_code}"
                )
            except Exception:
                pass
            logger.warning(f"[TELEGRAM] Send failed with HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        try:
            from src.storage.database import record_external_api_metric
            record_external_api_metric("telegram", "sendMessage", success=False, units=1, error_msg=str(e)[:100])
        except Exception:
            pass
        logger.warning(f"[TELEGRAM] Outbound dispatch error: {e}")
        return False


async def send_telegram_message_async(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
    disable_web_page_preview: bool = True
) -> bool:
    """
    Asynchronous Telegram message dispatch using httpx.AsyncClient.
    """
    token = get_bot_token()
    target_chat = chat_id or get_authorized_chat_id()
    if not token or not target_chat:
        return False

    url = f"{TELEGRAM_API_BASE}/bot{token}/sendMessage"
    payload = {
        "chat_id": target_chat,
        "text": text[:4000],
        "parse_mode": parse_mode,
        "disable_web_page_preview": disable_web_page_preview,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                try:
                    from src.storage.database import record_external_api_metric
                    record_external_api_metric("telegram", "sendMessage", success=True, units=1)
                except Exception:
                    pass
                return True
            is_429 = (resp.status_code == 429)
            try:
                from src.storage.database import record_external_api_metric
                record_external_api_metric(
                    "telegram", "sendMessage", success=False, rate_limited=is_429,
                    units=1, error_msg=f"HTTP {resp.status_code}"
                )
            except Exception:
                pass
            logger.warning(f"[TELEGRAM] Async send failed HTTP {resp.status_code}: {resp.text}")
            return False
    except Exception as e:
        try:
            from src.storage.database import record_external_api_metric
            record_external_api_metric("telegram", "sendMessage", success=False, units=1, error_msg=str(e)[:100])
        except Exception:
            pass
        logger.warning(f"[TELEGRAM] Async dispatch error: {e}")
        return False


def send_telegram_alert(title: str, body: str, url: str = "/") -> bool:
    """
    Formats a high-impact market alert into clean Telegram HTML and dispatches it.
    Non-blocking, exception-safe. Returns True on success.
    """
    token = get_bot_token()
    if not token:
        return False

    # Extract symbol if present in title (ignore common acronyms and pure digits)
    _STOP_TOKENS = {"BSE", "NSE", "MIL", "RVOL", "SMA", "FY", "LIVE", "ALERT", "TOP", "HIGH", "LOW", "NEWS", "SURGE", "DROP", "NIFTY", "SENSEX", "SEBI", "RBI", "IPO", "ETF", "PAT", "EPS", "ROE", "PE", "Q1", "Q2", "Q3", "Q4"}
    sym_match = re.search(r"\b([A-Z][A-Z0-9-]{1,11})\b", title)
    sym = sym_match.group(1) if sym_match else ""
    
    clean_title = html.escape(title.strip())
    clean_body = html.escape(body.strip())
    
    # Target URL on production frontend
    if url.startswith("http"):
        full_url = url
    elif sym and sym not in _STOP_TOKENS:
        full_url = f"{WEB_BASE_URL}/stocks/{sym}"
    else:
        clean_path = url.lstrip("/")
        full_url = f"{WEB_BASE_URL}/{clean_path}" if clean_path else WEB_BASE_URL

    msg_html = (
        f"<b>{clean_title}</b>\n\n"
        f"{clean_body}\n\n"
        f"🔗 <a href=\"{full_url}\">Open Terminal &amp; Chart</a>"
    )

    return send_telegram_message(msg_html)


async def register_telegram_webhook(webhook_url: Optional[str] = None) -> bool:
    """
    Registers the Telegram bot webhook with Telegram API.
    """
    token = get_bot_token()
    if not token:
        return False

    url = webhook_url or f"https://mil-quant-backend.onrender.com/api/v1/telegram/webhook"
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

    params: Dict[str, Any] = {"url": url}
    if secret:
        params["secret_token"] = secret

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{TELEGRAM_API_BASE}/bot{token}/setWebhook", json=params)
            return resp.status_code == 200
    except Exception as e:
        logger.warning(f"[TELEGRAM] Webhook registration failed: {e}")
        return False

