from __future__ import annotations

import pytest

from app.agents.components import ComponentType, validated_component
from app.agents.modules.base import BASE_RULES, MAX_SUGGESTIONS
from app.agents.modules.catalog import CATALOG_ROUTER
from app.agents.modules.inventory import INVENTORY_ROUTER
from app.agents.modules.pos import POS_ROUTER
from app.agents.modules.registry import ROUTERS, UnknownModuleScopeError, router_for_scope

ALL_ROUTERS = [CATALOG_ROUTER, INVENTORY_ROUTER, POS_ROUTER]
POS_ONLY_LABELS = {"Top sellers", "Lagging items", "Sales summary"}


class TestRegistry:
    def test_resolves_all_known_scopes(self):
        assert router_for_scope("pos") is POS_ROUTER
        assert router_for_scope("inventory") is INVENTORY_ROUTER
        assert router_for_scope("catalog") is CATALOG_ROUTER

    def test_unknown_scope_raises_with_supported_list(self):
        with pytest.raises(UnknownModuleScopeError, match="Unknown module scope 'billing'. Supported: catalog, inventory, pos"):
            router_for_scope("billing")

    def test_registry_scopes_match_router_scopes(self):
        assert set(ROUTERS) == {"pos", "inventory", "catalog"}
        for scope, router in ROUTERS.items():
            assert router.scope == scope


class TestRouterInvariants:
    @pytest.mark.parametrize("router", ALL_ROUTERS, ids=lambda r: r.scope)
    def test_prompt_contains_shared_rules_and_module_marker(self, router):
        assert router.system_prompt.startswith(BASE_RULES)
        assert "Never invent numbers" in router.system_prompt
        assert f"Module: {router.scope}" in router.system_prompt or router.scope == "pos"
        if router.scope == "pos":
            assert "Module: POS analytics" in router.system_prompt

    @pytest.mark.parametrize("router", ALL_ROUTERS, ids=lambda r: r.scope)
    def test_every_router_allows_follow_up_suggestions(self, router):
        assert ComponentType.FOLLOW_UP_SUGGESTIONS in router.allowed_component_types

    @pytest.mark.parametrize("router", ALL_ROUTERS, ids=lambda r: r.scope)
    def test_every_router_allows_flow_citations(self, router):
        assert ComponentType.FLOW_CITATIONS in router.allowed_component_types

    def test_inventory_router_allows_phase_c_inventory_components(self):
        assert ComponentType.INVENTORY_BALANCE_TABLE in INVENTORY_ROUTER.allowed_component_types
        assert ComponentType.INVENTORY_MOVEMENTS_TABLE in INVENTORY_ROUTER.allowed_component_types
        assert ComponentType.EMPTY_STATE in INVENTORY_ROUTER.allowed_component_types

    @pytest.mark.parametrize("router", ALL_ROUTERS, ids=lambda r: r.scope)
    def test_default_suggestions_are_valid_and_capped(self, router):
        chips = router.build_suggestions("", {}, {}, {})
        assert 1 <= len(chips) <= MAX_SUGGESTIONS
        assert len({chip["id"] for chip in chips}) == len(chips)
        component = validated_component("follow_up_suggestions", {"suggestions": chips})
        assert component is not None

    @pytest.mark.parametrize("router", ALL_ROUTERS, ids=lambda r: r.scope)
    def test_state_patch_carries_router_journey(self, router):
        expected = {"pos": "pos_analytics", "inventory": "inventory", "catalog": "catalog"}[router.scope]
        patch = router.state_patch_for_tool(
            "catalog_search",
            {"query": "rice"},
            {"count": 1, "items": [{"id": 7, "name": "Rice"}]},
        )
        assert patch["active_journey"] == expected
        assert patch["last_tool_name"] == "catalog_search"
        assert patch["displayed_catalog_item_ids"] == [7]


