"""
Market Intelligence Lab — Free-Tier LLM Agent Provider Abstraction & Telemetry Metering.
Supports active 2026 models via lightweight httpx.AsyncClient:
- Primary: Groq Cloud (openai/gpt-oss-120b -> openai/gpt-oss-20b)
- Secondary: Google AI Studio (gemini-3.8-flash -> gemini-3.5-flash-lite)
Tracks exact prompt/completion token usage and rate-limit headers in SQLite WAL.
"""

import os
import logging
import contextvars
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
import httpx
from dotenv import load_dotenv

from src.storage.database import DatabaseManager

load_dotenv()

logger = logging.getLogger("copilot.llm_client")

# Free-Tier Quota Baselines
MODEL_QUOTAS: Dict[str, Dict[str, int]] = {
    "openai/gpt-oss-120b": {"daily_request_limit": 1000, "daily_token_limit": 200000},
    "openai/gpt-oss-20b": {"daily_request_limit": 1000, "daily_token_limit": 200000},
    "gemini-3.8-flash": {"daily_request_limit": 500, "daily_token_limit": 250000},
    "gemini-3.5-flash-lite": {"daily_request_limit": 1000, "daily_token_limit": 250000},
    "gemini-3-flash-preview": {"daily_request_limit": 500, "daily_token_limit": 250000},
}

DEFAULT_TELEMETRY: Dict[str, Any] = {
    "model": "local:deterministic-quant",
    "provider": "local",
    "prompt_tokens": 0,
    "completion_tokens": 0,
    "total_tokens": 0,
}

_last_call_telemetry: contextvars.ContextVar[Dict[str, Any]] = contextvars.ContextVar(
    "last_call_telemetry", default=DEFAULT_TELEMETRY.copy()
)


def get_last_call_telemetry() -> Dict[str, Any]:
    """Returns the per-turn token and model attribution from the last LLM execution."""
    val = _last_call_telemetry.get().copy()
    if "model_id" not in val and "model" in val:
        val["model_id"] = val["model"]
    if "token_usage" not in val:
        val["token_usage"] = {
            "prompt_tokens": val.get("prompt_tokens", 0),
            "completion_tokens": val.get("completion_tokens", 0),
            "total_tokens": val.get("total_tokens", 0),
        }
    return val


def set_last_call_telemetry(model_or_data: Any, token_usage: Optional[Dict[str, int]] = None) -> None:
    """Sets active turn telemetry, accepting either a dict or (model_id, token_usage)."""
    if isinstance(model_or_data, dict):
        data = model_or_data.copy()
        if "model_id" not in data and "model" in data:
            data["model_id"] = data["model"]
        if "token_usage" not in data:
            data["token_usage"] = {
                "prompt_tokens": data.get("prompt_tokens", 0),
                "completion_tokens": data.get("completion_tokens", 0),
                "total_tokens": data.get("total_tokens", 0),
            }
        _last_call_telemetry.set(data)
    else:
        tokens = token_usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        data = {
            "model": str(model_or_data),
            "model_id": str(model_or_data),
            "provider": "groq" if "gpt" in str(model_or_data) else ("gemini" if "gemini" in str(model_or_data) else "local"),
            "prompt_tokens": tokens.get("prompt_tokens", 0),
            "completion_tokens": tokens.get("completion_tokens", 0),
            "total_tokens": tokens.get("total_tokens", 0),
            "token_usage": tokens
        }
        _last_call_telemetry.set(data)


def record_llm_usage(
    provider: str,
    model_id: str,
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int = 0,
    remaining_reqs_header: Optional[int] = None,
    remaining_tokens_header: Optional[int] = None,
    db: Optional[DatabaseManager] = None,
    headers: Optional[Dict[str, Any]] = None,
    db_manager: Optional[DatabaseManager] = None,
) -> None:
    """
    Upserts daily token and request consumption into llm_usage_telemetry for today's UTC session.
    """
    if headers:
        try:
            if remaining_reqs_header is None and "x-ratelimit-remaining-requests" in headers:
                remaining_reqs_header = int(headers["x-ratelimit-remaining-requests"])
            if remaining_tokens_header is None and "x-ratelimit-remaining-tokens" in headers:
                remaining_tokens_header = int(headers["x-ratelimit-remaining-tokens"])
        except Exception:
            pass

    if total_tokens <= 0:
        total_tokens = prompt_tokens + completion_tokens

    target_db = db or db_manager

    quotas = MODEL_QUOTAS.get(
        model_id, {"daily_request_limit": 1000, "daily_token_limit": 200000}
    )
    daily_req_lim = quotas["daily_request_limit"]
    daily_tok_lim = quotas["daily_token_limit"]
    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    now_iso = datetime.now(timezone.utc).isoformat()

    try:
        db_mgr = target_db or DatabaseManager()
        with db_mgr.get_connection() as conn:
            conn.execute(
                """
                INSERT INTO llm_usage_telemetry (
                    usage_date, provider, model_id, requests_used, prompt_tokens,
                    completion_tokens, total_tokens, remaining_requests_header,
                    remaining_tokens_header, daily_request_limit, daily_token_limit, last_used_at
                ) VALUES (
                    ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?
                )
                ON CONFLICT(usage_date, model_id) DO UPDATE SET
                    requests_used = requests_used + 1,
                    prompt_tokens = prompt_tokens + excluded.prompt_tokens,
                    completion_tokens = completion_tokens + excluded.completion_tokens,
                    total_tokens = total_tokens + excluded.total_tokens,
                    remaining_requests_header = COALESCE(excluded.remaining_requests_header, remaining_requests_header),
                    remaining_tokens_header = COALESCE(excluded.remaining_tokens_header, remaining_tokens_header),
                    last_used_at = excluded.last_used_at;
                """,
                (
                    today_utc,
                    provider,
                    model_id,
                    prompt_tokens,
                    completion_tokens,
                    total_tokens,
                    remaining_reqs_header,
                    remaining_tokens_header,
                    daily_req_lim,
                    daily_tok_lim,
                    now_iso,
                ),
            )
            conn.commit()
    except Exception as e:
        logger.debug(f"[LLM-METER] Failed to record token usage in SQLite: {e}")


