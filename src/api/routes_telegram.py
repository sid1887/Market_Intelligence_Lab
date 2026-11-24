"""
Market Intelligence Lab — Telegram Pocket Terminal Routes.
Provides interactive webhook handling and auto-pairing for @sidraj_1887.
"""

import os
import re
import html
import logging
from typing import Dict, Any, Optional

import httpx

# Silence noisy HTTP client loggers to prevent leaking Telegram bot tokens in request URLs
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

from fastapi import APIRouter, Request, Header, HTTPException, BackgroundTasks
from pydantic import BaseModel

from src.storage.database import DatabaseManager
from src.api.utils import DATABASE_PATH
from src.notifications.telegram_bot import (
    get_bot_token,
    get_authorized_chat_id,
    is_user_authorized,
    pair_chat_id,
    send_telegram_message,
    send_telegram_message_async,
    TELEGRAM_API_BASE,
)

logger = logging.getLogger("api.routes_telegram")

router = APIRouter(prefix="/telegram", tags=["telegram"])

RENDER_BACKEND_URL = os.getenv("RENDER_BACKEND_URL", "https://mil-quant-backend.onrender.com").rstrip("/")
WEB_BASE_URL = os.getenv("NEXT_PUBLIC_APP_URL", "https://market-intelligence-lab-vert.vercel.app").rstrip("/")


def _clean_html(text: str) -> str:
    """Safely escapes HTML and formats basic markdown bold/code for Telegram."""
    # Escape raw HTML first
    escaped = html.escape(text)
    # Convert **bold** to <b>bold</b>
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", escaped)
    # Convert `code` to <code>code</code>
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


@router.get("/status")
def telegram_status():
    """Returns Telegram bot configuration and pairing telemetry."""
    token = get_bot_token()
    chat_id = get_authorized_chat_id()
    allowed_user = os.getenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887").strip().lower().lstrip("@")
    return {
        "status": "ready" if (token and chat_id) else "unconfigured",
        "bot_token_configured": bool(token),
        "chat_id_paired": bool(chat_id),
        "chat_id": chat_id,
        "allowed_username": allowed_user,
        "webhook_url": f"{RENDER_BACKEND_URL}/api/v1/telegram/webhook",
    }


@router.post("/register-webhook")
async def register_webhook_endpoint(request: Request):
    """Registers the Telegram bot webhook with Telegram API."""
    token = get_bot_token()
    if not token:
        raise HTTPException(status_code=400, detail="TELEGRAM_BOT_TOKEN is not configured.")

    base_url = RENDER_BACKEND_URL
    webhook_url = f"{base_url}/api/v1/telegram/webhook"
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()

    params: Dict[str, Any] = {"url": webhook_url}
    if secret:
        params["secret_token"] = secret

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(f"{TELEGRAM_API_BASE}/bot{token}/setWebhook", json=params)
            data = resp.json()
            return {"status": "ok", "telegram_response": data, "registered_url": webhook_url}
    except Exception as e:
        logger.error(f"[TELEGRAM] Webhook registration failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def telegram_webhook_endpoint(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: Optional[str] = Header(None)
):
    """
    Main webhook receiver for Telegram Bot Updates.
    Locks execution strictly to authorized user @sidraj_1887.
    """
    secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if secret and x_telegram_bot_api_secret_token != secret:
        logger.warning("[TELEGRAM] Rejected webhook: secret token mismatch.")
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        update = await request.json()
    except Exception:
        return {"ok": True}

    msg = update.get("message") or update.get("edited_message")
    if not msg:
        return {"ok": True}

    chat = msg.get("chat", {})
    chat_id = chat.get("id")
    sender = msg.get("from", {})
    username = sender.get("username", "")
    text = (msg.get("text") or "").strip()

    if not chat_id:
        return {"ok": True}

    # Verify authorization
    allowed_user = os.getenv("TELEGRAM_ALLOWED_USERNAME", "sidraj_1887").strip().lower().lstrip("@")
    is_pairing = text.startswith("/start") and (username and username.lower().lstrip("@") == allowed_user)

    if not is_user_authorized(username, chat_id) and not is_pairing:
        logger.warning(f"[TELEGRAM] Unauthorized command from @{username} (chat_id={chat_id}): '{text}'")
        unauth_msg = (
            "🔒 <b>Unauthorized Access</b>\n\n"
            f"This pocket quantitative terminal is private and locked strictly to @{allowed_user}."
        )
        send_telegram_message(unauth_msg, chat_id=str(chat_id))
        return {"ok": True, "status": "unauthorized"}

    if is_pairing and username:
        pair_chat_id(username, chat_id)

    try:
        from src.storage.database import record_external_api_metric
        cmd_name = text.split()[0] if text.startswith("/") else "query"
        record_external_api_metric("telegram", f"webhook:{cmd_name[:20]}", success=True, units=1)
    except Exception:
        pass

    # Process Commands in background to ensure 200 OK is returned in < 500ms to Telegram
    background_tasks.add_task(
        _handle_telegram_command,
        chat_id=str(chat_id),
        username=username,
        text=text
    )
    return {"ok": True, "status": "ok", "action": "paired" if is_pairing else "queued"}