class TestPosSuggestions:
    def test_pos_prompt_contains_advertising_honesty(self):
        prompt = POS_ROUTER.system_prompt
        assert "no advertising-performance data" in prompt
        assert "impressions" in prompt

    def test_default_trio(self):
        labels = [chip["label"] for chip in POS_ROUTER.build_suggestions("", {}, {}, {})]
        assert labels == ["Top sellers", "Lagging items", "Reorder candidates"]

    def test_after_top_sellers_excludes_itself(self):
        chips = POS_ROUTER.build_suggestions("pos_top_selling_items", {}, {"count": 3}, {})
        labels = [chip["label"] for chip in chips]
        assert "Top sellers" not in labels
        assert "Lagging items" in labels

    def test_empty_output_prepends_widen_window(self):
        chips = POS_ROUTER.build_suggestions("pos_top_selling_items", {}, {"count": 0}, {})
        assert chips[0]["id"] == "widen"
        assert len(chips) <= MAX_SUGGESTIONS


class TestInventorySuggestions:
    def test_no_pos_only_chips_by_default(self):
        labels = {chip["label"] for chip in INVENTORY_ROUTER.build_suggestions("", {}, {}, {})}
        assert labels.isdisjoint(POS_ONLY_LABELS)
        assert "Stock balances" in labels

    def test_after_balance_tool_stays_inventory_framed(self):
        chips = INVENTORY_ROUTER.build_suggestions("inventory_balance", {}, {"count": 5}, {})
        labels = {chip["label"] for chip in chips}
        assert labels.isdisjoint(POS_ONLY_LABELS)
        assert "Recent movements" in labels

    def test_after_balance_tool_can_emit_structured_movement_action(self):
        chips = INVENTORY_ROUTER.build_suggestions(
            "inventory_balance",
            {},
            {"count": 1, "balances": [{"item_id": 7, "item_name": "Basmati Rice"}]},
            {},
        )
        assert chips[0]["action"] == {
            "type": "run_tool",
            "tool": "inventory_movements",
            "input": {"item_id": 7},
        }
        component = validated_component("follow_up_suggestions", {"suggestions": chips})
        assert component is not None

    def test_after_movements_tool_uses_real_item_name_for_balance_action(self):
        chips = INVENTORY_ROUTER.build_suggestions(
            "inventory_movements",
            {},
            {"count": 1, "movements": [{"item_id": 7, "item_name": "Basmati Rice 25kg"}]},
            {},
        )
        assert chips[0]["action"] == {
            "type": "run_tool",
            "tool": "inventory_balance",
            "input": {"search": "Basmati Rice 25kg"},
        }

    def test_prompt_explains_reorder_basis(self):
        assert "stock cover and sales velocity" in INVENTORY_ROUTER.system_prompt
        assert "not a configured reorder point" in INVENTORY_ROUTER.system_prompt


class TestCatalogSuggestions:
    def test_no_pos_analytics_chips(self):
        labels = {chip["label"] for chip in CATALOG_ROUTER.build_suggestions("", {}, {}, {})}
        assert labels.isdisjoint(POS_ONLY_LABELS)

    def test_default_chips_are_natural_language_prompts(self):
        messages = [chip["message"] for chip in CATALOG_ROUTER.build_suggestions("", {}, {}, {})]
        assert "Search by item name or SKU" in messages

    def test_search_results_ground_detail_suggestion_in_real_item(self):
        chips = CATALOG_ROUTER.build_suggestions(
            "catalog_search", {"query": "rice"}, {"count": 1, "items": [{"id": 7, "name": "Basmati Rice"}]}, {}
        )
        assert chips[0]["message"] == "Show details for Basmati Rice"

    def test_search_with_no_results_falls_back_to_generic_prompts(self):
        chips = CATALOG_ROUTER.build_suggestions("catalog_search", {"query": "x"}, {"count": 0, "items": []}, {})
        assert all("Show details for " not in chip["message"] or chip["id"] == "detail" for chip in chips)
