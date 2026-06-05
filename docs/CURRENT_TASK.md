# Current Task — Updated 2026-06-04 (Phase 3a MongoDB Shipped)

## ✅ P1 COMPLETE (2026-05-31): Phase 1 of governance roadmap shipped

**All 4 P1 items delivered and tested:**
- **A1** ✅ — hash-chain bilateral logger inside `commit()` + `verify_audit_log.py` + tamper-drill test. Detects any record mutation/reordering/deletion.
- **A2** ✅ — physician ActionRecord + `DENIAL_GATE_MODE` now flow into decision_log JSONL. Single audit trail for "who decided, under what mode."
- **A3** ✅ — escalation-log + physician-enqueue paths fail-closed. No silent errors; all exceptions audited + propagated.
- **R1** ✅ — completion-gated eval dims return N/A (not vacuous 1.00) on 0-claim cases. Closes Eval Gap 9 (grounding inflation).

**Off-repo (orchestration session owns):** R10 risk-acceptance signature (Iris/CAIO), A7 legal doc, milestone chart, decision log. Don't duplicate.

Tests: 303 pass / 8 skip (verified; 1 new test added for hash-chain tampering drill). All green.

---

## What we just shipped (this session)

**Marketing & Governance Positioning (2026-06-01):**

Four comprehensive documents proving GPA's governance achievements for sales, compliance, and audit audiences:

| Document | Purpose | Content | Files |
|---|---|---|---|
| **Executive Summary** | Sales + compliance overview | 4 governance outcomes, stakeholder benefits, key metrics, admissibility story | `GPA_Marketing_Executive_Summary.md` (revised) |
| **White Paper** | Technical deep-dive proof | 6 sections: Governance (5 findings) + RAI (8 findings) + Safety (6 findings) + Fairness (4 findings) + Admissibility (5 findings) = 39 total. Evidence traced to code. | `GPA_White_Paper_Full.md` (new) |
| **Data Sheet** | Specs + metrics reference | System architecture, performance metrics, governance metrics, audit trail specs, fairness metrics, scalability, non-deployment gates | `GPA_DataSheet_Specs_and_Metrics.md` (new) |
| **Forensic Guide** | Auditor's verification handbook | 7-question forensic framework: right evidence? → right rules? → source trail complete? → agent authority? → confidence? → human review? → explainable?. Worked examples, bash commands, 7-phase checklist. | `GPA_Admissibility_Story_Forensic_Guide.md` (new) |

**Session Focus:** Marketing/positioning of P1+P2 governance achievements. Framed admissibility as technical proof (5 proofs: durable, tamper-proof, complete, transparent, fail-closed), not legal arguments. Removed legal framing; kept technical governance controls.

**Key Achievement:** Complete governance narrative covering enforcement (gates), safety (metrics), RAI (fairness, explainability, reproducibility), auditability (forensics), and admissibility (verification). Ready for sales/compliance review.

---

**P2 — R7 (Transparency Artifacts):**

| Item | Work | Files Created |
|---|---|---|
| **R7** (system + model cards) | Drafted system card (architecture, governance, fairness). Drafted 4 per-agent model cards (Evidence Summarizer, Context Retriever, Policy Mapper, Reasoning Drafter). Fairness/bias risks + mitigations explicit in every card. Paired with R10 (risk-acceptance). | `docs/R7_TRANSPARENCY_CARDS.md` (scope + outline), `docs/r7_system_card.md`, `docs/r7_model_cards_evidence_summarizer.md`, `docs/r7_model_cards_context_retriever.md`, `docs/r7_model_cards_policy_mapper.md`, `docs/r7_model_cards_reasoning_drafter.md` |

**R7 Acceptance Criteria (all met):**
- ✅ System card complete (architecture, governance, HITL checkpoints, failure modes, fairness governance, audit trail, non-deploy posture)
- ✅ 4 model cards complete (one per agent: Evidence Summarizer, Context Retriever, Policy Mapper, Reasoning Drafter)
- ✅ Fairness & bias section in every card (known risks + mitigations explicit)
- ✅ Limitations section honest and specific (not generic; names deferred items + why)
- ✅ No overclaiming ("fair" qualified by R10 non-deploy + R4/R5 deferral; "auditable" grounded in A1/A2)
- ✅ Readable by non-ML audience (plain language; regulations + frameworks cited)
- ✅ Linked to supporting artifacts (eval report, verify_audit_log.py, R10, ADRs)

