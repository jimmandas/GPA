# Phase 3 Backlog

**Purpose:** Tracks items deferred beyond Phase 2 (Weeks 9-12). Phase 3 is the "Scale + Production" horizon named in scope doc §"Phase 3 (Future)." This file is the running list — including items already named in the scope doc and additions logged after Phase 2 work begins.

**Decision rule:** Items here are NOT prioritized. They are inventoried. Promotion to active work requires (a) a trigger condition being met (b) explicit user approval (c) an ADR for the implementation choice (d) corresponding entry in `SCOPE_DELTAS.md`.

---

## From scope doc §"Phase 3 (Future): Scale + Production"

| # | Item | Trigger to prioritize |
|---|---|---|
| 1 | Multi-workflow expansion (oncology treatment reviews, exception handling) | After oncology imaging shows stable production-grade metrics |
| 2 | Real EHR integration (HL7, FHIR API-based evidence ingestion) | Pilot deployment commitment with a payer or health system |
| 3 | Real-time governance dashboard | When real-time SLA monitoring becomes a regulatory requirement |
| 4 | Multi-rater labeling at scale | When eval dataset grows beyond 100 cases and Cohen's κ needs broader sampling |
| 5 | Human override workflow with logged rationale | When nurse / physician overrides become a real signal for prompt or rubric iteration |
| 6 | A/B testing framework | When prompt or model changes need to be compared in production rather than offline eval |
| 7 | Decision-rights matrix (per-authorization-type autonomy levels) | When the system handles >1 authorization category with different governance profiles |
| 8 | Runtime policy enforcement (policy changes without code redeploy) | When NCCN updates a guideline and the current rebuild-eval-redeploy loop is too slow |
| 9 | Regulatory compliance reporting | Pre-deployment to a regulated environment (HIPAA, state regulator filings) |

---

## Added after Phase 2 work began

### 10. Full RAG pipeline: parse / chunk / embed / index over a real corpus

- **Date logged:** 2026-05-27 (expanded from "Chroma → pgvector migration" after Phase 2 RAG cut)
- **What:** The actual RAG work the Phase 2 plan envisioned but Phase 2 did NOT deliver:
  - **Acquire source material** — public-domain clinical-guidelines corpus (NCCN is proprietary; substitutes: CDC clinical guidelines, ASCO consensus statements, USPSTF recommendations)
  - **PDF / HTML parsing** — PyMuPDF, pdfplumber, or equivalent; extract text + section structure
  - **Chunking strategy** — semantic chunking by section/passage OR fixed-size-with-overlap; metadata captured per chunk (section ID, page, effective date, guideline version)
  - **Real embedding** — pinned sentence-transformer or OpenAI embedding snapshot, applied to PARSED chunks (not hand-authored YAML)
  - **pgvector + LlamaIndex** — Postgres-backed index with hybrid (BM25 + vector) retrieval; replaces the current Chroma demo
  - **Re-activate Determinism Contract invariants 11, 12, 13** — embedding model pinning, RAG index content-hashing, corpus-update-triggers-rebuild policy
- **Why this is Phase 3, not Phase 2:**
  - **No strategy / PRD outcome depends on it.** Documented in Phase 2 deferral decision (2026-05-27 reality-check) — zero OKR2 KRs and zero PRD acceptance criteria require RAG. RAG is architectural completeness for a production future-state, not value for the current nurse-anchored governance proof.
  - **The actual GPA build's "NCCN corpus" was one hand-authored YAML file with 3 criteria** — even the existing Chroma demo retrieves over hand-structured data, not parsed source documents. Calling that "RAG" was overstated.
  - **Production HIPAA story belongs with Phase 3 deployment work** — pgvector inherits Postgres's HIPAA-eligible deployment posture; Chroma's is less established. Bundle this with item #2 (Real EHR integration).
- **What stays in the Phase 2 build** (preserved for Phase 3 to build on):
  - `PolicyRetriever` ABC (ADR-011)
  - `FixtureRetriever` (active retriever for the governance proof)
  - `ChromaRetriever` code + 1-fixture demo index (proof the interface generalizes)
  - `RAGIndexValidator` preflight (validates fixture-mode hash today; ready for real corpus)
  - ADRs 011, 012, 013 (Phase 3-deferral addendums applied)
