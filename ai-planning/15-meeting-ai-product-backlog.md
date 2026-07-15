# Phase 1.5 — Meeting AI Product Backlog and Reporting Map

Date: 2026-07-15

Scope: planning document only. No implementation is implied. This maps the July 4 meeting requirements into AI product backlog items and formally separates client-facing tenant reporting from AlphaSoft in-house reporting.

## Current State Recap

Phase 0 and Phase 1 are complete in the working tree:

- Python runtime has a provider-neutral LLM layer with Groq and Anthropic providers.
- Groq uses an OpenAI-compatible chat/completions path.
- Laravel remains the only executor for tenant tools and database queries.
- Python runtime calls Laravel internal tools through `X-AI-RUNTIME-TOKEN`.
- Backend permission enforcement now defaults on.
- Unknown model IDs no longer silently fall back to Anthropic.
- Durable chat memory exists through `ai_sessions`, `ai_messages`, and `ai_sessions.context_json`.
- Frontend supports ordered text/component blocks and renders only allow-listed AI components.

Existing shipped AI tools/components:

- `pos_top_selling_items`
- `pos_lagging_items`
- `pos_sales_summary`
- `inventory_reorder_candidates`
- catalog and inventory lookup tools
- UI components for top items, lagging items, sales summary, reorder candidates, and follow-up suggestions

All current AI work remains uncommitted.

## Reporting Surface Map

### Surface A: Client-Facing Tenant Reporting

This is AI used by authenticated users inside a tenant.

Rules:

- Uses live tenant data.
- Laravel is the sole tool/query executor.
- Laravel enforces tenancy, auth, permissions, validation, audits, sessions, and persistence.
- Python routes intent, chooses tools, reasons over tool outputs, writes state patches, and emits UI components.
- Frontend renders only allow-listed components.
- Initial modules: POS, restaurant, retail, inventory, catalog.

Text boundary:

```text
Tenant user
→ Laravel tenant API/auth/permissions
→ Python module router
→ Laravel tool/query contract execution
→ Python narration/components/state
→ Laravel persistence/audit
→ Frontend allow-listed rendering
```

### Surface B: In-House AlphaSoft / Super-Admin Reporting

This is internal reporting for AlphaSoft leadership/admin users.

Rules:

- Must not query live tenant databases.
- Must use opt-in anonymized telemetry only.
- Requires a central aggregate store.
- Super-admin analytics run on aggregate data, not tenant tables.
- No tenant-data mixing.
- No customer/vendor/employee PII in aggregates.
- Design only until explicitly approved for implementation.

Text boundary:

```text
Opted-in tenant
→ scheduled anonymized aggregate export
→ AlphaSoft central telemetry store
→ super-admin reporting tools/query contracts
→ Python narration/components
```

## Classified Feature Backlog

### 1. POS Top Sellers

- Surface: client-facing
- Horizon: Now
- Write posture: read-only
- Data exists today: yes. `pos_transactions.completed_at`, `grand_total`, and `pos_transaction_lines.catalog_item_id`, `qty`, `line_total` support this.
- Laravel tools needed: existing `pos_top_selling_items`; validate on real tenant data.
- Python router/resources needed: POS router prompt and metric definition.
- Frontend components needed: existing `pos_top_items_table`.
- Telemetry needed: no
- Acceptance criteria: top sellers render from completed transactions only; no incomplete transactions included; answer cites tool figures only.
- Risks/blockers: tenant must have completed POS sales.

### 2. POS Lagging / Stopped-Selling Items

- Surface: client-facing
- Horizon: Now
- Write posture: read-only
- Data exists today: yes. Completed transaction lines across comparable windows support this.
- Laravel tools needed: existing `pos_lagging_items`.
- Python router/resources needed: POS router date-window glossary.
- Frontend components needed: existing `pos_lagging_items_table`.
- Telemetry needed: no
- Acceptance criteria: equal recent/previous windows; stopped-selling items clearly flagged.
- Risks/blockers: low sales volume may produce empty results.

### 3. Reorder Candidates

- Surface: client-facing
- Horizon: Now
- Write posture: read-only
- Data exists today: yes. Inventory balance and POS sales velocity exist; no `reorder_point` field is required.
- Laravel tools needed: existing `inventory_reorder_candidates`.
- Python router/resources needed: shared POS/inventory router handling.
- Frontend components needed: existing `inventory_reorder_candidates_table`.
- Telemetry needed: no
- Acceptance criteria: candidates use stock cover and sales velocity; no purchase order is created.
- Risks/blockers: velocity depends on completed POS activity.

### 4. POS Sales Summary

