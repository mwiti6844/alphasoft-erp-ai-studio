# 26 — AI Business Use Cases & Multi-Agent Responsibilities

> Working artifact for the action item: *"David Mwiti and Denis Kaka will define AI business use cases and the multi-agent setup to determine agent responsibilities."* (Retail POS Product Review, 2026-07-18.)
> Bring this to the David/Denis session. Companion to `25-multi-agent-write-capable-strategy.md` (the why) and `15-meeting-ai-product-backlog.md` (the backlog).
> Date: 2026-07-18. Status: proposal to agree, edit, or reject line-by-line.

---

## 1. The one decision to make first: one rule layer, not two

Denis is drafting **business rules for fraud controls, shift scheduling, and access management** this week. David is defining **AI use cases and multi-agent responsibilities**. These are not two workstreams — they share a spine.

**Proposal: there is ONE deterministic control layer (the BRE). The POS/ERP enforces it. AI consumes it.**

- The **BRE blocks and authorizes** (out-of-shift sale → blocked; high-value refund → requires supervisor auth; adjustment → requires manager). Deterministic. A model can never override it.
- The **AI detects, narrates, dedups, prioritizes, and drafts** *on top of* that layer. It never enforces and never applies a sensitive change directly.

If we get this wrong, we build a parallel rules engine in the AI runtime and the two drift. If we get it right, Denis's fraud rules and David's agents reference the same rule IDs, versions, and audit envelope. **This is the item to lock in the session.**

Clean line for demos and sales decks: **"The system enforces the rules; the AI watches, explains, and prepares the work."** Do not let AI be sold as the thing that *prevents* fraud — that oversells the model and hides that the real control is the BRE.

---

## 2. Capability levels (shared vocabulary)

Every use case and every agent below is tagged with one level. Launch (July) ships only the first two.

| Level | AI may… | Human role | July? |
|---|---|---|---|
| `read` | query, summarize, explain | reads | ✅ |
| `recommend` | rank, flag, suggest | reads/acts manually | ✅ |
| `draft` | create a reviewable `ai_suggestion` | approves/edits/rejects | ❌ post-July |
| `execute_w_approval` | apply an approved suggestion via a standard action | approves before apply | ❌ Phase C+ |
| `forbidden` | — | — | — |

---

## 3. Use-case catalog (agreed scope + readiness)

Ordered by when we should build, not by demo appeal. "Rules" = which of Denis's rule domains the use case consumes.

| # | Use case | Surface | Level | Data ready? | Consumes rules | Window | Owner split |
|---|---|---|---|---|---|---|---|
| U1 | POS/inventory analytics (top/lagging/summary/reorder candidates) | tenant | read/rec | ✅ (validate on real tenant) | — | **July** | David: agent · Denis: metric defs |
| U2 | **Investigation / audit copilot** — "who did what, when, at what cost"; user-mapped stock movements; filters cashier/item/warehouse | tenant (supervisor) | read | ⏳ logs being built this week | access/authority (read) | **July** | David: agent · Caleb/Victor: log data · Denis: what supervisors need |
| U3 | **Anomaly / alert narration** — one deduped, explained, reviewable alert per threshold breach | tenant (mgr) | rec (→draft later) | ⏳ thresholds this week | fraud + cadence thresholds | **July→Next** | Denis: thresholds · David: narration agent |
| U4 | Onboarding / setup wizard assistant — guided config + "how do I set up X" | tenant | read | partial (`knowledge/flows`) | access (read) | **Next** | David: agent · Victor: config steps |
| U5 | Restaurant / retail / tax-aware analytics packs | tenant | read/rec | ✅ baseline; profit gated on price coverage | — | **Next** | David · Denis: fiscal defs per country |
| U6 | Catalog data-quality steward (missing prices, dup SKUs, bad units) | tenant | draft | ✅ | catalog write rules | **Next→C** | David |
| U7 | Stock-take / GRN reconciliation — variance explain + adjustment drafts | tenant | draft | ⏳ corrections/GRN being built | inventory adjust + authority | **Phase C** | David: agent · Denis: adjust auth rules |
| U8 | Supplier invoice / delivery-note document intelligence (extract → 3-way match → draft) | tenant | draft | ❌ upload pipeline not built | payables + supplier rules | **Phase C** | David + backend |
| U9 | Credit / debtor management assistant — aging, credit-limit flags, draft reminders | tenant | rec→draft | ❌ credit module being documented | credit limit + consent/cadence | **Phase C** | Denis: credit module · David: agent |
| U10 | Demand / stockout forecasting (stats compute, LLM narrates) | tenant | rec | ✅ velocity data | — | **Phase C** | David |
| U11 | Reorder → draft Purchase Order | tenant | draft | ✅ candidates; ⚠ PO write-action unverified | procurement (supplier/budget/scope) | **Phase C** | David + backend |
| U12 | Per-tenant AI metering + recharge/limits (billable) | platform | read | partial (token tallies exist) | budget/spend | **Next** (commercial) | David + backend |
| U13 | Super-admin cross-tenant insights (opt-in anonymized aggregates only) | in-house | read | ❌ no aggregate store; legal gate | data-protection | **Phase D** | David + legal |

