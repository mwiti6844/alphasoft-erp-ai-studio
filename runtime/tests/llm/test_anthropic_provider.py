from __future__ import annotations

from types import SimpleNamespace

from app.llm.anthropic_provider import build_messages, build_tools, map_stop_reason, parts_from_content
from app.llm.types import (
    ChatMessage,
    CompletionRequest,
    StopReason,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)


class TestBuildMessages:
    def test_user_message_becomes_plain_content(self):
        wire = build_messages((ChatMessage(role="user", parts=(TextPart("hello"),)),))
        assert wire == [{"role": "user", "content": "hello"}]

    def test_assistant_message_with_tool_call_becomes_blocks(self):
        message = ChatMessage(
            role="assistant",
            parts=(
                TextPart("Let me check."),
                ToolCallPart(call_id="toolu_1", name="pos_sales_summary", arguments={"period_days": 7}),
            ),
        )
        wire = build_messages((message,))
        assert wire == [
            {
                "role": "assistant",
                "content": [
                    {"type": "text", "text": "Let me check."},
                    {
                        "type": "tool_use",
                        "id": "toolu_1",
                        "name": "pos_sales_summary",
                        "input": {"period_days": 7},
                    },
                ],
            }
        ]

    def test_tool_message_becomes_user_tool_results(self):
        message = ChatMessage(
            role="tool",
            parts=(ToolResultPart(call_id="toolu_1", name="pos_sales_summary", content='{"count":3}'),),
        )
        wire = build_messages((message,))
        assert wire == [
            {
                "role": "user",
                "content": [
                    {"type": "tool_result", "tool_use_id": "toolu_1", "content": '{"count":3}'}
                ],
            }
        ]


def test_build_tools_uses_input_schema_key():
    request = CompletionRequest(
        system="s",
        messages=(),
        tools=(
            ToolDefinition(
                name="catalog_search",
                description="Search catalog",
                parameters={"type": "object", "properties": {}},
            ),
        ),
        max_tokens=128,
        temperature=0.0,
    )
    assert build_tools(request) == [
        {
            "name": "catalog_search",
            "description": "Search catalog",
            "input_schema": {"type": "object", "properties": {}},
        }
    ]


class TestPartsFromContent:
    def test_text_and_tool_use_blocks_translate(self):
        blocks = [
            SimpleNamespace(type="text", text="Here you go."),
            SimpleNamespace(type="tool_use", id="toolu_2", name="catalog_search", input={"query": "rice"}),
        ]
        parts = parts_from_content(blocks)
        assert parts == (
            TextPart(text="Here you go."),
            ToolCallPart(call_id="toolu_2", name="catalog_search", arguments={"query": "rice"}),
        )

    def test_non_dict_tool_input_becomes_empty_dict(self):
        blocks = [SimpleNamespace(type="tool_use", id="t", name="x", input="[]")]
        parts = parts_from_content(blocks)
        assert parts == (ToolCallPart(call_id="t", name="x", arguments={}),)

    def test_unknown_block_types_are_skipped(self):
        blocks = [SimpleNamespace(type="thinking", thinking="...")]
        assert parts_from_content(blocks) == ()


def test_stop_reason_mapping():
    assert map_stop_reason("end_turn") is StopReason.END_TURN
    assert map_stop_reason("tool_use") is StopReason.TOOL_USE
    assert map_stop_reason("max_tokens") is StopReason.MAX_TOKENS
    assert map_stop_reason("pause_turn") is StopReason.OTHER
    assert map_stop_reason(None) is StopReason.OTHER
