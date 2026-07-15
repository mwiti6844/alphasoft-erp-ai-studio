"""Module router contract and shared prompt rules.

A ModuleRouter owns everything module-specific: the system prompt, which
generative UI components may be emitted, deterministic follow-up
suggestions, and state-patch construction. The copilot loop stays generic.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agents.components import ComponentType

# {id, label, message} — matches FollowUpSuggestionsProps entries.
Suggestion = dict[str, str]

# (last_tool_name, last_tool_input, last_tool_output, conversation_state).
# last_tool_name is "" when the turn used no tools — builders must return
# scope-default suggestions in that case.
SuggestionBuilder = Callable[
    [str, dict[str, Any], dict[str, Any], dict[str, Any]], list[Suggestion]
]

# (tool_name, tool_input, output) -> state patch dict (whitelisted keys only).
StatePatchBuilder = Callable[[str, dict[str, Any], dict[str, Any]], dict[str, Any]]

MAX_SUGGESTIONS = 4

BASE_RULES = """You are AlphaSoft ERP AI Studio.

You help authenticated ERP users understand their own tenant data.
Rules:
- Use tools for all ERP facts. Never invent numbers.
- SQL/Laravel tools compute figures; you narrate and explain.
- If a tool returns empty data, say that clearly.
- Do not propose direct destructive actions.
- Keep answers concise and operational.
"""


@dataclass(frozen=True)
class ModuleRouter:
    scope: str
    system_prompt: str
    allowed_component_types: frozenset[ComponentType]
    build_suggestions: SuggestionBuilder
    state_patch_for_tool: StatePatchBuilder


def capped(suggestions: list[Suggestion]) -> list[Suggestion]:
    return suggestions[:MAX_SUGGESTIONS]
