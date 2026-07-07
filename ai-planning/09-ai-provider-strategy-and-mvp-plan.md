# AlphaSoft ERP — AI Provider Strategy & End-of-July MVP Plan

Author: David Mwiti (drafted with AI assistance) · Date: 2026-07-06
Basis: code audit of `alphasoft-backend` (canonical, last commit 2026-07-03), `alpaerpfrontend-1`, `alphasoft-erp-ai-studio` planning docs, `adk-samples` reference repo, plus current Microsoft Foundry documentation (June 2026).

---

## 1. Where We Actually Are (Code Audit)

### What exists and works

**Backend `app-modules/ai` (Laravel, tenant-scoped):**

- Session lifecycle: `POST/GET/DELETE /api/v1/tenant/ai/sessions`, chat endpoint with SSE streaming, tool-call history endpoint. Tenancy middleware + Sanctum auth on all routes.
- Provider abstraction: `AiProviderInterface`, `AiModelConfig`, `AiProviderResponse` — clean seam for adding providers.
- One implemented provider: `AnthropicHttpProvider` (Messages API, tool translation, configurable `base_url`).
- Agentic tool loop: `LaravelHttpAdapter` runs up to 8 tool iterations, logs tool calls, streams via `AiSseEmitter`.
- Five read-only tools: catalog search, catalog item detail, inventory balances, inventory movements, warehouse list.
- Persistence: `ai_sessions`, `ai_tool_calls`, `ai_suggestions` (suggestions table already models draft → review → apply/reject — the approval workflow schema exists).
- `AiModelRegistry` maps models → providers (anthropic, openai, groq, gemini) and `config/ai.php` has credential slots for all four.

**Frontend (`alpaerpfrontend-1`):**

- Copilot UI: `AiPanel`, `AiPanelToggle` (mounted in `ErpShell`/`Header`), message list/input, tool-call badges, SSE stream client (`src/lib/ai/`).

### What is stubbed or missing

| Meeting commitment | Code reality |
|---|---|
| Anthropic for analytics | ✅ Implemented (copilot only, not analytics reports) |
| OpenAI for NL/write-ups | ❌ Registry maps `gpt-*` → `openai`, but `resolveProvider()` **throws** for anything non-Anthropic. Selecting a GPT model today crashes the chat. |
| Provider fallback of any kind | ❌ Single provider call, no retry/failover chain |
| Predictive analytics (top/lagging sellers) | ❌ Nothing |
| Advertising/marketing analytics | ❌ Nothing (no ad-tracking data model exists to analyze) |
| E-commerce recommender | ❌ Nothing |
| Automated data entry from Excel | ❌ Nothing (bulk CSV/Excel import exists in catalog, but no AI draft flow) |
| Opt-in telemetry / regional analytics | ❌ Nothing |
| BYO API keys per tenant | ❌ Keys are global `.env` values only |
| Super-admin cross-tenant reporting | ❌ Nothing; AI routes are tenant-only |
| Permission enforcement | ⚠️ Built, but `AI_ENFORCE_PERMISSIONS` defaults to **false** |
| Tests | ⚠️ One unit test (`AnthropicToolSchemaTest`) for the whole module |

**Repo hygiene:** `alpha-erp-backend` and `alphasoft-backend/alphasoft-backend` are the same repo; the nested `alphasoft-backend` copy is 3 commits ahead (July 3). Two working copies of the same repo on one desktop is how deploys go wrong. Decide the canonical clone and delete or archive the other.

---

## 2. Provider Strategy: Foundry Primary, Direct APIs Fallback

### Why Foundry-primary is defensible

- Claude models reached **general availability in Microsoft Foundry on June 29, 2026** — 11 Claude models including Opus 4.8 and Sonnet 4.6, alongside the full Azure OpenAI catalog. One platform, one bill, one governance/compliance story to show enterprise clients.
- Critically for us: **Claude on Foundry speaks the native Anthropic Messages API** at `https://<resource>.services.ai.azure.com/anthropic/v1/messages`. Our `AnthropicHttpProvider` already has a configurable `base_url` — pointing it at Foundry is a config change plus an auth-header switch, not a rewrite.
- Foundry's **Model Router** can front OpenAI + Anthropic + others behind one deployment with automatic failover and routing strategies (Balanced/Cost/Quality). Useful later; do not depend on it for MVP — we want failover logic we control and can test.

