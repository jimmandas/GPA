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

### scope-addition: Phase 3a—Case Status Web UI + Audit Trail View + JWS Signatures — 2026-06-04

- **Date logged:** 2026-06-04
- **Decision:** User approved new Phase 3a scope goal (Jim, 2026-06-04): *"Add ability to view case status via web UI, audit trail per case. Supporting scope: add signatures, add MongoDB (deferred to Phase 3b/4)."*
- **What's being added:**
  - **Phase 3a goal:** Web UI dashboard showing case status (pending, in review, completed, escalated) with real-time queue visibility for nurses and physicians
  - **Per-case audit trail view:** Click into any case to inspect the full decision_log JSONL with signature verification in the browser
  - **Supporting infrastructure Priority 1 (do now):** JWS signatures on all JSONL records + `verify_audit_log.py` upgrade to validate signatures cryptographically
  - **Supporting infrastructure Priority 2 (Phase 3b/4):** MongoDB migration when concurrent case volume hits 100+ (trigger: file locks become bottleneck)

- **Why this matters:**
  - **Current state:** Audit trails are JSONL files + hash chains; only developers can inspect manually with CLI tools
  - **Phase 3a goal:** Non-technical nursing staff can click into a case in the web UI and see full decision history with cryptographic proof of authenticity (via JWS signature verification in the browser)
  - **Admissibility win:** Combining signatures + web UI = "anyone can independently verify the audit trail is authentic"
  - **Scaling path:** File-based storage works up to ~50 cases/day; MongoDB enters at Phase 3b when concurrent demand justifies the operational overhead

- **Implementation phases:**
  1. **Now (Phase 3 Week 1):** Add JWS signing to `bilateral_logger.py`; update `verify_audit_log.py` to check signatures; wire up key generation
  2. **Phase 3 Week 2-3:** Extend web UI (`ui/index.html`) with case status dashboard + per-case detail modal showing audit trail
  3. **Phase 3b (scale inflection):** When concurrent cases hit 100+, migrate to MongoDB while preserving signature chain

- **Scope boundaries (NOT included):**
  - NOT full clinical-audit export (HIPAA HITRUST compliance) — Phase 3+ regulatory track
  - NOT multi-tenancy or RBAC — single-tenant pilot scope (Phase 4)
  - NOT Opus/ship-tier eval on signatures — dev-tier Sonnet eval covers signature correctness

- **Reversals / Amendments:**
  - **Amends 2026-05-31 A4 removal:** That entry removed A4 (HMAC/signature) to avoid key-management costs. This decision reverses that — JWS adds ~2-3 hours of dev work, zero AWS costs (keys stored locally in gitignored config), and unlocks the admissibility + web UI story. A4's original "key-management cost" concern is moot.
  - **A8 (RFC 3161 timestamp):** Still deferred. JWS + per-case timestamp in the JSON is sufficient for admissibility; RFC 3161 TSA integration is higher-touch and not required for Phase 3a.

- **Traceability:**
  - New ADR forthcoming: `ADR-020-JWS-signatures-JSONL-audit-trail`
  - Existing ADR-017 (EVAL_TIER) + ADR-014 (PhysicianQueue) remain unchanged
  - Tests needed: signature generation, signature verification, tampered-record detection

- **Risk / Unknowns:**
  - MongoDB migration timing (Phase 3b): depends on actual concurrent case volume in pilot; if pilot volume stays <50/day, MongoDB can be further deferred to Phase 4
  - Browser-based signature verification: need to pick JWS library (e.g., `jose` npm package for the UI); add dependency

- **Backout / Rollback:** Straightforward. If signatures cause issues before Phase 3a ships, remove the signature field from JSONL and omit signature verification in `verify_audit_log.py`. The hash chain remains intact; admissibility story survives with hash-chain alone (pre-2026-06-04 status).

---

### scope-removal: A4 (HMAC/signature) + A8 (RFC 3161 timestamp) — 2026-05-31

