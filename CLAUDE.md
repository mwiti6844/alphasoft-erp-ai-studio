# CLAUDE.md — AlphaSoft AI Workstream (agent session instructions)

You are working on the AI layer of AlphaSoft ERP. This repo (`alphasoft-erp-ai-studio`) is the AI home: planning docs, prompts, evals, contracts, and (Phase C) a Python agent runtime. The code you will usually edit lives in the other two repos.

- **Architecture & narrative:** read `PROJECT.md` (what this is, how a copilot request flows, critical paths, surprises).
- **Known issues, ordered by severity, each with a scoped fix:** read `GAPS.md` before "improving" anything — it may already be diagnosed.
- **Direction & roadmap:** `ai-planning/11-ai-platform-master-plan.md` (umbrella), `10-ai-mvp-work-packets.md` (current sprint tasks WP1–WP11), `09` (provider strategy), `01/03/08` (vision, architecture, use cases).

## Repo map (paths on this machine)

| Repo | Path | You edit… |
|---|---|---|
| Backend (canonical) | `/Users/mac/Desktop/alphasoft-backend/alphasoft-backend` | `app-modules/ai/**`, module `config/permissions.php`, tests |
| Frontend | `/Users/mac/Desktop/alpaerpfrontend-1` | `src/components/ai/**`, `src/lib/ai/**`, `/ai` pages |
| AI repo (this) | `/Users/mac/Desktop/alphasoft-erp-ai-studio` | docs, `prompts/`, `evals/`, `contracts/`, later `runtime/` |
| ADK samples | `/Users/mac/Desktop/adk-samples` | never — reference only |

**Read the backend's `AGENTS.md` at session start when working there** — it holds binding house rules (UI conventions, tenancy rules, test-DB policy) learned over months. Do not contradict it.

## Commands

Backend (run from the backend repo root):
```bash
composer install                     # deps
php artisan test                     # full suite (sqlite :memory:, isolated per test)
php artisan test --filter=Ai         # AI module tests only
vendor/bin/pint                      # code style (Laravel Pint) — run before committing
composer dev                         # serve + queue + logs + vite concurrently
php artisan migrate --force          # central; tenant migrations run via tenancy
```
Frontend:
```bash
npm install && npm run dev           # dev server
npm run build && npm run lint        # verify before commit
```
This repo: no build yet. Markdown only. When `runtime/` exists: `uv sync && pytest` (to be confirmed).

## Conventions that are binding

- **Tenancy is sacred.** All AI routes sit behind `InitializeTenancyByDomain` + `auth:sanctum`. Never query tenant models outside tenancy context; never mix central and tenant permissions.
- **Tools are the only data access.** A tool = class implementing `AiToolContract` (`name`, `moduleScope`, `permission` triple, `definition` JSON schema, `execute`). Names are `snake_case`, scoped per module. Output = minimal fields only, never customer PII (aggregates, item names, totals). Register in `AiToolRegistry` (currently a hardcoded const — see GAPS #13).
- **Permissions:** every tool declares `['module','resource','action']` matching the module's `config/permissions.php`. Never invent permissions inline.
- **AI writes go through `ai_suggestions`** (draft → human review → apply). No AI code path may mutate ERP data directly. No exceptions.
- **SQL computes, models narrate.** Never let the LLM produce business figures; compute in queries, pass figures in, assert narrative numbers ⊆ payload.
- **Model tiering:** Haiku-class for volume/narration, Sonnet-class for copilot/tool-use, no premium models, no LLM where SQL suffices (recommender = SQL co-occurrence).
- **Errors are user-visible.** Never silently swallow AI/provider failures into empty panels (house rule). Emit a clear SSE error event / JSON message.
- **Tests:** new tool ⇒ unit test with fixtures; new endpoint ⇒ feature test; use `tests/Concerns/*` helpers; destructive tests only on the isolated test DB (enforced by `TEST_DB_ISOLATED`). Update module journey docs in backend `docs/` when scope changes.
- **Prompts are code:** copilot system prompt changes go through this repo's `prompts/` with a changelog entry (structure may need creating — see GAPS #10), then sync `AiSystemPromptBuilder`.

## Gotchas (things that look right but aren't)

1. `AI_RUNTIME_ADAPTER=python` does **nothing** — it binds `LaravelHttpAdapter` (placeholder). The real Python runtime doesn't exist yet (Phase C).
2. Choosing any `gpt-*`/groq/gemini model **throws** in `resolveProvider()` despite the registry mapping them. Fix path = WP1/WP2, not a registry tweak.
3. `AI_ENFORCE_PERMISSIONS` defaults **false** — tools open to all tenant users. Flipping it will break the Phase-0 test that asserts the permissive behavior; update the test too.
4. SSE "streaming" is simulated (blocking provider call, deltas replayed afterward). `supportsStreaming()` lies. Don't design UX assuming true token streaming.
5. Unknown model ids silently route to Anthropic — typos surface as vendor 404s, not local errors.
6. Backend repo root is **nested**: `alphasoft-backend/alphasoft-backend/`.
7. **Push to `main` auto-deploys to production** (`deploy-production.yml`). Never push/merge to main casually; prefer feature branches + PRs. (See GAPS #4.)
8. `.env.backup` in the backend root is the recovered legacy env (May 2026) — may be stale, contains real credentials, is gitignored. Never rename it to something unignored; never commit env-like files.
9. `max_tokens` default is 1024 — override per call for reports; don't raise globally.
10. Frontend calls Laravel directly (`tenantFetch`); do **not** add Next.js API proxy routes for CRUD or AI.

## Never change without care

- `AiToolRegistry::dispatch` (permission gate + audit) and `LaravelHttpAdapter::runConversation` (agent loop) — critical paths, no direct tests yet; add tests with any change.
- Tenancy middleware stacks on any route file.
- Module `config/permissions.php` role blocks.
- `ai_sessions` / `ai_tool_calls` / `ai_suggestions` migrations — additive changes only; tenant DBs are live.
- `.github/workflows/deploy-production.yml` — it deploys production.
- Anything in `adk-samples/` — read-only reference.

## Current priorities (July 2026)

Work the packets in `ai-planning/10-ai-mvp-work-packets.md` in order: WP1 `OpenAiHttpProvider` → WP2 `AiProviderRouter` (Foundry primary, direct fallback, metering) ∥ WP4 restaurant/retail analytics tools → WP5 demo seeder → WP6 insights report → WP7 report UI → WP9 SQL recommender → WP10 hardening (enforcement ON, budgets, tests). GAPS.md items #1–#3 are the non-negotiables before launch.
