# AlphaSoft AI Memory, State, Suggestions, and Generative UI Plan

Date: 2026-07-07

Scope: design the durable conversation layer and runtime state model for the Python orchestration path, using the current Laravel-backed ERP tools. This is a plan only; no commits are implied.

## Reference Findings

### Carduka

Carduka separates four concerns that AlphaSoft should not collapse into one table:

1. Durable conversation threads/messages in SQL.
   - `conversation_threads`: owner, title, status, summary, persisted context, last message timestamp.
   - `conversation_messages`: ordered text/component blocks plus trace/tools.
   - Threads are owner-scoped and support list/get/rename/delete.

2. Short-lived runtime state in a session store.
   - Redis-backed with in-memory fallback only for local/tests.
   - State includes active journey, last intent, focused entity, displayed entity ids, comparison ids, search constraints, and a compact summary.
   - IDs are user-scoped: browser-supplied session ids are prefixed with the authenticated user.

3. Deterministic follow-up suggestions.
   - Suggestions are not free-form model output.
   - They are generated from validated/rendered entities and carry allow-listed actions.
   - They cap at four suggestions.

4. Ordered message blocks in the frontend.
   - The UI stores a message as `blocks[]`, where each block is text or a component.
   - Components render exactly where they were emitted, not in a separate list after all text.

### ADK Samples

The useful ADK patterns are:

1. Session state as explicit keys, not hidden prompt memory.
   - Tools and callbacks read/write namespaced state such as `database_settings`, `sql_query`, and query results.
   - This maps well to AlphaSoft state like `displayed_item_ids`, `focused_item_id`, and `last_tool_outputs`.

2. Event/session separation.
   - ADK runners create sessions and stream events; application data/artifacts stay in domain tables.
   - The Navallist sample links domain records to `adk_session_id` and stores generated artifacts separately.

3. Conversation-plan evals.
   - ADK eval notebooks model realistic multi-turn conversations with a plan, then score tool trajectory and final answer quality.
   - AlphaSoft should add multi-turn evals for follow-ups, ordinal references, empty data, and component generation.

## Target Architecture

Keep the runtime boundary from the audit:

- Laravel owns tenant data, auth, permission checks, AI sessions, tool registry, audit logs, and persisted conversation data.
- Python owns orchestration, prompt assembly, model calls, state interpretation, tool selection, and component proposal.
- Frontend owns rendering only through an allow-listed component registry.

The memory model should have three layers.

### Layer 1: Durable Transcript

Backend tenant DB.

Tables:

- `ai_sessions`: already exists.
- `ai_messages`: expand the new audit-fix table into a replayable message block store.

Recommended `ai_messages` shape:

- `id`
- `ai_session_id`
- `user_id`
- `role`: `user | assistant | system`
- `status`: `pending | complete | failed | interrupted`
- `sequence_number`
- `content_json`: ordered blocks
- `trace_json`
- `tools_json`
- `token_input`
- `token_output`
- `created_at`

Block schema:

```json
[
  {"type": "text", "text": "Here are the lagging items."},
  {
    "type": "component",
    "component_type": "pos_lagging_items_table",
    "schema_version": 1,
    "props": {}
  }
]
```

This replaces the current `content` string as the real replay format. A plain text projection can remain for search/display.

### Layer 2: Conversation State

Backend tenant DB, serialized on `ai_sessions.context_json` or a new `ai_session_states` table.

State should be structured, small, and deterministic:

```json
{
  "version": 1,
  "active_journey": "pos_analytics",
  "last_intent": "pos.lagging_items",
  "focused_entity_type": "catalog_item",
  "focused_entity_id": 123,
  "displayed_catalog_item_ids": [123, 456],
  "displayed_transaction_ids": [],
  "displayed_component_ids": ["cmp_..."],
  "last_tool_name": "pos_lagging_items",
  "last_tool_input": {},
  "last_tool_output_summary": {},
  "date_range": {"from": "2026-06-23", "to": "2026-07-07"},
  "filters": {"branch_id": null, "warehouse_id": null},
  "conversation_summary": ""
}
```

Rules:

- Store IDs and compact facts, not large raw result sets.
- Never store untrusted browser labels as state.
- State is written by Laravel after Python returns state patches, or by Laravel when it emits/replays components.
- State must always be scoped by `tenant_id`, `user_id`, and `ai_session_id`.

### Layer 3: User Memory

Later, not in the first production slice.

Potential table: `ai_user_memories`.

Only persist explicit user preferences, not inferred operational facts:

- preferred dashboard/module
- preferred branch/warehouse filter
- preferred reporting period
- preferred currency/display format

Do not store:

- arbitrary employee/customer personal data extracted from chat
- business secrets from tool results
- model-generated guesses

User memory must be inspectable and clearable.

## Suggestions and Follow-Ups

Move from hardcoded Python suggestions to deterministic suggestion builders.

### Backend Contract

Component type: `follow_up_suggestions`.

Suggestion schema:

```json
{
  "id": "lagging-last-30",
  "label": "Lagging items",
  "message": "Show lagging items for the last 30 days",
  "action": {
    "type": "run_tool",
    "tool": "pos_lagging_items",
    "input": {"window_days": 30}
  }
}
```

For the first slice, support both:

- `message`: fallback text prompt
- `action`: allow-listed structured action

Action execution should go back through Laravel, not directly to Python, so auth/session ownership and tool permissions remain enforced.

### Suggestion Builders

Implement in Python first, because Python sees the selected tool result and can emit UI components. Keep them deterministic and data-derived.

Builders:

- `suggestions.for_top_items(output, state)`
  - compare previous period
  - show lagging items
  - check reorder candidates

