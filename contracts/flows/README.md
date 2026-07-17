# contracts/flows/ — ERP flow knowledge base

Citable "how do I use AlphaSoft?" resources, one YAML per flow, organized as `flows/{module}/{flow-id}.yaml`. Design: `ai-planning/19-ai-chat-memory-agent-flow-plan.md` §7 (schema, taxonomy, answer style) and §8 (retrieval rules).

Every file must validate against [`flow.schema.json`](flow.schema.json). Validation checks (planned pytest, not built yet): schema validity, unique ids, and every `related_flows` / `related_ai_tools` reference resolving (`related_ai_tools` against the registered tool list — proposed-but-unregistered tools are a validation error).

## Rules

- **Product knowledge only.** No tenant data, no customer PII, ever. Live figures come from tools; flows explain the product around them.
- **Citations are mandatory.** The runtime injects matched flows into the prompt tagged with `id` + `version`; answers built on a flow must cite it. A process question with no matching flow gets an honest "not documented yet" — never a confabulated procedure.
- **Grounded fields.** `permissions` are copied from the owning module's `config/permissions.php`; `route` values are verified against the frontend app router; `related_ai_tools` name only registered tools.
- **Honesty over polish.** Known limitations go in `notes` / `common_errors` so the assistant states them (e.g. the balance tool hiding zero-stock rows) instead of papering over them.
- **Flows are code.** Changes go through PR with a changelog entry below; bump `version` on any content change.

## Changelog

- **2026-07-16** — v1 of schema + first 8 flows: `inventory.check-stock`, `inventory.stock-movements`, `inventory.reorder-candidates`, `catalog.create-item`, `pos.setup`, `pos.restaurant-register`, `permissions.module-access`, `taxes.configure-tax` (doc 19 Phase A).
