from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

PLACEHOLDER_SECRETS = {"change-me-local", "changeme", "secret"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "local"
    ai_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    groq_api_key: str = ""
    groq_model: str = "llama-3.3-70b-versatile"
    groq_base_url: str = "https://api.groq.com/openai"
    laravel_internal_url: str = "http://127.0.0.1:8000"
    ai_runtime_shared_secret: str = ""
    cors_allowed_origins: str = ""
    request_timeout_seconds: int = 60

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"


def load_settings() -> Settings:
    settings = Settings()
    provider = settings.ai_provider.strip().lower()
    if provider == "anthropic" and not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is required when AI_PROVIDER=anthropic")
    if provider == "groq" and not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY is required when AI_PROVIDER=groq")
    unsafe_secret = (
        not settings.ai_runtime_shared_secret
        or settings.ai_runtime_shared_secret in PLACEHOLDER_SECRETS
    )
    if unsafe_secret and settings.is_production:
        raise RuntimeError("AI_RUNTIME_SHARED_SECRET must be configured in production")
    return settings