- `suggestions.for_lagging_items(output, state)`
  - show sales summary
  - top sellers
  - reorder candidates for stopped items

- `suggestions.for_sales_summary(output, state)`
  - top sellers in same period
  - lagging items in same period
  - branch comparison later

- `suggestions.for_reorder_candidates(output, state)`
  - show movement history for first candidate
  - top sellers
  - inventory balance

Rules:

- Cap at four.
- Reference IDs only from rendered/current tool output.
- Never suggest destructive actions.
- If no data, suggestions should help diagnose the scope: widen date range, check POS setup, switch branch, inspect completed transactions.

## Generative UI Plan

Current AlphaSoft frontend renders components separately after text. Move to ordered blocks.

Frontend message model:

```ts
type AiMessageBlock =
  | { type: "text"; text: string }
  | {
      type: "component";
      component_type: AiComponentType;
      schema_version: number;
      props: Record<string, unknown>;
    };
```

Renderer rules:

- Unknown components render nothing and log in dev.
- Components are compact operational UI, not marketing cards.
- Buttons/chips in suggestions call structured actions where possible.
- Components should be replayable from persisted `content_json`.

Near-term component set:

- `pos_top_items_table`
- `pos_lagging_items_table`
- `pos_sales_summary_card`
- `inventory_reorder_candidates_table`
- `follow_up_suggestions`

Next component set:

- `inventory_balance_table`
- `inventory_movements_timeline`
- `catalog_item_detail_panel`
- `tool_empty_state`
- `metric_delta_card`

## Backend API Plan

Add tenant AI thread endpoints around existing `ai_sessions`:

- `GET /api/v1/tenant/ai/sessions`
- `GET /api/v1/tenant/ai/sessions/{session}`
- `PATCH /api/v1/tenant/ai/sessions/{session}`
- `DELETE /api/v1/tenant/ai/sessions/{session}`

Payload should include:

- session metadata
- title
- status
- module scope
- last message timestamp
- messages with ordered blocks
- context summary, not full state by default

For the demo, keep the current side panel session flow if time is tight. For production, add a thread sidebar similar to Carduka.

## Python Runtime Plan

Accept richer request:

```json
{
  "tenant_id": "tenant",
  "user_id": 1,
  "session_id": 10,
  "module_scope": "pos",
  "message": "...",
  "messages": [],
  "conversation_state": {},
  "tool_definitions": []
}
```

Return/emit:

- tokens
- tool events
- component events
- trace events
- state_patch events
- done

Add `state_patch` event:

```json
{
  "active_journey": "pos_analytics",
  "last_intent": "pos.top_items",
  "displayed_catalog_item_ids": [1, 2, 3],
  "focused_entity_type": "catalog_item",
  "focused_entity_id": 1
}
```

Laravel applies only allow-listed state keys.

## Evaluation Plan

Add multi-turn evals before expanding UI:

1. Follow-up memory:
   - User: "Show top sellers for 14 days."
   - User: "What about the slow ones?"
   - Expected: calls `pos_lagging_items` with sensible related period.

2. Empty-result behavior:
   - Tool returns no rows.
   - Expected: says no data, emits diagnostic suggestions, does not invent.

3. Ordinal/reference resolution:
   - First result renders items.
   - User: "Show movements for the first one."
   - Expected: resolves first displayed item id from state, not model guessing.

4. Component replay:
   - Persist assistant message with text + component blocks.
   - Reload session.
   - Expected: same ordered UI appears without re-running tools.

5. Permission narrowing:
   - User lacks a module permission.
   - Expected: tool definition absent; action/suggestion cannot invoke it.

## Delivery Sequence

### Phase 0: Stabilize Current Audit Fix

- Keep `ai_messages` migration.
- Add recent-history replay.
- Run real tenant readiness check.

### Phase 1: Durable Blocks

- Change `ai_messages.content` to `content_json` or add `content_json` beside `content`.
- Persist assistant text, components, trace, and tools as ordered blocks.
- Frontend renders blocks.
- Add session reload API.

### Phase 2: Conversation State

- Add `context_json` to `ai_sessions` or `ai_session_states`.
- Python emits `state_patch`.
- Laravel validates/applies state patches.
- Runtime receives state on every turn.

### Phase 3: Deterministic Suggestions

- Replace hardcoded Python suggestions with `suggestions.py`.
- Add structured suggestion actions.
- Frontend sends suggestion actions to Laravel chat endpoint.

### Phase 4: Thread UX

- Session/thread sidebar.
- Rename/delete/list sessions.
- Auto-title after first user message, then optional LLM title later.
- Restore old sessions with components.

### Phase 5: User Memory

- Explicit preferences only.
- Inspect/clear endpoint.
- Prompt injection guard: only update from user statements matching conservative patterns or explicit UI confirmation.

## Decisions Needed

1. Should AlphaSoft call them `sessions` everywhere, or introduce user-facing `threads` while keeping `ai_sessions` internally?
   - Recommendation: user-facing "conversations"; backend can keep `ai_sessions`.

2. Should runtime state live in Laravel SQL or Redis?
   - Recommendation: SQL JSON first. Redis only when we need high-frequency collaborative/session state.

3. Do follow-up chips submit text only or structured actions?
   - Recommendation: both initially, but prefer structured actions for suggestions generated from tool output.

4. Do we persist full component props?
   - Recommendation: yes for replay, but hydrate mutable action state on reload later if/when actions can mutate data.

5. Do we implement ADK itself?
   - Recommendation: no. Borrow the session/state/eval patterns. Keep the current small FastAPI runtime until workflow complexity actually demands a graph framework.
