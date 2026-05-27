# GPA Scope Deltas

**Purpose:** One file, one answer to "what changed from the original scope/PRD/Phase 2 plan?"

Every approved deviation, addition, or unintentional drift gets a row. Each entry has: date, label, what changed, why, link to the commit or ADR.

**Labels:**

- **scope-addition** — new work explicitly approved (beyond what the docs anticipated)
- **scope-removal** — work named in the docs that we are explicitly cutting
- **scope-deviation** — deliberately differs from the docs (kept but altered)
- **scope-drift** — unintentional misalignment (to be corrected)
- **scope-clarification** — interpretation of ambiguous spec (not a real change)

---

## Active Deltas

### scope-clarification: RAG stack = Chroma now, pgvector at production scale

- **Date logged:** 2026-05-27 (clarification logged post-hoc during baseline reconciliation)
- **Phase 2 plan spec:** *"Index: pgvector database over full NCCN guideline corpus. Retrieval: LlamaIndex orchestration."*
- **Build:** ChromaRetriever (`rag/`) — local Chroma vector store
- **Why this is a clarification, not a deviation:** ADR-011 deliberately built a `PolicyRetriever` interface and listed Chroma, pgvector, and LanceDB as acceptable concrete implementations. Choosing Chroma for the POC is within the bounds ADR-011 already authorized. The Phase 2 plan was more prescriptive than ADR-011; the interface-first design reconciles them.
- **What stays intact:**
  - All Phase 2 Determinism Contract invariants (11-13) work with Chroma — embedding model pinning, content hashing, corpus-update rebuild policy
  - `PolicyRetriever` ABC contract is unchanged; `ChromaRetriever` satisfies it cleanly
  - Audit / evidence-lineage story works identically
