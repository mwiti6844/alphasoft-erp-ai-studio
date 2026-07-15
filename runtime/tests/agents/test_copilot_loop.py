from __future__ import annotations

import pytest

from app.agents.copilot import MAX_TOOL_ITERATIONS, build_conversation, parse_tool_definitions, run_copilot
from app.agents.events import ComponentReady, StatePatch, TextDelta, ToolCompleted, ToolStarted, Trace
from app.agents.modules.registry import UnknownModuleScopeError
from app.llm.types import (
    CompletionResponse,
    StopReason,
    TextPart,
    ToolCallPart,
    Usage,
)
from app.streaming.sse import async_events_to_sse
from tests.conftest import FakeLaravelToolClient, ScriptedProvider


def scripted_response(parts, stop_reason, input_tokens=10, output_tokens=5) -> CompletionResponse:
    return CompletionResponse(
        parts=tuple(parts),
        stop_reason=stop_reason,
        usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
        provider="scripted",
        model="scripted-model",
    )


async def collect_events(provider, laravel, **overrides) -> list[object]:
    kwargs = {
        "provider": provider,
        "laravel": laravel,
        "tenant_id": "tenant-1",
        "user_id": 1,
        "session_id": 1,
        "message": "Show top selling items",
        "messages": [],
        "conversation_state": {},
        "module_scope": "pos",
        "tool_definitions": [
            {"name": "pos_top_selling_items", "description": "Top sellers", "input_schema": {"type": "object", "properties": {}}}
        ],
        "max_tokens": 512,
        "temperature": 0.2,
    }
    kwargs.update(overrides)
    return [event async for event in run_copilot(**kwargs)]


class TestToolUseTurn:
    async def test_tool_call_flows_through_laravel_and_emits_events(self):
        provider = ScriptedProvider(
            [
                scripted_response(
                    [ToolCallPart(call_id="call_1", name="pos_top_selling_items", arguments={"period_days": 14})],
                    StopReason.TOOL_USE,
                ),
                scripted_response([TextPart("Rice topped sales.")], StopReason.END_TURN),
            ]
        )
        laravel = FakeLaravelToolClient(
            output={
                "period_days": 14,
                "count": 1,
                "items": [
                    {"item_id": 7, "item_name": "Rice", "sku": "R-1", "qty_sold": 20.0, "revenue": 500.0, "transaction_count": 9}
                ],
            }
        )

        events = await collect_events(provider, laravel)

        provider_trace = next(e for e in events if isinstance(e, Trace) and e.kind == "provider")
        assert provider_trace.detail == {"provider": "scripted", "model": "scripted-model"}

        assert laravel.calls == [
            {
                "tenant_id": "tenant-1",
                "user_id": 1,
                "session_id": 1,
                "tool_name": "pos_top_selling_items",
                "tool_input": {"period_days": 14},
            }
        ]

        started = next(e for e in events if isinstance(e, ToolStarted))
        completed = next(e for e in events if isinstance(e, ToolCompleted))
        assert started.call_id == completed.call_id == "call_1"
        assert completed.detail["summary"] == "1 rows"

        component = next(e for e in events if isinstance(e, ComponentReady))
        assert component.type == "pos_top_items_table"

        patch = next(e for e in events if isinstance(e, StatePatch))
        assert patch.values["last_tool_name"] == "pos_top_selling_items"
        assert patch.values["displayed_catalog_item_ids"] == [7]

        text = "".join(e.text for e in events if isinstance(e, TextDelta))
        assert "Rice topped sales." in text

        usage_trace = next(e for e in events if isinstance(e, Trace) and e.label == "tokens")
        assert usage_trace.detail == {"input_tokens": 20, "output_tokens": 10}

    async def test_tool_results_are_threaded_back_into_conversation(self):
        provider = ScriptedProvider(
            [
                scripted_response(
                    [ToolCallPart(call_id="call_1", name="pos_top_selling_items", arguments={})],
                    StopReason.TOOL_USE,
                ),
                scripted_response([TextPart("Done.")], StopReason.END_TURN),
            ]
        )
        await collect_events(provider, FakeLaravelToolClient())

        second_request = provider.requests[1]
        roles = [message.role for message in second_request.messages]
        assert roles == ["user", "assistant", "tool"]
        tool_message = second_request.messages[2]
        assert tool_message.parts[0].call_id == "call_1"
        assert '"count": 1' in tool_message.parts[0].content


class TestIterationCap:
    async def test_loop_stops_after_max_iterations_with_visible_message(self):
        responses = [
            scripted_response(
                [ToolCallPart(call_id=f"call_{i}", name="pos_top_selling_items", arguments={})],
                StopReason.TOOL_USE,
            )
            for i in range(MAX_TOOL_ITERATIONS)
        ]
        provider = ScriptedProvider(responses)
        events = await collect_events(provider, FakeLaravelToolClient())

        assert len(provider.requests) == MAX_TOOL_ITERATIONS
        final_text = [e for e in events if isinstance(e, TextDelta)]
        assert "maximum number of tool steps" in "".join(e.text for e in final_text)


