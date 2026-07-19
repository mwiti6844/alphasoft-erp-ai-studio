# 23 — Stakeholder Demo Walkthrough

**Date:** 2026-07-18  
**Audience:** Non-technical stakeholders, operators, partners  
**Status:** Planning only

## Goal

Show that the AI copilot is not a mockup. It works on live tenant data, stays read-only, and helps users ask questions about inventory, POS, and catalog data in plain language.

## One-minute opening

“This is the AlphaSoft ERP AI copilot. It answers live questions from tenant data, stays within permissions, and gives follow-up suggestions so users can continue the same line of thought without starting over.”

## Demo flow

1. Sign in to a seeded tenant account.
2. Open the AI copilot from the ERP shell.
3. Pick a module, starting with Inventory or POS.
4. Ask a simple live-data question, such as:
   - “Show current stock balances.”
   - “Show balances for the Main warehouse.”
   - “Which items are selling best this week?”
   - “What items are lagging or stopped selling?”
   - “What needs reorder this week?”
   - “Show recent movements for this item.”
   - “List the warehouses we have.”
   - “Search the catalog for Rice.”
   - “Show details for this catalog item.”
5. Show the AI response, then click one of the follow-up suggestions.
6. Switch to Catalog and ask a product lookup question.
7. End by showing that the copilot keeps the conversation thread and can be reopened.

## Best live question chains

### Inventory

- “Show current stock balances.”
- “Only for the Main warehouse.”
- “Include zero-stock items.”
- “Show movements for this item.”
- “What warehouse is this item in?”

### POS

- “Which items are selling best?”
- “What about the last 14 days instead of this week?”
- “Which items are lagging?”
- “Show the sales summary for this branch.”
- “Show me the daily trend.”

### Catalog

- “Search the catalog for Rice.”
- “Show details for the first item.”
- “Show the variants and unit of measure.”
- “Search by SKU instead of name.”

### Warehouses

- “List the warehouses we have.”
- “Which warehouse has stock for this item?”

## What to emphasize

- It uses live tenant data, not canned demo content.
- It is read-only for now, so it cannot change business records.
- It remembers the conversation within the session.
- It adapts to the module the user chose.
- It gives useful follow-up prompts instead of forcing the user to retype everything.

## Follow-up prompts worth showing

The follow-up chips should feel like natural next steps, not generic chatbot filler.

- After inventory balances:
  - “Show recent movements for this item”
  - “Filter to the Main warehouse”
  - “Include zero-stock rows”

- After inventory movements:
  - “Show current balances for this item”
  - “Which warehouse is this in?”
  - “Show the same movements for a longer period”

- After reorder candidates:
  - “Show current stock balances”
  - “Show recent movements for the most at-risk item”
  - “Which warehouse is low?”

- After POS top sellers:
  - “Show the sales summary”
  - “Show lagging items”
  - “Compare with last month”

- After POS lagging items:
  - “Show top sellers”
  - “Show the sales summary”
  - “What should we reorder?”

- After catalog search:
  - “Show item details”
  - “Search by SKU”
  - “Search a different product”

- After catalog item detail:
  - “Show matching items”
  - “Search a similar product”
  - “Open another catalog item”

## What to say if asked about safety

- The AI only sees data the logged-in user is allowed to access.
- Laravel controls permissions and tool execution.
- The Python runtime orchestrates the conversation, but it does not talk directly to tenant databases.
- Unsupported questions are handled honestly instead of making up numbers.

## Good audience-facing talking points

- “This reduces time spent searching across screens.”
- “It helps users ask business questions in natural language.”
- “The same assistant can support inventory, POS, and catalog workflows.”
- “The experience is designed to grow into write workflows later, but the current version is intentionally read-only.”
- “The assistant only shows options that match the current module and the user’s permissions.”

## Suggested closing

“The important part here is that the assistant is already connected to the ERP data model and can support real operations. What you are seeing is the base layer for a larger AI workflow, not a prototype prompt box.”
