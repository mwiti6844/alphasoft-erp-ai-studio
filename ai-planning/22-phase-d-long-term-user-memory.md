# 22 — Phase D: Long-Term User Memory

**Date:** 2026-07-17
**Status:** Implementation note. No commits/pushes accompany this document.
**Companions:** doc 19 §3.C / §13 Phase D, doc 20 Phase B, doc 21 Phase C.

## 1. Scope Shipped

Phase D implements the first durable user-memory slice:

- tenant-scoped `ai_user_memories` table in Laravel
- allow-listed per-user preferences only
- inspect, set, delete-one, and delete-all tenant API endpoints
- chat requests include a read-only `user_memory` snapshot for the Python runtime
- Python injects only scalar allow-listed preferences into the system prompt and traces memory keys only

No inferred memories, no business facts, no raw tool outputs, and no silent writes are allowed.

## 2. Allowed Keys

The backend service allow-list is the contract:

- `preferred_module_scope`
- `default_branch_id`
- `default_warehouse_id`
- `default_reporting_period`
- `number_display`
- `answer_verbosity`

Values are validated per key. Unsupported keys return validation errors rather than being stored.

## 3. Ownership

Laravel remains the source of truth:

- stores and validates memories
- exposes inspect/clear APIs
- passes a snapshot to the runtime on each chat turn

Python is read-only:

- receives `user_memory`
- emits a `memory/user_memory` trace with keys only
- appends safe scalar preferences to the prompt
- never writes memory

Frontend did not change in this slice. The backend API is ready for a later settings UI; there is not yet a clean AI preferences settings surface in the current frontend.

## 4. Tests

Runtime:

- prompt injection includes supported scalar preferences
- nested/unexpected memory values are not injected
- memory trace includes keys only

Backend:

- users can set/list/delete only their own allow-listed memories
- invalid keys and invalid typed values are rejected
- chat forwards the memory snapshot to the runtime adapter
- Python runtime adapter includes `user_memory` in the `/api/chat` payload

## 5. Remaining Phase D Work

- Add a visible user-facing memory settings panel once the AI preferences location is agreed.
- Add `memory_update_proposed` event and confirmation UI only when the product wants assistant-suggested preference saves.
- Decide whether tenant admins need an organization-level opt-in before long-term memory is shown in the UI.
