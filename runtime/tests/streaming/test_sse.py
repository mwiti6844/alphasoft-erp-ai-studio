from __future__ import annotations

from app.agents.events import TextDelta
from app.llm.provider import ProviderError
from app.streaming.sse import async_events_to_sse


async def failing_generator():
    yield TextDelta("partial ")
    raise ProviderError("groq", "Rate limit reached (429)", status_code=429)


async def test_provider_error_becomes_error_frame_then_done():
    frames = [frame async for frame in async_events_to_sse(failing_generator())]
    assert frames[0].startswith("event: token\n")
    assert 'groq: Rate limit reached (429)' in frames[1]
    assert frames[1].startswith("event: error\n")
    assert frames[-1] == "event: done\ndata: {}\n\n"


async def empty_generator():
    return
    yield  # pragma: no cover


async def test_done_frame_always_emitted():
    frames = [frame async for frame in async_events_to_sse(empty_generator())]
    assert frames == ["event: done\ndata: {}\n\n"]
