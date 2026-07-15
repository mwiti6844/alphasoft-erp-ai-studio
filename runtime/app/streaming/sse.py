from __future__ import annotations

import json
from collections.abc import AsyncIterable, Iterable, Iterator

from app.agents.components import validated_component
from app.agents.events import ComponentReady, StatePatch, TextDelta, ToolCompleted, ToolStarted, Trace


def frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, separators=(',', ':'))}\n\n"


def events_to_sse(events: Iterable[object]) -> Iterator[str]:
    try:
        for event in events:
            if isinstance(event, TextDelta):
                if event.text:
                    yield frame("token", {"text": event.text})
            elif isinstance(event, ToolStarted):
                yield frame("tool", {"call_id": event.call_id, "name": event.name, "status": "started", "params": event.params})
            elif isinstance(event, ToolCompleted):
                yield frame("tool", {"call_id": event.call_id, "name": event.name, "status": "completed", "ms": event.ms, "detail": event.detail})
            elif isinstance(event, Trace):
                yield frame("trace", {"kind": event.kind, "label": event.label, "detail": event.detail})
            elif isinstance(event, ComponentReady):
                component = validated_component(event.type, event.props)
                if component is None:
                    yield frame("error", {"message": f"Invalid component payload for {event.type}"})
                    continue
                yield frame("component", {"type": component.type.value, "props": component.props})
            elif isinstance(event, StatePatch):
                yield frame("state_patch", event.values)
    except Exception as exc:
        yield frame("error", {"message": f"The AI runtime hit an error: {exc}"})
    yield frame("done", {})


async def async_events_to_sse(events: AsyncIterable[object]):
    try:
        async for event in events:
            if isinstance(event, TextDelta):
                if event.text:
                    yield frame("token", {"text": event.text})
            elif isinstance(event, ToolStarted):
                yield frame("tool", {"call_id": event.call_id, "name": event.name, "status": "started", "params": event.params})
            elif isinstance(event, ToolCompleted):
                yield frame("tool", {"call_id": event.call_id, "name": event.name, "status": "completed", "ms": event.ms, "detail": event.detail})
            elif isinstance(event, Trace):
                yield frame("trace", {"kind": event.kind, "label": event.label, "detail": event.detail})
            elif isinstance(event, ComponentReady):
                component = validated_component(event.type, event.props)
                if component is None:
                    yield frame("error", {"message": f"Invalid component payload for {event.type}"})
                    continue
                yield frame("component", {"type": component.type.value, "props": component.props})
            elif isinstance(event, StatePatch):
                yield frame("state_patch", event.values)
    except Exception as exc:
        yield frame("error", {"message": f"The AI runtime hit an error: {exc}"})
    yield frame("done", {})
