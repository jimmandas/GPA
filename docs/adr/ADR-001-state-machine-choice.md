# ADR-001: Orchestration Pattern — Sequential Pipeline, Not State Machine

**Status:** Accepted
**Date:** 2026-05-25
**Owner:** Jim

---

## Context

The MVP has four agents executed in a fixed order, four gates that fire between agents, and a bilateral logger that captures pre- and post-state. The orchestration question: do we model this as a state machine (explicit states, transitions, persistence) or as a sequential function pipeline?

State machine arguments:
- Natural fit for "case has lifecycle" framing
- Phase 2 (physician escalation, pend, appeals) adds states; better to start with the right abstraction
- Easier to express invariants like "case cannot be in two states at once"

Sequential pipeline arguments:
- MVP has zero branching in the agent sequence — all four agents always run in order
- A state machine for a linear sequence is over-engineering
- Function call chains are easier to test, easier to read, lower cognitive overhead

---

## Decision

**Use a sequential pipeline function for MVP orchestration.**

`orchestrator/pipeline.py:run_pipeline(submission)` is the entry point. It calls the four gates and four agents in order. The pipeline returns a `PipelineResult` dataclass with status (`completed | escalated | failed`), determination, and audit log reference.

Branching states (physician escalation, pend, appeals) enter via separate functions (`record_nurse_decision`) that operate on already-determined cases. The case's "state" is implicit in what's in the bilateral log.

---

## Why Not LangGraph / Temporal / Custom State Machine

| Option | Reason Not Chosen for MVP |
|---|---|
| LangGraph | Designed for branching agent workflows; the MVP has none. Adoption cost (new dependency, mental model) > benefit. Strong Phase 2 candidate if physician escalation adds real branching. |
| Temporal | Durable case lifecycle is a Phase 3 concern. MVP cases complete in <60 seconds. |
| Custom state machine (e.g., `transitions` library) | Adds a state-modeling layer where the underlying logic is `if not result.passed: return early`. |

The simplest abstraction that captures MVP behavior is a function. Use the right tool for the actual scope, not the imagined future scope.

---

## Consequences

1. **Pipeline code is direct and readable.** `pipeline.py` reads top-to-bottom as the actual case flow.
2. **Testing is straightforward.** Each agent and each gate has its own unit tests; integration tests mock the SDK and assert the pipeline assembles correctly.
3. **Phase 2 may refactor.** When physician escalation introduces real branching (queue, peer review, return-to-nurse), reconsider LangGraph or a typed state machine.
4. **The "state" of a case lives in the bilateral log**, not in pipeline memory. The log is the source of truth; the pipeline is stateless.

---

## How to Recognize When to Revisit

This decision should be revisited if any of the following become true:
- More than 2 branching points exist in the agent sequence
- Cases need to suspend, resume, or migrate across infrastructure
- The pipeline function exceeds ~250 lines and is no longer the simplest expression of the flow

---

## Related ADRs

- ADR-002 — Claude Agent SDK (the call layer this pipeline orchestrates)
- ADR-005 — Write-before-emit (the bilateral log that holds case state externally)
