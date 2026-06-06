# GPA Scope Baseline

**Owner:** Jim
**Last updated:** 2026-05-27
**Eval framework version:** **v3** (RAI-aligned + business-value; 18 active dims after cohens_kappa removal 2026-05-28; see `CHANGELOG.md`)
**Phase 2 build version:** in-development (Week 11-12)
**Source-of-truth docs:** see "Canonical Docs" below

This file is the audit-grade reference for what's in scope, what's pending, and what's deviated. It captures the project's invariants, references the canonical PM docs, and tracks Phase 2 deliverables against the plan.

When a regulator, hiring manager, or new contributor opens the repo and asks "is this build aligned with the original scope?" — this file is the one-page answer.

For session-to-session continuity, the same baseline lives in `~/.claude/projects/.../memory/scope_baseline.md` (auto-loaded by Claude).

---

## Canonical Docs (the hierarchy)

```
Strategy Framing v2  ← the why (vision, OKRs, runtime governance thesis)
        ↓
POC Scope v4   +   PRD v4  ← the what (7-week MVP, 4 agents, 4 gates, 8 eval dims)
        ↓
Phase 2 Agentic RAG Plan  ← the next (Weeks 9-12, RAG, physician workflow)
        ↓
This repo (GPA)  ← the execution
```

All four canonical docs live outside the repo at:
`~/claude/projects/My AI Team/Owner's Inbox/imaging-pa-poc-scope-2026-05-22/`

| Doc | File | Role |
|---|---|---|
| Strategy framing | `strategy-framing-v2.docx` (canonical) + `strategy-framing-v2.md` (searchable mirror) | Vision, OKRs, runtime-governed operating model thesis |
| POC scope | `imaging-pa-poc-scope.md` | 7-week MVP build plan, agents/gates/eval/timeline |
| PRD | `imaging-pa-poc-prd.md` | Detailed reqs, data contracts, acceptance criteria |
| Phase 2 plan | `phase-2-agentic-rag-plan.md` | Weeks 9-12: RAG + physician workflow + new ADRs |
| Strategy → MVP alignment | `strategy-to-mvp-alignment.md` | Trace strategy claim → MVP architectural choice |

---

## Hard Invariants

These do NOT move without explicit user approval (and a logged delta in `SCOPE_DELTAS.md`).

### Customer & decision model