- **What's deferred to Phase 3:**
  - Migration to pgvector + LlamaIndex for production HIPAA / operational story → logged in `PHASE_3_BACKLOG.md` (item #10) with explicit trigger conditions
  - Hybrid retrieval (BM25 + vector) — LlamaIndex provides this; we'd build it ourselves on Chroma if needed earlier
- **ADR follow-up:** ADR-011 gets a "Phase 3 Migration" section explicitly naming pgvector as the production target.

### scope-addition: EVAL_TIER (dev/Sonnet vs ship/Opus) — ADR-017

- **Date logged:** 2026-05-27
- **What:** Eval runner reads `EVAL_TIER` env var. Dev (default) sets `MODEL_SNAPSHOT_OVERRIDE=Sonnet 4.5`; ship leaves it unset so agents fall back to `model.yaml` (Opus).
- **Why:** Eval iteration on Opus is ~45 min and expensive. Sonnet cuts to ~15-25 min. Production canonical config stays untouched.
- **Tradeoff named in ADR:** Dev tier is a dev signal only, NOT a production guarantee. Ship tier is the audit-grade run.
- **ADR:** `docs/adr/ADR-017-eval-tier-dev-vs-ship.md`
- **Commit:** `aef464f`

### scope-addition: GPT-4o judge snapshot pinned

- **Date logged:** 2026-05-27
- **What:** `eval/rationale_judge.py` default model changed from `"gpt-4o"` alias to dated snapshot `"gpt-4o-2024-11-20"`.
- **Why:** Alias lets OpenAI silently re-route the underlying model, drifting faithfulness scores without any code change. Pinned snapshot makes the judge part of the audit record.
- **Spec alignment:** PRD §11 OQ-8 specifies "different vendor (GPT-4 or equivalent)" — pinning hardens that, doesn't change vendor choice.
- **Commit:** `b791b02`

### scope-addition: Two physician-queue eval dimensions wired

- **Date logged:** 2026-05-27
- **What:** Added `physician_queue_routing_accuracy` and `physician_rationale_compliance` to `eval/dimensions.py`. Both return N/A until route mode is exercised in the eval.
- **Why:** Phase 2 plan's "New eval dimensions" table explicitly names these as Phase 2 §12 deliverables. Substrate (queue + ActionRecord) shipped in ADR-014; dims read that substrate.
- **Spec alignment:** **Directly in-scope per Phase 2 plan**. (Logged here for traceability, not because it's a deviation.)
- **Commit:** `343c704`

### scope-addition: Bilateral logger emission for physician_action_records

- **Date logged:** 2026-05-27
- **What:** `record_action()` now writes a `physician_action_record` to the bilateral logger before persisting queue state. Write-before-emit pattern preserved.
- **Why:** Phase 2 plan §"Physician Peer Review Workflow" explicitly calls for this: *"Bilateral Logger extension: Physician action events are appended to the same JSONL audit trail."*
- **Spec alignment:** **Directly in-scope per Phase 2 plan.** ADR-014 named it as a "Phase 2 Week 11 follow-up."
- **Commit:** `fe0b8eb`

### scope-addition: PhysicianQueue wired into pipeline's denial gate

- **Date logged:** 2026-05-27
- **What:** `record_nurse_decision()` accepts optional `physician_queue` and passes `case_id` + queue to `check_denial()`. Route-mode denial path now functional end-to-end.
- **Why:** ADR-014 / Phase 2 plan §"Denial Gate — Unlocked." Required to exercise the denial path through the queue.
- **Spec alignment:** **Directly in-scope per Phase 2 plan.**
- **Commit:** `37bc46e`

### scope-addition (on backlog): Runtime confidence gate

- **Date logged:** 2026-05-27
- **Decision:** User approved adding to scope (Jim, 2026-05-27)
- **What:** Runtime gate that asserts `if overall_signal == "ambiguous" OR per-criterion confidence < threshold → escalate`. Sibling to the 4 existing gates.
- **Why:** Strategy framing §6 lists "confidence gating" as part of Responsible AI execution architecture. Phase 2 plan reserves ADR-015 for the calibration story.
- **Maps to:** ADR-015 (planned), Phase 2 Week 12 (`ConfidenceCalibrator` deliverable).
- **Status:** Not started.

### scope-addition (on backlog): Bias monitoring

- **Date logged:** 2026-05-27
- **Decision:** User approved adding to scope (Jim, 2026-05-27)
- **What:** Eval dim and/or runtime hook that compares scores across cohort cuts (indication_category, case difficulty, etc.) to surface systematic disparities.
- **Why:** Strategy framing §6 names "bias monitoring" as part of Responsible AI execution architecture. Not in original scope or PRD.
- **Maps to:** New ADR (018+).
- **Status:** Not started.

### scope-drift: ADR-015 numbering collision (corrected)

- **Date logged:** 2026-05-27
- **What:** Initial commit `aef464f` named the EVAL_TIER ADR as ADR-015. Phase 2 plan reserves ADR-015 for "Confidence threshold calibration." Renumbered to ADR-017.
- **Why:** Drift caught during baseline reconciliation against the Phase 2 plan.
- **Resolution:** File renamed; references updated.

---

### scope-removal: EHR FHIR stub upgrade (Phase 2 Week 10)

- **Date logged:** 2026-05-27
- **Decision:** User cut from scope (Jim, 2026-05-27): *"not sure the product needs this"*
- **What was named:** Phase 2 plan §"Tool Layer" — *"patient_history_lookup / prior_imaging_lookup — responses now conform to HL7 FHIR R4 resource schemas (Patient, DiagnosticReport, ImagingStudy)."* Also Determinism Contract invariant 14 ("EHR stub schemas version-pinned").
- **Why cut:** Customer anchor is the nurse. The shape of underlying data (ad-hoc JSON vs. FHIR) is invisible to her. FHIR is a production-integration concern that ties to real EHR work (Phase 3), not a governance / judgment concern. Building synthetic FHIR is finicky for symbolic value.
- **Where it goes:** `PHASE_3_BACKLOG.md` — tied to existing item #2 "Real EHR integration."

### scope-removal: EvidenceLineageBuilder (Phase 2 Week 11)

- **Date logged:** 2026-05-27
- **Decision:** User cut from scope (Jim, 2026-05-27)
- **What was named:** Phase 2 plan §"New Agents and Tools" — *"Constructs evidence lineage from Source Verification Gate records for the provider explanation API."*
- **Why cut:** Its sole consumer (Provider Explanation API upgrade) is also being cut. The Source Verification Gate already enforces per-claim citations; a separate lineage-builder is provider-experience tooling, not governance tooling. Nurse-anchored customer model makes this provider-track work.
- **Where it goes:** `PHASE_3_BACKLOG.md` — bundled under provider experience track (new item, see below).

### scope-removal: Provider Explanation API upgrade (Phase 2 Week 11)

- **Date logged:** 2026-05-27
- **Decision:** User cut from scope (Jim, 2026-05-27)
- **What was named:** Phase 2 plan §"What Changes from MVP" — *"Provider explanation: basic structured rationale → full rationale with evidence lineage."*
- **Why cut:** Provider-facing surface area is strategy OKR3, not the GPA build's customer anchor. Without the lineage builder, this has no upgrade path anyway.
- **Where it goes:** `PHASE_3_BACKLOG.md` — provider experience track.

### scope-removal: Dataset expansion 15 → 50-75 cases (Phase 2 Week 12)

- **Date logged:** 2026-05-27
- **Decision:** User cut from scope (Jim, 2026-05-27)
- **What was named:** Phase 2 plan §"Eval Expansion" — *"Expand from 25-30 cases to 50-75 cases."*
- **Why cut:** Build holds 15 cases (mix of clean / judgment-intensive / adversarial). The architecture is proven; statistical power on the eval is a Phase 3 calibration question, not a Phase 2 ship-gate question.
- **Caveat:** Original MVP target per scope §7 was 25-30 cases. We are below that. The build is making a deliberate decision to ship at 15 with a documented limitation rather than chase 25-30 or 50-75. Recommend naming this explicitly in the final eval report.
- **Where it goes:** `PHASE_3_BACKLOG.md` — bundled with multi-rater labeling at scale (item #4).

### scope-removal: Evidence Lineage Completeness eval dim (Phase 2 Week 12)

- **Date logged:** 2026-05-27
- **Decision:** User cut from scope (Jim, 2026-05-27) — Option 1: drop the dim alongside the tooling that would have produced its substrate.
- **What was named:** Phase 2 plan §"New eval dimensions" — *"Evidence Lineage Completeness: Does the provider explanation API trace every claim back to a specific retrieved passage?"*
- **Why cut:** With EvidenceLineageBuilder and Provider Explanation API upgrade both cut, the dim has no substrate to score. Keeping the dim would have meant either (a) reinterpreting it as a redundant copy of `source_citation_accuracy` or (b) leaving it permanently N/A.
- **Where it goes:** `PHASE_3_BACKLOG.md` — provider experience track.

---

## Out-of-scope (do not pursue without explicit re-prioritization)

These were considered and explicitly deferred this session:

- **CMS-0057-F turnaround tracking / SLA timers** — declined by user 2026-05-27 (out of scope)
- **Provider experience layer** — declined by user 2026-05-27 (different strategy track, OKR3 — not the GPA build's customer anchor)
- **Judgment Boundary Discovery** — pass for now (2026-05-27)
- **Judge calibration tracks** (Track 1 = Cohen's κ human labels; Track 2 = GPT-5 audit overlay) — declined by user 2026-05-27 ("let's pass on these improvements")
