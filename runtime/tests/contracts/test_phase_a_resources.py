from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from app.agents.components import ComponentType, validated_component
from app.agents.modules.catalog import CATALOG_ROUTER
from app.agents.modules.inventory import INVENTORY_ROUTER
from app.agents.modules.pos import POS_ROUTER


REPO_ROOT = Path(__file__).resolve().parents[3]
CONTRACTS_DIR = REPO_ROOT / "contracts"
FLOW_DIR = CONTRACTS_DIR / "flows"
INVENTORY_EVAL_DIR = REPO_ROOT / "evals" / "inventory"

FLOW_ID_PATTERN = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*)+$")
FIXTURE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")
TOOL_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")

KNOWN_AI_TOOLS = {
    "catalog_item_detail",
    "catalog_search",
    "inventory_balance",
    "inventory_movements",
    "inventory_reorder_candidates",
    "pos_lagging_items",
    "pos_sales_summary",
    "pos_top_selling_items",
    "warehouse_list",
}

SHIPPED_COMPONENT_TYPES = {component_type.value for component_type in ComponentType}
EXPECTED_INVENTORY_FIXTURES = {
    "inventory_ambiguous_item",
    "inventory_balance_lookup",
    "inventory_component_contract",
    "inventory_cross_tenant_refusal",
    "inventory_follow_up_warehouse",
    "inventory_movement_history",
    "inventory_no_data",
    "inventory_raw_sql_refusal",
    "inventory_reorder",
    "inventory_unsafe_delete_refusal",
}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def load_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    assert isinstance(data, dict), f"{path} must parse to a mapping"
    return data


def flow_paths() -> list[Path]:
    return sorted(FLOW_DIR.glob("*/*.yaml"))


def inventory_eval_paths() -> list[Path]:
    return sorted(INVENTORY_EVAL_DIR.glob("*.yaml"))


def test_phase_a_json_schemas_are_valid() -> None:
    for schema_path in [
        FLOW_DIR / "flow.schema.json",
        CONTRACTS_DIR / "ai-followup-suggestion.schema.json",
    ]:
        Draft202012Validator.check_schema(load_json(schema_path))


def test_flow_resources_validate_and_have_stable_ids() -> None:
    schema = load_json(FLOW_DIR / "flow.schema.json")
    validator = Draft202012Validator(schema)
    resources = [load_yaml(path) for path in flow_paths()]

    assert len(resources) == 8
    ids = [resource["id"] for resource in resources]
    assert len(ids) == len(set(ids)), "flow ids must be unique"

    for path, resource in zip(flow_paths(), resources, strict=True):
        errors = sorted(validator.iter_errors(resource), key=lambda error: list(error.path))
        assert not errors, f"{path} schema errors: {[error.message for error in errors]}"

        module, slug = resource["id"].split(".", 1)
        assert module == resource["module"], f"{path} id module must match module field"
        assert path.parent.name == module, f"{path} directory must match module"
        assert path.stem == slug, f"{path} filename must match flow id slug"
        assert resource.get("common_questions"), f"{path} needs retrieval questions"


def test_flow_cross_references_and_tools_resolve() -> None:
    resources = [load_yaml(path) for path in flow_paths()]
    flow_ids = {resource["id"] for resource in resources}

    for resource in resources:
        for related_flow in resource.get("related_flows", []):
            assert related_flow in flow_ids, f"{resource['id']} references missing flow {related_flow}"

        for tool in resource.get("related_ai_tools", []):
            assert tool in KNOWN_AI_TOOLS, f"{resource['id']} references unknown tool {tool}"


def test_followup_schema_accepts_runtime_router_suggestions() -> None:
    schema = load_json(CONTRACTS_DIR / "ai-followup-suggestion.schema.json")
    validator = Draft202012Validator(schema)

    suggestion_sets = [
        POS_ROUTER.build_suggestions("", {}, {}, {}),
        INVENTORY_ROUTER.build_suggestions("", {}, {}, {}),
        CATALOG_ROUTER.build_suggestions("", {}, {}, {}),
    ]

    for suggestions in suggestion_sets:
        assert 1 <= len(suggestions) <= 4
        for suggestion in suggestions:
            errors = sorted(validator.iter_errors(suggestion), key=lambda error: list(error.path))
            assert not errors, [error.message for error in errors]


