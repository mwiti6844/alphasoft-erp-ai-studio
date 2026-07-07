# GAPS.md — Honest Audit of the AI Workstream

> Written 2026-07-06 after a deep review. Ordered by severity, worst first.
> Paths are relative to `alphasoft-backend/alphasoft-backend/` unless another repo is named.
> Each item ends with a **Fix** scoped small enough to be a single agent task.

---

## 1. Any authenticated tenant user can run every AI tool (permission enforcement off)

**What:** `config/ai.php` sets `enforce_permissions` from `AI_ENFORCE_PERMISSIONS` with default `false`. `AiToolRegistry` then skips `userCanRunTool()` entirely. The feature test `tests/Feature/Ai/AiCopilotPhase0Test.php::test_tools_available_without_erp_permissions_when_enforcement_disabled` codifies the unsafe default as expected behavior.
**Where:** `config/ai.php` (~line 38), `app-modules/ai/src/Services/AiToolRegistry.php`.
**Why it matters:** a register-only cashier can query warehouse balances and catalog economics through the copilot. Violates the product's own trust model (`ai-planning/01-product-vision.md`) and the house rule "gate ERP nav and actions by permission."
**Severity: CRITICAL (before any external demo/launch).**
**Fix (single task):** default `enforce_permissions` to `true`; add the AI-tool permission triples to the relevant module `config/permissions.php` role blocks; update the Phase-0 test to assert the *enforced* behavior and add one denial-path feature test.

## 2. Selecting any non-Anthropic model crashes the chat

**What:** `AiModelRegistry` maps `gpt-*`→openai, groq, gemini; `LaravelHttpAdapter::resolveProvider()` (line ~197) throws for anything but `'anthropic'`. There is no fallback, no retry, no graceful error to the user.
**Where:** `app-modules/ai/src/Services/Adapters/LaravelHttpAdapter.php`, `app-modules/ai/src/Services/AiModelRegistry.php`.
**Why it matters:** the whole multi-model/Foundry strategy (approved direction) is unimplementable until this seam is real; a stray model id in a session row 500s the endpoint.
**Severity: CRITICAL (blocks the provider strategy).**
**Fix:** two sequenced tasks already specced as WP1 (`OpenAiHttpProvider`) and WP2 (`AiProviderRouter` with failover + metering) in `ai-planning/10-ai-mvp-work-packets.md`. If only one small task is possible now: catch the exception in the controller and return a 422 with a clear message.

## 3. No spend controls: token counts recorded, never limited

**What:** `AiSessionService::recordTurn()` tallies tokens per session, but nothing enforces a per-tenant or per-day ceiling, and there is no per-tenant cost attribution or kill switch. The payment proposal promises leadership a "$10/tenant/day cap with automatic cutoff" that does not exist in code.
**Where:** `app-modules/ai/src/Services/AiSessionService.php`; absence in `LaravelHttpAdapter` / middleware.
**Why it matters:** one scripted client hammering the chat endpoint spends real money with no brake. The org's financial approval is premised on this control existing.
**Severity: HIGH.**
**Fix (single task):** daily per-tenant token budget in `config/ai.php`; check + increment a cache/DB counter in `AiCopilotController::chat` before invoking the adapter; return a clear user-visible "AI budget reached" message (house rule: never silent failures); one feature test for the exhaustion path.

## 4. Pushing to `main` deploys straight to production — dangerous with coding agents

**What:** `.github/workflows/deploy-production.yml` triggers on push to `main`, `production`, `prod` and deploys to the VPS.
**Where:** backend `.github/workflows/deploy-production.yml`.
**Why it matters:** the team now works with Claude Code/Codex agents making frequent commits. One agent merge to main = an unreviewed production deploy of a financial system.
**Severity: HIGH (process, cheap to fix).**
**Fix (single task):** restrict the trigger to `production` only (or add `workflow_dispatch`-gated approval / GitHub environment protection); document "main is not production" in the repo README/AGENTS.md.

## 5. The AI module is effectively untested

