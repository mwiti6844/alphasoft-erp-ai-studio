from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError


class ComponentType(str, Enum):
    TOP_ITEMS_TABLE = "pos_top_items_table"
    LAGGING_ITEMS_TABLE = "pos_lagging_items_table"
    SALES_SUMMARY_CARD = "pos_sales_summary_card"
    REORDER_CANDIDATES_TABLE = "inventory_reorder_candidates_table"
    INVENTORY_BALANCE_TABLE = "inventory_balance_table"
    INVENTORY_MOVEMENTS_TABLE = "inventory_movements_table"
    EMPTY_STATE = "ai_empty_state"
    FOLLOW_UP_SUGGESTIONS = "follow_up_suggestions"
    FLOW_CITATIONS = "flow_citations"


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


class InventoryBalanceRow(StrictProps):
    item_id: int
    item_name: str | None = None
    sku: str | None = None
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    warehouse_code: str | None = None
    on_hand_qty: float
    reserved_qty: float
    available_qty: float
    uom_symbol: str | None = None
    lot_number: str | None = None


class InventoryBalanceProps(StrictProps):
    total_on_hand: float
    include_zero_stock: bool = False
    zero_stock_visibility: str | None = None
    rows: list[InventoryBalanceRow]


class InventoryMovementRow(StrictProps):
    id: int
    item_id: int
    item_name: str | None = None
    sku: str | None = None
    occurred_at: str | None = None
    direction: str
    movement_type: str
    qty: float
    warehouse_id: int | None = None
    warehouse_name: str | None = None
    warehouse_code: str | None = None
    lot_number: str | None = None
    source_document_type: str | None = None


class InventoryMovementsProps(StrictProps):
    item_name: str | None = None
    limit: int
    truncated: bool
    timestamp_basis: str
    rows: list[InventoryMovementRow]


class EmptySuggestion(StrictProps):
    id: str
    label: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=300)


class EmptyStateProps(StrictProps):
    title: str
    reason: str
    suggestions: list[EmptySuggestion] = Field(default_factory=list, max_length=4)


class FollowUpSuggestion(StrictProps):
    id: str
    label: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=300)
    action: dict[str, Any] | None = None


class FollowUpSuggestionsProps(StrictProps):
    suggestions: list[FollowUpSuggestion] = Field(min_length=1, max_length=4)


class FlowCitation(StrictProps):
    id: str = Field(min_length=1, max_length=120)
    version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=160)


class FlowCitationsProps(StrictProps):
    sources: list[FlowCitation] = Field(min_length=1, max_length=3)


