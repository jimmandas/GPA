# ADR-011: RAG Architecture and Retriever Interface

**Status:** Accepted (Phase 2 scaffold)
**Date:** 2026-05-27
**Owner:** Jim
**Phase 2 plan:** `phase-2-agentic-rag-plan.md`

---

## Context

Phase 1 used `nccn_passage_lookup` — a direct YAML-file lookup tool — to feed NCCN criteria to the Policy Mapper. ADR-003 explained why: the MVP's primary thesis was governance plumbing, and fixture lookup gave us deterministic, content-hashable, byte-stable retrieval for the reproducibility eval to score against.

Phase 2 needs real retrieval: a vector store over the full NCCN corpus, embedding-based ranking, top-k passage selection with metadata (guideline version, section ID, effective date). The two new failure modes that real retrieval introduces (retrieval relevance, retrieval drift) need to be measurable, auditable, and controllable.

The question for Phase 2 Week 9: **what's the shape of the change, and what's the bridge from MVP to RAG?**

---

## Decision

**Introduce a `PolicyRetriever` abstract interface. MVP gets a `FixtureRetriever` that wraps the existing YAML lookup. Phase 2 will add `PgvectorRetriever` (or `ChromaRetriever` / `LanceDBRetriever` — picked at integration time) that fills the same interface.**

The interface lives in `rag/retriever.py`:

```python
class PolicyRetriever(ABC):
    @abstractmethod
    def retrieve(self, indication_category: str, modality: str) -> RetrievedCorpus:
        ...

@dataclass
class RetrievedCorpus:
    indication_category: str
    modality: str
    criteria: list[dict]
    overall_policy_reference: str | None
    source_identifier: str        # fixture path / index name
    content_hash: str             # sha256 of the canonical content
    retriever_kind: str           # "fixture" | "pgvector" | ...
    extra: dict = field(default_factory=dict)
```

The Policy Mapper agent (`agents/policy_mapper/agent.py`) calls `_get_retriever().retrieve(...)` instead of `nccn_passage_lookup(...)` directly. Today that returns a `FixtureRetriever`. When Phase 2 wires in the real vector store, `set_retriever(PgvectorRetriever(...))` flips the entire pipeline over with no other code change.

---

## Why an Abstract Interface (Not Just "Replace nccn_passage_lookup")

Three concrete reasons:

1. **The eval framework can test both implementations against the same cases.** A "fixture vs RAG" comparison eval is a one-line config swap, not a code branch. This is the substrate for the new Phase 2 dimensions (RAG Passage Relevance, Evidence Lineage Completeness).
2. **The agent code stays stable across the swap.** No prompt change, no schema change, no audit-log change — just a different value at the seam. Governance defensibility improves: the v1 → v2 → v3 audit trail extends cleanly to v4-with-RAG without re-baselining everything.
3. **The `content_hash` field on `RetrievedCorpus` formalizes corpus provenance.** Every Policy Mapper agent_event already records `tool_calls_made` with a `fixture_hash`; the new field generalizes that to `corpus_content_hash` and `retriever_kind`. Per-call provenance is preserved across retriever implementations.

---

## Why Defer the Pgvector Decision

Three vector store options are viable: pgvector (PostgreSQL-backed), Chroma (embedded), LanceDB (embedded). Each has different tradeoffs:

| Store | Pro | Con |
|---|---|---|
| pgvector | Production-conventional; SQL ops; AWS RDS / Supabase ready | Requires PostgreSQL + extension |
| Chroma | Embedded, zero infrastructure, easy demo | Less "real production" feel |
| LanceDB | Embedded, very fast, modern API | Smaller community |

The Phase 2 Week 9 scaffold doesn't commit to one. The `PolicyRetriever` interface accommodates all three (and any future option). The decision gets made when actually wiring real retrieval — at which point we have measured demands (corpus size, query patterns, latency budget) that the abstract choice today doesn't.

---

## What's In the Scaffold

- **`rag/retriever.py`** — `PolicyRetriever` ABC, `FixtureRetriever` working implementation, `RetrievedCorpus` dataclass.
- **`rag/index_validator.py`** — `RAGIndexValidator` enforces Invariants 11-13 (see ADR-012, ADR-013).
- **`config/rag_index.yaml`** — v0.1-fixture-mode, populated with current state.
- **`agents/policy_mapper/agent.py`** — refactored to call the retriever via the interface; behavior unchanged.
- **`tests/rag/`** — 23 unit tests covering retriever interface, hash stability, drift detection, error paths.

## What's NOT In the Scaffold

- No real pgvector / Chroma / LanceDB implementation. That's Week 9-10 integration work once the substrate is chosen.
- No new eval dimensions yet (RAG Passage Relevance, Evidence Lineage Completeness). Those land after a real retriever exists to measure.
- No embedding model selected. ADR-012 documents the pinning protocol, not the choice.
- No agent prompt changes. Same prompt, same schema.

---

## Consequences

1. **Phase 2 Week 9 has a working scaffold today** that anyone can extend by implementing `PolicyRetriever`. 165 tests still pass; unit-mode eval still runs.
2. **The substrate for Phase 2 eval dims is in place.** When RAG Passage Relevance lands, it scores `RetrievedCorpus.criteria` against ground-truth relevance labels — same shape regardless of retriever.
3. **A reviewer can diff the audit log to see which retriever was used.** The new `retriever_kind` + `corpus_content_hash` fields on `tool_calls_made` provide explicit provenance per call.
4. **The MVP eval is unchanged in behavior.** `FixtureRetriever` wraps the existing fixture lookup exactly; no eval scores should move.
5. **Future migration cost is constrained.** Any one of the real-vector-store options can land in <500 lines of code touching only `rag/` — no agent code, no prompt, no schema migration.

---

## Alternatives Considered

| Option | Reason Not Chosen |
|---|---|
| Direct `nccn_passage_lookup` rewrite (no interface) | Couples the agent to one retrieval implementation. Phase 2 swap becomes invasive. |
| LangChain VectorStore abstraction | Heavy dependency for a single contract we can express in ~50 lines. |
| Don't scaffold — go straight to pgvector | Premature; we haven't measured query patterns yet, and Phase 2 Week 9 is the right place for the substrate, not the implementation. |
| Single concrete retriever, swap via subclassing later | Same as the first option. Inheritance is a worse coupling than composition through an interface. |

---

## Related ADRs

- ADR-003 — Why MVP used fixture lookup (the lookup ADR-011 is replacing)
- ADR-004 — Tool mocking strategy (the broader pattern this fits into)
- ADR-009 — Eval methodology (the framework that will get 4 new Phase 2 dimensions)
- ADR-012 — Embedding model pinning strategy
- ADR-013 — Corpus update policy