**What:** exactly two AI tests exist: `AiCopilotPhase0Test` (stub adapter only — session lifecycle + audit rows) and `AnthropicToolSchemaTest` (schema normalization). Untested critical paths: the entire `LaravelHttpAdapter` tool loop (iteration cap, tool-result threading, token accumulation), `AnthropicHttpProvider` payload/response mapping, `AiToolRegistry::dispatch` permission-denial and unknown-tool paths, all five tools' `execute()` against fixtures, SSE emission, `AiSessionService::recordTurn`.
**Where:** `tests/Feature/Ai/`, `tests/Unit/Ai/` vs `app-modules/ai/src/**` (28 files). Compare: POS has 22 test files.
**Why it matters:** the agentic loop is exactly the code that fails weirdly (infinite tool loops, dropped results, mis-threaded conversations), and it will be modified heavily during WP1–WP10.
**Severity: HIGH.**
**Fix (series of small tasks, one per class):** start with `LaravelHttpAdapterTest` using a fake `AiProviderInterface` that scripts `tool_use` → `end_turn` sequences; then one unit test per tool with seeded fixtures; then a permission-denial feature test.

## 6. Secrets hygiene around recovered `.env` (mitigated 2026-07-06, verify)

**What:** during the old-repo retirement, its `.env` was copied into the backend as `.env.from-alpha-erp-backend-2026-05-24` — a filename **not** covered by `.gitignore` (which lists only `.env`, `.env.backup`, `.env.production`). One `git add -A` away from committing credentials. It was renamed to `.env.backup` (gitignored) and the settings copy to `*.bak` (now gitignored) on 2026-07-06.
**Where:** backend repo root; `.gitignore` lines 3–5.
**Why it matters:** APP_KEY/DB/API credentials in git history are a permanent leak requiring rotation.
**Severity: HIGH at discovery; now LOW residual.**
**Fix (single task):** verify `git status` is clean of env-like files; rotate any credentials in `.env.backup` that are still live if the file ever left the machine; consider adding `.env.*` (with `!.env.example`) to `.gitignore`.

## 7. Streaming is simulated, and the abstraction misreports it

**What:** `AnthropicHttpProvider::supportsStreaming()` returns `true`, but `chat()` is a blocking POST; `LaravelHttpAdapter::streamTextDeltas()` fakes deltas by chunking the finished text on sentence boundaries.
**Where:** `app-modules/ai/src/Services/Providers/AnthropicHttpProvider.php`, `LaravelHttpAdapter.php` (~line 205).
**Why it matters:** users stare at a spinner for the full model latency (worst on long reports), and the misleading `supportsStreaming()` will confuse anyone implementing the router or a second provider.
**Severity: MEDIUM (UX + honesty of the abstraction).**
**Fix (single task, choose one):** either flip `supportsStreaming()` to `false` and document simulated deltas, or implement real SSE passthrough from Anthropic's `stream: true` API in the provider (bigger; do after WP2).

## 8. `'python'` runtime adapter silently binds `LaravelHttpAdapter`

**What:** `AiServiceProvider::register()` maps `'python' => LaravelHttpAdapter::class` with no warning.
**Where:** `app-modules/ai/src/Providers/AiServiceProvider.php` (~line 21).
**Why it matters:** an operator setting `AI_RUNTIME_ADAPTER=python` believes they switched runtimes; nothing changed. Placeholder config values that "work" hide real state.
**Severity: MEDIUM.**
**Fix (single task):** throw a descriptive exception for `'python'` until the runtime exists ("Python runtime not implemented; see ai-planning/11 §3"), or log a loud warning and fall back.

## 9. Unknown model ids silently default to Anthropic

**What:** `AiModelRegistry::providerForModel()` returns `'anthropic'` for anything unrecognized.
**Where:** `app-modules/ai/src/Services/AiModelRegistry.php` (final return).
**Why it matters:** a typo'd model id is sent verbatim to Anthropic's API, producing a confusing vendor-side 404 instead of a clear local error; with the future router it could silently route to the wrong (more expensive) endpoint.
**Severity: MEDIUM-LOW.**
**Fix (single task):** throw `InvalidArgumentException("Unknown model id ...")` on no match; add the allowed-models list to `config/ai.php`; one unit test.

## 10. System prompt is an inline heredoc in PHP, unversioned