- **Date logged:** 2026-05-31
- **Decision:** User removed from scope (Jim, 2026-05-31): *"I don't want to spend any money. Let's remove this item from the Scope list."*
- **What was named:** P2 phase — **A4** (HMAC/digital signature on audit records) and **A8** (RFC 3161 trusted timestamping). Both depended on key-management decision (where/how to store cryptographic keys).
- **Why removed:**
  - **Key management cost not budgeted.** AWS KMS estimate was ~$2–4/month for MVP, negligible but beyond current budget constraints.
  - **O1 (Admissibility) remains defensible without them.** A1 (hash-chain) + A2 (complete audit trail) + A3 (fail-closed HITL) + A7 (chain-of-custody legal doc) is sufficient for regulated-tenant auditability. A4/A8 add non-repudiation and timestamping (nice-to-have, not critical-path).
  - **A4 + A8 were lowest GIST priority.** A4: 280 (Ease docked by key-mgmt blocker). A8: 180 (lowest on board). A1 was 729; A7 is 336. The core governance spine doesn't depend on signatures or timestamps.
  - **Key-management decision is off-repo.** No control over when it lands; better to remove the items than be blocked.
- **Impact on P2:**
  - **A7 (chain-of-custody doc)** unblocked: was blocked by A4 + legal review; now blocked by A1 ✅ + legal review only.
  - **R7 (transparency cards)** shipped ✅ regardless; pairs with R10, not A4/A8.
  - **P2 remaining items:** A7 + R7. Both move forward without key-mgmt decision.
- **Impact on O1 (Admissibility) claim:**
  - **Before removal:** "Records are authentic (A4 signature), complete (A2), untampered (A1), HITL-verified (A3), timestamped (A8), legally framed (A7)"
  - **After removal:** "Records are complete (A2), untampered (A1), HITL-verified (A3), legally framed (A7)" — still sufficient for regulator verification without vendor trust.
  - **Regulator can independently verify:** Run `verify_audit_log.py` on any case → chain integrity. Query audit trail → full decision trail. Check A3 fail-closed enforcement → HITL guarantee. A1+A2+A3+A7 is the defensible core.
- **Where they go:** Not Phase 3 backlog. Out-of-scope (deferred indefinitely pending key-mgmt decision + budget).
- **Backout:** None needed; A4/A8 were never in code (blocked on external decision). Removal affects docs only.

---

### scope-clarification: per-case dims rolled up into bucket view (Fix B) — 2026-05-28

- **Date logged:** 2026-05-28
- **Issue surfaced:** The dashboard advertised "18 dims across 3 buckets" but the bucket cards only rendered 14 — the 4 per-case dims (source_citation_accuracy, ai_decision_limit, rationale_faithfulness, decision_reproducibility) lived in the per-case tables and never appeared in the aggregate bucket view. Felt inconsistent on inspection.
- **Decision:** Added 4 suite-wide roll-ups (`<dim>_suite_avg`) that compute the mean per-case score across all cases. They flow into `aggregate_scores` and render as tiles in the appropriate bucket card. The original per-case dims remain — the roll-ups are a *view*, not a replacement.
- **Bucket totals (correct after Fix B):**
  - Value / Outcomes: **4** (unchanged)
  - Trust: **10** — 7 aggregate + 3 per-case roll-ups
  - Operational Reliability: **4** — 3 aggregate + 1 per-case roll-up
  - Total: **18**
