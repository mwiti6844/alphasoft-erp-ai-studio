# Dataset Spec — `demo_retail`

Demo tenant matching the retail/imports client profile (cashier business + imported goods) and the cashew-vendor e-commerce story. Story: **"Kampala General Traders"**, single shop + small warehouse, ~90 days on system.

## Catalog (~120 items)

- Imported goods: kitchenware, electronics accessories, construction hand tools — UGX 5,000–450,000; several with `warranty_days` set (serial-tracked) to exercise retail warranty flows.
- Packaged foods incl. cashew nuts in 3 pack sizes (the e-commerce hero product).
- 10 items with incomplete setup (missing base UoM or sale price) → catalog-completeness copilot questions have real answers.

## Sales history (90 days)

- ~60 receipts/day; month-end spike (salary week ≈ 1.5×).
- Clear co-occurrence pairs for the recommender: cashews ↔ dried fruit; drill ↔ drill bits; phone case ↔ screen protector. Seed these deliberately — the SQL co-occurrence recommender demo depends on them.
- Top sellers stable; 5–6 slow movers with >60 days since last sale.

## Inventory

- 1 warehouse + shop floor location; 8 items below reorder point; 3 stockouts with recent demand (reorder story).
- Import receipts arriving in monthly batches (lumpy inbound movements — realistic for importers).

## Users

- Owner, 2 cashiers (register-only), 1 stock clerk.

## Non-goals

No restaurant/kitchen data. E-commerce order source flag on ~15% of sales (for later storefront analytics) is optional in v1 of the seeder.