- **Trigger to prioritize:**
  - Commitment to a regulated production deployment (bundles with item #2 Real EHR integration), OR
  - Strategy OKR3 (Provider Flywheel) work is greenlit and needs richer rationale provenance, OR
  - A payer / health system stakeholder commits to a pilot with real authorization volume
- **Migration scope when activated:**
  - Parser + chunker module (new — `rag/parse.py`, `rag/chunk.py`)
  - `PgvectorRetriever` (new — replaces `ChromaRetriever`)
  - LlamaIndex wrapper for hybrid retrieval
  - Real-corpus build script (replaces `build_chroma_index.py`)
  - Activate Determinism Contract invariants 11-13
  - New ADR documenting the full pipeline (likely ADR-019+)

---

## Added from other Phase 2 follow-ups

### 11. Multi-physician concurrency on PhysicianQueue

- **Date logged:** 2026-05-27
- **What:** Replace `FilePhysicianQueue` (single-writer, JSON-file-backed) with `PostgresPhysicianQueue` (row-locked, multi-writer).
- **Why deferred:** Named explicitly in ADR-014 §"What This ADR Does NOT Cover": *"FilePhysicianQueue is single-writer. Production needs queue-service semantics."*
- **Trigger to prioritize:** Multiple physicians actively reviewing concurrently in a pilot or production setting.

### 12. Stronger judge model for audit-grade faithfulness scoring

- **Date logged:** 2026-05-27
- **What:** Add a GPT-5 (or equivalent frontier) audit overlay that re-grades a 20-25% sample of cases. Computes Judge-Audit Agreement Rate as a calibration check on the daily GPT-4o judge.
- **Why deferred:** User passed on judge calibration tracks in 2026-05-27 session. The path stays available.
- **Trigger to prioritize:** Faithfulness scores need to be production-defensible to a regulator OR the daily judge starts looking like the bottleneck on detecting issues.

### 20. AI Evals expansion — accuracy / hallucinations / benchmarks (Phase 3)

- **Date logged:** 2026-05-28
- **Context:** During v3 eval-framework design, identified that traditional "AI Evals" (the model-eval sub-category of the broader eval landscape) has three primitives the GPA framework doesn't fully cover: accuracy, hallucinations, benchmarks.
- **What's missing today:**
  - `accuracy_vs_clinical_truth` — % of cases where the AI's full clinical assessment matches a clinician-labeled correct answer. We added `clinical_signal_accuracy` in v3 as a proxy (signal-alignment with `expected_overall_signal`) but real clinical accuracy needs clinician-graded cases. PRD §1 honest limit: clinical accuracy is out of POC scope.
  - `hallucination_rate` (composite) — single-number summary derived from `source_citation_accuracy` + `rationale_faithfulness` + `citation_correctness`. Useful for a regulator who wants "the hallucination number," not three numbers to triangulate.
  - `benchmark_alignment_*` — runs against published benchmarks (MedQA, ASCO, USPSTF clinical-reasoning tests). Useful for cross-system comparability.
- **Why deferred:** All three need either clinical-grader involvement (accuracy) or external benchmark integration work (benchmarks). The composite hallucination_rate is cheap to add (~30 min) but doesn't add measurement that the existing three dims don't already provide; it's a packaging improvement.
- **Trigger to prioritize:** External evaluation by clinical advisors OR submission of the build for industry benchmarking (e.g., a payer-AI competition).

### 21. Observability dims — trace completeness, log integrity (Phase 3)

- **Date logged:** 2026-05-28
- **Context:** Identified that "Observability" (traces, latency, logs) is the third traditional eval sub-category. GPA has the infrastructure (bilateral logger + Pipeline Trace UI) but no dims that SCORE observability quality.
- **What's missing today:**
  - `trace_completeness_rate` — % of cases where the bilateral log contains all expected event types (pre_state, 4 agent_events, 5 gate_events, post_state). Catches partial / interrupted traces.
  - `log_integrity_rate` — % of bilateral log records that have all required fields populated (no malformed entries, no missing timestamps, no hash mismatches).
  - `latency_variance_score` — coefficient of variation of pipeline wall time. Tail latency was added in v3 (p90); a variance number adds another reliability dimension.
- **Why deferred:** None are blocking. The infrastructure (bilateral logger, Pipeline Trace UI) is already in production-grade shape; these dims add SCORING on top, which becomes meaningful at scale (>50 cases). At n=15, log-integrity dim would be trivially passing.
- **Trigger to prioritize:** Production-deployment pre-flight OR observability concerns surfaced by an SRE review.

### 22. Real ROI measurement (Phase 3 — bigger than item #18)

- **Date logged:** 2026-05-28
- **Context:** v3 added `estimated_roi_per_case_usd` using a heuristic (manual-review baseline × nurse hourly rate − API cost). User feedback: *"ideally we want to show ROI from the eval."* The heuristic surfaces the dimension; real ROI needs production data.
- **What's missing today (beyond the heuristic):**
  - Real nurse-time-per-case measurements (pre/post AI pilot)
  - Real provider TAT measurements (pre/post)
  - Real denial-rate / appeal-rate changes
  - Real member-satisfaction delta
  - Per-payer / per-region ROI breakdowns
- **Why deferred:** All require months of production data or a pilot study with real users. Bigger than #18 Tier 2 (which is per-case dims); item #22 is the SYSTEM-LEVEL ROI story for an executive audience.
- **Trigger to prioritize:** Pilot deployment OR a board / payer-buyer conversation needing ROI evidence.

### 23. Evals as Enterprise Value Instrumentation — strategic positioning

- **Date logged:** 2026-05-28
- **Context:** During v3 design, identified that the GPA eval framework operates at a *higher level* than traditional model/agent/observability evals. It measures: trust, admissibility, workflow correctness, operational quality, governance adherence, business impact, ROI realization. This is "AI operational intelligence" — a market-positioning concept worth surfacing.
- **What this is NOT (a Phase 3 deliverable):** It's not a feature to build. It's a positioning thesis that informs HOW the existing eval framework is described to a market.
- **Why it's logged here:** Phase 3 may include market-facing materials (whitepaper, pitch deck, conference talk). The positioning thesis is the throughline for those.
- **The thesis (in one sentence):** Traditional AI eval frameworks measure model behavior; enterprise-grade AI eval frameworks measure organizational accountability. The GPA framework is the second.
- **Implementation when activated:** Whitepaper / blog post / conference submission. Maps the 16 dims to the 7 enterprise-value categories (trust, admissibility, workflow correctness, operational quality, governance adherence, business impact, ROI realization) and shows how the 3-bucket structure maps to enterprise-org questions (CFO, regulator, SRE).

### 18. Tier 2 business-value eval dims (need ground-truth fields)

- **Date logged:** 2026-05-28
- **What:** Three dims that close OKR1-outcome measurement but need data we don't have yet.
  - `tat_reduction_estimate` — system wall-time vs. published manual-review baselines for PA. Requires either a hard-coded baseline (e.g., "5 min per case manual" from published UM studies) OR a real pilot pre/post comparison.
  - `nurse_time_saved_per_brief_minutes` — workflow compression value. Needs either nurse-pilot data OR a heuristic based on `uncertainty_flag` count × seconds-per-flag-review.
  - `over_review_rate` — % of cases where the nurse reads the brief but doesn't gain new info vs. what she'd have decided without it. Requires nurse-pilot data; not feasible without real users.
- **Why deferred:** All three require external data (baselines or pilot users). The Tier 1 dims (v3 — pipeline_wall_time, completion_rate, cost_estimate, gate_fire_distribution) cover what's measurable today without external data.
- **Trigger to prioritize:** Pilot deployment with real nurses OR commitment to a quantified TAT-reduction claim that needs a defensible baseline.

### 19. Tier 3 business-value eval dims (need production telemetry)

- **Date logged:** 2026-05-28
- **What:** Dims that only make sense once the system has real production deployment.
  - `actual_provider_TAT_minutes` — measured from real provider submission → notification timestamps
  - `actual_member_satisfaction_delta` — pre/post member surveys
  - `appeal_rate_change` — operational outcome over months
  - `production_token_cost_actual` — real SDK telemetry replacing the v3 heuristic
- **Why deferred:** All four require months of operational data. Out of scope for Phase 2 (POC) and Phase 3 (until a real pilot).
- **Trigger to prioritize:** Live production pilot OR commitment to operational outcomes claims that need actuals not estimates.

### 17. Opus reasoning_drafter JSON parse stability

- **Date logged:** 2026-05-28 (surfaced by the 2026-05-27 ship-tier eval)
- **What:** On the ship-tier (Opus 4.1) eval run, the `reasoning_drafter` agent produced JSON outputs that failed `json.loads()` on 2-3 of 5 runs for 6 cases (case_0001, 0006, 0008, 0009, 0011, 0014). The pipeline correctly logged `schema_validation_event` records and cascaded to the next attempt, but this dropped `decision_reproducibility` to 0.60 on those cases (3/5 modal signal + 2/5 None).
- **Root cause (from one captured event):**
  - `failure_reason: "json_parse_error"`
  - `failure_detail: "Expecting ',' delimiter: line 56 column 701 (char 3794)"`
  - Opus's longer / more verbose output occasionally contains unescaped quotes, missing commas, or truncation-induced invalid JSON
- **Why Sonnet doesn't show this rate:** Sonnet outputs are shorter and less likely to hit edge cases in JSON formatting. The eval framework's earlier dev-tier (Sonnet) runs had 0-1 schema validation failures vs. Opus's 2-3 per case.
- **Recommended fix paths (any one, ordered by likely-effective):**
  1. **Anthropic structured output / tool-use schema enforcement** — if available for Opus 4.1, this is the cleanest fix; lets the model emit guaranteed-valid JSON
  2. **Prompt tightening** — explicit "output ONLY a JSON object, no markdown fences, no commentary, no trailing text" + add a section after the schema spec showing a valid example
  3. **Post-processing JSON repair** — add a `_try_repair_json()` step that catches common Opus patterns (unescaped quotes inside strings, trailing commas in lists, markdown fence wrappers) and retries the parse once before failing
  4. **Retry-with-feedback** — if first parse fails, send the model the error message and ask it to fix; one extra round-trip per case
- **Not blocking Phase 2 ship** because:
  - The pipeline correctly LOGS the failure (write-before-emit invariant holds)
  - The reproducibility dim correctly catches the failure (not a silent bug)
  - The cases that fail this still produce a valid brief on 3/5 runs (modal signal is recoverable)
  - Sonnet (dev-tier) doesn't show this rate, so daily iteration is unaffected
- **Trigger to prioritize:** Pre-production deployment OR shipping ship-tier eval numbers externally (e.g., to a regulator or external reviewer). Either context, reliability of the reasoning_drafter on Opus needs to be near-100%.

### 13. Bilateral logger physician_action event audit-log unification

- **Date logged:** 2026-05-27 — **partially shipped this session**
- **What:** Phase 2 plan §11 calls for physician action events to flow into the same audit trail as nurse decisions. Today: shipped at the record_action() boundary, writes to per-case `decision_log/{case_id}.jsonl`. Phase 3 extension: add a cross-case "audit trail explorer" view to surface every physician action across cases for compliance reporting.
- **Trigger to prioritize:** Compliance reporting becomes a real requirement (intersects with item #9).

### 14. EHR FHIR stub upgrade (cut from Phase 2)

- **Date logged:** 2026-05-27 (cut from Phase 2)
- **What:** Upgrade `patient_history_lookup` / `prior_imaging_lookup` from ad-hoc JSON fixtures to HL7 FHIR R4 resource schemas (Patient, DiagnosticReport, ImagingStudy). Version-pin schemas in `config/tool_registry.yaml` per Determinism Contract invariant 14.
- **Why deferred:** Customer anchor is the nurse; the underlying data shape is invisible to her. FHIR is a production-integration concern tied to real EHR work, not a governance/judgment concern.
- **Trigger to prioritize:** Bundled with item #2 (Real EHR integration). They prioritize together — there's no value in synthetic FHIR without real EHR plumbing on the other end.

### 15. Provider Experience Track — bundle (cut from Phase 2)

- **Date logged:** 2026-05-27 (cut from Phase 2)
- **What:** Three Phase 2 items that collectively serve provider experience (strategy OKR3, not the GPA build's customer anchor):
  - **EvidenceLineageBuilder** — pure-function tool that constructs evidence lineage from Source Verification Gate records
  - **Provider Explanation API upgrade** — full rationale with evidence lineage end-to-end (replaces "basic structured rationale")
  - **Evidence Lineage Completeness eval dim** — scores whether the API traces every claim back to a specific retrieved passage
- **Why deferred:** Strategy OKR3 ("Provider Flywheel") is a different strategy track than what the GPA build targets (nurse-anchored governance proof per OKR2). Phase 2 plan named these because the original framing treated provider experience as a strategic dependency; the nurse-anchor decision (2026-05-27) made these explicitly out of scope for this build.
- **Trigger to prioritize:** Strategy OKR3 work is greenlit OR a payer / provider stakeholder commits to using a provider-facing surface (status visibility, rationale visibility, digital intake).
- **Dependencies:** Some Phase 3 items also unlock this — real EHR integration (#2) and runtime policy enforcement (#8) overlap.

### 16. Dataset expansion to scope target (cut from Phase 2)

- **Date logged:** 2026-05-27 (cut from Phase 2)
- **What:** Expand the eval dataset from the current 15 cases to the scope §7 target (25-30) or the Phase 2 plan target (50-75).
- **Current state:** 15 cases (4 clean / 6 judgment-intensive / 5 adversarial) — covers the architectural diversity but is below the scope §7 target of 25-30. The build ships at 15 with a documented limitation.
- **Why deferred:** Statistical power is a calibration concern, not a governance-proof concern. The architecture works on 15 cases; scaling the dataset doesn't change what the system proves.
- **Trigger to prioritize:** Multi-rater labeling at scale (#4) lands OR the eval results need tighter confidence intervals for a specific portfolio claim.
- **Implication for the eval report:** The current report should explicitly name "n=15" as a limitation, with the scope §7 target (25-30) and Phase 2 plan target (50-75) cited as what production-grade evidence would require.
