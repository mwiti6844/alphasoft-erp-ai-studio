from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from app.agents.components import component_for_tool, validated_component
from app.agents.events import ComponentReady, StatePatch, TextDelta, ToolCompleted, ToolStarted, Trace
from app.agents.modules.registry import router_for_scope
from app.clients.laravel import LaravelToolClient
from app.llm.provider import LLMProvider
from app.llm.types import (
    ChatMessage,
    CompletionRequest,
    TextPart,
    ToolDefinition,
    ToolResultPart,
)

MAX_TOOL_ITERATIONS = 8
HISTORY_LIMIT = 20


def parse_tool_definitions(
    tool_definitions: list[dict[str, Any]],
) -> tuple[tuple[ToolDefinition, ...], tuple[str, ...]]:
    """Validate raw tool definitions at the boundary.

    Returns (valid definitions, labels of skipped entries) so callers can
    surface skips instead of dropping them silently.
    """
    parsed: list[ToolDefinition] = []
    skipped: list[str] = []
    for index, tool in enumerate(tool_definitions):
        name = tool.get("name")
        if not isinstance(name, str) or not name.strip():
            skipped.append(f"#{index}")
            continue
        schema = tool.get("input_schema")
        if not isinstance(schema, dict):
            schema = {"type": "object", "properties": {}}
        parsed.append(
            ToolDefinition(
                name=name.strip(),
                description=str(tool.get("description", "")),
                parameters=schema,
            )
        )
    return tuple(parsed), tuple(skipped)


def build_conversation(messages: list[dict[str, str]], message: str) -> list[ChatMessage]:
    conversation = [
        ChatMessage(role=item["role"], parts=(TextPart(text=item["content"]),))
        for item in messages[-HISTORY_LIMIT:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    last = conversation[-1] if conversation else None
    if last is None or last.role != "user" or last.text() != message:
        conversation.append(ChatMessage(role="user", parts=(TextPart(text=message),)))
    return conversation


async def run_copilot(
    *,
    provider: LLMProvider,
    laravel: LaravelToolClient,
    tenant_id: str,
    user_id: int,
    session_id: int,
    message: str,
    messages: list[dict[str, str]],
    conversation_state: dict[str, Any],
    module_scope: str,
    tool_definitions: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
) -> Iterator[object]:
    # Resolve the router before anything else: an unknown scope must fail
    # visibly and before any provider spend.
    router = router_for_scope(module_scope)

    yield Trace(kind="routing", label="module_scope", detail={"module_scope": module_scope})
    yield Trace(
        kind="provider",
        label="model",
        detail={"provider": provider.name, "model": provider.model},
    )
    if conversation_state:
        yield Trace(kind="state", label="conversation_state", detail={"keys": sorted(conversation_state.keys())})

    tools, skipped_tools = parse_tool_definitions(tool_definitions)
    if skipped_tools:
        yield Trace(
            kind="routing",
            label="skipped_tool_definitions",
            detail={"skipped": list(skipped_tools)},
        )

    conversation = build_conversation(messages, message)
    input_tokens = 0
    output_tokens = 0
    last_tool_name = ""
    last_tool_input: dict[str, Any] = {}
    last_tool_output: dict[str, Any] = {}

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await provider.complete(
            CompletionRequest(
                system=router.system_prompt,
                messages=tuple(conversation),
                tools=tools,
                max_tokens=max_tokens,
                temperature=temperature,
            )
        )
        input_tokens += response.usage.input_tokens
        output_tokens += response.usage.output_tokens

        tool_calls = response.tool_calls()
        if not tool_calls:
            text = response.text()
            for chunk in split_text(text or "I could not generate a response."):
                yield TextDelta(chunk)
            yield Trace(
                kind="usage",
                label="tokens",
                detail={"input_tokens": input_tokens, "output_tokens": output_tokens},
            )
            chips = router.build_suggestions(
                last_tool_name, last_tool_input, last_tool_output, conversation_state
            )
            if chips:
                suggestions = validated_component("follow_up_suggestions", {"suggestions": chips})
                if suggestions is not None:
                    yield ComponentReady(type=suggestions.type.value, props=suggestions.props)
            return

        conversation.append(ChatMessage(role="assistant", parts=response.parts))
        tool_results = []
        for call in tool_calls:
            yield ToolStarted(call_id=call.call_id, name=call.name, params=call.arguments)
            started = time.perf_counter()
            output = await laravel.execute_tool(
                tenant_id=tenant_id,
                user_id=user_id,
                session_id=session_id,
                tool_name=call.name,
                tool_input=call.arguments,
            )
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            yield ToolCompleted(
                call_id=call.call_id,
                name=call.name,
                ms=elapsed_ms,
                detail={"count": output.get("count"), "summary": summarize_output(call.name, output)},
            )
            component = component_for_tool(call.name, output)
            if component is not None and component.type in router.allowed_component_types:
                yield ComponentReady(type=component.type.value, props=component.props)
            yield StatePatch(router.state_patch_for_tool(call.name, call.arguments, output))
            last_tool_name = call.name
            last_tool_input = call.arguments
            last_tool_output = output
            tool_results.append(
                ToolResultPart(call_id=call.call_id, name=call.name, content=json.dumps(output))
            )
        conversation.append(ChatMessage(role="tool", parts=tuple(tool_results)))

    yield TextDelta("I reached the maximum number of tool steps for this turn. Please ask a narrower question.")


def split_text(text: str) -> Iterator[str]:
    parts = text.replace("\n", "\n ").split(" ")
    for part in parts:
        if part:
            yield part + " "


def summarize_output(tool_name: str, output: dict[str, Any]) -> str:
    count = output.get("count")
    if count is not None:
        return f"{count} rows"
    if tool_name == "pos_sales_summary":
        current = output.get("current_period", {})
        return f"{current.get('transactions', 0)} transactions"
    return "completed"
