"""Provider-neutral message and completion types.

Every LLM provider translates between these shapes and its own wire format
at its own boundary. Nothing outside app/llm may depend on a vendor SDK's
message shapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Literal, Union

Role = Literal["user", "assistant", "tool"]


@dataclass(frozen=True)
class TextPart:
    text: str


@dataclass(frozen=True)
class ToolCallPart:
    call_id: str
    name: str
    # Always a parsed dict internally — providers that receive JSON-string
    # arguments must parse (and fail loudly) before constructing this.
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResultPart:
    call_id: str
    name: str
    content: str


Part = Union[TextPart, ToolCallPart, ToolResultPart]


@dataclass(frozen=True)
class ChatMessage:
    role: Role
    parts: tuple[Part, ...]

    def text(self) -> str:
        return "".join(part.text for part in self.parts if isinstance(part, TextPart))


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    description: str
    parameters: dict[str, Any]


class StopReason(str, Enum):
    END_TURN = "end_turn"
    TOOL_USE = "tool_use"
    MAX_TOKENS = "max_tokens"
    OTHER = "other"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class CompletionRequest:
    system: str
    messages: tuple[ChatMessage, ...]
    tools: tuple[ToolDefinition, ...]
    max_tokens: int
    temperature: float


@dataclass(frozen=True)
class CompletionResponse:
    parts: tuple[Part, ...]
    stop_reason: StopReason
    usage: Usage
    provider: str
    model: str

    def tool_calls(self) -> tuple[ToolCallPart, ...]:
        return tuple(part for part in self.parts if isinstance(part, ToolCallPart))

    def text(self) -> str:
        return "".join(part.text for part in self.parts if isinstance(part, TextPart))
