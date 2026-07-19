# 25 — From Read-Only Copilot to Governed Multi-Agent Platform

> Strategy pass. Owner: David Mwiti. Date: 2026-07-18.
> Companion to `11-ai-platform-master-plan.md` (the umbrella) and `15-meeting-ai-product-backlog.md` (the backlog).
> Written as a first heavy pass **before** the current meeting transcript is in. §12 marks exactly where transcript decisions slot in. Treat everything here as a proposal to stress-test, not a locked plan.

---

## 0. The hard truth first (read this before the vision)

We do not have a "read-only AI system that we now scale up to writes." We have a **read-only demo with the security spine still missing**, and the jump to writes is the moment every missing control becomes a production liability. Be honest about the starting line:

- **The write path does not exist.** `ai_suggestions` is a table with a full status workflow and **zero endpoints, zero UI, and nothing writing to it** (GAPS #11). Every "heavy AI use case" on our wishlist depends on a review/apply flow that is currently vapor.
- **There is no deterministic rule layer.** Today "safety" = the LLM is only handed read tools. The moment a tool can mutate ERP data, "the model chose well" is not a control. Akili already worked this out and built a **Business Rules Engine (BRE) as the deterministic spine** — "AI advises, BRE governs." We have nothing equivalent. This is the single biggest gap between us and a write-capable system.
- **Multi-agent today is one loop.** `runtime/app/agents/copilot.py` is a single ≤8-iteration tool loop with per-module *routers* (pos/inventory/catalog) that swap the system prompt and suggestion builders. That is good modular hygiene, but it is **not** multi-agent orchestration — there is no planner, no specialist delegation, no workflow state, no HITL pause/resume.
- **Streaming is faked, spend is unbounded, and provider failover is unimplemented** (GAPS #2, #3, #7). None of these block a demo; all of them block a launch that leadership was told has a "$10/tenant/day cap with automatic cutoff" that does not exist in code (GAPS #3).

So the real project is not "add write features." It is **"build the governance control plane, then let writes ride on it."** Everything below is organized around that inversion. If we add write tools before the control plane, we will have built the exact system OWASP calls out as *Excessive Agency* (LLM06:2025): excessive functionality, excessive permissions, excessive autonomy.

---

## 1. Where we actually are (grounded snapshot, 2026-07-18)

**Backend (`alphasoft-backend`, canonical):** 9 tools, all read-only — `catalog_search`, `catalog_item_detail`, `inventory_balance`, `inventory_movements`, `warehouse_list`, `inventory_reorder_candidates`, `pos_top_selling_items`, `pos_lagging_items`, `pos_sales_summary`. Each implements `AiToolContract` (name / moduleScope / permission triple / JSON schema / execute). Dispatch goes through `AiToolRegistry::dispatch` (permission gate + `ai_tool_calls` audit row). Permission enforcement now defaults **on** (GAPS #1 closed). Unknown model IDs now throw instead of silently routing to Anthropic (GAPS #9 closed).

**Runtime bridge (shipped, per `brain.md` 2026-07-17):** Laravel `PythonRuntimeAdapter` → Python FastAPI runtime over an **MCP-shaped internal HTTP gateway** (`/api/internal/ai/mcp/*`), authed by a shared secret (`X-AI-RUNTIME-TOKEN`), short-lived runtime sessions minted in cache carrying `{user_id, tenant_id, domain, permissions, ai_session_id, module_scope}`. Five invariants already locked: Python never opens a tenant DB; browser never calls Python; user Sanctum token never leaves Laravel; every tool run audited under the real user; python adapter forces `AI_ENFORCE_PERMISSIONS=true`. **This is the most important thing we've built** — it is the seam every future agent plugs into.

**Runtime internals:** provider-neutral LLM layer (Anthropic + Groq, factory + fallback provider), module routers (`pos`/`inventory`/`catalog`) with allow-listed component types and deterministic suggestion builders, ordered text/component blocks, a small knowledge/flow retrieval helper. Durable memory via `ai_sessions` + `ai_messages` (+ `context_json`) and `ai_user_memories` (explicit prefs only).

**Frontend (`alpaerpfrontend-1`):** `AiPanel` + `AiComponentRenderer` render an **allow-listed** component registry (tables/cards/suggestions), thread list, SSE stream parser. No `/ai` studio pages yet.

**Net:** the *plumbing* for governed AI is unusually good for this stage. The *governance content* (rules, approvals, write tools, safety screening, budgets, orchestration) is mostly not built. That is the opportunity.

---

## 2. The core move: a governance control plane, borrowed from Akili and adapted to ERP

Akili (the NCBA sales-agent sister project) is 6 months ahead of us on exactly the problem we're about to hit: **letting AI act in a regulated, auditable, human-gated way.** We should steal its spine wholesale and adapt the nouns from "prospect/RM" to "ERP record/operator." Its model is six shared services (S1–S6) sitting across every workflow phase, eight guardrails, and a BRE. Mapped to AlphaSoft:

| Akili service | AlphaSoft ERP equivalent | Build state | Where it lives |
|---|---|---|---|
| **S1 Orchestrator** — routes/sequences/escalates, owns workflow state, opens approvals | **ERP Orchestrator** — decides which agent/tool/workflow runs, tracks multi-step state, opens `ai_suggestions`, escalates | none (single loop today) | Python runtime |
| **S2 Knowledge** — cited product/policy Q&A | **ERP Knowledge** — how-to/process Q&A over module docs + config ("why can't I…", "how do I set up a warehouse") | partial (`knowledge/flows.py`) | Python runtime + Laravel docs |
| **S3 Comms/Draft Studio** — drafts, never sends | **Draft Studio** — produces the *content* of a suggestion (PO lines, catalog rows, price change), never applies | none | Python runtime |
| **S4 Non-Hallucination** — verifies every figure/claim traces to a source | **Grounding Verifier** — asserts every number in narration ⊆ tool payload; blocks invented figures | convention only ("SQL computes, models narrate") — not enforced in code | Laravel (cheapest) + eval |
| **S5 QA** — golden-set + schema checks, blocks release | **Eval Harness** — per-module golden Q&A, tool-trajectory, narrative-grounding, run in CI | specced (`evals/`), thin | AI studio repo CI |
| **S6 Governance** — DPA/consent/suitability/least-privilege/audit gate | **Governance Gate** — tenant isolation, permission triples, PII posture, budget, audit completeness, DPPA/DPA | scattered across middleware + registry; not a named layer | Laravel |

**And the BRE — the piece we do not have at all.** Akili's rule: *"AI advises; BRE governs. Hard rules cannot be overridden by the model. Soft rules can be overridden only by an authorized human with a logged reason."* For ERP this becomes a small, deterministic **policy layer that every write suggestion must pass before it can be applied**, returning the exact contract Akili uses:

```json
{
  "rule_set": "inventory_write",
  "rule_version": "1.0.0",
  "decision": "pass | fail | warning | requires_approval",
  "hard_failures": [],
  "soft_warnings": [],
  "required_approvals": ["role:inventory_manager"],
  "explanations": [],
  "audit_refs": []
}
```

Concrete ERP hard rules for launch scope: *no stock write that drives a balance negative; no price change beyond ±X% without manager approval; no PO to a supplier not on the approved list; no write outside the operator's branch/warehouse scope; no bulk write above N rows without escalation; no apply without a matching permission triple.* These are **code, not prompts** — a typo'd model output can never bypass them.

Why borrow rather than invent: Akili already paid the design cost, its docs are in-repo (`docs/research/shared_services_guardrails_bre_design.md`, `infosec_control_register.md`, `agent-cards/`), and reusing its vocabulary means the two products share a governance language when leadership reviews both. [Confidence: high that the pattern transfers; medium on how much Akili *code* we can literally reuse — Akili is Azure/PostgreSQL/Python, we are Laravel/MySQL, so we reuse the *design*, not the classes.]

---

## 3. The capability ladder (this is the whole game)

`03-ai-module-architecture.md` already defines five action levels. Make them the **explicit, enforced spine** of every tool, mapped to the OWASP LLM06 root causes so the security story is legible to any reviewer:

| Level | What AI may do | OWASP LLM06 control | Gate required |
|---|---|---|---|
| `read_only` | Query, aggregate, narrate | limit *functionality* — read tools only | permission triple + audit |
| `recommendation` | Rank/suggest, no state proposed | same | + "recommendation, not instruction" framing |
| `draft` | Produce a reviewable `ai_suggestion` (rows, PO, price) | limit *autonomy* — human applies | + BRE pass + apply-flow |
| `execute_with_approval` | Apply an approved suggestion via an approved backend action, idempotently | limit *permissions* — scoped service action, least privilege | + challenge-response approval + rollback + idempotency key |
| `forbidden` | never | — | hard rule |

**Launch discipline:** ship `read_only` + `recommendation` now (we mostly have it), make `draft` the entire Phase B focus (build the apply-flow once, every module inherits), and treat `execute_with_approval` as Phase C+ — and even then only for **reversible, low-blast-radius** actions first (catalog row create, stock adjustment draft), never for money movement or anything irreversible until the audit-replay and rollback story is proven. This is the opposite of "let the agent do things"; it is "let the agent *propose*, make proposing safe, then widen the aperture one reversible action at a time."

The failure mode to design against, stated plainly: **the demo pressure to show "AI created a purchase order" will push us to skip `draft` and wire a write tool directly.** That is the single decision that turns this from a governed platform into the liability OWASP describes. The rule for the team: *no write tool ships without going through `ai_suggestions` + BRE + approval. No exceptions, same as the "tools never SQL-from-prompts" rule.*

---

## 4. Multi-agent architecture (what "multi-agent" should actually mean here)

The research (Microsoft Agent Framework, Google ADK, Akili's synthesis) converges on one rule worth tattooing on the runtime: **use a workflow/state-machine where the steps are known; use an agent where the work is open-ended; use code/BRE for anything deterministic; make human approval a first-class workflow node — not a UI afterthought.** We should *not* build "a swarm of free-running agents." We build a **governed workflow with specialist agents plugged in at specific points** (Akili's exact conclusion, and ADK's `workflows-HITL_concierge` / `supply-chain` orchestrator pattern).

### Proposed agent roster (each is a small, scoped unit — an "agent card")

Borrow Akili's **agent-card** discipline (`docs/agent_card_template.md`): every agent has a declared purpose, allowed tools, allowed data scope, action level, escalation rules, and evals. Roster for AlphaSoft:

**Control plane (built once):**
- **Orchestrator** (S1) — the only thing that decides "what runs next." Determines module + intent, picks a workflow or a specialist, tracks state, opens suggestions/approvals, enforces the iteration/step budget, escalates. Replaces the "the copilot loop just keeps calling tools" model.
- **Grounding Verifier** (S4) — post-processes any narrated numbers against tool payloads; blocks/downgrades unsupported claims. Cheap, deterministic, high trust value. Directly modeled on ADK `llm-auditor` (extract claim → verify against source → block/rewrite).
- **Safety screen** (global hooks) — modeled on ADK `safety-plugins`: interception points **before** user input is trusted, **before** a tool call, **after** a tool result, and **before** a suggestion is created. Treats every tool output and every uploaded document as hostile until screened (OWASP prompt-injection / document-poisoning). Enforced in orchestration, not just at the API edge.

**Specialists (per module, plugged into workflows):**
- **Analytics agent** (read/rec) — what we have today (POS/inventory/catalog analytics). Keep.
- **Reorder/Procurement agent** (rec→draft) — turns reorder candidates into a *draft PO suggestion*.
- **Document-intelligence agent** (draft) — supplier invoice / delivery note → extracted, validated draft rows (ADK `invoice-processing` 9-stage pipeline: classify → extract → 4-phase validate → transform → audit; "human approval always").
- **Data-quality / Catalog-steward agent** (rec→draft) — finds missing prices, duplicate SKUs, bad units; drafts cleanup suggestions.
- **Reconciliation agent** (draft) — stock-take vs system balance; drafts adjustment suggestions with variance explanations.
- **Forecasting agent** (rec) — classical stats in a job, LLM narrates only (never LLM math). Demand + stockout risk.
- **Knowledge/how-to agent** (S2, read) — process Q&A over module docs.

Each specialist **only ever proposes through the apply-flow**; none holds a write credential of its own. Least-privilege is structural: the agent's tool list *is* its permission boundary.

### Where the runtime already supports this — and the one refactor needed

`app/agents/modules/registry.py` + `base.py` already give us a per-scope router with allowed components and suggestion builders. The multi-agent upgrade is: (1) add an **Orchestrator** above the routers that can call a specialist *as a tool* (ADK "AgentTools" pattern), (2) add **workflow state** (`active_workflow`, `step`, `pending_approval_id`) to the conversation state we already persist, and (3) add a **HITL pause/resume** primitive so a workflow can stop at "needs approval" and be resumed by an approval event from Laravel. We do **not** need to adopt ADK/Google as a dependency — Akili reached the same "borrow the patterns, keep our own FastAPI orchestration" conclusion. [Confidence: high — this is an additive layer over the existing seam, not a rewrite.]

---

## 5. The write path in detail (the one feature everything depends on)

Build this **once**, generically, in Phase B. Every draft/execute use case rides it.

```
Agent (Draft Studio, S3)
  → proposes ai_suggestion { type, module, payload(rows/PO/change), rationale, source_tool_calls[] }
  → BRE evaluation (hard/soft rules)  ── hard fail → blocked, explained, audited
  → S4 grounding check (figures ⊆ evidence) ── fail → blocked
  → status = draft, opened in /ai/approvals
Human reviewer (challenge-response, not a naked "Approve?")
  → sees: intent · source evidence · expected result · blast radius · rollback plan · permissions chain
  → approve / edit / reject (+reason)   ── every decision audited (actor, timestamp, before/after)
On approve
  → apply via an APPROVED backend action (the same service the UI uses — never a raw AI-only writer)
  → idempotency key (we already send Idempotency-Key headers per frontend CLAUDE.md)
  → RecordsActivity event + ai_suggestion.applied_at + audit envelope
  → reversible actions carry a stored rollback handle
```

**Challenge-response approval** (from 2026 HITL best practice): replace "Approve?" with a checklist the approver must positively acknowledge — *intent, data lineage, permissions chain, expected blast radius, rollback plan.* For anything touching spend/pricing/regulated data, require it item-by-item, and consider two-factor judgment (second approver or a counter-model sanity check) for high-value writes.

**Audit envelope** (adopt Akili's schema): `correlation_id, actor_type{human|agent|system}, actor_id, action, target_type, target_id, input_digest, output_digest, source_ids, rule_version, model_alias, prompt_version, approval_id, result`. The test that proves it works is **audit replay**: reconstruct a full "AI drafted → human approved → applied → (rolled back)" journey from the event store alone. Make that a release gate.

---

## 6. Security is everything — the concrete control set

Organized as the three layers Akili's infosec register uses. This is what "security is everything" has to actually mean in code, not slideware.

**A. Tenant & identity (the worst-possible-bug layer)**
- Tenant isolation stays sacred: Python never opens a tenant DB; Laravel is the only door; runtime session carries domain + user and Laravel re-asserts tenancy on every MCP tool call (already true — protect it with tests, never "optimize" it away).
- Least-privilege tools: an agent's declared tool list is its whole capability. No "admin" agent. Cross-tenant / central-admin AI is a **separate context** (separate routes, tokens, prompts) — never the same runtime reaching across tenants.
- **AI access tiers** (backlog #14): end-user vs client-admin vs super-admin tool sets, filtered **before** definitions reach Python, so a cashier's copilot cannot even see a manager's tools.

**B. Model/agent behavior layer**
- **Prompt injection / document poisoning:** treat every tool result *and every uploaded document* (invoices, spreadsheets) as hostile until screened. Never let untrusted content drive a write without passing the safety screen. Quarantine uploaded docs before they touch durable memory (ADK "do not store untrusted content into session memory before screening").
- **Grounding/non-hallucination:** enforce "numbers in narration ⊆ tool payload" in code (S4), not just as a prompt convention. Withhold profit/margin until purchase-price coverage passes a readiness check (already flagged in backlog #7).
- **Excessive agency defense:** the capability ladder (§3) *is* the control — functionality/permissions/autonomy each bounded and separately gated.
- **BRE hard rules** as the deterministic backstop the model cannot argue past (§2).

**C. Platform & spend layer**
- **Spend controls (GAPS #3, HIGH):** per-tenant daily token/cost cap + kill switch, checked before the adapter runs. Leadership was promised this exists; make it exist before any pilot with real tenants.
- **Provider router (GAPS #2, WP2):** failover + metering + circuit breaker; fixes the "non-Anthropic model crashes" bug that currently blocks the whole multi-model strategy.
- **Deploy safety (GAPS #4):** `push to main = production deploy` is genuinely dangerous now that coding agents commit frequently. Gate it (environment protection / `workflow_dispatch`) before we scale agent-generated changes.
- **Secrets:** shared runtime secret and provider keys never reach the browser; production rejects placeholder secrets (already true) — keep BYOK (per-tenant keys) encrypted and server-side only.

**Release gates (adopt Akili's list, trimmed to us):** DPIA/DPA readiness (Uganda DPPA / Kenya DPA), human-in-loop path tested, BRE sign-off, audit-replay test passed, grounding tests passed, permission-denial tests passed, spend-cap exhaustion test passed. No write feature pilots with a real tenant until its gates are green.

---

## 7. New business cases (the "heavy" use-case menu)

Grouped by how hard the governance is, not by how flashy the demo is. Each maps to an agent from §4 and a level from §3. **★ = strong candidate to build first because data exists and blast radius is low.**

**Tier 1 — draft-level, reversible, data mostly exists (build after apply-flow):**
- ★ **Reorder → draft Purchase Order.** We already compute `inventory_reorder_candidates`. The heavy step is drafting a PO suggestion (supplier, qty, expected cost) a human approves. Reversible (delete draft PO). Highest-value, lowest-risk first agent. Maps to ADK `supply-chain` + `order-processing` HITL.
- ★ **Catalog data-quality steward.** Missing purchase prices, duplicate SKUs, unmapped units, empty categories → batched cleanup suggestions. Unblocks profit reporting (backlog #7). Reversible.
- ★ **Stock-take reconciliation.** Operator enters counted quantities; agent explains variances and drafts adjustment suggestions with reasons. Reversible; huge time-saver for retail/pharmacy.
- **Supplier invoice / delivery-note document intelligence.** Photo/PDF → extracted lines → 3-way match against PO + goods-received → draft GRN or payable. This is the ADK `invoice-processing` pattern (classify→extract→validate→audit, human approval always). High value, higher risk (document poisoning, money-adjacent) — do it *after* the safe drafts prove the pipeline.

**Tier 2 — recommendation-level, no writes, needs data readiness:**
- **Demand & stockout forecasting** (classical model narrates via LLM). Inventory + POS velocity exist.
- **Pricing / margin guard.** Flags items sold below cost, margin drift, discount leakage. Read-only alerting first; price-change *drafts* later behind a ±X% BRE rule.
- **Restaurant / retail analytics packs** (already in backlog #5/#6) — daypart, menu-mix, basket analysis.
- **Promotion effectiveness** (backlog #8) from redemption + velocity (explicitly *not* ad ROI — no ad schema exists; the do-not-claim list matters).
- **Pharmacy expiry & slow-stock alerts** (RO/REC only — clinical/interaction logic stays assist-only pending pharmacy-owner review).

**Tier 3 — needs new foundations (design now, build later):**
- **Admin alerts / anomaly detection** (backlog #11) — dedup'd, threshold-based, one reviewable suggestion per breach (not a stream). Blocked on threshold + review-UX design.
- **Month-end / close assistant** — reconciliations, anomaly flags, narrated P&L. Accounting module isn't AI-enabled yet.
- **Multi-branch stock-transfer agent** — proposes transfers to balance stock across branches. Draft-level, cross-branch BRE rules.
- **Collections / AR assistant** — prioritizes overdue receivables, drafts reminders (draft-only, consent-gated — reuse Akili's comms guardrail).
- **Super-admin cross-tenant insights** (backlog #12/#13) — **opt-in anonymized telemetry only, central aggregate store, never live tenant DBs.** Hard legal gate.
- **Cross-vertical agent packs** (hotels, fuel, clinics, salons) — each is a tool pack + demo dataset + evals, *not* new platform work. That reuse is the entire payoff of the inheritance contract.

**The honest sequencing recommendation:** apply-flow + BRE → Reorder-to-PO draft → Catalog steward → Reconciliation → then document intelligence. Resist starting with invoice OCR because it's the most impressive demo — it's also the highest blast radius and the most exposed to document-poisoning. Earn it.

---

## 8. Three multi-agent workflows, spelled out

These make "multi-agent workflow" concrete and reviewable. Each is a **workflow (known steps) with agents plugged in and a human node**, not a free-running swarm.

### 8.1 Reorder-to-PO (the flagship first workflow)
```
Orchestrator (S1)
  → Analytics agent: inventory_reorder_candidates(scope=operator's warehouses)   [read]
  → Forecasting agent (optional): stockout risk to rank urgency                  [read]
  → Procurement agent: draft PO lines per supplier (qty, indicative cost)        [draft]
  → BRE: approved-supplier? within budget band? branch scope? qty sane?          [hard/soft]
  → S4: every figure traces to a tool payload                                    [verify]
  → HITL PAUSE → /ai/approvals: challenge-response (intent, spend blast radius, rollback=delete draft)
  → on approve → apply via standard PO-create action + idempotency key + audit    [execute_w_approval]
  → P8-style outcome capture feeds eval/learning
```

### 8.2 Supplier-invoice to payable (Phase C, higher governance)
```
Orchestrator
  → Safety screen: quarantine + content-safety on the uploaded document          [global hook]
  → Document-intelligence agent: classify → extract lines (ADK invoice pipeline)  [draft]
  → Matching (Laravel, deterministic): 3-way match invoice ↔ PO ↔ goods-received  [code, not LLM]
  → BRE: totals within tolerance? supplier/tax valid? no duplicate invoice no.?   [hard]
  → S4: extracted numbers ⊆ document + match result
  → HITL PAUSE → approval (item-by-item for amounts; second approver over threshold)
  → on approve → draft payable (never auto-pay; money movement stays human)
```

### 8.3 Stock-take reconciliation (retail/pharmacy, reversible)
```
Orchestrator
  → operator submits counted quantities (typed, validated by Laravel)
  → Reconciliation agent: compute variances, cluster by likely cause (shrinkage/miscount/unit error)  [draft]
  → BRE: variance within auto-explain band vs requires-manager escalation
  → HITL PAUSE → approval of adjustment suggestions (with narrated reasons)
  → on approve → apply stock adjustments via standard action + audit; rollback handle stored
```

---

## 9. What this changes in the existing roadmap (delta, not rewrite)

The `11`-master-plan phases stay. Insert the control plane as the backbone of Phase B and gate Phase C writes on it:

- **Phase B (was: apply-flow + studio + extraction pilot).** Add explicitly: **(1) BRE v1** (inventory/catalog hard+soft rules, the evaluation contract), **(2) Orchestrator + HITL pause/resume** in the runtime, **(3) Safety screen + Grounding Verifier** as global hooks, **(4) challenge-response approval UI** at `/ai/approvals` with the audit envelope + audit-replay test. Apply-flow is no longer "an endpoint" — it's the whole governed write pipeline.
- **Phase C (was: python runtime + forecasting + telemetry).** First multi-step agent = **Reorder-to-PO (§8.1)**, not invoice OCR. Invoice document-intelligence lands *after* Reorder proves the pipeline. Forecasting agent (stats + narration) in parallel. Telemetry only post-legal.
- **Phase D.** Cross-vertical agent packs as sellable modules; central-admin cross-tenant AI on aggregates; procurement multi-agent chains.

Cheap wins to pull forward regardless (they de-risk everything): spend cap + kill switch (GAPS #3), provider router (WP2), deploy-to-main gate (GAPS #4), grounding check in code (S4). None require the transcript to start.

---

## 10. What we should explicitly NOT do (guardrails against our own hype)

- No autonomous sends or auto-writes of anything, ever, at current maturity. AI proposes; humans apply. (Matches the vision doc and the do-not-claim list.)
- No raw SQL from model output. Laravel stays the only executor; NL2SQL, when it comes, is a *typed, allow-listed query contract* validated on both sides — not free SQL.
- No LLM doing arithmetic that becomes a business figure. SQL/stats compute; the model narrates.
- No write tool that bypasses `ai_suggestions` + BRE + approval — same non-negotiable status as tenant isolation.
- No claiming capabilities we haven't shipped (real streaming, ad analytics, profit margins pre-readiness, cross-tenant insights, BYOK) — the do-not-claim list in `15` is a marketing safety rail, keep it.
- No adopting Google ADK / Azure Foundry Agent Service as a hard dependency to get multi-agent — we borrow patterns; our seam already supports it.
- No swarm of free-running agents. Governed workflow + plugged-in specialists + human nodes.

---

## 11. Assumptions & confidence

- The MCP runtime bridge in `brain.md` (2026-07-17) is real and merged. [Confidence: medium — `brain.md` says "all current AI work remains uncommitted" as of 2026-07-15 in doc 15; verify branch state before building on it.]
- `ai_suggestions` still has no apply endpoints/UI. [Confidence: high — consistent across GAPS, master plan, and backlog.]
- Akili's governance design transfers to ERP; its *code* mostly does not (different stack). [Confidence: high on design, high on the code caveat.]
- OWASP LLM06 (excessive agency = functionality/permissions/autonomy) is the right external framing for the read→write jump. [Confidence: high.]
- Reorder-to-PO is the right first write workflow (data exists, reversible, high value). [Confidence: medium-high — depends on whether the PO/purchasing module has a stable create action to reuse; unverified in this pass.]
- Data readiness for POS/inventory analytics is real; profit/forecasting/telemetry are gated on checks. [Confidence: high — backlog's data-dependency matrix is explicit.]

**Unverified in this pass (worth a follow-up dig):** the purchasing/PO module's existing write actions; whether an upload/document pipeline exists yet; current `evals/` coverage depth; whether `AiSuggestion` model columns match the challenge-response fields (rollback handle, blast-radius metadata).

---

## 12. Feed the meeting transcript in here

When the transcript lands, slot decisions into these open questions (the ones that actually change the plan):

1. **First write use case** — is leadership pulling toward Reorder-to-PO, invoice OCR, or something from the transcript? (I argue Reorder first; invoice is the riskier crowd-pleaser.)
2. **BRE ownership** — who authors/signs off ERP hard rules (pricing bands, approved suppliers, branch scope)? Akili routes this to product/pricing owners; who is our equivalent?
3. **Approval authority model** — which roles approve which write levels? Two-factor for spend?
4. **Verticals in scope** — restaurant + retail confirmed; is pharmacy/hotel/fuel entering the near-term packs list?
5. **Telemetry / cross-tenant** — is there appetite (and legal cover) to start the DPIA now, or is it firmly Phase D?
6. **Timeline pressure** — does end-July still mean "read/rec demo," with writes explicitly Phase B/C? (Strongly recommend yes.)
7. **New business cases raised in the meeting** — capture verbatim into §7's tiers and tag each with level + data readiness.

Add a §13 changelog entry when the transcript is integrated so we can see what the meeting actually moved.

---

## 13. Transcript integration — Retail POS Product Review, 2026-07-18

The meeting was 80% POS-sellability, ~15% tax integration, ~5% AI. That ratio is itself the most useful signal: **the room's appetite is "sell a limited-but-usable product now, co-create with early customers," targeting July 31.** Writes are not a July conversation. That validates the capability-ladder discipline in §3 — but the transcript also moved three things and added five use cases.

### 13.1 What the transcript confirmed
- **Multi-agent is now a named deliverable.** Action item: *"David Mwiti and Denis Kaka will define AI business use cases and the multi-agent setup to determine agent responsibilities."* This doc is the first draft of David's half; `26-ai-use-cases-and-agent-responsibilities.md` is the shared working artifact for the Denis session.
- **Per-user / per-org data scoping** was called out in the AI demo — that is exactly the **AI access tiers** in §6A (filter tool defs before they reach Python). Already on the list; now leadership-visible.
- **Foundry + per-tenant tracking + "billing/token recharge for clients"** were raised commercially. That makes the spend router/metering (GAPS #3, WP2) not just a safety control but a **revenue mechanic** — recharge/limits are a billable feature, not only a cost brake. Elevate accordingly.
- **July 31 = sellable POS + read-only AI pushed to shared env + setup wizard.** No writes. Confirms: ship read/rec now, `draft` is post-July.

### 13.2 What moved — the BRE just got an owner (the key insight)
In §2 I argued the BRE (deterministic rule layer) is our biggest missing piece and pitched it abstractly. The transcript makes it concrete: **Denis is drafting "business rules for fraud controls, shift scheduling, and access management" this week** — out-of-shift sale blocks, admin authorization for sensitive actions, HR-linked access, excessive-return / high-value-refund thresholds, notification triggers.

**Those rules *are* the BRE content.** The sharp recommendation: **AI must consume the same rule layer Denis is building for POS fraud/access control — do not let the AI workstream build a parallel rules engine.** David's "AI use cases + multi-agent" task and Denis's "business rules" task should converge on **one shared policy artifact**: the POS/ERP control layer blocks and authorizes; the AI layer detects, narrates, dedups, and drafts *on top of it*. This is the single most important cross-workstream decision coming out of the meeting.

Corollary caution to raise out loud: the room wants **fraud *controls*** — blocks, thresholds, authorization. Those are deterministic BRE, **not AI**. AI detects and explains anomalies; the BRE/POS enforces. If we let "AI" get sold as the thing that *prevents* fraud, we oversell the model and under-build the actual control. Keep the line clean: **BRE blocks, AI flags.**

### 13.3 New / re-prioritized use cases from the transcript
1. **Investigation / audit copilot (read-only) — promote to July-safe slice.** The room repeatedly asked for comprehensive time-stamped activity logs, a single downloadable investigation view, and **stock movements mapped to individual users** with filters (cashier / item / warehouse / cost-at-time). That data is being built this week anyway (Caleb + Victor action items). A read-only "who did what, when, at what cost" copilot over those logs is low-risk, high-value, and serves the supervisor/fraud pain the room cared about most. Strong candidate to demo alongside analytics.
2. **Anomaly / alert narration (read-only now, draft later) — pull forward from Tier 3.** Denis is defining the thresholds this week. AI surface = take a threshold breach (excessive returns, high-value refund, out-of-shift attempt) and produce **one deduplicated, explained, reviewable** alert — not a stream. Hard blocks stay in the BRE; AI only narrates/prioritizes. Backlog #11 was blocked on "threshold definitions + review UX"; the transcript unblocks the thresholds.
3. **Credit / debtor management assistant (draft, later).** Big chunk of the meeting: sales-order model, partial payments, credit limits, debtor aging. AI use case = AR/collections assistant — prioritize overdue, narrate aging, flag credit-limit breaches, draft reminders (consent-gated, reuse the "draft never send" guardrail). Depends on the credit/sales-order module Denis is documenting.
4. **Delivery-note / GRN / adjustment reconciliation (draft, post-July).** Michael requested delivery-note support, adjustment authorization, and GRN-after-receipt; Victor showed a "corrections" feature (posted 10 → actual 8). This is precisely the **reconciliation agent (§8.3)** and the reversible-adjustment surface. Strengthens my §7 pick of reconciliation as an early write workflow — the surface is being built now.
5. **Setup / onboarding wizard agent (read/guided).** David committed to a setup wizard next week. The S2 knowledge/how-to agent (partially exists in `knowledge/flows.py`) is the natural home — guided config + "how do I set up X" during onboarding.

### 13.4 Revised sequencing recommendation (given July 31 + sellability)
- **July (ship-safe, read-only):** keep POS/inventory analytics; **add the investigation/audit copilot** over the new user-mapped logs and **anomaly narration** consuming Denis's thresholds. Both are read-only, ride data being built anyway, and hit the meeting's dominant pain (supervisor control / fraud visibility). Push to shared env as committed.
- **First write workflow (post-July):** the transcript adds two contenders to my §7 pick — **reconciliation/GRN** and **credit/AR**. Reconciliation stays my recommendation (reversible, surface being built via corrections/GRN work, low blast radius). **Reorder-to-PO drops in confidence** — purchasing wasn't a meeting focus and the PO module's write-action maturity is unverified; retail sellability is where the energy and data are.
- **Commercial:** treat per-tenant metering + recharge/limits as a **billable feature** (Foundry-backed model access + centralized monitoring), not just a cost cap. It's the "how do clients pay for AI" answer the room was reaching for.

### 13.5 Items explicitly out of the AI workstream (but noted)
Tax integration (IFRIS/ETIMS/KRA), the integrator-vs-self-integrate business decision, hardware procurement, and POS UX redesign are not AI work. One future AI hook worth parking: once fiscal receipts + QR mapping exist, a **fiscal reconciliation / tax-anomaly** read-only agent could sit on top — but only after the integration itself is certified. Do not build ahead of it.

> Net: the transcript did not contradict this doc; it gave the BRE an owner, made metering a revenue feature, and surfaced two read-only use cases (audit copilot, anomaly narration) that fit the July window better than anything write-based. The action item David co-owns is captured in doc `26`.
