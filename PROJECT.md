# PROJECT.md — AlphaSoft ERP AI Platform

> Knowledge-transfer document, written 2026-07-06 during a deep codebase review.
> Audience: an engineer or AI agent who has never seen this project.
> Companion files: `GAPS.md` (honest audit of weaknesses), `CLAUDE.md` (operational rules for agent sessions).

---

## 1. What This Is

AlphaSoft is a multi-tenant POS + ERP platform for small and mid-size businesses in East Africa (Uganda/Kenya focus): restaurants, retail shops, pharmacies, importers, and online sellers. Tenants get invoicing, receipting, catalog, inventory, POS registers (web now, desktop later), and vertical-specific flows (restaurant kitchens, pharmacy prescriptions, retail warranties).

**This repository (`alphasoft-erp-ai-studio`) is the AI workstream's home.** The AI layer — branded "AI Studio" — adds a governed copilot, automated business-insight reports, recommendation systems, and (later) document intelligence and multi-step agents on top of the ERP. The AI owner is David Mwiti; launch target is end of July 2026, restaurant + retail first.

The AI system is deliberately **not a chatbot bolted on**. It is a permissioned, audited, tool-based layer where the model can only touch tenant data through narrow, typed, permission-checked tools, and where any AI-proposed change must pass human review. Read `ai-planning/01-product-vision.md` for the philosophy and `ai-planning/11-ai-platform-master-plan.md` for the full plan.

## 2. The Three Repositories

| Repo (on Desktop) | Role | Stack |
|---|---|---|
| `alphasoft-backend/alphasoft-backend` | Canonical backend. Laravel modular monolith. **All tenant data access and all AI tool execution happens here.** | PHP 8.3, Laravel 12, stancl/tenancy 3.9, spatie/laravel-permission 7, internachi/modular 3, Sanctum, SQLite-per-test / MySQL prod |
| `alpaerpfrontend-1` | Frontend SPA shell. All AI UX (copilot panel, future studio pages). | Next.js 15, React 19, TypeScript, zustand, TanStack Query, Tailwind |
| `alphasoft-erp-ai-studio` (this repo) | AI planning docs today; grows into prompts/, evals/, contracts/, and a Python agent runtime (Phase C). | Markdown now; FastAPI later |

