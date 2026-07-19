# 27 — BRE Rule Schema & Authoring Template

> Hand this to Denis so the fraud / shift / access / adjustment / credit rules are authored as **structured, versioned objects** the AI and POS can both consume — not prose.
> Companion to `25` (§2 BRE rationale) and `26` (§1 "one rule layer, not two").
> Date: 2026-07-18. This defines how a rule is *written*; it does not decide the rule *values* — those are Denis's to set.

---

## 1. Why structure (30-second pitch to Denis)

If the rules are prose in a doc, the POS engineer re-encodes them one way, the AI runtime re-encodes them another way, and they drift the first time a threshold changes. If they're structured objects with IDs and versions, **both the POS enforcement layer and the AI agents reference the same `rule_id` + `rule_version`**, every decision carries that reference into the audit trail, and changing a threshold is a versioned edit in one place. Same rules, one source of truth.

The division stays clean: **the BRE (POS/Laravel) enforces; the AI consumes.** AI reads the active rule set to explain and pre-check; it never authors a rule and never overrides a hard rule.

---

## 2. The rule object (canonical shape)

Every rule is one object. Denis fills the human table in §4; this JSON is what it compiles to.

```json
{
  "rule_id": "POS-SHIFT-001",
  "rule_set": "shift_control",
  "rule_version": "1.0.0",
  "status": "active",
  "name": "No sale outside an open shift",
  "description": "A cashier cannot complete a sale unless they have an open shift on the register.",
  "type": "hard",
  "applies_to": {
    "module": "pos",
    "resource": "sale",
    "action": "create",
    "scope": "register"
  },
  "condition": {
    "all": [
      { "fact": "shift.status", "op": "not_equals", "value": "open" }
    ]
  },
  "effect": "block",
  "parameters": {},
  "override": {
    "allowed": false,
    "authority_roles": [],
    "reason_required": true
  },
  "escalation_target": "supervisor",
  "consent_or_dpa": null,
  "message": "This register has no open shift. Start a shift before selling.",
  "owner": "denis",
  "effective_from": "2026-07-21",
  "effective_to": null
}
```

### Field rules
- **`rule_id`** — stable, human-readable: `MODULE-DOMAIN-NNN`. Never reused.
- **`type`** — `hard` (model/UI can never bypass) or `soft` (authorized human can override with a logged reason).
- **`condition`** — boolean tree of `{fact, op, value}` leaves under `all`/`any`. **`fact` must be an allow-listed field** (see §5); no free expressions, no SQL. This is what keeps rules safe to evaluate.
- **`effect`** — one of `block` · `require_approval` · `authorize` · `warn` · `flag`.
- **`parameters`** — named, versionable thresholds (e.g. `refund_ceiling: 5000`) so a value change is a version bump, not a re-author.
- **`override`** — for `soft` rules: which roles may override and whether a reason is mandatory. For `hard`: `allowed:false`.
- **`consent_or_dpa`** — set when the rule enforces consent/data-protection (credit reminders, contact channels); else `null`.

---

## 3. Evaluation response (what the AI/POS gets back)

Unchanged from `25` §2 — every write/sensitive action carries this:

```json
{
  "rule_set": "shift_control",
  "rule_version": "1.0.0",
  "decision": "pass | fail | warning | requires_approval",
  "hard_failures": [{ "rule_id": "POS-SHIFT-001", "message": "..." }],
  "soft_warnings": [],
  "required_approvals": [{ "rule_id": "POS-REFUND-002", "authority_roles": ["supervisor"] }],
  "explanations": [],
  "audit_refs": ["POS-SHIFT-001@1.0.0"]
}
```

---

## 4. Authoring table for Denis (fill one row per rule)

This is the only thing Denis has to complete. It maps 1:1 to the JSON. Rows below are **worked examples from the meeting** — values are placeholders for Denis to confirm/replace.

