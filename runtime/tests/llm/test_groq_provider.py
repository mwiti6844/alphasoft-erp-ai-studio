from __future__ import annotations

import json

import httpx
import pytest

from app.llm.groq_provider import GroqProvider, build_payload, parse_response
from app.llm.provider import ProviderError
from app.llm.types import (
    ChatMessage,
    CompletionRequest,
    StopReason,
    TextPart,
    ToolCallPart,
    ToolDefinition,
    ToolResultPart,
)

MODEL = "llama-3.3-70b-versatile"


def request_with(messages: tuple[ChatMessage, ...], tools: tuple[ToolDefinition, ...] = ()) -> CompletionRequest:
    return CompletionRequest(
        system="You are a test assistant.",
        messages=messages,
        tools=tools,
        max_tokens=512,
        temperature=0.2,
    )


class TestBuildPayload:
    def test_system_message_comes_first(self):
        payload = build_payload(
            request_with((ChatMessage(role="user", parts=(TextPart("hi"),)),)), MODEL
        )
        assert payload["messages"][0] == {"role": "system", "content": "You are a test assistant."}
        assert payload["messages"][1] == {"role": "user", "content": "hi"}
        assert payload["model"] == MODEL
        assert "tools" not in payload

    def test_assistant_tool_calls_serialize_arguments_as_json_string(self):
        message = ChatMessage(
            role="assistant",
            parts=(
                TextPart("Checking sales."),
                ToolCallPart(call_id="call_1", name="pos_sales_summary", arguments={"period_days": 14}),
            ),
        )
        payload = build_payload(request_with((message,)), MODEL)
        wire = payload["messages"][1]
        assert wire["role"] == "assistant"
        assert wire["content"] == "Checking sales."
        assert wire["tool_calls"] == [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "pos_sales_summary", "arguments": json.dumps({"period_days": 14})},
            }
        ]

    def test_tool_message_fans_out_one_wire_message_per_result(self):
        message = ChatMessage(
            role="tool",
            parts=(
                ToolResultPart(call_id="call_1", name="a", content='{"count":1}'),
                ToolResultPart(call_id="call_2", name="b", content='{"count":2}'),
            ),
        )
        payload = build_payload(request_with((message,)), MODEL)
        assert payload["messages"][1:] == [
            {"role": "tool", "tool_call_id": "call_1", "content": '{"count":1}'},
            {"role": "tool", "tool_call_id": "call_2", "content": '{"count":2}'},
        ]

    def test_tools_and_tool_choice_present_when_tools_defined(self):
        tool = ToolDefinition(
            name="pos_top_selling_items",
            description="Top sellers",
            parameters={"type": "object", "properties": {}},
        )
        payload = build_payload(
            request_with((ChatMessage(role="user", parts=(TextPart("hi"),)),), (tool,)), MODEL
        )
        assert payload["tool_choice"] == "auto"
        assert payload["tools"] == [
            {
                "type": "function",
                "function": {
                    "name": "pos_top_selling_items",
                    "description": "Top sellers",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]


class TestParseResponse:
    def test_text_only_response(self):
        data = {
            "choices": [{"message": {"content": "Hello."}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }
        response = parse_response(data, MODEL)
        assert response.text() == "Hello."
        assert response.stop_reason is StopReason.END_TURN
        assert response.usage.input_tokens == 10
        assert response.usage.output_tokens == 5
        assert response.provider == "groq"
        assert response.model == MODEL

    def test_tool_call_arguments_parsed_from_json_string(self):
        data = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "tool_calls": [
                            {
                                "id": "call_9",
                                "type": "function",
                                "function": {"name": "pos_sales_summary", "arguments": '{"period_days": 30}'},
                            }
                        ],
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
        response = parse_response(data, MODEL)
        calls = response.tool_calls()
        assert response.stop_reason is StopReason.TOOL_USE
        assert calls == (ToolCallPart(call_id="call_9", name="pos_sales_summary", arguments={"period_days": 30}),)

    def test_malformed_tool_arguments_raise_provider_error(self):
        data = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [
                            {"id": "c", "function": {"name": "pos_sales_summary", "arguments": "{not json"}}
                        ]
                    },
                    "finish_reason": "tool_calls",
                }
            ]
        }
        with pytest.raises(ProviderError, match="malformed tool arguments for pos_sales_summary"):
            parse_response(data, MODEL)

    def test_non_object_tool_arguments_raise_provider_error(self):
        data = {
            "choices": [
                {
                    "message": {"tool_calls": [{"id": "c", "function": {"name": "x", "arguments": "[1,2]"}}]},
                    "finish_reason": "tool_calls",
                }
            ]
        }
        with pytest.raises(ProviderError, match="non-object tool arguments"):
            parse_response(data, MODEL)

    def test_finish_reason_length_maps_to_max_tokens(self):
        data = {"choices": [{"message": {"content": "truncated"}, "finish_reason": "length"}]}
        assert parse_response(data, MODEL).stop_reason is StopReason.MAX_TOKENS

    def test_finish_reason_stop_with_tool_calls_treated_as_tool_use(self):
        data = {
            "choices": [
                {
                    "message": {
                        "tool_calls": [{"id": "c", "function": {"name": "x", "arguments": "{}"}}]
                    },
                    "finish_reason": "stop",
                }
            ]
        }
        assert parse_response(data, MODEL).stop_reason is StopReason.TOOL_USE

    def test_missing_usage_defaults_to_zero(self):
        data = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]}
        response = parse_response(data, MODEL)
        assert response.usage.input_tokens == 0
        assert response.usage.output_tokens == 0

    def test_empty_choices_raise_provider_error(self):
        with pytest.raises(ProviderError, match="no choices"):
            parse_response({"choices": []}, MODEL)


def provider_with_handler(handler) -> GroqProvider:
    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)
    return GroqProvider(api_key="test-key", model=MODEL, client=client)


class TestHttpErrors:
    async def test_rate_limit_error_surfaces_status_and_message(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(429, json={"error": {"message": "Rate limit reached"}})

        provider = provider_with_handler(handler)
        with pytest.raises(ProviderError) as excinfo:
            await provider.complete(
                request_with((ChatMessage(role="user", parts=(TextPart("hi"),)),))
            )
        assert excinfo.value.status_code == 429
        assert "Rate limit reached" in str(excinfo.value)

    async def test_non_json_error_body_still_raises_cleanly(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(500, text="upstream exploded")

        provider = provider_with_handler(handler)
        with pytest.raises(ProviderError) as excinfo:
            await provider.complete(
                request_with((ChatMessage(role="user", parts=(TextPart("hi"),)),))
            )
        assert excinfo.value.status_code == 500
        assert "upstream exploded" in str(excinfo.value)

    async def test_successful_round_trip(self):
        def handler(request: httpx.Request) -> httpx.Response:
            body = json.loads(request.content)
            assert body["model"] == MODEL
            assert request.url.path == "/openai/v1/chat/completions"
            return httpx.Response(
                200,
                json={
                    "choices": [{"message": {"content": "All good."}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 2},
                },
            )

        provider = provider_with_handler(handler)
        response = await provider.complete(
            request_with((ChatMessage(role="user", parts=(TextPart("hi"),)),))
        )
        assert response.text() == "All good."
        assert response.usage.input_tokens == 3
