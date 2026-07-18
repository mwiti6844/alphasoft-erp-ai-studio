from __future__ import annotations

import hmac
from typing import Annotated
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.agents.copilot import run_copilot
from app.streaming.sse import async_events_to_sse

router = APIRouter(prefix="/api", tags=["chat"])


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "tenant_id": "local",
                "user_id": 1,
                "session_id": 1,
                "runtime_session_id": "test-runtime-session",
                "domain": "tenant.localhost",
                "module_scope": "inventory",
                "message": "Say one short sentence confirming you are ready for inventory questions.",
                "messages": [
                    {
                        "role": "user",
                        "content": "Say one short sentence confirming you are ready for inventory questions.",
                    }
                ],
                "conversation_state": {},
                "ui_action": None,
                "user_memory": {},
                "tool_definitions": [],
                "max_tokens": 256,
                "temperature": 0.1,
            }
        }
    )

    tenant_id: str = Field(min_length=1, max_length=128)
    user_id: int = Field(gt=0)
    session_id: int = Field(gt=0)
    runtime_session_id: str = Field(min_length=1, max_length=128)
    domain: str = Field(min_length=1, max_length=255)
    module_scope: str = Field(min_length=1, max_length=64)
    message: str = Field(min_length=1, max_length=4000)
    messages: list[dict[str, str]] = Field(default_factory=list)
    conversation_state: dict[str, Any] = Field(default_factory=dict)
    ui_action: dict[str, Any] | None = None
    user_memory: dict[str, Any] = Field(default_factory=dict)
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
async def chat(
    body: ChatRequest,
    request: Request,
    x_ai_runtime_token: Annotated[str, Header(alias="x-ai-runtime-token")] = "",
) -> StreamingResponse:
    settings = request.app.state.settings
    received = x_ai_runtime_token
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
        runtime_session_id=body.runtime_session_id,
        domain=body.domain,
        message=body.message,
        messages=body.messages,
        conversation_state=body.conversation_state,
        ui_action=body.ui_action,
        user_memory=body.user_memory,
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
