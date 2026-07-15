from __future__ import annotations

from typing import Any

from app.llm.types import CompletionRequest, CompletionResponse


class ScriptedProvider:
    """LLMProvider double that replays canned responses and records requests."""

    name = "scripted"
    model = "scripted-model"

    def __init__(self, responses: list[CompletionResponse]) -> None:
        self._responses = list(responses)
        self.requests: list[CompletionRequest] = []

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        self.requests.append(request)
        if not self._responses:
            raise AssertionError("ScriptedProvider ran out of scripted responses")
        return self._responses.pop(0)


class FakeLaravelToolClient:
    """Records tool executions and returns a canned minimal output."""

    def __init__(self, output: dict[str, Any] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._output = output if output is not None else {"count": 1, "items": []}

    async def execute_tool(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return self._output
