"""
rag/index_validator.py — enforces Determinism Contract invariants 11-13.

Phase 2 invariants (per scope §11 + phase-2-agentic-rag-plan.md):
  11. Embedding model snapshot pinned (config/rag_index.yaml, per mode)
  12. RAG index content-hashed (config/rag_index.yaml, per mode)
  13. Corpus update requires index rebuild + full eval re-run

config/rag_index.yaml is multi-mode (v0.2+): each retriever mode
(fixture, chroma, ...) has its own block. The validator reads the
RAG_RETRIEVER env var, picks the matching mode, and validates against
that mode's expected hash using the mode's declared hash_strategy:

  hash_strategy: "directory_files"
    SHA-256 over every file in corpus_path (sorted, content-delimited).
    Used by fixture mode — the corpus IS the files.

  hash_strategy: "canonical_documents"
    SHA-256 over the canonical document set produced by build_chroma_index.
    Used by chroma mode — the indexed corpus is derived from the YAML
    fixtures but stored as opaque sqlite blobs we can't hash directly.

Validation always fails fast and loud on drift; no eval run is allowed
to proceed with an unvalidated index.

See ADR-011 (architecture), ADR-012 (embedding pinning), ADR-013
(corpus update policy).
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
from dataclasses import dataclass
from typing import Any

import yaml


_DEFAULT_CONFIG_PATH = pathlib.Path(__file__).resolve().parents[1] / "config" / "rag_index.yaml"


class RAGIndexError(Exception):
    """Raised when the RAG index fails validation. Always fail-fast."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{reason}] {detail}")


@dataclass(frozen=True)
class RAGIndexConfig:
    """Snapshot of the expected RAG index state for ONE mode."""

    mode: str                       # e.g., "fixture", "chroma"
    version: str
    embedding_model: str
    retriever_kind: str
    corpus_hash: str
    corpus_path: str
    hash_strategy: str              # "directory_files" | "canonical_documents"
    extras: dict[str, Any]          # mode-specific extras (e.g., chroma_persist_path)
    notes: str = ""


# ---------------------------------------------------------------------------
# Config loading: multi-mode v0.2+ with backward compat for legacy v0.1
# ---------------------------------------------------------------------------

def _pick_active_mode(raw: dict, requested_mode: str | None) -> str:
    """
    Decide which mode block to validate.

    Precedence:
      1. requested_mode argument (caller override; e.g., from RAG_RETRIEVER env)
      2. raw["active_mode"] from the config
      3. fall back to "fixture"
    """
    if requested_mode:
        return requested_mode
    return raw.get("active_mode", "fixture")


def load_rag_index_config(
    config_path: pathlib.Path | None = None,
    requested_mode: str | None = None,
) -> RAGIndexConfig:
    """
    Load and minimally validate rag_index.yaml for the chosen mode.

    Args:
      config_path: defaults to repo config/rag_index.yaml
      requested_mode: overrides active_mode in the config; typically passed
                      from the RAG_RETRIEVER env var.

    Raises RAGIndexError on missing file / malformed structure / unknown mode.
    """
    config_path = config_path or _DEFAULT_CONFIG_PATH

    if not config_path.exists():
        raise RAGIndexError(
            "missing_config",
            f"RAG index config not found at {config_path}.",
        )

    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise RAGIndexError(
            "invalid_config",
            f"Config root must be a mapping, got {type(raw).__name__}",
        )

    version = str(raw.get("version", ""))
    modes = raw.get("modes")

    # Backward compatibility: legacy v0.1 had a single top-level mode.
    if not modes:
        legacy_required = {"retriever_kind", "embedding_model", "corpus_hash", "corpus_path"}
        missing = legacy_required - set(raw.keys())
        if missing:
            raise RAGIndexError(
                "incomplete_config",
                f"rag_index.yaml missing required keys: {sorted(missing)}",
            )
        return RAGIndexConfig(
            mode="(legacy-single-mode)",
            version=version or "0.1-legacy",
            embedding_model=str(raw["embedding_model"]),
            retriever_kind=str(raw["retriever_kind"]),
            corpus_hash=str(raw["corpus_hash"]),
            corpus_path=str(raw["corpus_path"]),
            hash_strategy=str(raw.get("hash_strategy", "directory_files")),
            extras={},
            notes=str(raw.get("notes", "")),
        )

    if not isinstance(modes, dict):
        raise RAGIndexError("invalid_config", f"'modes' must be a mapping, got {type(modes).__name__}")

    mode_name = _pick_active_mode(raw, requested_mode)
    if mode_name not in modes:
        raise RAGIndexError(
            "unknown_mode",
            f"Mode {mode_name!r} not defined in rag_index.yaml. "
            f"Available modes: {sorted(modes.keys())}.",
        )

    block = modes[mode_name]
    if not isinstance(block, dict):
        raise RAGIndexError("invalid_config", f"Mode block {mode_name!r} must be a mapping")

    required = {"retriever_kind", "embedding_model", "corpus_hash", "corpus_path"}
    missing = required - set(block.keys())
    if missing:
        raise RAGIndexError(
            "incomplete_config",
            f"Mode {mode_name!r} missing required keys: {sorted(missing)}",
        )

    # Anything not in the required set goes into extras (e.g., chroma_persist_path).
    extras = {k: v for k, v in block.items() if k not in required | {"hash_strategy", "notes"}}

    return RAGIndexConfig(
        mode=mode_name,
        version=version,
        embedding_model=str(block["embedding_model"]),
        retriever_kind=str(block["retriever_kind"]),
        corpus_hash=str(block["corpus_hash"]),
        corpus_path=str(block["corpus_path"]),
        hash_strategy=str(block.get("hash_strategy", "directory_files")),
        extras=extras,
        notes=str(block.get("notes", "")),
    )


