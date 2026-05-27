# ADR-010: Policy Mapper Opts Into Direct Anthropic SDK (Closes ADR-002 Gap)

**Status:** Accepted
**Date:** 2026-05-26
**Owner:** Jim
**Triggered by:** v1→v2→v3 delta report (`eval/results/v1-to-v3-delta.md`)

---

## Context

ADR-002 named a known gap in the Determinism Contract: `claude_agent_sdk`'s `ClaudeAgentOptions` does not accept a `temperature` parameter. The Contract's Invariant #1 — *"`temperature=0` on every LLM call, asserted at the agent boundary"* — was therefore weakened from **architecturally guaranteed** to **empirically observed**.

The v1 → v2 iteration confirmed the cost of that gap. v1 had 2 reproducibility failures (case_0002+0008 in one run, case_0004+0005 in the next — flakiness migrates between runs, confirming the cause is systemic, not case-specific). v2 introduced deterministic Python aggregation of `overall_signal` (ADR-005 + `agents/policy_mapper/aggregate.py`). v2's spot-check showed:

- case_0005: reproducibility 0.60 → 0.80 (now passing — variance was in the aggregation step)
- case_0004: reproducibility 0.60 → 0.60 (no change — variance is in per-criterion judgments)

**The aggregation fix worked. The residual is per-criterion judgment variance, which the temperature gap directly causes.**

---

## Decision

**The Policy Mapper agent can opt into a direct `anthropic` SDK call with `temperature=0.0`, controlled by the `POLICY_MAPPER_SDK=anthropic_direct` env var.**

```bash
# Default (claude_agent_sdk, matches the other 3 agents):
SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py

# v3 path (direct anthropic SDK with temperature=0):
POLICY_MAPPER_SDK=anthropic_direct \
SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py
```

The implementation is in `agents/policy_mapper/agent.py`:

- `_call_via_anthropic_direct(user_prompt)` — async function using `anthropic.AsyncAnthropic().messages.create(temperature=0.0, ...)`. Lazy-initializes the client (uses `ANTHROPIC_API_KEY` from environment).
- `_call_via_claude_agent_sdk(user_prompt)` — the original path, unchanged.
- Dispatch happens inside `run()` based on the env var.
- The `agent_event` audit record now includes `sdk_used` and `temperature` fields.

---

## Why Policy Mapper Specifically, Not All Agents

v1→v2 evidence is clear: per-criterion variance in the policy_mapper is the dominant source of `overall_signal` flakiness on judgment-intensive cases. The other three agents (evidence_summarizer, context_retriever, reasoning_drafter) do not produce outputs the eval framework measures for reproducibility — their variance is downstream of the policy_map signal.

Targeting one agent narrows the blast radius:
- Tooling, prompts, schemas, hashes — unchanged for the other three agents.
- ADR-002's `claude_agent_sdk` choice still holds for agents where its governance primitives (hooks, event stream, ToolSearch) are valuable.
- The architectural pattern for migrating an agent off `claude_agent_sdk` is now established and can be repeated for other agents if their measurements warrant it.

---

## Why an Env-Var Toggle, Not an Outright Replacement

Three reasons to keep the toggle rather than ripping out the `claude_agent_sdk` path:

1. **A/B comparison.** The v3 spot-check needs to demonstrate that direct-SDK produces better reproducibility than the SDK path. Toggling lets us measure the delta cleanly, on the same case, with no other variables changed.
2. **Audit/governance defensibility.** If a regulator asks "did the eval that produced this report use `temperature=0`?", the `agent_event`'s `sdk_used` + `temperature` fields answer it. Both paths are auditable.
3. **Graceful fallback.** If `ANTHROPIC_API_KEY` is missing or the direct path errors out, default behavior is preserved. The other three agents continue to function regardless.

Long-term, the right move is to migrate the other three agents to direct SDK as well and remove the toggle. That's a Phase 2 cleanup.

---

## Consequences

1. **The Determinism Contract Invariant #1 is now architecturally enforced for `policy_mapper`** when `POLICY_MAPPER_SDK=anthropic_direct` is set. The two failure modes from ADR-002 Gap 1 (`final_text` varies / event stream varies due to temperature) no longer apply to this agent.
2. **The Determinism Contract Invariant #2 (pinned model snapshot) is preserved** — the direct SDK call passes `model=_MODEL_SNAPSHOT` from `config/model.yaml`.
3. **Split-stack inconsistency** between policy_mapper (direct) and the other 3 agents (SDK). Named honestly. Phase 2 cleanup.
4. **Loss of governance primitives** for policy_mapper specifically: no `claude_agent_sdk` hooks, no native event stream, no ToolSearch. Acceptable because:
   - Policy Mapper uses no tools at SDK call time (NCCN passages are pre-fetched in Python; see `nccn_passage_lookup` call before the SDK invocation).
   - Hooks add no value here — the agent has `max_turns=1` equivalent (a single message exchange).
   - The audit trail is preserved via the bilateral logger; the SDK's event stream was not the source of truth.
5. **Bilateral log includes `sdk_used` + `temperature` fields** on every policy_mapper `agent_event` so the v1/v2/v3 lineage is reconstructable from the log alone.

---

## How v3 Will Be Validated

1. **Unit tests** verify the dispatch logic (existing 165 tests still pass after the change).
2. **Spot-check** on case_0004 (the v2 holdout) with `POLICY_MAPPER_SDK=anthropic_direct`. Compare reproducibility to v2's 0.60.
3. **Full 8-case re-run** with the direct SDK path. Expect reproducibility ≥0.80 on all judgment-intensive cases.
4. **Eval report v3 section** documents the delta vs v2.

---

## Alternatives Considered

| Option | Reason Not Chosen |
|---|---|
| Replace `claude_agent_sdk` everywhere | Bigger change, higher risk, no measured benefit for evidence_summarizer / context_retriever / reasoning_drafter. |
| Few-shot examples in prompt only | Cheaper but doesn't address the root cause (temperature non-determinism). May reduce variance but does not eliminate it. |
| Ensemble per-criterion judgments (run N times, take modal) | Deterministic by construction but Nx cost and adds latency. Direct SDK is cheaper and more honest. |
| Switch to OpenAI / a different vendor | Different problem. The temperature gap is in the SDK, not in Claude. Direct API call to the same model closes the gap without changing the model. |

---

## Related ADRs

- **ADR-002** — Orchestration Framework & SDK Choice. Named the temperature gap; this ADR addresses it.
- **ADR-005** — Bilateral logger (the audit substrate that records `sdk_used` and `temperature` for every call).
- **ADR-009** — Eval methodology (the `decision_reproducibility` dim that surfaced the need for this fix).
