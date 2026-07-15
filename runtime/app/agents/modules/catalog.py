"""Catalog module router — items, SKUs, pricing, data quality."""

from __future__ import annotations

from typing import Any

from app.agents.components import ComponentType, state_patch_for_tool
from app.agents.modules.base import BASE_RULES, ModuleRouter, Suggestion, capped

JOURNEY = "catalog"

CATALOG_SECTION = """
Module: catalog.
- Focus on catalog items: names, SKUs, types, status, pricing, and
  stockability/data quality.
- Search needs a term from the user; when a request is too vague to search,
  ask what item name or SKU to look for instead of guessing.
- This session is catalog-focused: do not make POS sales-analytics claims;
  sales questions belong to the POS copilot scope.
"""

SYSTEM_PROMPT = BASE_RULES + CATALOG_SECTION

# Default chips are natural-language prompts, not pretend-executable actions,
# because catalog_search requires a user-supplied query.
_SEARCH = {"id": "search", "label": "Search catalog", "message": "Search by item name or SKU"}
_DETAIL = {"id": "detail", "label": "Item details", "message": "Show details for a catalog item"}
_QUALITY = {"id": "quality", "label": "Data quality", "message": "Help me check an item's SKU, status, and pricing"}

_DEFAULT = [_SEARCH, _DETAIL, _QUALITY]


def build_suggestions(
    last_tool_name: str,
    last_tool_input: dict[str, Any],
    last_tool_output: dict[str, Any],
    conversation_state: dict[str, Any],
) -> list[Suggestion]:
    if last_tool_name == "catalog_search":
        first_name = _first_item_name(last_tool_output)
        if first_name:
            return capped(
                [
                    {
                        "id": "detail_first",
                        "label": "First result details",
                        "message": f"Show details for {first_name}",
                    },
                    _SEARCH,
                ]
            )
        return capped([_SEARCH, _DETAIL])
    if last_tool_name == "catalog_item_detail":
        return capped([_SEARCH, _QUALITY])
    return capped(_DEFAULT)


def _first_item_name(output: dict[str, Any]) -> str:
    items = output.get("items")
    if isinstance(items, list) and items and isinstance(items[0], dict):
        name = items[0].get("name")
        if isinstance(name, str) and name.strip():
            return name.strip()[:100]
    return ""


def build_state_patch(
    tool_name: str, tool_input: dict[str, Any], output: dict[str, Any]
) -> dict[str, Any]:
    return state_patch_for_tool(tool_name, tool_input, output, journey=JOURNEY)


CATALOG_ROUTER = ModuleRouter(
    scope="catalog",
    system_prompt=SYSTEM_PROMPT,
    allowed_component_types=frozenset({ComponentType.FOLLOW_UP_SUGGESTIONS}),
    build_suggestions=build_suggestions,
    state_patch_for_tool=build_state_patch,
)