- Surface: client-facing
- Horizon: Now
- Write posture: read-only
- Data exists today: yes. `pos_transactions.grand_total`, `tax_total`, `discount_total`, `completed_at`, `vertical`, and `branch_id`.
- Laravel tools needed: existing `pos_sales_summary`; later add branch/vertical filters.
- Python router/resources needed: POS metric glossary.
- Frontend components needed: existing `pos_sales_summary_card`.
- Telemetry needed: no
- Acceptance criteria: current and previous periods compare cleanly; empty periods are explicit.
- Risks/blockers: fiscal/tax interpretation may need refinement by country.

### 5. Restaurant Analytics Pack

- Surface: client-facing
- Horizon: Now/Next
- Write posture: read-only
- Data exists today: yes for baseline. `pos_transactions.vertical = restaurant` enables filtering.
- Laravel tools needed: add vertical/daypart/menu-mix parameters to POS tools.
- Python router/resources needed: POS router should understand restaurant terms like menu mix, daypart, table/server context where available.
- Frontend components needed: existing summary/table components first; later daypart/menu-mix components.
- Telemetry needed: no
- Acceptance criteria: restaurant answers filter restaurant transactions and do not mix retail/pharmacy unless requested.
- Risks/blockers: daypart and server/table analytics depend on available POS fields and data quality.

### 6. Retail Analytics Pack

- Surface: client-facing
- Horizon: Now/Next
- Write posture: read-only
- Data exists today: yes for baseline. `pos_transactions.vertical = retail`.
- Laravel tools needed: vertical filter on existing POS tools.
- Python router/resources needed: retail glossary for basket, category, stock velocity, promotions.
- Frontend components needed: existing tables/cards first.
- Telemetry needed: no
- Acceptance criteria: retail analytics isolate retail sales where vertical is present.
- Risks/blockers: category-level reporting depends on catalog category joins.

### 7. Tax-Aware Revenue / Profit Summaries

- Surface: client-facing
- Horizon: Next
- Write posture: read-only
- Data exists today: partial. Revenue and tax exist through `grand_total`, `tax_total`, `discount_total`; profit is unknown because `catalog_items.purchase_price` is nullable and coverage is unknown.
- Laravel tools needed: `pos_tax_revenue_summary`; profit variant only after readiness check.
- Python router/resources needed: definitions for gross revenue, tax, discount, net revenue, margin.
- Frontend components needed: metric summary card/table.
- Telemetry needed: no
- Acceptance criteria: revenue/tax summary works; profit is withheld unless purchase-price coverage passes a readiness threshold.
- Risks/blockers: missing or stale purchase prices create misleading margins.

### 8. Product-Promotion Recommendations

- Surface: client-facing
- Horizon: Next
- Write posture: read-only recommendation
- Data exists today: partial. Sales velocity and `pos_promotions.redemption_count` exist; ad impressions/clicks do not.
- Laravel tools needed: promotion performance/velocity comparison tool.
- Python router/resources needed: suggestion builder that separates promotion recommendations from ad analytics.
- Frontend components needed: recommendation list/card.
- Telemetry needed: no
- Acceptance criteria: recommends products to promote from sales and promotion redemption evidence only.
- Risks/blockers: must not claim ad campaign ROI.

### 9. Advertising Analytics

- Surface: client-facing
- Horizon: Conditional/Later
- Write posture: read-only
- Data exists today: no. No ad campaign, impressions, click, spend, or attribution schema was found.
- Laravel tools needed: none until ad-tracking data exists.
- Python router/resources needed: no-data response rule.
- Frontend components needed: optional empty-state component.
- Telemetry needed: no
- Acceptance criteria: assistant says ad-tracking data is unavailable and suggests trackable alternatives.
- Risks/blockers: high demo risk if marketed as existing.

### 10. E-Commerce Customer/Product Recommendations

- Surface: e-commerce
- Horizon: Later
- Write posture: read-only
- Data exists today: no in ERP. E-commerce is a separate deployment; cashew client path may be WooCommerce.
- Laravel tools needed: future recommendation/co-occurrence tools only after integration boundary is defined.
- Python router/resources needed: e-commerce resource pack later.
- Frontend components needed: storefront recommendation UI later.
- Telemetry needed: no for tenant-local; maybe aggregate later.
- Acceptance criteria: documented ERP/e-commerce contract before implementation.
- Risks/blockers: do not let storefront call Python directly; keep ERP boundary.

### 11. Admin Alerts / Suggestions

