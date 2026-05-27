# ADR-016: max_turns Budget — Pinned at 1 Across All Agents

**Status:** Accepted
**Date:** 2026-05-27
**Owner:** Jim
**Related:** ADR-004 (Tool mocking strategy), ADR-010 (Policy mapper SDK choice), ADR-011 (Retriever interface)
**Reserved by:** Phase 2 plan §"ADRs to Write" (originally framed as "max_turns budget increase")

---

## Context

The original scope (§4) and PRD (§5.3-5.6) named per-agent `max_turns` settings assuming the agents would drive tool calls themselves:

| Agent | Scope-stated max_turns | Tools enabled? |
|---|---|---|
| Evidence Summarizer | 1 | No |
| Context Retriever | 3 | Yes — `patient_history_lookup`, `prior_imaging_lookup` |
| Policy Mapper | 3 | Yes — `nccn_passage_lookup` |
| Reasoning Drafter | 1 | No |

The Determinism Contract (scope §9, invariant 6) requires `max_turns` to be **pinned** per agent. The Phase 2 plan reserved ADR-016 for documenting a potential increase to support real RAG retrieval (estimated need: max_turns up by ~1-2 to accommodate retrieval round-trips).

When the agents were actually built, they took a different architectural path: **pre-fetch retrieval**. Instead of letting the LLM iterate through tool calls, the agent calls the tool functions directly in Python, injects the results into the prompt, and then makes a single LLM call. This pattern is documented in ADR-004 (tool mocking).

---

## Decision

**All four agents run with `max_turns=1`. No agent uses LLM-driven tool calling. The Phase 2 plan's anticipated "max_turns budget increase" is therefore NOT taken; we ship with the lower budget.**

```python
# evidence_summarizer / context_retriever / policy_mapper / reasoning_drafter
_AGENT_OPTIONS = ClaudeAgentOptions(
    system_prompt=_SYSTEM_PROMPT,
    max_turns=1,
    allowed_tools=[],  # pre-fetch pattern — tools are NOT exposed to the LLM
)
```

Tool functions (`patient_history_lookup`, `prior_imaging_lookup`, `nccn_passage_lookup`) still exist and are still called — but they're called as **regular Python functions** from the agent code, not as LLM-invokable tools. The fetched data is injected into the prompt as structured context.

---

## Why pre-fetch (not LLM-driven) tool calling

| Concern | LLM-driven (max_turns=3) | Pre-fetch (max_turns=1) |
|---|---|---|
| Determinism | Variable — LLM decides when to call tools, tool calls go through SDK | **Byte-identical 5-run outputs**: agent always fetches in the same order |
| Audit traceability | Tool calls appear in event stream but require parsing the SDK trace | Tool calls are explicit Python lines; the bilateral logger records each as a structured event |
| Cost | Higher — multiple LLM round trips per case | Lower — one LLM call per agent per case |
| Latency | Higher — sequential round trips | Lower — fetches happen before the single LLM call |
| Failure mode if a tool returns empty | LLM might retry / hallucinate / give up unpredictably | Agent decides explicitly in Python whether to escalate, raise, or substitute |

For a governed agentic workflow optimizing for reproducibility and audit, **pre-fetch wins on every dimension we measured for**. The trade-off is that the agent loses the ability to make tool-call decisions dynamically — but for the constrained per-agent contracts in this build, that trade-off is invisible (each agent makes the same fetch calls every time anyway).

---

## When max_turns could legitimately rise

The Phase 2 plan anticipated max_turns going up for RAG retrieval. We did not need that increase because the RAG retriever (`PolicyRetriever`, ADR-011) is **also** pre-fetched — the policy_mapper calls `policy_retriever.search(...)` as a regular Python call and injects the result.

Conditions under which max_turns should rise (future ADR required):

1. **Agent needs to decide between tools dynamically.** E.g., "if the patient history shows X, also query the imaging archive Y." Today's agents have a fixed fetch graph.
2. **Multi-step reasoning with intermediate tool calls.** E.g., "compute a derived value from one tool, then query a second tool with that value as input." Today's tools are independent.
3. **LLM-driven re-query for missing data.** E.g., "the first tool returned no records; ask a different tool with broader parameters." Today's missing-data handling is explicit Python.

None of these are present in Phase 2's scope. They become candidates as the agent surface area grows in Phase 3.

---

## What this ADR does NOT cover

- **The pre-fetch pattern itself.** That's ADR-004.
- **The PolicyRetriever interface that lets pre-fetch RAG work.** That's ADR-011.
- **The model snapshot pinning that the determinism contract requires.** ADR-002.

This ADR's scope is narrowly the per-agent `max_turns` value and why every agent uses 1.

---

## Consequences

1. **Determinism contract invariant 6 is satisfied trivially.** Every agent pins max_turns=1, hard-coded in the agent module — no env var, no runtime mutation.
2. **The scope-stated max_turns=3 for Context Retriever / Policy Mapper does not match the implementation.** This ADR makes the difference explicit and audit-defensible. The scope assumed LLM-driven tool calls; the build chose pre-fetch. Both are valid architectures; we picked the determinism-optimizing one.
3. **`allowed_tools=[]` is a security boundary.** With LLM-driven tools disabled, no agent can be prompt-injected into calling arbitrary tools — even if the model tried, the SDK would refuse. This complements the AI-Decision-Limit Gate (ADR-007).
4. **Future max_turns increases require an ADR.** This is the documented contract — any agent moving off max_turns=1 has to justify the choice, name the failure modes (variable outputs, retry storms), and update the Determinism Contract.