- **Also corrected:** the "Trust 9 / Operational 5" counts written in the cohens-removal entry (and downstream docs) were off-by-one. Pre-cohens Trust was 11 (not 10); post-removal Trust = 10 (not 9). Pre-cohens Operational was 4 (not 5); post-removal Operational = 4. Fix B addresses both the structural gap and the count error.
- **What changed:**
  - `eval/dimensions.py`: 4 new scorers + 1 helper (`_suite_avg_of_per_case_dim`)
  - `eval/runner.py`: imports + aggregate_scores entries; per-case table gets a Bucket column
  - `tests/test_eval_harness.py`: aggregate count 14 → 18; expected name set expanded
  - `README.md`, `docs/SCOPE_BASELINE.md`, `docs/EVAL_WRITEUP.md`, `docs/LOOM_SCRIPT.md`, `docs/eval-methodology.md`, `CHANGELOG.md`: bucket subcounts corrected
- **Backout:** Trivial. Remove the 4 roll-up scorers from `aggregate_scores` and the Bucket column from print_report. The roll-up scorers don't replace per-case data.

### scope-removal: cohens_kappa removed from active eval dims — 2026-05-28

- **Date logged:** 2026-05-28
- **Decision:** Removed `cohens_kappa` from the active eval dimension set. Net dim count 19 → 18; Trust bucket 11 → 10 (the earlier "10 → 9" written here was an off-by-one — corrected 2026-05-28).
- **Why removed:**
  - **It's a meta-eval**, not a system-quality eval. It measures whether two human raters labeled the same ground-truth cases the same way — i.e., whether the ground truth itself is reliably labeled. It does NOT measure agent quality, workflow correctness, governance, value, or operational properties.
  - **It does not move outcomes.** Doesn't move OKR1 (workflow compression), doesn't move OKR2 (governance proof). At best it validates the foundation under `false_escalation_rate`, `citation_correctness`, `bias_disparity`, `clinical_signal_accuracy` — second-order.
  - **Cost-benefit fails for this build.** Producing the signal requires ~10 person-hours minimum (Pax labels 15 cases independently, Jim labels the same 15, compute κ) for a single scalar. The same 10 person-hours spent on dataset expansion (15 → 25-30 cases) strengthen every other dim simultaneously — strictly higher leverage.
  - **The PRD domain isn't subjective.** Prior auth on structured NCCN criteria has objectively-checkable ground truth. κ matters where labels are subjective (radiology read agreement, psychiatric coding) — not here.
  - **Reporting κ as N/A with this reasoning is more credible than gaming a number.** A hiring manager who knows evals reads "removed because it would need 10 person-hours for one scalar without moving outcomes" and sees a PM who knows the difference between rigor and theater.
- **Where κ would actually pay off (Phase 3 / future):**
  - Real deployment with multiple nurse reviewers — κ across the *humans in the loop*
  - A regulatory submission demanding evidence of ground-truth reliability
  - A subjective domain
  None of these are Phase 2 conditions. Re-add when one of them is true.
- **Counterfactual:** Keeping κ in scope as "N/A pending co-labels" was the half-measure for several weeks. It cluttered every report, signaled an open commitment we weren't going to fund, and produced zero signal.
- **What changed:**
  - `eval/dimensions.py`: `_cohens_kappa` + `score_cohens_kappa` deleted; section comment retained for audit trail
  - `eval/runner.py`: import + `aggregate_scores` entry removed
  - `tests/test_eval_harness.py`: 3 cohens tests removed; expected aggregate count 15 → 14; expected name set updated
  - `docs/SCOPE_BASELINE.md`: hard invariant struck through; "8 dimensions" line updated to 18 across 3 buckets; aggregate-dims table marks κ removed
  - `docs/eval-methodology.md`: dim count 19 → 18; cohens row replaced with removal note
  - `README.md`: count 19 → 18; table renumbered; v3-follow-up dims added as rows 16-18
  - `docs/EVAL_WRITEUP.md`: aggregate-dims table updated; honest-limits paragraph reflects removal
  - `docs/LOOM_SCRIPT.md`: Trust bucket count 10 → 9; total 19 → 18
  - `CHANGELOG.md`: top-section entry
- **Backout:** Trivial. `git revert <this commit>` restores everything. The scorer function is removed; co-labels in `ground_truth.jsonl` (currently zero) would need to be added before re-running.

