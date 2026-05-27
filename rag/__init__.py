"""
rag/ — Phase 2 retrieval layer.

Provides the abstract PolicyRetriever interface and a FixtureRetriever
implementation that wraps the MVP fixture-lookup behavior. Future
implementations (PgvectorRetriever, ChromaRetriever, etc.) will swap into
the same interface without changing the agent code.

See:
- ADR-011: RAG architecture choice + retriever interface contract
- ADR-012: Embedding model pinning strategy
- ADR-013: Corpus update policy
- phase-2-agentic-rag-plan.md (private scope doc) for the broader plan
"""

from .retriever import PolicyRetriever, FixtureRetriever, RetrievedCorpus
from .index_validator import RAGIndexValidator, RAGIndexError

__all__ = [
    "PolicyRetriever",
    "FixtureRetriever",
    "RetrievedCorpus",
    "RAGIndexValidator",
    "RAGIndexError",
]
