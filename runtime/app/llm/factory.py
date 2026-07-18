"""Provider selection — fails at startup, not on the first request."""

from __future__ import annotations

from app.config import Settings
from app.llm.anthropic_provider import AnthropicProvider
from app.llm.fallback_provider import FallbackProvider
from app.llm.groq_provider import GroqProvider
from app.llm.provider import LLMProvider

SUPPORTED_PROVIDERS = ("anthropic", "groq")


def _build_anthropic(settings: Settings) -> AnthropicProvider:
    return AnthropicProvider(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )


def _build_groq(settings: Settings) -> GroqProvider:
    return GroqProvider(
        api_key=settings.groq_api_key,
        model=settings.groq_model,
        base_url=settings.groq_base_url,
        timeout_seconds=settings.request_timeout_seconds,
    )


def _build_single(provider: str, settings: Settings) -> LLMProvider:
    if provider == "anthropic":
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
        return _build_anthropic(settings)
    if provider == "groq":
        if not settings.groq_api_key:
            raise RuntimeError("GROQ_API_KEY is required when AI_PROVIDER=groq")
        return _build_groq(settings)
    supported = ", ".join(SUPPORTED_PROVIDERS)
    raise RuntimeError(
        f"Unsupported AI_PROVIDER '{settings.ai_provider}'. Supported providers: {supported}"
    )


def build_provider(settings: Settings) -> LLMProvider:
    provider = settings.ai_provider.strip().lower()
    primary = _build_single(provider, settings)

    # If the *other* provider's key is configured, keep it as a fallback so a
    # rate-limited primary degrades gracefully instead of failing the turn.
    if provider == "groq" and settings.anthropic_api_key:
        return FallbackProvider(primary, _build_anthropic(settings))
    if provider == "anthropic" and settings.groq_api_key:
        return FallbackProvider(primary, _build_groq(settings))
    return primary