### scope-addition: eval framework v3 — 3-bucket framing + ROI + signal accuracy + latency p90 — 2026-05-28

- **Date logged:** 2026-05-28
- **Decision:** Major framing expansion: the eval went from "12 dims grouped by 6 RAI categories" (v2) to **"16+3=19 dims grouped by 3 stakeholder buckets, with RAI categories nested inside Trust"** (v3). The new framing is more PM-defensible because each bucket answers a different audience's question. Also added 7 new dims (4 Tier 1 business-value + 3 follow-ups including ROI heuristic).
- **What's now included in v3 (19 active dims across 3 buckets):**

  **Value bucket (4) — "Did it matter?"**
  - `false_escalation_rate` (workflow compression — moved from HITL when buckets were introduced)
  - `pipeline_wall_time_p50_seconds` (TAT proxy, OKR1 KR1)
  - `estimated_cost_per_case_usd` (admin cost proxy, heuristic)
  - `estimated_roi_per_case_usd` (ROI heuristic — value saved minus cost, NEW 2026-05-28)

  **Trust bucket (10 after cohens_kappa removal later 2026-05-28; earlier "9" was an off-by-one corrected with Fix B) — "Can we rely on it safely?" — nests the 6 RAI categories**
  - `source_citation_accuracy`, `ai_decision_limit`, `rationale_faithfulness`, `adversarial_gate_bypass_rate`, `confidence_calibration`, `physician_queue_routing_accuracy`, `physician_rationale_compliance`, `bias_disparity`, `citation_correctness`
  - `clinical_signal_accuracy` (signal-alignment with ground truth, NEW 2026-05-28; the closest dim to "clinical accuracy" within the PRD honest-limit constraint)
  - **Amendment 2026-05-28:** `cohens_kappa` removed later same day — see preceding entry. Net Trust count is 9, not 10. Net total is 18, not 19.

  **Operational Reliability bucket (4; earlier "5" was an off-by-one corrected with Fix B) — "Can it reliably operate at scale?"**
  - `decision_reproducibility` (per-case)
  - `pipeline_completion_rate`, `gate_fire_distribution`
  - `pipeline_latency_p90_seconds` (tail-latency variance, NEW 2026-05-28)

- **Why this matters strategically:** The 3-bucket framing is "evals as enterprise-value instrumentation" — a level UP from traditional model/agent/observability evals. It measures organizational accountability properties (trust, admissibility, workflow correctness, governance adherence, business impact, ROI realization), not just model behavior. Logged as Phase 3 backlog item #23 for the market-positioning whitepaper / pitch.
- **What this is NOT:**
  - NOT real ROI — the new dim is a heuristic using published nurse rate + UM-study baseline. Real ROI is Phase 3 #22.
  - NOT clinical accuracy — `clinical_signal_accuracy` measures signal-alignment with ground truth's `expected_overall_signal`, not full clinical correctness. PRD §1 honest limit holds.
- **Implementation:**
  - `DimensionScore.bucket` first-class field with __post_init__ validation
  - 37 + 3 = 40 DimensionScore constructors carry `bucket=BUCKET_X`
  - `eval/runner.py` print_report groups aggregate dims by bucket subsections
  - `api/main.py` /api/v1/eval/latest parses bucket subsection headers
  - `ui/index.html` dashboard renders 3 bucket cards with per-bucket pass/fail counts and colored dim tiles
- **Gaps named (logged in Phase 3 backlog):**
  - Item #20: AI Evals expansion (real accuracy / hallucination composite / benchmarks)
  - Item #21: Observability dims (trace completeness, log integrity, latency variance score)
  - Item #22: Real ROI from production data
  - Item #23: Evals as enterprise-value instrumentation — market positioning

### scope-addition: RAI-aligned eval framework expansion (eval v1 → v2) — 2026-05-27

