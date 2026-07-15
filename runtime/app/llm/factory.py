"""Provider selection — fails at startup, not on the first request."""

from __future__ import annotations

from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.groq_provider import GroqProvider
from app.llm.provider import LLMProvider

SUPPORTED_PROVIDERS = ("anthropic", "groq")


def build_provider(settings: Settings) -> LLMProvider:
    provider = settings.ai_provider.strip().lower()
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
        )
    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when AI_PROVIDER=groq")
        return GroqProvider(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            base_url=settings.groq_base_url,
            timeout_seconds=settings.request_timeout_seconds,
        )
    supported = ", ".join(SUPPORTED_PROVIDERS)
    raise RuntimeError(
        f"Unsupported AI_PROVIDER '{settings.ai_provider}'. Supported providers: {supported}"
    )
