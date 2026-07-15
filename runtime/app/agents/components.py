from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ComponentType(str, Enum):
    TOP_ITEMS_TABLE = "pos_top_items_table"
    LAGGING_ITEMS_TABLE = "pos_lagging_items_table"
    SALES_SUMMARY_CARD = "pos_sales_summary_card"
    REORDER_CANDIDATES_TABLE = "inventory_reorder_candidates_table"
    FOLLOW_UP_SUGGESTIONS = "follow_up_suggestions"


class Component(BaseModel):
    type: ComponentType
    props: dict[str, Any]


class StrictProps(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TopItem(StrictProps):
    item_id: int
    item_name: str
    sku: str | None = None
    qty_sold: float
    revenue: float
    transaction_count: int


class TopItemsProps(StrictProps):
    period_days: int
    items: list[TopItem]


class LaggingItem(StrictProps):
    item_id: int
    item_name: str
    sku: str | None = None
    previous_qty: float
    recent_qty: float
    change_pct: float
    stopped_selling: bool


class LaggingItemsProps(StrictProps):
    window_days: int
    items: list[LaggingItem]


class SalesPeriod(StrictProps):
    revenue: float
    transactions: int
    average_ticket: float
    from_: str = Field(alias="from")
    to: str


class SalesSummaryProps(StrictProps):
    period_days: int
    current_period: SalesPeriod
    previous_period: SalesPeriod
    revenue_change_pct: float | None = None


class ReorderCandidate(StrictProps):
    item_id: int
    item_name: str
    sku: str | None = None
    avg_daily_sales: float
    available_qty: float
    days_of_cover: float
    out_of_stock: bool


class ReorderCandidatesProps(StrictProps):
    velocity_window_days: int
    cover_days_threshold: int
    items: list[ReorderCandidate]


class FollowUpSuggestion(StrictProps):
    id: str
    label: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=300)


class FollowUpSuggestionsProps(StrictProps):
    suggestions: list[FollowUpSuggestion] = Field(min_length=1, max_length=4)


PROP_MODELS: dict[ComponentType, type[BaseModel]] = {
    ComponentType.TOP_ITEMS_TABLE: TopItemsProps,
    ComponentType.LAGGING_ITEMS_TABLE: LaggingItemsProps,
    ComponentType.SALES_SUMMARY_CARD: SalesSummaryProps,
    ComponentType.REORDER_CANDIDATES_TABLE: ReorderCandidatesProps,
    ComponentType.FOLLOW_UP_SUGGESTIONS: FollowUpSuggestionsProps,
}


def validated_component(type_: str, props: dict[str, Any]) -> Component | None:
    try:
        component_type = ComponentType(type_)
        parsed = PROP_MODELS[component_type].model_validate(props)
        return Component(type=component_type, props=parsed.model_dump(by_alias=True, mode="json"))
    except (ValueError, ValidationError):
        return None


def component_for_tool(tool_name: str, output: dict[str, Any]) -> Component | None:
    if tool_name == "pos_top_selling_items":
        return validated_component(
            ComponentType.TOP_ITEMS_TABLE.value,
            {
                "period_days": output.get("period_days", 0),
                "items": output.get("items", []),
            },
        )
    if tool_name == "pos_lagging_items":
        return validated_component(
            ComponentType.LAGGING_ITEMS_TABLE.value,
            {
                "window_days": output.get("window_days", 0),
                "items": output.get("items", []),
            },
        )
    if tool_name == "pos_sales_summary":
        return validated_component(
            ComponentType.SALES_SUMMARY_CARD.value,
            {
                "period_days": output.get("period_days", 0),
                "current_period": output.get("current_period", {}),
                "previous_period": output.get("previous_period", {}),
                "revenue_change_pct": output.get("revenue_change_pct"),
            },
        )
    if tool_name == "inventory_reorder_candidates":
        return validated_component(
            ComponentType.REORDER_CANDIDATES_TABLE.value,
            {
                "velocity_window_days": output.get("velocity_window_days", 0),
                "cover_days_threshold": output.get("cover_days_threshold", 0),
                "items": output.get("items", []),
            },
        )
    return None


def state_patch_for_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    output: dict[str, Any],
    journey: str | None = None,
) -> dict[str, Any]:
    if journey is None:
        journey = "pos_analytics" if tool_name.startswith("pos_") else "inventory"
    patch: dict[str, Any] = {
        "active_journey": journey,
        "last_intent": tool_name.replace("_", "."),
        "last_tool_name": tool_name,
        "last_tool_input": tool_input,
        "last_tool_output_summary": {
            "count": output.get("count"),
            "summary": output.get("summary"),
        },
    }

    item_ids = []
    for key in ("items", "balances", "movements"):
        rows = output.get(key)
        if isinstance(rows, list):
            for row in rows:
                if isinstance(row, dict):
                    item_id = row.get("item_id") or row.get("catalog_item_id") or row.get("id")
                    if isinstance(item_id, int):
                        item_ids.append(item_id)
            break

    if item_ids:
        patch["displayed_catalog_item_ids"] = item_ids[:20]
        patch["focused_entity_type"] = "catalog_item"
        patch["focused_entity_id"] = item_ids[0]

    date_range = {}
    if "from" in output:
        date_range["from"] = output["from"]
    if "to" in output:
        date_range["to"] = output["to"]
    current_period = output.get("current_period")
    if isinstance(current_period, dict):
        if "from" in current_period:
            date_range["from"] = current_period["from"]
        if "to" in current_period:
            date_range["to"] = current_period["to"]
    if date_range:
        patch["date_range"] = date_range

    return patch
