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

### 10. Vector store migration: Chroma → pgvector (+ LlamaIndex)

- **Date logged:** 2026-05-27
- **What:** Replace the current `ChromaRetriever` implementation with a `PgvectorRetriever` backed by PostgreSQL + pgvector extension, optionally wrapping a LlamaIndex retrieval pipeline for hybrid (BM25 + vector) retrieval and response synthesis.
- **Why deferred:**
  - Phase 2 prioritizes proving the governance model and retriever-interface pattern; Chroma is sufficient for a single-node POC
  - The `PolicyRetriever` ABC (ADR-011) makes the swap mechanical when the time comes
  - pgvector earns its place only at production scale where the Postgres ops stack (backup, RBAC, HA, observability) and HIPAA-eligible deployment posture matter
- **Why it belongs on Phase 3:**
  - **Production HIPAA story** — pgvector inherits Postgres's HIPAA-eligible deployment story; Chroma's is less established
  - **Operational maturity** — backup / replication / migrations are standard Postgres tooling
  - **Hybrid retrieval** — NCCN passage IDs benefit from BM25 + vector together; LlamaIndex provides this out of the box
  - **Audit defensibility** — at scale, the audit trail is easier to defend against a regulator on a standard RDBMS than on an embedded vector DB
- **Trigger to prioritize:**
  - Commitment to a regulated production deployment, OR
  - Eval dataset / corpus exceeds Chroma's comfortable single-node scale (rough threshold: NCCN corpus > 10k passages OR > 100 concurrent queries), OR
  - HIPAA-eligible AWS deployment is committed
- **Migration scope (when activated):**
  - New `PgvectorRetriever` implementing the existing `PolicyRetriever` ABC
  - Index build script for pgvector
  - LlamaIndex wrapper for hybrid retrieval (BM25 + vector + reranking)
  - Determinism Contract carry-over (invariants 11-13 already designed to be retriever-agnostic)
  - Migration ADR (next available number, currently 018+)

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

### 13. Bilateral logger physician_action event audit-log unification

- **Date logged:** 2026-05-27 — **partially shipped this session**
- **What:** Phase 2 plan §11 calls for physician action events to flow into the same audit trail as nurse decisions. Today: shipped at the record_action() boundary, writes to per-case `decision_log/{case_id}.jsonl`. Phase 3 extension: add a cross-case "audit trail explorer" view to surface every physician action across cases for compliance reporting.
- **Trigger to prioritize:** Compliance reporting becomes a real requirement (intersects with item #9).
