# GPA Scope Deltas

**Purpose:** One file, one answer to "what changed from the original scope/PRD/Phase 2 plan?"

Every approved deviation, addition, or unintentional drift gets a row. Each entry has: date, label, what changed, why, link to the commit or ADR.

**Labels:**

- **scope-addition** — new work explicitly approved (beyond what the docs anticipated)
- **scope-deviation** — deliberately differs from the docs
- **scope-drift** — unintentional misalignment (to be corrected)
- **scope-clarification** — interpretation of ambiguous spec (not a real change)

---

## Active Deltas

### scope-deviation: RAG stack = Chroma instead of pgvector + LlamaIndex

- **Date logged:** 2026-05-27 (deviation predates the log; baseline reconciliation)
- **Spec:** Phase 2 plan §"Tool Layer" — *"Index: pgvector database over full NCCN guideline corpus. Retrieval: LlamaIndex orchestration."*
- **Build:** ChromaRetriever (`rag/`) — local Chroma vector store
- **Why:** TBD (Jim to confirm). Likely lower setup cost for a solo build; Chroma works locally without a Postgres dependency. Worth a one-paragraph addendum to ADR-011.
- **Open question:** Does the deviation stick (update Phase 2 plan to reflect Chroma), or revert (rebuild on pgvector)?

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

## Out-of-scope (do not pursue without explicit re-prioritization)

These were considered and explicitly deferred this session:

- **CMS-0057-F turnaround tracking / SLA timers** — declined by user 2026-05-27 (out of scope)
- **Provider experience layer** — declined by user 2026-05-27 (different strategy track, OKR3 — not the GPA build's customer anchor)
- **Judgment Boundary Discovery** — pass for now (2026-05-27)
- **Judge calibration tracks** (Track 1 = Cohen's κ human labels; Track 2 = GPT-5 audit overlay) — declined by user 2026-05-27 ("let's pass on these improvements")
