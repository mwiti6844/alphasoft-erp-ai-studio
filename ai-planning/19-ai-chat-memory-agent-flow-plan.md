# 19 — AI Chat, Memory, and Agent Flow Plan

**Date:** 2026-07-16
**Status:** Planning only — no implementation approved by this document. No code changes, no backend/frontend edits, no commits accompany it.
**Companions:**
- doc 13 — Memory, State, and Generative UI Plan (`13-memory-state-generative-ui-plan.md`)
- doc 15 — Meeting AI Product Backlog (`15-meeting-ai-product-backlog.md`)
- doc 16 — Inventory AI Contract and NL2SQL Plan (`16-inventory-ai-contract-and-nl2sql-plan.md`)
- doc 17 — NL2SQL Resources and Typed Analytics Query Contract (`17-nl2sql-resources-and-query-contract.md`)
- doc 18 — Inventory Backend Contract Questions (`18-inventory-backend-contract-questions.md`)

**Scope:** Design the full chat-based AI system for AlphaSoft ERP: memory management (short-term, session, long-term), conversation flows, follow-up questions, agent/module design and agent-to-agent communication, knowledge-base/flow guidance, frontend chat UX, and how the AI consumes backend APIs/tools/MCP as they become available.

**Non-negotiable boundaries (restated from docs 15–17, binding here):**
- Laravel owns tenant data, auth, permissions, tool execution, persistence, audit, and all business writes.
- Python/FastAPI owns orchestration, module routing, model calls, memory interpretation, follow-up generation, and component proposals.
- Python never connects to tenant databases. No raw SQL from model output. All ERP facts come through Laravel tools/endpoints.
- Frontend renders only allow-listed components.
- Writes/destructive actions become human-approved drafts (`ai_suggestions`), never direct AI writes.
- No fake/mock data in product behavior. Test doubles only in tests/evals.

---

## 1. Current State Summary

Everything below was verified against the working trees on 2026-07-16. File references are the source of truth; where a companion doc disagrees with code, code wins.

### 1.1 What works today

**Frontend** (`alpaerpfrontend-1/src/components/ai/`, `src/lib/ai/`):
- `AiPanel.tsx` is a slide-over "ERP Copilot" with a module-scope `<select>` (inventory/catalog/pos, default inventory). It lazily creates one session (`POST /api/v1/tenant/ai/sessions` via `lib/ai/api.ts`) and streams chat over fetch-reader SSE (`lib/ai/stream.ts`).
- Generative UI: `AiComponentRenderer.tsx` renders exactly five allow-listed component types (`pos_top_items_table`, `pos_lagging_items_table`, `pos_sales_summary_card`, `inventory_reorder_candidates_table`, `follow_up_suggestions`); unknown types render nothing.
- Suggestion chips (`follow_up_suggestions` props) send their `message` text as a new user message via `handleSend`.

**Backend** (`alphasoft-backend/app-modules/ai/`):
- Routes under `api/v1/tenant/ai` behind `InitializeTenancyByDomain` + `auth:sanctum`: `POST sessions`, `GET sessions/{id}` (`showSession`, loads messages ordered by `sequence_number`), `DELETE sessions/{id}` (soft close), `POST sessions/{id}/chat` (JSON or SSE), `GET sessions/{id}/tool-calls`.
- `AiCopilotController::recordMessages()` persists both turn messages into `ai_messages` with ordered blocks (`content_json`), `trace_json`, `tools_json`, token counts, and auto-titles the session from the first user message.
- `AiSessionService::applyStatePatch()` merges runtime state patches into `ai_sessions.context_json` through a 13-key allow-list (see §3.B); non-whitelisted keys are dropped.
- `AiToolRegistry` (hardcoded const, 9 tools) filters tool definitions by module scope and permission (`enforce_permissions` defaults **true** in `config/ai.php`); `dispatch()` re-checks permission and always writes an `ai_tool_calls` audit row with `permission_snapshot`.
- `PythonRuntimeAdapter` POSTs to the runtime's `/api/chat` with `{tenant_id, user_id, session_id, module_scope, message, messages (last 20), conversation_state (context_json), tool_definitions, max_tokens, temperature}` and a shared-secret header.

**Python runtime** (`runtime/app/`):
- `routes/chat.py` → `agents/copilot.py::run_copilot()` — a single orchestrator loop (max 8 tool iterations) with **deterministic module routing**: `agents/modules/registry.py::router_for_scope()` resolves the `ModuleRouter` (pos/inventory/catalog) before any provider call; unknown scope fails fast. The LLM never chooses the module, only tools within the scope.
- Providers: Anthropic and Groq behind a provider-neutral `LLMProvider` protocol (`llm/factory.py`); selection is process-level env config, not per-request.
- Events (`agents/events.py` → `streaming/sse.py`): `token`, `tool` (started/completed), `component` (re-validated pydantic props, `extra="forbid"`), `trace`, `state_patch`, `error`, `done`.
- Deterministic per-router suggestion builders (`agents/modules/{pos,inventory,catalog}.py`) and `state_patch_for_tool()` (`agents/components.py`) — no LLM involvement in suggestions or state patches.
- Tool execution goes through exactly one path: `clients/laravel.py::LaravelToolClient.execute_tool()` → `POST {laravel}/api/internal/ai/tools/{tool}/execute`.

### 1.2 Frontend gaps

1. **No thread/sidebar UX, no session list/reload.** Messages live only in React state; the frontend never calls `showSession` even though `ai_messages` is fully replay-ready. Closing or clearing the panel loses the visible conversation (the data survives server-side but is unreachable from the UI).
2. **SSE event coverage is partial.** `types.ts::AiSseEvent` defines `session_start`, `text_delta`, `tool_start`, `tool_result`, `component`, `state_patch`, `trace`, `error`, `done` — but `AiPanel.handleSend` currently only handles `tool_start`, `tool_result`, `text_delta`, `component`, and `error`. It does not act on `session_start`, `state_patch`, `trace`, or `done` (stream end is detected via the reader, not the `done` event).
3. **Suggestions are message-only.** Chips carry `{id, label, message}` and are replayed as typed text; there is no structured action handling.
4. **Module scope switch destroys the conversation.** Changing the scope `<select>` calls `handleClear()` (aborts stream, closes session, resets state).
5. **No error recovery for interrupted streams** beyond a red banner; a partially streamed turn vanishes on panel close.

### 1.3 Backend gaps