**Earlier in session (prior commits referenced above):**
- Portfolio deck markdown (13-slide CAIO / hiring-manager hub)
- Portfolio deck `.pptx` (Google-Slides-import-ready)
- CURRENT_TASK.md mid-session update with real eval numbers
- README Quick Start block
- conftest.py + dotenv loading + `.env.example`
- Reset Demo Case States endpoint

## Latest eval (live, dev-tier Sonnet, recalibrated thresholds)

Report: `eval/results/eval_report_20260529_205655.md`

- **Per-case pass: 8/15** (was 1/15 pre-recalibration; predicted ~9, hit 8)
- **Aggregate dims pass: 12/15**
- 3 honest fails surfaced (false_escalation 60%, clinical_signal 58%, completion 59%) — root-caused to Sonnet variance; Opus would tighten
- Value bucket 3/4 · Trust 7/8 scored · Operational 2/3 scored
- Real per-case cost from SDK telemetry: **$0.291/case**

## ✅ P1 & P2 COMPLETE (2026-05-31)

**P1 Governance Roadmap (shipped):**
- A1 ✅ hash-chain bilateral logger + verify_audit_log.py
- A2 ✅ physician ActionRecord + DENIAL_GATE_MODE routed to decision_log
- A3 ✅ fail-closed escalation paths
- R1 ✅ completion-gated eval dims (N/A, not vacuous 1.0)
- R10 ✅ risk-acceptance (Iris signed)

**P2 Transparency & Admissibility (shipped):**
- R7 ✅ system card + 4 model cards (Evidence Summarizer, Context Retriever, Policy Mapper, Reasoning Drafter)
- A7 ✅ chain-of-custody legal doc (legal approved 2026-05-31, v0.2 with A4/A8 scope removal finalized)

**Tests:** 303 pass / 8 skip. All deliverables auditable + governed.

---

## ✅ GPA FEATURE-COMPLETE (2026-06-01)

**No more build work needed.** Architecture locked. Governance proven. Eval framework solid. Marketing materials ready.

---

## What's next (Phase 3b: RAG + Classifier Agent)

### 🎯 **PHASE 3b APPROVED (2026-06-04): RAG-Enhanced NCCN Guideline Retrieval + Classifier Agent**

**User approval:** Jim approved Phase 3b scope addition 2026-06-04.

**High-level goal:** Expand from fixture-based policy mapping (1 guideline, 3 criteria) to RAG-backed NCCN retrieval with explicit classification + gap detection. 5-agent pipeline.

**Scope:**
- **NEW:** Classifier Agent (cancer type, stage, ICD/CPT, therapy, urgency extraction)
- **ENHANCED:** Policy Mapper (vector search NCCN by indication, dynamic criteria retrieval)
- **ENHANCED:** Context Retriever (biomarkers, prior treatments, meds)
- **ENHANCED:** Reasoning Drafter (gap detection: flag missing staging, biomarkers, prior docs)
- **UI CHANGES:** Display all 5 agent outputs (classifier metadata, NCCN source, retrieved context, gap flags, RAG metadata)

**Timeline:** Weeks 13-20 post-Phase-3a (est. 8 weeks for full POC)

**Decisions finalized (2026-06-04):**
- ✅ Vector DB: **pgvector + LlamaIndex** (production-ready)
- ✅ NCCN corpus: **NSCLC only** (lean POC, Phase 4 for multi-cancer)
- ✅ Timeline: **Weeks 13-20** (8 weeks post-Phase-3a)
- ✅ Embedding model: **OpenAI text-embedding-3-small** (pinned snapshot)

