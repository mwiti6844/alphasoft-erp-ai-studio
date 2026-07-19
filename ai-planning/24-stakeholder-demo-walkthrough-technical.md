# 24 — Technical Demo Walkthrough

**Date:** 2026-07-18  
**Audience:** Engineers, implementation leads, reviewers  
**Status:** Planning only

## Goal

Explain the AI path end to end so stakeholders understand what is happening when a user asks a question, how data stays bounded, and where future phases will expand the system.

## System summary

- Frontend renders the ERP shell and the AI panel.
- Laravel owns tenant auth, permissions, session persistence, and tool execution.
- Python runtime owns orchestration, module routing, provider calls, memory interpretation, and follow-up generation.
- The runtime never connects to tenant databases.
- AI responses are assembled from streamed events and persisted back through Laravel.

## Current endpoints and contracts

These are the live surfaces the demo can exercise today.

### Frontend to Laravel

- `POST /api/auth/tenant/login` for tenant sign-in.
- `POST /api/v1/tenant/ai/sessions` to start a session.
- `GET /api/v1/tenant/ai/sessions/{id}` to replay a thread.
- `POST /api/v1/tenant/ai/sessions/{id}/chat` to send chat messages.
- `GET /api/v1/tenant/ai/sessions/{id}/tool-calls` to inspect tool execution history.
- `PATCH /api/v1/tenant/ai/sessions/{id}` to rename a thread.
- `DELETE /api/v1/tenant/ai/sessions/{id}` to close a thread.
- `GET /api/v1/tenant/ai/memories` and memory write/delete routes for explicit user memory management.

### Laravel to Python runtime

- `POST /api/chat` with a shared secret and a structured request body.
- `GET /api/health` on the runtime for service health.

### Laravel internal AI tool execution

- `POST /api/internal/ai/tools/{tool}/execute`
- This is the only path Python uses to request tenant data.
- Laravel validates permissions, executes the tool, and audits the call.

### Python runtime surfaced behavior

- `token` events become text deltas.
- `tool` events become tool start/result records.
- `component` events become generative UI blocks.
- `trace` events remain developer-visible.
- `state_patch` is proposed by Python and accepted by Laravel.
- `error` and `done` close the turn.

## Live request path

1. User sends a chat message in the frontend.
2. Frontend posts to Laravel.
3. Laravel resolves tenant context, permissions, session state, and available tools.
4. Laravel forwards the request to the Python runtime with:
   - `tenant_id`
   - `user_id`
   - `session_id`
   - `runtime_session_id`
   - `domain`
   - `module_scope`
   - `message`
   - `messages`
   - `conversation_state`
   - `ui_action`
   - `user_memory`
   - `tool_definitions`
   - `max_tokens`
   - `temperature`
5. Python selects the module router and provider.
6. Python may call Laravel tools.
7. Python streams token, tool, component, trace, and state patch events.
8. Laravel persists the result and returns the response to the browser.

## Request body fields explained

The request body matters because it is the contract between Laravel and the Python runtime. Each field exists for a reason.

- `tenant_id`: the tenant being served. This is used for tenancy-aware audit and request correlation.
- `user_id`: the signed-in user asking the question.
- `session_id`: the persisted AI session in Laravel.
- `runtime_session_id`: the runtime-side conversation token used to link the request back to a live orchestration session.
- `domain`: the tenant hostname, used so the runtime and Laravel can agree on which tenant context is active.
- `module_scope`: the selected AI scope such as `inventory`, `pos`, or `catalog`.
- `message`: the latest user utterance.
- `messages`: the recent chat history window passed in by Laravel, so the runtime can keep short-term conversational context.
- `conversation_state`: the durable session state snapshot from Laravel, including focused entity, date range, filters, and memory-derived hints.
- `ui_action`: a structured interaction from the frontend, such as a suggestion click that should be treated as an action instead of ordinary text.
- `user_memory`: explicit user preferences such as default module or answer verbosity.
- `tool_definitions`: only the tools Laravel has already filtered as allowed for the current tenant, user, and scope.
- `max_tokens`: the generation budget for the turn.
- `temperature`: the sampling setting for the provider.

The important part is that the runtime does not invent any of this state. It receives the state that Laravel already owns, then reasons over it.

## What to point out in the demo

- Module routing is deterministic: the user chooses Inventory, POS, or Catalog.
- Tool access is permission-filtered before Python sees it.
- Memory is layered:
  - short-term conversation history
  - session state
  - explicit user memory
- Follow-up suggestions are deterministic, not generated from thin air.
- The assistant can say “I do not know” when the data does not exist.

## Memory layers and why they exist

Memory is split into layers because each layer solves a different problem and carries a different risk profile.

### 1. Short-term conversation history

- Lives in the current chat thread and the latest message window.
- Purpose: keep the current conversation coherent without replaying the whole history forever.
- Why it matters: lets the assistant answer follow-ups like “what about last month?” or “show me its movements” without the user repeating themselves.

### 2. Session state

- Lives in Laravel session state, currently in `ai_sessions.context_json`.
- Purpose: hold structured facts that should survive across turns in the same session.
- Examples:
  - selected entity
  - date range
  - filters
  - currently displayed IDs
  - last tool used
- Why it matters: the AI can continue a line of thought across multiple questions and suggestions.

### 3. Explicit user memory

- Lives in explicit memory storage, one row per preference key.
- Purpose: capture stable user preferences such as default branch, preferred module, or verbosity.
- Why it matters: it reduces repetition across sessions without turning the assistant into a hidden profile store.

### Why the split matters