def test_followup_schema_accepts_planned_action_shapes() -> None:
    schema = load_json(CONTRACTS_DIR / "ai-followup-suggestion.schema.json")
    validator = Draft202012Validator(schema)

    examples = [
        {
            "id": "inventory-movements-focused-item",
            "label": "Recent movements",
            "message": "Show recent stock movements for this item",
            "action": {
                "type": "run_tool",
                "tool": "inventory_movements",
                "input": {"item_id": 7},
            },
        },
        {
            "id": "ask-reorder",
            "label": "Reorder candidates",
            "message": "What should we reorder?",
            "action": {"type": "ask"},
        },
        {
            "id": "start-inventory",
            "label": "Inventory",
            "message": "Start an inventory check",
            "action": {"type": "start_journey", "journey": "inventory"},
        },
    ]

    for example in examples:
        errors = sorted(validator.iter_errors(example), key=lambda error: list(error.path))
        assert not errors, [error.message for error in errors]


def test_inventory_eval_fixtures_have_expected_contract_shape() -> None:
    fixtures = [load_yaml(path) for path in inventory_eval_paths()]

    assert {fixture["id"] for fixture in fixtures} == EXPECTED_INVENTORY_FIXTURES

    for path, fixture in zip(inventory_eval_paths(), fixtures, strict=True):
        assert FIXTURE_ID_PATTERN.match(fixture["id"]), f"{path} has invalid id"
        assert fixture["scope"] == "inventory", f"{path} must stay inventory scoped"
        assert fixture.get("fixture") == "demo_restaurant", f"{path} must name its demo fixture"

        has_question = isinstance(fixture.get("question"), str) and bool(fixture["question"])
        has_turns = isinstance(fixture.get("turns"), list) and bool(fixture["turns"])
        has_components = isinstance(fixture.get("components"), list) and bool(fixture["components"])
        assert has_question or has_turns or has_components, f"{path} needs question, turns, or components"

        for tool_call in fixture.get("scripted_tools", []):
            tool = tool_call["tool"]
            assert TOOL_NAME_PATTERN.match(tool), f"{path} has invalid tool name {tool}"
            assert tool in KNOWN_AI_TOOLS, f"{path} references unregistered tool {tool}"

        expect = fixture.get("expect")
        if expect is not None:
            assert isinstance(expect, dict), f"{path} expect must be a mapping"
            for tool in expect.get("tools_called", []):
                assert tool in KNOWN_AI_TOOLS, f"{path} expects unknown tool {tool}"


def test_inventory_refusal_fixtures_dispatch_zero_tools() -> None:
    for filename in [
        "cross-tenant-refusal.yaml",
        "raw-sql-refusal.yaml",
        "unsafe-delete-refusal.yaml",
    ]:
        fixture = load_yaml(INVENTORY_EVAL_DIR / filename)
        assert fixture.get("scripted_tools") == []
        assert fixture["expect"]["tools_called"] == []
        assert fixture["expect"]["no_write_language"] is True


def test_inventory_component_contract_matches_shipped_runtime_component() -> None:
    fixture = load_yaml(INVENTORY_EVAL_DIR / "component-contract.yaml")
    components = fixture["components"]

    existing = [component for component in components if component["status"] == "exists"]
    proposed = [component for component in components if component["status"] == "proposed"]

    assert {component["type"] for component in existing} == {
        "inventory_reorder_candidates_table",
        "inventory_balance_table",
        "inventory_movements_table",
        "ai_empty_state",
    }

    for component in existing:
        parsed = validated_component(component["type"], component["props"])
        assert parsed is not None, f"{component['type']} must match today's pydantic props"

    for component in proposed:
        assert component["type"] in {
            "inventory_balance_table",
            "inventory_movements_table",
            "inventory_stock_position_card",
            "ai_empty_state",
        }
        if component["type"] in SHIPPED_COMPONENT_TYPES:
            parsed = validated_component(component["type"], component["props"])
            assert parsed is not None, f"{component['type']} must match today's pydantic props"
        else:
            assert isinstance(component["props"], dict) and component["props"]
