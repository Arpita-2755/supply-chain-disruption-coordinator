"""Configuration: chooses the "model lane" (LLM mode or deterministic offline mode).

Why it exists: the system must run both with a real LLM and with NO API key.
There is ONE switch, SCC_MODE = auto | offline | llm (default auto):
  * auto    -> LLM mode if OpenAI / Azure OpenAI / OpenAI-compatible credentials are
               found in the environment (or .env), otherwise offline mode.
  * offline -> always deterministic, rule-based text; no network calls.
  * llm     -> require credentials (raises an error if none are set).
In both modes the tools are really called and decisions are made by deterministic
code; the LLM only writes explanatory text.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from offline_llm import OfflineChatCompletion

load_dotenv(Path(__file__).resolve().parent / ".env")  # harmless if the file does not exist


@dataclass(frozen=True)
class Settings:
    mode: str              # "offline" or "llm"
    provider: str          # "offline" | "openai" | "azure" | "openai_compatible"
    model: str


def detect_provider() -> str:
    """Look at the environment and say which provider credentials are available."""
    if os.getenv("AZURE_OPENAI_API_KEY") and os.getenv("AZURE_OPENAI_ENDPOINT"):
        return "azure"
    if os.getenv("OPENAI_API_KEY") and os.getenv("OPENAI_BASE_URL"):
        return "openai_compatible"
    if os.getenv("OPENAI_API_KEY"):
        return "openai"
    return "offline"


def load_settings() -> Settings:
    """Resolve the single SCC_MODE flag into concrete settings."""
    requested = os.getenv("SCC_MODE", "auto").strip().lower()
    provider = detect_provider()
    if requested == "offline" or (requested == "auto" and provider == "offline"):
        return Settings(mode="offline", provider="offline", model="rule-based")
    if provider == "offline":
        raise RuntimeError("SCC_MODE=llm but no OPENAI_API_KEY / AZURE_OPENAI_* credentials are set.")
    model = os.getenv("AZURE_OPENAI_DEPLOYMENT") if provider == "azure" else os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    return Settings(mode="llm", provider=provider, model=model or "gpt-4o-mini")


def build_chat_service(settings: Settings):
    """Create the Semantic Kernel chat-completion service for the chosen lane."""
    if settings.mode == "offline":
        return OfflineChatCompletion(ai_model_id="offline-rule-based")
    if settings.provider == "azure":
        from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
        return AzureChatCompletion(deployment_name=settings.model,
                                   endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
                                   api_key=os.environ["AZURE_OPENAI_API_KEY"],
                                   api_version=os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))
    from semantic_kernel.connectors.ai.open_ai import OpenAIChatCompletion
    if settings.provider == "openai_compatible":
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=os.environ["OPENAI_API_KEY"], base_url=os.environ["OPENAI_BASE_URL"])
        return OpenAIChatCompletion(ai_model_id=settings.model, async_client=client)
    return OpenAIChatCompletion(ai_model_id=settings.model, api_key=os.environ["OPENAI_API_KEY"])
