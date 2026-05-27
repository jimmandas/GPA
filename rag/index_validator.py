"""
rag/index_validator.py — enforces Determinism Contract invariants 11-13.

Phase 2 invariants (per scope §11 + phase-2-agentic-rag-plan.md):
  11. Embedding model snapshot pinned (config/rag_index.yaml)
  12. RAG index content-hashed (config/rag_index.yaml)
  13. Corpus update requires index rebuild + full eval re-run

This validator runs at the start of any live eval (in v1, the policy_mapper
already does fixture-level hash verification; this validator extends the
same pattern to the whole RAG corpus). Fails fast and loud if drift is
detected — no eval run is allowed to proceed with an unvalidated index.

In the MVP/Phase 2-scaffold state, the "corpus" is the NCCN YAML fixtures
directory. When pgvector/Chroma is wired in, the corpus shape changes but
the validator's contract stays the same.

See ADR-011 (RAG architecture), ADR-012 (embedding pinning), ADR-013
(corpus update policy).
"""

from __future__ import annotations

import hashlib
import pathlib
from dataclasses import dataclass

import yaml


class RAGIndexError(Exception):
    """Raised when the RAG index fails validation. Always fail-fast."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{reason}] {detail}")


@dataclass(frozen=True)
class RAGIndexConfig:
    """Snapshot of the expected RAG index state, loaded from rag_index.yaml."""

    version: str
    embedding_model: str
    retriever_kind: str
    corpus_hash: str
    corpus_path: str
    notes: str = ""


def load_rag_index_config(config_path: pathlib.Path) -> RAGIndexConfig:
    """Load and minimally validate rag_index.yaml. Raises RAGIndexError on issues."""
    if not config_path.exists():
        raise RAGIndexError(
            "missing_config",
            f"RAG index config not found at {config_path}. "
            "Phase 2 requires config/rag_index.yaml to be populated.",
        )

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RAGIndexError("invalid_config", f"Config root must be a mapping, got {type(raw).__name__}")

    required = {"version", "embedding_model", "retriever_kind", "corpus_hash", "corpus_path"}
    missing = required - set(raw.keys())
    if missing:
        raise RAGIndexError(
            "incomplete_config",
            f"rag_index.yaml missing required keys: {sorted(missing)}",
        )

    return RAGIndexConfig(
        version=str(raw["version"]),
        embedding_model=str(raw["embedding_model"]),
        retriever_kind=str(raw["retriever_kind"]),
        corpus_hash=str(raw["corpus_hash"]),
        corpus_path=str(raw["corpus_path"]),
        notes=str(raw.get("notes", "")),
    )


def compute_corpus_hash(corpus_dir: pathlib.Path) -> str:
    """
    SHA-256 over a deterministic concatenation of every file in corpus_dir
    (sorted alphabetically, content delimited by separator). Same input
    always produces same hash; any file content or filename change flips it.
    """
    if not corpus_dir.exists() or not corpus_dir.is_dir():
        raise RAGIndexError(
            "corpus_missing",
            f"Corpus directory does not exist: {corpus_dir}",
        )

    files = sorted(p for p in corpus_dir.rglob("*") if p.is_file())
    if not files:
        raise RAGIndexError(
            "corpus_empty",
            f"Corpus directory contains no files: {corpus_dir}",
        )

    hasher = hashlib.sha256()
    for f in files:
        rel = f.relative_to(corpus_dir).as_posix()
        hasher.update(b"--FILE--")
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\n")
        hasher.update(f.read_bytes())
    return "sha256:" + hasher.hexdigest()


class RAGIndexValidator:
    """
    Validates that the live corpus matches the registered hash in rag_index.yaml.
    Designed to be called at the start of any eval run.

    Usage:
      validator = RAGIndexValidator(config_path, corpus_root)
      validator.validate()   # raises RAGIndexError on drift; returns None on pass
    """

    def __init__(self, config_path: pathlib.Path, corpus_root: pathlib.Path):
        self.config_path = config_path
        self.corpus_root = corpus_root

    def validate(self) -> RAGIndexConfig:
        """
        Returns the loaded config if validation passes.
        Raises RAGIndexError on any drift or misconfiguration.
        """
        config = load_rag_index_config(self.config_path)

        # Allow config.corpus_path to be relative to repo root or absolute.
        if pathlib.Path(config.corpus_path).is_absolute():
            corpus_dir = pathlib.Path(config.corpus_path)
        else:
            corpus_dir = self.corpus_root / config.corpus_path

        computed = compute_corpus_hash(corpus_dir)
        if computed != config.corpus_hash:
            raise RAGIndexError(
                "corpus_hash_drift",
                f"Corpus content has changed since the index was registered.\n"
                f"  Registered: {config.corpus_hash}\n"
                f"  Computed  : {computed}\n"
                f"  Corpus dir: {corpus_dir}\n"
                "Per Invariant 13, a corpus change requires an index rebuild + "
                "full eval re-run. Update config/rag_index.yaml after rebuilding.",
            )

        return config