- Surface: client-facing
- Horizon: Next — but explicitly sequenced **after** POS module routers (Phase 2) and POS analytics hardening. Do not implement before alert thresholds and the review UX are defined; unbounded alerts become noise fast.
- Write posture: draft
- Data exists today: yes for baseline. `activity_events` plus thresholds can drive alerts.
- Laravel tools needed: alert candidate/readiness tools; use `ai_suggestions` for draft actions.
- Python router/resources needed: alert/suggestion policy and thresholds.
- Frontend components needed: alert/suggestion cards and review actions.
- Telemetry needed: no
- Acceptance criteria: alerts are explainable and never auto-apply sensitive changes; a threshold breach produces one deduplicated, reviewable suggestion, not a stream.
- Risks/blockers: alert fatigue; threshold tuning. Blocked on threshold definitions and review-UX design (product decision) before any implementation.

### 12. Opt-In Anonymized Telemetry

- Surface: in-house
- Horizon: Next design / Later build
- Write posture: approval-required consent
- Data exists today: yes by definition only after consent and aggregate-job implementation.
- Laravel tools needed: consent settings, aggregate export jobs, central ingestion.
- Python router/resources needed: telemetry metric resources.
- Frontend components needed: consent UI and super-admin dashboards later.
- Telemetry needed: yes
- Acceptance criteria: no tenant data leaves without opt-in; aggregates contain no PII.
- Risks/blockers: privacy, customer trust, central schema design.

### 13. Super-Admin Consolidated Reporting

- Surface: in-house
- Horizon: Later
- Write posture: read-only over aggregates
- Data exists today: no central aggregate store yet.
- Laravel tools needed: central aggregate query tools.
- Python router/resources needed: in-house reporting router.
- Frontend components needed: super-admin reporting dashboard.
- Telemetry needed: yes
- Acceptance criteria: reports query aggregate tables only, never live tenant DBs.
- Risks/blockers: must not create lateral movement or tenant data leakage.

### 14. AI Access Levels

- Surface: cross-cutting
- Horizon: Next
- Write posture: policy/configuration
- Data exists today: partial. Permission enforcement is now on by default; explicit AI access tiers still need design.
- Laravel tools needed: role/permission mappings for end user, client admin, super-admin.
- Python router/resources needed: scope-aware prompts and tool filtering assumptions.
- Frontend components needed: hide unavailable AI scopes/actions.
- Telemetry needed: for super-admin only.
- Acceptance criteria: end users cannot see admin/super-admin tools; tool definitions are filtered before reaching Python.
- Risks/blockers: role mapping mismatch can block legitimate demos.

### 15. BYO Client AI Keys

- Surface: cross-cutting
- Horizon: Later
- Write posture: approval-required configuration
- Data exists today: no.
- Laravel tools needed: encrypted per-tenant provider key storage, audit, policy, usage controls.
- Python router/resources needed: provider/model request fields only after Laravel validates tenant entitlement.
- Frontend components needed: tenant AI settings UI.
- Telemetry needed: no
- Acceptance criteria: tenant keys are encrypted, scoped, auditable, and never exposed to frontend.
- Risks/blockers: billing, support, provider abuse, key leakage.

### 16. AI-Assisted Data Entry / Imports

- Surface: client-facing
- Horizon: Later
- Write posture: draft/approval-required only
- Data exists today: partial. Bulk import templates exist; `ai_suggestions` can hold drafts.
- Laravel tools needed: draft suggestion creation/approval tools; import preview validation.
- Python router/resources needed: extraction/normalization prompt and strict schemas.
- Frontend components needed: review/approve UI.
- Telemetry needed: no
- Acceptance criteria: AI produces drafts; user approves before ERP writes.
- Risks/blockers: data quality and accidental writes.

### 17. Release Deliverables

- Surface: cross-cutting
- Horizon: Now tracked / Phase 7 delivered
- Write posture: documentation
- Data exists today: yes for implemented features only.
- Laravel tools needed: none.
- Python router/resources needed: none.
- Frontend components needed: screenshots and user flows.
- Telemetry needed: no
- Acceptance criteria: product, technical write-up, user guide, and marketing claims match actual shipped behavior.
- Risks/blockers: marketing overclaiming.

## Data-Dependency Matrix

| Feature | Required data | Exists? | Gating check |
|---|---|---:|---|
| Top sellers | `pos_transactions`, `pos_transaction_lines`, catalog item names | Yes | `php artisan ai:demo-readiness <tenant-id> --days=14` |
| Lagging items | Completed POS lines across two comparable windows | Yes | Same readiness check |
| Reorder candidates | Inventory balances + POS velocity | Yes | Confirm stock movements and completed POS sales |
| Sales summary | `grand_total`, `tax_total`, `discount_total`, `completed_at` | Yes | Compare tool output to POS reports |
| Restaurant analytics | `pos_transactions.vertical = restaurant` | Yes baseline | Confirm tenant uses restaurant vertical consistently |
| Retail analytics | `pos_transactions.vertical = retail` | Yes baseline | Confirm tenant uses retail vertical consistently |
| Profit summaries | `catalog_items.purchase_price` | Unknown | Purchase-price coverage query before enabling |
| Promotion recommendations | `pos_promotions.redemption_count`, sales velocity | Partial | Confirm promotion setup and redemption data |
| Advertising analytics | impressions/clicks/spend/campaign attribution | No | Must return explicit no-data response |
| E-commerce recommendations | storefront orders/product views/cart events | No in ERP | Define e-commerce integration contract |
| Admin alerts | `activity_events`, thresholds, module activity | Yes baseline | Define alert thresholds |
| In-house telemetry | opt-in aggregate tables/jobs | No | Build consent + aggregate store first |
| Super-admin reports | central telemetry aggregates | No | Telemetry phase required |
| BYO keys | encrypted tenant provider credentials | No | Design storage and policy |
| AI imports | import templates + draft suggestions | Partial | Build draft/approval path |

