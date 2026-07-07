# AI MVP Work Packets — Claude Code / Codex Execution Plan

Companion to `09-ai-provider-strategy-and-mvp-plan.md`. One packet ≈ one agent session ≈ one branch ≈ one PR you review. Target: end-of-July MVP, restaurant demo mid-July.

## Operating Rules (read before dispatching agents)

1. **Canonical repo first.** Pick `alphasoft-backend/alphasoft-backend` (it's ahead) or reconcile into `alpha-erp-backend`. Do this before any agent writes a line — two agents on two divergent clones of the same repo is unrecoverable churn.
2. **One agent per repo at a time.** Backend packets serialize where they share files (`config/ai.php`, `AiServiceProvider`). Frontend packets run in parallel with backend safely. Use git worktrees or branches per packet.
3. **Max 2 concurrent agents.** You review everything; a queue of unreviewed agent PRs is debt, not progress.
4. **Agents never touch secrets.** You create Foundry deployments and put keys in `.env` yourself. Agents get interface contracts, not credentials.
5. **Shared instructions file.** Your repo already has a rich `AGENTS.md` (Codex reads it natively). Symlink or copy it as `CLAUDE.md` so Claude Code gets the same rules. Add the AI-module conventions from this doc to it once, instead of repeating them per prompt.
6. **Tests-first prompts.** Every packet's prompt ends with: "Write the tests first, run them failing, then implement. Use the dedicated test DB config — never the dev database." (This is already a learned rule in AGENTS.md; agents comply better when it's re-stated in the task.)
7. **Definition of done** for every packet: tests pass, `AGENTS.md`/docs updated if conventions changed, no unrelated file churn in the diff.

---

## Day 0 — Human Tasks (you, not agents, ~half a day)

- [ ] **H1.** Verify Azure Marketplace billing eligibility for your billing country (Kenya/Uganda) for Anthropic models. This decides whether Foundry is primary or fallback. Blocks nothing in code (router is endpoint-agnostic) but blocks the leadership proposal.
- [ ] **H2.** Choose canonical backend repo; archive the other. Announce to team.
- [ ] **H3.** Create Foundry project + deploy one Claude model and one GPT model (East US2 or Sweden Central). Capture: base URLs, deployment names, keys. Also get direct Anthropic + OpenAI keys (fallback endpoints).
- [ ] **H4.** Decide demo tenant story: restaurant name, menu (~40 items), 60–90 days of synthetic sales history shape (peak hours, weekend lift, 3–4 lagging dishes). WP5's agent needs this narrative from you — agents invent unconvincing data unprompted.

---

## Week 1 — Provider Plumbing + Demo Foundation

### WP1 — `OpenAiHttpProvider` (backend, serial-1)

**Spec:** New `src/Services/Providers/OpenAiHttpProvider.php` implementing `AiProviderInterface`. Chat Completions API with tool calling; translate the module's tool schema to OpenAI `tools` format and map responses back into `AiProviderResponse` (content blocks + `stop_reason` semantics matching what `LaravelHttpAdapter::runConversation()` expects — study how `AnthropicHttpProvider` and `AiProviderResponse::toolUses()` interact first). Configurable `base_url` so the same class serves openai.com and Azure/Foundry GPT deployments (note: Azure uses `api-key` header and deployment-name-in-path or model param — support both via endpoint config).
**Acceptance:** unit tests for tool translation both directions; a stubbed-HTTP test walking one tool-use round trip; selecting `gpt-4o-mini` in a session no longer throws.
**Agent fit:** ideal first Codex/Claude Code task — isolated, contract-driven.

### WP2 — `AiProviderRouter` + endpoint config (backend, serial-2, after WP1)

**Spec:** `config/ai.php` restructure: named `endpoints` (`foundry_anthropic`, `anthropic_direct`, `foundry_openai`, `openai_direct`) each with `base_url`, `auth_mode` (`x-api-key` | `api-key` | `bearer`), `api_key` env var; `routing_profiles` (e.g. `default`, `cheap_bulk`) as ordered endpoint lists. New `AiProviderRouter` implementing `AiProviderInterface`: walks the profile chain, fails over on 429/5xx/timeout/auth errors, simple circuit breaker (cache-based, skip endpoint N minutes after M consecutive failures), logs `{endpoint, model, input_tokens, output_tokens, tenant}` per call. `LaravelHttpAdapter::resolveProvider()` now returns the router. Keep backward compat: if only `AI_ANTHROPIC_KEY` is set, behave exactly as today.
**Acceptance:** failover test (first endpoint 500s → second succeeds), circuit-breaker test, token-log assertion, existing chat flow green.
**Note:** this touches `AiServiceProvider` and config — do not run concurrently with WP1 or WP3.

### WP3 — Foundry auth support in `AnthropicHttpProvider` (backend, small, can fold into WP2)

**Spec:** Parameterize auth header per endpoint (`x-api-key` for direct, Foundry per its docs) and accept deployment-name-as-model. Likely ~30 lines. Fold into WP2's session if the agent is doing well; separate PR if not.

### WP4 — Restaurant analytics tools (backend, parallel with WP1 — different files)

