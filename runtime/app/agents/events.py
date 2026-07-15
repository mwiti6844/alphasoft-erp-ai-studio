from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TextDelta:
    text: str


@dataclass
class ToolStarted:
    call_id: str
    name: str
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCompleted:
    call_id: str
    name: str
    ms: int
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class ComponentReady:
    type: str
    props: dict[str, Any]


@dataclass
class Trace:
    kind: str
    label: str
    detail: dict[str, Any] = field(default_factory=dict)


@dataclass
class StatePatch:
    values: dict[str, Any]


AgentEvent = TextDelta | ToolStarted | ToolCompleted | ComponentReady | Trace | StatePatch
