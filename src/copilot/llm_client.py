"""
Market Intelligence Lab — Free-Tier LLM Agent Provider Abstraction.
Supports active 2026 models via lightweight httpx.AsyncClient:
- Primary: Groq Cloud (openai/gpt-oss-120b -> openai/gpt-oss-20b)
- Secondary: Google AI Studio (gemini-3.8-flash -> gemini-3-flash-preview)
Zero heavy dependencies, works seamlessly in CLOUD_LIGHTWEIGHT_MODE (<200MB RAM).
"""

import os
import logging
from typing import Optional, List, Dict, Any, Tuple
import httpx
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger("copilot.llm_client")


def is_live_llm_configured() -> bool:
    """Checks whether a valid live Groq or Gemini credential is configured."""
    return bool(os.getenv("GROQ_API_KEY", "").strip() or os.getenv("GEMINI_API_KEY", "").strip())


async def call_llm_completion(
    messages: List[Dict[str, str]],
    max_tokens: int = 850,
    temperature: float = 0.2
) -> Optional[str]:
    """
    Executes an async completion against the LLM cascade (Groq Primary -> Gemini Secondary).
    Logs exact HTTP status code and error text on failures so they are never silent.
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
                    "Content-Type": "application/json"
                }
                body = {
                    "model": model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens
                }
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers=headers,
                        json=body
                    )
                    if resp.status_code == 200:
                        choice = resp.json().get("choices", [{}])[0].get("message", {})
                        content = choice.get("content") or choice.get("reasoning") or ""
                        if content.strip():
                            logger.info(f"[COPILOT-LLM] Successfully generated completion via Groq ({model}).")
                            return content.strip()
                    else:
                        logger.warning(
                            f"[COPILOT-LLM] Groq ({model}) failed with HTTP {resp.status_code}: {resp.text[:200]}"
                        )
            except Exception as ge:
                logger.warning(f"[COPILOT-LLM] Groq ({model}) network/runtime exception: {ge}")

    # 2. Secondary: Google AI Studio (gemini-3.8-flash -> gemini-3-flash-preview)
    if gemini_key:
        gemini_models = ["gemini-3.8-flash", "gemini-3-flash-preview", "gemini-2.5-flash-lite"]
        # Format messages for Gemini API
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
            full_prompt += f"System Instructions:\n" + "\n".join(system_instructions) + "\n\n"
        full_prompt += "\n\n".join(conversation_parts)

        for model in gemini_models:
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={gemini_key}"
                payload = {
                    "contents": [{"parts": [{"text": full_prompt}]}],
                    "generationConfig": {
                        "temperature": temperature,
                        "maxOutputTokens": max_tokens
                    }
                }
                async with httpx.AsyncClient(timeout=14.0) as client:
                    resp = await client.post(url, json=payload)
                    if resp.status_code == 200:
                        candidates = resp.json().get("candidates", [])
                        if candidates and "content" in candidates[0]:
                            parts = candidates[0]["content"].get("parts", [])
                            if parts and "text" in parts[0]:
                                text_out = parts[0]["text"].strip()
                                if text_out:
                                    logger.info(f"[COPILOT-LLM] Successfully generated completion via Gemini ({model}).")
                                    return text_out
                    else:
                        logger.warning(
                            f"[COPILOT-LLM] Gemini ({model}) failed with HTTP {resp.status_code}: {resp.text[:200]}"
                        )
            except Exception as gme:
                logger.warning(f"[COPILOT-LLM] Gemini ({model}) network/runtime exception: {gme}")

    return None


# Backward-compatible mock for legacy callers
def get_copilot_client() -> Tuple[Any, str]:
    """Compatibility shim returning provider info."""
    return None, "openai/gpt-oss-120b"