## NL2SQL Direction

Client-facing NL2SQL:

```text
natural language
→ module intent
→ schema/metric resources
→ typed tenant analytics query contract
→ Laravel validation/execution
→ Python narration/component
```

In-house NL2SQL:

```text
natural language
→ telemetry metric resources
→ central aggregate query contract
→ Laravel/central service execution
→ Python narration/component
```

Hard rules:

- No raw SQL from model output.
- Python/FastAPI must not connect to tenant databases.
- Laravel remains the only SQL/tool executor.
- Tenant queries must be validated against allow-listed tables, metrics, dimensions, filters, sorts, and limits.
- In-house queries must use central telemetry aggregates only.
- Unsupported or unsafe questions return a clarification/refusal, never guessed numbers.

The full contract should be planned in Phase 2.5 as `ai-planning/16-nl2sql-resources-and-query-contract.md`.

## Prioritized Backlog

### Now

- Validate POS top sellers, lagging items, reorder candidates, and sales summary on real tenant data.
- Add POS module router with restaurant/retail behavior.
- Add readiness checks for restaurant/retail sales volume.
- Track release deliverables against actual features.

Layer ownership:

- Laravel: tools, permissions, readiness command, audit.
- Python: POS router, deterministic suggestions, state handling.
- Frontend: existing components, later empty-state polish.

### Next

- Restaurant and retail analytics packs.
- Tax-aware revenue summary.
- Profit summary only after purchase-price coverage check.
- Product-promotion recommendations from sales velocity/redemption data.
- Admin alerts through draft `ai_suggestions` — only after module routers and analytics hardening, and only once thresholds/review UX are defined.
- Explicit AI access-level policy.
- NL2SQL resources and typed query contract doc.

Layer ownership:

- Laravel: new typed tools/query contracts.
- Python: module resources, query-spec generation, no-data/refusal rules.
- Frontend: analytics cards, empty state, suggestion review UI.

### Later

- Advertising analytics after ad-tracking schema exists.
- E-commerce recommendations after storefront/ERP contract exists.
- Opt-in telemetry and central aggregate store.
- Super-admin consolidated reporting.
- BYO client AI keys.
- AI-assisted data entry/imports as draft/approval workflow.

## Recommended Next Implementation Slice

Agreed order:

1. **Phase 2 — Module routers (Python).**
   - Create `pos`, `inventory`, and `catalog` routers in Python.
   - Move POS-specific prompt/suggestions/state logic out of generic `copilot.py`.
   - Fold restaurant/retail behavior into the POS router using `vertical`.
   - Keep the SSE and frontend contracts unchanged.
2. **POS analytics hardening.**
   - Add `vertical`/`branch_id`/date filters where missing on the POS tools.
   - Add the empty-state component (runtime allow-list + frontend renderer).
   - Validate against real tenant data (`php artisan ai:demo-readiness`).
3. **Phase 2.5 — NL2SQL resources and typed analytics query contract doc** (`ai-planning/16-nl2sql-resources-and-query-contract.md`): metric glossary, allowed dimensions/filters/sorts, typed query schema, Laravel validator/executor design, refusal behaviors, eval cases.
4. **First typed analytics query implementation** — POS only, read-only, contract-validated on both sides, no raw SQL from model output.

Admin alerts (item 11) intentionally come after all four steps.

## Do-Not-Claim List

Do not claim these in demos, technical write-ups, user guides, or marketing yet:

- Real streaming. The pipeline is still buffered end to end.
- Advertising analytics. No ad impressions/clicks/spend schema exists.
- Autonomous actions or auto-writes. AI can recommend or draft only.
- Profit margins until purchase-price coverage is verified.
- Cross-tenant insights until opt-in telemetry and central aggregates exist.
- E-commerce recommendations until the storefront/ERP integration contract exists.
- BYO AI keys until encrypted storage, entitlement, and audit controls exist.
