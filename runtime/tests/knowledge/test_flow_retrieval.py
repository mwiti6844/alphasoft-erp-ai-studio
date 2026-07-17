from __future__ import annotations

from app.knowledge.flows import flow_context_prompt, is_process_question, load_flow_resources, retrieve_flows


def test_loads_curated_flow_resources():
    resources = load_flow_resources()

    assert len(resources) == 8
    assert {resource.id for resource in resources} >= {
        "inventory.check-stock",
        "permissions.module-access",
        "pos.setup",
    }


def test_retrieves_inventory_check_stock_for_process_question():
    matches = retrieve_flows("How do I check stock for rice?", module_scope="inventory")

    assert matches
    assert matches[0].resource.id == "inventory.check-stock"


def test_retrieves_permissions_flow_for_access_denied_question():
    matches = retrieve_flows("Why can't the AI answer inventory questions for me?", module_scope="inventory")

    assert matches
    assert matches[0].resource.id == "permissions.module-access"


def test_analytics_question_does_not_trigger_flow_retrieval():
    assert not is_process_question("Show top selling items for the last 14 days")
    assert retrieve_flows("Show top selling items for the last 14 days", module_scope="pos") == ()


def test_flow_prompt_includes_steps_and_citation_ids():
    matches = retrieve_flows("How do I configure taxes?", module_scope="catalog")
    prompt = flow_context_prompt(matches)

    assert "taxes.configure-tax" in prompt
    assert "Catalog > Settings > Taxes" in prompt
    assert "do not invent screens" in prompt