- **Date logged:** 2026-05-27
- **Decision:** Major capability expansion. The eval framework went from scope §7's original 8 dimensions to **12 active dimensions** explicitly aligned to the 6 RAI evaluation categories (safety, grounding, policy compliance, HITL, explainability, fairness) the strategy doc §6 names as core constraints.
- **What was named:** Scope §7 defines 8 dimensions. Phase 2 plan §12 named 4 additional dims. Strategy framing §6 names RAI as core constraint but the original PRD didn't operationalize specific RAI sub-categories in the eval.
- **What's now included (12 active dims):**

  **4 per-case dims (scope §7, unchanged):**
  1. `source_citation_accuracy` — grounding category
  2. `ai_decision_limit` — safety category
  3. `rationale_faithfulness` — grounding + explainability categories (cross-vendor GPT-4o judge, pinned snapshot `gpt-4o-2024-11-20`)
  4. `decision_reproducibility` — explainability + trustworthy category

  **4 aggregate dims (scope §7, unchanged):**
  5. `adversarial_gate_bypass_rate` — safety category
  6. `false_escalation_rate` — HITL + operational category
  7. `confidence_calibration` — trustworthy category (Brier proxy)
  8. `cohens_kappa` — trustworthy category (currently N/A, no co-labels)

  **2 Phase 2 §12 dims (now wired into the runner):**
  9. `physician_queue_routing_accuracy` — HITL + policy compliance categories
  10. `physician_rationale_compliance` — policy compliance category

  **2 scope-addition dims:**
  11. `bias_disparity` — fairness category (ADR-018; cohort cuts across `label_category` + `indication_category`)
  12. `citation_correctness` — closes scope §8 Failure Mode #9 ("Faithful-but-Wrong"); precision of cited NCCN passages vs. ground-truth expected passages

- **Why this is a "major capability":**
  - Strategy doc §6 explicitly names "Responsible AI as a Core System Constraint" — RAI must be embedded in execution architecture, not bolted on
  - The original PRD operationalized this through 8 dims; the expansion adds explicit coverage for HITL flow (physician routing), fairness (cohort disparity), and faithful-but-wrong citations
  - Without the expansion, the build's regulator-facing claim ("we built RAI into the eval") rests on inference; with the expansion, the claim rests on named dims with thresholds
  - Per-case report Notes column also added so N/A scores carry actionable diagnostic detail
- **Version bump:** **Eval framework v1 → v2.** The Determinism Contract invariant 10 (`ClaudeAgentOptions` version-pinned + full eval re-run on changes) extends naturally — the eval framework itself is a version-pinned artifact.
- **What this is NOT:**
  - Not a clinical-accuracy expansion (PRD §1 honest limit still holds — POC proves governance plumbing, not clinical accuracy at scale)
  - Not a demographic-fairness expansion (synthetic fixtures don't carry protected attributes; that's Phase 3, ADR-018)
  - Not a regulation-specific compliance expansion (NCQA, CMS-0057-F still not measured)
- **ADRs:** 015 (Confidence threshold calibration), 016 (max_turns budget), 017 (EVAL_TIER), 018 (Bias disparity monitoring). The dim `citation_correctness` is in the code; the ADR for it can fold into 018 or get its own (ADR-019) if you want explicit documentation.



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

### scope-removal: Chroma + RAGIndexValidator code (2026-05-27, follow-up to RAG cut)

- **Date logged:** 2026-05-27
- **Decision:** User cut after asking "do we need chroma or ragindexvalidator?" Answer was no.
- **What was named:** Phase 2 plan §"Tool Layer" / "Architecture Changes" — Chroma as the concrete retriever implementation; `RAGIndexValidator` as a build-time preflight check enforcing Determinism Contract invariants 11-13.
- **What's removed:**
  - `rag/chroma_retriever.py` (159 lines)
  - `rag/build_chroma_index.py` (132 lines, standalone indexer script)
  - `rag/index_validator.py` (322 lines)
  - `tests/rag/test_chroma_retriever.py` (119 lines)
  - `tests/rag/test_index_validator.py` (295 lines)
  - `.chroma/` directory (208 KB sqlite + collection data)
  - Multi-mode dispatch in `agents/policy_mapper/agent.py`
  - Preflight call in `eval/runner.py`
  - Multi-mode block in `config/rag_index.yaml` (now fixture-only)