**Phase 3b roadmap (Weeks 13-20):**
1. **Week 13-14:** ✅ Classifier Agent design + schema (ADR-022, tests)
2. **Week 15-16:** ✅ Embedder + Chunker infrastructure + 4 NCCN fixtures (CHROMA + LLAMAINDEX, not pgvector)
3. **Week 17-18:** ✅ Chroma + LlamaIndex vector index creation + Policy Mapper RAG integration
4. **Week 18-19:** Context Retriever expansion (biomarkers, prior treatments) — TODO
5. **Week 19-20:** Reasoning Drafter gap detection + UI integration (all 5 outputs) — TODO
6. **Week 20 (concurrent):** Update eval cost dimensions for new agents (Classifier + vector search); re-run full eval for Phase 3b baseline — TODO

**Decision (2026-06-05):** Use **Chroma (local) + LlamaIndex** instead of pgvector for POC. Simpler, no external DB, ADR-011 allows easy migration to pgvector in Phase 4.

**STATUS (end of session 2026-06-05):**
- ✅ 5-agent pipeline fully integrated (Classifier → Evidence → Context → Policy Mapper (RAG) → Reasoning)
- ✅ Chroma vector index built (12 NCCN criteria, NSCLC)
- ✅ Policy Mapper wired to query Chroma by cancer_type + indication
- ✅ 327 tests passing + 6 classifier tests ready for live eval
- ⏳ Remaining: Context Retriever enhancements, Reasoning Drafter gaps, UI, eval cost updates

**Next immediate:** Stabilize Phase 3a dashboard (live eval finishing tonight), then start Phase 3b Week 1 tomorrow.

---

## What's next (Phase 3a: Case Status UI + Audit Trail)

### 🎯 **PHASE 3a IN PROGRESS: Web UI for Case Status + Audit Trail View**

**Goal:** Non-technical nursing staff can view case status, click into any case, inspect full audit trail with cryptographic proof of authenticity.