**Spec:** Four new read-only tools following the existing pattern (`CatalogSearchTool` et al.): `pos.top_selling_items`, `pos.lagging_items`, `pos.sales_summary` (period-over-period), `inventory.reorder_candidates`. Pure SQL/Eloquent aggregation over POS sale lines; parameters: date range, branch, limit; outputs: compact structured rows (tool responses minimal and task-specific — architecture doc rule). Register in `AiToolRegistry` under a `pos` module scope; add `pos` to enabled-modules default. Each tool declares its required permission.
**Acceptance:** unit tests per tool against seeded fixtures; tool appears in registry for a `pos`-scoped session; permission denied path tested.
**Agent fit:** great parallel packet — zero overlap with provider files.

### WP5 — Demo tenant seeder (backend, parallel, after H4)

**Spec:** Seeder/command `php artisan demo:restaurant-tenant` creating the H4 narrative: menu, 60–90 days of sales with realistic peaks, a few lagging items, inventory levels that make `reorder_candidates` return something interesting. Idempotent, dev/demo environments only, hard-refuses to run in production.
**Acceptance:** run twice → no duplicates; WP4 tools return demo-plausible answers against it.

**Gate ✋ end of Week 1:** you manually run the copilot against the demo tenant through Foundry and direct endpoints, kill one endpoint, watch failover. Do not proceed to Week 2 until this works — everything after builds on it.

---

## Week 2 — Analytics Reports + Demo

### WP6 — Business Insights report (backend, serial)

**Spec:** `POST /api/v1/tenant/ai/reports/business-insights` (+ list/show). Pipeline: SQL aggregations compute the figures (reuse WP4 query logic via shared query classes — do not duplicate SQL in two places) → cheap-model routing profile narrates → persist as `ai_suggestions` row (`suggestion_type=insight_report`, payload = figures + narrative + period). The LLM never computes numbers; it receives them. Queued job, not inline request.
**Acceptance:** report generates against demo tenant; narrative references only figures present in payload (assert numbers in text ⊆ payload figures — cheap hallucination guard); tokens logged.

### WP7 — Frontend report card + copilot polish (frontend repo, parallel with WP6)

**Spec:** In `alpaerpfrontend-1`: insights report page (card layout: headline figures, narrative, "generated by AI" label, regenerate button), wire to WP6 endpoints via existing `tenantFetch` pattern; surface tool-call badges for the new `pos.*` tools in `AiPanel`. Follow AGENTS.md UI rules (permission-gated nav, no silent 403s).
**Acceptance:** renders against local backend with demo tenant; loading/error/empty states; no new BFF proxy routes.

### WP8 — Demo dry run (you + one agent for fixes)

Script the demo: 5 copilot questions + 1 insights report, run it twice, file whatever breaks as micro-tasks. Record a backup screen capture — live demos fail.

---

## Week 3 — Recommender + Hardening

### WP9 — Co-occurrence recommender (backend, parallel)

**Spec:** Nightly job computing item-pair co-occurrence from sale lines into a `recommendation_pairs` table (tenant-scoped, min-support threshold); endpoint `GET /api/v1/tenant/catalog/items/{id}/recommendations` with popularity fallback for cold-start items. Pure SQL — no LLM calls anywhere in this packet.
**Acceptance:** deterministic fixtures test (known baskets → known pairs); cold-start fallback test; p95 endpoint latency trivial (indexed lookup).

### WP10 — Hardening (backend, serial, last)

**Spec:** Default `AI_ENFORCE_PERMISSIONS=true` (fix whatever breaks — the tools declare permissions; seed the roles); per-tenant daily token budget in config + enforcement in router (429-style refusal with clear message per AGENTS.md error rules); tenant-level AI kill switch; integration tests: full tool loop, router failover, budget exhaustion, permission denial.
**Acceptance:** all green; budget breach shows a user-visible message, not a silent empty panel.

### WP11 — Write-ups (you + agent draft)

Technical write-up + marketing-deck inputs generated from the *working* system: real screenshots, real report output. Agent drafts from the repo docs; you edit for accuracy.

---

## Claude Code vs Codex — honest division

Don't split by "which model is smarter" — split by **workflow friction**:

- **Backend (Laravel) packets → Claude Code**, mainly because your AGENTS.md conventions are dense and behavioral, and you'll be iterating conversationally on review feedback. Keep one long-lived session per packet.
- **Frontend packets and parallel second tracks → Codex** (or the reverse — the real rule is *one tool per repo per moment* so you never get two agents mid-flight in the same worktree).
- **Both read the same instructions:** maintain `AGENTS.md` as source of truth, mirror to `CLAUDE.md`.
- Whichever you use, the prompt is the packet spec above + "tests first, dedicated test DB, small diff."

## Sequencing Summary

```txt
Day 0:   H1 H2 H3 H4 (you)
Wk1:     WP1 → WP2(+WP3)   ∥   WP4 → WP5     → GATE: failover demo
Wk2:     WP6               ∥   WP7           → WP8 dry run
Wk3:     WP9               ∥   WP10 → WP11   → launch
```

Slack in the plan: none. If a packet slips, cut WP9 (recommender) first — the storefront isn't demo-critical; the restaurant demo and hardening are.
