# Alphasoft ERP AI Studio Instructions

You are helping build the AI layer for Alphasoft ERP.

Alphasoft ERP currently has two local repositories:

- Frontend: `/Users/mac/Desktop/alpaerpfrontend-1`
- Backend: `/Users/mac/Desktop/alphasoft-backend/alphasoft-backend` (canonical; the older `alpha-erp-backend` clone was retired 2026-07-06)

This repository (`alphasoft-erp-ai-studio`) is the AI repo: planning docs, prompts, evals, contracts, and (from Phase C) the Python agent runtime. See `ai-planning/11-ai-platform-master-plan.md` for the full plan.

The AI system must be built as a governed ERP capability, not as a loose chatbot pasted onto screens.

## Core Rules

- Respect tenant boundaries at all times.
- Do not bypass Laravel authentication, authorization, policies, roles, or permissions.
- AI actions must use approved backend tools or APIs.
- Sensitive write actions must require human approval.
- Every agent run and tool call must be auditable.
- Start with Catalog and Inventory because they are the live ERP modules.
- Prefer read-only, draft, and recommendation workflows before execution workflows.
- Keep the architecture modular so future agents can support Accounting, Sales, Purchase, CRM, HR, Reporting, and Localization.

## Product Direction

The AI layer should eventually become an ERP module named **Alphasoft ERP AI Studio**.

AI Studio should provide:

- Agent configuration
- Tool registry
- Knowledge sources
- Permissions and approval rules
- Run history
- Tool-call audit logs
- Human feedback
- Evaluation results

## First Target

Build an **Inventory + Catalog Copilot** that can answer read-only questions and produce safe recommendations using existing backend APIs.

Initial questions it should support:

- Which stockable items have no stock?
- Which catalog items are missing a base unit of measure?
- Explain this product's stock position.
- Show recent stock movements for this item.
- Suggest reorder candidates.
- Find catalog items with risky tracking settings.
- Summarize warehouse balances.

## Safety Principles

AI may explain, summarize, recommend, and prepare drafts.

AI must not directly perform sensitive business actions without explicit user approval. Sensitive actions include:

- Posting stock receipts
- Issuing stock
- Publishing localization packs
- Creating tenants
- Creating invoices
- Approving payments
- Deleting records
- Changing accounting settings

## Engineering Principles

- Laravel remains the source of truth for business data and permissions.
- Next.js provides the AI user experience and embedded copilots.
- Agents should call narrow, typed tools instead of unrestricted database queries.
- Tool outputs should return only the data needed for the task.
- All AI behavior must be explainable enough for ERP users to trust and audit.
