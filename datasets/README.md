# datasets/

Specifications for demo/eval tenant data. These specs are the single source of truth for the backend seeders (WP5: `php artisan demo:restaurant-tenant` etc.) and for eval fixtures (`evals/*.yaml` reference them by name).

Rules:

- Specs here, seeder code in the backend. When the spec changes, the seeder PR links the spec change.
- Seeders must be idempotent and hard-refuse to run in production.
- Data must be plausible enough to demo: realistic names, prices in local currency context, believable seasonality. Agents invent unconvincing data unprompted — the narrative lives here so they don't have to.

| Spec | Fixture name | Used by |
|---|---|---|
| `restaurant-demo-tenant.md` | `demo_restaurant` | July demo, restaurant evals |
| `retail-demo-tenant.md` | `demo_retail` | retail/imports client story, retail evals |
