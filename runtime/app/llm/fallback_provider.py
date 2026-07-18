"""A provider that falls back to a secondary backend on transient failures.

Keeps a cheap primary (e.g. Groq) as the default and only reaches for the
secondary (e.g. Anthropic) when the primary is rate-limited or briefly
unavailable — so a saturated free tier degrades to a working answer instead
of an empty panel.
"""

from __future__ import annotations

from app.llm.provider import LLMProvider, ProviderError
from app.llm.types import CompletionRequest, CompletionResponse

# Rate limit (429), overloaded (529), and transient upstream errors (5xx).
FALLBACK_STATUS_CODES = frozenset({429, 500, 502, 503, 504, 529})


class FallbackProvider:
    name = "fallback"

    def __init__(self, primary: LLMProvider, secondary: LLMProvider) -> None:
        self._primary = primary
        self._secondary = secondary
        # Report the primary's identity so traces reflect the default path.
        self.name = primary.name
        self.model = primary.model

    async def complete(self, request: CompletionRequest) -> CompletionResponse:
        try:
            return await self._primary.complete(request)
        except ProviderError as exc:
            if exc.status_code in FALLBACK_STATUS_CODES:
                return await self._secondary.complete(request)
            raise
