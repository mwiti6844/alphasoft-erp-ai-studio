# evals/inventory/

Golden fixtures for the inventory copilot, per `ai-planning/16` §9 and `ai-planning/19` Phase A. One file per fixture, named as doc 16 names them. These extend the base golden format (`evals/README.md`) with multi-turn conversations and scripted tool payloads.

## Extended format

```yaml
id: unique_snake_case_id
scope: inventory                  # module_scope the session is opened with
question: "single-turn message"   # OR turns: for multi-turn cases
turns:                            # multi-turn alternative to question
  - user: "message"
    expect: { ... }               # per-turn expectations (same keys as below)
scripted_tools:                   # fake-Laravel-client payloads for the runtime pytest runner
  - tool: tool_name               # matched in call order; match_input narrows when a tool is called twice
    match_input: { key: value }   # optional subset-match on the tool input
    output: { ... }               # contract-shaped payload (doc 16 §5) — test doubles are legal in evals ONLY
expect:
  tools_called: [tool_name]       # exact set (order-insensitive) the run must dispatch
  tools_not_called: []            # optional: forbidden tools
  grounded_numbers: true          # every number in the answer must appear in a tool payload
  must_mention: []                # substrings the answer must contain (use sparingly)
  must_not_mention: []            # hallucination tripwires
  no_write_language: true         # answer must not claim to have changed data
  clarification: true             # the turn must end in exactly one clarifying question, no arbitrary pick
  discloses: []                   # named honesty assertions, see below
  component: component_type       # component the turn must emit (omit = no assertion)
  state: { key: value }           # keys the state_patch must carry (subset match)
fixture: demo_restaurant          # tenant dataset for the future backend live harness (see datasets/)
```

**`discloses` vocabulary** (named honesty assertions — the runner/reviewer checks the substance, not exact wording):
- `movement_list_cap` — narration says the movement list is capped (last 20).
- `cover_basis` — narration states reorder basis = stock cover + sales velocity, not reorder points.
- `zero_stock_blind_spot` — narration notes the balance lookup only shows items with stock on hand.
- `read_only_alternative` — a refusal offers the adjacent read-only ask.
- `tenant_boundary` — a refusal names the tenant-data boundary.

## Rules

- Scripted payloads mirror the **frozen contracts** in doc 16 §5 exactly (field names, shapes). If a contract changes, these fixtures change in the same PR.
- Fixtures reference only tools that exist in `AiToolRegistry` today. Proposed tools (`inventory_low_stock`, `inventory_dead_stock`, `inventory_stock_cover`) have **no fixtures yet** — they arrive with Phase C once backend registers them (doc 18 protocol).
- `component` expectations for proposed components (`inventory_balance_table`, `inventory_movements_table`, `ai_empty_state`) are marked `once_shipped: true` — until those components exist, the turn renders text and the assertion is skipped.
- `component-contract.yaml` is a different kind of fixture: shared props payloads that must validate against both the runtime pydantic model and the frontend TS type.

## Runner

Planned: pytest goldens in the runtime with a scripted provider + fake Laravel client (doc 16 §9). **Does not exist yet** — until it does, these fixtures are the executable spec. The backend mirrors tool-level cases in its own feature tests using the `fixture` tenant datasets.
