"""Inventory module router — stock balances, movements, reorder cover."""

from __future__ import annotations

from typing import Any

from app.agents.components import ComponentType, state_patch_for_tool
from app.agents.modules.base import BASE_RULES, ModuleRouter, Suggestion, capped

JOURNEY = "inventory"

INVENTORY_SECTION = """
Module: inventory.
- Focus on stock balances, stock movements, warehouses, and stock cover.
- Reorder candidates are based on stock cover and sales velocity from
  completed sales, not a configured reorder point — say so when presenting
  them.
- This session is inventory-focused: do not volunteer POS sales analytics;
  answer sales-side questions only as far as tool outputs support them.
"""

SYSTEM_PROMPT = BASE_RULES + INVENTORY_SECTION

_BALANCES = {"id": "balances", "label": "Stock balances", "message": "Show current stock balances"}
_MOVEMENTS = {"id": "movements", "label": "Recent movements", "message": "Show recent stock movements"}
_REORDER = {"id": "reorder", "label": "Reorder candidates", "message": "Which items should we reorder this week?"}
_WAREHOUSES = {"id": "warehouses", "label": "Warehouses", "message": "List our warehouses"}
_WIDEN = {"id": "widen", "label": "Widen the window", "message": "Ask the same question over a longer period"}

_AFTER_TOOL: dict[str, list[Suggestion]] = {
    "inventory_balance": [_MOVEMENTS, _REORDER],
    "inventory_movements": [_BALANCES, _REORDER],
    "warehouse_list": [_BALANCES, _MOVEMENTS],
    "inventory_reorder_candidates": [_BALANCES, _MOVEMENTS],
}

_DEFAULT = [_BALANCES, _MOVEMENTS, _REORDER]


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


INVENTORY_ROUTER = ModuleRouter(
    scope="inventory",
    system_prompt=SYSTEM_PROMPT,
    allowed_component_types=frozenset(
        {
            ComponentType.REORDER_CANDIDATES_TABLE,
            ComponentType.FOLLOW_UP_SUGGESTIONS,
        }
    ),
    build_suggestions=build_suggestions,
    state_patch_for_tool=build_state_patch,
)