1. **No session list endpoint.** Doc 13 planned `GET /api/v1/tenant/ai/sessions`; only show-by-id exists. `PATCH sessions/{id}` (rename) also does not exist.
2. **`state_patch` is not forwarded to the client.** `PythonRuntimeAdapter` captures it server-side for `applyStatePatch()` but only re-emits `token→text_delta`, `tool→tool_start/tool_result`, `component`, `trace`, `error` (plus its own `session_start`/`done`).
3. **Buffered relay, not true streaming.** `PythonRuntimeAdapter` reads the entire Python SSE body, then replays events; `LaravelHttpAdapter` (the config default) fake-streams text after the loop completes and emits no `component`/`state_patch`/`trace` at all. The doc-15 do-not-claim list ("no true streaming") stands.
4. **`ai_suggestions` is dormant.** Table and model exist; nothing reads or writes them. This is the designated approval path for structured actions (§10, §12) but is currently unused.
5. **Long-term user memory does not exist** (no table, no API).
6. **Knowledge-base / flow resource system does not exist** (no resources, no retrieval, no citation format). `contracts/resources/*.yaml` from docs 16/17 are planned-but-absent.

---

## 2. Target Chat Architecture

### 2.1 End-to-end flow

```
User
 └─▶ Frontend chat surface (AiPanel → thread UI)
      └─▶ Laravel tenant AI session/thread API  (auth, tenancy, session, history)
           └─▶ Python runtime orchestrator      (POST /api/chat, shared secret)
                └─▶ Module router (deterministic, scope-bound)
                     └─▶ LLM provider (Groq/Anthropic) — tool selection + narration only
                          └─▶ Laravel tools/endpoints/MCP  (POST /api/internal/ai/tools/{tool}/execute)
                               ◀─ validated tool output (minimal fields, no PII)
                     ◀─ narration, components, follow-ups, state patches (SSE events)
           ◀─ Laravel persistence + audit (ai_messages blocks, context_json merge, ai_tool_calls)
      ◀─ SSE relay to browser (text_delta, tool_*, component, state_patch*, done)
 ◀─ Ordered-block rendering + replay on reload (showSession)
```
(*`state_patch` forwarding to the client is a proposed change — see §11.)

### 2.2 Ownership by layer (exact)

| Concern | Frontend | Laravel | Python runtime |
|---|---|---|---|
| Auth, tenancy, permissions | sends Bearer token | **owns** (sanctum + tenancy middleware, `PermissionBundleResolver`) | trusts Laravel-filtered tool list; never re-derives permissions |
| Session/thread lifecycle | create/select/rename/close via API | **owns** (`ai_sessions`, `AiSessionService`) | stateless per request |
| Turn history | renders replay | **owns** (`ai_messages` ordered blocks) | receives last-20 window per request |
| Conversation state | may read (display filters) — never writes | **owns** (`context_json`, allow-list merge) | proposes patches (`state_patch` events) |
| Long-term user memory (future) | inspect/clear UI | **owns** (table, API, approval) | receives read-only snapshot per request |
| Module routing | scope picker | validates scope ∈ `enabled_modules` | **owns** deterministic `router_for_scope` |
| Model calls | never | never | **owns** (provider protocol) |
| Tool execution + audit | never | **owns** (`AiToolRegistry::dispatch`, `ai_tool_calls`) | requests execution via internal endpoint only |
| Components | **renders allow-listed only** | persists blocks verbatim | proposes + validates props (pydantic) |
| Follow-up suggestions | renders chips, sends message/action | relays; executes `action` via session chat endpoint | **owns** deterministic builders |
| Knowledge-base retrieval (future) | renders cited answers | may host authoring later | **owns** loading + matching + citation |
| Business writes | never | **owns** — only via approved `ai_suggestions` | never; may propose drafts |

Every layer refuses work that belongs to another layer. Python receiving a request with an unknown scope fails fast; the frontend receiving an unknown component type renders nothing; Laravel receiving a non-whitelisted state key drops it.

---

## 3. Memory Model

Three layers, mirroring the ADK separation (Session + State for the current conversation; MemoryService as a separate long-term store) and the OpenAI Agents pattern (load prior history before each run, persist new items after). Doc 13 designed layers A and B; both are now largely implemented — this section confirms, extends, and adds layer C.

### 3.A Short-term turn history

**What is sent to Python:** the last **20** user/assistant messages (`AiCopilotController::conversationMessages()` on the Laravel side; re-validated by `ChatRequest` and `build_conversation` with `HISTORY_LIMIT=20` on the Python side). Each entry is plain text extracted via `AiMessage::plainText()`, trimmed to 4,000 chars.

**Durable form:** `ai_messages` stores each turn as ordered blocks in `content_json`:

```json
[
  { "type": "text", "text": "Here are your top sellers…" },
  { "type": "component", "component_type": "pos_top_items_table", "schema_version": 1, "props": { … } }
]
```

plus `trace_json` and `tools_json` (tool traces), `sequence_number` (unique per session), `status` (`complete|failed|interrupted`), and token counts. This is already replay-ready; §9 makes the frontend consume it.

**Compaction strategy (proposed, Phase B/D):** when a session's history exceeds the 20-message window, Laravel maintains `context_json.conversation_summary` — a compact digest (≤ ~1,500 chars) of the rolled-off turns, following Carduka's `refresh_summary` pattern (digest of the last N turns, regenerated when the window slides). The summary is passed to Python inside `conversation_state` and injected into the system prompt as background. Rules: the summary never contains business figures the model could re-quote as fresh facts (it references what was *asked and shown*, not the numbers); regeneration is a deterministic truncating concatenation first, LLM-written summaries only if evals show the deterministic version loses too much.

**How follow-ups like "what about last month?" resolve:** three cooperating signals, in priority order:
1. **Session state** (`context_json`): `last_tool_name`, `last_tool_input`, `date_range`, `focused_entity_*`, `filters` — the runtime's system prompt instructs the model to reuse the last tool with the shifted parameter (`date_range` moved back one period) rather than asking again.
2. **Turn history**: the previous exchanges are in the message window, so the model can see the original question.
3. **Deterministic guardrail**: `state_patch_for_tool()` records the new `date_range` after the follow-up runs, so a second follow-up ("and the month before that?") chains correctly.
If neither state nor history disambiguates (e.g. fresh session, "what about last month?" as the first message), the model asks a clarifying question — never guesses a metric.

### 3.B Session conversation state

**Store:** `ai_sessions.context_json`, merged exclusively by `AiSessionService::applyStatePatch()`. The current allow-list (verified in code):

```
active_journey, last_intent, focused_entity_type, focused_entity_id,
displayed_catalog_item_ids, displayed_transaction_ids, displayed_component_ids,
last_tool_name, last_tool_input, last_tool_output_summary,
date_range, filters, conversation_summary          (+ forced version=1)
```

**Additive keys (proposed, from doc 16 §8):** `focused_entity_name`, `displayed_warehouse_ids`. Both are additive to the whitelist and the runtime's `state_patch_for_tool()`; no migration needed (`context_json` is JSON).

**Inventory-specific state** (doc 16): the focused item (`focused_entity_type: "catalog_item"`, `focused_entity_id`, proposed `focused_entity_name`), `filters.warehouse_id`, `displayed_warehouse_ids`, and `date_range` for movements queries. These are what let "show me its movements" and "only for the main warehouse" resolve without re-asking.