async def _handle_telegram_command(chat_id: str, username: str, text: str):
    """Processes interactive commands and queries for authorized user."""
    try:
        clean_text = text.strip()
        cmd_parts = clean_text.split()
        cmd = cmd_parts[0].lower() if cmd_parts else ""

        # 1. /start or /help
        if cmd in ("/start", "/help"):
            if username:
                pair_chat_id(username, chat_id)
            welcome = (
                f"👋 <b>Welcome @sidraj_1887 to Market Intelligence Lab</b>\n\n"
                f"Your account has been authenticated & paired with the quant terminal.\n"
                f"<b>Paired Chat ID:</b> <code>{chat_id}</code>\n\n"
                f"<b>Interactive Commands:</b>\n"
                f"• <code>/forecast &lt;SYMBOL&gt;</code> — ML multi-horizon alpha forecast\n"
                f"• <code>/scan</code> — Top 5 real-time causal price & volume anomalies\n"
                f"• <code>/watchlist</code> — Live watchlist status & distance to targets\n"
                f"• <code>/top</code> — Top 7 factor-ranked equities from screener\n"
                f"• <code>/ask &lt;QUESTION&gt;</code> or send any free-text query (e.g. <i>\"Compare SUZLON vs RVNL\"</i> or <i>\"Why did BEL surge?\"</i>)\n\n"
                f"🔗 <a href=\"{WEB_BASE_URL}\">Open Web Terminal</a>"
            )
            await send_telegram_message_async(welcome, chat_id=chat_id)
            return

        # 2. /forecast <SYMBOL>
        if cmd == "/forecast":
            sym = cmd_parts[1].upper() if len(cmd_parts) > 1 else ""
            if not sym:
                await send_telegram_message_async("⚠️ Please provide a stock symbol, e.g. <code>/forecast RELIANCE</code>", chat_id=chat_id)
                return
            await _handle_forecast_command(chat_id, sym)
            return

        # 3. /scan or /catalysts
        if cmd in ("/scan", "/catalysts"):
            await _handle_scan_command(chat_id)
            return

        # 4. /watchlist
        if cmd == "/watchlist":
            await _handle_watchlist_command(chat_id)
            return

        # 5. /top
        if cmd == "/top":
            await _handle_top_command(chat_id)
            return

        # 6. /ask <QUESTION> or Free-Text Prompt
        query = clean_text
        if query.lower().startswith("/ask"):
            query = query[4:].strip()

        await _handle_copilot_query(chat_id, query)

    except Exception as e:
        logger.error(f"[TELEGRAM] Error handling command: {e}", exc_info=True)
        await send_telegram_message_async(f"⚠️ Internal error processing command: {html.escape(str(e))}", chat_id=chat_id)


