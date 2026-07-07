# Dataset Spec — `demo_restaurant`

Demo tenant for the July restaurant demonstration and restaurant evals. Story: **"Mama Kevina's Kitchen"**, a two-branch Kampala restaurant (Main — Kansanga; Branch — Ntinda), on the system for ~90 days.

## Menu (~40 items)

- 8 mains (e.g. luwombo chicken, beef stew, tilapia fillet, pilau) — UGX 15,000–35,000
- 6 fast movers (rolex, chips, chicken wings, samosas) — UGX 3,000–12,000
- 6 breakfast items, 5 sides, 4 desserts
- 8 drinks as **retail stockable items** (sodas, water, juice) — proves the mixed retail/restaurant catalog
- 3 catalog modifiers in use (extra sauce, portion size)

## Sales history (90 days of POS sale lines)

- Weekly rhythm: Fri/Sat ≈ 1.8× weekday volume; Sunday lunch spike.
- Daily rhythm: lunch peak 12:00–14:30 (~45% of covers), dinner peak 19:00–21:30.
- ~120 receipts/day Main, ~70/day Branch; average ticket UGX 28,000.
- **Deliberately lagging items (the demo's punchline):** 3–4 dishes with steady decline over the last 30 days (e.g. dessert line, one fish dish) so `pos_lagging_items` has a story.
- **One clear winner trending up** (rolex + chips combo) for `pos_top_selling_items`.
- A handful of supervisor-PIN comps and one refunded receipt (realistic audit noise).

## Inventory

- ~25 stockable ingredients + the 8 drink SKUs across 2 warehouses (one per branch).
- 4–5 items sitting **below reorder point** with recent outbound movement → `inventory_reorder_candidates` returns something interesting.
- 2 items with zero stock but active menu presence (the "no stock" eval case).
- 60 days of receipts/issues so `inventory_movements` has depth.

## Users & permissions

- Owner (full ERP), branch manager, 3 cashiers (register-only — must NOT see AI copilot answers beyond their permissions once enforcement is on), 1 kitchen display user.

## Non-goals

No pharmacy/patient data, no e-commerce storefront, no telemetry. Keep the tenant single-purpose for a clean demo.