**Validation and whitelisting:** unchanged principle — Python *proposes* patches (whitelisted keys built deterministically from validated tool output, never from raw model text); Laravel *disposes* (drops unknown keys, merges over `defaultContext()`, forces `version`). Values derived from tool outputs are trusted only as IDs/aggregates; browser-supplied labels are never written into state. Any new key requires a change in **both** `agents/components.py::state_patch_for_tool` and `AiSessionService::applyStatePatch` plus a changelog note — drift between the two lists is a bug.

### 3.C Long-term user memory (design only — do not implement yet)

**Principle:** explicit user preferences only, following the ADK MemoryService separation — long-term memory is a *different store* with a *different write policy* than session state, never a dumping ground for conversation residue.

**Allowed content (exhaustive, extend only by doc revision):**
- preferred module scope (e.g. opens on inventory)
- default branch / warehouse filter
- default reporting period (e.g. "last 30 days")
- currency / number-display preferences
- preferred answer verbosity (short vs detailed)

**Prohibited content:** inferred traits, secrets, arbitrary PII, business facts, raw tool outputs, anything the user did not explicitly set or confirm. A "memory_update_proposed" event (§11) may *suggest* saving a preference ("Always use the Westlands branch? "), but nothing is written without an explicit user confirmation click.

**Later table concept** (`ai_user_memories`, tenant DB — not to be created yet):

```
id, user_id (FK), key (64, allow-listed enum), value_json, source (explicit|confirmed_suggestion),
created_at, updated_at
unique (user_id, key)
```

**Later API concept:** `GET /api/v1/tenant/ai/memories` (inspect), `PUT …/memories/{key}` (set), `DELETE …/memories/{key}` and `DELETE …/memories` (clear one/all). Inspectable and clearable is a hard requirement, not a nice-to-have. Python receives memories as a read-only `user_memory` map inside the chat request; it never writes them.

### 3.D Redis: not needed for the first slice

- **SQL remains the durable source** for all three layers. `context_json` merge happens once per turn inside the request that already holds the session row — no latency or concurrency pressure today (one panel, one stream per session, `busy` guard on the frontend).
- Carduka's Redis layer earns its keep because its graph nodes read/write state mid-turn across processes with optimistic `WATCH/MULTI` retries. AlphaSoft's runtime is stateless per request and patches flow through one Laravel merge point, so Redis would add an infrastructure dependency without removing any bottleneck.
- **Revisit trigger:** if/when (a) multiple concurrent streams per session are allowed, (b) mid-turn state reads by parallel agents appear (§5), or (c) `applyStatePatch` contention shows up in traces. If adopted, Redis holds only ephemeral locks/scratchpad with TTL (Carduka uses 6h) and SQL keeps the durable copy — the Carduka `context_json`-rehydration pattern is the one to copy.

---

## 4. Conversation Flow

For each flow: **F** = frontend behavior, **L** = Laravel behavior, **P** = Python behavior, **S** = state/memory updates, **U** = user-visible response. "(target)" marks proposed behavior; unmarked items describe what exists.

**4.1 New conversation.**
F: user opens panel / clicks "New conversation" (target: thread UI); frontend `POST sessions` with chosen module scope.
L: creates `ai_sessions` row (status active, `defaultContext()`), returns session resource.
P: not involved until first message.
S: fresh `context_json` v1.
U: empty chat with journey starters (target, §9.4) instead of a blank pane.

**4.2 Resume conversation (target — Phase B).**
F: on panel open, fetch session list, restore the last active session id (localStorage), `GET sessions/{id}` and replay ordered blocks from `content_json`.
L: existing `showSession` returns session + messages sorted by `sequence_number`; new `GET sessions` list endpoint needed (§9.2).
P: on the next message, receives the persisted `context_json` as `conversation_state` — resumption is invisible to the runtime.
S: none on resume; state was already durable.
U: the full prior conversation, components included, exactly as streamed.

**4.3 Switch module.**
F (current): scope change destroys the session. F (target): scope is a property of a conversation; switching scope starts a *new* thread while the old one remains in the list. No cross-scope mutation of an existing session.
L: `module_scope` is immutable on a session (already validated at start against `enabled_modules`).
P: next request resolves a different router deterministically.
S: each thread keeps its own `context_json`; nothing leaks between scopes.
U: previous conversation still reachable in the sidebar.

**4.4 Ambiguous question** (e.g. "how are we doing?").
F: normal send.
L: normal relay.
P: router prompt (module `BASE_RULES` + scope prompt) instructs the model to ask **one** clarifying question naming 2–3 concrete options within its scope, rather than guessing a metric or calling a speculative tool. No tool call is made for a question the model cannot ground.
S: `last_intent` may record the clarification topic; no tool state.
U: a short clarifying question, optionally with suggestion chips as answer shortcuts (target: `clarification` event, §11.4).

**4.5 Follow-up question** ("what about last month?", "show me its movements").
F: normal send.
L: passes `context_json` + last-20 history.
P: resolves via §3.A — reuses `last_tool_name`/`last_tool_input` with the shifted `date_range` or the `focused_entity_id`.
S: `state_patch` updates `date_range` / `last_tool_*` / displayed ids.
U: the answer, plus follow-ups that chain from the new state.

**4.6 Suggestion chip (message fallback).**
F: chip click calls `handleSend(suggestion.message)` — behaves exactly like typed text (current behavior, kept as the universal fallback).
L/P/S/U: identical to a typed message.

**4.7 Structured suggestion/action click (target — Phase B/C, §10).**
F: chip with an `action` payload sends `POST sessions/{id}/chat` with `{message: label, action: {...}}` — never a direct frontend→Python call.
L: validates the action (allow-listed `type`, tool exists, permission holds, referenced ids ⊆ `displayed_*` ids in `context_json`), then forwards it inside the runtime request as `ui_action`. Invalid action → 422 with a clear message, nothing forwarded.
P: router precedence honors `ui_action` first (Carduka pattern): the declared tool runs without an LLM routing round-trip; the LLM only narrates the validated output.
S: normal `state_patch` from the tool run.
U: deterministic, fast response; the chip label appears as the user message.

**4.8 No-data result.**
F: renders the `ai_empty_state` component (target, doc 16 §7) instead of an empty table.
L: tool returns `count: 0` honestly (no fabrication).
P: routers already prepend a "widen the range" suggestion when `count == 0` (`_WIDEN` chips in `pos.py`/`inventory.py`); narration states plainly that no rows matched and why that might be (per `BASE_RULES` empty-data honesty).
S: `last_tool_output_summary.count = 0` recorded.
U: "No sales found for that period." + widen/adjust chips. Never an invented number, never a silent empty panel.

