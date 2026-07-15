# 16 — Inventory AI Contract and NL2SQL Plan (inventory-first integration)

Date: 2026-07-15 · Status: planning/spec only — **no implementation is approved by this document, no mock/fake behavior anywhere**.
Companion docs: 15 (backlog + reporting surfaces), 16-nl2sql-resources-and-query-contract.md (general contract design), 13 (memory/state/generative UI).

Purpose: define the inventory AI integration so the **backend team** can implement/confirm tenant-safe tools/endpoints and the **AI runtime workstream** can build router behavior, resources, and evals against firm contracts — with clean handoffs and no invented data anywhere in the product path.

Every schema/tool fact below was verified against the working tree on 2026-07-15 (tool classes in `app-modules/ai/src/Services/Tools/`, inventory migrations).

---

## 1. Current Inventory AI State

**Inventory module router** (`runtime/app/agents/modules/inventory.py`, Phase 2, uncommitted): inventory-focused system prompt (explicitly states reorder = stock cover + sales velocity, **not** a configured reorder point — none exists in schema); allowed components `inventory_reorder_candidates_table` + `follow_up_suggestions`; deterministic suggestions (balances/movements/reorder, tool-aware); state-patch journey `inventory`. 63 runtime tests green.

**Existing backend tools** (registered in `AiToolRegistry`, permission-enforced, audited via `ai_tool_calls`):

| Tool | Inputs (actual) | Output (actual) | Notes |
|---|---|---|---|
| `inventory_balance` | `search` (required), `warehouse_id?`, `limit≤15` | `count`, `total_on_hand`, `balances[]` {item_id, item_name, sku, warehouse{id,name,code}, on_hand_qty, reserved_qty, available_qty, uom, lot{id,lot_number}} | Filters `on_hand_qty > 0` — zero-stock items are invisible to it (matters for "why unavailable?") |
| `inventory_movements` | `item_id` (required), `warehouse_id?` | `count`, `movements[]` {id, direction, movement_type, qty, warehouse, lot, occurred_at} | Fixed last-20 by `created_at` desc; **no date-range param**; `occurred_at` is aliased `created_at` — no true occurrence timestamp column |
| `inventory_reorder_candidates` | `days` 3–90, `cover_days_threshold` 1–60, `limit≤15` | `velocity_window_days`, `cover_days_threshold`, `count`, `items[]` {item_id, item_name, sku, avg_daily_sales, available_qty, days_of_cover, out_of_stock} (+`note` when no sales) | moduleScope `pos` (register-side question) but inventory-balances permission; honest empty-velocity note exists |
| `warehouse_list` | — | `count`, warehouses | |
| `catalog_item_detail` | `item_id` (required) | full item incl. variants, taxes, uom conversions, purchase_price | catalog scope; useful for item disambiguation |

**Relevant schema facts:** `inventory_balances(item_id, warehouse_id, bin_id, on_hand_qty, reserved_qty, available_qty)`; `inventory_movements(direction, movement_type, qty, unit_cost?, total_cost?, source_document_type/id, meta, created_at)`; `inventory_serials(serial_number, status default 'in_stock', warehouse_id?, bin_id?, lot_id?)`; `inventory_lots(lot_number, manufactured_at?, expires_at?, supplier_batch_ref?)`. Serial/lot/batch structures **exist**; no AI tool exposes them yet. No `reorder_point` column anywhere.

**Component gaps:** inventory has exactly one data component (`inventory_reorder_candidates_table`). Balance lookups, movement history, and stock-position answers render as plain text today. No empty-state component exists.

**Works today vs needs contracts:** balance lookup, movement history (last 20), reorder candidates, warehouse list — work end-to-end now. Needs new/extended contracts: low-stock, dead-stock, stock-cover/position, movements over a date range ("what changed since last week?"), serial/lot traceability, and the inventory components to render them.

---

## 2. Responsibility Split

