# AI Platform Master Plan — POS First, ERP-Wide Foundation

Status: working plan · Owner: David Mwiti (AI Engineering) · Date: 2026-07-06
Builds on: `01-product-vision.md`, `03-ai-module-architecture.md`, `08-first-usecases.md`, `09-ai-provider-strategy-and-mvp-plan.md`, `10-ai-mvp-work-packets.md`

---

## 1. The Core Idea: One AI Platform, Many Inheriting Modules

The POS AI (restaurant + retail, launching end of July) is not a feature — it is the **first tenant of an AI platform** that every ERP module inherits. We build the platform once; each module buys in by shipping a small, standardized "AI pack." Nothing AI-specific is ever rebuilt per module.

**The inheritance contract.** A module becomes AI-enabled by shipping exactly five things:

1. **A tool pack** — classes implementing `AiToolContract`, registered in `AiToolRegistry` under the module's scope (`pos`, `catalog`, `inventory`, `accounting`, …). Tools are narrow, typed, minimal-output, and never raw SQL from prompts.
2. **Permission mappings** — each tool declares its required permission in the module's `config/permissions.php` roles block (existing house convention).
3. **Action-level declarations** — every tool is tagged with one of: `read_only` | `recommendation` | `draft` | `execute_with_approval` | `forbidden` (levels from `03-ai-module-architecture.md`). Launch scope allows only the first three.
4. **Insight queries** — reusable SQL aggregation classes that power both AI tools and scheduled insight reports (single source of truth for figures; the LLM never computes numbers).
5. **Eval fixtures** — golden question/answer datasets in the AI repo so the module's AI behavior is regression-tested like code.

Once a module ships its pack, every AI surface works for it automatically: the copilot panel, insight reports, the suggestions/approval workflow, budgets, audit, and (later) multi-step agents. Catalog and Inventory already conform; POS is the proof that a new vertical can be added this way.

---

## 2. Platform Architecture (Layers)

```txt
L4  Experience surfaces      AiPanel copilot (exists) · insight report cards · /ai studio pages
                             (runs, approvals, settings) · recommendations API for storefront
L3  Provider routing         AiProviderRouter → Foundry (primary) → Anthropic/OpenAI direct (fallback)
                             per-call token metering · per-tenant budgets · kill switch · circuit breaker
L2  Runtime                  now: LaravelHttpAdapter (agentic tool loop, SSE, ≤8 iterations)
                             later: Python AI Runtime service (this repo) for multi-step agents,
                             document intelligence, forecasting — behind AiRuntimeAdapterInterface
                             ('python' adapter slot already exists in config/ai.php)
L1  Tool layer (Laravel)     per-module tool packs · AiToolRegistry · permission enforcement ·
                             ai_tool_calls audit · ai_suggestions draft/approve workflow
L0  Data                     tenant DBs · module schemas · (later) telemetry aggregates · vector store
```

**Two invariants that never change, regardless of layer evolution:**

- **Laravel is the only door to tenant data.** The Python runtime, when it exists, calls Laravel's tool-execution API with scoped service tokens carrying tenant + user context. It never opens a DB connection. (This is the `03` doc's rule, made mechanical.)
- **Models never compute business figures.** SQL computes; models narrate, explain, and draft. This is both a correctness rule and the single biggest cost control (see `09` §2).

**Cross-cutting services (built once, inherited by all):**

| Service | Mechanism | Status |
|---|---|---|
| Permissions | tool-declared permission + `AI_ENFORCE_PERMISSIONS=true` | built, must be enabled (WP10) |
| Audit | `ai_sessions` / `ai_tool_calls` + `RecordsActivity` events on AI-applied changes | tables built; apply-flow events pending |
| Draft → approval | `ai_suggestions` (status: draft → reviewed → applied/rejected, reviewer, reason) | schema built; apply UI pending |
| Budgets & metering | router logs {tenant, endpoint, model, tokens} per call; daily cap + kill switch | pending (WP2/WP10) |
| Guardrails | Foundry content filters, PII redaction, Prompt Shields as defense-in-depth; primary PII control = tools return aggregates only | platform-side ready; ours by design |
| Telemetry (opt-in) | dedicated agent-auth endpoints; k-anonymous aggregates only; post-legal-review | Phase C |
| BYOK | per-tenant encrypted keys become highest-priority router endpoint for that tenant | Phase C |

---

## 3. This Repo (alphasoft-erp-ai-studio) Becomes the AI Repo

Today this repo is planning docs. It grows into the AI engineering home — everything AI that is *not* tenant-data access lives here:

```txt
alphasoft-erp-ai-studio/
├── ai-planning/          # these docs (source of truth for AI direction)
├── contracts/            # shared JSON Schemas / OpenAPI: tool spec, run spec, suggestion spec
│                         # (generated from / validated against the Laravel side in CI)
├── prompts/              # versioned system prompts + prompt changelog
│                         # Laravel reads released prompt versions; no inline prompt edits in PHP
├── evals/                # per-module eval suites: golden Q&A fixtures, tool-call assertions,
│                         # narrative-grounding checks (numbers in text ⊆ payload figures)
├── datasets/             # demo tenant seed specs (restaurant, retail) shared with backend seeders
└── runtime/              # Phase C: Python FastAPI agent service
    ├── agents/           # multi-step agent definitions (ADK-inspired patterns from adk-samples)
    ├── pipelines/        # document intelligence, forecasting jobs
    ├── clients/          # Foundry/Anthropic/OpenAI clients + Laravel tool-API client
    └── tests/
```

**Why the runtime lives here and not in Laravel:** multi-step agents, document pipelines, and forecasting want Python's ecosystem (and the ADK patterns we're referencing), but they must not weaken the L1 boundary. The `AiRuntimeAdapterInterface` in Laravel already anticipates this — the `python` adapter delegates orchestration while tool execution stays in Laravel. The runtime is stateless per request; all state (sessions, tool calls, suggestions) persists in Laravel's tables.

**Rule for the transition:** nothing moves to the Python runtime until it exists as a working Laravel-adapter feature or is impossible there (long-running pipelines, heavy Python deps). The copilot stays on `LaravelHttpAdapter` for launch; the runtime earns its way in.

---

## 4. Module Capability Map (What Inherits, and When)

Levels: RO = read_only, REC = recommendation, DR = draft, XA = execute_with_approval.

| Module / vertical | AI capabilities | Level | Phase |
|---|---|---|---|
| Catalog | completeness checks, item Q&A, cleanup suggestions | RO/REC | live (5 tools) |
| Inventory | balances, movements, stock explanations, reorder candidates | RO/REC | live / A |
| POS — restaurant | top/lagging dishes, sales summaries, peak hours, kitchen insights | RO/REC | A (launch) |
| POS — retail | same analytics pack (vertical-agnostic sale-line aggregations), imports client | RO/REC | A (launch) |
| Insight reports | scheduled SQL figures + narrated business report per tenant | RO | A (launch) |
| E-commerce | co-occurrence recommender (SQL, no LLM); later personalized ranking + "why" copy | — / REC | A / C |
| Suggestions apply-flow | AI drafts reviewed and applied by humans (generic, all modules) | DR | B |
| Excel/document entry | extraction → draft rows via suggestions flow; catalog import first, then supplier invoices | DR | B pilot / C |
| Accounting & finance | income/expense insights, anomaly flags, profit narration | RO/REC | C |
| Purchasing | reorder plan drafts, purchase request drafts, supplier comparison | DR/XA | C/D |
| Pharmacy | expiry/slow-stock alerts, interaction-check assist (assist only — never autonomous clinical logic) | RO/REC | C/D |
| Forecasting | demand/stockout forecasts (classical stats models + LLM narration, not LLM math) | REC | C |
| Telemetry insights | regional aggregate trends (opt-in, k-anonymous) | RO | C (post-legal) |
| Central admin | cross-tenant reporting in a separate AI context (separate routes, tokens, prompts) | RO | D |
| Knowledge / RAG | policy & contract Q&A over `ai_knowledge_sources` | RO | D |

The PM's cross-industry use-case list (hotels, fuel, clinics, salons) maps onto this same grid later: each is a vertical tool pack + demo dataset, not new platform work. That is the payoff of the inheritance contract.

---

## 5. Phased Roadmap

### Phase A — POS MVP (now → end July) · detailed in `10-ai-mvp-work-packets.md`
Provider router (Foundry primary + fallbacks, fixes the GPT-crash bug) · 4 restaurant/retail analytics tools · demo tenant seeders · business-insights report (SQL → Haiku narration → `ai_suggestions`) · frontend report card · SQL co-occurrence recommender · hardening (permissions ON, budgets, kill switch, integration tests) · demo + write-ups.
**Exit criteria:** restaurant demo passes twice; retail dataset answers the same questions; failover proven; per-tenant token metering live.