class TestBoundaryValidation:
    def test_parse_tool_definitions_skips_nameless_entries(self):
        tools, skipped = parse_tool_definitions(
            [
                {"name": "valid_tool", "description": "ok"},
                {"description": "missing name"},
                {"name": "   "},
            ]
        )
        assert [tool.name for tool in tools] == ["valid_tool"]
        assert skipped == ("#1", "#2")
        assert tools[0].parameters == {"type": "object", "properties": {}}

    async def test_skipped_tool_definitions_emit_trace(self):
        provider = ScriptedProvider([scripted_response([TextPart("Hi.")], StopReason.END_TURN)])
        events = await collect_events(
            provider,
            FakeLaravelToolClient(),
            tool_definitions=[{"description": "nameless"}],
        )
        trace = next(e for e in events if isinstance(e, Trace) and e.label == "skipped_tool_definitions")
        assert trace.detail == {"skipped": ["#0"]}

    def test_build_conversation_appends_current_message_once(self):
        history = [
            {"role": "user", "content": "Show top sellers"},
            {"role": "assistant", "content": "Here they are."},
            {"role": "user", "content": "What about last month?"},
        ]
        conversation = build_conversation(history, "What about last month?")
        assert len(conversation) == 3
        assert conversation[-1].text() == "What about last month?"

        conversation = build_conversation(history[:2], "What about last month?")
        assert len(conversation) == 3
        assert conversation[-1].role == "user"


def follow_up_labels(events: list[object]) -> list[str]:
    component = next(
        e for e in events if isinstance(e, ComponentReady) and e.type == "follow_up_suggestions"
    )
    return [chip["label"] for chip in component.props["suggestions"]]


class TestModuleScopeBehavior:
    async def test_pos_scope_uses_pos_prompt_and_suggestions(self):
        provider = ScriptedProvider([scripted_response([TextPart("Hi.")], StopReason.END_TURN)])
        events = await collect_events(provider, FakeLaravelToolClient(), module_scope="pos")

        assert "Module: POS analytics" in provider.requests[0].system
        assert follow_up_labels(events) == ["Top sellers", "Lagging items", "Reorder candidates"]

    async def test_inventory_scope_has_no_pos_only_suggestions(self):
        provider = ScriptedProvider([scripted_response([TextPart("Hi.")], StopReason.END_TURN)])
        events = await collect_events(provider, FakeLaravelToolClient(), module_scope="inventory")

        assert "Module: inventory" in provider.requests[0].system
        labels = follow_up_labels(events)
        assert "Top sellers" not in labels
        assert "Lagging items" not in labels
        assert "Stock balances" in labels

    async def test_catalog_scope_has_no_pos_only_suggestions(self):
        provider = ScriptedProvider([scripted_response([TextPart("Hi.")], StopReason.END_TURN)])
        events = await collect_events(provider, FakeLaravelToolClient(), module_scope="catalog")

        assert "Module: catalog" in provider.requests[0].system
        labels = follow_up_labels(events)
        assert "Top sellers" not in labels
        assert "Search catalog" in labels

    async def test_unknown_scope_fails_before_any_provider_call(self):
        provider = ScriptedProvider([])
        with pytest.raises(UnknownModuleScopeError, match="Unknown module scope 'billing'"):
            await collect_events(provider, FakeLaravelToolClient(), module_scope="billing")
        assert provider.requests == []

    async def test_unknown_scope_surfaces_as_sse_error_frame(self):
        events = run_copilot(
            provider=ScriptedProvider([]),
            laravel=FakeLaravelToolClient(),
            tenant_id="tenant-1",
            user_id=1,
            session_id=1,
            message="hello",
            messages=[],
            conversation_state={},
            module_scope="billing",
            tool_definitions=[],
            max_tokens=512,
            temperature=0.2,
        )
        frames = [frame async for frame in async_events_to_sse(events)]
        assert frames[0].startswith("event: error\n")
        assert "Unknown module scope 'billing'" in frames[0]
        assert frames[-1] == "event: done\ndata: {}\n\n"

    async def test_component_not_allowed_by_router_is_suppressed(self):
        provider = ScriptedProvider(
            [
                scripted_response(
                    [ToolCallPart(call_id="call_1", name="pos_top_selling_items", arguments={"period_days": 14})],
                    StopReason.TOOL_USE,
                ),
                scripted_response([TextPart("Done.")], StopReason.END_TURN),
            ]
        )
        laravel = FakeLaravelToolClient(
            output={
                "period_days": 14,
                "count": 1,
                "items": [
                    {"item_id": 7, "item_name": "Rice", "sku": "R-1", "qty_sold": 20.0, "revenue": 500.0, "transaction_count": 9}
                ],
            }
        )
        # Catalog scope does not allow pos_top_items_table — the tool still
        # runs and the state patch still flows, but no data component is emitted.
        events = await collect_events(provider, laravel, module_scope="catalog")

        component_types = [e.type for e in events if isinstance(e, ComponentReady)]
        assert "pos_top_items_table" not in component_types
        assert "follow_up_suggestions" in component_types
        assert any(isinstance(e, ToolCompleted) for e in events)
        patch = next(e for e in events if isinstance(e, StatePatch))
        assert patch.values["active_journey"] == "catalog"
