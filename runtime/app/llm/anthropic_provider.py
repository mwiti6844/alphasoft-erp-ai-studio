"""Anthropic provider behind the neutral LLMProvider interface."""

from __future__ import annotations

from typing import Any

import anthropic

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

PROVIDER_NAME = "anthropic"

_STOP_REASON_MAP = {
    "end_turn": StopReason.END_TURN,
    "tool_use": StopReason.TOOL_USE,
    "max_tokens": StopReason.MAX_TOKENS,
}


def build_messages(messages: tuple[ChatMessage, ...]) -> list[dict[str, Any]]:
    """Translate neutral messages into Anthropic wire messages."""
    wire: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "tool":
            wire.append(
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "tool_result",
                            "tool_use_id": part.call_id,
                            "content": part.content,
                        }
                        for part in message.parts
                        if isinstance(part, ToolResultPart)
                    ],
                }
            )
        elif message.role == "assistant":
            wire.append({"role": "assistant", "content": _assistant_blocks(message)})
        else:
            wire.append({"role": "user", "content": message.text()})
    return wire


def _assistant_blocks(message: ChatMessage) -> list[dict[str, Any]]:
    blocks: list[dict[str, Any]] = []
    for part in message.parts:
        if isinstance(part, TextPart) and part.text:
            blocks.append({"type": "text", "text": part.text})
        elif isinstance(part, ToolCallPart):
            blocks.append(
                {
                    "type": "tool_use",
                    "id": part.call_id,
                    "name": part.name,
                    "input": part.arguments,
                }
            )
    return blocks


def build_tools(request: CompletionRequest) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.parameters,
        }
        for tool in request.tools
    ]


def parts_from_content(blocks: list[Any]) -> tuple[Part, ...]:
    """Translate Anthropic response content blocks into neutral parts."""
    parts: list[Part] = []
    for block in blocks:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(TextPart(text=block.text))
        elif block_type == "tool_use":
            arguments = block.input if isinstance(block.input, dict) else {}
            parts.append(ToolCallPart(call_id=block.id, name=block.name, arguments=arguments))
    return tuple(parts)


def map_stop_reason(stop_reason: str | None) -> StopReason:
    return _STOP_REASON_MAP.get(stop_reason or "", StopReason.OTHER)


class AnthropicProvider:
    name = PROVIDER_NAME

    def __init__(
        self,
        api_key: str,
        model: str,
        client: anthropic.AsyncAnthropic | None = None,
    ) -> None:
        self.model = model
        self._client = client or anthropic.AsyncAnthropic(
            api_key=api_key, timeout=60.0, max_retries=2
        )

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        try:
            response = await self._client.messages.create(
                model=self.model,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
                system=request.system,
                messages=build_messages(request.messages),
                tools=build_tools(request),
            )
        except anthropic.APIStatusError as exc:
            raise ProviderError(
                PROVIDER_NAME, f"{exc.message} ({exc.status_code})", status_code=exc.status_code
            ) from exc
        except anthropic.APIError as exc:
            raise ProviderError(PROVIDER_NAME, str(exc)) from exc

        usage = getattr(response, "usage", None)
        return CompletionResponse(
            parts=parts_from_content(list(response.content)),
            stop_reason=map_stop_reason(getattr(response, "stop_reason", None)),
            usage=Usage(
                input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
                output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            ),
            provider=PROVIDER_NAME,
            model=self.model,
        )
