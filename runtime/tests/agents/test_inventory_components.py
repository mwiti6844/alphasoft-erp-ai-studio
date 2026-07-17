from __future__ import annotations

from app.agents.components import component_for_tool, state_patch_for_tool
from app.agents.copilot import run_copilot
from app.agents.events import ComponentReady, TextDelta, ToolCompleted, ToolStarted, Trace
from tests.conftest import FakeLaravelToolClient, ScriptedProvider


def test_inventory_balance_maps_to_table_component_and_state_patch():
    output = {
        "count": 1,
        "total_on_hand": 120,
        "include_zero_stock": False,
        "zero_stock_visibility": "zero_stock_rows_hidden",
        "balances": [
            {
                "item_id": 7,
                "item_name": "Basmati Rice 25kg",
                "sku": "RICE-25KG",
                "warehouse": {"id": 1, "name": "Main Store", "code": "MAIN"},
                "on_hand_qty": 120,
                "reserved_qty": 20,
                "available_qty": 100,
                "uom": {"id": 1, "name": "Bag", "symbol": "bag"},
                "lot": {"id": 3, "lot_number": "LOT-A"},
            }
        ],
    }

    component = component_for_tool("inventory_balance", output)

    assert component is not None
    assert component.type == "inventory_balance_table"
    assert component.props["rows"][0] == {
        "item_id": 7,
        "item_name": "Basmati Rice 25kg",
        "sku": "RICE-25KG",
        "warehouse_id": 1,
        "warehouse_name": "Main Store",
        "warehouse_code": "MAIN",
        "on_hand_qty": 120.0,
        "reserved_qty": 20.0,
        "available_qty": 100.0,
        "uom_symbol": "bag",
        "lot_number": "LOT-A",
    }

    patch = state_patch_for_tool("inventory_balance", {"search": "rice"}, output, journey="inventory")
    assert patch["focused_entity_type"] == "catalog_item"
    assert patch["focused_entity_id"] == 7
    assert patch["focused_entity_name"] == "Basmati Rice 25kg"
    assert patch["displayed_catalog_item_ids"] == [7]
    assert patch["displayed_warehouse_ids"] == [1]


def test_inventory_balance_empty_output_maps_to_empty_state():
    component = component_for_tool(
        "inventory_balance",
        {
            "count": 0,
            "total_on_hand": 0,
            "balances": [],
        },
    )

    assert component is not None
    assert component.type == "ai_empty_state"
    assert component.props["title"] == "No stock rows found"


def test_inventory_movements_maps_to_table_component_and_preserves_item_identity():
    output = {
        "count": 1,
        "limit": 20,
        "truncated": False,
        "timestamp_basis": "created_at",
        "movements": [
            {
                "id": 341,
                "item_id": 7,
                "item_name": "Basmati Rice 25kg",
                "sku": "RICE-25KG",
                "direction": "out",
                "movement_type": "sale",
                "qty": 2,
                "warehouse": {"id": 1, "name": "Main Store", "code": "MAIN"},
                "lot": {"id": 3, "lot_number": "LOT-A"},
                "source_document_type": "pos_transaction",
                "occurred_at": "2026-07-15T18:22:00Z",
            }
        ],
    }

    component = component_for_tool("inventory_movements", output)

    assert component is not None
    assert component.type == "inventory_movements_table"
    assert component.props["item_name"] == "Basmati Rice 25kg"
    assert component.props["rows"][0]["item_id"] == 7
    assert component.props["rows"][0]["warehouse_name"] == "Main Store"

    patch = state_patch_for_tool("inventory_movements", {"item_id": 7}, output, journey="inventory")
    assert patch["focused_entity_id"] == 7
    assert patch["focused_entity_name"] == "Basmati Rice 25kg"
    assert patch["displayed_warehouse_ids"] == [1]


async def test_ui_action_runs_tool_without_provider_request():
    laravel = FakeLaravelToolClient(
        output={
            "count": 1,
            "limit": 20,
            "truncated": False,
            "timestamp_basis": "created_at",
            "movements": [
                {
                    "id": 341,
                    "item_id": 7,
                    "item_name": "Basmati Rice 25kg",
                    "sku": "RICE-25KG",
                    "direction": "out",
                    "movement_type": "sale",
                    "qty": 2,
                    "warehouse": {"id": 1, "name": "Main Store", "code": "MAIN"},
                    "lot": None,
                    "source_document_type": "pos_transaction",
                    "occurred_at": "2026-07-15T18:22:00Z",
                }
            ],
        }
    )
    provider = ScriptedProvider([])

    events = [
        event
        async for event in run_copilot(
            provider=provider,
            laravel=laravel,
            tenant_id="tenant-1",
            user_id=1,
            session_id=1,
            message="Recent movements",
            messages=[],
            conversation_state={"focused_entity_type": "catalog_item", "focused_entity_id": 7},
            ui_action={
                "type": "run_tool",
                "tool": "inventory_movements",
                "input": {"item_id": 7},
            },
            user_memory={},
            module_scope="inventory",
            tool_definitions=[],
            max_tokens=512,
            temperature=0.2,
        )
    ]

    assert provider.requests == []
    assert laravel.calls[0]["tool_name"] == "inventory_movements"
    assert any(isinstance(event, Trace) and event.label == "ui_action" for event in events)
    assert any(isinstance(event, ToolStarted) for event in events)
    assert any(isinstance(event, ToolCompleted) for event in events)
    assert any(
        isinstance(event, ComponentReady) and event.type == "inventory_movements_table"
        for event in events
    )
    assert "Here are the results" in "".join(
        event.text for event in events if isinstance(event, TextDelta)
    )
