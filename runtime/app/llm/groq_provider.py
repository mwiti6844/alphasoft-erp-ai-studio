"""Groq provider using the OpenAI-compatible chat/completions API.

Raw httpx client — no vendor SDK. This class is the template for any
OpenAI-compatible provider (Foundry serverless endpoints included).
"""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.llm.provider import ProviderError
from app.llm.types import (
    ChatMessage,
    CompletionRequest,
    CompletionResponse,
    Part,
    StopReason,
    TextPart,
    ToolCallPart,
    ToolResultPart,
    Usage,
)

PROVIDER_NAME = "groq"
DEFAULT_BASE_URL = "https://api.groq.com/openai"
CHAT_COMPLETIONS_PATH = "/v1/chat/completions"

_FINISH_REASON_MAP = {
    "stop": StopReason.END_TURN,
    "tool_calls": StopReason.TOOL_USE,
    "length": StopReason.MAX_TOKENS,
}


def build_payload(request: CompletionRequest, model: str) -> dict[str, Any]:
    """Translate a neutral CompletionRequest into an OpenAI-compatible payload."""
    messages: list[dict[str, Any]] = [{"role": "system", "content": request.system}]
    for message in request.messages:
        messages.extend(_wire_messages(message))
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": request.max_tokens,
        "temperature": request.temperature,
    }
    if request.tools:
        payload["tools"] = [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in request.tools
        ]
        payload["tool_choice"] = "auto"
    return payload


def _wire_messages(message: ChatMessage) -> list[dict[str, Any]]:
    if message.role == "tool":
        # OpenAI shape requires one tool message per call result.
        return [
            {"role": "tool", "tool_call_id": part.call_id, "content": part.content}
            for part in message.parts
            if isinstance(part, ToolResultPart)
        ]
    if message.role == "assistant":
        wire: dict[str, Any] = {"role": "assistant", "content": message.text() or None}
        tool_calls = [
            {
                "id": part.call_id,
                "type": "function",
                "function": {"name": part.name, "arguments": json.dumps(part.arguments)},
            }
            for part in message.parts
            if isinstance(part, ToolCallPart)
        ]
        if tool_calls:
            wire["tool_calls"] = tool_calls
        return [wire]
    return [{"role": "user", "content": message.text()}]


def parse_response(data: dict[str, Any], model: str) -> CompletionResponse:
    """Translate an OpenAI-compatible response body into a neutral CompletionResponse."""
    choices = data.get("choices") or []
    if not choices:
        raise ProviderError(PROVIDER_NAME, "response contained no choices")
    choice = choices[0]
    wire_message = choice.get("message") or {}

    parts: list[Part] = []
    content = wire_message.get("content")
    if isinstance(content, str) and content:
        parts.append(TextPart(text=content))
    tool_calls = wire_message.get("tool_calls") or []
    for call in tool_calls:
        parts.append(_parse_tool_call(call))

    finish_reason = choice.get("finish_reason")
    stop_reason = _FINISH_REASON_MAP.get(finish_reason, StopReason.OTHER)
    if tool_calls:
        # Some Llama endpoints report finish_reason "stop" alongside tool_calls.
        stop_reason = StopReason.TOOL_USE

    usage = data.get("usage") or {}
    return CompletionResponse(
        parts=tuple(parts),
        stop_reason=stop_reason,
        usage=Usage(
            input_tokens=int(usage.get("prompt_tokens") or 0),
            output_tokens=int(usage.get("completion_tokens") or 0),
        ),
        provider=PROVIDER_NAME,
        model=model,
    )


def _parse_tool_call(call: dict[str, Any]) -> ToolCallPart:
    function = call.get("function") or {}
    name = function.get("name") or ""
    if not name:
        raise ProviderError(PROVIDER_NAME, "model returned a tool call without a name")
    raw_arguments = function.get("arguments") or "{}"
    try:
        arguments = json.loads(raw_arguments)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProviderError(
            PROVIDER_NAME, f"model returned malformed tool arguments for {name}"
        ) from exc
    if not isinstance(arguments, dict):
        raise ProviderError(
            PROVIDER_NAME, f"model returned non-object tool arguments for {name}"
        )
    return ToolCallPart(call_id=str(call.get("id") or ""), name=name, arguments=arguments)


def _error_message(response: httpx.Response) -> str:
    try:
        body = response.json()
        message = (body.get("error") or {}).get("message")
        if isinstance(message, str) and message:
            return message
    except (json.JSONDecodeError, AttributeError):
        pass
    return response.text[:200] or "request failed"


class GroqProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout_seconds: float = 60.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"authorization": f"Bearer {api_key}"},
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        payload = build_payload(request, self.model)
        try:
            response = await self._client.post(
                f"{self._base_url}{CHAT_COMPLETIONS_PATH}", json=payload
            )
        except httpx.HTTPError as exc:
            raise ProviderError(PROVIDER_NAME, f"request failed: {exc}") from exc
        if response.status_code >= 400:
            raise ProviderError(
                PROVIDER_NAME,
                f"{_error_message(response)} ({response.status_code})",
                status_code=response.status_code,
            )
        try:
            data = response.json()
        except json.JSONDecodeError as exc:
            raise ProviderError(PROVIDER_NAME, "response was not valid JSON") from exc
        return parse_response(data, self.model)
