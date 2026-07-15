"""POS module router — restaurant and retail analytics."""

from __future__ import annotations

from typing import Any

from app.agents.components import ComponentType, state_patch_for_tool
from app.agents.modules.base import BASE_RULES, ModuleRouter, Suggestion, capped

JOURNEY = "pos_analytics"

POS_SECTION = """
Module: POS analytics (restaurant and retail).
- POS transactions carry a vertical (restaurant, retail, pharmacy). Frame
  restaurant answers around menu items and dishes, retail answers around
  products and stock, and note when figures span more than one vertical.
- Reorder candidates are computed from stock cover and sales velocity, not
  from a configured reorder point.
- Advertising honesty: no advertising-performance data exists in this system
  (no impressions, clicks, or campaign spend). If asked which ads worked or
  about ad performance, say that plainly and offer what is answerable
  instead: top sellers, lagging items, sales summaries, and promotion or
  sales-velocity analysis. Never estimate or imply ad performance figures.
"""

SYSTEM_PROMPT = BASE_RULES + POS_SECTION

_TOP = {"id": "top", "label": "Top sellers", "message": "Show top selling items for the last 14 days"}
_LAGGING = {"id": "lagging", "label": "Lagging items", "message": "Which items have stopped selling in the last 30 days?"}
_REORDER = {"id": "reorder", "label": "Reorder candidates", "message": "Which items should we reorder this week?"}
_SUMMARY = {"id": "summary", "label": "Sales summary", "message": "How were sales in the last 14 days?"}
_WIDEN = {"id": "widen", "label": "Widen the window", "message": "Ask the same question over the last 30 days"}

_AFTER_TOOL: dict[str, list[Suggestion]] = {
    "pos_top_selling_items": [_LAGGING, _SUMMARY, _REORDER],
    "pos_lagging_items": [_TOP, _SUMMARY, _REORDER],
    "pos_sales_summary": [_TOP, _LAGGING, _REORDER],
    "inventory_reorder_candidates": [_TOP, _LAGGING, _SUMMARY],
}

_DEFAULT = [_TOP, _LAGGING, _REORDER]


def build_suggestions(
    last_tool_name: str,
    last_tool_input: dict[str, Any],
    last_tool_output: dict[str, Any],
    conversation_state: dict[str, Any],
) -> list[Suggestion]:
    suggestions = list(_AFTER_TOOL.get(last_tool_name, _DEFAULT))
    if last_tool_name and last_tool_output.get("count") == 0:
        suggestions = [_WIDEN, *suggestions]
    return capped(suggestions)


def build_state_patch(
    tool_name: str, tool_input: dict[str, Any], output: dict[str, Any]
) -> dict[str, Any]:
    return state_patch_for_tool(tool_name, tool_input, output, journey=JOURNEY)


POS_ROUTER = ModuleRouter(
    scope="pos",
    system_prompt=SYSTEM_PROMPT,
    allowed_component_types=frozenset(
        {
            ComponentType.TOP_ITEMS_TABLE,
            ComponentType.LAGGING_ITEMS_TABLE,
            ComponentType.SALES_SUMMARY_CARD,
            ComponentType.REORDER_CANDIDATES_TABLE,
            ComponentType.FOLLOW_UP_SUGGESTIONS,
        }
    ),
    build_suggestions=build_suggestions,
    state_patch_for_tool=build_state_patch,
)