**✅ COMPLETED (2026-06-04):**
1. **Phase 3 Week 1:** JWS signatures for JSONL audit records ✓
   - ✅ New: `config/key_generation.py` (RSA keypair generator, 40 lines)
   - ✅ New: `config/public_key.pem` (committed to repo, safe for verification)
   - ✅ Update: `logs/bilateral_logger.py` — signs records with RSA-PSS SHA-256 (25 lines added)
   - ✅ Update: `verify_audit_log.py` — verifies hash chain + JWS signatures (45 lines added)
   - ✅ Update: `tests/test_bilateral_logger.py` — adapted for signatures (1 line change)
   - ✅ Testing: All 8 existing tests passing, 1 new integration test passing
   - ✅ Eval framework: Compatible (signatures are additional fields, don't break dims)
   - **Payoff:** Audit trail now cryptographically proves GPA created each record
   - **Commit:** `28bc13c` (2026-06-04)

**✅ COMPLETED (2026-06-04):**
2. **Phase 3a Week 2–3:** MongoDB implementation ✓ (USER APPROVAL: 2026-06-04)
   - ✅ New: `persistence/mongo_client.py` — CaseStore ABC + MongoDBCaseStore (155 lines)
   - ✅ New: `logs/bilateral_logger_mongodb.py` — signs + writes to MongoDB (115 lines)
   - ✅ New: `ops/export_signed_cases.py` — nightly export job (125 lines)
   - ✅ New: `config/persistence.yaml` — mode toggle (jsonl ↔ mongodb)
   - ✅ New: `persistence/__init__.py` — factory + singleton pattern (50 lines)
   - ✅ New: `tests/test_mongodb_integration.py` — 10 comprehensive tests (170 lines)
   - ✅ Testing: All 10 new tests pass; 313 total tests pass / 8 skip
   - **Architecture:** Hybrid — MongoDB (online, indexed queries) + signed JSONL (archive, verifiable)
   - **Effort:** ~6 hours (completed on schedule)
   - **Payoff:** Production-ready audit storage, doc-level locking for concurrent nurses, indexed dashboard queries (50ms vs. 2s file iteration)
   - **Commit:** `5694f46` (2026-06-04)

**✅ COMPLETED (2026-06-04):**
3. **Phase 3a Week 4:** Case Status Dashboard UI ✓ (backend-agnostic via CaseStore)
   - ✅ New: `ui/cases.html` — status-filtered case table + click-into audit modal
   - ✅ New: `persistence/jsonl_store.py` — real JSONLCaseStore read path (was a stub)
   - ✅ New API: `GET /api/v1/cases` (+ `?status=` filter) and `GET /api/v1/cases/{id}/audit`
   - ✅ Refactor: `verify_audit_log.verify_records()` — backend-agnostic chain+signature
     verifier (works for JSONL files AND in-memory MongoDB records; single source of truth)
   - ✅ Modal renders per-record "✓ signature verified" pills + overall verification banner;
     honest red "VERIFICATION FAILED" on tamper
   - ✅ `ui/index.html` — dashboard link card + live case count
   - ✅ Testing: 12 new tests (`tests/test_cases_dashboard.py`); 325 total pass / 8 skip
   - ✅ Verified live: API backend=JSONLCaseStore, 19 cases; 3 freshly-signed demo cases
     verify end-to-end; browser render confirmed via preview snapshot
   - **Key property:** `PERSISTENCE_MODE=mongodb` swaps the backend with ZERO endpoint or
     UI changes — the dashboard demonstrates the CaseStore abstraction's payoff
   - **Commit:** `d5f9232` (2026-06-04)

**⏭️ NEXT (optional, pilot-gated):**
4. **Live MongoDB cutover** — only when pilot hits 50+ concurrent nurses or 100+ cases/day.
   Set `PERSISTENCE_MODE=mongodb` + `MONGODB_URI`; run `ops/export_signed_cases.py` nightly.
   Until then JSONL + CLI/dashboard verification is sufficient.

**Supporting decisions:**
- A4 (JWS signatures) is back in scope; 2026-05-31 removal is reversed (see SCOPE_DELTAS entry 2026-06-04)
- A8 (RFC 3161 timestamp) remains deferred; per-record timestamp in JSON is sufficient
- MongoDB in Phase 3a active scope (user approval 2026-06-04); trigger = 100+/day pilot volume

---

## What's next (measurement + market motion, not build)

1. **Marketing engagement** ✅ (materials ready 2026-06-01)
   - Executive Summary (4 governance outcomes, stakeholder benefits, admissibility story)
   - White Paper (6 sections, 39 findings, evidence traced to code)
   - Data Sheet (specs, metrics, audit trail, non-deployment gates)
   - Forensic Guide (7-question framework, auditor's handbook)
   - **Note:** All materials explicitly defer physician reversal rate to Phase 3 (production deployment needed)
   - **Action:** Sales/compliance review cycle + target accounts

2. **Interview & hiring prep**
   - Portfolio deck ready (13-slide CAIO/hiring-manager hub, `.pptx`)
   - Resume v4 ready (runtime governance + outcome-driven evals as two pillars)
   - Loom recording script ready (`docs/LOOM_SCRIPT.md`); decision pending on timing

3. **Phase 3 Planning** — Deferred; no work starting now
   - R4/R5 (demographic fairness testing on real data)
   - A9 (audit-log forensic validation)
   - R6 (oversight metrics), R8 (contestability)
   - Opus eval upgrade (tighter completion + clinical signal on ship-tier model)
   - Timeline: Post-marketing feedback cycle

**Removed from scope (2026-05-31):**
- ~~A4 (HMAC/signature)~~ — no AWS KMS costs
- ~~A8 (RFC 3161 timestamp)~~ — no TSA integration costs
- See `SCOPE_DELTAS.md` for rationale: O1 defensible via A1+A2+A3+A7 alone

## Open questions / decisions pending

- Timing of Loom recording (now vs. after Phase 3 decision).
- Target accounts for initial marketing engagement.

## Recently rejected directions (this & prior sessions)

- **Physician reversal rate** (2026-06-01) — No prod data, so deferred to Phase 3. Marketing materials explicit: we prove system behavior, not physician adoption.
- **Cohen's κ** — meta-eval; doesn't move OKR1/OKR2.
- **Larry-style dev orchestrator** — routing overhead kills velocity; chose project-level `.claude/agents/` subagents instead.
- **`load_dotenv()` in library modules** — silent side effects on import; entry points own env loading.
- **"Reusable components" framing in resume** — sounds like consultant deliverable; v4 cut it and leads with runtime governance + outcome-driven evals as the two pillars.
- **GraphRAG-Pharma portfolio project (prior session)** — pulled back pending problem-discovery research on adjacent verticals.