### Phase B — Platform-ization (August)
1. **Suggestions apply-flow** (the platform's most important generic feature): review UI at `/ai/approvals`, apply/reject endpoints, `RecordsActivity` audit events on apply. Every future draft feature rides this.
2. **AI Studio surfaces v1:** `/ai` landing, `/ai/runs` (session + tool-call history), `/ai/settings` (budget visibility). Reuses existing tables — mostly frontend work.
3. **Excel extraction pilot** on the safest target: catalog bulk-import (templates already exist) → drafts into apply-flow. Not accounting entries yet.
4. **Metering dashboard:** per-tenant token/cost visibility for us and for the client admin.
5. **Eval harness v1** in this repo: golden Q&A per module, run in CI against a seeded test tenant; narrative-grounding assertion (every number in AI text must exist in the tool payload).
6. **Prompt versioning:** system prompts move from PHP into `prompts/` with releases.
7. Onboard the retail/imports client and the cashew-nut vendor's e-commerce storefront on the recommender.

### Phase C — Runtime & Intelligence (September–October)
1. **Python AI Runtime v1** (`runtime/`): FastAPI, `python` adapter wired in Laravel, service-token auth carrying tenant+user context, first multi-step agent = supplier-invoice document intelligence (extract → match to receipts → draft via apply-flow). ADK samples (`customer-service`, `data-science`, invoice patterns) are the reference designs.
2. **Forecasting v1:** classical models (moving averages / seasonal decomposition) computed in jobs; LLM narrates. Demand + stockout risk for inventory.
3. **Telemetry pipeline** — only after legal review (Uganda DPPA / Kenya DPA): consent flags, agent-auth collection endpoints, k-anonymous aggregate store, regional insight reports.
4. **BYOK:** encrypted per-tenant keys as priority router endpoints; validation UX; liability terms.
5. **E-commerce recommender v2:** personalized ranking (user history features), optional LLM "why we suggest this" copy on the cheap tier.

### Phase D — Scale & Ecosystem (Q4 2026)
Central-admin cross-tenant AI (separate context per `03` doc) · knowledge sources + RAG (`ai_knowledge_sources`, vector store decision deferred until here) · multi-agent workflows (procurement chains) · per-vertical agent packaging ("Restaurant AI pack", "Pharmacy AI pack") as sellable modules · enterprise-account negotiation from metered usage data (per the payment proposal).

---

## 6. Cross-Repo Change Map

| Repo | Phase A | Phase B | Phase C |
|---|---|---|---|
| `alphasoft-backend` | OpenAI provider, router, POS tool pack, seeders, insights endpoint, hardening | apply-flow endpoints, metering API, extraction pilot endpoints, prompt-loading from AI repo releases | `python` adapter, service-token auth for runtime, telemetry endpoints, BYOK key store |
| `alpaerpfrontend-1` | insights report card, `pos.*` tool badges | `/ai` studio pages (approvals, runs, settings), metering dashboard, extraction review UI | agent-run views, forecast displays, telemetry consent UI |
| `alphasoft-erp-ai-studio` (this repo) | docs 09–11, demo dataset specs | `contracts/`, `prompts/`, `evals/` + CI harness | `runtime/` service, pipelines, agent evals |
| `adk-samples` | reference only — never a dependency | reference | reference for agent/pipeline patterns |

---

## 7. Engineering Conventions (Binding for All AI Work)

- **Tool spec:** name (`module.snake_case`), description, input schema, output schema, required permission, action level, audit behavior. Defined once in `contracts/`, enforced in code review.
- **Minimal output:** tools return only task-required fields; never customer PII in tool payloads (aggregates, item names, totals only). This is the primary PII control; Foundry redaction is the backstop.
- **Suggestions flow is the only write path:** any AI-proposed change becomes an `ai_suggestions` row and passes human review. No exceptions at current maturity (matches `01` vision "What AI Should Not Do Initially").
- **Model tiering:** Haiku-class for volume/narration, Sonnet-class for copilot/tool-use, no premium models without a named justification, no LLM where SQL suffices. Routing profiles live in `config/ai.php`; changing them is an engineering decision with zero procurement impact.
- **Testing:** every tool ships unit tests against fixtures; every module ships eval fixtures; CI runs evals on a dedicated test tenant DB (never dev DBs — house rule).
- **Prompts are code:** versioned in this repo, released explicitly, changelog required.
- **Budgets always on:** every runtime path passes the router's metering and caps; a feature that bypasses metering does not ship.

---

## 8. Open Decisions & Risks

1. **Azure billing eligibility** (verification in progress) — if it fails, direct APIs become primary; architecture unchanged. [Blocker only for procurement, not code.]
2. **Runtime hosting** (Phase C): same VPS as Laravel vs. separate service — decide when the runtime exists; start same-host for simplicity.
3. **Vector store** (Phase D): defer; do not pick a database before RAG is scoped.
4. **Pharmacy AI scope:** interaction checks and controlled-substance workflows have regulatory weight — pharmacy tools stay RO/REC until reviewed with the pharmacy-module owners.
5. **Telemetry legal review** is a hard gate for Phase C item 3 — engineering will not build ahead of it.
6. **Team bandwidth:** one AI engineer + coding agents. The phase plan is serialized accordingly; if Phase A slips, Phase B items 3–7 slip before items 1–2 (apply-flow and studio surfaces are the platform's spine).
