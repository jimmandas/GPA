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

### scope-addition: Real RAG ingestion pipeline (NCI PDQ corpus) — 2026-06-06

- **Date logged:** 2026-06-06
- **Decision:** User approved building the real parse/chunk/embed ingestion (Jim, 2026-06-06), after discovering Phase 3b never delivered it (the corpus was hand-authored YAML, not a parsed document — see Phase 3b as-built amendment below). Promotes `PHASE_3_BACKLOG.md` item #10 to active. ADR-019.
- **Corpus decision — NOT NCCN.** The original plan named `nscl.pdf` (NCCN). **Rejected on license grounds:** the NCCN EULA (page 2) states *"you MAY NOT distribute this Content or use it with any artificial intelligence model or tool"* and the PDF is watermarked to a single licensee. Ingesting it into a RAG pipeline violates the EULA (AI use + distribution); committing derived chunks to this **public** repo would be distribution. For a *governed-AI* project that is a disqualifying own-goal (failure mode #5, Trustworthy). **Chosen instead: NCI PDQ — Non-Small Cell Lung Cancer Treatment (Health Professional Version)** — public-domain text (*"The content of PDQ documents can be used freely as text"*), same NSCLC domain, structured HTML. The licensing decision is itself a Responsible-AI credibility point.
- **What was built:** `rag/ingest_pdq.py` (section-aware chunk + fixed fallback → embed → Chroma), corpus extracted to `rag/pdq_corpus/nsclc_hp.json` (committed, public-domain text + provenance), `tests/test_pdq_ingestion.py` (5 tests). Result: **1,737 chunks from 47 sections** embedded into Chroma `pdq_nsclc_v1`; semantic retrieval verified (Stage IIIA query returns the Stage IIIA treatment section at 0.75). Activates Determinism Contract invariants 11 (embedding pinned) + 12 (idempotent build) over a *parsed* corpus.
- **Deliberately NOT done (sequenced):** the **live policy-mapper cutover** (YAML criteria → PDQ prose chunks). PDQ returns prose, not the discrete `passage_id`/`status` criteria the policy_mapper schema + eval dims expect. Cutting over now would destabilize the in-flight top-priority GT audit + not_applicable work. Sequence: GT audit → not_applicable → confidence-gate → THEN prose-RAG cutover (own ADR addendum). Two corpora coexist transiently: `nccn_nsclc_v5` (YAML, live) + `pdq_nsclc_v1` (PDQ, ingestion artifact, retrieval-verified, not yet wired). Logged, not hidden.
- **Compliance guardrails (binding, in ADR-019):** text-only (PDQ images carry separate permissions); chunks attributed as *source: NCI PDQ* with citation, never claimed to BE an official PDQ summary; preferred citation carried in corpus metadata.
- **Honest claim this makes true:** *"Real RAG ingestion with section-aware chunking over a license-clean public-domain corpus, embedded into Chroma, with verified semantic retrieval."* What it does NOT yet claim: that PDQ is the live retrieval path (it isn't — YAML still is, pending the sequenced cutover).
- **Traceability:** ADR-019; PHASE_3_BACKLOG #10 marked promoted.

---

### scope-addition: Ground-Truth Label Audit — TOP PRIORITY — 2026-06-06

- **Date logged:** 2026-06-06
- **Decision:** User approved as **top scope priority** (Jim, 2026-06-06): *"lets add this as a top scope priority."*
- **What's being added:** A rigorous audit of the 15-case ground-truth labels in `eval/ground_truth.jsonl` (`expected_overall_signal` + per-criterion `expected_criterion_status`), to make the eval trustworthy as a *scoreboard*, not just as a decision instrument.
- **Why this is #1 (the dependency argument):** The 2026-06-05/06 eval investigation surfaced that the headline `clinical_signal_accuracy` (~0.58) is **partly measuring the labels, not the system**. The eval-critic found the GT is **internally inconsistent** for judgment-intensive cases — e.g. `case_0005 SURV-3=unmet` vs `case_0011 SURV-3=ambiguous` for materially similar "not-indicated-by-stage" situations. Every downstream eval-driven decision (the `not_applicable` status fix `task_f9bc2a32`, the confidence-gate recal `task_cd4ce4f3`, any future tuning) **validates against these labels**. With inconsistent labels you cannot tell whether a fix worked — you risk improving the score by fitting noise, or rejecting a real fix because it disagrees with a wrong label. The GT audit therefore **sequences ahead of both existing eval backlog tasks**.
- **Deliverable:**
  1. A written **labeling rubric** — the decision rule for assigning each criterion `met / unmet / ambiguous / not_applicable` given a case scenario, derived from clinical/NCCN logic. This rubric must incorporate the `not_applicable` category being added in `task_f9bc2a32` (the two are coupled; the rubric defines what the code must produce).
  2. A **consistency pass** over all 15 cases, re-labeling where the rubric exposes inconsistency, with **per-change rationale logged** (fits GPA's forensic/audit ethos — the GT itself becomes auditable).
  3. Updated `eval/ground_truth.jsonl` + a `docs/` rubric doc.
- **Hard constraints / integrity guardrails:**
  - **Derive the rubric from clinical/NCCN logic FIRST, then apply it blind to cases — do NOT relabel to match model output.** Label-fitting to the model is the inverse of eval-gaming and equally invalidating. The rubric must be defensible independent of what any agent currently produces.
  - **Do NOT reintroduce Cohen's κ / multi-rater labeling.** That was explicitly removed from scope 2026-05-28 (meta-eval; doesn't move OKR1/OKR2). This is a single-rater, documented-rubric audit — rigor via an explicit, reproducible rule, not via inter-rater statistics.
  - 15-case suite size is unchanged (the 25-30/50-75 expansion stays cut per 2026-05-27). This audits the labels we have, it does not expand the suite.
- **Sequencing:** GT audit → then `task_f9bc2a32` (not_applicable code, validated against audited labels) → then `task_cd4ce4f3` (confidence gate).
- **Traceability:** new backlog task spawned; rubric doc forthcoming. No ADR (process/quality task, not an architecture decision).

---

### scope-addition: Phase 3b—RAG-Enhanced NCCN Guideline Retrieval + Classifier Agent — 2026-06-04

- **Date logged:** 2026-06-04
- **Decision:** User approved (Jim, 2026-06-04): *"lets add RAG to scope... I approve all five agent output changes to UI"*
- **What's being added:**
  - **Phase 3b goal:** Expand from fixture-based policy mapping to vector-search-backed NCCN guideline retrieval with explicit classification and gap detection
  - **5-agent pipeline (replacing current 4):**
    1. **Classifier Agent (NEW)** — Step 1: Extract cancer type, stage, ICD/CPT, therapy line, urgency from submission
    2. **Evidence Summarizer (MINIMAL CHANGE)** — Step 4: Extract findings (takes classifier output as context)
    3. **Context Retriever (ENHANCED)** — Step 3: Expand EHR retrieval (biomarkers, prior treatments, medication history)
    4. **Policy Mapper (MAJOR CHANGE)** — Steps 2, 5: Vector search NCCN guidelines by indication, map evidence to retrieved criteria (no longer static)
    5. **Reasoning Drafter (ENHANCED)** — Steps 6-7: Add gap detection logic, flag missing staging/biomarkers/prior docs
  
- **UI changes (all approved):**
  - **Classifier outputs:** Display cancer type, stage, ICD/CPT, therapy, urgency as case metadata
  - **Policy Mapper source:** Show retrieved NCCN section (e.g., "Used: NCCN NSCLC v5.2026 § Staging Criteria")
  - **Context Retriever detail:** Display retrieved biomarkers, prior treatments, medication history
  - **Gap detection panel:** Prominent, actionable list of missing items (red/yellow flags)
  - **RAG metadata:** Show guideline retrieval source (audit transparency)

- **Why this matters:**
  - **Current state (fixture-based):** Works for 1 guideline, 3 criteria. Not scalable.
  - **Phase 3b goal:** Proven RAG pipeline supporting 3-5 NCCN guidelines, multiple indications, real corpus
  - **Admissibility win:** Explicit source citation (which NCCN doc was used) + gap detection (what evidence is missing)
  - **Production readiness:** Enables multi-cancer case routing with semantic guideline matching

- **Implementation phases:**
  1. **Phase 3b Week 1-2:** Classifier Agent + schema
  2. **Phase 3b Week 3-4:** Policy Mapper RAG integration (vector search + NCCN corpus indexing)
  3. **Phase 3b Week 5:** Context Retriever expansion (biomarkers + prior treatments)
  4. **Phase 3b Week 6-7:** Reasoning Drafter gap detection
  5. **Phase 3b Week 8:** UI integration (all 5 outputs)

- **Scope boundaries (NOT included):**
  - NOT multi-tenancy or RBAC
  - NOT real EHR integration (still fixtures for patient context)
  - NOT dynamic guideline updates (static indexed corpus for Phase 3b)
  - NOT Opus/ship-tier eval on RAG quality (dev-tier Sonnet)

- **Eval framework changes (Phase 3b Week 20):**
  - Add cost tracking for Classifier Agent (~$0.02-0.03/case)
  - Add cost tracking for vector search / embedding lookup (~$0.001-0.002/case)
  - Update `estimated_cost_per_case_usd` dimension calculation (baseline shifts ~$0.291 → ~$0.32-0.35/case)
  - Recalculate `estimated_roi_per_case_usd` (ROI heuristic changes with new cost baseline)
  - Re-run full eval to establish Phase 3b baseline metrics + per-bucket pass/fail counts

- **Traceability:**
  - New ADR forthcoming: `ADR-021-RAG-NCCN-guideline-retrieval`
  - New ADR forthcoming: `ADR-022-Classifier-agent-design`
  - Existing ADR-011 (RAG architecture) to be updated with Phase 3b concrete implementation
  - Tests needed: classifier schema validation, vector search retrieval, gap detection logic, UI rendering, eval cost calculations

- **Decisions finalized (2026-06-04):**
  - **Vector DB:** pgvector + LlamaIndex (production-grade, determinism-ready)
  - **NCCN corpus:** NSCLC only for Phase 3b POC (multi-cancer Phase 4+)
  - **Timeline:** Phase 3b Weeks 13-20 (8 weeks post-Phase-3a stabilization)
  - **Embedding model:** OpenAI text-embedding-3-small (pinned snapshot, Determinism Contract invariant 11)
  - **EHR expansion:** Biomarkers + prior treatment history added to fixtures

- **Risk / Unknowns:**
  - **pgvector ops:** Need PostgreSQL + pgvector extension. Docker container for local dev, cloud (Supabase/RDS) for production.
  - **NCCN licensing:** Assumption is NCCN guideline text is available (user sourced /Users/lauramandas/Downloads/nscl.pdf). Chunking/indexing starts from there.
  - **Embedding model cost:** OpenAI text-embedding-3-small is ~$0.02/1M tokens. NSCLC guideline (~100K tokens) = ~$0.002 to index once.

- **Backout / Rollback:** Straightforward for POC. If RAG retrieval causes quality issues before Phase 3b ships, fall back to static fixture-based criteria. The Classifier Agent can be left in (minimal risk); Policy Mapper reverts to fixtures. pgvector can be dropped and replaced with Chroma without code changes (same retriever interface, ADR-011).

- **Next:** Begin Phase 3b Week 1 — Classifier Agent design + schema (ADR-022 + code).

#### AS-BUILT AMENDMENT — 2026-06-05 (implementation complete + eval-validated)

The planning record above is preserved as written. What actually shipped deviates on the vector DB and ADR numbering, and is now eval-validated. Recording the deltas-from-the-plan here.

- **Vector DB: Chroma (local) + LlamaIndex — NOT pgvector.** Decision reversed 2026-06-05 (Jim approved: *"switch to chroma and llamindex"*). This also **reverses the 2026-05-27 `scope-removal` of Chroma** — Chroma is back in scope, now over a real 12-criterion NSCLC corpus (4 indication categories × 3 criteria) instead of the old 1-fixture/3-criteria demo. Rationale: no external Postgres dependency for a POC; ADR-011's `PolicyRetriever` interface makes pgvector a Phase 4 swap with zero pipeline changes. The plan's own backout note anticipated this ("pgvector can be dropped and replaced with Chroma without code changes").
- **ADR numbering deviation:** ADR-021 (`RAG-NCCN-guideline-retrieval`) was NOT written as a separate doc. The Chroma decision + RAG design folded into **ADR-022** (Classifier Agent, now `APPROVED & IMPLEMENTED`) plus this amendment. ADR-011 remains the retriever-interface authority. No orphaned ADR-021 placeholder.
- **Determinism Contract invariants 11 & 12 are now ACTIVE** (were deferred). Invariant 11: embedding model pinned (`text-embedding-3-small`) in `rag/build_index.py` + `rag/chroma_retriever.py`. Invariant 12: index rebuild is idempotent (delete-before-recreate) — see bug 2 below. Invariant 13 (corpus-update-triggers-rebuild) is mechanically satisfied by the idempotent build but not yet enforced by a preflight; remains a Phase 4 hardening item. SCOPE_BASELINE updated to match.
- **Two integration bugs found during eval validation and fixed** (commit `3c0aba5`):
  1. **Source Verification Gate allowlist** missed the Phase 3b context fields (`patient_context.biomarkers`, `patient_context.prior_treatments`), causing hard pipeline failures when the Reasoning Drafter cited them. Fixed in gate + reasoning_drafter prompt (hash updated).
  2. **RAG index doubled on every rebuild** — `get_or_create_collection` + re-insert appended a full corpus copy each run (24 docs instead of 12), returning duplicate criteria that falsely escalated clean cases. Violated Determinism Contract invariants 12 & 13. Fixed to delete-before-recreate.
- **Eval baseline (dev-tier Sonnet, 2026-06-05, `eval_report_20260605_200000`):** per-case 3/15, aggregate 9/15. Pipeline completion **0.21 → 0.47** after the bug fixes (escalations halved, 49→24). Governance invariants held perfectly throughout: AI-decision-limit 1.00, adversarial-bypass 0.00, source-citation 1.00, cost ~$0.30/case. **Honest caveat:** the aggregate count and `clinical_signal_accuracy` (1.00→0.58) did not regress — the completion fix *doubled the scored sample* (6→12 cases), revealing the true clinical-signal score previously masked by uniform escalation.

- **Ship-tier Opus run — HYPOTHESIS REFUTED (2026-06-05, `eval_report_20260605_223300`).** We hypothesized the clinical-signal gap was Sonnet variance and that ship-tier Opus would be the fix. **Tested on Opus 4.1 (model_snapshot verified on live records): clinical_signal_accuracy went 0.58 → 0.50 — Opus was *worse*, not better.** The hypothesis is disproven by direct measurement. What Opus *did* improve was consistency, not correctness: decision_reproducibility 0.76 → 0.81 (crossed threshold), per-case pass 3/15 → 5/15, rationale_faithfulness 0.93 → 0.97. Governance invariants held identically (AI-decision-limit 1.00, adversarial-bypass 0.00).
  - **Root cause (the real finding):** the policy mapper has a **systematic conservative bias** — every clinical-signal mismatch is the same direction: `AI=does_not_meet` vs `expected=ambiguous|meets_criteria` (case_0004/0005/0011 expected ambiguous; case_0009 expected meets_criteria). The prompt defines "ambiguous" as requiring evidence *present but insufficient*, so **absent/silent evidence falls through to "unmet"**, and the `overall_signal` precedence cascades one "unmet" into a whole-case `does_not_meet`. It is **not model-tier** (Opus does it more) — it is **prompt calibration**, and fixing it is also a *product-correctness* fix: an over-strict policy mapper pre-judges `does_not_meet` instead of routing ambiguity to the nurse, which violates the "AI assists, nurse decides" model.
  - **CORRECTION (eval-critic, 2026-06-05):** an earlier draft of this entry claimed the bias was "one root cause behind three failing dims (clinical_signal, completion_rate, false_escalation), favorable on all three." That is **wrong** and is corrected here. The prompt fix targets **clinical_signal_accuracy** (its real lever). It does **not** straightforwardly improve completion_rate or false_escalation_rate, and may *regress* them: the confidence gate (`gates/confidence.py:133`) escalates on `overall_signal=="ambiguous"` but NOT on `does_not_meet`, so routing cases from `does_not_meet`→`ambiguous` can *increase* escalations. `case_0011` is **structurally** a false-escalation the prompt cannot fix (its correct answer is `ambiguous`, which trips the gate by design). The real lever for completion/false_escalation is the **confidence gate**, which also contradicts its own docstring (lines 32-36 intend to let 1-2 ambiguous "assist-able" cases through; line 133 escalates *all* ambiguous). That is a **separate** change, not to be bundled with the prompt fix.
  - **Fix (prompt):** recalibrate `prompts/policy_mapper.md` — reserve "unmet" for evidence that *affirmatively contradicts* a criterion; treat *absent/silent* evidence as "ambiguous". Eval-critic verdict: SOUND-WITH-CAVEATS (legitimate, not eval-gaming; adversarial-bypass 0.00 preserved; decision-emission invariant intact). Drafted + reviewed 2026-06-05; dev-tier re-run pending before commit. **Watch in re-run:** (1) clinical_signal should rise; (2) completion/false_escalation may NOT improve (gate-driven) — do not re-tune the prompt to chase them; (3) case_0002 (expected `does_not_meet`, 2 genuine `unmet`) must still land `does_not_meet` — if it drifts to `ambiguous`, the calibration over-corrected.
  - **Follow-up (separate):** confidence-gate recalibration to honor its own "1-2 ambiguous criteria are assist-able" intent — the actual lever for completion_rate + false_escalation_rate. Backlog; own change + own review.
  - **Cost telemetry caveat — DO NOT trust the Opus cost number.** Ship-tier reported $0.285/case, implausibly close to Sonnet's $0.295 despite Opus being ~5× list rate (reasoning sub-cost $0.264 vs $0.274). The SDK `total_cost_usd` is likely reporting a proxy/subscription flat cost, not per-token API pricing. Needs verification before any Opus cost figure is published.
- **Eval tooling:** `eval/save_report.py` now emits a machine-readable `eval_report_<ts>.json` alongside the `.md` (comparability-aware: tier, framework version, case-set, mode). Canonical source for a future eval diff/trend view (backlogged). Cheap hygiene; unlocks honest run-to-run comparison.
- **Cost dimension:** `_AGENTS_PER_RUN` 4→5, `_VECTOR_SEARCH_COST_PER_CASE` $0.001 added. Real telemetry shows ~$0.30/case (vs the planned ~$0.32-0.35 estimate — came in slightly under).
- **Commits:** `02843e0`→`3c0aba5` (Phase 3b build + UI + eval updates + bug fixes). Completion summary: `docs/PHASE_3b_COMPLETION_SUMMARY.md`.

---

### scope-addition: Phase 3a—Case Status Web UI + Audit Trail View + JWS Signatures + MongoDB — 2026-06-04 (AMENDED 2026-06-04)

- **Date logged:** 2026-06-04 | **Amended:** 2026-06-04
- **Decision:** User approved Phase 3a scope, later amended (Jim, 2026-06-04): *"Add MongoDB to active scope NOW (Phase 3a). Move from Phase 3b/4 deferral to immediate implementation."*
- **What's being added:**
  - **Phase 3a goal:** Web UI dashboard showing case status (pending, in review, completed, escalated) with real-time queue visibility
  - **Per-case audit trail view:** Click into any case to inspect decision_log with JWS signature verification in browser
  - **Supporting infrastructure Priority 1 (DONE ✓):** JWS signatures on JSONL records (2026-06-04 commit 28bc13c)
  - **Supporting infrastructure Priority 2 (ACTIVE NOW):** MongoDB implementation for production-scale audit storage
    - Hybrid architecture: MongoDB (online) + signed JSONL archive (forensic)
    - Nightly export from MongoDB to signed JSONL archive
    - No change to signature/hash-chain verification (preserved in archive)

- **Why this matters:**
  - **Current state (JSONL):** Works for pilot (50–200 cases/day); developers inspect via CLI
  - **Phase 3a goal (Hybrid):** MongoDB online for real-time nursing dashboards + signed JSONL archive for forensic verification by auditors
  - **Admissibility win:** Signatures + archive = "anyone can independently verify the audit trail is authentic" (offline, using public key)
  - **Production readiness:** MongoDB enables multi-nurse concurrent access, indexed queries, automatic backups
  - **Cost:** $0 (local Docker dev) or $50–200/mo (MongoDB Atlas cloud, production)

- **Implementation phases (UPDATED):**
  1. **Phase 3 Week 1 (DONE ✓):** JWS signatures on JSONL records (commit 28bc13c, 2026-06-04)
  2. **Phase 3 Week 2-3 (NEXT):** MongoDB implementation
     - `persistence/mongo_client.py` — CaseStore interface + MongoDBCaseStore implementation
     - `logs/bilateral_logger_mongodb.py` — sign-and-write to MongoDB (mirrors JSONL behavior)
     - `ops/export_signed_cases.py` — nightly batch job exporting completed cases to signed JSONL archive
     - Dual-write fallback (write to both JSONL and MongoDB during transition)
  3. **Phase 3 Week 4:** Web UI dashboard wired to MongoDB queries (real-time case status)

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
