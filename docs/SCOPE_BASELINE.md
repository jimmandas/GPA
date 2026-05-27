# GPA Scope Baseline

**Owner:** Jim
**Last updated:** 2026-05-27
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

### Phase 2 extensions (invariants 11-14)

11. Embedding model snapshot pinned (`config/rag_index.yaml`)
12. RAG index content-hashed
13. Corpus update requires index rebuild + full eval re-run
14. EHR stub schemas version-pinned

### Eval framework

- **8 dimensions** (4 per-case + 4 aggregate; scope §7)
- **9 named failure modes** (scope §8)
- **25-30 cases** (30% straightforward / 40% judgment-intensive / 30% adversarial)
- **LLM-as-judge: different vendor** (GPT-4o for now, pinned snapshot)
- **Cohen's κ ≥ 0.60** (Jim + Pax co-labels)

---

## Phase 2 Deliverable Status

Per `phase-2-agentic-rag-plan.md`:

| Phase 2 Week | Deliverable | Status |
|---|---|---|
| 9 | pgvector + LlamaIndex setup | ⚠ **deviation** — built on Chroma (see deltas) |
| 9 | Embedding model pinning + `RAGIndexValidator` | ✅ done (ADR-012, ADR-013) |
| 9 | `nccn_passage_lookup` RAG upgrade | ✅ done (ChromaRetriever) |
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

### Phase 2 new eval dimensions

| Dimension | Status |
|---|---|
| RAG Passage Relevance | ⏳ pending |
| Evidence Lineage Completeness | ❌ **REMOVED 2026-05-27** (no substrate after provider track cuts) |
| Physician Queue Routing Accuracy | ✅ done |
| Physician Rationale Compliance | ✅ done |

---

## ADR Registry

ADR-000 through ADR-014 are written. The Phase 2 plan reserves 015-016 for confidence calibration and max_turns budget. New ADRs from sessions outside the Phase 2 plan start at **017**.

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
| **015** | **Confidence threshold calibration** | **RESERVED (per Phase 2 plan)** |
| **016** | **max_turns budget increase** | **RESERVED (per Phase 2 plan)** |
| 017 | EVAL_TIER: dev/Sonnet vs ship/Opus | ✅ (this session — renumbered from 015) |

---

## Approved Scope Additions (beyond the original docs)

Tracked in `SCOPE_DELTAS.md`. Two active items:

- **Runtime confidence gate** — not in original scope; user approved adding 2026-05-27. Maps to planned ADR-015.
- **Bias monitoring** — not in original scope/strategy; user approved adding 2026-05-27. New ADR (018+).

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
