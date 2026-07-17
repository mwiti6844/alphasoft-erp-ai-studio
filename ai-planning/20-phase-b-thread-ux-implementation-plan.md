# 20 — Phase B: Thread/Session UX Hardening — Implementation Plan

**Date:** 2026-07-16
**Status:** Implementation plan — approved scope is doc 19 Phase B. No code accompanies this document; tests are specified here but implemented by a separate agent.
**Companions:** doc 19 (`19-ai-chat-memory-agent-flow-plan.md`, master design — Phase B definition in §13), doc 13 (original memory/state/UI plan), `contracts/ai-followup-suggestion.schema.json` (structured chip schema, Phase A).

**Scope:** Laravel backend + Next.js frontend thread UX; minimal runtime changes only where needed. Hard boundaries unchanged: frontend never calls Python; Python never touches tenant DBs; Laravel owns auth/sessions/state/tools/audit; no mock data in product behavior; no commits/pushes; preserve existing uncommitted work.

Every claim below was verified against the working trees on 2026-07-16.

---

## 1. Current Gap Summary (exact file references)

### Backend (`alphasoft-backend/app-modules/ai/`)

| # | Gap | Evidence |
|---|---|---|
| B1 | No session list route — only `POST sessions`, `GET/DELETE sessions/{id}`, `POST …/chat`, `GET …/tool-calls` exist | `routes/ai-routes.php:18–36` |
| B2 | No rename route (`PATCH sessions/{id}`) | `routes/ai-routes.php` (absent) |
| B3 | Nothing is persisted on stream failure — `recordMessages()` runs only after `executeChatStream()` returns; on Throwable the catch emits `error` and exits, losing the **user message too** | `AiCopilotController::streamChat()` :170–198, `recordMessages()` :229–268 |
| B4 | `done` is never emitted on the error path (only `error`) | `AiCopilotController::streamChat()` :197 |
| B5 | Accepted `state_patch` never reaches the browser — `PythonRuntimeAdapter::executeChatStream()` relays only `token/tool/component/trace/error` (match at :43–50); `state_patch` is captured into `AiRuntimeResult` (:226–228) and merged server-side only | `PythonRuntimeAdapter.php:43–50, 226–228`; `AiSessionService::applyStatePatch()` :53–87 |
| B6 | Both adapters own `session_start` + `done` emission themselves, so the controller cannot emit anything between the last runtime event and `done` | `PythonRuntimeAdapter.php:32–35, 55–60`; `LaravelHttpAdapter.php:44, 61` |
| B7 | `ai_messages.status` accepts any string (default `'complete'`) but only `'complete'` is ever written; failed/interrupted values are unused | migration `2026_07_07_120000_create_ai_messages_table.php`; `recordMessages()` writes `'complete'` for both rows |
| B8 | No index supports "order by recent activity" (`last_message_at` added without index) | migrations `2026_06_03_100000` (indexes `[user_id,status]`, `[module_scope,created_at]`), `2026_07_07_121000` (adds `last_message_at`, `title` — no index) |
| B9 | `conversationMessages()` includes every message regardless of `status` — harmless today (only `complete` exists) but wrong once `failed/interrupted` rows exist | `AiCopilotController::conversationMessages()` :210–227 |

### Frontend (`alpaerpfrontend-1/src/`)

