# brain.md — AI Studio working memory

> Living notes for what we have actually shipped in the AI workstream.
> Companion to `PROJECT.md` (architecture narrative) and `GAPS.md` (open weaknesses).
> Update this file when closing a platform gap — not for every prompt tweak.

Last updated: **2026-07-17**

---

## 2026-07-17 — Laravel MCP + Python Runtime Bridge

Closed the Phase-C seam: Laravel is no longer a silent alias of `LaravelHttpAdapter` when `AI_RUNTIME_ADAPTER=python`. Browser still talks only to Laravel; Python orchestrates LLM + tool loops and calls back into Laravel over an MCP-shaped HTTP gateway.

### Architecture (locked)

```txt
Browser (AiPanel)
  │  Sanctum + tenant Host
  │  POST /api/v1/tenant/ai/sessions/{id}/chat  (SSE)
  ▼
Laravel  PythonRuntimeAdapter
  │  mint short-lived runtime session (cache)
  │    → user_id, tenant_id, domain, permissions, ai_session_id, module_scope
  │  POST {AI_PYTHON_RUNTIME_URL}/api/chat
  │    header: X-AI-RUNTIME-TOKEN
  │    body: ChatRequest + runtime_session_id + domain
  ▼
Python FastAPI runtime  (LLM loop, module routers)
  │  POST /api/internal/ai/mcp/tools/call
  │    header: X-AI-RUNTIME-TOKEN
  │    body: runtime_session_id, domain, name, arguments (+ optional claim confirmations)
  ▼
Laravel MCP gateway
  │  VerifyAiRuntimeToken → load runtime session → assert domain
  │  tenancy()->initialize(tenant) → AiToolRegistry::dispatch → ai_tool_calls audit
  │  tenancy()->end()
  ▼
Python SSE → Laravel remaps → Browser SSE
  token → text_delta
  tool started/completed → tool_start / tool_result
  done / error → done / error
```

**Invariants**

1. Python never opens a tenant DB connection.
2. Browser never calls Python or `/api/internal/ai/*`.
3. User Sanctum token never leaves Laravel; Python holds only `runtime_session_id` + shared secret.
4. Every tool run is audited under the real user in `ai_tool_calls`.
5. When adapter is `python`, `AI_ENFORCE_PERMISSIONS` is forced `true`.

### Laravel pieces (canonical backend `app-modules/ai`)

| Piece | Path / location |
|-------|-----------------|
| Config | `config/ai.php` → `python.base_url`, `shared_secret`, `timeout`, `runtime_session_ttl` |
| Env | `AI_RUNTIME_ADAPTER=python`, `AI_PYTHON_RUNTIME_URL`, `AI_RUNTIME_SHARED_SECRET`, `AI_PYTHON_TIMEOUT`, `AI_RUNTIME_SESSION_TTL` |
| Middleware | `Http/Middleware/VerifyAiRuntimeToken.php` — constant-time `X-AI-RUNTIME-TOKEN` check |
| Runtime session DTO | `DataObjects/AiRuntimeSession.php` |
| Session store | `Services/AiRuntimeSessionStore.php` (cache; create/get/touch/forget) |
| Tenancy hydrate | `Services/AiRuntimeContext.php` — domain ownership + user + `AiSession` |
| MCP controller | `Http/Controllers/Internal/AiMcpController.php` |
| Internal routes | `routes/ai-internal-routes.php` (loaded from `AiServiceProvider`) |
| Adapter | `Services/Adapters/PythonRuntimeAdapter.php` |
| Binding | `AiServiceProvider`: `'python' => PythonRuntimeAdapter::class` |

### MCP HTTP endpoints

All require `X-AI-RUNTIME-TOKEN` matching `AI_RUNTIME_SHARED_SECRET`. JSON envelope: `{ data, message, errors }`.

| Method | Path | Role |
|--------|------|------|
| `POST` | `/api/internal/ai/mcp/initialize` | Validate session; return protocol + context |
| `POST` | `/api/internal/ai/mcp/tools/list` | Permission-filtered tool defs for module_scope |
| `POST` | `/api/internal/ai/mcp/tools/call` | **Canonical** tool execute + audit |
| `POST` | `/api/internal/ai/mcp/resources/read` | `erp://context/me\|tenant\|session` |
| `POST` | `/api/internal/ai/tools/{tool}/execute` | Thin alias → `tools/call` (`input` → `arguments`) |

**Canonical `tools/call` body**

```json
{
  "runtime_session_id": "...",
  "domain": "shop.alphasoft.app",
  "name": "inventory_balance",
  "arguments": {},
  "tenant_id": "optional-confirm",
  "user_id": 42,
  "session_id": 7
}
```

Rejects: bad secret (`401`), wrong/expired session (`404`), domain or claim mismatch (`403`), missing tool permission (`403`), unknown tool (`404`).

### Python runtime pieces (this repo)

| Piece | Path |
|-------|------|
| Chat contract | `runtime/app/routes/chat.py` — `runtime_session_id`, `domain` required on `ChatRequest` |
| Laravel client | `runtime/app/clients/laravel.py` — posts MCP `tools/call`; unwraps `data.output` |
| Copilot loop | `runtime/app/agents/copilot.py` — passes runtime session + domain on every tool call |
| Env examples | `runtime/.env.example`, `runtime/.env.production.example` — secret must match Laravel |

### Frontend

**No code changes.** Existing panel still uses:

- `POST /api/v1/tenant/ai/sessions`
- `POST /api/v1/tenant/ai/sessions/{id}/chat` with `Accept: text/event-stream`

SSE event names the UI already understands (`session_start`, `tool_start`, `tool_result`, `text_delta`, `done`, `error`) are produced by Laravel’s remap layer. Do **not** expose MCP URLs or the shared secret to Next.js.

### Local enable checklist

```env
# Laravel
AI_RUNTIME_ADAPTER=python
AI_PYTHON_RUNTIME_URL=http://127.0.0.1:8090
AI_RUNTIME_SHARED_SECRET=<strong-shared-value>
AI_ENFORCE_PERMISSIONS=true

# Python runtime
LARAVEL_INTERNAL_URL=http://127.0.0.1:8000
AI_RUNTIME_SHARED_SECRET=<same-value>
```

Production rejects empty/placeholder secrets when the python adapter is active.

### Tests added

| Suite | What |
|-------|------|
| Backend `tests/Feature/Ai/AiMcpInternalTest.php` | secret reject; tools/call success; wrong domain; expired session; execute alias; permission deny; cross-tenant claim |
| Runtime `tests/clients/test_laravel_client.py` | MCP payload includes `runtime_session_id` + `domain` |
| Runtime agent tests | updated for new `execute_tool` kwargs |

### Explicitly still out of scope (do not invent)

- Real MCP stdio / SSE SDK packaging (HTTP MCP-shaped only for now)
- Browser → Python direct
- NL2SQL / Python DB access
- New ERP tools beyond catalog/inventory set
- Forwarding Python `component` / `state_patch` / `trace` into the frontend panel (adapter ignores them today; chat still works)

### Docs debt this supersedes

Older notes that said `AI_RUNTIME_ADAPTER=python` silently binds `LaravelHttpAdapter` / “Python runtime not implemented” are **obsolete** for the monorepo backend that contains `PythonRuntimeAdapter` and the MCP routes. Prefer this file over `CLAUDE.md` gotcha #1 and `GAPS.md` item #8 until those are refreshed.
