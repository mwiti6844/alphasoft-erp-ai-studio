from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.clients.laravel import LaravelToolClient
from app.config import load_settings
from app.llm.factory import build_provider
from app.routes.chat import router as chat_router
from app.routes.health import router as health_router


def create_app() -> FastAPI:
    settings = load_settings()
    app = FastAPI(title="AlphaSoft ERP AI Studio Runtime")
    allowed_origins = [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]
    if allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=allowed_origins,
            allow_methods=["POST", "GET"],
            allow_headers=["authorization", "content-type", "x-ai-runtime-token"],
        )
    app.state.settings = settings
    app.state.provider = build_provider(settings)
    app.state.laravel = LaravelToolClient(
        base_url=settings.laravel_internal_url,
        shared_secret=settings.ai_runtime_shared_secret,
        timeout_seconds=settings.request_timeout_seconds,
    )
    app.include_router(health_router)
    app.include_router(chat_router)
    return app


app = create_app()