# ---------------------------------------------------------------------------
# Hash strategies — one per supported retriever family
# ---------------------------------------------------------------------------

def compute_corpus_hash(corpus_dir: pathlib.Path) -> str:
    """
    hash_strategy="directory_files".

    SHA-256 over a deterministic concatenation of every file in corpus_dir
    (sorted alphabetically, content delimited by separator). Same input
    always produces same hash; any file content or filename change flips it.
    """
    if not corpus_dir.exists() or not corpus_dir.is_dir():
        raise RAGIndexError("corpus_missing", f"Corpus directory does not exist: {corpus_dir}")

    files = sorted(p for p in corpus_dir.rglob("*") if p.is_file())
    if not files:
        raise RAGIndexError("corpus_empty", f"Corpus directory contains no files: {corpus_dir}")

    hasher = hashlib.sha256()
    for f in files:
        rel = f.relative_to(corpus_dir).as_posix()
        hasher.update(b"--FILE--")
        hasher.update(rel.encode("utf-8"))
        hasher.update(b"\n")
        hasher.update(f.read_bytes())
    return "sha256:" + hasher.hexdigest()


def compute_canonical_document_hash(corpus_dir: pathlib.Path) -> str:
    """
    hash_strategy="canonical_documents".

    Compute the same canonical document hash that rag/build_chroma_index.py
    uses when populating Chroma. Reads every YAML fixture, splits to per-
    criterion documents with their metadata, sorts by id, and hashes the
    canonical JSON.

    Catches the case where someone edits a YAML and forgets to rebuild the
    Chroma index.
    """
    if not corpus_dir.exists() or not corpus_dir.is_dir():
        raise RAGIndexError("corpus_missing", f"Corpus directory does not exist: {corpus_dir}")

    fixtures = sorted(corpus_dir.glob("*.yaml"))
    if not fixtures:
        raise RAGIndexError("corpus_empty", f"No YAML fixtures in {corpus_dir}")

    all_docs: list[dict[str, Any]] = []
    for fixture in fixtures:
        data = yaml.safe_load(fixture.read_text(encoding="utf-8"))
        indication = data.get("indication_category", "")
        modality = data.get("modality", "")
        overall_ref = data.get("overall_policy_reference", "")
        for criterion in data.get("criteria", []) or []:
            passage_id = criterion.get("passage_id", "")
            criterion_text = (criterion.get("criterion_text", "") or "").strip()
            required_evidence = criterion.get("required_evidence", []) or []
            all_docs.append({
                "id": f"{indication}::{modality}::{passage_id}",
                "document": criterion_text,
                "metadata": {
                    "indication_category": indication,
                    "modality": modality,
                    "passage_id": passage_id,
                    "overall_policy_reference": overall_ref,
                    "required_evidence_json": json.dumps(required_evidence, ensure_ascii=False),
                    "source_fixture": fixture.name,
                },
            })

    canonical = json.dumps(
        sorted(all_docs, key=lambda r: r["id"]),
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


_HASH_STRATEGIES = {
    "directory_files": compute_corpus_hash,
    "canonical_documents": compute_canonical_document_hash,
}


# ---------------------------------------------------------------------------
# RAGIndexValidator
# ---------------------------------------------------------------------------

class RAGIndexValidator:
    """
    Validates that the live corpus matches the registered hash for the active mode.
    Designed to be called at the start of any eval run.

    Usage:
      validator = RAGIndexValidator(config_path, corpus_root)
      validator.validate()              # uses RAG_RETRIEVER env var (or active_mode)
      validator.validate(mode="chroma") # explicit override
    """

    def __init__(self, config_path: pathlib.Path | None = None, corpus_root: pathlib.Path | None = None):
        self.config_path = config_path or _DEFAULT_CONFIG_PATH
        self.corpus_root = corpus_root or _DEFAULT_CONFIG_PATH.parents[1]

    def validate(self, mode: str | None = None) -> RAGIndexConfig:
        """
        Returns the loaded config if validation passes.
        Raises RAGIndexError on any drift or misconfiguration.
        """
        # Resolve mode: explicit arg → RAG_RETRIEVER env → active_mode in config → "fixture"
        if mode is None:
            mode = os.environ.get("RAG_RETRIEVER")
        config = load_rag_index_config(self.config_path, requested_mode=mode)

        # Resolve corpus dir
        if pathlib.Path(config.corpus_path).is_absolute():
            corpus_dir = pathlib.Path(config.corpus_path)
        else:
            corpus_dir = self.corpus_root / config.corpus_path

        # Pick + run the hash strategy
        strategy = _HASH_STRATEGIES.get(config.hash_strategy)
        if strategy is None:
            raise RAGIndexError(
                "unknown_hash_strategy",
                f"hash_strategy {config.hash_strategy!r} for mode {config.mode!r} "
                f"is not implemented. Known: {sorted(_HASH_STRATEGIES.keys())}",
            )

        computed = strategy(corpus_dir)
        if computed != config.corpus_hash:
            raise RAGIndexError(
                "corpus_hash_drift",
                f"Corpus content has changed since the index was registered.\n"
                f"  Mode      : {config.mode}\n"
                f"  Strategy  : {config.hash_strategy}\n"
                f"  Registered: {config.corpus_hash}\n"
                f"  Computed  : {computed}\n"
                f"  Corpus dir: {corpus_dir}\n"
                "Per Invariant 13, a corpus change requires an index rebuild + "
                "full eval re-run. Update config/rag_index.yaml after rebuilding.",
            )

        return config
