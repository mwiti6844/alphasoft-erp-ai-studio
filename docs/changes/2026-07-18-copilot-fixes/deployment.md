# Deployment — Copilot reliability + markdown (2026-07-18)

Three repos changed. Deploy the **AI runtime** and **backend** together (they
are a request/response pair); the **frontend** is independent.

| Repo | Branch pushed | Deploys via |
|---|---|---|
| `alphasoft-erp-ai-studio` (AI runtime) | `dev` | Rebuild the runtime Docker image on the VPS |
| `alphasoft-backend` | `feature/ai-runtime-backend-integration` | PR → `dev` ([#15](https://github.com/Geekigen/alphasoft-backend/pull/15)); prod = later `dev` → `main` |
| `alpaerpfrontend-1` | `feature/ai-chat-ui-integration` | PR → `dev` ([#54](https://github.com/Geekigen/alpaerpfrontend/pull/54)) |

---

## 1. AI runtime (this repo)

The runtime fixes (Groq null-arg handling, Anthropic fallback, SSE error detail,
prompt rule) live in `runtime/app/**` and are **baked into the image at build
time** — a restart alone is not enough; you must rebuild.

**Production (VPS `ai.alphasoft.app`, path `/var/www/ai`):**
```bash
cd /var/www/ai
git pull                       # dev (or the release branch you deploy from)
./deploy/deploy.sh             # builds + recreates + waits for /api/health
# or manually:
docker compose -f docker-compose.production.yml up -d --build
```
Container listens on `8100` internally, published to `127.0.0.1:8000` (nginx
proxies). Requires `runtime/.env` with `GROQ_API_KEY` and, for fallback,
`ANTHROPIC_API_KEY` (`ANTHROPIC_MODEL=claude-sonnet-5`), plus
`LARAVEL_INTERNAL_URL` pointing at the backend and `AI_RUNTIME_SHARED_SECRET`.

**Verify:** `curl -s http://127.0.0.1:8000/api/health` → `{"status":"ok"}`.

## 2. Backend

PR **[#15](https://github.com/Geekigen/alphasoft-backend/pull/15)** targets
`dev` (the repo default/integration branch). Merging into `dev` is safe — it
does **not** deploy production.

> ⚠️ **Production deploys on push to `main`** (`.github/workflows/deploy-production.yml`).
> Promote to prod as a **separate, deliberate** `dev` → `main` PR/merge, and
> deploy the AI runtime (step 1) first or together — the new runtime relies on
> the backend's normalized (`{}`) tool schemas for Groq.

## 3. Frontend

Independent of the backend/runtime. PR **[#54](https://github.com/Geekigen/alpaerpfrontend/pull/54)**
targets `dev`; merge when reviewed. `npm ci` on the build host picks up the new
deps (`react-markdown`, `remark-gfm`); no config changes required.

---

## Local dev environment (lessons from this session)

These bit us repeatedly — keep them straight when running locally:

- **One canonical backend port: `:8000`.** The frontend (`NEXT_PUBLIC_TENANT_API_PORT`,
  `NEXT_PUBLIC_CENTRAL_API_URL`) and `runtime/.env` `LARAVEL_INTERNAL_URL` all
  target `:8000`. Run Laravel there.
- **Laravel dev server MUST have concurrent workers**, or the runtime's tool
  callback deadlocks (single worker is busy holding the chat request):
  ```bash
  cd alphasoft-backend/alphasoft-backend/public
  env PHP_CLI_SERVER_WORKERS=6 php -S 127.0.0.1:8000 \
    ../vendor/laravel/framework/src/Illuminate/Foundation/resources/server.php
  ```
  (`php artisan serve` does **not** forward `PHP_CLI_SERVER_WORKERS` to its child.)
- **`NEXT_PUBLIC_*` are inlined at dev-server start** — after changing `.env`,
  restart `npm run dev` or the browser keeps calling the old port.
- **Runtime container env is fixed at creation** — `docker restart` won't change
  `LARAVEL_INTERNAL_URL`; recreate with
  `docker compose -f docker-compose.ai.yml up -d` (reads `runtime/.env`).
- Ports: **`:8000`** Laravel · **`:8100`** runtime · **`:3000`** frontend.

## Rollback
- **Runtime:** redeploy the previous image tag / `git checkout <prev> && ./deploy/deploy.sh`.
- **Backend/Frontend:** revert the merge commit; backend revert to `main`
  re-triggers the production deploy.