### Constraints to verify before committing (blockers if wrong)

1. **Billing eligibility:** Claude in Foundry requires a paid pay-as-you-go Azure subscription in a country where Anthropic offers models via Azure Marketplace. Verify our Azure billing country (Kenya/Uganda) is on the supported-regions list **before** the leadership proposal. If not, invert the plan: direct Anthropic/OpenAI APIs primary, Foundry later.
2. **Deployment regions:** Claude deployments are Global Standard in **East US2 or Sweden Central** only. Latency from East Africa via Sweden Central should be acceptable for chat/reports, but measure it.
3. **Auth:** Foundry Claude supports API-key or Entra ID. API-key is the low-friction start; Entra ID (keyless) is the enterprise story.

### Target architecture (extends what's already built)

```txt
AiRuntimeAdapterInterface (exists)
  └── LaravelHttpAdapter (exists)
        └── AiProviderRouter (NEW — implements AiProviderInterface)
              ├── priority chain per capability profile:
              │     analytics:  foundry-claude → anthropic-direct → openai-direct
              │     nl-tasks:   foundry-gpt    → openai-direct    → anthropic-direct
              │     cheap-bulk: foundry-haiku  → anthropic-direct
              ├── failover on: 429, 5xx, timeout, auth failure
              ├── circuit breaker: skip a provider for N minutes after M failures
              └── logs provider used + tokens per call (cost attribution per tenant)
  Providers:
    AnthropicHttpProvider   (exists — parameterize base_url/auth per endpoint: direct or Foundry)
    OpenAiHttpProvider      (NEW — chat completions/responses API, tool translation; also covers Foundry GPT deployments via Azure base_url)
```

Config change: replace flat `providers.anthropic` with named **endpoints** (`foundry_anthropic`, `anthropic_direct`, `foundry_openai`, `openai_direct`), each with base_url + auth mode + key, and **routing profiles** listing endpoint priority. Default model stays Haiku-class for cost.

### Model assignment (replaces the "Anthropic=analytics, OpenAI=writing" split)

The meeting's provider split is the wrong axis — both vendors do both tasks well. Split by **cost tier and volume** instead:

| Workload | Model class | Why |
|---|---|---|
| Copilot chat + tool use | Claude Sonnet | Best tool-use reliability; already built against it |
| Report narration, summaries, write-ups | Claude Haiku or GPT-4o-mini | High volume, low complexity — cheapest capable model |
| Excel/document extraction drafts | Sonnet-class (vision) | Accuracy matters; human reviews anyway |
| E-commerce recommendations | **No LLM** | Co-occurrence/association rules in SQL. Deterministic, ~free, milliseconds. An LLM call per product view is a cost and latency mistake. Add LLM copy ("why we suggest this") later if at all. |
| Top/lagging seller analytics | **No LLM for the math** | SQL aggregation computes the numbers; a cheap model narrates the result. Never let the LLM compute figures. |

---

## 3. End-of-July MVP — Cut List

Three and a half weeks remain. The full meeting scope (predictive analytics + recommender + ad analytics + auto data entry + telemetry + BYO keys) is **not shippable** by then with the current foundation. Ship this:

### In scope (MVP)

**Week 1 (by Jul 12) — provider plumbing + demo prep**
1. `OpenAiHttpProvider` + `AiProviderRouter` with failover chain (this also fixes the "GPT model crashes chat" bug).
2. Foundry account/project + Claude & GPT deployments; verify billing eligibility (leadership proposal now targets **one Azure/Foundry enterprise agreement** instead of two separate vendor accounts — Anthropic/OpenAI direct keys become fallback-only, a smaller ask).
3. Restaurant demo dataset + 3–4 restaurant tools: `pos.top_selling_items`, `pos.lagging_items`, `pos.sales_summary`, `inventory.reorder_candidates`. These are SQL queries wrapped as AI tools — the pattern already exists.

