# Backend changes — Copilot reliability (2026-07-18)

**Repo:** `alphasoft-backend` · **Branch:** `feature/ai-runtime-backend-integration` · **Commit:** `198569f`
**File:** `app-modules/ai/src/Services/Adapters/PythonRuntimeAdapter.php`

## Summary
The Laravel → Python-runtime request serialized empty PHP arrays as JSON `[]`,
which broke the runtime request and Groq tool-calling. Fixed the serialization
at the request boundary.

## What changed
1. **`user_memory` and `conversation_state` are cast to objects** before the
   runtime call:
   ```php
   'user_memory'        => (object) $userMemory,
   'conversation_state' => (object) (is_array($session->context_json) ? $session->context_json : []),
   ```
2. **Tool definitions are normalized** through the existing
   `Modules\Ai\Support\AnthropicToolSchema::normalize()` helper via a new
   `normalizeToolDefinitions()` method, so a tool with no parameters encodes
   `"properties": {}` instead of `"properties": []`.

## Why (root cause)
In PHP an empty array `[]` serializes to a JSON **array**, not an object.

| Field | Symptom |
|---|---|
| `user_memory: []` | Runtime Pydantic model requires a dict → `422 Unprocessable Entity` (`Input should be a valid dictionary`). |
| `conversation_state: []` | Same 422 once `user_memory` was fixed. |
| tool `input_schema.properties: []` | Groq's strict JSON-schema validator rejects it (`'/properties' … expected object, but got array`). Anthropic tolerates it, so it only surfaced on Groq. |

The runtime returned an `event: error` SSE frame (HTTP 200) that the adapter
silently dropped, surfacing as the panel's "I could not generate a response."

## How to verify
1. Ensure Laravel talks to the runtime (`AI_RUNTIME_ADAPTER=python`,
   `AI_PYTHON_RUNTIME_URL`).
2. Send an inventory-scope chat that triggers a **no-argument** tool, e.g.
   *"List warehouses"* (calls `warehouse_list`, whose schema has no properties).
3. Expect a normal streamed answer with a rendered table — not a 422 or an
   empty "could not generate a response."

## Tests to add (follow-up)
- Unit test asserting `PythonRuntimeAdapter` serializes `user_memory` /
  `conversation_state` as `{}` when empty, and that tool `properties` encode as
  `{}`. (`AnthropicToolSchema` already has coverage in
  `tests/Unit/Ai/AnthropicToolSchemaTest.php`.)
