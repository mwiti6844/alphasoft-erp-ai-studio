# Audit — Python Runtime Slice (2026-07-06, pre-demo)

Scope: the uncommitted work moving orchestration to the AI Studio Python runtime — `runtime/app` (610 lines), `PythonRuntimeAdapter` + `AiRuntimeToolController` in the backend, generative-UI events in the frontend. Demo in 4 days. Every finding below verified against the code, not the change summary.

## Verdict

The boundary design held: Python never touches a database, tools still execute in Laravel under the audited, permission-checkable registry, tool definitions offered to the model are filtered by Laravel per user+scope, and generative UI components are allow-listed on both sides (pydantic `extra="forbid"` in Python; five known types in `AiComponentRenderer`). The internal tool endpoint is well-built: timing-safe `hash_equals`, empty-secret rejection, session-ownership check, tenancy ended in `finally`.

Follow-up patch status: the four critical code defects are fixed in the working tree. The remaining demo blocker is data selection: a real tenant must pass the read-only backend readiness check before the first live run.

## Critical (fix before any live run)

**C1 — The runtime's `/api/chat` is unauthenticated and holds the shared secret.**
`app/routes/chat.py` accepts arbitrary `tenant_id`/`user_id`/`session_id` from any caller and relays them to Laravel with the valid `X-AI-RUNTIME-TOKEN`. Anyone who can reach port 8100 can act as any user of any tenant. This chains with `AI_ENFORCE_PERMISSIONS=false` (GAPS #1): with both as-is, a reachable runtime = run any tool against any tenant.
*Fix (small):* require the same shared-secret header on `/api/chat` and verify in a FastAPI dependency; bind uvicorn to 127.0.0.1 always; never port-forward 8100.
*Status:* fixed in `runtime/app/routes/chat.py`; Laravel now sends `X-AI-RUNTIME-TOKEN` to Python.

**C2 — `CORSMiddleware(allow_origins=["*"])` on the runtime.**
The runtime is server-to-server (Laravel is its only legitimate caller). A wildcard CORS grant invites the exact browser-origin access we must prevent, and amplifies C1.
*Fix (trivial):* delete the CORS middleware entirely.
*Status:* fixed. CORS is disabled by default and only enabled for explicit `CORS_ALLOWED_ORIGINS`.

**C3 — Default model was retired: `claude-sonnet-4-20250514`.**
Set in `runtime/app/config.py`, backend `config/ai.php` (`AI_PYTHON_MODEL` fallback), and listed in `AiModelRegistry`. Claude Sonnet 4 is retired on the direct Anthropic API (available only via Bedrock/Vertex). First live call with defaults will fail — likely mid-demo-prep.
*Fix (15 min):* default to a currently available Claude API model; update the registry map.
*Status:* fixed to `claude-sonnet-5`, which Anthropic's current model docs list as the Claude API ID for Sonnet 5.

**C4 — No conversation memory.**
`PythonRuntimeAdapter::callRuntime()` extracts only the latest message; `run_copilot` starts `messages = [{"role":"user","content":message}]` fresh each call. Every turn is amnesiac — "and what about last month?" will confuse the model in front of the team. The old `LaravelHttpAdapter` passed full history; this is a regression.
*Fix (~1 hr):* Laravel already holds the full message array — send it; accept `messages: list` in `ChatRequest`; seed `run_copilot` with it.
*Status:* fixed with tenant `ai_messages` persistence plus full-history passthrough to Python.

## High

**H1 — Streaming is now double-fake.** Laravel `Http::post` buffers the runtime's entire SSE body, and the runtime buffers the entire (synchronous) Anthropic response, then word-splits it. The user sees nothing until the whole turn finishes, then a fast replay — with an extra network hop added. Acceptable for the demo; do not describe it as streaming in the write-up. Real passthrough streaming is a post-demo task.

**H2 — Sync Anthropic client inside async FastAPI** blocks the event loop for the duration of each model call. Irrelevant single-user, breaks under concurrency. Post-demo: `anthropic.AsyncAnthropic`.

**H3 — Real tenant data is still the demo gate.** The synthetic restaurant seeder was removed for the "real-data direction," but no real tenant with 14+ days of completed `pos_transactions` has been named. Analytics tools over an empty table demo nothing — this is now the single biggest demo risk. *Decision needed today:* name a real tenant with adequate sales history and run `php artisan ai:demo-readiness <tenant-id> --days=14`. The command is read-only and fails if the tenant has too little completed POS activity.

**H4 — Laravel accepts the placeholder secret.** `AiRuntimeToolController` rejects an *empty* secret; it happily accepts `change-me-local` (the `.env.example` value) in production. Python guards production; Laravel doesn't. *Fix (small):* reject known-placeholder values + add a production check; add `throttle` middleware to the internal route. *Status:* fixed; placeholder secrets are rejected and the internal route has `throttle:60,1`.

**H5 — Verify token accounting survives the hop.** Usage travels as a `trace` event and is folded back by `resultFromEvents`; confirm `AiSessionService::recordTurn` still receives real token counts under the python adapter (one integration test). Budgets (GAPS #3) will sit on these numbers.

## Medium / notes

- Master-plan contradiction, acknowledged: `ai-planning/11` §3 said the runtime must "earn its way in" and ships Phase C. It arrived in Phase A. The direction is fine *if* we accept the extra moving part at demo time (two processes + a key instead of one). §3's rule should be amended to reflect reality rather than silently violated.
- Follow-up suggestions are hardcoded every turn (`copilot.py`) — fine as demo sugar; make data-driven later.
- `run_copilot` return annotation says `Iterator[object]` for an async generator; cosmetic.
- New `httpx.AsyncClient` per tool call — fine at demo scale.
- Frontend: `pos` scope option added to `AiPanel`; renderer handles exactly the five allow-listed component types; targeted TS checks clean (full repo typecheck fails on pre-existing unrelated issues).
- Eval fixtures in `evals/pos-analytics.golden.yaml` match the implemented tool names — they remain the acceptance spec; the future harness should exercise the python path.

## Four-day execution plan

**Today (Day 0) — config + safety, ~half day of small fixes:** C3 model id → C4 history passthrough → C1 auth on `/api/chat` + localhost bind → C2 remove CORS → H4 placeholder-secret rejection. Then set real secrets (`runtime/.env`, backend `.env`) and run the first live end-to-end smoke test: browser → Laravel → runtime → Anthropic → Laravel tool → component render.

**Day 1 — data + demo script:** resolve H3 (real tenant or restored demo seeder); run the six `pos-analytics` golden questions manually against the live stack; fix whatever breaks; decide `AI_ENFORCE_PERMISSIONS` for the demo (flip on if role mapping fits in the day; otherwise demo on an internal tenant only and say so).

**Day 2 — dry run #1 + backup:** full scripted rehearsal (restaurant questions + component renders + follow-up chips); record a screen capture as the fallback; H5 token-accounting check.

**Day 3 — dry run #2 + freeze:** second rehearsal, then freeze — no code changes after it passes twice. Prepare the one-command startup (Laravel, queue, uvicorn, frontend) so demo-day setup is boring.

**Explicitly deferred past demo:** real streaming (H1), async client (H2), budgets/metering, module registration decoupling (GAPS #13), prompt sync (`copilot.py` now has a *second* divergent system prompt — reconcile with `prompts/copilot-system-v1.md` after the demo), Foundry endpoint switch, WP1/WP2 router.

## Commit plan (when cleared to commit)

Backend: (1) POS analytics tools + tests; (2) internal runtime endpoint + adapter + config. Frontend: (3) generative UI events + renderer + pos scope. AI repo: (4) runtime service; (5) this audit + plan docs. Small, revertable, in that order.