**What:** the copilot's entire behavioral contract lives in `AiSystemPromptBuilder::build()` as a heredoc. No versioning, no changelog, no eval before change. The master plan (`ai-planning/11` §7) requires prompts to live in this repo's `prompts/` with releases — that structure doesn't exist yet.
**Where:** `app-modules/ai/src/Services/AiSystemPromptBuilder.php`; missing `alphasoft-erp-ai-studio/prompts/`.
**Why it matters:** prompt edits are the highest-frequency, lowest-visibility behavior changes in an AI product; untracked edits make regressions undiagnosable.
**Severity: MEDIUM.**
**Fix (single task):** create `prompts/copilot-system-v1.md` in this repo mirroring the current prompt + a CHANGELOG; make the builder load from a published config path with the heredoc as fallback.

## 11. `ai_suggestions` is a table without a feature (half-finished work)

**What:** model + migration + resource exist (`AiSuggestion`, full status workflow columns), but there are no endpoints, no UI, and nothing writes to it. It is the designated write path for insights reports (WP6), Excel extraction (Phase B), and every future draft action.
**Where:** `app-modules/ai/src/Models/AiSuggestion.php`, migration `2026_06_03_100200`, `Http/Resources/`.
**Why it matters:** three roadmap features assume this flow; it silently rotting means each will improvise its own.
**Severity: MEDIUM (by design "pending", but flag it).**
**Fix:** WP6 makes insights reports write suggestions; Phase B item 1 builds review/apply endpoints + `/ai/approvals` UI. Do not build any AI write feature that bypasses it.

## 12. No retry/backoff/timeout strategy on the provider call

**What:** `AnthropicHttpProvider::chat()` is a single `Http::post` with a 120s timeout; any 429/5xx throws `RuntimeException` straight up the stack to the user.
**Where:** `app-modules/ai/src/Services/Providers/AnthropicHttpProvider.php` (~line 55).
**Why it matters:** transient vendor blips become user-facing errors; 120s ties up a PHP-FPM worker per stuck request.
**Severity: MEDIUM (subsumed by WP2's router, which owns failover).**
**Fix (single task if done before WP2):** wrap with 2 retries + exponential backoff on 429/5xx, drop timeout to ~60s, and map failures to a friendly error event on the SSE stream.

## 13. Registry/tool list is hardcoded; module scopes are strings

**What:** `AiToolRegistry::TOOL_CLASSES` is a hand-maintained const; `enabled_modules` in config and `moduleScope()` strings must agree by convention. Adding a module's tool pack means editing the AI module — the opposite of the "inheritance contract" in `ai-planning/11` §1.
**Where:** `app-modules/ai/src/Services/AiToolRegistry.php` (~line 20).
**Why it matters:** POS tools (WP4) and every future vertical compound the coupling; a typo'd scope string fails silently (tools just don't appear).
**Severity: LOW-MEDIUM.**
**Fix (single task):** let modules register tools via their own service providers (tagged bindings, e.g. `$this->app->tag([...], 'ai.tools')`), registry collects the tag; keep the const as fallback during migration; validate scopes against `enabled_modules` at boot.

## 14. Minor consistency and hygiene items

- **Stray test artifacts committed:** `database/tenantmail_test_co_*` directories in the backend look like leaked per-test SQLite state. *Fix:* delete + gitignore the pattern.
- **`LIKE '%term%'` search** in `CatalogSearchTool` is unindexable; fine at pilot scale, will degrade on large catalogs. *Fix later:* prefix-match or FULLTEXT when a tenant exceeds ~50k items.
- **`max_tokens` default 1024** truncates long narratives (reports). *Fix:* per-call override in the insights pipeline (WP6), not a global raise.
- **Naming drift:** repo folder `alpaerpfrontend-1` (typo'd, versioned name) vs docs saying `alpaerpfrontend`; Postman collection still named `alpha-erp-backend.postman_collection.json`. *Fix:* cosmetic; align when convenient.
- **`AGENTS.md` exists only in the backend;** the frontend and this repo have no agent instruction files. *Fix:* this repo now has `CLAUDE.md`; consider a frontend one.
- **This repo has no CI** and none of the planned `contracts/`, `evals/`, `prompts/` directories yet (see `ai-planning/11` §3). *Fix:* create the skeleton with a lint check for planning docs as the first workflow.

---

## Top 3 (if you only fix three things)

1. **#1 permission enforcement** — flip it, map the permissions, fix the test. Security posture of the whole AI layer.
2. **#2 provider seam** — WP1 + WP2. Everything strategic (Foundry, failover, metering, budgets) sits behind it.
3. **#3 spend controls** — leadership approved money on the premise this exists. Make the premise true before the pilot.