PROP_MODELS: dict[ComponentType, type[BaseModel]] = {
    ComponentType.TOP_ITEMS_TABLE: TopItemsProps,
    ComponentType.LAGGING_ITEMS_TABLE: LaggingItemsProps,
    ComponentType.SALES_SUMMARY_CARD: SalesSummaryProps,
    ComponentType.REORDER_CANDIDATES_TABLE: ReorderCandidatesProps,
    ComponentType.INVENTORY_BALANCE_TABLE: InventoryBalanceProps,
    ComponentType.INVENTORY_MOVEMENTS_TABLE: InventoryMovementsProps,
    ComponentType.EMPTY_STATE: EmptyStateProps,
    ComponentType.FOLLOW_UP_SUGGESTIONS: FollowUpSuggestionsProps,
    ComponentType.FLOW_CITATIONS: FlowCitationsProps,
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
    if tool_name == "inventory_balance":
        rows = []
        for row in output.get("balances", []):
            if not isinstance(row, dict):
                continue
            warehouse = row.get("warehouse") if isinstance(row.get("warehouse"), dict) else {}
            uom = row.get("uom") if isinstance(row.get("uom"), dict) else {}
            lot = row.get("lot") if isinstance(row.get("lot"), dict) else {}
            rows.append(
                {
                    "item_id": row.get("item_id"),
                    "item_name": row.get("item_name"),
                    "sku": row.get("sku"),
                    "warehouse_id": warehouse.get("id"),
                    "warehouse_name": warehouse.get("name"),
                    "warehouse_code": warehouse.get("code"),
                    "on_hand_qty": row.get("on_hand_qty", 0),
                    "reserved_qty": row.get("reserved_qty", 0),
                    "available_qty": row.get("available_qty", 0),
                    "uom_symbol": uom.get("symbol"),
                    "lot_number": lot.get("lot_number"),
                }
            )
        if output.get("count") == 0:
            return validated_component(
                ComponentType.EMPTY_STATE.value,
                {
                    "title": "No stock rows found",
                    "reason": (
                        "No inventory balance rows matched that lookup. "
                        "The balance tool hides zero-stock rows unless zero stock is explicitly included."
                    ),
                    "suggestions": [
                        {
                            "id": "search-catalog",
                            "label": "Search catalog",
                            "message": "Search the catalog for this item",
                        }
                    ],
                },
            )
        return validated_component(
            ComponentType.INVENTORY_BALANCE_TABLE.value,
            {
                "total_on_hand": output.get("total_on_hand", 0),
                "include_zero_stock": output.get("include_zero_stock", False),
                "zero_stock_visibility": output.get("zero_stock_visibility"),
                "rows": rows,
            },
        )
    if tool_name == "inventory_movements":
        rows = []
        for row in output.get("movements", []):
            if not isinstance(row, dict):
                continue
            warehouse = row.get("warehouse") if isinstance(row.get("warehouse"), dict) else {}
            lot = row.get("lot") if isinstance(row.get("lot"), dict) else {}
            rows.append(
                {
                    "id": row.get("id"),
                    "item_id": row.get("item_id"),
                    "item_name": row.get("item_name"),
                    "sku": row.get("sku"),
                    "occurred_at": row.get("occurred_at"),
                    "direction": row.get("direction", ""),
                    "movement_type": row.get("movement_type", ""),
                    "qty": row.get("qty", 0),
                    "warehouse_id": warehouse.get("id"),
                    "warehouse_name": warehouse.get("name"),
                    "warehouse_code": warehouse.get("code"),
                    "lot_number": lot.get("lot_number"),
                    "source_document_type": row.get("source_document_type"),
                }
            )
        if output.get("count") == 0:
            return validated_component(
                ComponentType.EMPTY_STATE.value,
                {
                    "title": "No stock movements found",
                    "reason": "No inventory movements matched that item and warehouse filter.",
                    "suggestions": [
                        {
                            "id": "check-balance",
                            "label": "Check balance",
                            "message": "Show the current stock balance for this item",
                        }
                    ],
                },
            )
        return validated_component(
            ComponentType.INVENTORY_MOVEMENTS_TABLE.value,
            {
                "item_name": rows[0].get("item_name") if rows else None,
                "limit": output.get("limit", 20),
                "truncated": output.get("truncated", False),
                "timestamp_basis": output.get("timestamp_basis", "created_at"),
                "rows": rows,
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

    warehouse_ids = []
    focused_name = None
    for key in ("items", "balances", "movements", "warehouses"):
        rows = output.get(key)
        if isinstance(rows, list):
            for row in rows:
                if not isinstance(row, dict):
                    continue
                if focused_name is None:
                    name = row.get("item_name") or row.get("name")
                    if isinstance(name, str) and name:
                        focused_name = name
                warehouse = row.get("warehouse")
                warehouse_id = None
                if isinstance(warehouse, dict):
                    warehouse_id = warehouse.get("id")
                elif key == "warehouses":
                    warehouse_id = row.get("id")
                if isinstance(warehouse_id, int):
                    warehouse_ids.append(warehouse_id)
            break

    if focused_name is not None:
        patch["focused_entity_name"] = focused_name
    if warehouse_ids:
        patch["displayed_warehouse_ids"] = warehouse_ids[:20]

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
