"""
rag/retriever.py — abstract PolicyRetriever interface + FixtureRetriever.

The abstract interface lets the policy_mapper agent stay implementation-
agnostic. MVP code uses FixtureRetriever (file-system lookup of NCCN YAML
fixtures). Phase 2 will add PgvectorRetriever (or ChromaRetriever, etc.)
that returns the same shape from an actual vector store.

The retrieval contract is intentionally narrow:
  retrieve(indication_category, modality) -> RetrievedCorpus

Returns a typed object containing:
- the criterion list (preserved from the YAML structure)
- the source identifier (which fixture/index/corpus it came from)
- a provenance hash so the audit log can record exactly what was used

See ADR-011 for the rationale.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import yaml


@dataclass
class RetrievedCorpus:
    """
    Shape of what every PolicyRetriever returns.

    Keep this stable across implementations — the policy_mapper agent
    code reads from these fields by name.
    """

    indication_category: str
    modality: str
    criteria: list[dict[str, Any]]              # passage_id, criterion_text, required_evidence
    overall_policy_reference: str | None = None
    source_identifier: str = ""                  # fixture path, index name, etc.
    content_hash: str = ""                       # SHA-256 of the canonical content
    retriever_kind: str = ""                     # "fixture" | "pgvector" | etc.
    extra: dict[str, Any] = field(default_factory=dict)

    def to_payload_dict(self) -> dict[str, Any]:
        """Serializable shape suitable for inclusion in an LLM prompt."""
        return {
            "indication_category": self.indication_category,
            "modality": self.modality,
            "criteria": self.criteria,
            "overall_policy_reference": self.overall_policy_reference,
        }


class PolicyRetriever(ABC):
    """Abstract retriever contract. All retrievers must implement retrieve()."""

    @abstractmethod
    def retrieve(self, indication_category: str, modality: str) -> RetrievedCorpus:
        """
        Look up NCCN-style criteria for the given indication/modality.

        Must always return a RetrievedCorpus. If nothing is found, the
        criteria list is empty and source_identifier explains why.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# FixtureRetriever — MVP implementation, wraps the YAML files
# ---------------------------------------------------------------------------

class FixtureRetriever(PolicyRetriever):
    """
    File-system-backed retriever. Reads from the same NCCN YAML fixtures the
    MVP has used since Day 1. Computes the corpus content hash on every read
    so the audit log captures fixture provenance per call.

    This is the bridge implementation. Phase 2's real retriever will be a
    drop-in replacement.
    """

    def __init__(self, fixtures_dir: pathlib.Path):
        self.fixtures_dir = fixtures_dir
        self.kind = "fixture"

    def retrieve(self, indication_category: str, modality: str) -> RetrievedCorpus:
        fixture_key = f"{indication_category}_{modality}"
        fixture_path = self.fixtures_dir / f"{fixture_key}.yaml"

        if not fixture_path.exists():
            return RetrievedCorpus(
                indication_category=indication_category,
                modality=modality,
                criteria=[],
                overall_policy_reference=None,
                source_identifier=str(fixture_path),
                content_hash="sha256:" + hashlib.sha256(b"").hexdigest(),
                retriever_kind=self.kind,
                extra={"error": f"No NCCN fixture for {indication_category}/{modality}"},
            )

        raw_bytes = fixture_path.read_bytes()
        content_hash = "sha256:" + hashlib.sha256(raw_bytes).hexdigest()
        data = yaml.safe_load(raw_bytes)

        return RetrievedCorpus(
            indication_category=data.get("indication_category", indication_category),
            modality=data.get("modality", modality),
            criteria=data.get("criteria", []),
            overall_policy_reference=data.get("overall_policy_reference"),
            source_identifier=str(fixture_path),
            content_hash=content_hash,
            retriever_kind=self.kind,
        )

    def retrieve_as_json(self, indication_category: str, modality: str) -> str:
        """
        Compatibility helper for code paths that still expect the old
        nccn_passage_lookup string return. Returns the same JSON shape.
        """
        corpus = self.retrieve(indication_category, modality)
        if corpus.extra.get("error"):
            return json.dumps({"error": corpus.extra["error"]})
        return json.dumps(corpus.to_payload_dict(), ensure_ascii=False)
