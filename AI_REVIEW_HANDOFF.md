# AI Integration Review Handoff

## Summary

This repo contains the AI Studio runtime and AI planning/contracts. The runtime is now a FastAPI orchestration service with provider-neutral LLM support, module routers, structured suggestions, flow-knowledge retrieval, Docker packaging, and tests.

Nothing in this repo should connect directly to tenant databases. Laravel remains the only executor for tenant data and tools.

## Architecture Boundary

- **Laravel owns:** tenant data, auth, tenancy, permissions, tool execution, persistence, audit, business writes.
- **Python runtime owns:** orchestration, module routing, model calls, deterministic follow-ups, component proposals, flow-resource retrieval.
- **Frontend owns:** rendering allow-listed components and sending chat/suggestion actions through Laravel only.

## Main Runtime Changes

- Provider-neutral LLM layer with Groq and Anthropic providers.
- `pos`, `inventory`, and `catalog` module routers.
- Structured suggestion action support via `ui_action`.
- Inventory generative UI component contracts.
- Long-term user memory snapshot consumption as read-only prompt preferences.
- Flow knowledge retrieval from `contracts/flows/*.yaml`.
- `flow_citations` component for cited ERP process answers.
- Dockerfile and `docker-compose.ai.yml` for the FastAPI runtime.

## Contracts / Planning Artifacts

- `contracts/flows/` — curated ERP flow resources.
- `contracts/ai-followup-suggestion.schema.json` — structured chip/action schema.
- `evals/inventory/` — inventory behavior fixtures.
- `ai-planning/19-22` — chat/memory/agent flow, thread UX, inventory integration, long-term memory notes.

## Config / Env

Runtime provider is selected by env:

- `AI_PROVIDER=groq|anthropic`
- `GROQ_API_KEY` or `ANTHROPIC_API_KEY`
- `LARAVEL_INTERNAL_URL`
- `AI_RUNTIME_SHARED_SECRET`

For Docker:

```bash
docker compose -f docker-compose.ai.yml up --build
```

## Verification Run

- `cd runtime && .venv/bin/python -m pytest tests -q` — passed, `89 passed`
- Frontend build was run in the frontend repo — passed
- Backend AI suite was run in the backend repo — passed, `64 passed (290 assertions)`
- Docker build passed: `docker build -f runtime/Dockerfile -t alphasoft-ai-runtime:flow-knowledge .`
- Container flow-resource load check returned `8`

## Review Focus

- Runtime stays orchestration-only.
- Prompt/resource boundaries are clear.
- Flow retrieval should cite only curated resources and not invent screens.
- Docker image includes flow resources but excludes secrets/tests/dev artifacts.

## Known Gaps

- Live browser-to-Laravel-to-runtime-to-Groq smoke against a real tenant is still pending.
- Pipeline is buffered; do not claim true token streaming yet.
- Memory settings UI is deferred to frontend/backend follow-up.
