# Prompt Changelog

All notable prompt changes. Format: version — date — surface — summary — eval evidence.

## runtime BASE_RULES — 2026-07-18 — tenant copilot (python runtime)
- Added a rule to `runtime/app/agents/modules/base.py` `BASE_RULES`: the UI already renders tool results as structured tables/cards, so the model must NOT reproduce that data as a markdown table or row-by-row list — narrate insights (highlights, comparisons, outliers, next steps) instead. Light markdown (bold, short bullets) is allowed.
- Motivation: panel responses were duplicating each rendered component table as a raw markdown pipe-table in prose (unreadable, and violated "SQL computes, models narrate"). Paired with a frontend change rendering assistant text as GFM markdown (`AiMarkdown`).
- Note: the effective copilot prompt now lives in the python runtime routers, not `AiSystemPromptBuilder` (see GAPS #10). Manual verification only (no eval harness): POS "top sellers" query now returns prose + 2 component tables, 0 markdown-table rows in narration.

## copilot-system-v1 — 2026-07-06 — tenant copilot
- Initial capture of the production prompt from `AiSystemPromptBuilder::build()` (backend, unversioned until now).
- No eval run (harness does not exist yet). Baseline for all future comparisons.
