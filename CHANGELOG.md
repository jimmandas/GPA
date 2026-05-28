# Changelog

Material version bumps. Scope-level changes that affect what the system claims to do or the eval claims to measure. Working-level deltas live in `docs/SCOPE_DELTAS.md`.

---

## eval framework v2 — RAI-aligned expansion (2026-05-27)

**Headline:** Eval coverage expanded from 8 dimensions (scope §7 original) to **12 active dimensions** explicitly mapped to the 6 Responsible AI evaluation categories (safety, grounding, policy compliance, HITL, explainability, fairness).

### What's new in v2

**Added dims (4):**

1. `physician_queue_routing_accuracy` — Phase 2 §12; HITL + Policy Compliance. Was implemented in v1 but not wired into the runner; now surfaces in every report.
2. `physician_rationale_compliance` — Phase 2 §12; Policy Compliance. Was implemented in v1 but not wired into the runner; now surfaces in every report.
3. `bias_disparity` — Scope-addition (ADR-018); Fairness. Cohort cuts across `label_category` + `indication_category` with a 0.20 spread threshold.
4. `citation_correctness` — Scope-addition (closes scope §8 Failure Mode #9 "Faithful-but-Wrong"); Grounding. Precision of cited NCCN passages vs. ground-truth expected passages.

**Improved reporting:**

- Per-case dim Notes column added so N/A scores carry diagnostic detail. Previous v1 report dropped the notes field; debugging an N/A score required separate investigation.
- GPT-4o judge pinned to dated snapshot `gpt-4o-2024-11-20`, not the `gpt-4o` alias (audit-defensible).

**EVAL_TIER system (ADR-017):**

- `EVAL_TIER=dev` (default) — Sonnet 4.5 via env override, ~50-80 min for dev iteration. Dev signal only, NOT production guarantee.
- `EVAL_TIER=ship` — leaves the override unset → Opus 4.1 from `config/model.yaml`. Audit-grade, ~90-120 min.

### Why v2 deserves a version bump (not just a delta entry)

- Strategy §6 names RAI as a core constraint, not a downstream concern. The v1 eval operationalized this through 8 dims; v2 explicitly covers all 6 RAI categories with named dims and thresholds. The regulator-facing claim moves from "we tested AI behavior" to "we tested AI behavior across the 6 RAI categories the strategy framing identifies."
- v1 reports could not answer "did the system route to physician correctly?" or "is the brief citing the *right* NCCN passages?" — those dims existed in code but were absent from the report. v2 surfaces them.
- A regulator's first question — "show me your fairness numbers" — gets a defensible answer in v2 (a real dim with a threshold and a number) where v1 had nothing to point to.

### Removed dims (logged separately in `SCOPE_DELTAS.md`)

| Dim | Reason |
|---|---|
| `rag_passage_relevance` | RAG initiative cut from Phase 2 (Phase 3 backlog item #10) |
| `evidence_lineage_completeness` | Provider experience track cut from Phase 2 |

### What v2 does NOT claim

- Clinical accuracy at scale (scope §1 honest limit)
- Demographic-fairness (synthetic fixtures don't carry protected attributes; Phase 3)
- Regulation-specific compliance (NCQA, CMS-0057-F) — out of Phase 2 scope
- Real RAG over a real corpus — Phase 3
- Audit-replay from log content alone — bilateral logger stores hashes by design (Determinism Contract invariant 4); replay requires source content. Phase 3 candidate.

### Compatibility

- Backwards-compatible with v1 reports. v1 reports remain valid for what they measured; v2 supersedes them with broader coverage.
- The Determinism Contract (10 + Phase 2 invariants) is unchanged; v2 is purely additive to the eval scoring layer.
- The runner's CLI surface is unchanged. `python eval/save_report.py` produces a v2 report.

---

## phase 2 build — physician peer review + 5th gate + RAG cut (2026-05-27)

Major shape changes to the Phase 2 build during the 2026-05-27 session. Documented in `SCOPE_DELTAS.md` and the ADR registry; summarized here.

**Added to Phase 2:**

- 5th hard control gate: `Confidence Gate` (ADR-015)
- Physician peer review workflow: PhysicianQueue + FilePhysicianQueue + ActionRecord + 3 API endpoints + 2 UI files
- Bilateral logger emits `physician_action_record` (write-before-emit)
- ConfidenceCalibrator pure-function tool (ADR-015)
- Nurse → physician handoff wired in `record_nurse_decision` (escalate enqueues to physician queue)
- EVAL_TIER system (ADR-017)
- Pipeline Trace UI (`ui/pipeline_trace.html`)
- All 5 UIs wired to live API endpoints (was: hardcoded fixtures)
- CORS middleware added so static UI can reach the API
- 19 ADRs (000-018)

**Removed from Phase 2:**

- Entire RAG initiative (ChromaRetriever, RAGIndexValidator, embedding pinning enforcement). Interface (`PolicyRetriever` ABC) + `FixtureRetriever` retained. Phase 3 backlog item #10.
- EHR FHIR stub upgrade — bundles with Phase 3 real EHR integration.
- EvidenceLineageBuilder + Provider Explanation API upgrade + Evidence Lineage Completeness dim — provider experience track, OKR3.
- Dataset expansion 15 → 50-75 cases — Phase 3 calibration work.
- ~1,030 lines of code + tests removed with the RAG cut.

**Phase 3 backlog:** 16 items with explicit trigger conditions (`docs/PHASE_3_BACKLOG.md`).

---

## v1 (MVP — 2026-05-25 baseline)

The 7-week MVP per `imaging-pa-poc-scope.md` v4. 4 agents + 4 gates + 3 mocked tools + 8 eval dims + bilateral logger. Foundation for everything above.
