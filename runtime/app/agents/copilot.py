from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

from app.agents.components import component_for_tool, validated_component
from app.agents.events import ComponentReady, StatePatch, TextDelta, ToolCompleted, ToolStarted, Trace
from app.agents.modules.registry import router_for_scope
from app.clients.laravel import LaravelToolClient
from app.knowledge.flows import flow_context_prompt, retrieve_flows
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
    ui_action: dict[str, Any] | None,
    user_memory: dict[str, Any],
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
    if user_memory:
        yield Trace(kind="memory", label="user_memory", detail={"keys": sorted(user_memory.keys())})

    flow_matches = retrieve_flows(message, module_scope)
    if flow_matches:
        yield Trace(
            kind="knowledge",
            label="flow_matches",
            detail={
                "sources": [
                    {
                        "id": match.resource.id,
                        "score": match.score,
                        "title": match.resource.title,
                    }
                    for match in flow_matches
                ]
            },
        )
    elif is_likely_process_question(message):
        yield Trace(kind="knowledge", label="flow_matches", detail={"sources": []})

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

    if ui_action is not None:
        handled = execute_ui_action(
            ui_action=ui_action,
            router=router,
            laravel=laravel,
            tenant_id=tenant_id,
            user_id=user_id,
            session_id=session_id,
            conversation_state=conversation_state,
        )
        async for event in handled:
            yield event
        return

    for _ in range(MAX_TOOL_ITERATIONS):
        response = await provider.complete(
            CompletionRequest(
                system=system_prompt(
                    router.system_prompt,
                    user_memory=user_memory,
                    flow_matches=flow_matches,
                    message=message,
                ),
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
            if flow_matches:
                citations = validated_component(
                    "flow_citations",
                    {"sources": [match.resource.citation() for match in flow_matches]},
                )
                if citations is not None and citations.type in router.allowed_component_types:
                    yield ComponentReady(type=citations.type.value, props=citations.props)
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


async def execute_ui_action(
    *,
    ui_action: dict[str, Any],
    router: Any,
    laravel: LaravelToolClient,
    tenant_id: str,
    user_id: int,
    session_id: int,
    conversation_state: dict[str, Any],
):
    if ui_action.get("type") != "run_tool":
        yield TextDelta("I can only run read-only tool actions from suggestions right now.")
        return

    tool_name = str(ui_action.get("tool", ""))
    tool_input = ui_action.get("input")
    if not tool_name or not isinstance(tool_input, dict):
        yield TextDelta("That suggestion is no longer valid. Please ask again.")
        return

    call_id = "ui_action_1"
    yield Trace(kind="action", label="ui_action", detail={"type": "run_tool", "tool": tool_name})
    yield ToolStarted(call_id=call_id, name=tool_name, params=tool_input)
    started = time.perf_counter()
    output = await laravel.execute_tool(
        tenant_id=tenant_id,
        user_id=user_id,
        session_id=session_id,
        tool_name=tool_name,
        tool_input=tool_input,
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    yield ToolCompleted(
        call_id=call_id,
        name=tool_name,
        ms=elapsed_ms,
        detail={"count": output.get("count"), "summary": summarize_output(tool_name, output)},
    )
    component = component_for_tool(tool_name, output)
    if component is not None and component.type in router.allowed_component_types:
        yield ComponentReady(type=component.type.value, props=component.props)
    yield StatePatch(router.state_patch_for_tool(tool_name, tool_input, output))
    yield TextDelta("Here are the results from that suggestion.")
    yield Trace(kind="usage", label="tokens", detail={"input_tokens": 0, "output_tokens": 0})
    chips = router.build_suggestions(tool_name, tool_input, output, conversation_state)
    if chips:
        suggestions = validated_component("follow_up_suggestions", {"suggestions": chips})
        if suggestions is not None:
            yield ComponentReady(type=suggestions.type.value, props=suggestions.props)


def split_text(text: str) -> Iterator[str]:
    parts = text.replace("\n", "\n ").split(" ")
    for part in parts:
        if part:
            yield part + " "


def system_prompt(
    base_prompt: str,
    *,
    user_memory: dict[str, Any],
    flow_matches: tuple[Any, ...],
    message: str,
) -> str:
    prompt = system_prompt_with_memory(base_prompt, user_memory)
    if flow_matches or is_likely_process_question(message):
        prompt += flow_context_prompt(flow_matches)
    return prompt


def system_prompt_with_memory(system_prompt: str, user_memory: dict[str, Any]) -> str:
    lines = memory_prompt_lines(user_memory)
    if not lines:
        return system_prompt

    return system_prompt + "\nUser preferences from explicit memory:\n" + "\n".join(lines) + "\n"


def memory_prompt_lines(user_memory: dict[str, Any]) -> list[str]:
    labels = {
        "preferred_module_scope": "Preferred module scope",
        "default_branch_id": "Default branch id",
        "default_warehouse_id": "Default warehouse id",
        "default_reporting_period": "Default reporting period",
        "number_display": "Number display",
        "answer_verbosity": "Answer verbosity",
    }
    lines: list[str] = []
    for key in sorted(labels):
        value = user_memory.get(key)
        if isinstance(value, (str, int, float, bool)):
            lines.append(f"- {labels[key]}: {value}")
    return lines


def is_likely_process_question(message: str) -> bool:
    normalized = message.lower().replace("’", "'")
    return any(
        pattern in normalized
        for pattern in (
            "how do i",
            "how can i",
            "why can't",
            "why cant",
            "why can’t",
            "what does",
            "where do i",
            "set up",
            "setup",
            "configure",
            "create",
            "add",
            "access denied",
        )
    )


def summarize_output(tool_name: str, output: dict[str, Any]) -> str:
    count = output.get("count")
    if count is not None:
        return f"{count} rows"
    if tool_name == "pos_sales_summary":
        current = output.get("current_period", {})
        return f"{current.get('transactions', 0)} transactions"
    return "completed"
