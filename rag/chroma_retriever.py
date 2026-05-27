"""
rag/chroma_retriever.py — ChromaRetriever implementation of PolicyRetriever.

Backs the same interface as FixtureRetriever, but reads from a persistent
Chroma collection that was built from the NCCN YAML fixtures. Today the
retrieval is metadata-filtered exact match on (indication_category, modality)
— semantically equivalent to fixture lookup, but using the embedded vector
store as substrate.

Future iterations can layer semantic ranking, fuzzy indication matching,
and cross-indication retrieval on top of this same retriever without
breaking the agent contract.

Embedding model: Chroma default (sentence-transformers/all-MiniLM-L6-v2).
Local, free, ~80MB on first download. No API key required.

To build the index from scratch:
    PYTHONPATH=. python rag/build_chroma_index.py

See ADR-011 (interface), ADR-012 (embedding pinning), ADR-013 (corpus policy).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from typing import Any

from .retriever import PolicyRetriever, RetrievedCorpus


# Where the Chroma persistent collection lives. Gitignored.
_DEFAULT_CHROMA_PATH = pathlib.Path(__file__).resolve().parents[1] / ".chroma"
_COLLECTION_NAME = "nccn_criteria"


class ChromaRetriever(PolicyRetriever):
    """
    Reads NCCN criteria from a persistent Chroma collection.

    Retrieval is currently metadata-filtered (exact match on indication
    category + modality). The vector embeddings are present but not used
    for ranking in v0 — that's a future iteration.
    """

    def __init__(
        self,
        chroma_path: pathlib.Path | None = None,
        collection_name: str = _COLLECTION_NAME,
    ):
        self.chroma_path = chroma_path or _DEFAULT_CHROMA_PATH
        self.collection_name = collection_name
        self.kind = "chroma"
        self._client = None
        self._collection = None

    def _ensure_collection(self):
        """Lazy-init: only import chromadb when actually used."""
        if self._collection is None:
            import chromadb
            from chromadb.config import Settings

            if not self.chroma_path.exists():
                raise FileNotFoundError(
                    f"Chroma collection not found at {self.chroma_path}. "
                    f"Run: PYTHONPATH=. python rag/build_chroma_index.py"
                )

            self._client = chromadb.PersistentClient(
                path=str(self.chroma_path),
                settings=Settings(anonymized_telemetry=False),
            )
            try:
                self._collection = self._client.get_collection(name=self.collection_name)
            except Exception as exc:
                raise FileNotFoundError(
                    f"Chroma collection '{self.collection_name}' missing at {self.chroma_path}. "
                    f"Run: PYTHONPATH=. python rag/build_chroma_index.py\n"
                    f"  underlying error: {exc}"
                ) from exc
        return self._collection

    def retrieve(self, indication_category: str, modality: str) -> RetrievedCorpus:
        collection = self._ensure_collection()

        # Metadata-filtered exact match. Returns ALL criteria matching the
        # (indication_category, modality) pair.
        # Chroma's `where` filter requires nested $and for multi-key matches.
        results = collection.get(
            where={
                "$and": [
                    {"indication_category": indication_category},
                    {"modality": modality},
                ]
            },
            include=["metadatas", "documents"],
        )

        ids = results.get("ids", []) or []
        metadatas = results.get("metadatas", []) or []
        documents = results.get("documents", []) or []

        if not ids:
            return RetrievedCorpus(
                indication_category=indication_category,
                modality=modality,
                criteria=[],
                overall_policy_reference=None,
                source_identifier=f"chroma://{self.collection_name}",
                content_hash="sha256:" + hashlib.sha256(b"").hexdigest(),
                retriever_kind=self.kind,
                extra={"error": f"No NCCN criteria for {indication_category}/{modality}"},
            )

        # Build the criteria list in passage_id order for deterministic output.
        rows = list(zip(ids, metadatas, documents))
        rows.sort(key=lambda row: row[1].get("passage_id", ""))

        criteria = []
        overall_policy_reference = None
        for _id, meta, doc in rows:
            criterion = {
                "passage_id": meta.get("passage_id"),
                "criterion_text": doc,
            }
            # Required evidence is stored as a JSON-encoded list in metadata
            # (Chroma metadata values must be primitives).
            req_ev_json = meta.get("required_evidence_json")
            if req_ev_json:
                try:
                    criterion["required_evidence"] = json.loads(req_ev_json)
                except json.JSONDecodeError:
                    criterion["required_evidence"] = []
            else:
                criterion["required_evidence"] = []
            criteria.append(criterion)
            if overall_policy_reference is None:
                overall_policy_reference = meta.get("overall_policy_reference")

        # Content hash over the canonical retrieved payload — deterministic
        # given same documents + metadatas.
        canonical = json.dumps(
            {"criteria": criteria, "overall_policy_reference": overall_policy_reference},
            sort_keys=True,
            separators=(",", ":"),
        )
        content_hash = "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        return RetrievedCorpus(
            indication_category=indication_category,
            modality=modality,
            criteria=criteria,
            overall_policy_reference=overall_policy_reference,
            source_identifier=f"chroma://{self.collection_name}",
            content_hash=content_hash,
            retriever_kind=self.kind,
            extra={"document_count": len(criteria)},
        )
