# contracts/

JSON Schemas that form the stable agreement between the Laravel backend, the Next.js frontend, the eval suites, and the future Python runtime. If backend code and a schema here disagree, that is a bug — fix one of them in the same PR.

| File | Describes | Source of truth in backend |
|---|---|---|
| `ai-tool.schema.json` | An AI tool's spec (name, scope, permission, schemas, action level) | `Modules\Ai\Contracts\AiToolContract` + tool classes |
| `ai-run.schema.json` | A session + its tool calls (the audit shape) | `ai_sessions` / `ai_tool_calls` migrations |
| `ai-suggestion.schema.json` | An AI-proposed change awaiting human review | `ai_suggestions` migration |
| `ai-followup-suggestion.schema.json` | A follow-up chip (+ optional structured action, doc 19 §10) | `FollowUpSuggestion` in `runtime/app/agents/components.py` (`action` is the planned extension) |
| `flows/` | ERP flow knowledge resources + their schema (doc 19 §7) | the product itself — flows must track UI/permissions changes |

Conventions: schemas use draft 2020-12; field names are `snake_case` matching DB columns; enums list only values the code actually produces. `action_level` is forward-looking (planned in `ai-planning/03`) — tools that don't declare it are treated as `read_only`.
