# evals/

Golden test fixtures for AI behavior. A module is not "AI-enabled" until it has fixtures here (inheritance contract, `ai-planning/11` §1).

## Format

YAML files, one per module scope: `<scope>.golden.yaml`. Each case:

```yaml
- id: unique_snake_case_id
  scope: inventory            # module_scope the session is opened with
  question: "user message"
  expect:
    tools_called: [tool_name] # exact set (order-insensitive) the run must dispatch
    tools_not_called: []      # optional: forbidden tools
    grounded_numbers: true    # every number in the answer must appear in a tool payload
    must_mention: []          # substrings the answer must contain (use sparingly)
    must_not_mention: []      # e.g. hallucination tripwires
    no_write_language: true   # answer must not claim to have changed data
  fixture: demo_restaurant    # dataset the test tenant is seeded with (see datasets/)
```

## Runner

Does not exist yet (Phase B item 5, `ai-planning/11` §5). Planned: a backend feature-test harness that seeds the named fixture tenant, opens a session with the case's scope, plays the question through `LaravelHttpAdapter` with a **scripted fake provider** for deterministic CI, plus an optional live-model mode for prompt releases. Until then, these fixtures are the executable spec — write them first, before expanding AI behavior.

## The one assertion that matters most

`grounded_numbers: true`. The platform's core promise is that models narrate figures computed by SQL and never invent them. Every analytics case must carry it.
