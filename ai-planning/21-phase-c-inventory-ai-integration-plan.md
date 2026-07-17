# 21 — Phase C: Inventory AI Integration

**Date:** 2026-07-17
**Status:** Implemented slice — no commits or pushes accompany this document.
**Companions:** doc 16 (inventory contracts), doc 18 (backend questions), doc 19 (chat/memory flow), doc 20 (thread UX).

## 1. Current State

The backend already had the inventory AI tools registered in `AiToolRegistry`: `inventory_balance`, `inventory_movements`, `warehouse_list`, and `inventory_reorder_candidates`. Phase C therefore did not create a new transport or move data access into Python. Laravel remains the sole tenant-data executor, with permission checks and `ai_tool_calls` audit intact.

Runtime support before this slice only rendered `inventory_reorder_candidates_table`; balance and movement tool results were narrated but had no generative UI component.

Frontend support before this slice only allowed the reorder table plus POS components and follow-up suggestions.

## 2. Scope Shipped Now

Now:
- Harden `inventory_balance` output for generative UI, including explicit zero-stock visibility semantics.
- Harden `inventory_movements` output with item identity, warehouse code, source document type, cap metadata, and timestamp basis.
- Add strict runtime pydantic components for `inventory_balance_table`, `inventory_movements_table`, and `ai_empty_state`.
- Allow the inventory router to emit those components.
- Extend session state patches with `focused_entity_name` and `displayed_warehouse_ids`.
- Render the new inventory components in the existing frontend AI component registry.

Deferred:
- `inventory_stock_position_card` remains spec-only until stock-cover/position semantics are finalized.
- `inventory_low_stock` and `inventory_dead_stock` remain deferred pending threshold definitions.
- Serial/lot traceability remains later; lot number is displayed when it already appears in balance/movement outputs, but no dedicated traceability tool ships here.
- Structured suggestion action execution remains Phase B.5/C follow-up, as planned in doc 20.

## 3. Backend Contracts

`inventory_balance`
- Permission: `inventory.inventory-balances.list`.
- Inputs: `search` required; optional `warehouse_id`, `include_zero_stock`, `limit`.
- Behavior: default keeps the existing `on_hand_qty > 0` filter. `include_zero_stock=true` includes existing zero-balance rows, but cannot show catalog items with no balance row.
- Output adds `include_zero_stock` and `zero_stock_visibility`.

`inventory_movements`
- Permission: `inventory.inventory-movements.list`.
- Inputs: `item_id` required; optional `warehouse_id`, `limit`.
- Behavior: still ordered by `created_at` and capped at 20. `occurred_at` is explicitly based on `created_at`.
- Output adds `item_id`, `item_name`, `sku`, warehouse code, `source_document_type`, `limit`, `truncated`, and `timestamp_basis`.

`warehouse_list`
- Permission: `inventory.warehouses.list`.
- Input schema is strict with `additionalProperties: false`.

## 4. Runtime Integration

New component types:
- `inventory_balance_table`
- `inventory_movements_table`
- `ai_empty_state`

`component_for_tool()` maps:
- `inventory_balance` with rows → `inventory_balance_table`
- `inventory_balance` count 0 → `ai_empty_state`
- `inventory_movements` with rows → `inventory_movements_table`
- `inventory_movements` count 0 → `ai_empty_state`

`state_patch_for_tool()` now records:
- `focused_entity_name`
- `displayed_warehouse_ids`

The inventory router allows the three new component types while preserving deterministic suggestions and scope boundaries.

## 5. Frontend Integration

`AiUiComponent` now includes:
- `inventory_balance_table`
- `inventory_movements_table`
- `ai_empty_state`

`AiComponentRenderer` renders both inventory tables with the existing embedded-table pattern and renders empty states with optional suggestion chips. Unknown component types still render nothing.

## 6. Eval Mapping

Executable after this slice:
- balance lookup component path
- movement history component path
- no-data empty-state component path
- reorder candidates component path
- unsafe/raw-SQL/cross-tenant refusal fixtures remain behavioral evals rather than direct component tests.

Still spec-only:
- stock position card
- low-stock/dead-stock threshold flows
- serial/lot traceability beyond showing lot number already present in outputs.

## 7. Verification

- Runtime: `75 passed`
- Backend AI subset: `61 passed, 269 assertions`
- Backend style: `vendor/bin/pint --dirty` passed
- Frontend: `npm run build` passed

## 8. Next Slice

The next useful slice is live smoke testing against a real tenant with inventory balances and movements:
1. Ask "How much rice do we have?"
2. Follow with "What happened to it recently?"
3. Ask a no-data stock question and confirm `ai_empty_state`.
4. Confirm `state_patch` includes only accepted keys and includes displayed warehouse IDs.

After that, choose between Phase B.5 structured suggestion actions or Phase C.2 low/dead-stock contracts.