async def _handle_forecast_command(chat_id: str, symbol: str):
    """Handles /forecast <SYMBOL>."""
    db = DatabaseManager(DATABASE_PATH)
    sym = symbol.strip().upper()
    try:
        from src.copilot.mcp_bridge import QuantMCPBridge
        bridge = QuantMCPBridge(db)
        funds = bridge.get_stock_fundamentals(sym)
        if "error" in funds:
            await send_telegram_message_async(f"⚠️ {funds['error']}", chat_id=chat_id)
            return

        price = funds.get("current_price", 0.0)
        ml = bridge.get_ml_champion_forecast(sym)
        garch = bridge.get_forecast_bounds(sym)

        champ_model = ml.get("champion_model", "HistGradientBoosting")
        tier = ml.get("conviction_tier", "MOMENTUM_ACCUMULATION")
        conviction = ml.get("conviction_score", 75)

        fc = ml.get("forecasts", {})
        fc_5 = fc.get("5D", {})
        fc_20 = fc.get("20D", {})
        fc_60 = fc.get("60D", {})

        target_20 = garch.get("expected_20d_price", round(price * 1.05, 2))
        stop_loss = garch.get("invalidation_floor", round(price * 0.95, 2))

        msg = (
            f"🎯 <b>{sym} · Multi-Horizon ML Alpha Forecast</b>\n"
            f"<b>Settled Price:</b> ₹{price:.2f} | <b>Conviction:</b> <code>{tier}</code> ({conviction}/100)\n"
            f"<b>Champion Model:</b> {champ_model}\n\n"
            f"• <b>5D Horizon:</b> {fc_5.get('expected_return_pct', 0.0):+.2f}% ({fc_5.get('expected_excess_bps', 0.0):+.1f} bps)\n"
            f"• <b>20D Target:</b> {fc_20.get('expected_return_pct', 0.0):+.2f}% ({fc_20.get('expected_excess_bps', 0.0):+.1f} bps)\n"
            f"• <b>60D Structural:</b> {fc_60.get('expected_return_pct', 0.0):+.2f}% ({fc_60.get('expected_excess_bps', 0.0):+.1f} bps)\n\n"
            f"<b>GARCH Bounds:</b> Target: ₹{target_20:.2f} | Floor: ₹{stop_loss:.2f}\n"
            f"🔗 <a href=\"{WEB_BASE_URL}/stocks/{sym}\">Inspect Terminal Tearsheet</a>"
        )
        await send_telegram_message_async(msg, chat_id=chat_id)
    except Exception as e:
        logger.error(f"[TELEGRAM] Forecast error for {sym}: {e}", exc_info=True)
        await send_telegram_message_async(f"⚠️ Could not compute forecast for {sym}: {html.escape(str(e))}", chat_id=chat_id)


async def _handle_scan_command(chat_id: str):
    """Handles /scan or /catalysts."""
    try:
        from src.tasks.catalyst_engine import CausalCatalystEngine
        cats = CausalCatalystEngine.get_live_catalysts(limit=5)
        if not cats:
            await send_telegram_message_async("📡 <b>No active price/volume anomalies detected in the last scan window.</b>", chat_id=chat_id)
            return

        lines = ["⚡ <b>Latest Causal Anomaly Catalysts</b>\n"]
        for c in cats:
            sym = c.get("symbol", "")
            title = c.get("push_title") or c.get("causal_headline", sym)
            body = c.get("push_body") or ""
            lines.append(f"• <b>{html.escape(title)}</b>\n  <i>{html.escape(body[:120])}</i>\n")

        msg = "\n".join(lines)
        await send_telegram_message_async(msg, chat_id=chat_id)
    except Exception as e:
        logger.error(f"[TELEGRAM] Scan error: {e}", exc_info=True)
        await send_telegram_message_async(f"⚠️ Scan error: {html.escape(str(e))}", chat_id=chat_id)


