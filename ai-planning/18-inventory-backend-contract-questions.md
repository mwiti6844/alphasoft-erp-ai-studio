# 18 — Inventory Backend Contract Questions

Date: 2026-07-15

Status: backend handoff brief. No implementation is approved by this document.

Source: `ai-planning/16-inventory-ai-contract-and-nl2sql-plan.md`, especially section 11.

Purpose: give the backend/MCP/endpoints team a concise decision checklist so the AI runtime workstream can build inventory resources, evals, conversation behavior, and UI contracts against stable backend tool contracts.

## Context

The AI runtime workstream owns inventory natural-language behavior:

- intent mapping
- clarification questions
- schema/metric resources
- typed tool/query requests
- narration
- follow-up suggestions
- conversation state
- component mapping
- eval fixtures

The backend team owns tenant-safe facts:

- SQL/query builder execution
- tenancy and permissions
- request validation
- tool/endpoint registration
- JSON response contracts
- audit through `ai_tool_calls`
- backend tests

Python/FastAPI must not connect to tenant databases and must not execute raw SQL from model output. It will call Laravel tools/endpoints only.

## Decision Checklist

### 1. Permission Triples for Proposed Tools

**Why AI needs it:** Python receives only tool definitions that Laravel exposes for the logged-in user. Every proposed tool must declare a real permission triple before it can be advertised to the model.

**Current evidence:** Existing tools use inventory permissions. `inventory_reorder_candidates` uses inventory-balance access even though it is useful in POS/inventory contexts.

**Recommended default:** Use `inventory / inventory-balances / list` for read-only balance/cover tools, and `inventory / inventory-movements / list` for movement-history tools. Introduce finer permissions only if the inventory module already has them.

**Backend decision needed:** Confirm permission triples for:

- `inventory_low_stock`
- `inventory_dead_stock`
- `inventory_stock_cover`
- extended `inventory_movements`
- any future traceability tool

**Affected contracts:** all proposed inventory tools.

**Acceptance criteria:** each tool permission resolves through the existing permission bundle resolver, denied users see no tool definition, denied dispatch is audited.

### 2. Zero-Stock Visibility

**Why AI needs it:** Questions like “why is this item unavailable?” and “list out-of-stock items” require rows where available/on-hand quantity is zero or negative.

**Current evidence:** `inventory_balance` currently filters `on_hand_qty > 0`, so zero-stock rows are invisible.

**Recommended default:** Add an additive `include_zero_stock: boolean` input to `inventory_balance`, default `false` to preserve current behavior.

**Backend decision needed:** Should zero/negative stock visibility be added to `inventory_balance`, or should it be exposed through a separate `inventory_low_stock` / `inventory_out_of_stock` tool?

**Affected contracts:** `inventory_balance`, `inventory_low_stock`, `inventory_stock_cover`, unavailability explanations.

**Acceptance criteria:** the assistant can distinguish:

- no matching item
- item exists but has no stock row
- item has stock but `available_qty <= 0`
- item is unavailable because stock is reserved

### 3. Inventory Movements Date Range

**Why AI needs it:** Questions like “what changed since last week?” need a bounded movement window.

**Current evidence:** `inventory_movements` currently accepts `item_id` and optional `warehouse_id`, returns fixed last 20 rows, ordered by `created_at`.

**Recommended default:** Extend the existing tool rather than creating a new one:

```json
{
  "item_id": 123,
  "warehouse_id": null,
  "date_range": {"from": "2026-07-08", "to": "2026-07-15"},
  "limit": 50,
  "movement_type": null,
  "direction": null
}
```

**Backend decision needed:** Confirm whether `date_range`, `limit`, `movement_type`, and `direction` are acceptable additive inputs.

**Affected contracts:** `inventory_movements`, movement-history conversations, “what changed since last week?” evals.

**Acceptance criteria:** tool can return movements within a date window, clamps limit server-side, and indicates truncation when results exceed the limit.

### 4. Movement Timestamp Semantics

**Why AI needs it:** Narration must be honest about what a movement date means.

**Current evidence:** AI contract review found `occurred_at` is effectively aliased from `created_at`; no separate occurrence timestamp was identified.

**Recommended default:** Treat `created_at` as the movement timestamp and name it clearly in the contract. If the business has a true occurrence/posting date, expose that instead.

**Backend decision needed:** Is `created_at` the canonical timestamp for inventory movement reporting? Are there business cases where movement creation time differs from effective stock movement time?

**Affected contracts:** `inventory_movements`, date-range filters, movement timeline UI.

**Acceptance criteria:** response includes a documented timestamp field with stable semantics, and AI narration does not imply a different business date.

### 5. Low-Stock Definition