Do-not-claim (from `15`): real streaming, ad analytics, profit pre-readiness, cross-tenant insights, autonomous writes, BYO keys — until each is actually shipped.

---

## 4. Multi-agent responsibilities (the RACI the action item asks for)

Two planes: a **control plane** built once, and **specialists** plugged into workflows. Every agent has: a purpose, an allowed tool/data scope (= its permission boundary), an action level, the rules it consults, and its human gate. No specialist holds a write credential — writes only ever flow through the apply-flow.

### Control plane (build once, all modules inherit)

| Agent | Responsibility | Level | Human gate |
|---|---|---|---|
| **Orchestrator (S1)** | Decides which agent/tool/workflow runs next; owns multi-step state; opens suggestions/approvals; enforces step budget; escalates | — | opens approvals |
| **Governance gate (S6)** | Tenant isolation, permission-triple filtering, AI access tiers (end-user/admin/super-admin), budget check, audit completeness | — | blocks/escalates |
| **BRE evaluator** | Runs Denis's hard/soft rules; returns `pass/fail/warning/requires_approval` + audit refs | — | requires_approval routes to human |
| **Grounding verifier (S4)** | Every narrated number ⊆ tool payload; blocks invented figures | — | blocks |
| **Safety screen** | Screens user input, tool outputs, and uploaded docs as hostile until cleared (prompt-injection / doc-poisoning); quarantines uploads | — | blocks |

### Specialists (scoped, plugged into workflows)

| Agent | Owns use cases | Tools/scope | Level | Consults |
|---|---|---|---|---|
| **Analytics agent** | U1, U5, U10-narration | POS/inventory/catalog read tools | read/rec | — |
| **Audit/investigation agent** | U2 | activity-log + stock-movement read tools, scoped to supervisor role | read | access rules |
| **Anomaly agent** | U3 | threshold/alert-candidate read tools | rec | fraud thresholds |
| **Knowledge/onboarding agent (S2)** | U4 | module docs + config flows | read | access rules |
| **Catalog steward** | U6 | catalog read + draft-suggestion | draft | catalog write rules |
| **Reconciliation agent** | U7 | inventory read + adjustment-draft | draft | adjust + authority rules |
| **Document-intelligence agent** | U8 | upload pipeline + extract + draft | draft | payables/supplier rules |
| **Credit/AR agent** | U9 | receivables read + reminder-draft | rec→draft | credit + consent rules |
| **Procurement agent** | U11 | reorder read + PO-draft | draft | procurement rules |

---

## 5. The July slice vs after

**July (read-only, ship-safe, push to shared env):** U1 analytics (validated on real tenant) + **U2 audit copilot** + **U3 anomaly narration** (as thresholds land) + U4 onboarding starts. Control-plane pieces needed for read-only: Governance gate (access tiers) + Grounding verifier. No apply-flow, no BRE-write, no draft tools yet.

**Immediately after July (platform-ization):** apply-flow + BRE-write evaluation + Orchestrator + Safety screen + `/ai/approvals` UI + metering/recharge (U12). This is the gate that unlocks every `draft` use case.

**Phase C (first writes, reversible only):** reconciliation (U7) first, then catalog steward (U6), then document intelligence (U8) / credit (U9) / reorder-PO (U11).

---

## 6. Division of labor for the session

- **Denis owns the rule content:** fraud controls, shift scheduling, access management, adjustment authorization, credit limits — expressed as versioned hard/soft rules with IDs. These become the BRE the AI consumes.
- **David owns the AI layer:** the agents in §4, the read-only July slice (§5), the apply-flow + control plane, evals, metering.
- **Agree in the session:** (1) one shared rule layer, not two; (2) the July read-only slice = analytics + audit copilot + anomaly narration; (3) first write use case = reconciliation, not reorder/invoice; (4) metering/recharge is a billable feature; (5) rule IDs/versioning format so Denis's rules and David's agents reference the same objects.

---

## 7. Questions for Denis (bring to the session)
1. Will the fraud/shift/access rules be authored as structured, versioned rules (IDs, hard vs soft, override authority) so the AI can consume them — or as prose? (Argue for structured.)
2. Who is the approval authority per write level (adjustments, refunds, credit, POs)? Two-factor for high-value?
3. Is the credit/sales-order module firm enough to design the AR assistant against, or still moving?
4. For the July demo, is "AI flags, BRE blocks" an acceptable line to leadership, or is there pressure to show AI "doing" something?
5. Aggregated cross-tenant insight (U13) — start the DPIA/legal read now, or hold to Phase D?
