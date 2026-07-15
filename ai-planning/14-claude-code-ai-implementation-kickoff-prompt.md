# Claude Code Prompt: AlphaSoft AI Implementation Plan

Use this prompt to start the next Claude Code planning session.

```text
You are Claude Code working on the AlphaSoft ERP AI implementation. Your first job is to inspect the real codebases, understand the current uncommitted AI slice, read the meeting notes, and produce a phased implementation plan before coding.

Do not commit or push anything. Do not overwrite uncommitted work. The repos are dirty by design because AI runtime/backend/frontend work is in progress.

Repos on this machine:
- AI Studio/runtime/planning repo: /Users/mac/Desktop/alphasoft-erp-ai-studio
- Backend Laravel repo: /Users/mac/Desktop/alphasoft-backend/alphasoft-backend
- Frontend Next.js repo: /Users/mac/Desktop/alpaerpfrontend-1
- Reference only: /Users/mac/Desktop/carduka
- Reference only: /Users/mac/Desktop/adk-samples

Meeting notes to read:
- /Users/mac/Downloads/E-commerce ERP Architecture and AI Inte_ Summary.txt
- /Users/mac/Downloads/E-commerce ERP Architecture and AI Inte_ Transcript.txt
- /Users/mac/Downloads/POS Product Launch Planning Summary.txt
- /Users/mac/Downloads/POS Product Launch Planning Transcript.txt

Important current status:
- Backend and frontend `main` were fetched/pulled and are already up to date with `origin/main`.
- Backend and frontend have uncommitted AI changes. Preserve them.
- The AI Studio repo also has uncommitted runtime/planning changes. Preserve them.
- We are building the real AI implementation, not a mock demo.
- Python is the orchestration runtime direction.
- Laravel remains the source of truth for tenant data, auth, permissions, sessions, tools, audit logs, and business writes.
- Python must not connect directly to tenant databases.
- Frontend renders only allow-listed generative UI components.
- Start provider support with Groq models for test purposes before Microsoft Foundry, Claude, and OpenAI are fully integrated.
- We will use module routers so AI behavior can be separated by module/domain.

Read first:
- /Users/mac/Desktop/alphasoft-erp-ai-studio/CLAUDE.md
- /Users/mac/Desktop/alphasoft-erp-ai-studio/AI_PROJECT_INSTRUCTIONS.md
- /Users/mac/Desktop/alphasoft-erp-ai-studio/PROJECT.md
- /Users/mac/Desktop/alphasoft-erp-ai-studio/GAPS.md
- /Users/mac/Desktop/alphasoft-erp-ai-studio/ai-planning/11-ai-platform-master-plan.md
- /Users/mac/Desktop/alphasoft-erp-ai-studio/ai-planning/12-runtime-slice-audit.md
- /Users/mac/Desktop/alphasoft-erp-ai-studio/ai-planning/13-memory-state-generative-ui-plan.md
- /Users/mac/Desktop/alphasoft-backend/alphasoft-backend/AGENTS.md

Then inspect the actual implementation:

Backend:
- app-modules/ai/routes/ai-routes.php
- app-modules/ai/src/Contracts/*
- app-modules/ai/src/Services/AiToolRegistry.php
- app-modules/ai/src/Services/AiSessionService.php
- app-modules/ai/src/Services/AiModelRegistry.php
- app-modules/ai/src/Services/Adapters/LaravelHttpAdapter.php
- app-modules/ai/src/Services/Adapters/PythonRuntimeAdapter.php
- app-modules/ai/src/Services/Providers/AnthropicHttpProvider.php
- app-modules/ai/src/Services/Tools/*
- app-modules/ai/src/Http/Controllers/Api/V1/AiCopilotController.php
- app-modules/ai/src/Http/Controllers/Api/V1/AiRuntimeToolController.php
- app-modules/ai/src/Models/AiSession.php
- app-modules/ai/src/Models/AiMessage.php
- config/ai.php
- tests/Unit/Ai/PosAnalyticsToolsTest.php

Frontend:
- src/components/ai/AiPanel.tsx
- src/components/ai/AiMessageList.tsx
- src/components/ai/AiComponentRenderer.tsx
- src/lib/ai/api.ts
- src/lib/ai/stream.ts
- src/lib/ai/types.ts

Python runtime:
- runtime/README.md
- runtime/.env.example
- runtime/app/config.py
- runtime/app/main.py
- runtime/app/routes/chat.py
- runtime/app/agents/copilot.py
- runtime/app/agents/components.py
- runtime/app/agents/events.py
- runtime/app/clients/laravel.py
- runtime/app/llm/*

Current architecture facts to preserve:
- Laravel exposes tenant AI routes behind tenancy + Sanctum.
- Laravel exposes an internal runtime tool endpoint at `/api/internal/ai/tools/{tool}/execute`.
- Python calls that internal endpoint using `X-AI-RUNTIME-TOKEN`.
- Laravel filters available tool definitions by module scope and, once enabled, permissions.
- Tool execution goes through `AiToolRegistry::dispatch`, which records `ai_tool_calls`.
- Durable conversation memory is in tenant SQL via `ai_sessions` and `ai_messages`.
- `ai_sessions.context_json` stores compact conversation state.
- Python receives recent messages, conversation state, and tool definitions from Laravel.
- Python emits SSE events: `token`, `tool`, `trace`, `component`, `state_patch`, `error`, `done`.
- Frontend appends ordered text/component blocks and renders only known component types.
- Existing component types: `pos_top_items_table`, `pos_lagging_items_table`, `pos_sales_summary_card`, `inventory_reorder_candidates_table`, `follow_up_suggestions`.

Meeting-derived product requirements:
- AI access levels must eventually cover end user, client/admin, and super admin consolidated reporting.
- Opt-in telemetry is required for cross-tenant, anonymized, predefined analytics. Do not mix tenant data.
- Future clients may bring their own AI keys for advanced tasks; this must be planned but not built first.
- POS launch AI must focus on restaurant and retail analytics first.
- Required near-term AI use cases:
  - top-selling products
  - lagging/stopped-selling products
  - reorder candidates
  - sales summaries
  - advertising/product-promotion recommendations based only on available data
  - customer/product recommendation system later, likely SQL/co-occurrence first
- If no data exists, the AI must say so clearly and suggest scope/data checks. It must not invent campaign performance or sales numbers.
- The ERP and e-commerce storefront are separate deployments/codebases; AI must respect that boundary.
- Product release deliverables should include product, technical write-up, user guide/manual, and marketing material. Include AI documentation tasks in the plan.

Provider direction:
- Immediate test provider: Groq.
- Treat "grokq" in discussion as Groq unless code proves otherwise.
- Groq should use an OpenAI-compatible chat/completions client path where practical.
- Foundry, Claude, OpenAI, Gemini can be later providers behind the same provider interface/router.
- Do not hardcode Anthropic-only message/tool formats as the permanent runtime shape.
- Current runtime config is Anthropic-only; plan and implement a generic Python provider interface plus Groq provider.
- Keep Laravel config/model registry aligned with runtime provider routing.
- The first Groq model can be env-driven. Prefer a currently available Groq tool-capable model; document the env var rather than baking business logic to one model name.

Non-negotiable engineering rules:
- No direct Python DB access.
- No direct AI mutations of ERP records.
- Sensitive writes must become suggestions/drafts and require human approval.
- SQL/Laravel tools compute business figures; models explain and route.
- Tool outputs must be minimal and avoid unnecessary PII.
- Errors must be visible to users, not silently swallowed.
- No fabricated/demo/mock data for production behavior.
- Use real tenant data for tests/smoke where available; if unavailable, use isolated automated test fixtures only.
- Tenancy boundaries are sacred.
- Do not add Next.js API proxy routes for ERP CRUD/AI; frontend talks to Laravel via existing tenant API utilities.
- Do not change production deployment workflows.

Your planning output must include:

1. Current State Summary
- What already exists in backend, frontend, and Python runtime.
- What is uncommitted and should be preserved.
- What works today versus what is only scaffolded.

2. Target Architecture
- Laravel responsibilities.
- Python runtime responsibilities.
- Frontend responsibilities.
- Module router design.
- Provider router design.
- Memory/state/suggestions/generative UI design.
- Telemetry and super-admin reporting boundary.

3. Phased Implementation Plan
Use practical phases with explicit acceptance criteria. Suggested phases:

Phase 0: Safety and baseline verification
- Verify current uncommitted work.
- Run focused tests/checks.
- Confirm env requirements.
- Confirm no direct DB access from Python.

Phase 1: Groq provider and provider router
- Python provider interface.
- Groq OpenAI-compatible provider.
- Anthropic provider adapted behind same interface if retained.
- Runtime env/config update.
- Laravel config/model registry alignment.
- Clear provider/model errors.
- Acceptance: one real chat request can route through Groq and still call Laravel tools.

Phase 2: Module routers
- `catalog`, `inventory`, `pos` module router separation in Python.
- Each router owns system instructions, allowed components, deterministic suggestions, and state patch rules.
- Keep common orchestration shared.
- Acceptance: POS questions do not leak into catalog/inventory prompt behavior and vice versa.

Phase 3: Memory, state, and follow-up suggestions
- Confirm SQL `ai_messages` replay works.
- Confirm ordered message blocks persist and replay.
- Replace hardcoded follow-ups with deterministic suggestion builders.
- Support structured suggestion actions where safe, with message fallback.
- Acceptance: multi-turn follow-up like "what about last month?" uses context correctly.

Phase 4: POS analytics and generative UI hardening
- Validate existing POS tools and component contracts.
- Add empty-state component if needed.
- Add advertising recommendation tool only if the real schema has enough data; otherwise explicitly defer and make the assistant say there is no ad-tracking data.
- Acceptance: top sellers, lagging items, sales summary, reorder candidates render with live data and no invented numbers.

Phase 5: E-commerce/recommendations planning slice
- Plan but do not overbuild cross-sell/recommendation system.
- Use SQL co-occurrence and catalog/order history first, not LLM guesses.
- Keep e-commerce deployment separate from ERP.
- Acceptance: documented interface between e-commerce and ERP AI endpoints/tools.

Phase 6: Telemetry, access levels, and BYO keys
- Design opt-in telemetry tables/jobs/endpoints.
- Define end-user/client/super-admin access levels.
- Define BYO provider-key storage/security model.
- Acceptance: architecture doc and minimal DB/API contracts; implementation can be later unless requested.

Phase 7: Evals, docs, and release packaging
- Add/expand eval fixtures for multi-turn conversations, empty data, ordinal references, and component rendering.
- Produce technical write-up outline, user guide outline, and marketing/launch claims that match actual functionality.
- Acceptance: no release claim says "streaming", "ad analytics", or "autonomous actions" unless implemented.

4. Immediate Next Implementation Steps
- Provide the exact first code changes you would make, ordered.
- Include files to edit.
- Include commands to run.
- Include risks and rollback strategy.

5. Questions/Decisions Needed
- Only list decisions that block implementation.
- If a reasonable default exists, choose it and mark it as an assumption.

Expected first recommendation:
- Start with Phase 1: Groq provider/router in Python runtime plus Laravel config alignment, then smoke test browser -> Laravel -> Python runtime -> Groq -> Laravel tool -> frontend component.

Do not implement until you have produced the plan and the user approves the first phase.
```
