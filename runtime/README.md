# runtime/

**Phase C. Intentionally empty. Do not build yet.**

This will be the Python (FastAPI) agent runtime for multi-step agents, document intelligence, and forecasting — per `ai-planning/11-ai-platform-master-plan.md` §3 and §5 Phase C.

Hard rules decided in advance:

1. The runtime calls the Laravel tool-execution API with scoped service tokens carrying tenant + user context. It **never** opens a database connection.
2. It is stateless per request; sessions/tool-calls/suggestions persist in Laravel's tables only.
3. Nothing moves here until it works as a Laravel-adapter feature or is impossible there (long-running pipelines, Python-only deps).
4. The `AI_RUNTIME_ADAPTER=python` config value in the backend currently aliases `LaravelHttpAdapter` (GAPS #8) — wiring it for real is part of this phase, not before.

Reference patterns: `~/Desktop/adk-samples` (customer-service, data-science, invoice-processing agents). Reference only — not a dependency.
