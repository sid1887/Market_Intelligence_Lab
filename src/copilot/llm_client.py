"""
Market Intelligence Lab — Free-Tier LLM Agent Provider Abstraction.
Milestone B12.0: Part 2.

Supports Google AI Studio (Gemini 2.0 Flash / 1.5 Flash), Groq Cloud (llama-3.3-70b),
or Local Ollama (qwen2.5:7b) via an OpenAI-compatible Async client.
Lazy-loaded to guarantee 100% offline core platform operation and testability.
"""

import os
from typing import Any, Tuple

try:
    from openai import AsyncOpenAI
    HAS_OPENAI = True
except ImportError:
    AsyncOpenAI = None  # type: ignore
    HAS_OPENAI = False


def is_live_llm_configured() -> bool:
    """Checks whether a valid live credential or local host is configured and SDK is installed."""
    if not HAS_OPENAI:
        return False

    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider == "gemini":
        return bool(os.getenv("GEMINI_API_KEY"))
    elif provider == "groq":
        return bool(os.getenv("GROQ_API_KEY"))
    elif provider == "ollama":
        return True
    return False


def get_copilot_client() -> Tuple[Any, str]:
    """
    Returns an async OpenAI-compatible client and the target model name.
    Supports Google AI Studio (Free), Groq (Free), or local Ollama (Free).
    Raises RuntimeError if openai extra is not installed.
    """
    if not HAS_OPENAI:
        raise RuntimeError(
            "The 'openai' package is not installed. "
            "Install with 'pip install openai' or 'pip install .[llm]' to activate live LLM features."
        )

    provider = os.getenv("LLM_PROVIDER", "gemini").lower()

    if provider == "gemini":
        # Google AI Studio Free Tier (OpenAI compatible endpoint)
        api_key = os.getenv("GEMINI_API_KEY", "")
        client = AsyncOpenAI(
            api_key=api_key or "free_tier_placeholder",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    elif provider == "groq":
        # Groq Cloud Free Tier
        api_key = os.getenv("GROQ_API_KEY", "")
        client = AsyncOpenAI(
            api_key=api_key or "free_tier_placeholder",
            base_url="https://api.groq.com/openai/v1"
        )
        model = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
    else:
        # Local Ollama
        client = AsyncOpenAI(
            api_key="ollama",
            base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434/v1")
        )
        model = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

    return client, model