- **Why:**
  - Chroma indexed 1 fixture / 3 criteria — not a corpus
  - RAGIndexValidator was multi-mode for fixture/chroma/pgvector; with only fixture mode active, it's overkill
  - Fixture integrity is already enforced by `config/tool_registry.yaml` (Determinism Contract invariant 4) — separate, simpler mechanism
  - Phase 3 RAG will likely use pgvector + LlamaIndex, NOT Chroma — keeping Chroma artifacts creates "we have RAG (sort of)" ambiguity
- **What stays:** `PolicyRetriever` ABC (ADR-011 interface pattern) + `FixtureRetriever` + `tests/rag/test_retriever.py`. These are the active pieces; they exercise the interface and serve the real pipeline.
- **Net effect:** ~1,030 lines of code + tests removed. The "we don't have RAG" narrative is now also "we don't have demo Chroma either" — cleaner and more honest.

### scope-removal: ENTIRE Phase 2 RAG initiative (Week 9 deliverables) — 2026-05-27

- **Date logged:** 2026-05-27
- **Decision:** User cut from Phase 2 scope after reality-check: *"will RAG move the outcomes in the strategy, and outcomes defined in the PRD forward?"* Answer: no — zero of OKR2's KRs require RAG; only 1 of 12 eval dims is materially affected (and that dim was the rag_passage_relevance dim, which itself gets cut here).
- **What was named:** Phase 2 plan §"Architecture Changes / Tool Layer" — *"`nccn_passage_lookup` queries pgvector + LlamaIndex over full NCCN corpus … embedding model pinned … index content-hashed … any corpus change requires a rebuild and hash update."* Plus Determinism Contract invariants 11-13.
- **Why cut:** Honest gap audit found the RAG work was architecturally complete but corpus-ally empty. The repo's "NCCN corpus" is one hand-authored YAML file with 3 criteria. We never built a parse / chunk / embed pipeline over real source documents — what we have is structured-data lookup wearing RAG clothing. Building real RAG (parse PDFs/HTML → chunk → embed → index) would take 4-8 hours AND doesn't move any strategy or PRD outcome forward. The interface generalizes; the corpus pipeline is a Phase 3 investment when production deployment makes it matter.
- **What stays in the build (NOT cut):**
  - `PolicyRetriever` ABC (interface pattern; useful regardless of RAG status)
  - `FixtureRetriever` (the actual active retriever — was always going to be this in Phase 2)
  - `ChromaRetriever` code + 1-fixture Chroma index on disk (demo proof that the interface generalizes; NOT exercised by default eval)
  - `RAGIndexValidator` preflight (still validates fixture-mode corpus hash; that part is useful even without RAG)
  - ADRs 011, 012, 013 (preserved with Phase 3-deferral addendum at the top of each)
- **What's cut from the build:**
  - The claim of "RAG built" — replaced with "retriever interface + fixture-mode active, Chroma demo, Phase 3 will do real RAG"
  - Active enforcement of Determinism Contract invariants 11-13 (deferred until real RAG enters production)
  - The `rag_passage_relevance` eval dim (removed from `eval/dimensions.py` and its test file; restoration path documented inline)
  - Any portfolio claim that depends on RAG quality at scale
- **Where it goes:** `PHASE_3_BACKLOG.md` item #10 (vector store migration → broaden to "real parse/chunk/embed pipeline over a real clinical-guidelines corpus, with pgvector + LlamaIndex").

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
