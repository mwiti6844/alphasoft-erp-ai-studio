# First AI Use Cases

## First Focus

The first AI focus should be **Inventory + Catalog Copilot**.

This is the best starting point because Catalog and Inventory are already live modules in Alphasoft ERP. They also provide practical data for safe, read-only AI assistance without requiring sensitive accounting or payment workflows.

## Phase 1: Read-Only Copilot

The copilot should answer questions using approved backend tools.

Initial questions:

- Which stockable items have no stock?
- Which catalog items are missing base unit of measure?
- Which catalog items are missing sale price or purchase price?
- Which products are active but not ready for inventory?
- Explain this product's stock position.
- Show recent stock movements for this item.
- Summarize stock by warehouse.
- Which warehouses have no bins configured?
- Which items have lot tracking but no expiry rules?
- Which items have serial tracking and recent movement activity?

## Phase 2: Recommendations

After read-only questions work, add recommendations.

Recommended tasks:

- Suggest reorder candidates.
- Suggest products that should use lot tracking.
- Suggest products that should use serial tracking.
- Suggest catalog cleanup actions.
- Suggest warehouse setup improvements.
- Highlight slow-moving stock.
- Highlight products with recent outbound movement but low available stock.

These recommendations should not mutate data.

## Phase 3: Draft Actions

After recommendations, allow AI to prepare drafts.

Possible drafts:

- Reorder plan draft
- Purchase request draft
- Stock receipt draft
- Stock issue draft
- Catalog cleanup task list
- Warehouse bin setup proposal

Drafts must be reviewed by a user before execution.

## Phase 4: Human Approval

Sensitive actions should require explicit human approval.

Approval-required examples:

- Post stock receipt
- Post stock issue
- Change inventory tracking settings
- Bulk update catalog fields
- Create purchase request
- Publish localization pack
- Create invoice
- Approve payment

The approval screen should show:

- What the AI wants to do
- Why it wants to do it
- Records affected
- Tool calls used
- Risks or assumptions
- Approve/reject buttons

## Phase 5: Document Intelligence

Once the action and audit architecture is stable, add document workflows.

Good candidates:

- Supplier invoice extraction
- Delivery note extraction
- Goods received note matching
- Supplier quote comparison
- Contract/policy Q&A
- Tax document review

The invoice-processing ADK sample is a strong reference pattern for this phase.

## Phase 6: Forecasting And Analytics

Later, add analytics-oriented agents.

Examples:

- Demand forecast
- Stockout risk forecast
- Supplier performance analysis
- Slow-moving stock analysis
- Gross margin analysis
- Sales trend explanations
- Natural-language reporting

The data-science and supply-chain ADK samples are useful references for this stage.

## Initial Success Criteria

The first AI milestone is successful when a tenant user can:

- Ask a natural-language inventory/catalog question.
- Receive a clear answer grounded in ERP records.
- See which records were used.
- See the tool calls behind the answer.
- Receive a safe recommendation.
- Avoid any unapproved write action.

## Example First Demo Script

User asks:

```txt
Which catalog items are stockable but not ready for inventory?
```

The copilot should:

1. Search active product and parts items.
2. Check base UoM, tracking settings, and stockability.
3. Return a grouped list of issues.
4. Explain why each issue matters.
5. Suggest cleanup steps.
6. Offer to prepare a draft cleanup task list.

No data should be changed during this first demo.
