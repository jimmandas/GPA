# ADR-005: Write-Before-Emit Bilateral Logging

**Status:** Accepted
**Date:** 2026-05-25
**Owner:** Jim

---

## Context

The strategy framing document is explicit (§8): *"In AI-native healthcare systems, logging is not merely an observability function. Logging becomes a governance gate."*

The MVP must produce an audit trail of:
- What evidence the AI saw (submission, findings, context)
- What policy mapping the AI produced (criterion-by-criterion status)
- What reasoning brief the AI surfaced for the nurse
- What the nurse decided (approve / escalate / pend) and why
- Every gate that fired, every schema validation, every agent event

The question: when is "the case is complete" — when the AI's output is computed in memory, or when the audit log has confirmed a durable write?

---

## Decision

**Write-before-emit: the AI brief is not returned to the nurse until the bilateral logger confirms a durable write of the pre-state record.**

```python
# orchestrator/pipeline.py:151
pre_state = _build_pre_state_record(case_id, submission, findings, context, policy_map, reasoning_brief)
get_logger().commit(case_id, pre_state)
# If this raises BilateralLoggerError → propagates up, do not emit
```

The logger's `commit()` performs an `fsync()` before returning. The case determination is only returned to the caller after `commit()` succeeds.

The same invariant applies to nurse actions: `record_nurse_decision` writes the `nurse_action_record` to the log before returning the final determination.

---

## Why Write-Before-Emit, Not Write-After-Emit

| Pattern | What happens if the process crashes between `emit` and `write` |
|---|---|
| Write-after-emit (typical app logging) | The nurse sees an AI brief that has no audit record. The case looks "started" externally but is untraceable internally. The audit log is *eventually consistent*. |
| Write-before-emit (this design) | Either both the audit record exists AND the AI brief was returned, OR neither happened. The audit log is *strongly consistent* with externally observable behavior. |

For regulated healthcare workflows where audit defensibility is a strategic dependency, eventual consistency is the wrong choice. A nurse acting on a brief without an audit record creates an evidence gap — the system cannot reconstruct what the AI told her.

---

## What the Bilateral Log Contains

For each case, `decision_log/{case_id}.jsonl` accumulates event records over the case lifetime:

| Event type | When | Contents |
|---|---|---|
| `agent_event` | After each agent call | prompt hash, user_prompt hash, output hash, model snapshot, tool calls, timestamp |
| `schema_validation_event` | When a schema validation fails | agent, result, failure_reason, failure_detail, escalation_triggered |
| `pre_state_record` | After all agents complete, before brief is returned | hashes of submission, findings, context, policy_map, reasoning_brief |
| `nurse_action_record` | When nurse submits a decision | nurse_decision, rationale, timestamp |
| `escalation_event` | When any gate escalates | reason, detail, timestamp |

The log is append-only JSONL. No record is ever modified. Every hash is SHA-256.

---

## Consequences

1. **Every emitted determination has a corresponding durable audit record.** This is enforced by the pipeline structure, not by policy or runtime monitoring.
2. **Logger failure halts the case.** If the bilateral logger cannot commit (disk full, fsync error), the case fails closed: no determination is returned. The nurse never sees an unaudited brief.
3. **The audit log can reconstruct any case from inputs.** Given the input submission and the hashes in the log, the full case can be replayed (modulo the temperature gap from ADR-002).
4. **Regulator-defensible by construction.** "Show me the audit trail for case X" returns a complete record because the system would not have returned X's determination without that record existing first.

---

## Cost

- **Latency:** Each case pays an fsync (typically 1–10ms on local SSD). For an MVP with sub-minute case latency this is negligible. For Phase 2/3 at scale this becomes a question of batch fsync or per-case journal.
- **Crash recovery:** If the pipeline crashes mid-agent (before the pre-state record), partial agent_events are in the log without a pre-state record. Recovery logic must distinguish "incomplete case" (no pre-state record) from "completed case" (pre-state record present).

---

## Why This Matters for the Eval

Several eval dimensions depend on the bilateral log:
- `ai_decision_limit` is verified against agent_event payloads
- `decision_reproducibility` is verified by hashing outputs across 5 runs — the hashes live in agent_event records
- `adversarial_gate_bypass_rate` is verified by reading escalation_event and schema_validation_event records

If the log were eventually consistent, the eval could not trust it.

---

## Related ADRs

- ADR-000 — Solution shape that requires this audit trail
- ADR-007 — AI-Decision-Limit Gate (uses agent_event records to verify no forbidden fields emitted)
- ADR-009 — Eval methodology (multiple dims depend on the log)