**4.9 Unsafe / destructive request** ("delete this item", "change the price").
F: normal send.
L: no write tools exist in the registry, so there is nothing to execute even if prompted.
P: `BASE_RULES` refuse destructive actions; the model states it is read-only and that changes go through the normal ERP screens (or, later, a draft suggestion per §12). **Zero tool calls** on refusal (doc 16 §3.13 acceptance).
S: no state change.
U: a polite refusal naming the safe alternative. Later phases may create an `ai_suggestions` draft for approvable write flows — never a direct write.

**4.10 Backend tool unavailable** (registered but failing, or permission denied).
F: shows the tool badge in error state + the error text.
L: `AiToolRegistry::dispatch` records the failure in `ai_tool_calls.error_message`; permission denial throws `AiToolPermissionDeniedException`; the internal endpoint returns a structured error to Python.
P: emits `tool` completed-with-error, tells the model the tool failed so it can say so honestly, and does not retry more than once.
S: no fabricated state.
U: "I couldn't fetch inventory balances (permission/service error). " — errors are user-visible per house rule, never swallowed into an empty panel.

**4.11 Provider/model failure** (Groq/Anthropic error, timeout).
F: red error banner (existing), pending assistant message removed or marked failed.
L: relays the runtime `error` event; persists the turn with `status: failed` (target — today a throw mid-stream can lose the partial turn, see 4.12).
P: `ProviderError` carries a user-safe, secret-free message; SSE emits `error` then `done`.
S: `recordTurn` still counts the attempt; no state patch.
U: clear failure message + a retry affordance (target).

**4.12 Partial / interrupted stream** (network drop, user abort, panel close).
F: abort via `AbortController` (existing); target: on reload, the replayed thread shows the partial turn with an "interrupted" marker.
L (target): persist partial turns in a `finally` (Carduka pattern) with `ai_messages.status = interrupted` — the column already supports it. Today interruption can lose the assistant message entirely.
P: generator cancellation stops provider/tool work; the SSE layer always terminates with `done` when it can.
S: whatever `state_patch` was captured before interruption still applies (it describes completed tool calls, which did run).
U: the partial text survives reload instead of vanishing.

**4.13 Backend endpoint pending / not implemented** (e.g. `inventory_low_stock` before doc-18 answers land).
F: nothing special — the tool simply never appears.
L: unregistered tools are not in `getAvailableTools`, so Python never sees them. **We do not wire proposed tools speculatively** (doc 18 rule).
P: the model, lacking the tool, answers from what it *can* ground or states the capability isn't available yet — the do-not-claim list (§12.9) forbids pretending.
S: none.
U: "I can show current balances and recent movements; low-stock threshold alerts aren't available yet." Honest capability statements, never mock data.

---

## 5. Agent / Module Design

### 5.1 Recommended first design (the position of this doc)

**Keep exactly what exists, harden it, and resist framework adoption:**

