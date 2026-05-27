"""
rag/ — retrieval layer.

Provides the abstract PolicyRetriever interface and a FixtureRetriever
implementation. ADR-011 documents the interface contract.

Phase 2 status (2026-05-27): the RAG initiative (real parse / chunk /
embed pipeline) was cut and deferred to Phase 3 (PHASE_3_BACKLOG.md
item #10). The Chroma retriever + index validator that briefly lived
here were removed because they served a corpus that doesn't exist
(1 hand-authored YAML file). The interface stays because it's a useful
abstraction the active FixtureRetriever uses.

See:
- ADR-011: Retriever interface contract (Phase 3-deferral addendum at top)
- ADR-012, ADR-013: Phase 3-deferred (embedding pinning + corpus policy)
"""

from .retriever import PolicyRetriever, FixtureRetriever, RetrievedCorpus

__all__ = [
    "PolicyRetriever",
    "FixtureRetriever",
    "RetrievedCorpus",
]