- **Customer anchor: nurse reviewer.** Project goal is workflow compression + judgment assist for the nurse. (NOT provider experience — that's a separate strategy track per OKR3.)
- **AI-Assists / Human-Decides.** AI surfaces evidence and drafts reasoning. The nurse decides. The physician decides on denial.
- **No AI-emitted decision. Ever.** `reasoning_brief.json` schema has no `decision` field.
- **No autonomous denial.** `determination.json` accepts only `{approve, escalate}`. Phase 2 unlocks denial via PhysicianQueue + ActionRecord — not by relaxing the gate.

### Determinism Contract (10 invariants — scope §6 / §9)

1. `temperature=0` on every LLM call
2. Pinned model snapshot: `claude-opus-4-1-20250805` (production)
3. Prompt-byte SHA-256 hashing (per agent)
4. Tool fixture content hashing
5. No retrieval in MVP (RAG enters Phase 2)
6. `max_turns` pinned per agent (1/3/3/1)
7. Deterministic aggregation (`mean()`, no LLM aggregation)
8. Hooks as pure functions
9. Byte-identical event stream across 5 runs (mod timestamps)
10. `ClaudeAgentOptions` version-pinned

### Phase 2 extensions (invariants 11-14) — STATUS: 11-12 ACTIVE (Phase 3b), 13 partial, 14 removed

Activated by Phase 3b RAG (Chroma + LlamaIndex, 2026-06-05). See SCOPE_DELTAS Phase 3b as-built amendment.

| # | Invariant | Status |
|---|---|---|
| 11 | Embedding model snapshot pinned | ✅ **active** — `text-embedding-3-small` pinned in `rag/build_index.py` + `rag/chroma_retriever.py` (Phase 3b, 2026-06-05) |
| 12 | RAG index content-hashed | ✅ **active** — index rebuild is idempotent (delete-before-recreate); 12-criterion NSCLC corpus in Chroma. (Content-hash preflight is Phase 4 hardening; idempotent build is the load-bearing guarantee today.) |
| 13 | Corpus update requires rebuild + eval re-run | ⚠ partial — idempotent rebuild makes this mechanically true; no automated preflight enforcing it yet (Phase 4) |
| 14 | EHR stub schemas version-pinned | ❌ removed (FHIR upgrade cut) |

### Eval framework

- **18 dimensions** across 3 buckets (Value 4 / Trust 10 / Operational 4; v3, 2026-05-28)
- **9 named failure modes** (scope §8)
- **15 cases** shipped (scope-cut from original 25-30; see SCOPE_DELTAS)
- **LLM-as-judge: different vendor** (GPT-4o pinned snapshot `gpt-4o-2024-11-20`)
- ~~**Cohen's κ ≥ 0.60** (Jim + Pax co-labels)~~ — **REMOVED 2026-05-28**, see SCOPE_DELTAS

---

## Phase 2 Deliverable Status

Per `phase-2-agentic-rag-plan.md`:

| Phase 2 Week | Deliverable | Status |
|---|---|---|
| 9 | pgvector + LlamaIndex setup | ❌ **REMOVED 2026-05-27** (entire RAG initiative deferred to Phase 3) |
| 9 | Embedding model pinning + `RAGIndexValidator` | ❌ **REMOVED 2026-05-27** — RAGIndexValidator code deleted (redundant with tool_registry hashing); ADR-012/013 carry Phase 3-deferral addendums |
| 9 | `nccn_passage_lookup` RAG upgrade | ❌ **REMOVED 2026-05-27** — `PolicyRetriever` ABC + `FixtureRetriever` are active; ChromaRetriever code deleted |
| 10 | EHR stub upgrade (FHIR-structured) | ❌ **REMOVED 2026-05-27** (nurse anchor; provider/EHR is Phase 3) |
| 10 | Tool registry version-pinning | ✅ done (config/tool_registry.yaml) |
| 10 | Denial Gate routing logic | ✅ done (ADR-014) |
| 10 | `PhysicianQueueAgent` scaffolded | ✅ done (`physician_queue/`) |
| 11 | Physician queue UI | ✅ done (`ui/physician_queue.html` + `ui/physician_workspace.html` + 3 API endpoints) |
| 11 | Physician action handlers | ✅ done (`record_action()`) |
| 11 | Bilateral Logger extension for physician_action | ✅ done |
| 11 | `EvidenceLineageBuilder` | ❌ **REMOVED 2026-05-27** (provider track; Phase 3) |
| 11 | Provider explanation API upgrade | ❌ **REMOVED 2026-05-27** (provider track; Phase 3) |
| 12 | 50-75 case dataset | ❌ **REMOVED 2026-05-27** (ship at 15 with documented limitation) |
| 12 | `ConfidenceCalibrator` | ⏳ pending — overlaps with runtime confidence gate (ADR-015) |
| 12 | Threshold recommendations | ⏳ pending — depends on ConfidenceCalibrator |
| 12 | Full eval run + ADRs merged | ⏳ partial — eval framework live; ADRs 015-016 + ship-tier run pending |

### Phase 2 eval dimensions (v2 — RAI-aligned expansion)

The eval framework was bumped from v1 (8 scope §7 dims) to **v2 (12 active dims)** on 2026-05-27 to explicitly cover all 6 RAI evaluation categories the strategy doc §6 names as core constraints. See `SCOPE_DELTAS.md` for the full v1→v2 changelog.

**4 per-case dims (scope §7, unchanged from v1):**

| Dimension | RAI category | Status |
|---|---|---|
| source_citation_accuracy | Grounding | ✅ |
| ai_decision_limit | Safety | ✅ |
| rationale_faithfulness | Grounding + Explainability | ✅ (judge pinned to `gpt-4o-2024-11-20`) |
| decision_reproducibility | Trustworthy | ✅ |

**3 aggregate dims (scope §7; cohens_kappa removed 2026-05-28):**

| Dimension | RAI category | Status |
|---|---|---|
| adversarial_gate_bypass_rate | Safety | ✅ |
| false_escalation_rate | HITL + Operational | ✅ |
| confidence_calibration | Trustworthy | ✅ |
| ~~cohens_kappa~~ | ~~Trustworthy~~ | ❌ **REMOVED 2026-05-28** (meta-eval; ~10 person-hour cost, doesn't move OKR1/OKR2 — see SCOPE_DELTAS) |

**Phase 2 §12 additions (wired into runner 2026-05-27):**

| Dimension | RAI category | Status |
|---|---|---|
| physician_queue_routing_accuracy | HITL + Policy compliance | ✅ wired (returns N/A until route mode + labeled cases) |
| physician_rationale_compliance | Policy compliance | ✅ wired (returns N/A until physician actions exist) |

**Scope-additions (this build):**

| Dimension | RAI category | Status |
|---|---|---|
| bias_disparity (ADR-018) | Fairness | ✅ wired (cohort cuts: label_category, indication_category) |
| citation_correctness | Grounding (closes scope §8 Failure Mode #9) | ✅ wired |

**Removed dims (logged in `SCOPE_DELTAS.md`):**

| Dimension | Reason |
|---|---|
| RAG Passage Relevance | RAG initiative deferred to Phase 3 (2026-05-27) |
| Evidence Lineage Completeness | Provider experience track cut (2026-05-27) |

---

## ADR Registry

ADR-000 through ADR-018 are written, plus ADR-022 (Phase 3b Classifier Agent + RAG, 2026-06-05). (Phase 2 plan originally reserved 015-016 for confidence calibration and max_turns budget; both were written 2026-05-27 and corrected in this registry on 2026-05-28. ADR-019-021 were not written — 019-020 unused; 021 folded into ADR-022 + SCOPE_DELTAS as-built amendment.)

| # | Title | Status |
|---|---|---|
| 000 | Solution shape (AI-Assists / Human-Decides) | ✅ |
| 001 | State machine choice | ✅ |
| 002 | Orchestration framework | ✅ |
| 003 | RAG when and why not yet (MVP) | ✅ |
| 004 | Tool mocking strategy | ✅ |
| 005 | Write-before-emit pattern | ✅ |
| 006 | Source Verification Gate | ✅ |
| 007 | AI-Decision-Limit Gate | ✅ |
| 008 | Nurse workspace design | ✅ |
| 009 | Eval methodology | ✅ |
| 010 | Policy mapper direct anthropic SDK | ✅ |
| 011 | RAG architecture and retriever interface | ✅ |
| 012 | Embedding model pinning | ✅ |
| 013 | Corpus update policy | ✅ |
| 014 | Denial Gate unlock + physician workflow | ✅ |
| 015 | Confidence threshold calibration | ✅ |
| 016 | max_turns budget increase | ✅ |
| 017 | EVAL_TIER: dev/Sonnet vs ship/Opus | ✅ (renumbered from earlier draft 015) |
| 018 | Bias / disparity monitoring | ✅ (scope-addition) |
| 022 | Classifier Agent design (+ Phase 3b RAG: Chroma over pgvector) | ✅ APPROVED & IMPLEMENTED (2026-06-05). ADR-021 folded in — see SCOPE_DELTAS as-built amendment |

---

## Approved Scope Additions (beyond the original docs)

Tracked in `SCOPE_DELTAS.md`. Active items:

- **Ground-Truth Label Audit — TOP PRIORITY** (approved 2026-06-06). Audit the 15-case GT labels for internal consistency via a documented clinical/NCCN-derived labeling rubric (incl. `not_applicable`); relabel inconsistencies with per-change rationale. Makes the eval trustworthy as a *scoreboard*. Sequences ahead of the not_applicable + confidence-gate eval tasks (they validate against these labels). Constraints: rubric derived from clinical logic then applied blind (no label-fitting to model output); NO Cohen's κ / multi-rater (stays cut); suite stays 15 cases.
- **Runtime confidence gate** — not in original scope; user approved adding 2026-05-27. Maps to planned ADR-015.
- **Bias monitoring** — not in original scope/strategy; user approved adding 2026-05-27. New ADR (018+).
- **Phase 3b — RAG-enhanced NCCN retrieval + Classifier Agent** — approved 2026-06-04, implemented + eval-validated 2026-06-05. 5-agent pipeline (Classifier → Evidence → Context → Policy Mapper[Chroma RAG] → Reasoning). Chroma+LlamaIndex over a 12-criterion NSCLC corpus (reverses 2026-05-27 Chroma removal). Activates Determinism Contract invariants 11-12. Dev-tier baseline: completion 0.21→0.47 after bug fixes; governance invariants held (AI-decision-limit 1.00, adversarial-bypass 0.00). ADR-022. Ship-tier Opus run pending.

## Phase 3 Backlog

Items explicitly deferred beyond Phase 2 (Weeks 9-12) live in `docs/PHASE_3_BACKLOG.md`. Includes the 9 items named in scope doc §"Phase 3 (Future)" plus additions logged during Phase 2 (e.g., Chroma → pgvector migration, multi-physician concurrency, stronger judge model overlay).

---

## How to use this file

**Before writing any new code:**

1. Check if the work is on the Phase 2 timeline above
2. If yes → execute, label "in-scope"
3. If no → ask the user; if approved, log in `SCOPE_DELTAS.md` and label "scope-addition"
4. If it differs from the scope/PRD/Phase 2 plan deliberately → label "scope-deviation" and add to `SCOPE_DELTAS.md` with rationale

**When writing any new ADR:**

1. Check the ADR registry above
2. Use the next available number ≥ 017
3. Do NOT claim 015 or 016 unless writing the planned content