1. **One runtime orchestrator** — `run_copilot()` remains the single agent loop. It already handles tool iteration, component validation, suggestion building, and state patches in ~one screenful of control flow.
2. **Module routers stay the deterministic boundary** — `router_for_scope()` (registry dispatch on `module_scope` from Laravel) is the routing mechanism. No LLM-based module classification: the user picks the scope, Laravel validates it, Python dispatches on it. This is cheaper, auditable, and eliminates a whole class of misrouting bugs.
3. **Specialized planner helpers only when needed** — if a flow genuinely requires multi-step planning (e.g. the doc-17 typed analytics query builder), add it as a *function* the orchestrator calls (a "planner helper" that returns a validated JSON contract), not as a peer agent with its own conversation.
4. **No LangGraph/ADK runtime dependency.** Doc 13 already decided this ("borrow patterns, keep small FastAPI") and nothing since has invalidated it. The adoption trigger is concrete: if the orchestrator loop needs conditional multi-node graphs with independent state channels (Carduka's actual complexity), reconsider; scope-dispatched single-loop agents do not need a graph engine.

### 5.2 Module agents/routers

| Router | Scope | Exists | Notes |
|---|---|---|---|
| `POS_ROUTER` | `pos` | yes (`modules/pos.py`) | restaurant/retail verticals via `vertical` filter, all 5 components |
| `INVENTORY_ROUTER` | `inventory` | yes (`modules/inventory.py`) | balances/movements/warehouses; grows with doc-16 tools |
| `CATALOG_ROUTER` | `catalog` | yes (`modules/catalog.py`) | data-aware suggestions from search results |
| `KNOWLEDGE_ROUTER` | `knowledge` (proposed) | no | §7 — answers "how do I…" from flow resources with citations; read-only, no ERP tools, or available cross-scope as a helper (see §7.6) |
| reporting | future | no | doc 15 "Next" horizon; likely a POS/inventory capability, not a new scope |

Each router is a frozen dataclass (`modules/base.py`): scope, system prompt, `allowed_component_types` frozenset, deterministic `build_suggestions`, `state_patch_for_tool`. **This is also the module-leak prevention mechanism** (§5.5).

### 5.3 Handoff vs tool-call

**Decision: tool-call style, not handoff.** In the OpenAI Agents taxonomy, a *handoff* transfers the conversation to another agent; a *tool-call* asks a specialist for a structured result and keeps control. AlphaSoft's constraints (auditable, deterministic, single scope per session) fit tool-calls:

- A module never "becomes" another module mid-conversation — the user switches scope explicitly (new thread, §4.3).
- If a POS question needs an inventory fact (e.g. "are my top sellers in stock?"), the *orchestrator* may call an inventory *tool* if Laravel's tool filter granted it — the permission system, not agent politics, decides. No second LLM conversation is spawned.
- The future knowledge helper (§7.6) is likewise invoked as a retrieval function returning `{answer_blocks, citations}` JSON, not a peer agent.

### 5.4 When agent-to-agent communication is actually needed — and its format

Legitimate future cases: (a) the typed-analytics planner producing an `analytics-query.v1` contract for validation; (b) a report-composer assembling multiple tool results; (c) knowledge retrieval feeding the main narration. In every case the exchange is a **strict JSON contract, never free-form agent chatter**:

```json
{
  "type": "agent_result",
  "agent": "analytics_planner",
  "schema": "alphasoft.analytics-query.v1",
  "ok": true,
  "payload": { "…validated contract…" },
  "trace": { "ms": 412, "model": "…", "prompt_version": "analytics-planner.v1" }
}
```

Rules: results are schema-validated before use (both sides); failures produce a structured `{ok: false, reason}` the orchestrator handles explicitly; every helper invocation appears in the `trace` stream so it is auditable end-to-end. Free-form message passing between agents is prohibited — it is un-auditable and un-evaluable.

### 5.5 Shared state contract and module-leak prevention

- **Shared state** = the `conversation_state` snapshot (Laravel-owned) passed read-only into the request, plus the whitelisted `state_patch` out. Helpers see only the slice they need.
- **Leak prevention (already implemented, keep):** components outside `router.allowed_component_types` are dropped before emission (`copilot.py`); suggestions come only from the scope's own builder; each router's prompt explicitly fences its domain (inventory: "do not volunteer POS analytics"). Adding a component type to a router is a deliberate, reviewed change.
- **New rule to adopt:** suggestion builders may only reference tools within their own scope; a cross-scope suggestion ("check stock for this item" from POS) requires the target tool to be in the request's `tool_definitions` (i.e., Laravel granted it) — otherwise the builder must omit the chip.

---

## 6. Backend API / MCP Consumption Plan

### 6.1 The contract chain (who defines what)

1. **Tool definition** lives in Laravel (`AiToolContract`: `name`, `moduleScope`, `permission{module,resource,action}`, `definition()` with JSON `input_schema`, `execute`). Canonical schema: `contracts/ai-tool.schema.json`.
2. **Filtering** — `AiToolRegistry::getAvailableTools($user, $moduleScope)` filters by scope and permission. **Python sees only the tools this user, in this tenant, in this scope, may run.** Python's `parse_tool_definitions` re-validates shape at its boundary and skips malformed entries (logged in trace).
3. **Input schema** — Anthropic-style JSON schema per tool, already in `definition()`. Rule: `additionalProperties: false` everywhere new (doc 17 discipline).
4. **Output schema** — currently implicit; **proposal:** add `output_schema` to `AiToolContract`/`contracts/ai-tool.schema.json` (already marked "planned" there) so component prop-mapping and evals validate against a declared shape. Outputs stay minimal-field, aggregate-only, no customer PII.
5. **Audit** — every execution writes `ai_tool_calls` (input, output, `permission_snapshot`, `duration_ms`, `error_message`) via `dispatch()`. Non-negotiable; new tools inherit it for free by going through the registry.
6. **Versioning** — tools are versioned by name suffix only when breaking (`inventory_movements` → keep name, additive params per doc 18 Q3; a true break would be `_v2`). Resource YAMLs carry `version:` headers (doc 17). Components carry `schema_version` in every block. Prompts version via `prompts/CHANGELOG.md`.

### 6.2 When the backend team adds inventory endpoints (doc 16/18 tools)

The backend team may implement endpoints/tools independently. The integration protocol:

1. Backend answers the 9 doc-18 questions (permission triples, zero-stock default, movement date semantics, low/dead-stock definitions, identifier rules, …).
2. Backend implements + registers the tool in `AiToolRegistry::TOOL_CLASSES` with its permission triple and unit tests. From that moment Python *automatically* receives it in `tool_definitions` — no runtime deploy needed for the tool to be callable.
3. AI repo then ships the *interpretation layer*: component mapping in `component_for_tool`, prop model, state-patch extraction, suggestion chips, router prompt line, eval fixtures. This is the only Python change per tool.
4. Frontend ships the component renderer (if a new component type).
5. Smoke test: golden eval + one real-tenant question per doc 16 §3 acceptance rows.

### 6.3 Before endpoints exist (allowed parallel work — doc 18)

- Draft `contracts/resources/inventory-analytics.v1.yaml` and flow resources (§7) — pure specs.
- Write eval fixtures under `evals/inventory/` with scripted tool outputs (test doubles are legal in evals).
- Write clarification/refusal tests that need **no** tools at all.
- **Forbidden:** wiring production calls to unregistered tools, mock data in product paths, "coming soon" components.

### 6.4 MCP

If the backend team exposes tools via MCP instead of (or alongside) the internal HTTP endpoint, the contract does not change: Laravel remains the MCP server / gateway, the tool list is still permission-filtered per user+scope before Python sees it, and `execute_tool` swaps transport (HTTP POST → MCP call) behind `LaravelToolClient`'s interface. Python never connects to an MCP server that fronts the tenant DB directly. Decision point deferred until the backend team commits to MCP; nothing in this plan blocks either transport.

---

## 7. Knowledge Base on ERP Flows

Users will ask *process* questions ("How do I set up POS?", "How do I create an item?", "Why can't I see a module?", "What does this field mean?"). Today the model would answer from pretraining — plausible, unverifiable, likely wrong about AlphaSoft specifics. The knowledge base makes flow answers **grounded, cited, and maintainable**.

### 7.1 Source formats

- **Flow resources:** YAML files (one flow per file) — structured, diffable, schema-validatable.
- **Longer explanations / concepts:** Markdown documents with front-matter ids, referenced *from* flow YAML (`docs:` links), for prose that doesn't fit steps.
- **Machine-readable index:** generated JSON manifest (id → module, title, keywords) built from the YAML at load time — no hand-maintained index.

Location: `contracts/flows/{module}/{flow-id}.yaml` in this repo (versioned next to the other contracts, PR-reviewed like code — "prompts are code" applies to flows too).

### 7.2 Flow taxonomy

Top-level `module` values: `pos`, `inventory`, `catalog`, `tenants`, `permissions`, `taxes`, `restaurant`, `retail`, `reporting`. Cross-cutting flows (e.g. "why can't I see a module?") live under `permissions` or `tenants` with `related_modules` listing the rest.

### 7.3 Flow resource schema

```yaml
# contracts/flows/inventory/check-stock.yaml
id: inventory.check-stock          # globally unique, dotted, stable — this is the citation id
version: 1
module: inventory
title: Check stock balance
audience: tenant_user              # tenant_user | tenant_admin | super_admin
summary: >
  Look up on-hand quantity for an item across warehouses.
prerequisites:
  - At least one warehouse configured (see inventory.setup-warehouse)
  - Item exists in the catalog (see catalog.create-item)
permissions:
  - inventory.inventory-balances.list
steps:
  - screen: Inventory > Balances
    route: /inventory/balances
    action: Search item by name or SKU
  - screen: Inventory > Balances
    action: Filter by warehouse if you manage more than one
related_ai_tools:
  - inventory_balance
related_flows:
  - inventory.stock-movements
common_questions:
  - How much stock do we have?
  - Why is this item unavailable?
common_errors:
  - symptom: Item not listed in balances
    cause: Items with zero on-hand quantity are currently hidden
    resolution: Check the item exists in Catalog; zero-stock visibility is a known limitation
docs:
  - id: docs.inventory-overview
    title: Inventory module overview
```

Required: `id, version, module, title, audience, summary, steps`. Optional: everything else. Validation: a JSON Schema for this shape lives at `contracts/flows/flow.schema.json`; CI-style check (pytest) asserts every YAML validates, every `related_flows`/`related_ai_tools` reference resolves, and ids are unique.

### 7.4 Answer style with citations

Flow answers always: (1) answer from the resource steps, adapted to the user's phrasing; (2) mention prerequisites and required permissions when relevant ("you'll need the inventory balances permission — if you don't see the screen, ask your admin"); (3) end with a **citation block** carrying the source ids (§11.6) so the frontend can render "Source: Check stock balance" chips; (4) never invent steps — if no resource matches, the model says the flow isn't documented yet and offers what it *can* do with tools.

The "Why can't I see a module?" class of question is answered by the `permissions` flows plus, later, a safe read-only `user_permissions_summary` tool (proposed, not committed) so the answer can be specific rather than generic.

### 7.5 Update process when the product changes

- Flow YAMLs change via PR in this repo with a `CHANGELOG` entry (same discipline as `prompts/`).
- Each resource carries `version`; the citation includes it, so stale answers are traceable to stale resources.
- When backend module journey docs change (backend `docs/`, per CLAUDE.md), the corresponding flow resource is updated in the same working cycle — the open question of *where the master product docs live* is §15.4; until answered, this repo's flow YAMLs are the AI-facing source of truth.

### 7.6 How the model consumes flows

First slice: the runtime loads all flow YAMLs at startup (they are small — tens of files), and a **deterministic retriever** (§8) selects candidates per question. Injection: matched flows (title + steps + prerequisites, trimmed) are added to the system prompt for that turn, tagged with their ids. Exposure options, in order of preference:
1. **Cross-scope helper:** any module router can receive flow context when the retriever matches ("how do I…" asked inside the inventory scope) — no scope switch needed.
2. **Dedicated `knowledge` scope** (§5.2) if usage shows people want a "help me use the ERP" surface distinct from analytics.
Start with (1); add (2) only on demand.

---

## 8. RAG / Retrieval Plan

**Phase 1 — curated, deterministic, no vectors:**
- Python loads flow YAMLs at startup into an in-memory index: id, title, `common_questions`, keywords (derived from title/summary/questions).
- Retrieval = normalized keyword/phrase scoring against the user message (+ `last_intent` from state as a tie-breaker). Top 1–3 matches above a threshold are injected (§7.6); zero matches → no injection, and the model must not answer process questions from memory (§8 rule below).
- This is cheap, fully testable (eval fixtures assert "question X retrieves flow Y"), and has no infrastructure cost.

**Phase 2 — embeddings, only if triggered:** adopt vector search when (a) the corpus exceeds what keyword scoring handles (rough trigger: >100 resources or measurable retrieval misses in evals), or (b) multilingual questions arrive. Design constraint for later: embeddings are computed over *flow resources only* (product knowledge), stored in infrastructure Python owns (no tenant DB), and re-computed on resource change.

**Hard rules (both phases):**
- **Always cite source ids.** An uncited process answer is an eval failure.
- **Never answer policy/process questions from model memory alone when a source exists** — and when no source exists, say so rather than confabulating a procedure.
- **Strict separation:** the knowledge base contains product flows only. Tenant data (balances, sales, names) never enters it; live facts always come from tools. A single answer may combine both ("here's how balances work [flow cite] — and here are yours [tool result]") but the provenance of each part stays distinct.
- **No customer PII in the knowledge base**, ever — it is tenant-agnostic by construction.

---

## 9. Frontend Chat UX Plan

### 9.1 AlphaSoft vs Carduka comparison

| Capability | Carduka (reference) | AlphaSoft today | Target |
|---|---|---|---|
| Thread sidebar/list | `ThreadSidebar` + cursor-paginated list API | none | Phase B |
| Create/select/delete/rename | full REST (`POST/GET/PATCH/DELETE /threads`) | create + soft-close only | add list + rename |
| Persisted ordered-block replay | `messageFromPersisted`, blocks rendered in order | data persisted, never fetched | Phase B |
| Session restore on reopen | localStorage active id + bootstrap fetch | none (React state only) | Phase B |
| Empty-state journey starters | journey chips | blank pane | Phase B |
| Structured action suggestions | `action` on every chip, `sendAction()` | message-only chips | Phase B/C (§10) |
| Trace/tool panel | trace persisted + renderable | `trace` ignored | dev/admin only |
| Interrupted-stream persistence | `finally` persists partial turns | partial turns can vanish | Phase B |
| Component registry | ~14 types | 5 types | +4 inventory types (Phase C) |

### 9.2 Concrete AlphaSoft improvements (recommended, in order)

1. **Backend: add `GET /api/v1/tenant/ai/sessions`** (list, `forUser`, newest `last_message_at` first, cursor pagination, fields: id, title, module_scope, status, last_message_at) and **`PATCH sessions/{id}`** (rename `title`). These are the only missing routes blocking thread UX — everything else already exists (`showSession` returns replay-ready messages).
2. **Session restore:** on panel open, list sessions → restore `localStorage` active id (fall back to most recent active) → `GET sessions/{id}` → map `content_json` blocks to the existing `AiMessage` state shape → render. Reuse `AiMessageResource` as-is.
3. **Thread sidebar:** collapsible list inside the slide-over (title, scope badge, relative time), new-conversation button, inline rename, close (existing DELETE). Mobile: sidebar becomes a top drawer/sheet; the panel already goes full-width (`w-full max-w-md`).
4. **Empty state:** on a fresh thread, render 3–4 journey-starter chips per scope (reuse the routers' `_DEFAULT` suggestion sets so starters and follow-ups stay consistent).
5. **Handle the ignored events:** `done` → finalize pending message (stop relying solely on reader end); `state_patch` (once forwarded, §11) → optionally surface active filters ("Westlands · last 30 days") as passive chips above the input; `trace` → collected into a collapsible dev/admin-only panel (visibility rule is open question §15.5); `session_start` → confirm/refresh session metadata.
6. **Structured suggestion actions** per §10 — extend `AiSuggestion` type with optional `action`, send it through the chat endpoint.
7. **Inventory components (Phase C, doc 16 §7):** `inventory_balance_table`, `inventory_movements_table`, `inventory_stock_position_card`, `ai_empty_state` — added to `AiComponentRenderer` + `types.ts`, matching the runtime prop models 1:1.
8. **Error & interruption display:** failed turns render with a subtle failure marker + retry button; interrupted replayed turns show "interrupted" (uses `ai_messages.status`).
9. **Provider/tool status, carefully:** keep the existing tool badges (they're good); do *not* surface provider names/models to end users — that belongs in the trace panel. A single unobtrusive "thinking…" state suffices; avoid a wall of status chrome.

### 9.3 What not to do

- No Next.js API proxy routes (house rule — frontend calls Laravel directly via `tenantFetch`).
- No direct frontend→Python calls, ever (actions route through Laravel, §10).
- No rendering of un-allow-listed component types "just in case" — unknown types keep rendering nothing.
- No optimistic UI for actions that imply writes.

---

## 10. Follow-Up Suggestions

### 10.1 Principles (confirming and extending current behavior)

- **Deterministic**: generated by router builders from (last tool, validated tool output, conversation state) — never by the LLM. This already works (`build_suggestions` per router); keep it.
- **Max 4** (enforced in `modules/base.py::capped` and the `FollowUpSuggestionsProps` model — keep both).
- **No destructive actions** — suggestions are read-only questions/queries by construction; the builder catalog simply contains no write verbs.
- **Reference only displayed/current entity ids** — builders may only use ids present in the tool output just rendered or in `context_json.displayed_*` / `focused_entity_id`. Never a guessed or historical id.
- **Structured action where possible, message fallback always** — every suggestion carries `message`; `action` is optional and additive, so old frontends degrade gracefully.

### 10.2 Schema

Extends the runtime `FollowUpSuggestion` model (`agents/components.py`, currently `{id, label, message}`) with an optional `action` — matching doc 13's design and Carduka's proven shape:

```json
{
  "id": "inventory-movements-focused-item",
  "label": "Recent movements",
  "message": "Show recent stock movements for this item",
  "action": {
    "type": "run_tool",
    "tool": "inventory_movements",
    "input": { "item_id": 123 }
  }
}
```

Action types (initial allow-list — extend only by doc revision):

| type | payload | semantics |
|---|---|---|
| `run_tool` | `tool`, `input` | run this registered tool with these validated inputs, narrate result |
| `ask` | — (uses `message`) | plain message send (explicit form of the fallback) |
| `start_journey` | `journey` | seed a scoped starter (empty-state chips) |

### 10.3 Execution path (no shortcuts)

Chip click → `POST /api/v1/tenant/ai/sessions/{id}/chat` with `{message: <label>, action: {…}}` → **Laravel validates**: action type allow-listed; `tool` exists in the registry, matches the session's scope, and the user holds its permission; every id in `input` ⊆ the session's `displayed_*`/`focused_entity_id` state → forwarded to Python as `ui_action` → router precedence runs it first (§4.7) → normal narration/component/state-patch flow → normal persistence/audit (the tool call is audited identically to a model-chosen call). Direct frontend→Python is structurally impossible (Python's `/api/chat` requires the shared secret only Laravel holds).

Invalid or stale actions (id no longer displayed, permission revoked) → Laravel 422 with a human message; the frontend falls back to sending `message` as plain text, so the user still gets an answer.

### 10.4 Persistence

Suggestions are already persisted for replay as `follow_up_suggestions` component blocks inside `content_json` — sufficient. On replay, chips referencing state that no longer matches (different `focused_entity_id`) still work safely because Laravel re-validates on click; no hydration machinery needed in the first slice (Carduka's re-hydration pattern becomes relevant only when interactive components carry mutable status).

---

## 11. Event / Data Formats

### 11.1 SSE events — current inventory and the naming split

Two vocabularies exist today; this is deliberate (runtime events are internal, client events are the frontend contract), but the mapping must be documented and complete:

| Runtime → Laravel (Python emits) | Laravel → browser (client receives) | Status |
|---|---|---|
| `token {text}` | `text_delta {delta}` | working |
| `tool {call_id,name,status,params/ms,detail}` | `tool_start {call_id,tool,input}` / `tool_result {call_id,tool,summary,count}` | working |
| `component {type,props}` | `component` (pass-through) | working |
| `trace {kind,label,detail}` | `trace` (pass-through) | relayed; frontend collects onto the message (not rendered) |
| `state_patch {…whitelisted keys…}` | `state_patch` — **accepted subset only**, emitted by the controller after `applyStatePatch`, before `done` | **shipped (Phase B, 2026-07-16)** |
| `error {message}` | `error {message}` | working; frontend also marks the turn failed |
| `done {}` (runtime-internal, not relayed) | `done` — emitted once by `AiCopilotController::streamChat` after persistence, on success and failure paths (adapters no longer emit it) | **shipped (Phase B)** — frontend finalizes on it |
| — | `session_start {session_id}` (adapter-emitted, first) | sent; frontend tolerates |

Shipped in Phase B (2026-07-16): (a) `state_patch` is forwarded after Laravel validates/merges it — the *merged accepted* patch, never rejected keys; (b) `done` ownership moved from the adapters to the controller so the accepted patch can precede it; (c) the frontend handles `done`, `state_patch`, and `trace`. Full renaming unification remains *not* worth the churn — this table is the contract.

### 11.2 Message / block shapes (persisted + replayed)

```json
{
  "id": 812, "role": "assistant", "status": "complete", "sequence_number": 14,
  "content_json": [
    { "type": "text", "text": "…" },
    { "type": "component", "component_type": "inventory_balance_table", "schema_version": 1, "props": { } }
  ],
  "trace_json": [ { "kind": "routing", "label": "module", "detail": "inventory" } ],
  "tools_json": [ { "call_id": "…", "tool": "inventory_balance", "ms": 84, "count": 12 } ],
  "input_tokens": 913, "output_tokens": 288
}
```

### 11.3 Component event

```json
{ "type": "inventory_balance_table", "schema_version": 1,
  "props": { "items": [ { "item_id": 123, "name": "…", "on_hand_qty": 40, "warehouse": "Main" } ], "count": 12 } }
```
Props validate against `extra="forbid"` pydantic models in the runtime **and** against the frontend's TS types; invalid props are dropped at emission (existing `validated_component` behavior).

### 11.4 Future optional events (design now, implement when needed)

- `clarification { question, options: [{id,label,message}] }` — a typed clarifying question whose options render as chips (§4.4). Until implemented, clarifications remain plain text.
- `action_required { suggestion_id, summary, ai_suggestion_id }` — signals a draft was created in `ai_suggestions` and awaits human approval (write flows, §12).
- `memory_update_proposed { key, value, prompt }` — proposes saving an explicit preference (§3.C); frontend renders confirm/dismiss; confirmation calls the memories API, never silent writes.

### 11.5 Tool call, state patch, agent result

Tool call audit shape: `contracts/ai-run.schema.json` (`ai_tool_calls` row) — unchanged. State patch: whitelisted-keys object (§3.B), same shape on the wire and in `context_json`. Agent handoff/result: §5.4 `agent_result` envelope — appears only in `trace`, never as a user-visible event.

### 11.6 Flow knowledge citation

```json
{ "type": "citations", "sources": [ { "id": "inventory.check-stock", "version": 1, "title": "Check stock balance" } ] }
```
Emitted as a block (or component) at the end of a flow answer; the frontend renders unobtrusive source chips. An answer built on flow resources without this block fails evals (§8).

---

## 12. Safety, Privacy, and Governance

1. **Tenancy boundaries.** All AI routes stay behind `InitializeTenancyByDomain` + `auth:sanctum`. Sessions are user-scoped (`forUser`); no cross-tenant anything (doc 15 Surface B stays design-only). Python receives `tenant_id` for audit/echo, not as a capability.
2. **Permission enforcement.** `enforce_permissions` stays **true**. Tools are filtered before Python sees them and re-checked at dispatch. Structured actions re-validate on click (§10.3). New tools ship with their permission triple from `config/permissions.php` — never invented inline.
3. **No Python DB access.** The runtime's only outbound paths remain the LLM provider and `LaravelToolClient`. Adding any DB driver to `runtime/` is a review-blocking event.
4. **No raw SQL from model output.** The NL2SQL path is the doc-17 typed contract only: validated JSON against allow-listed resources, executed by Laravel, validated twice.
5. **No direct writes.** Read-only tools today; future write intents produce `ai_suggestions` drafts (pending → approved → applied, human reviewer recorded) surfaced via `action_required`. No exceptions, no "safe" writes.
6. **PII rules.** Tool outputs: aggregates, item names, totals — never customer personal data. Knowledge base: tenant-agnostic, zero PII. Conversation state: ids and compact facts only. Traces: no payload echo of anything sensitive.
7. **User-memory rules.** Explicit, confirmed, allow-listed keys only; inspectable and clearable; proposed-not-silent writes (§3.C). Whether tenant admins must approve the feature at all is open question §15.6.
8. **Audit.** Every tool call → `ai_tool_calls` with `permission_snapshot`. Every turn → `ai_messages` with trace/tools. Every helper-agent invocation → `trace`. Every applied state patch is reconstructable from persisted patches. Suggestions-as-drafts carry reviewer identity and timestamps.
9. **Do-not-claim list** (extends doc 15; the model and marketing both bound by it): no true token streaming (pipeline is buffered); no advertising analytics; no autonomous writes; no profit margins until purchase-price coverage is verified; no cross-tenant insights; no capabilities from unregistered tools; **no undocumented process answers** (flow questions without a matching resource get an honest "not documented yet").
10. **Prompt/resource versioning.** System prompts via `prompts/` + CHANGELOG; flow resources via `contracts/flows/` + version headers; analytics resources via `contracts/resources/`; sync rule with `AiSystemPromptBuilder` unchanged.
11. **Eval requirements.** Every new tool: golden fixtures asserting `tools_called`, `grounded_numbers`, `no_write_language`. Every refusal path: a golden asserting zero tool calls. Every flow resource: a retrieval golden (question → resource id) and a citation assertion. Interrupted/error paths: at least one fixture each once Phase B lands.

---

## 13. Implementation Roadmap

### Phase A — planning/resource/eval layer (no endpoint dependency; can start immediately)
- `contracts/flows/flow.schema.json` + first ~8–10 flow resources (inventory + POS + permissions taxonomy seeds), validated by a pytest check.
- `contracts/resources/inventory-analytics.v1.yaml` committed from doc 16 §4.
- `evals/inventory/` golden fixtures (the 10 named in doc 16 §9) with scripted tool outputs; clarification/refusal goldens that need no tools.
- Structured suggestion schema (§10.2) written into `contracts/` as JSON schema (spec only).
- This doc's frontend UX plan (§9) socialized with whoever owns the frontend sprint.

### Phase B — conversation/thread UX hardening
- Backend: `GET sessions` (list) + `PATCH sessions/{id}` (rename); partial-turn persistence in a `finally` with `status: interrupted`; forward validated `state_patch` to the client; feature tests for all.
- Frontend: session list + sidebar, localStorage restore, ordered-block replay via `showSession`, empty-state journey starters, `done`/`session_start` handling, failed/interrupted turn display.
- Runtime: add optional `action` to `FollowUpSuggestion` + builder support; Laravel action validation on the chat endpoint (`ui_action` forwarding).

### Phase C — inventory API integration (blocked on doc-18 answers + backend registration)
- Wire new inventory tools (low stock, dead stock, stock cover, movements v2) through the §6.2 protocol: component mappings, prop models, state-patch extraction, router prompt lines, suggestion chips.
- Frontend inventory components: `inventory_balance_table`, `inventory_movements_table`, `inventory_stock_position_card`, `ai_empty_state`.
- Whitelist additions: `focused_entity_name`, `displayed_warehouse_ids` (both sides, same PR).
- Smoke tests: goldens go from scripted to live-shaped fixtures; one real-tenant validation pass per doc 16 acceptance rows.

### Phase D — long-term user memory
- `ai_user_memories` table + memories API (§3.C), allow-listed keys only.
- `memory_update_proposed` event + confirm UI; inspect/clear UI in settings.
- Runtime consumes `user_memory` read-only (default filters/period seeded into state at session start).

### Phase E — optional advanced orchestration (trigger-gated, not scheduled)
- Agent-to-agent helpers (analytics planner per doc 17) only when the typed-query slice starts — as functions returning validated contracts (§5.3/§5.4).
- RAG embeddings only past the §8 trigger (>100 resources or measured retrieval misses).
- Redis scratchpad only past the §3.D trigger. LangGraph/ADK only past the §5.1 trigger.

Dependencies: A has none. B is self-contained (backend+frontend+runtime, no new tools). C blocks on doc 18. D is independent of C. E is contingent, not planned.

---

## 14. Concrete Next Step Recommendation

**Do not wait for backend endpoints.** The immediate next implementation after this doc is **Phase A**, specifically in this order:

1. **Flow knowledge resource schema + first resources** (`contracts/flows/…`) — pure spec work, unblocks §7/§8 evals, zero dependencies.
2. **Inventory eval fixtures** (`evals/inventory/`, doc 16 §9) with scripted tool outputs — legal test doubles that lock in expected behavior before the tools exist.
3. **Structured suggestion action schema** committed to `contracts/` — so runtime, Laravel, and frontend implement against one reviewed shape in Phase B.
4. **Frontend session restore/list/replay** may start as soon as the two small backend routes (session list, rename) are scheduled — `showSession` and the replay-ready `ai_messages` data already exist, so this is low-risk high-visibility work.
5. **Do not wire nonexistent tools** (`inventory_low_stock`, `inventory_dead_stock`, `inventory_stock_cover`, movements v2) — they wait for doc-18 answers and registry registration, per the §6.2 protocol.

---

## 15. Open Questions (blockers only)

1. **Doc-18 backend answers.** The 9 inventory contract decisions (permission triples, zero-stock default, movement date semantics, low/dead-stock definitions, identifier rules, serial/lot feasibility, reorder-point roadmap) gate all of Phase C.
2. **Thread endpoints readiness.** Are `GET sessions` (list) and `PATCH sessions/{id}` (rename) small enough to land in the current backend cycle, so frontend Phase B isn't blocked? (Everything else Phase B needs already exists.)
3. **SQL-only vs Redis for later ephemeral runtime state.** Position here is SQL-only until the §3.D triggers fire — needs explicit sign-off so infra isn't provisioned speculatively.
4. **Where official product flow docs are maintained.** Backend `docs/` journey docs, this repo's `contracts/flows/`, or a product wiki? This plan treats `contracts/flows/` as the AI-facing source of truth until decided; a second master source would need a sync process.
5. **Trace/tool panel visibility.** Which users see the dev/trace panel — super-admin only, tenant admin, or a permission? Affects §9.2.5.
6. **Long-term memory approval.** Does `ai_user_memories` require tenant-admin opt-in per tenant, or is per-user explicit consent sufficient? Affects Phase D design.