- It keeps stable preferences separate from temporary turn context.
- It makes permission and audit behavior easier to reason about.
- It gives us a clean path for future memory features without mixing them into session state.

## Module routing and cross-module questions

Module routing is deterministic today: the user chooses the scope, and the runtime loads the matching router.

That is deliberate. It keeps the assistant predictable and avoids module confusion.

### What that means today

- If the user is in Inventory, the assistant behaves like Inventory.
- If the user is in POS, it behaves like POS.
- If the user is in Catalog, it behaves like Catalog.
- The module does not get re-inferred from every question.

### What happens with cross-module questions today

- The runtime stays within the chosen scope.
- If the question clearly needs data from another module, the assistant can either:
  - answer with the current scope’s available tools, or
  - ask the user to switch scope, or
  - explain that the needed tool is not available yet.

### Future cross-module design

Later phases can support richer cross-module orchestration, but that should remain explicit and permission-aware.

Examples:

- Inventory asking POS for sales velocity to explain reorder risk.
- POS asking Inventory whether a catalog item is in stock.
- Catalog asking Inventory whether a product is sellable in a warehouse.

The likely pattern is not free-form agent handoff. It is a controlled multi-step flow where:

- Laravel still owns the tool permissions.
- The runtime asks for a second tool only when it is allowed.
- The final answer remains grounded in validated tool output.

## Future endpoints and MCP paths

The current system is read-only from the AI side, but the contract is designed to grow.

### Likely future read endpoints

- module-specific resource lookups for richer Gen UI
- inventory item detail lookups
- catalog item and bundle lookups
- movement history with better filters
- thread list and thread metadata endpoints if we need richer AI navigation

### Likely future action endpoints

- draft creation for AI-assisted updates
- approve/reject flows for human-reviewed changes
- onboarding helpers for catalog item creation
- guided inventory setup flows

### MCP direction

If we add MCP later, it should be a transport change, not a new AI contract.

- Laravel still gates access.
- The runtime still receives validated tool metadata.
- The runtime still calls a Laravel-owned execution surface.
- MCP would mainly change how that execution surface is reached.

## Future multi-agent workflows

We do not need a full multi-agent system to explain the current demo, but the architecture leaves room for one.

### Example future flows

#### Catalog onboarding

User: “Help me onboard a new catalog item.”

Future assistant flow:

1. Ask for required item details.
2. Check whether the item already exists.
3. Check module permissions.
4. Prepare a draft suggestion or guided form payload.
5. Let the user confirm before any write happens.

#### Inventory setup

User: “Set up a warehouse and link it to the main branch.”

Future assistant flow:

1. Gather the required details.
2. Verify the branch and warehouse relationship.
3. Generate a structured draft.
4. Route it through approval if writes are enabled.

#### POS reporting help

User: “Why did sales drop last week?”

Future assistant flow:

1. Pull POS report data.
2. Check whether inventory constraints explain the drop.
3. Present the result with follow-up options.

### Why this matters

The conversation interface can become an operational layer, not just a reporting layer.

That said, it should only automate what the system can already do safely and visibly. We should not build AI behavior ahead of the underlying business workflow.

## What is read-only today

- Inventory analytics
- POS analytics
- Catalog queries
- Thread replay and session restore

## Interactive Gen UI

The current assistant is not just text. It can emit structured UI blocks.

### Why Gen UI matters

- It makes the answer easier to scan.
- It lets users interact with the output instead of reading a wall of text.
- It supports module-specific rendering, such as tables or summary cards.
- It supports permission-specific rendering, because the frontend only allows known component types.

### Practical demo angle

Show a result that includes:

- a text explanation
- a data table or summary block
- a follow-up suggestion chip

Then click the suggestion to show the conversation continuing naturally.

### Future Gen UI direction

- richer inventory tables
- product detail cards
- onboarding forms for catalog items
- action-confirmation components
- clarification components for ambiguous questions

## What is intentionally not claimed

- No autonomous writes
- No raw SQL from the model
- No Python database access
- No true token streaming end to end
- No invented ad or campaign analytics

## Why AI comes after system build

The assistant should come after the underlying workflows are stable, not before them.

Reason:

- AI is only useful when it can rely on real system behavior.
- If the business workflow is not built yet, the assistant will only expose gaps.
- It is better to first build the actual screens, permissions, and data models, then decide which steps are worth automating or exposing through AI.

That is why the current demo should frame AI as an orchestration layer over real ERP workflows, not as a replacement for unfinished application logic.

## Demo checkpoints

1. Login succeeds on the seeded tenant.
2. AI panel opens with the selected module scope.
3. A live question returns a grounded answer.
4. A follow-up suggestion works without retyping context.
5. A scope switch starts a new thread cleanly.
6. Reopening the panel restores the existing conversation.
7. A Gen UI result renders as more than plain text.
8. A catalog onboarding or item-help question shows how future workflows could become interactive.

## If a failure appears during the demo

- Login issue: check tenant host, seeded credentials, and password-change state.
- Empty or wrong AI response: verify Laravel runtime adapter and tool definitions.
- Missing UI styling: restart the Next dev server and clear stale `.next` output.
- 401 from runtime: check the shared secret between Laravel and Python.
- 422 from runtime: check the request body shape, especially dictionary fields.
- Missing Gen UI blocks: confirm the frontend component allow-list matches the runtime output.

## Closing line

“This demo shows the contract between UI, Laravel, and the Python runtime. The current value is live, read-only assistance with permission-aware tool use. The next phases extend memory, reporting, interactive Gen UI, and action flows without changing that separation.”
