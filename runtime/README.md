# runtime/

Python FastAPI agent runtime for AlphaSoft ERP AI Studio.

This service owns orchestration only. Laravel remains the only door to tenant
data, permissions, tool execution, sessions, audit logs, and suggestions.

## Current Slice

The first runnable slice is a POS analytics copilot:

- `POST /api/chat`
- SSE events: `token`, `tool`, `trace`, `component`, `state_patch`, `error`, `done`
- Calls Laravel internal AI tool endpoint for ERP data
- Emits allow-listed generative UI components for POS analytics
- Requires `X-AI-RUNTIME-TOKEN` on chat requests
- Requires an API key for the selected provider (see Providers)

## Providers

The LLM backend is selected at startup via `AI_PROVIDER` (`groq` or
`anthropic`). Startup fails loudly if the selected provider's key is missing
or `AI_PROVIDER` is unknown.

- `AI_PROVIDER=groq` — `GROQ_API_KEY` required; `GROQ_MODEL` picks the model
  (default `llama-3.3-70b-versatile`; use a tool-capable model from
  https://console.groq.com/docs/models); `GROQ_BASE_URL` defaults to Groq's
  OpenAI-compatible endpoint.
- `AI_PROVIDER=anthropic` — `ANTHROPIC_API_KEY` required; `ANTHROPIC_MODEL`
  defaults to `claude-sonnet-5`.

Providers implement the neutral interface in `app/llm/provider.py` and
translate to/from the shapes in `app/llm/types.py` at their own boundary —
no vendor message format leaks into the agent loop. Rollback is an env flip.

Laravel's `AI_PYTHON_MODEL` is display-only; keep it mirrored to the model
configured here.

## Run

```bash
cd runtime
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8100
```

`CORS_ALLOWED_ORIGINS` is empty by default because Laravel is the only normal
caller. Add explicit origins only for a controlled local browser test.

Before a live demo, point Laravel at a real tenant and run:

```bash
php artisan ai:demo-readiness <tenant-id> --days=14
```

That command is read-only. It does not seed or fabricate data.

## Test

```bash
pip install -r requirements-dev.txt
python -m pytest tests -q
```

## Docker

The runtime ships with a production-oriented `Dockerfile` (Python 3.12 slim,
non-root user, prod deps only — no tests, `.env`, `.venv`, or caches in the
image).

### Build

```bash
docker build -t alphasoft-ai-runtime ./runtime
```

### Compose

For a minimal AI-runtime-only Compose run from the repo root:

```bash
cp runtime/.env.example runtime/.env
# edit runtime/.env with AI_PROVIDER, provider key, Laravel URL, and shared secret
docker compose -f docker-compose.ai.yml up --build
```

This Compose file intentionally starts only the FastAPI runtime. It does not
start Laravel, queues, databases, Redis, or the frontend. For production,
deployment may remove the published port and expose the container only on the
private network used by Laravel. The local Compose file does not set a restart
policy so missing or invalid env vars fail once with a clear startup error
instead of looping.

### Run locally (Groq example)

```bash
docker run --rm -p 8100:8100 \
  -e APP_ENV=local \
  -e AI_PROVIDER=groq \
  -e GROQ_API_KEY=... \
  -e GROQ_MODEL=llama-3.3-70b-versatile \
  -e GROQ_BASE_URL=https://api.groq.com/openai \
  -e LARAVEL_INTERNAL_URL=http://host.docker.internal:8000 \
  -e AI_RUNTIME_SHARED_SECRET=... \
  alphasoft-ai-runtime
```

`host.docker.internal` reaches a Laravel dev server running on the host
machine (Docker Desktop). The container fails to start with a clear error if
the selected provider's API key is missing or `AI_PROVIDER` is unknown.

### Production environment variables

```bash
APP_ENV=production
AI_PROVIDER=groq
GROQ_API_KEY=...
GROQ_MODEL=...
LARAVEL_INTERNAL_URL=https://<backend-internal-or-private-url>
AI_RUNTIME_SHARED_SECRET=<strong shared secret>
CORS_ALLOWED_ORIGINS=
REQUEST_TIMEOUT_SECONDS=60
```

In production the shared secret must be set to a real value — the app refuses
to start with an empty or placeholder secret when `APP_ENV=production`.
`LARAVEL_INTERNAL_URL` should be a private/internal service URL (same private
network or service mesh), not the public backend URL; Laravel should call the
AI runtime back over that same private network.

### Security notes

- Do not expose this container publicly if avoidable — it is an internal
  service; Laravel should be the only caller.
- Keep `CORS_ALLOWED_ORIGINS` empty by default (no browser calls this
  service directly).
- `/api/chat` requires `X-AI-RUNTIME-TOKEN`, but the token is
  defense-in-depth, not a substitute for network isolation — keep the
  container on a private network/firewalled.
- Never bake API keys or `.env` files into the image; pass all secrets as
  runtime environment variables (the `.dockerignore` excludes `.env*` and
  the Dockerfile never copies them).

### Healthcheck

The image defines a `HEALTHCHECK` against `GET /api/health` using the Python
stdlib (the slim image has no curl). To check manually:

```bash
curl http://127.0.0.1:8100/api/health
# {"status":"ok"}
```

## Boundary

The runtime must not connect to tenant databases. It calls Laravel tools with:

- `X-AI-RUNTIME-TOKEN`
- tenant id
- user id
- session id
- tool name and input

Laravel validates the runtime token, initializes tenancy, checks the user and tool
permissions, executes the tool, and records `ai_tool_calls`.