A fourth folder, `adk-samples` (Google's Agent Development Kit samples, May 2026 snapshot), is **reference material only** — never a dependency.

History note: an older clone `alpha-erp-backend` (different GitHub remote, `mugambi-victor/alpha-erp-backend`) was retired on 2026-07-06 after verifying it contained no unique code. The canonical remote is `Geekigen/alphasoft-backend`.

## 3. Why This Stack

- **Laravel modular monolith** (`internachi/modular`): each domain is a composer package in `app-modules/` (`ai`, `catalog`, `inventory`, `pos`, `patients`, `activity-log`) with its own `src/`, `routes/`, `database/migrations/tenant/`, and `config/permissions.php`. Chosen for one deployable unit with module boundaries — right call for a small team.
- **stancl/tenancy, DB-per-tenant, domain-identified**: every tenant gets its own database; tenancy is initialized by domain middleware. Central DB holds tenants, domains, central users. This is the platform's deepest architectural commitment — everything else respects it.
- **spatie/laravel-permission**: roles/permissions per module declared in each module's `config/permissions.php` (house rule: never ad-hoc seeders). The AI layer reuses these exact permissions for tool access.
- **Next.js client-shell SPA**: the frontend calls Laravel directly via `tenantFetch`/`centralFetch` — **no Next.js BFF proxy routes for CRUD** (house rule). AI streaming likewise goes browser → Laravel SSE directly.
- **Anthropic-first AI**: the copilot was built and tested against Claude's Messages API + tool use. Provider strategy (see `ai-planning/09-...md`): Microsoft Foundry as primary endpoint (Claude GA there since 2026-06-29, native Messages API at an Azure base URL), direct Anthropic/OpenAI as fallbacks.

## 4. Architecture — How a Copilot Request Flows

```txt
Browser (AiPanel.tsx, mounted in ErpShell)
  │  POST /api/v1/tenant/ai/sessions            (create session, module scope e.g. 'inventory')
  │  POST /api/v1/tenant/ai/sessions/{id}/chat  (Accept: text/event-stream)
  ▼
Laravel  routes: app-modules/ai/routes/ai-routes.php
  middleware: InitializeTenancyByDomain → PreventAccessFromCentralDomains → auth:sanctum
  ▼
AiCopilotController ── AiSessionService (ai_sessions row, token tallies via recordTurn)
  ▼
AiRuntimeAdapterInterface  ← bound in AiServiceProvider from config('ai.runtime_adapter')
  ├─ StubRuntimeAdapter        ('stub' — canned responses, used by Phase-0 tests)
  └─ LaravelHttpAdapter        ('laravel_http' — the real one)
       │  loop ≤ 8 iterations:
       │    AiSystemPromptBuilder (inline PHP heredoc prompt: tenant, user, scope, tool list)
       │    AiModelRegistry.providerForModel(model) → provider id
       │    resolveProvider() → AnthropicHttpProvider   ⚠ throws for any non-anthropic id
       │    provider.chat() → POST {base_url}/v1/messages (x-api-key, 120s timeout, no retry)
       │    stop_reason == 'tool_use' ? → AiToolRegistry.dispatch(name, input, user, session)
       │         • permission check (config 'ai.enforce_permissions' — DEFAULT FALSE)
       │         • tool.execute() → Eloquent queries, minimal field selection
       │         • ai_tool_calls audit row (+ duration, permission snapshot)
       │    else → final text
       ▼
  AiSseEmitter → SSE events (session_start, tool events, text deltas, done)
       ⚠ "streaming" is simulated: the provider call is blocking; the final text is
         chunked into deltas afterwards (LaravelHttpAdapter::streamTextDeltas)
  ▼
Browser stream.ts parses SSE → AiMessageList renders text + AiToolCallBadge per tool call
```

**Tables (tenant DB):** `ai_sessions` (user, module_scope, model_id, token tallies, status), `ai_tool_calls` (session, tool, input/output, duration, permission snapshot), `ai_suggestions` (draft → reviewed → applied/rejected workflow — **schema exists, no endpoints/UI yet**; this is the designated write path for all future AI drafts).

**The five live tools** (all read-only, `app-modules/ai/src/Services/Tools/`): `catalog_search`, `catalog_item_detail`, `inventory_balance`, `inventory_movements`, `warehouse_list`. Tool classes implement `AiToolContract`: `name()`, `moduleScope()`, `permission()` (module/resource/action triple), `definition()` (JSON schema), `execute(array, User): array`. Registration is a hardcoded const list in `AiToolRegistry::TOOL_CLASSES`.

## 5. Key Design Decisions (and Why)

1. **Tools, never SQL-from-prompts.** The model requests named tools; Laravel executes them under the caller's identity and permissions, returns minimal fields, and audits every call. This is the load-bearing safety decision — everything else (approvals, budgets, PII posture) hangs off it.
2. **Adapter seam for the runtime.** `AiRuntimeAdapterInterface` lets orchestration move to a Python service later (this repo's `runtime/`, Phase C) without touching tools, sessions, or the controller. Note: the `'python'` config value currently silently maps to `LaravelHttpAdapter` — a placeholder, not an implementation.
3. **Provider abstraction with one implementation.** `AiProviderInterface`/`AiModelConfig`/`AiProviderResponse` are clean; only Anthropic is implemented. `config/ai.php` has credential slots for openai/groq/gemini and the registry maps model ids to those providers, but selecting them throws at runtime. The planned `AiProviderRouter` (Foundry primary → direct fallbacks, metering, circuit breaker) is specced in `ai-planning/10-ai-mvp-work-packets.md` WP2.
4. **SQL computes, models narrate.** Analytics figures come from aggregation queries; the LLM only writes prose around them. Correctness rule and the main cost control.
5. **`ai_suggestions` as the only future write path.** AI never mutates ERP data directly; it files a suggestion a human approves. The schema anticipates this fully (status, reviewer, rejection_reason, applied_at).
6. **Per-vertical demo/tooling follows the module system.** New verticals (restaurant, pharmacy, hotel…) become tool packs + permissions + eval fixtures — the "inheritance contract" in `ai-planning/11-...md` §1.

## 6. Critical Paths (Handle With Care)

- **Tenancy middleware chain** on `ai-routes.php` and everywhere else. Breaking tenant isolation is the worst possible bug in this product. Never query tenant models outside an initialized tenancy context.
- **`AiToolRegistry::dispatch`** — permission gate + audit trail. Any change here changes the security posture of every tool.
- **`LaravelHttpAdapter::runConversation`** — the agentic loop (iteration cap, tool-result threading, token tallies). Subtle bugs here cause runaway loops or silent tool-result loss. It currently has **no direct test**.
- **Module `config/permissions.php` files** — roles derive from these; the AI permission triples must match them exactly.
- **`.github/workflows/deploy-production.yml`** — pushes to `main` auto-deploy to the production VPS. Treat every merge to main as a deploy.

**Safe to change casually:** frontend AI components (`src/components/ai/*` — self-contained), tool `description()` texts, the system prompt wording, `config/ai.php` defaults (except `enforce_permissions`), planning docs in this repo.

## 7. Surprises That Will Trip You Up

1. **Streaming is fake.** `AnthropicHttpProvider::supportsStreaming()` returns true, but the HTTP call is non-streaming; SSE deltas are replayed from the finished response. Long answers feel slow for a reason.
2. **Selecting a GPT model crashes.** The model registry happily maps `gpt-4o` → `openai`; `resolveProvider()` then throws `InvalidArgumentException`. Fix is WP1/WP2, not a one-liner in the registry.
3. **Permission enforcement is OFF by default** (`AI_ENFORCE_PERMISSIONS=false`). Tests even assert tools are available *without* ERP permissions when disabled. Must be flipped before launch (WP10).
4. **The `'python'` adapter is a lie** — it binds `LaravelHttpAdapter`. Don't assume config values reflect implementations; read `AiServiceProvider`.
5. **Unknown model ids silently become Anthropic** (`AiModelRegistry` default branch). A typo'd model id doesn't error where you expect.
6. **Tests require the isolated DB machinery.** `phpunit.xml` forces sqlite `:memory:` + `TEST_DB_ISOLATED=true`; helpers in `tests/Concerns/` provision tenants per test. House rule: destructive tests must never touch dev databases.
7. **The backend nests one level:** the repo root you want is `alphasoft-backend/alphasoft-backend/` (a folder inside a folder of the same name).
8. **`docs/` in the backend is rich** — module implementation guides, user journeys, runbook. Read `docs/project-runbook.md` and the module doc for whatever you touch; the team keeps journey docs current as a working practice (see backend `AGENTS.md`).
9. **Frontend auth for SSE** is a bearer token from a zustand store (`getTenantToken()`); a 401 mid-stream clears auth and redirects to login (`stream.ts`).
10. **`max_tokens` defaults to 1024** — fine for chat answers, too small for long report narratives; raise per-call, not globally.