| # | Gap | Evidence |
|---|---|---|
| F1 | No thread list/sidebar; no restore — messages live only in React state; `GET sessions/{id}` is never called anywhere | `components/ai/AiPanel.tsx` (whole file); `lib/ai/api.ts` has only `startAiSession` + `closeAiSession` |
| F2 | Module scope switch destroys the conversation — `<select onChange>` calls `handleClear()` which aborts, `DELETE`s the session, and wipes messages | `AiPanel.tsx:243–255, 67–81` |
| F3 | SSE events partially handled: `handleSend` acts on `tool_start`, `tool_result`, `text_delta`, `component`, `error`; the `AiSseEvent` union also defines `session_start`, `state_patch`, `trace`, `done` but the panel does not act on them (stream end = reader `done`, not the `done` event) | `AiPanel.tsx:120–188`; `lib/ai/types.ts:141–173` |
| F4 | Frontend `AiSession` type lacks `title`, `last_message_at`, `context`, `created_at` — the resource returns them (`AiSessionResource.php:20–33`) but the type drops them | `lib/ai/types.ts:3–17` |
| F5 | On send failure the pending assistant message is deleted entirely — no failed-turn display, no retry | `AiPanel.tsx:203–212` |
| F6 | Empty state is a static sentence, not per-module journey starters | `AiMessageList.tsx:14–21` |
| F7 | Suggestion chips are message-only (`follow_up_suggestions` props typed `{id,label,message}`) | `lib/ai/types.ts:106–112`; renderer passes `suggestion.message` to `onSuggestion` |

### Runtime (`alphasoft-erp-ai-studio/runtime/`)
No gaps block Phase B. `state_patch` is already emitted (`streaming/sse.py`); suggestions already flow as a component. The only candidate change is the optional `action` field on `FollowUpSuggestion` — deferred, see §6.

---

## 2. Backend Route/API Contract

### 2.1 `GET /api/v1/tenant/ai/sessions` (new)

- **Route:** in the existing `api/v1/tenant/ai` group (same middleware stack: `InitializeTenancyByDomain`, `PreventAccessFromCentralDomains`, `auth:sanctum`, `SubstituteBindings`), name `ai.sessions.index`. Declare **before** `sessions/{session}` or rely on `whereNumber('session')` (already present) — both safe; keep declaration order list-first for readability.
- **Handler:** `AiCopilotController::listSessions(Request $request)`.
- **Request (query params):**
  - `status` — optional, `in:active,closed`; omitted = all.
  - `module_scope` — optional, `Rule::in(config('ai.enabled_modules'))`.
  - `cursor` — optional, opaque Laravel cursor string.
  - `per_page` — optional int, default 20, max 50.
