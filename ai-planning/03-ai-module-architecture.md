# Alphasoft ERP AI Studio Module Architecture

## High-Level Shape

AI Studio should be built as a governed ERP module.

Recommended backend module:

```txt
app-modules/ai
```

Recommended frontend routes:

```txt
/ai
/ai/agents
/ai/tools
/ai/runs
/ai/approvals
/ai/knowledge
/ai/settings
```

## Architecture Responsibilities

## Laravel Backend

Laravel should own:

- Tenant data access
- Permissions and roles
- Business rules
- AI tool definitions
- Tool execution
- Approval workflows
- Audit logs
- Agent run records
- Knowledge source metadata

The AI layer must not bypass Laravel policies or direct tenant boundaries.

## Next.js Frontend

Next.js should own:

- AI Studio screens
- Copilot panels inside ERP modules
- Agent run views
- Approval UI
- Tool-call history display
- Chat and task interaction UX
- Readable explanations for users

## Agent Runtime

The agent runtime can be introduced behind the Laravel tool layer.

Candidate patterns:

- Start with a simple server-side AI service integration.
- Add an ADK-based agent runtime when workflows become multi-step.
- Keep ERP tool execution in Laravel even if orchestration happens elsewhere.

The runtime should call approved tools, not raw database queries.

## Tool-Based Design

Agents should act through narrow tools.

Example tools:

```txt
catalog.search_items
catalog.get_item
catalog.find_items_missing_base_uom
catalog.find_items_missing_tracking_rules
inventory.get_balances
inventory.get_movements
inventory.explain_stock_position
inventory.suggest_reorder_candidates
inventory.create_receipt_draft
inventory.create_issue_draft
localization.validate_pack
tenant.get_profile
```

Each tool should define:

- Name
- Description
- Input schema
- Output schema
- Required permission
- Read/write level
- Approval requirement
- Audit behavior

## Permission Levels

Recommended AI action levels:

```txt
read_only
recommendation
draft
execute_with_approval
forbidden
```

Initial work should focus on `read_only`, `recommendation`, and `draft`.

## Audit Tables

Expected backend tables later:

```txt
ai_agents
ai_agent_tools
ai_agent_runs
ai_tool_calls
ai_approvals
ai_knowledge_sources
ai_feedback
```

Every AI run should record:

- Tenant
- User
- Agent
- Prompt/request
- Tools called
- Records accessed
- Proposed action
- Approval decision
- Final result
- Error details
- Timestamps

## Tenant Isolation

AI must always operate within the current tenant unless the user is a central admin using an explicitly central AI workflow.

Tenant AI and central admin AI should be treated as separate contexts.

Rules:

- No cross-tenant data leakage
- No raw token exposure
- No unrestricted SQL from agent prompts
- No hidden system-table access unless explicitly exposed by a tool
- Tool responses should be minimal and task-specific

## First Backend Scope

The first backend AI module should support:

- Agent registry
- Tool registry
- Agent run logging
- Tool-call logging
- Read-only Catalog tools
- Read-only Inventory tools

Approval workflows can be added after read-only and draft workflows are stable.

## First Frontend Scope

The first frontend UI should support:

- AI Studio landing page
- Inventory + Catalog Copilot
- Run history
- Tool-call details
- Safe recommendation display

Embedded copilot entry points can later be added to:

- Catalog item detail
- Catalog items list
- Inventory overview
- Stock balances
- Stock movements
- Warehouse detail
