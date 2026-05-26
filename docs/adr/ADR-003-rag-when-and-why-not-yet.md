# ADR-003: RAG Enters in Phase 2, Not MVP

**Status:** Accepted
**Date:** 2026-05-25
**Owner:** Jim
**Phase 2 plan:** `phase-2-agentic-rag-plan.md`

---

## Context

The Policy Mapper Agent needs access to NCCN guideline criteria. Two paths:

1. **RAG** — embed the full NCCN corpus into a vector store (pgvector + LlamaIndex); retrieve top-k relevant passages at runtime.
2. **Fixture lookup** — store a curated set of NCCN passages as checked-in YAML files; the `nccn_passage_lookup` tool reads from these.

RAG is closer to the production pattern. Fixture lookup is simpler, deterministic, and content-hashable. Choosing between them affects determinism, reproducibility, and the eval baseline.

---

## Decision

**MVP uses fixture lookup. Phase 2 upgrades to RAG.**

`policy/nccn_fixtures/*.yaml` contains hand-curated NCCN criteria for the indication categories the MVP covers (currently `post_treatment_surveillance` × `CT`). The `nccn_passage_lookup(indication_category, modality)` tool reads from these files. Tool registry hashes the fixture content; any change forces a hash update and full eval re-run.

---

## Why MVP Defers RAG

The MVP's primary thesis is *the governance plumbing works for judgment-intensive AI assistance*. Proving that thesis requires:

- **Determinism:** Reproducibility eval dimension requires byte-identical outputs across 5 runs. Fixture lookup is deterministic by construction. RAG introduces a retrieval layer whose outputs depend on embedding model behavior and corpus state — a second surface that would need its own Determinism Contract extension.
- **Audit-grade traceability:** Every reasoning brief claim must cite a verifiable evidence field. Fixture YAML files have stable `passage_id` values that survive across runs. RAG retrievals' provenance is more complex to anchor (top-k indices, similarity scores, etc.).
- **Isolation of failure modes:** If RAG and governance were built simultaneously, a failure could be attributed to either layer. Building them sequentially means each can be debugged in isolation.

RAG is the right move for production — but only on top of a validated governance baseline.

---

## Phase 2 RAG Plan (Summary)

`phase-2-agentic-rag-plan.md` details the upgrade:

- **Index:** pgvector + LlamaIndex over full NCCN corpus
- **Embedding model:** pinned snapshot in `config/rag_index.yaml`
- **Index content-hash:** SHA-256 of indexed corpus in `config/rag_index.yaml`
- **Determinism Contract extensions:** invariants 11–14 add embedding model pinning, index content hashing, corpus update requires full eval re-run, EHR stub schema version pinning
- **`RAGIndexValidator`:** build-time check that runs before every eval — fails fast if computed corpus hash ≠ registered hash

This means the RAG layer inherits a governance model that has already been validated.

---

## Consequences

1. **MVP eval dimension `decision_reproducibility` is testable in isolation.** Fixture lookup is byte-stable; any reproducibility variance is attributable to the agents, not the policy retrieval layer.
2. **Coverage limit, documented:** The MVP only handles indication categories whose NCCN passages have been authored as YAML fixtures. Phase 2 unlocks the full corpus.
3. **No silent corpus drift.** Tool registry's content-hash check means a fixture edit without a hash update fails CI.
4. **`nccn_passage_lookup` interface is preserved.** Phase 2 changes only the implementation; agents don't need to change.

---

## Alternatives Considered

| Option | Reason Not Chosen for MVP |
|---|---|
| RAG from day one | Would require building governance + retrieval simultaneously; failure attribution becomes ambiguous. |
| Direct LLM-based "what does NCCN say" lookup (no retrieval) | Untraceable, can't be content-hashed, would fail Source Verification Gate. |
| Embedded NCCN as a JSON blob in the system prompt | Doesn't scale beyond ~1 indication; pollutes the context window. |

---

## Related ADRs

- ADR-002 — Claude Agent SDK + ToolSearch behavior
- ADR-004 — Tool mocking strategy (the broader pattern fixture lookup fits into)
- ADR-009 — Eval methodology (reproducibility dimension that fixture lookup enables)