| rule_id | domain | name | hard/soft | applies_to (module.resource.action) | condition (plain) | effect | parameters | override roles | escalate to |
|---|---|---|---|---|---|---|---|---|---|
| POS-SHIFT-001 | shift_control | No sale outside an open shift | hard | pos.sale.create | shift.status ≠ open | block | — | none | supervisor |
| POS-SHIFT-002 | shift_control | No login outside scheduled shift | soft | pos.session.open | now ∉ scheduled_shift | warn | grace_minutes=15 | supervisor | manager |
| POS-REFUND-001 | fraud_control | High-value refund needs supervisor | hard→approval | pos.refund.create | refund_amount ≥ ceiling | require_approval | refund_ceiling=5000 | supervisor | manager |
| POS-REFUND-002 | fraud_control | Excessive returns alert | soft | pos.refund.create | cashier.returns_today ≥ N | flag | max_returns_per_day=10 | — | supervisor |
| INV-ADJ-001 | inventory_control | Stock adjustment needs manager auth | hard→approval | inventory.adjustment.create | any adjustment | require_approval | — | manager | — |
| INV-ADJ-002 | inventory_control | No adjustment driving balance negative | hard | inventory.adjustment.create | resulting_balance < 0 | block | — | none | manager |
| ACC-CREDIT-001 | credit_control | Credit sale needs supervisor credential | hard→approval | pos.sale.create (mode=credit) | payment_mode = credit | require_approval | — | supervisor | — |
| ACC-CREDIT-002 | credit_control | No credit above customer limit | hard | pos.sale.create (mode=credit) | outstanding + amount > credit_limit | block | — | none | manager |
| ACC-CREDIT-003 | credit_control | Reminder only on consented channel | hard | ar.reminder.send | channel ∉ customer.consented_channels | block | — | none | compliance |
| ACCESS-001 | access_mgmt | Sensitive action needs admin auth | hard→approval | *.settings.update | action ∈ sensitive_set | require_approval | — | admin | — |
| ACCESS-002 | access_mgmt | No access while on HR leave | hard | auth.session.open | user.hr_status = on_leave | block | — | none | manager |

Notes for Denis:
- **Hard vs soft test:** if a person with authority should *never* be able to override it → `hard` with `block`. If a manager should be able to override with a logged reason → `soft`. If it should proceed but only after a named role signs off → `require_approval` (a hard rule whose effect is approval, not block).
- Keep each rule to **one testable condition**. Two conditions → two rules. This is what lets us write a test per rule (`25` §6 release gates require it).
- Every threshold goes in `parameters`, never hard-coded in the sentence — so tuning is a version bump.

---

## 5. Allow-listed facts (the vocabulary conditions may use)

Conditions may only reference these (extend by adding here, never by free expression). This is the contract the POS exposes and the AI reads.

`shift.status` · `shift.scheduled_window` · `now` · `refund_amount` · `refund_ceiling` · `cashier.returns_today` · `sale.total` · `payment_mode` · `outstanding_balance` · `credit_limit` · `resulting_balance` · `adjustment.qty` · `user.role` · `user.hr_status` · `user.branch_id` · `warehouse_id` · `customer.consented_channels` · `action` (+ named sets: `sensitive_set`, …)

---

## 6. Lifecycle & ownership
- **Owner:** Denis owns rule *values* and hard/soft classification. David owns the *evaluator* and the AI consumption path. Backend owns *enforcement* in POS actions.
- **Versioning:** any change to `condition`, `effect`, or `parameters` bumps `rule_version`; `status` moves `draft → active → retired` (never delete — audit needs history).
- **Change control (from `25` §6):** rule-set changes are a governance action — logged, and gated behind the same review as a prompt/model change.
- **AI consumption:** the AI runtime pulls the **active** rule set (read-only), uses it to (a) pre-check a draft before proposing, (b) explain "why is this blocked," (c) narrate anomaly thresholds. The AI records the `rule_id@version` it saw in the run's audit envelope. It cannot author, edit, or override.

---

## 7. What to agree in the session
1. Denis authors in the §4 table format (not prose). ✅/❌
2. The §5 allow-listed facts cover the July fraud/shift/access rules — anything missing?
3. `require_approval` (approval, not block) is the pattern for refunds/adjustments/credit — agreed?
4. One rule set per domain (`shift_control`, `fraud_control`, `inventory_control`, `credit_control`, `access_mgmt`) — agreed naming?
5. Rule values that block the **July POS** (shift + access + refund) are Denis's priority this week; credit rules can follow the credit module.