**Why AI needs it:** “Low stock” can mean absolute quantity, available quantity, stock cover, or configured reorder point. The assistant must state the definition used.

**Current evidence:** No reorder-point field exists. Existing reorder candidates are based on stock cover and sales velocity.

**Recommended default:** For `inventory_low_stock`, define low stock as `available_qty <= threshold`, with optional warehouse filter. Keep stock-cover logic in `inventory_stock_cover` / `inventory_reorder_candidates`.

**Backend decision needed:** Should low stock be absolute-threshold based, cover-based, or both with explicit `basis`?

**Affected contracts:** `inventory_low_stock`, inventory balance table, low-stock evals.

**Acceptance criteria:** output includes the effective threshold/basis, and the assistant states it in narration.

### 6. Dead-Stock Definition

**Why AI needs it:** “Dead stock” and “slow movers” require a precise window and sales-source definition.

**Current evidence:** POS completed transaction lines exist and can power sales velocity/co-occurrence. Inventory alone does not define dead stock.

**Recommended default:** Define dead stock as items with `available_qty > 0` and zero completed POS sales over a configurable window, default 30 days.

**Backend decision needed:** Confirm:

- default no-sale window
- whether to use completed POS transactions only
- whether to filter by warehouse or tenant-wide stock
- whether restaurant/retail vertical affects the definition

**Affected contracts:** `inventory_dead_stock`, product-promotion handoff, dead-stock evals.

**Acceptance criteria:** tool returns stock-on-hand items with no completed sales in the chosen window and states the window in output.

### 7. Serial/Lot Population and Traceability Feasibility

**Why AI needs it:** Users may ask “where did this serial/batch go?” The schema exists, but the assistant should not claim traceability if data is not populated or no tool exposes it.

**Current evidence:** `inventory_serials` and `inventory_lots` exist with status/warehouse/lot/expiry-style fields, but no AI tool exposes them.

**Recommended default:** Keep traceability as Later until backend confirms real tenant population and builds a read-only traceability tool.

**Backend decision needed:** Are serial and lot tables populated in real tenants? Is a read-only AI traceability endpoint feasible for v1?

**Affected contracts:** future `inventory_traceability` tool, traceability refusal rule.

**Acceptance criteria:** before implementation, backend can demonstrate serial/lot rows on a real or fixture tenant and define a minimal output contract.

### 8. Warehouse and Item Identifier Rules

**Why AI needs it:** Python should pass stable IDs, not guessed names. Ambiguous names should become clarification flows.

**Current evidence:** Existing tools accept `item_id` or `warehouse_id`; `warehouse_list` can resolve warehouse names; inventory balances have `warehouse_id` but no `branch_id`.

**Recommended default:** Resolve warehouse names through `warehouse_list`, item names/SKUs through `inventory_balance` or catalog tools, then pass integer IDs to downstream tools.

**Backend decision needed:** Confirm:

- warehouse is the only inventory location scope the AI should expose initially
- no branch-to-warehouse rule must be applied by the assistant
- item IDs are catalog item IDs across all inventory tools

**Affected contracts:** all item/warehouse-filtered inventory tools.

**Acceptance criteria:** ambiguous item/warehouse names lead to clarification, not guessed tool calls.

### 9. Reorder-Point Roadmap

**Why AI needs it:** Current prompts and contracts say reorder candidates are based on stock cover and sales velocity, not configured reorder points.

**Current evidence:** No `reorder_point` field was found; existing reorder tool docblock confirms the stock-cover basis.

**Recommended default:** Keep stock-cover as the contractual basis until an actual reorder-point field exists.

**Backend decision needed:** Confirm there is no near-term reorder-point schema change that should alter the AI contract or marketing language.

**Affected contracts:** `inventory_reorder_candidates`, `inventory_stock_cover`, inventory router prompt, user guide/marketing claims.

**Acceptance criteria:** assistant never says “below reorder point” unless backend ships a real reorder-point field and tool contract.

## Required Backend Output

Backend should respond with:

1. Approved permission triples for each proposed/extended tool.
2. Decision on `include_zero_stock`.
3. Approved `inventory_movements` v2 input/output shape.
4. Timestamp semantics for movement reporting.
5. Low-stock definition.
6. Dead-stock definition.
7. Serial/lot traceability decision.
8. Warehouse/item identifier rules.
9. Reorder-point roadmap confirmation.

## Parallel AI Work While Backend Decides

The AI runtime workstream can proceed with:

- inventory resource YAML drafts
- inventory conversation/eval fixtures
- clarification behavior tests
- refusal/no-data tests
- deterministic follow-up refinements
- component prop contracts
- scripted-provider tests using contract-shaped payloads

Do not wire production calls to proposed tools until backend contracts are approved and tools are registered.
