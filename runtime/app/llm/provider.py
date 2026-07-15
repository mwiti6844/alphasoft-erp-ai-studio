"""The provider contract every LLM backend implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from app.llm.types import CompletionRequest, CompletionResponse


class ProviderError(RuntimeError):
    """A provider-level failure with a user-presentable message.

    These messages flow to the SSE `error` frame, so keep them clear and
    free of secrets/internal paths.
    """

    def __init__(self, provider: str, message: str, status_code: int | None = None) -> None:
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status_code = status_code


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    async def complete(self, request: CompletionRequest) -> CompletionResponse: ...