async def _handle_watchlist_command(chat_id: str):
    """Handles /watchlist."""
    db = DatabaseManager(DATABASE_PATH)
    try:
        with db.get_connection() as conn:
            rows = conn.execute("""
                SELECT w.symbol, w.company_name, w.target_price, w.stop_loss,
                       o.close, o.trading_date
                FROM user_watchlists w
                LEFT JOIN (
                    SELECT symbol, close, trading_date,
                           ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY trading_date DESC) as rn
                    FROM ohlcv_daily
                ) o ON w.symbol = o.symbol AND o.rn = 1
                ORDER BY w.symbol ASC
            """).fetchall()

        if not rows:
            await send_telegram_message_async("👁️ <b>Your Watchlist is currently empty.</b> Add symbols on the web terminal.", chat_id=chat_id)
            return

        lines = ["👁️ <b>Institutional Watchlist Monitor</b>\n"]
        for r in rows:
            sym = r["symbol"]
            close = r["close"] or 0.0
            tgt = r["target_price"]
            stop = r["stop_loss"]
            tgt_str = f"Tgt: ₹{tgt:.2f}" if tgt else ""
            stop_str = f"SL: ₹{stop:.2f}" if stop else ""
            lines.append(f"• <b>{sym}</b>: ₹{close:.2f} {tgt_str} {stop_str}".strip())

        lines.append(f"\n🔗 <a href=\"{WEB_BASE_URL}\">Manage Watchlist</a>")
        msg = "\n".join(lines)
        await send_telegram_message_async(msg, chat_id=chat_id)
    except Exception as e:
        logger.error(f"[TELEGRAM] Watchlist error: {e}", exc_info=True)
        await send_telegram_message_async(f"⚠️ Watchlist error: {html.escape(str(e))}", chat_id=chat_id)


async def _handle_top_command(chat_id: str):
    """Handles /top."""
    db = DatabaseManager(DATABASE_PATH)
    try:
        from src.quant.screener import FactorScreener
        screener = FactorScreener(db)
        df = screener.screen(limit=7)
        if df.empty:
            await send_telegram_message_async("⚠️ Screener returned 0 records.", chat_id=chat_id)
            return

        lines = ["🏆 <b>Top Quantitative Quality-Momentum Equities</b>\n"]
        for idx, row in df.head(7).iterrows():
            sym = row.get("symbol", "")
            close = row.get("close", 0.0)
            score = row.get("blended_score") or row.get("composite_score", 0.0)
            ret_20d = row.get("ret_20d", 0.0)
            lines.append(
                f"{idx + 1}. <b>{sym}</b>: ₹{close:.2f} | Score: <b>{score:.1f}</b> | 20D: {ret_20d:+.1f}%"
            )

        lines.append(f"\n🔗 <a href=\"{WEB_BASE_URL}\">View Full Screener</a>")
        msg = "\n".join(lines)
        await send_telegram_message_async(msg, chat_id=chat_id)
    except Exception as e:
        logger.error(f"[TELEGRAM] Top screener error: {e}", exc_info=True)
        await send_telegram_message_async(f"⚠️ Screener error: {html.escape(str(e))}", chat_id=chat_id)


async def _handle_copilot_query(chat_id: str, query: str):
    """Processes free-text quantitative question using the upgraded Copilot engine."""
    from src.copilot.deliberation import MultiAgentDeliberationEngine
    engine = MultiAgentDeliberationEngine()
    try:
        reply = await engine.generate_direct_response(prompt=query)
        clean = _clean_html(reply)
        await send_telegram_message_async(clean, chat_id=chat_id)
    except Exception as e:
        logger.error(f"[TELEGRAM] Copilot query error for '{query}': {e}", exc_info=True)
        await send_telegram_message_async(f"⚠️ Copilot analysis error: {html.escape(str(e))}", chat_id=chat_id)