**Week 2 (by Jul 19) — analytics reports**
4. "Business Insights" report endpoint: SQL computes top/lagging sellers, sales by period, basic expense/income summary → cheap model writes the narrative → stored as `ai_suggestions` rows → simple frontend report card.
5. Restaurant-sector demo script end-to-end (this is the scheduled demonstration).

**Week 3 (by Jul 26) — recommender + hardening**
6. SQL co-occurrence recommender for e-commerce ("bought X also bought Y"), exposed as an endpoint the storefront can call. No LLM in the hot path.
7. Flip `AI_ENFORCE_PERMISSIONS=true`, add per-tenant daily token budget + kill switch, integration tests for the tool loop and router failover.
8. Technical write-up + marketing-deck inputs (generated from the working demo, not aspirationally).

### Explicitly deferred (say so at the next meeting)

- **Automated Excel data entry** — highest-risk feature (writes to books of account); needs draft/approval UX. Phase next. The `ai_suggestions` schema is ready for it, which is the honest good news.
- **Opt-in telemetry / regional analytics** — needs legal review (Uganda Data Protection Act / Kenya DPA), consent flows, and an aggregation pipeline. Not an MVP feature; a data-protection liability if rushed.
- **BYO API keys per tenant** — nice enterprise story, zero MVP value. Needs encrypted per-tenant key storage and validation UX.
- **Advertising analytics** — there is no ad-event data model in the ERP to analyze. Requires instrumentation first; scoping it now is premature.
- **Super-admin cross-tenant AI** — separate security context per the architecture doc; do not bolt onto tenant copilot.

---

## 4. Risks (Ranked)

1. **Azure Marketplace billing eligibility for our region** — could invalidate Foundry-primary. Verify first. Mitigation: direct APIs primary, Foundry secondary.
2. **Demo depends on realistic restaurant data** — seed a credible demo tenant early; analytics on empty tables demo nothing.
3. **Cost blowout** — no per-tenant budget or metering today; one chatty tenant on Sonnet burns real money. Router must log tokens per tenant from day one.
4. **Permission enforcement off by default** — any authenticated tenant user can invoke all tools. Must flip before any external demo.
5. **Repo divergence** (`alpha-erp-backend` vs `alphasoft-backend`) — pick the canonical clone this week.
6. **Test coverage ≈ 0 for the AI module** — the tool loop and router are exactly the code that fails weirdly in production.

## 5. Decisions Needed From Leadership

1. Approve Azure/Foundry enterprise account (replaces the two-vendor token proposal); direct Anthropic + OpenAI keys as fallback only.
2. Confirm MVP cut list above — specifically that Excel auto-entry, telemetry, and BYO keys slip past July.
3. Monthly AI spend ceiling per tenant (drives the budget/kill-switch defaults).

## 6. Useful ADK Sample References (ideas only — we are not adopting ADK for MVP)

- `customer-service`, `data-science` — tool-grounded analytics agent patterns.
- The invoice-processing style samples — reference for the deferred Excel/document extraction phase (matches `08-first-usecases.md` Phase 5).
- ADK-based runtime remains the Phase 2+ option already noted in `03-ai-module-architecture.md`; the Laravel tool layer stays the boundary either way.

---

## Sources

- [Deploy and use Claude models in Microsoft Foundry — Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/how-to/use-foundry-models-claude)
- [Introducing Anthropic's Claude models in Microsoft Foundry — Azure Blog](https://azure.microsoft.com/en-us/blog/introducing-anthropics-claude-models-in-microsoft-foundry-bringing-frontier-intelligence-to-azure/)
- [Model router for Microsoft Foundry — Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/openai/concepts/model-router)
- [Foundry Models from partners and community — Microsoft Learn](https://learn.microsoft.com/en-us/azure/foundry/foundry-models/concepts/models-from-partners)
- [Claude on Foundry starter kit — GitHub](https://github.com/Azure-Samples/claude#readme)
