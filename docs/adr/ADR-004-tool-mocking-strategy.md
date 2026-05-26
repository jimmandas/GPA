# ADR-004: Tool Mocking via Checked-In Fixtures + Content Hashing

**Status:** Accepted
**Date:** 2026-05-25
**Owner:** Jim

---

## Context

The MVP needs three retrieval tools to give the agents access to patient context, prior imaging, and policy criteria:

- `patient_history_lookup(patient_id)` → prior authorizations, diagnoses, medications
- `prior_imaging_lookup(patient_id, modality)` → prior imaging events
- `nccn_passage_lookup(indication_category, modality)` → NCCN criteria passages

In production these would be EHR/payer system API calls and a RAG index over NCCN. For MVP, we mock all three. The question is *how* to mock them so the eval baseline is trustworthy.

---

## Decision

**Three principles for MVP tool mocking:**

1. **All tool data is checked-in fixture files.** No HTTP calls, no remote dependencies. The data lives in `tools/fixtures/patients/`, `tools/fixtures/imaging/`, and `policy/nccn_fixtures/`.
2. **Tool implementations are pure idempotent functions.** Same input → same output. Calling twice returns the same data. Tolerates the duplicate-call behavior identified in the Day 2 SDK spike (see ADR-002).
3. **Tool registry content-hashes every fixture file.** `config/tool_registry.yaml` stores SHA-256 of each fixture. Any change to any fixture file requires updating the registry. CI asserts no drift.

---

## Why These Three Principles

### Principle 1: checked-in fixtures, not stubs

Stubs (return hard-coded objects) are even simpler but lose two things:
- **Realistic data shape.** Real EHR responses are nested, contain fields the agents must learn to skip, and include data the agents must learn to extract. Stub returns of `{"diagnoses": ["cancer"]}` don't exercise the agent's parsing.
- **Reusable test inputs.** Fixture files become the substrate for the eval dataset itself. The same `pt_anon_0001.json` that powers `patient_history_lookup` also drives `case_0001`'s ground truth.

### Principle 2: idempotent pure functions

The Day 2 SDK spike (ADR-002 Gap section) found that without `temperature=0` (not configurable), agents sometimes call the same tool twice in one turn. The tool implementation must tolerate this without state corruption, double-counting, or side effects. Pure functions handle this trivially.

### Principle 3: content hashing in tool registry

If a fixture is silently edited mid-eval, the eval baseline is invalidated. CI must catch this. The `tool_registry.yaml` hash check is the enforcement mechanism. This is the Determinism Contract Invariant #4 in action.

---

## What This Enables

- **Reproducible eval runs.** Fixture content is byte-stable; tool outputs are byte-stable; the `decision_reproducibility` eval dim has a stable substrate to measure against.
- **No external dependencies in CI.** Eval can run in any environment without network access, secrets, or third-party API quotas.
- **Phase 2 swap-in.** When `patient_history_lookup` becomes a real FHIR call in Phase 2, the function signature is preserved. The agents don't change.

---

## What This Doesn't Cover

- **Tool output validation against schema:** Tool returns are not currently jsonschema-validated at the tool boundary. Agents validate their own output schemas, but a malformed tool return would manifest as a downstream agent failure. Phase 2 should add schema validation at the tool boundary (relevant once tools become real API calls).
- **Tool latency simulation:** Fixture reads are instant. Real EHR APIs aren't. Eval doesn't measure latency-induced failure modes.
- **Tool failure mode coverage:** No fixture currently simulates an EHR timeout, 5xx, or partial response. Adding these is a follow-up.

---

## Consequences

1. **Eval is reproducible across machines** as long as the fixture set is committed and the registry hash is current.
2. **CI guards against fixture drift** — any change to a fixture file requires an explicit registry hash update.
3. **Phase 2 RAG upgrade preserves the `nccn_passage_lookup` interface** — the change is beneath the function signature.
4. **Phase 2 FHIR/EHR stubs preserve the `patient_history_lookup` / `prior_imaging_lookup` interfaces** — the upgrade is to a structured FHIR R4 stub, not a complete API swap.

---

## Related ADRs

- ADR-002 — Day 2 spike: tool-call idempotency requirement
- ADR-003 — Why RAG (the natural Phase 2 upgrade to `nccn_passage_lookup`) is deferred
