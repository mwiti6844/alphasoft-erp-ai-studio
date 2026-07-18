# Copilot fixes — 2026-07-18

Change set that made the tenant AI copilot work end-to-end (browser → Laravel →
Python runtime → Groq/Anthropic) and cleaned up its output.

## Docs
- [backend.md](./backend.md) — Laravel serialization fixes (`PythonRuntimeAdapter`).
- [frontend.md](./frontend.md) — markdown rendering in the copilot panel.
- [deployment.md](./deployment.md) — how to ship all three repos + local-dev notes.

## AI runtime changes (this repo)
Documented in git history on `dev` and [prompts/CHANGELOG.md](../../../prompts/CHANGELOG.md):
- `fix(runtime): coerce Groq/llama null & empty tool arguments`
- `feat(runtime): fall back to Anthropic when Groq is rate-limited`
- `fix(runtime): include exception type in SSE error frames`
- `feat(runtime): narrate insights instead of re-dumping tool tables`

## One-line problem history
Blank/`422` panel → Groq schema/arg quirks → swallowed runtime errors →
single-worker Laravel deadlock → backend on the wrong port (`:8001` vs `:8000`)
→ stale test sessions → unrendered markdown + duplicated tables. All resolved.