def is_live_llm_configured() -> bool:
    """Checks whether a valid live Groq or Gemini credential is configured."""
    return bool(os.getenv("GROQ_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip())


async def call_llm_completion(
    messages: List[Dict[str, str]],
    max_tokens: int = 850,
    temperature: float = 0.2,
    db: Optional[DatabaseManager] = None,
) -> Optional[str]:
    """
    Executes an async completion against the LLM cascade (Groq Primary -> Gemini Secondary).
    Parses exact tokens and rate-limit headers and records live usage metrics into SQLite WAL.
    """
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()

    # 1. Primary: Groq Cloud (openai/gpt-oss-120b -> openai/gpt-oss-20b)
    if groq_key:
        groq_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
        for model in groq_models:
            try:
                headers = {
                    "Authorization": f"Bearer {groq_key}",
                    "Content-Type": "application/json",
                }
                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                }
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=body,
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        choice = data.get("choices", [{}])[0].get("message", {})
                        content = choice.get("content") or choice.get("reasoning") or ""
                        if content.strip():
                            usage = data.get("usage", {})
                            p_tok = int(usage.get("prompt_tokens", 0) or 0)
                            c_tok = int(usage.get("completion_tokens", 0) or 0)
                            t_tok = int(usage.get("total_tokens", p_tok + c_tok) or 0)

                            # Parse rate-limit headers
                            rem_req = None
                            rem_tok = None
                            try:
                                h_req = resp.headers.get("x-ratelimit-remaining-requests")
                                if h_req is not None:
                                    rem_req = int(h_req)
                                h_tok = resp.headers.get("x-ratelimit-remaining-tokens")
                                if h_tok is not None:
                                    rem_tok = int(h_tok)
                            except Exception:
                                pass

                            record_llm_usage(
                                provider="groq",
                                model_id=model,
                                prompt_tokens=p_tok,
                                completion_tokens=c_tok,
                                total_tokens=t_tok,
                                remaining_reqs_header=rem_req,
                                remaining_tokens_header=rem_tok,
                                db=db,
                            )

                            set_last_call_telemetry({
                                "model": model,
                                "provider": "groq",
                                "prompt_tokens": p_tok,
                                "completion_tokens": c_tok,
                                "total_tokens": t_tok,
                            })

                            logger.info(
                                f"[COPILOT-LLM] Successfully generated completion via Groq ({model}, tokens={t_tok})."
                            )
                            return content.strip()
                    else:
                        logger.warning(
                            f"[COPILOT-LLM] Groq ({model}) failed with HTTP {resp.status_code}: {resp.text[:200]}"
                        )
            except Exception as ge:
                logger.warning(f"[COPILOT-LLM] Groq ({model}) network/runtime exception: {ge}")

    # 2. Secondary: Google AI Studio (gemini-3.8-flash -> gemini-3.5-flash-lite)
    if gemini_key:
        gemini_models = ["gemini-3.8-flash", "gemini-3.5-flash-lite", "gemini-3-flash-preview"]
        system_instructions = []
        conversation_parts = []
        for m in messages:
            role = m.get("role", "user")
            content = m.get("content", "")
            if role == "system":
                system_instructions.append(content)
            else:
                prefix = "User: " if role == "user" else "Assistant: "
                conversation_parts.append(f"{prefix}{content}")

        full_prompt = ""
        if system_instructions:
            full_prompt += "System Instructions:\n" + "\n".join(system_instructions) + "\n\n"
        full_prompt += "\n\n".join(conversation_parts)

        for model in gemini_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens,
                    },
                }
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        data = resp.json()
                        candidates = data.get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                text_out = parts[0]["text"].strip()
                                if text_out:
                                    u_meta = data.get("usageMetadata", {})
                                    p_tok = int(u_meta.get("promptTokenCount", 0) or 0)
                                    c_tok = int(u_meta.get("candidatesTokenCount", 0) or 0)
                                    t_tok = int(u_meta.get("totalTokenCount", p_tok + c_tok) or 0)

                                    record_llm_usage(
                                        provider="google",
                                        model_id=model,
                                        prompt_tokens=p_tok,
                                        completion_tokens=c_tok,
                                        total_tokens=t_tok,
                                        db=db,
                                    )

                                    set_last_call_telemetry({
                                        "model": model,
                                        "provider": "google",
                                        "prompt_tokens": p_tok,
                                        "completion_tokens": c_tok,
                                        "total_tokens": t_tok,
                                    })

                                    logger.info(
                                        f"[COPILOT-LLM] Successfully generated completion via Gemini ({model}, tokens={t_tok})."
                                    )
                                    return text_out
                    else:
                        logger.warning(
                            f"[COPILOT-LLM] Gemini ({model}) failed with HTTP {resp.status_code}: {resp.text[:200]}"
                        )
            except Exception as gme:
                logger.warning(f"[COPILOT-LLM] Gemini ({model}) network/runtime exception: {gme}")

    # Reset telemetry to local deterministic if no live provider succeeded
    set_last_call_telemetry(DEFAULT_TELEMETRY.copy())
    return None


def get_copilot_client() -> Tuple[Any, str]:
    """Compatibility shim returning provider info."""
    return None, "openai/gpt-oss-120b"
