# ADR-014: Denial Gate Unlock + Physician Peer Review Workflow

**Status:** Accepted (Phase 2 scaffold)
**Date:** 2026-05-27
**Owner:** Jim
**Phase 2 plan:** `phase-2-agentic-rag-plan.md` (Week 10-11 work)

---

## Context

The MVP's Denial Gate (ADR-007) raised `DenialAttemptError` on any `"deny"` path, unconditionally. That was the right Phase 1 choice — denial is a regulated clinical action, and architecturally omitting any path to it was the simplest defensible governance posture for the MVP.

Phase 2 introduces a real physician peer review workflow. The MVP's blunt block now becomes too restrictive: denials are clinically necessary for the cases where the AI brief shows clear unmet criteria AND the nurse has triaged them appropriately. The right architectural move is to **add a path through the gate for physician-authored denials, without weakening the "no autonomous denial" guarantee.**

---

## Decision

**The Denial Gate operates in one of two modes, env-var-gated. Default behavior matches MVP exactly.**

```bash
# MVP / default:
# DENIAL_GATE_MODE unset → "block" mode
# Behaves identically to Phase 1: any "deny" path raises.

# Phase 2 unlock:
DENIAL_GATE_MODE=route
# "deny" path is permitted IFF:
#   1. The determination includes a case_id
#   2. A PhysicianQueue is passed to check()
#   3. The queue has an ActionRecord with action=DENY for that case_id
# Otherwise: still raises DenialAttemptError.
```

The Phase 2 mode is **not a softening** of the gate. It's a **second hard control**: instead of "denial impossible," it becomes "denial requires a recorded physician action with clinical_basis, guideline_citation, and evidence_gaps." Both halves of the AND must hold.

Implementation lives in `gates/denial.py:check()` with a new optional `physician_queue` parameter. The lazy import of `physician_queue` keeps the MVP-mode code path zero-dependency.

---

## The Physician Queue Workflow

`physician_queue/` is a new module that scaffolds the queue and its persistence:

### `PhysicianQueue` ABC
Same pattern as `PolicyRetriever` (ADR-011). Narrow interface:

```python
class PhysicianQueue(ABC):
    def enqueue(case_id, reason, ai_brief_summary, nurse_note) -> QueueEntry
    def list_pending() -> list[QueueEntry]
    def get(case_id) -> QueueEntry | None
    def record_action(case_id, action, physician_id, clinical_basis,
                      guideline_citation, evidence_gaps, rationale) -> ActionRecord
```

### `FilePhysicianQueue`
JSON-file-backed bridge implementation. Persists to `physician_queue/state.json` (gitignored). Single-writer; no concurrent-physician handling. Phase 2 follow-up could replace with Postgres + row locks if multi-physician concurrency becomes a real requirement — the interface won't change.

### `QueueEntry`, `ActionRecord`, `QueueState`, `PhysicianAction`
Dataclasses + string enums for type-safe state transitions:

- `QueueState`: PENDING → IN_REVIEW → COMPLETED (or RETURNED for request_additional_evidence)
- `PhysicianAction`: APPROVE | DENY | REQUEST_ADDITIONAL_EVIDENCE

### Hard validation rules at the record_action boundary
Same fail-loud principle as the rest of the system:

- `physician_id` required, non-empty
- `clinical_basis` required, non-empty
- `guideline_citation` required, non-empty
- `evidence_gaps` required to be non-empty when action == DENY
  (a single-item explanation is fine; an empty list is rejected)

These aren't policy — they're enforced at the function boundary, so a developer can't accidentally record a half-formed denial.

---

## Why Env-Var Gating, Not Outright Replacement

Three reasons (same pattern as ADR-010 for the SDK choice):

1. **MVP behavior preserved by default.** The bilateral logger, eval framework, and existing tests assume the Phase 1 gate behavior. Default-off means nothing existing breaks.
2. **A/B-able.** Two consecutive eval runs (one with `DENIAL_GATE_MODE=route`, one without) measure the workflow's effect cleanly.
3. **Audit defensibility.** When a regulator asks "was this case decided under route mode or block mode?", the answer is in the env at runtime and can be captured in the audit log as a future enhancement.

---

## Accountability Chain (the whole reason this exists)

ADR-000 named the solution shape as "AI-Assists / Human-Decides." For denials specifically, that chain is:

```
AI surfaces structured reasoning (with uncertainty_flags)
        ↓
Nurse reviews; if denial-shaped, escalates to physician
        ↓
Case enqueued: PhysicianQueue.enqueue(case_id, reason, ai_brief_summary)
        ↓
Physician dequeues from queue (UI: Phase 2 Week 11 deliverable)
        ↓
Physician records action with clinical_basis + guideline_citation + evidence_gaps
        ↓
Denial Gate (route mode) verifies the action record exists before permitting "deny" path
        ↓
Determination emitted with full audit lineage:
    case_id → ai_brief → nurse_action → queue_entry → physician_action → determination
```

**Every denial in the system, after Phase 2, has a physician ID and a clinically defensible rationale attached.** The bilateral logger captures it; the regulator-defensible answer to "who denied this case and why?" is one query away.

---

## Why Not Just Trust the Nurse to Escalate?

The MVP design already lets a nurse `escalate` instead of `approve`. Two reasons that's not enough for Phase 2:

1. **Denial accountability requires a licensed physician.** Nurse escalation creates a holding state, not a denial. Without a physician downstream, escalation is just a queue with no consumer.
2. **The eval framework needs a measurable physician-action loop to score `Physician Queue Routing Accuracy` and `Physician Rationale Compliance` (Phase 2 §12 deliverables).** The queue + ActionRecord provides the data those dimensions read.

---

## Consequences

1. **MVP eval unchanged.** Default behavior is byte-for-byte identical to Phase 1.
2. **Phase 2 route-mode is opt-in per eval run.** Set `DENIAL_GATE_MODE=route` in env, pass a `PhysicianQueue` to `check()`, denials work.
3. **The physician queue is real, not a stub.** `FilePhysicianQueue` persists state to disk; the workflow can be exercised end-to-end today without standing up a database.
4. **Two future Phase 2 eval dimensions have their substrate.** When `Physician Queue Routing Accuracy` and `Physician Rationale Compliance` land, they read the queue's state and action records — not new infrastructure.
5. **The "no autonomous denial" guarantee survives.** Route mode adds a physician-action requirement, not a relaxation. The gate still blocks any path-to-deny that doesn't have a paired physician record.

---

## What This ADR Does NOT Cover (Phase 2 Week 11 follow-ups)

- **Physician UI.** `ui/physician_queue.html` and the per-case review screen. The queue exists; the UI lands in Week 11.
- **Bilateral logger extension for physician_action events.** Action records exist in the queue's state file; they should also flow into the per-case decision_log JSONL for unified audit. Small follow-up.
- **Multi-physician concurrency.** `FilePhysicianQueue` is single-writer. Production needs queue-service semantics.
- **Physician queue routing decisions automated.** Today, "route to queue" is a nurse decision. Phase 2 could explore AI suggestions for which cases warrant physician review based on uncertainty flags + criteria status — separate ADR if pursued.

---

## Related ADRs

- ADR-000 — Solution shape (AI-Assists / Human-Decides)
- ADR-007 — AI-Decision-Limit Gate (the architectural sibling)
- ADR-009 — Eval methodology (where the future Phase 2 eval dims plug in)
- ADR-011 — Retriever interface pattern (this ADR follows the same interface-+-bridge structure)