- **Query:** `AiSession::query()->forUser($user)` (existing scope, `AiSession.php:68`) `->orderByDesc('last_message_at')->orderByDesc('id')` `->cursorPaginate($perPage)`. Cursor pagination (not offset) — matches the Carduka thread list pattern and stays stable while new turns bump `last_message_at`.
- **Response:** the standard tenant envelope with `data: AiSessionResource[]` and cursor meta (`next_cursor`, `per_page`). Reuse `AiSessionResource` (messages relationship not loaded ⇒ omitted via `whenLoaded`). `context` rides along; it is small (bounded whitelist, `AiSessionService::defaultContext()`), so a slim list resource is not worth the second type — decision recorded here, revisit only if payloads grow.
- **Authorization:** implicit via `forUser` — a user sees only their own sessions; tenancy via middleware. No extra policy needed (matches `resolveOwnedSession` semantics).
- **Failure cases:** 401 unauthenticated (middleware); 422 invalid `status`/`module_scope`/`per_page`; invalid cursor → Laravel treats as first page (document, don't fight it).

### 2.2 `PATCH /api/v1/tenant/ai/sessions/{session}` (new)

- **Route:** same group, `->whereNumber('session')`, name `ai.sessions.update`.
- **Handler:** `AiCopilotController::updateSession(Request $request, int $session)`.
- **Request body:** `{ "title": string }` — `['required','string','min:1','max:120']` (120 = column width, migration `2026_07_07_121000`). Title only; `status`/`module_scope` are **not** patchable (scope is immutable per doc 19 §4.3; close stays on DELETE).
- **Behavior:** `resolveOwnedSession()` (existing, 404 on other users' sessions), set `title`, save. Renaming also pins the title: `recordMessages()`'s auto-title only fires when title is `'New conversation'` or null (`AiCopilotController:264–266`), so a user-chosen title is never overwritten — no new flag needed.
- **Response:** `AiSessionResource`, message "AI session updated."
- **Failure cases:** 401; 404 not-owned/unknown id; 422 title missing/empty/too long. Renaming a closed session is allowed (harmless, keeps the list tidy).

### 2.3 Partial/interrupted turn persistence (restructure `streamChat` + `recordMessages`)

Current sequence loses everything on failure (gap B3). Target sequence inside the stream closure:

1. **Persist the user message first** — before calling the adapter, create the `ai_messages` user row (`status: complete`, next `sequence_number`) and bump `last_message_at` + auto-title. Extract from `recordMessages()` into `recordUserMessage()`; the remaining assistant-row logic becomes `recordAssistantMessage(…, string $status)`.
2. Call `executeChatStream(...)` in `try`.
3. **Success path:** `recordTurn`, `applyStatePatch`, `recordAssistantMessage(status: 'complete')`, emit accepted `state_patch`, emit `done` (see §4).
4. **Failure path (`catch \Throwable`):** emit `error` (user-safe message, as today), then `done`; persist an assistant row with `status: 'failed'`, `content: null`, `content_json: []`, `trace_json: [{kind:'error', label:'runtime_failure', detail: <exception class + safe message>}]`, zero tokens. **No fabricated content** — an empty failed row is the honest record; the UI renders it as a failed turn (§5).
5. **Client abort:** call `ignore_user_abort(true)` at the top of the stream closure so PHP completes persistence after the browser disconnects. With `PythonRuntimeAdapter` this is cheap: the runtime response is fully buffered before relay, so the result is usually already in hand when the client vanishes — persist it with `status: 'complete'` (the turn really happened; replay shows it). If the abort interrupts before the adapter returns, the catch path (4) applies with `status: 'interrupted'` when the exception is a write-to-closed-socket error, `'failed'` otherwise. Feasibility note recorded honestly: PHP-FPM abort semantics vary by SAPI/proxy; the tests (§8) must pin what we can control (persist-before-call for user rows, catch-path assistant rows) and the abort case is best-effort.
6. **History hygiene (B9):** `conversationMessages()` adds `->where('status', 'complete')` so failed/interrupted rows never re-enter the prompt window. (Empty-content rows would be dropped by `normalizeMessages()` anyway — `PythonRuntimeAdapter:117–136` — but the filter makes intent explicit.)

The non-streaming JSON `chat()` path gets the same user-row-first + failed-assistant-row treatment for consistency (it already returns 422/502 on failure; now it also leaves an honest transcript).

### 2.4 Forward accepted `state_patch` + `done` ownership (B5/B6)

Today both adapters emit `done` themselves, so the controller cannot emit the accepted patch before the stream terminator. Change of ownership, backward compatible (the frontend currently ignores `done` entirely, F3):

- **Adapters stop emitting `done`.** Remove the `done` emission from `PythonRuntimeAdapter::executeChatStream()` (:55–60) and `LaravelHttpAdapter` (:61). `session_start` stays adapter-emitted (it carries the model id the adapter knows).
- **Controller emits the tail** in `streamChat` after persistence:
  1. `state_patch` — **the accepted subset only**: `applyStatePatch()` gains a return of (or a sibling method computes) the intersection it actually merged, i.e. `array_intersect_key($statePatch, array_flip($allowed))`. The browser never sees rejected keys. Emit only when non-empty.
  2. `done` — same payload shape as today (`session_id`, `input_tokens`, `output_tokens`, `tool_calls`), now emitted once by the controller on both success and failure paths.
- **Wire contract after this change** (event order): `session_start` → (`tool_start`/`tool_result`/`text_delta`/`component`/`trace`)* → [`error`] → [`state_patch`] → `done`. All existing event names and payloads unchanged — additive only; a frontend that ignores `state_patch`/`done` behaves exactly as before. This supersedes nothing in `contracts/` — doc 19 §11.1's table gets a follow-up edit marking `state_patch` forwarding as shipped when this lands.

### 2.5 Supporting migration (additive only)

New tenant migration: `$table->index(['user_id', 'last_message_at'])` on `ai_sessions` (gap B8). Additive, live-tenant safe. No other schema changes — `ai_messages.status` already accommodates `failed`/`interrupted` (string 32).

---

## 3. Frontend Component/State Design

### 3.1 API client additions (`src/lib/ai/api.ts`)

```ts
listAiSessions(params?: { status?: "active"|"closed"; module_scope?: AiModuleScope; cursor?: string }): Promise<{ sessions: AiSession[]; nextCursor: string | null }>
showAiSession(sessionId: number): Promise<AiSession>          // GET sessions/{id} — exists server-side, unused until now
renameAiSession(sessionId: number, title: string): Promise<AiSession>  // PATCH
// startAiSession / closeAiSession unchanged
```
All via `tenantFetch` (house rule: no Next.js proxy routes). `AiSession` type (`lib/ai/types.ts`) extended with `title: string | null`, `last_message_at: string | null`, `created_at: string | null`, `context: Record<string, unknown>` — matching `AiSessionResource` exactly (fixes F4). Add `AiPersistedMessage` mirroring `AiMessageResource` (`role`, `status`, `sequence_number`, `content`, `blocks`, `trace`, `tools`, token counts, `created_at`) and extend `AiSession` with optional `relationships.messages`.

### 3.2 Thread list / sidebar (new `components/ai/AiThreadList.tsx`)

- Rendered inside `AiPanel` as a collapsible section (toggle button in the header next to the scope picker; slides over the message area on mobile — the panel is already `w-full max-w-md`, a second fixed column doesn't fit).
- Rows: title (fallback "New conversation"), scope badge, relative `last_message_at`. Active row highlighted.
- Actions: **New conversation** (creates a session in the current scope, selects it), **select** (loads + replays), **rename** (inline input → PATCH, on blur/submit — Carduka `ThreadSidebar` pattern), **close** (existing DELETE with a `confirm()`; closed sessions stay listed under a "closed" filter toggle, since DELETE is a soft close and `showSession` still replays them read-only).
- Data: `listAiSessions()` on panel open and after any create/rename/close/first-turn (first turn changes the auto-title — refresh after a send completes, mirroring Carduka's post-send thread refresh).
- Pagination: "load more" button driven by `nextCursor`; no infinite scroll in the first cut.

### 3.3 Active session state + localStorage

`AiPanel` state changes:
- `sessionId` remains the single source of the active thread; `messages` become derived-from-server + streamed-deltas (replay on select, append during stream).
- **localStorage key:** `alphasoft.ai.active_session.<tenantDomain>.<userId>` (tenant + user scoped so shared machines/accounts never restore someone else's thread id — the server would 404 via `forUser` anyway, but don't even try). Written on select/create, cleared on close-of-active.
- **Restore on open** (replaces the current `ensureSession` auto-create, `AiPanel.tsx:43–53`): on `open`, `listAiSessions({status:"active"})` → pick the localStorage id if present in the list → else newest active session → else **no auto-create**: show the empty state with journey starters and create lazily on first send or explicit "New conversation" (stops the current behavior of minting an orphan session per panel-open).
- **Replay:** `showAiSession(id)` → map `relationships.messages` to `AiChatMessage[]`:
  - `blocks` → the existing `AiMessageBlock[]` (assign client ids; `component` blocks keep `component_type`/`props` — unknown types already render nothing in `AiComponentRenderer`, defense unchanged);
  - `content` → `content`; `tools` → `toolCalls` badges (entries with `status:"completed"` → `done`); `status: "failed"|"interrupted"` → failure marker on the message (§3.5); `pending: false`.
  - Module scope select syncs to the loaded session's `module_scope`.

### 3.4 Module scope behavior (fixes F2)

The scope `<select>` stops calling `handleClear()`. New behavior: switching scope = **switching threads**, never destroying one:
1. Look for the most recent **active** session with that scope (from the already-fetched list) → select + replay it.
2. None exists → empty state with that scope's journey starters; session created lazily on first send.
3. The previous session is left untouched (still active, still listed). `handleClear` is retired; its two remaining uses become explicit actions: "close" in the thread list (DELETE) and "New conversation" (create).

### 3.5 Error / interrupted display (fixes F5)

- On stream failure, keep the assistant message (don't filter it out as today, `AiPanel.tsx:212`) and mark it `failed: true` — rendered with a subtle error border + the error text, plus a **Retry** button that re-sends the same user text (a plain `handleSend(text)`; the failed row stays in local state but is excluded from what the server replays as history — the backend already excludes non-complete rows from the prompt window, §2.3.6).
- Replayed messages with `status: "failed"` / `"interrupted"` render the same marker ("This response failed/was interrupted").
- No optimistic anything: Retry sends a new turn; it never pretends the failed one succeeded.

### 3.6 Empty-state journey starters (fixes F6)

Per-scope starter chips shown when the active thread has no messages. Text **copied verbatim from the runtime routers' default suggestion sets** (`runtime/app/agents/modules/{pos,inventory,catalog}.py` `_DEFAULT` maps) so starters and follow-ups speak one language — maintained as a small `JOURNEY_STARTERS: Record<AiModuleScope, {id,label,message}[]>` constant in `lib/ai/` with a comment pointing at the runtime source. Clicking one sends the message (creating the session lazily). No data is fetched or invented for the empty state.

---

## 4. SSE Handling Changes

### 4.1 Current vs target (frontend, `AiPanel.handleSend`)

| Event | Current | Target |
|---|---|---|
| `session_start` | defined in types, ignored | sanity-check `data.session_id === active`; ignore otherwise (log in dev) |
| `text_delta` | appended to content + blocks | unchanged |
| `tool_start` / `tool_result` | badge map | unchanged |
| `component` | appended | unchanged |
| `trace` | ignored | collected onto the streaming message (`traces: []`) — **not rendered** in Phase B (dev/admin trace panel is deferred; open question doc 19 §15.5). Zero UI cost, enables the panel later |
| `error` | sets the banner | sets the banner **and** marks the assistant message `failed` (§3.5) |
| `state_patch` | ignored | store on panel state as `sessionContext` (merged locally over the replayed `session.attributes.context`); Phase B renders nothing from it yet — it exists so the thread list/starters can later show active filters. Cheap, additive |
| `done` | ignored (reader-end detection) | finalize: `pending: false`, badges flushed, thread list refresh (auto-title may have changed). Reader-end stays as fallback finalizer for old-backend compatibility |

### 4.2 `state_patch` forwarding contract (backend, restated from §2.4)

- Python emits the raw proposal (unchanged, `runtime/app/streaming/sse.py`).
- Laravel validates/merges via `AiSessionService::applyStatePatch()` and emits **only the accepted subset** after persistence, before `done`.
- Browser therefore only ever sees keys from the server allow-list — rejected keys are invisible end-to-end.
- Event order becomes: `session_start` → stream events → [`error`] → [`state_patch`] → `done`.

### 4.3 Backward compatibility

All changes are additive or ownership moves invisible on the wire (`done` still arrives exactly once, last). A frontend deployed before the backend change ignores `state_patch`/`done` as it does today; a backend deployed before the frontend change streams events the panel already tolerates. No event is renamed, no payload field removed.

---

## 5. Persistence / Error Behavior Matrix

| Scenario | User row | Assistant row | SSE tail | UI |
|---|---|---|---|---|
| Normal turn | `complete` (persisted **before** adapter call) | `complete`, full blocks/trace/tools/tokens | `state_patch` (if accepted keys) → `done` | finalized message |
| Provider error (Groq/Anthropic failure inside runtime) | `complete` | `failed`, empty content, error in `trace_json` | `error` → `done` | failed marker + banner + Retry |
| Runtime unreachable / non-2xx (`callRuntime` throws) | `complete` | `failed` (same shape) | `error` → `done` | same |
| User abort (panel close / new send aborts fetch) | `complete` | best-effort: `complete` if the adapter already returned (buffered runtime response), else `interrupted` — `ignore_user_abort(true)` gives persistence a chance to finish | client stopped reading; tail may not be received | on replay: turn present (complete) or interrupted marker |
| Network interruption mid-relay | `complete` | same best-effort as abort | truncated stream; no `done` received | reader-end fallback finalizes locally; replay reconciles on next open |
| Non-stream JSON `chat()` failure | `complete` | `failed` | n/a (JSON 422/502 as today) | error banner |

Invariants: the user's message is never lost once accepted; assistant content is never fabricated; `status` values used are exactly `complete` / `failed` / `interrupted` (column already accommodates them); non-`complete` rows are excluded from the prompt history (§2.3.6).

---

## 6. Structured Suggestion Action Decision

**Decision: defer execution to Phase B.5; ship the tolerant surface in Phase B.**

What Phase B ships:
- Frontend `follow_up_suggestions` props type gains optional `action?: AiSuggestionAction` matching `contracts/ai-followup-suggestion.schema.json` (Phase A). The renderer **ignores** `action` and keeps sending `message` — the schema-mandated fallback, working today.
- No Laravel `action` validation, no runtime `ui_action` precedence, no builder changes.

Why defer (exact reasoning):
1. **Phase B already spans three codebases** (routes/controller/service + migration; panel/list/api/types/stream). The action path adds three more coordinated changes — Laravel chat-endpoint validation (tool ∈ registry ∧ scope ∧ permission ∧ ids ⊆ `context_json` displayed/focused), runtime `ui_action` router precedence, and runtime `FollowUpSuggestion.action` emission with per-builder inputs. That is a coherent standalone slice with its own test surface (doc 19 §10.3), not an increment on thread UX.
2. **No user-visible regression from deferring:** chips work today via `message`; the schema guarantees `message` remains mandatory, so B.5 is purely additive when it lands.
3. **Risk isolation:** action validation touches the permission path (`AiToolRegistry`) — a critical path per CLAUDE.md ("never change without care"). Bundling it with a UX sprint invites rushed review.
4. **Sequencing benefit:** B.5 can land together with the Phase C inventory tools, where `run_tool` actions (e.g. `{item_id}` movements) have their first real payloads.

Phase B.5 definition (for the record, not planned here): Laravel `action` request validation + `ui_action` forwarding; runtime router precedence honoring `ui_action` before the LLM; builders emitting `action` for chips whose inputs are fully determined; frontend `sendAction` path with 422→message fallback.

---

## 7. File-by-File Implementation Plan

### Backend (`alphasoft-backend/app-modules/ai/`) — implementation order within backend: 1→6

| # | File | Change |
|---|---|---|
| 1 | `routes/ai-routes.php` | Add `GET sessions` (`ai.sessions.index`) and `PATCH sessions/{session}` (`ai.sessions.update`, `whereNumber`) to the existing group |
| 2 | `database/migrations/tenant/2026_07_XX_add_activity_index_to_ai_sessions.php` (new) | Additive index `['user_id','last_message_at']` |
| 3 | `src/Http/Controllers/Api/V1/AiCopilotController.php` | Add `listSessions()` (§2.1) + `updateSession()` (§2.2). Restructure `streamChat()`: `ignore_user_abort(true)`; persist user row before adapter call; try/catch → assistant `complete|failed|interrupted` row; emit accepted `state_patch` then `done` on both paths (§2.3–2.4). Split `recordMessages()` → `recordUserMessage()` + `recordAssistantMessage(status)`. Add `->where('status','complete')` in `conversationMessages()`. Mirror user-row-first + failed-row in JSON `chat()` |
| 4 | `src/Services/AiSessionService.php` | `applyStatePatch()` returns/exposes the accepted subset (e.g. return `array{session: AiSession, accepted: array}` or add `acceptedKeys(array $patch): array` sibling — pick the smaller diff at implementation time) |
| 5 | `src/Services/Adapters/PythonRuntimeAdapter.php` | Remove `done` emission (:55–60). No other change — `session_start`, relay map, buffering untouched |
| 6 | `src/Services/Adapters/LaravelHttpAdapter.php` | Remove `done` emission (:61). (`StubRuntimeAdapter` — check and align if it also emits `done`) |

### Frontend (`alpaerpfrontend-1/src/`) — order: 1→2→3→4→5

| # | File | Change |
|---|---|---|
| 1 | `lib/ai/types.ts` | Extend `AiSession.attributes` (title, last_message_at, created_at, context) + optional `relationships.messages`; add `AiPersistedMessage`; add `failed?: boolean`, `traces?: unknown[]` to `AiChatMessage`; add optional `action` to the `follow_up_suggestions` suggestion type (§6) |
| 2 | `lib/ai/api.ts` | Add `listAiSessions`, `showAiSession`, `renameAiSession` (§3.1) |
| 3 | `lib/ai/replay.ts` (new, small) | `messagesFromSession(session): AiChatMessage[]` — pure mapping from `AiMessageResource` shape to panel state (blocks ids, tool badges, failed markers). Pure function ⇒ unit-testable |
| 4 | `components/ai/AiThreadList.tsx` (new) | Thread list per §3.2 |
| 5 | `components/ai/AiPanel.tsx` | Restore-on-open (no auto-create), localStorage handling, scope-switch-as-thread-switch (retire `handleClear`), SSE handling per §4.1, failed-turn + Retry rendering hooks, journey starters (constant in `lib/ai/journey-starters.ts`), thread-list integration, refresh-after-send |
| — | `components/ai/AiMessageList.tsx` | Render failure marker for `failed` messages; starters slot for empty state (props-driven, keeps the component dumb) |

### Runtime (`alphasoft-erp-ai-studio/runtime/`)
**No changes required for Phase B.** (`state_patch` already emitted; `done` is runtime-internal and consumed by Laravel's parser, unaffected by the Laravel-side `done` ownership move — the runtime's own `done` frame is simply not relayed, exactly as today.) The `action` field lands in B.5.

---

## 8. Test Plan (specification only — implemented by a separate agent)

### Backend feature tests (`tests/Feature/Ai/`, sqlite :memory:, existing `tests/Concerns/*` helpers)

1. **List endpoint:** returns only the authed user's sessions (second user's sessions invisible); ordered by `last_message_at` desc; `status`/`module_scope` filters; cursor pagination walks all pages; 422 on bad filter values; 401 unauthenticated.
2. **PATCH rename:** 200 + persisted title; 422 empty/>120-char title; 404 for another user's session; rename survives a subsequent chat turn (auto-title must not overwrite a user title).
3. **Persistence restructure:** user row persisted even when the adapter throws (fake adapter that throws); assistant `failed` row shape (empty content, error trace, zero tokens); success path unchanged (two rows, statuses `complete`); `conversationMessages` excludes non-complete rows (seed a `failed` row, assert prompt window skips it); JSON `chat()` failure leaves the same transcript.
4. **SSE tail:** streamed response ends `…state_patch(accepted subset only) → done` on success — assert a patch containing a non-whitelisted key streams without that key; `error → done` on failure; `done` emitted exactly once (adapters no longer emit it — assert no duplicate).
5. **Regression:** existing Phase-0/1 AI feature tests still green (notably any that asserted the old event order or `recordMessages` behavior — update alongside, per the CLAUDE.md rule about tests asserting old behavior).

### Frontend tests (only if the project has a component test setup — verify before writing; if none exists, do not introduce a framework for this, cover via manual smoke)

- `lib/ai/replay.ts` unit tests: text/component/failed message mapping (pure function — testable even with just the existing lint/type toolchain if a runner exists).
- Type-level: `npm run build && npm run lint` (house minimum).

### Runtime tests
None — runtime untouched in Phase B.

### Manual smoke test (browser, real tenant, Python adapter active)

1. Open panel → no orphan session created; starters shown.
2. Send in inventory scope → stream renders; thread appears in list with auto-title; `done` finalizes.
3. Switch scope to POS → old thread preserved in list; new starters; send → second thread.
4. Rename a thread; reload the page; reopen panel → active thread restored from localStorage with full replay (text + components + badges).
5. Kill the runtime container mid-conversation → failed turn visible with Retry; user message survives reload.
6. Close a thread → moves under closed filter; replay still works read-only; chat on it returns 422 "Session is closed".
7. Verify in devtools: `state_patch` frames contain only whitelisted keys; event order per §4.2.

---

## 9. Risks and Rollback

| Risk | Mitigation / rollback |
|---|---|
| `streamChat` restructure touches the one path every AI conversation crosses | Change is sequencing + try/catch, not logic; feature tests pin both paths before merge. Rollback = revert the controller file — routes/migration are independent and can stay |
| `done` ownership move breaks a consumer that relied on adapter-emitted `done` | Only known consumer is the frontend, which ignores `done` today (F3). Wire shape identical (one `done`, last). Rollback = re-add the two adapter emissions |
| `ignore_user_abort` keeps PHP workers alive on abandoned streams | Bounded by the existing 120 s runtime timeout (`config ai.python_runtime.timeout`); the buffered adapter means post-abort work is persistence only (ms). If worker pressure appears, drop to best-effort persistence without the flag |
| Scope-switch behavior change surprises existing users (Clear used to wipe) | "New conversation" + per-thread close remain one click away; old behavior was data loss, not a feature. No rollback path needed beyond reverting `AiPanel` |
| localStorage restores a session the server since closed | Restore validates against the fetched list (`status: active`); stale ids fall through to newest-active/empty state |
| Cursor pagination + `last_message_at` ties | Secondary `orderByDesc('id')` makes the cursor total |
| Uncommitted Phase-0/1/2 work in both repos | All changes are additive files or edits to files already uncommitted — no rebase/revert of unrelated work; verify `git status` before starting and touch nothing outside §7's list |

---

## 10. Recommended Implementation Order

1. **Backend routes + migration + controller list/rename** (§7 backend 1–3 partial) — smallest slice that unblocks frontend thread UX; frontend work can start against it immediately.
2. **Backend `streamChat` restructure + `state_patch`/`done` tail + adapter `done` removal** (§7 backend 3–6) — one reviewable PR-sized change with its feature tests (§8.3–8.4) specified for the test agent.
3. **Frontend types + api + replay mapper** (§7 frontend 1–3) — pure additions, no UI change yet.
4. **Frontend `AiPanel` restore/scope/SSE handling + thread list + starters + failed-turn display** (§7 frontend 4–5) — the visible change, last, on top of everything above.
5. **Manual smoke test** (§8) end-to-end with the Python adapter active.
6. Hand the test specifications (§8) to the testing agent alongside slices 1–2, not after slice 4 — backend tests should gate the frontend work, not trail it.

Definition of done for Phase B: all §8 backend tests green, manual smoke §8 items 1–7 pass, `state_patch` visible in devtools with whitelisted keys only, and no event-contract regression for a frontend that hasn't updated yet.
