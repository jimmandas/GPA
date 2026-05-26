# ADR-000: Solution Shape — AI-Assists / Human-Decides for Judgment-Intensive PA

**Status:** Accepted
**Date:** 2026-05-25
**Owner:** Jim
**Informed by:** `imaging-pa-poc-scope.md` v4

---

## Context

Prior authorization automation has two distinct segments:

1. **Deterministic** (rules-engine territory): eligibility checks, benefit verification, document completeness. Already automated by payers since the early 2010s.
2. **Judgment-intensive** (non-deterministic): cases with comorbidities, ambiguous timing windows, exception requests, competing diagnoses. Remains manual because reliable rules don't exist.

The v3 scope of this POC targeted segment 1 — automating routine oncology imaging approvals via a Confidence Scoring Agent + Confidence Gate. After portfolio review and re-reading the strategy framing (§2 of `Revised AI-Native Prior Authorization Strategy V2`), it became clear v3 solved the wrong problem: it tried to use AI where rules already work, and produced a "confidence threshold" governance story that doesn't address the actual hard governance challenges (hallucination, unauthorized autonomy, faithful-but-wrong rationale).

The strategy framing is explicit: *"The strategic opportunity is not the already-automated rule-based segment of prior authorization. The true operational bottleneck exists in the remaining judgment-intensive segment."*

---

## Decision

**The POC implements the AI-Assists / Human-Decides pattern for judgment-intensive oncology imaging PA cases.**

Four architectural commitments follow from this:

1. **The nurse is the decision actor.** Every architectural choice serves her judgment. The AI surfaces evidence and structured reasoning; she decides approve / escalate / pend.
2. **The AI cannot emit a decision field.** This is enforced architecturally (output schema omits `decision`) AND at runtime (AI-Decision-Limit Gate raises on any attempt).
3. **No autonomous denial.** The `determination` schema accepts only `approve` or `escalate`. Denial requires physician review (Phase 2).
4. **Every AI claim is traceable.** Reasoning brief items must cite a verifiable field from the case input. Source Verification Gate enforces this at runtime.

---

## Why This Shape vs. Alternatives

| Alternative | Reason Not Chosen |
|---|---|
| Full autonomous approve/deny with confidence gates (v3) | Solves the already-automated segment; doesn't address judgment-intensive workflows where the actual market gap is. |
| AI as pure summarizer (no policy mapping, no reasoning brief) | Doesn't materially help the nurse — most of her cognitive load is policy interpretation, not document reading. |
| AI as copilot in nurse's existing tool | Couples to a payer's specific UM platform; doesn't prove the governance plumbing portably. |
| LangGraph + branching workflows | Phase 2/3 candidate. MVP doesn't need branching; the gate sequence is linear. |

---

## What This Shape Proves

- The AI-Assists / Human-Decides pattern is implementable with **hard architectural controls** (gates), not just policy guidance.
- The four runtime gates (Admission, Source Verification, AI-Decision-Limit, Denial) operate as **runtime governance**, not retrospective monitoring.
- Bilateral logging (write-before-emit) creates an audit-grade trail of both AI assistance and nurse decision.
- The 8-dimension eval framework surfaces real failure modes; v1 → v2 iteration documents improvement.

---

## What This Shape Does NOT Prove (Honest Limits)

- Clinical accuracy at scale — dataset is 15-30 cases, sourced from NCCN guidelines and de-identified studies.
- EHR integration safety — tools are mocked via checked-in fixtures.
- Physician review workflow — scaffolded in MVP, fully built in Phase 2.
- Multi-rater inter-judgment agreement — Cohen's κ requires Pax co-labels, queued for v1→v2.

---

## Consequences

1. **Strategic alignment:** The POC now maps cleanly to strategy framing §2 (judgment-intensive segment) and §7 (runtime governance as foundational capability).
2. **Risk posture:** Trades coverage breadth (one indication category, oncology imaging surveillance) for depth of governance proof.
3. **Portfolio framing:** Hiring-manager / governance-reviewer narrative is *governance plumbing*, not *automation throughput*.
4. **Phase 2 unlock:** RAG + physician peer review build on top of a validated governance baseline rather than alongside it.

---

## Related ADRs

- ADR-002 — Orchestration framework (Claude Agent SDK)
- ADR-005 — Write-before-emit pattern (the audit trail this shape requires)
- ADR-007 — AI-Decision-Limit Gate (the architectural control that makes "AI cannot emit a decision" enforceable)
- ADR-009 — Eval methodology (the 8 dimensions that measure whether this shape works)