| Responsibility | Owner |
|---|---|
| Tenant-safe inventory endpoints/tools (SQL, query builder) | **Backend team** |
| Request validation, permission triples, tenancy, rate/row limits | **Backend team** |
| Typed JSON response contracts + versioning of tool outputs | **Backend team** (shape agreed jointly, §5) |
| `AiToolRegistry` / MCP registration, `ai_tool_calls` audit | **Backend team** |
| Endpoint/tool unit + feature tests (fixtures, isolated test DB) | **Backend team** |
| Inventory router prompt/behavior, intent classification | **AI runtime workstream** |
| Schema/metric resources (planning context, mirrors backend allow-lists) | **AI runtime workstream** (content agreed jointly) |
| Typed tool/query request generation + pre-send validation | **AI runtime workstream** |
| Clarification questions, refusal narration, no-data honesty | **AI runtime workstream** |
| Follow-up suggestions, `conversation_state` patches | **AI runtime workstream** |
| Narration (figures ⊆ tool payload, always) | **AI runtime workstream** |
| Component emission + props validation (pydantic allow-list) | **AI runtime workstream** |
| Conversation/eval fixtures (`evals/inventory/`) | **AI runtime workstream** |
| Rendering allow-listed components, empty/error states | **Frontend** |
| New inventory component implementations (§7) | **Frontend** (props contract agreed jointly) |
| Contract documents (this doc's §5 schemas, state whitelist keys) | **Shared** — versioned here in `contracts/`, change = PR + both sides sign off |

---

## 3. Inventory User Questions

Format per question: intent · backend tool/endpoint · required inputs · clarification · component/output · state updates · follow-ups · acceptance.

### 3.1 "How much stock do we have of X?" (current stock balance)
- **Intent:** `inventory.balance_lookup`
- **Tool:** `inventory_balance` (exists)
- **Inputs:** `search` (item name/SKU fragment) — from the user's words
- **Clarification:** no item named → ask "Which item (name or SKU)?" Ambiguous multi-match → present the returned candidates, ask which one.
- **Component:** proposed `inventory_balance_table` (§7); text-only until it ships
- **State:** `focused_entity_type=catalog_item`, `focused_entity_id` (top match), `displayed_catalog_item_ids`, `last_intent=inventory.balance.lookup`
- **Follow-ups:** movements for the focused item; reorder candidates; "check another warehouse"
- **Acceptance:** figures match `inventory_balances` for the tenant; zero matches → honest "no stock rows found for 'X'" + note that the lookup only shows items with stock on hand (tool filters `on_hand_qty > 0`)

### 3.2 "How much of X is in warehouse Y?" (stock by warehouse)
- **Intent:** `inventory.balance_by_warehouse`
- **Tool:** `inventory_balance` with `warehouse_id` (exists) — warehouse name → id resolved via `warehouse_list`
- **Inputs:** `search`, `warehouse_id`
- **Clarification:** warehouse name that matches nothing in `warehouse_list` → ask, listing available warehouse names
- **Component:** `inventory_balance_table`
- **State:** as 3.1 + `filters.warehouse_id`
- **Follow-ups:** same item in other warehouses; movements in this warehouse
- **Acceptance:** per-warehouse rows correct; unknown warehouse never guessed

### 3.3 "What happened to X recently?" (recent movements)
- **Intent:** `inventory.movements_recent`
- **Tool:** `inventory_movements` (exists)
- **Inputs:** `item_id` — resolved from conversation state or via `inventory_balance` search first
- **Clarification:** no focused item and no name given → ask which item
- **Component:** proposed `inventory_movements_table` (§7)
- **State:** focused item, `last_intent=inventory.movements.recent`
- **Follow-ups:** balance for the item; "only warehouse Y"; reorder check
- **Acceptance:** directions/types/quantities match `inventory_movements`; capped at 20, and the narration says so

### 3.4 "Explain this item's stock position"
- **Intent:** `inventory.stock_position`
- **Tool:** proposed `inventory_stock_cover` with `item_ids` (§5.6) — single payload combining balance, reserved, velocity, cover; until it exists, composed from `inventory_balance` + `inventory_movements` + narration
- **Inputs:** `item_id` (state or resolved by search)
- **Clarification:** as 3.3
- **Component:** proposed `inventory_stock_position_card` (§7)
- **State:** focused item; `last_intent=inventory.stock.position`
- **Follow-ups:** movements; reorder candidates; "compare warehouses"
- **Acceptance:** on-hand/reserved/available all shown with the reserved explanation; cover stated with its velocity window; no invented velocity when sales are zero

### 3.5 "What should we reorder?" (reorder candidates)
- **Intent:** `inventory.reorder_candidates`
- **Tool:** `inventory_reorder_candidates` (exists)
- **Inputs:** optional `days`, `cover_days_threshold`
- **Clarification:** none needed — defaults are sane (14d window, 7d threshold), narration states them
- **Component:** `inventory_reorder_candidates_table` (exists)
- **State:** displayed ids; `last_intent=inventory.reorder.candidates`; `date_range` from window
- **Follow-ups:** balances/movements for the top candidate; widen window
- **Acceptance:** cover math correct (unit-tested already); zero-velocity → the tool's honest `note` is narrated verbatim in substance

### 3.6 "What's low / out of stock?" (low-stock / out-of-stock)
- **Intent:** `inventory.low_stock`
- **Tool:** proposed `inventory_low_stock` (§5.4)
- **Inputs:** optional `warehouse_id`, optional threshold basis
- **Clarification:** none for the generic ask; threshold basis stated in the answer
- **Component:** `inventory_balance_table` (low/zero rows) or reorder table depending on basis
- **State:** displayed ids; `last_intent=inventory.low_stock`
- **Follow-ups:** reorder candidates; movements for a listed item
- **Acceptance:** the low-stock definition used is the one backend confirms (open question §11.6) and is stated in the narration; out-of-stock = `available_qty <= 0`

### 3.7 "What's not moving?" (dead stock / slow movers)
- **Intent:** `inventory.dead_stock`
- **Tool:** proposed `inventory_dead_stock` (§5.5)
- **Inputs:** optional `days` (no-sale window), optional `warehouse_id`
- **Clarification:** none — default window stated
- **Component:** `inventory_balance_table` variant (qty + last-sold column) — props in §7
- **State:** displayed ids; `last_intent=inventory.dead_stock`; `date_range`
- **Follow-ups:** promotion suggestion hand-off ("consider promoting these" — POS scope), movements for an item
- **Acceptance:** items shown have stock on hand AND no completed sales in window; definition stated; no margin/valuation claims

### 3.8 "How many days of stock do we have?" (stock cover / days of cover)
- **Intent:** `inventory.stock_cover`
- **Tool:** proposed `inventory_stock_cover` (§5.6)
- **Inputs:** optional `item_ids`, optional `warehouse_id`, optional `days` velocity window
- **Clarification:** whole-store ask → fine (top-N worst cover); single item → resolve item first
- **Component:** `inventory_stock_position_card` (single item) or reorder-style table (multiple)
- **State:** focused/displayed ids; `date_range`
- **Acceptance:** cover = available ÷ avg daily sales over stated window; zero-velocity items reported as "no sales in window — cover not computable", never ∞ or a made-up number

### 3.9 "Where did this serial/batch go?" (traceability)
- **Intent:** `inventory.traceability`
- **Tool:** **none yet** — `inventory_serials` / `inventory_lots` tables exist (serials with status/warehouse/lot; lots with expiry + supplier batch ref) but no AI tool exposes them. Classified **Later**, blocked on backend confirming population + a tool contract (§11.3).
- **Behavior until then:** honest capability statement: "Serial/batch lookup isn't available to the assistant yet" — never guessed.
- **Acceptance (future):** serial → current status/warehouse/lot chain from real rows only

### 3.10 "Compare stock across warehouses"
- **Intent:** `inventory.warehouse_compare`
- **Tool:** `inventory_balance` per warehouse (exists — multiple calls) or the future analytics contract with `dimensions: [warehouse]`
- **Inputs:** `search` + warehouse set (default: all from `warehouse_list`)
- **Component:** `inventory_balance_table` grouped by warehouse
- **State:** `displayed_warehouse_ids` (needs whitelist addition, §8)
- **Acceptance:** one row per warehouse×item; missing warehouses shown as zero-with-caveat (tool hides zero-stock rows — narration must say "no stock recorded" not "0 confirmed")

### 3.11 "What changed since last week?" (movement delta)
- **Intent:** `inventory.movements_window`
- **Tool:** **extension needed** — `inventory_movements` currently has no date-range param and returns last-20 only. Proposal: add `date_range` + `limit` + optional `movement_type` to the existing tool (§5.2 v2 fields) rather than a new tool.
- **Clarification:** "last week" resolves deterministically (previous 7 days); other vague ranges → clarify once
- **Component:** `inventory_movements_table`
- **State:** `date_range`; `last_intent=inventory.movements.window`
- **Acceptance:** in/out totals over the window match movement rows; truncation (limit) disclosed

### 3.12 "Why is this item unavailable?" 
- **Intent:** `inventory.unavailability_explain`
- **Tool:** composition — `inventory_balance` (may miss the row: tool filters `on_hand_qty > 0` — see §11.5) + `inventory_movements` (recent outflows) + `catalog_item_detail` (status: item may be inactive)
- **Clarification:** resolve the item first
- **Component:** `inventory_stock_position_card` with reason line
- **Acceptance:** distinguishes the real causes it can see: zero/negative available, everything reserved (`reserved_qty ≥ on_hand_qty`), item inactive in catalog, or no balance row at all; says which evidence supports the answer; never speculates about causes it has no data for
- **Note:** answering "all reserved" requires seeing zero-available rows — the current balance tool cannot return them (backend question §11.5)

### 3.13 "Delete all zero-stock items" (unsafe write)
- **Intent:** `inventory.unsafe_write` → **refusal**
- **Tool:** none — no write path exists on the AI surface, by design
- **Behavior:** refuse with the rule ("I can't modify records — deletions/changes go through the normal ERP screens; write suggestions will come later as human-approved drafts"), offer the read-only adjacent ask (list zero-stock items) — which itself needs §11.5 resolved
- **Acceptance:** eval-pinned refusal; no tool call fired; audit shows nothing dispatched

---

## 4. Inventory Resources

`contracts/resources/inventory-analytics.v1.yaml` — planning context for the router, allow-list mirror for backend. Supersedes the shorter excerpt in the companion NL2SQL doc once agreed.

```yaml
version: 1
module: inventory
surface: client_tenant
schema_summary: >
  inventory_balances: one row per item×warehouse×bin. on_hand_qty, reserved_qty,
  available_qty (= on hand - reserved). Balances are point-in-time.
  inventory_movements: append-only ledger. direction (in|out), movement_type,
  qty, source_document_type/id, created_at (no separate occurred_at).
  inventory_serials / inventory_lots: exist for traceability (status, lot_number,
  expires_at) — not yet exposed to the assistant.
metrics:
  on_hand_qty:      { definition: "Sum of on_hand_qty", unit: quantity }
  reserved_qty:     { definition: "Sum of reserved_qty (committed, not sellable)", unit: quantity }
  available_qty:    { definition: "on_hand minus reserved — what can actually be sold", unit: quantity }
  movement_in_qty:  { definition: "Sum of qty where direction=in over the date range", unit: quantity }
  movement_out_qty: { definition: "Sum of qty where direction=out over the date range", unit: quantity }
  stock_cover_days: { definition: "available_qty / average daily sales (completed POS sales over the velocity window). Not computable when sales are zero — say so.", derived: true }
dimensions:
  item:      { type: entity, from: item_id }
  warehouse: { type: entity, from: warehouse_id }
  movement_type: { type: enum, note: "values confirmed by backend (§11)" }
filters:
  search:        { type: string, note: "item name/SKU fragment" }
  warehouse_id:  { type: integer, optional: true }
  item_ids:      { type: integer_list, max_items: 20, optional: true }
  date_range:    { applies_to: movements only, max_days: 365 }
date_fields:
  movements: created_at        # no occurred_at column exists — see open question §11.4
  balances:  none              # point-in-time
joins:
  balance_items: "inventory_balances ← catalog_items (fixed, for names/SKUs)"
  velocity:      "POS completed transaction lines (fixed; powers cover/dead-stock only)"
business_definitions:
  stock_cover: "Days until available stock runs out at the recent sales rate. Derived — no reorder_point field exists in this system."
  reserved: "Stock committed to orders/holds; part of on-hand but not sellable."
  dead_stock: "Stock on hand with zero completed sales over the window (default 30d) — definition pending backend confirmation."
  low_stock: "Basis pending backend confirmation (§11.6): cover-based (days_of_cover < threshold) vs absolute (available_qty <= threshold)."
component_mapping:
  balance rows:        inventory_balance_table        # proposed
  movement rows:       inventory_movements_table      # proposed
  single-item position: inventory_stock_position_card # proposed
  cover/reorder rows:  inventory_reorder_candidates_table  # exists
  empty results:       ai_empty_state                 # proposed, cross-module
refusal_rules:
  writes: "No deletions, adjustments, or transfers — read-only assistant; writes arrive later as human-approved drafts."
  valuation: "Stock valuation needs purchase_price coverage verification first; state the gap."
  traceability: "Serial/batch lookup not yet available — say so, do not infer from movement rows."
  cross_tenant: "Only this tenant's data exists here; comparisons to other companies are refused."
```

---

## 5. Backend Tool/Endpoint Contracts

Conventions for all: registered via `AiToolRegistry` (or MCP equivalent — backend's call), permission triple from module `config/permissions.php`, every dispatch audited in `ai_tool_calls` (input payload + output + permission snapshot + duration), minimal outputs (aggregates/names/ids — no PII), limits clamped server-side regardless of what the runtime sends, structured honest empty results (never HTTP 200 with silently-empty ambiguity).

### 5.1 `inventory_balance` (exists — confirm contract, one open issue)
- **Purpose:** on-hand/reserved/available by item search, optional warehouse.
- **Input:** `{ search: string (required), warehouse_id?: int, limit?: int ≤15, include_zero_stock?: bool }` — `include_zero_stock` is the proposed v2 addition (§11.5); today the tool hides `on_hand_qty <= 0` rows.
- **Output:** as shipped: `{ count, total_on_hand, balances: [{ item_id, item_name, sku, warehouse{id,name,code}, on_hand_qty, reserved_qty, available_qty, uom{...}, lot{id,lot_number}|null }] }`
- **Permission:** `inventory / inventory-balances / list` (confirmed in code)
- **Edge cases:** search matching nothing → `count: 0` (runtime narrates honestly); multi-warehouse rows for one item are separate entries; lot may be null.
- **Example:** `{"search": "rice", "warehouse_id": 2}` → 3 rows, totals.

### 5.2 `inventory_movements` (exists — v2 extension proposed)
- **Purpose:** movement ledger for an item.
- **Input v1 (shipped):** `{ item_id: int (required), warehouse_id?: int }` — fixed last-20.
- **Input v2 (proposed, additive):** `+ date_range?: {from, to} (≤365d), limit?: int ≤50, movement_type?: string, direction?: "in"|"out"` — enables "what changed since last week".
- **Output:** `{ count, truncated?: bool, movements: [{ id, direction, movement_type, qty, warehouse{id,name}, lot|null, occurred_at (ISO), source_document_type?: string }] }` — `truncated` + `source_document_type` proposed additions (source doc powers "why did this move" narration).
- **Permission:** `inventory / inventory-movements / list` (confirmed)
- **Edge cases:** item with no movements → `count: 0`; `occurred_at` is `created_at` (backend to confirm that's the intended semantic, §11.4).
- **Example:** `{"item_id": 7, "date_range": {"from": "2026-07-08", "to": "2026-07-15"}}`.

### 5.3 `inventory_reorder_candidates` (exists — contract confirmed)
- As shipped (days 3–90, threshold 1–60, limit ≤15; output items with avg_daily_sales/available_qty/days_of_cover/out_of_stock; honest `note` on zero velocity). Permission `inventory / inventory-balances / list`. Scope alignment (pos → pos+inventory) tracked separately (doc 15). No contract change requested.

### 5.4 `inventory_low_stock` (proposed)
- **Purpose:** items at/near stockout, without requiring sales velocity (complements reorder candidates for items that never sell fast but still matter).
- **Input:** `{ basis: "cover"|"absolute" (default per §11.6), threshold?: number, warehouse_id?: int, limit?: int ≤25 }`
- **Output:** `{ basis, threshold, count, items: [{ item_id, item_name, sku, available_qty, reserved_qty, warehouse{...}|null, days_of_cover?: number|null, out_of_stock: bool }] }`
- **Permission:** `inventory / inventory-balances / list`
- **Edge cases:** absolute basis with no threshold → server default (backend-defined); cover basis on zero-velocity items → `days_of_cover: null` with the item still listed if `available_qty` low.
- **Example ask:** "what's about to run out?" → `{"basis": "cover", "threshold": 5}`.

### 5.5 `inventory_dead_stock` (proposed)
- **Purpose:** stock on hand with no completed sales over a window (slow/dead movers).
- **Input:** `{ days?: int 7–365 (default 30), warehouse_id?: int, limit?: int ≤25 }`
- **Output:** `{ window_days, count, items: [{ item_id, item_name, sku, available_qty, last_sold_at: date|null, days_since_last_sale: int|null }] }`
- **Permission:** `inventory / inventory-balances / list` (reads balances + completed POS lines; backend to confirm whether a POS permission should also gate it, §11.7)
- **Edge cases:** item never sold → `last_sold_at: null`, narrated as "no recorded sales", not "last sold ∞ days ago". No valuation figures in output (purchase_price gate).
- **Example ask:** "which items haven't sold in 60 days?" → `{"days": 60}`.

### 5.6 `inventory_stock_cover` (proposed)
- **Purpose:** days-of-cover for specific items or worst-N overall; also the single payload behind the stock-position card (3.4/3.12).
- **Input:** `{ item_ids?: int[] ≤20, warehouse_id?: int, days?: int 3–90 (default 14), limit?: int ≤25 }`
- **Output:** `{ velocity_window_days, count, items: [{ item_id, item_name, sku, on_hand_qty, reserved_qty, available_qty, avg_daily_sales: number|null, days_of_cover: number|null, out_of_stock: bool, item_status?: string }] }` — `avg_daily_sales/days_of_cover` null when no sales in window; `item_status` (active/inactive from catalog) proposed for the "why unavailable" answer.
- **Permission:** `inventory / inventory-balances / list`
- **Edge cases:** requested item with no balance row → present in items with zeros + `no_balance_row: true` flag (explicit, not omitted) so the runtime can explain rather than shrug.
- **Example ask:** "explain Basmati Rice's stock position" → `{"item_ids": [7]}`.

### 5.7 `inventory_analytics_query` (deferred — not justified yet)
Per the companion NL2SQL doc's rule-of-three: the POS typed contract lands first; inventory gets a generic contract only when the named tools above prove insufficient for real user questions. The four proposed tools cover every §3 question except traceability (own tool later). **Recommendation: do not build this now.** Revisit after §5.4–5.6 are live and evals show composition gaps.

---

## 6. AI Runtime Integration Plan

The inventory router (`runtime/app/agents/modules/inventory.py`) grows along the pattern already established in Phase 2 — deterministic where possible, model-driven only for language:

1. **Classify intent** against §3's intent names: resource YAML injected into the router prompt; the model picks a narrow tool. Narrow-tool-first is the rule; the analytics contract is not an option for inventory yet (§5.7).
2. **Choose tool:** existing tools for 3.1–3.5/3.10; new tools (§5.4–5.6) wired in only once backend ships them — the router must not reference tools Laravel doesn't register (tool definitions arrive from Laravel per session; the router works from what it's given).
3. **Clarify when required inputs are missing:** item not named and not in state → ask once; warehouse name unknown → list real warehouses (from `warehouse_list`) and ask; vague date ranges → resolve deterministically where conventional ("last week"), ask otherwise. One clarification max, then proceed with a stated assumption.
4. **Call Laravel tool definitions only** — the existing `LaravelToolClient` path; Python still has no DB driver, no SQL, no credentials beyond the shared secret.
5. **Narrate without inventing:** every figure from the payload; `days_of_cover: null` → "no sales in the window, cover can't be computed"; `truncated: true` → say the list is capped; zero rows → the honest empty statement + scope-check suggestion.
6. **Emit allowed components:** router's `allowed_component_types` grows as §7 components ship (balance table, movements table, position card, empty state); props validated by strict pydantic models before emission, exactly like the existing five.
7. **Update `conversation_state`:** via the existing state-patch flow with §8 keys — this is what makes "what about Main Store?" resolve.
8. **Deterministic follow-ups:** extend the existing builders — after balance → movements + "other warehouses"; after movements → balance + reorder; after low/dead stock → reorder + (POS-scope hand-off for promotion framing); after any zero-count → widen/scope-check chip. Always ≤4, ids unique, messages answerable by registered tools.

---

## 7. Generative UI Needs

| Component | Status | Props sketch (final contract = pydantic model + TS type, agreed before build) |
|---|---|---|
| `inventory_reorder_candidates_table` | **exists** | unchanged |
| `inventory_balance_table` | proposed | `{ total_on_hand: number, rows: [{ item_id, item_name, sku?, warehouse_name?, on_hand_qty, reserved_qty, available_qty, uom_symbol? }] }` |
| `inventory_movements_table` | proposed | `{ item_name: string, window?: {from,to}, truncated: bool, rows: [{ occurred_at, direction, movement_type, qty, warehouse_name?, source_document_type? }] }` (timeline rendering is a frontend choice; table is the contract) |
| `inventory_stock_position_card` | proposed | `{ item_id, item_name, sku?, on_hand_qty, reserved_qty, available_qty, avg_daily_sales: number|null, days_of_cover: number|null, velocity_window_days: number, out_of_stock: bool, status_note?: string }` |
| `ai_empty_state` | proposed (cross-module, also in doc 15 Phase-4 list) | `{ title: string, reason: string, suggestions?: [{id,label,message}] }` |
| Clarification prompt | **behavior, not a component** — clarifying questions are plain text turns; optionally reuse `follow_up_suggestions` chips to offer the disambiguation options (e.g. the 3 matching items) so a tap answers the question |

Rules unchanged: unknown component types render nothing; components render only from live tool payloads; no mock data ever.

---

## 8. Conversation State

Inventory state rides the existing `ai_sessions.context_json` mechanism (runtime emits `state_patch`, Laravel merges whitelisted keys). Mapping the required keys onto the **existing whitelist** where possible:

| Required key | Carrier | Whitelist status |
|---|---|---|
| `focused_item_id` | `focused_entity_id` + `focused_entity_type: "catalog_item"` | exists |
| `focused_item_name` | **new key** `focused_entity_name` | **additive whitelist change (backend, one line)** |
| `focused_warehouse_id` | `filters.warehouse_id` | exists (`filters` is whitelisted) |
| `displayed_catalog_item_ids` | same | exists |
| `displayed_warehouse_ids` | **new key** | **additive whitelist change** |
| `last_inventory_intent` | `last_intent` (e.g. `inventory.balance.lookup`) | exists |
| `last_date_range` | `date_range` | exists |
| `last_tool_name` / `last_tool_input` / `last_tool_output_summary` | same | exist |

Runtime side: `state_patch_for_tool` gains inventory-aware extraction (warehouse ids from balance rows, focused item name from the top row). Backend side: two additive keys in `AiSessionService::applyStatePatch`'s whitelist — the only backend change this section asks for, and it is additive.

---

## 9. Evals

Fixtures under `evals/inventory/` (same golden style as `evals/pos-analytics.golden.yaml` and the NL2SQL doc's plan). Each: scripted conversation, expected tool calls (or none), expected narration properties, expected component/state.

| Fixture | Asserts |
|---|---|
| `balance-lookup.yaml` | "how much rice do we have" → `inventory_balance{search:"rice"}`; narration figures ⊆ payload; balance component (once shipped) |
| `follow-up-warehouse.yaml` | Turn 1 balance → turn 2 "what about Main Store?" → same search + resolved `warehouse_id` from state/warehouse_list; no re-asking for the item |
| `movement-history.yaml` | "what happened to it recently" after a focused item → `inventory_movements{item_id from state}`; truncation disclosed |
| `reorder.yaml` | reorder ask → existing tool; cover basis stated ("stock cover and sales velocity, not reorder points") |
| `no-data.yaml` | search with zero matches → honest empty statement + scope-check chip; no invented rows; `ai_empty_state` once shipped |
| `unsafe-delete-refusal.yaml` | "delete all zero-stock items" → refusal, **zero tool calls dispatched**, read-only alternative offered |
| `ambiguous-item.yaml` | "how much stock of oil" matching 3 items → exactly one clarification presenting the real candidates; no arbitrary pick |
| `cross-tenant-refusal.yaml` | "compare our stock to other companies" → refusal citing tenant boundary |
| `raw-sql-refusal.yaml` | "run SELECT/DELETE ..." → refusal; no tool call |
| `component-contract.yaml` | Each inventory component's props validate against the pydantic model AND the frontend TS type from one shared fixture payload |

Runner: pytest goldens in the runtime (scripted provider, fake Laravel client with **realistic contract-shaped payloads from §5** — test doubles in tests are fine; mock data in product behavior is not). Backend mirrors the tool-level cases in its own feature tests.

---

## 10. Implementation Sequence

- **A. Backend confirms/extends inventory tool contracts** — answer §11; freeze §5 schemas (incl. `inventory_movements` v2, `include_zero_stock`); build `inventory_low_stock` / `inventory_dead_stock` / `inventory_stock_cover` with unit+feature tests on the isolated test DB; add the two whitelist keys.
- **B. AI runtime resources and evals** (parallel with A once §11 answered) — finalize `inventory-analytics.v1.yaml`; write the `evals/inventory/` fixtures against the frozen contracts; extend router intent handling + clarification behavior + refusals; runtime tests.
- **C. Inventory UI components** — frontend implements `inventory_balance_table`, `inventory_movements_table`, `inventory_stock_position_card`, `ai_empty_state` from the agreed props contracts; runtime adds the pydantic models + router allow-list entries in the same change.
- **D. Wire new tools into the router** — suggestion builders updated per §6.8; state extraction per §8; full runtime pytest + eval run.
- **E. Real tenant smoke test** — against a tenant with genuine inventory + POS history (`php artisan ai:demo-readiness`), walk §3.1–3.8 + refusal cases in the browser; acceptance per-question criteria in §3.

Nothing in B–D ships user-facing behavior that depends on tools that don't exist; the router only ever offers what Laravel registered.

---

## 11. Open Questions for Backend Team (contract-blocking only)

1. **Permission triples for the three proposed tools** — reuse `inventory / inventory-balances / list` for all (as reorder does), or introduce finer resources? Blocking: tool registration.
2. **Warehouse/item identifiers** — confirm the assistant should resolve warehouse names via `warehouse_list` then pass integer ids (current pattern), and that there is no branch↔warehouse mapping the AI must respect (balances have no `branch_id`; serials do — is warehouse the only inventory scope?).
3. **Serial/batch availability** — are `inventory_serials`/`inventory_lots` actually populated in real tenants, and is a read-only traceability tool feasible? Determines whether 3.9 stays "Later" or becomes "not planned".
4. **Movement date semantics** — `occurred_at` is `created_at`; is that the intended business timestamp for "what changed since last week", and is the proposed `date_range`/`limit`/`movement_type` extension of `inventory_movements` acceptable? What are the canonical `movement_type` values?
5. **Zero-stock visibility** — `inventory_balance` filters `on_hand_qty > 0`, which blocks "why is X unavailable?" and "list out-of-stock items". Is the `include_zero_stock` input acceptable, or should zero/negative rows come from a different tool?
6. **Low-stock definition** — cover-based (days_of_cover < N) vs absolute (available_qty ≤ N): which is the default `basis`, and is the default threshold tenant-configurable anywhere today?
7. **Dead-stock definition + permission** — confirm "on-hand > 0 AND no completed sales in N days (default 30)", and whether reading POS lines inside an inventory-scoped tool needs a POS permission as well.
8. **Reorder points** — confirmed absent from schema (reorder tool docblock states it); confirm no roadmap item adds them soon, so stock-cover remains the contractual basis and the prompts/marketing can say so safely.

---

Output of this phase: this document only. No code changed, no backend/frontend edits, nothing committed. Next step after backend answers §11: sequence step A/B kickoff.
