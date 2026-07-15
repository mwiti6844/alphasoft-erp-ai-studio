from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, field_validator

from app.agents.copilot import run_copilot
from app.streaming.sse import async_events_to_sse

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    module_scope: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    messages: list[dict[str, str]] = Field(default_factory=list)
    conversation_state: dict[str, Any] = Field(default_factory=dict)
    tool_definitions: list[dict[str, Any]] = Field(default_factory=list)
    max_tokens: int = Field(default=1024, ge=128, le=4096)
    temperature: float = Field(default=0.2, ge=0, le=1)

    @field_validator("messages")
    @classmethod
    def validate_messages(cls, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        validated = []
        for message in messages[-20:]:
            role = message.get("role")
            content = message.get("content", "")
            if role not in {"user", "assistant"} or not isinstance(content, str):
                continue
            content = content.strip()
            if content:
                validated.append({"role": role, "content": content[:4000]})
        return validated


@router.post("/chat")
async def chat(body: ChatRequest, request: Request) -> StreamingResponse:
    settings = request.app.state.settings
    received = request.headers.get("x-ai-runtime-token", "")
    expected = settings.ai_runtime_shared_secret

    if not expected or not hmac.compare_digest(received, expected):
        raise HTTPException(status_code=401, detail="Unauthorized AI runtime request.")

    provider = request.app.state.provider
    laravel = request.app.state.laravel

    events = run_copilot(
        provider=provider,
        laravel=laravel,
        tenant_id=body.tenant_id,
        user_id=body.user_id,
        session_id=body.session_id,
        message=body.message,
        messages=body.messages,
        conversation_state=body.conversation_state,
        module_scope=body.module_scope,
        tool_definitions=body.tool_definitions,
        max_tokens=body.max_tokens,
        temperature=body.temperature,
    )

    return StreamingResponse(
        async_events_to_sse(events),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
