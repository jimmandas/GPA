"""
Tests for rag/index_validator.py — RAGIndexValidator + compute_corpus_hash.

Enforces Determinism Contract invariants 11-13.
"""

import pathlib
import tempfile

import pytest
import yaml

from rag.index_validator import (
    RAGIndexValidator,
    RAGIndexError,
    RAGIndexConfig,
    compute_corpus_hash,
    load_rag_index_config,
)


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_REAL_CONFIG = _REPO_ROOT / "config" / "rag_index.yaml"
_REAL_CORPUS = _REPO_ROOT / "policy" / "nccn_fixtures"


# ---------------------------------------------------------------------------
# compute_corpus_hash
# ---------------------------------------------------------------------------

class TestComputeCorpusHash:
    def test_returns_sha256_prefixed_hash(self):
        h = compute_corpus_hash(_REAL_CORPUS)
        assert h.startswith("sha256:")
        assert len(h) == len("sha256:") + 64

    def test_hash_is_stable_across_calls(self):
        assert compute_corpus_hash(_REAL_CORPUS) == compute_corpus_hash(_REAL_CORPUS)

    def test_hash_changes_when_content_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "a.yaml").write_text("foo: 1\n", encoding="utf-8")
            h1 = compute_corpus_hash(d)
            (d / "a.yaml").write_text("foo: 2\n", encoding="utf-8")
            h2 = compute_corpus_hash(d)
            assert h1 != h2

    def test_hash_changes_when_filename_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = pathlib.Path(tmp)
            (d / "a.yaml").write_text("foo: 1\n", encoding="utf-8")
            h1 = compute_corpus_hash(d)
            (d / "a.yaml").rename(d / "b.yaml")
            h2 = compute_corpus_hash(d)
            assert h1 != h2

    def test_raises_for_missing_dir(self):
        with pytest.raises(RAGIndexError, match="corpus_missing"):
            compute_corpus_hash(pathlib.Path("/does/not/exist/anywhere"))

    def test_raises_for_empty_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            with pytest.raises(RAGIndexError, match="corpus_empty"):
                compute_corpus_hash(pathlib.Path(tmp))


# ---------------------------------------------------------------------------
# load_rag_index_config
# ---------------------------------------------------------------------------

class TestLoadRagIndexConfig:
    def test_loads_real_config(self):
        config = load_rag_index_config(_REAL_CONFIG)
        assert isinstance(config, RAGIndexConfig)
        assert config.version
        assert config.retriever_kind == "fixture"
        assert config.embedding_model == "none-fixture-mode"
        assert config.corpus_hash.startswith("sha256:")
        assert config.corpus_path == "policy/nccn_fixtures"

    def test_raises_for_missing_file(self):
        with pytest.raises(RAGIndexError, match="missing_config"):
            load_rag_index_config(pathlib.Path("/does/not/exist.yaml"))

    def test_raises_for_incomplete_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "bad.yaml"
            bad.write_text(yaml.safe_dump({"version": "0.1"}), encoding="utf-8")
            with pytest.raises(RAGIndexError, match="incomplete_config"):
                load_rag_index_config(bad)


# ---------------------------------------------------------------------------
# RAGIndexValidator
# ---------------------------------------------------------------------------

class TestRAGIndexValidatorHappyPath:
    def test_validate_passes_for_real_config(self):
        v = RAGIndexValidator(_REAL_CONFIG, _REPO_ROOT)
        config = v.validate()
        assert config.corpus_hash.startswith("sha256:")


class TestRAGIndexValidatorDriftDetection:
    """The Invariant 13 enforcement: corpus drift must fail loudly."""

    def test_detects_drift_when_corpus_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            corpus = tmp_path / "corpus"
            corpus.mkdir()
            (corpus / "a.yaml").write_text("foo: 1\n", encoding="utf-8")

            registered_hash = compute_corpus_hash(corpus)

            config_file = tmp_path / "rag_index.yaml"
            config_file.write_text(yaml.safe_dump({
                "version": "0.1-test",
                "retriever_kind": "fixture",
                "embedding_model": "none-fixture-mode",
                "corpus_hash": registered_hash,
                "corpus_path": "corpus",
            }), encoding="utf-8")

            v = RAGIndexValidator(config_file, tmp_path)
            v.validate()   # initial validation passes

            # Mutate the corpus
            (corpus / "a.yaml").write_text("foo: 2\n", encoding="utf-8")

            with pytest.raises(RAGIndexError, match="corpus_hash_drift"):
                v.validate()


class TestRAGIndexValidatorMissingPieces:
    def test_raises_when_config_path_missing(self):
        v = RAGIndexValidator(pathlib.Path("/does/not/exist.yaml"), _REPO_ROOT)
        with pytest.raises(RAGIndexError, match="missing_config"):
            v.validate()

    def test_raises_when_corpus_path_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            config_file = tmp_path / "rag_index.yaml"
            config_file.write_text(yaml.safe_dump({
                "version": "0.1-test",
                "retriever_kind": "fixture",
                "embedding_model": "none-fixture-mode",
                "corpus_hash": "sha256:abc",
                "corpus_path": "nonexistent",
            }), encoding="utf-8")
            v = RAGIndexValidator(config_file, tmp_path)
            with pytest.raises(RAGIndexError, match="corpus_missing"):
                v.validate()


# ---------------------------------------------------------------------------
# Multi-mode v0.2 behavior
# ---------------------------------------------------------------------------

class TestMultiModeConfig:
    def test_loads_fixture_mode_from_real_config(self):
        config = load_rag_index_config(_REAL_CONFIG, requested_mode="fixture")
        assert config.mode == "fixture"
        assert config.retriever_kind == "fixture"
        assert config.hash_strategy == "directory_files"

    def test_loads_chroma_mode_from_real_config(self):
        config = load_rag_index_config(_REAL_CONFIG, requested_mode="chroma")
        assert config.mode == "chroma"
        assert config.retriever_kind == "chroma"
        assert config.hash_strategy == "canonical_documents"
        assert "chroma_persist_path" in config.extras
        assert config.extras["chroma_persist_path"] == ".chroma"

    def test_active_mode_default_used_when_no_request(self):
        # active_mode in the real config is "fixture"
        config = load_rag_index_config(_REAL_CONFIG)
        assert config.mode == "fixture"

    def test_unknown_mode_raises(self):
        with pytest.raises(RAGIndexError, match="unknown_mode"):
            load_rag_index_config(_REAL_CONFIG, requested_mode="not_a_real_mode")


class TestEnvVarDispatch:
    def test_env_var_picks_mode(self, monkeypatch):
        monkeypatch.setenv("RAG_RETRIEVER", "chroma")
        v = RAGIndexValidator(_REAL_CONFIG, _REPO_ROOT)
        config = v.validate()
        assert config.mode == "chroma"
        assert config.retriever_kind == "chroma"

    def test_no_env_var_falls_back_to_active_mode(self, monkeypatch):
        monkeypatch.delenv("RAG_RETRIEVER", raising=False)
        v = RAGIndexValidator(_REAL_CONFIG, _REPO_ROOT)
        config = v.validate()
        # real config's active_mode is "fixture"
        assert config.mode == "fixture"


class TestChromaCanonicalDocumentValidation:
    """
    Chroma mode validates against the canonical document hash, NOT the
    fixture file bytes. This means a comment-only edit to a YAML still
    triggers drift (because canonical_documents normalizes whitespace
    differently than directory_files does).
    """

    def test_chroma_mode_validates_against_real_config(self):
        v = RAGIndexValidator(_REAL_CONFIG, _REPO_ROOT)
        config = v.validate(mode="chroma")
        assert config.mode == "chroma"
        # If this passes, the canonical document hash in the config matches
        # what compute_canonical_document_hash produces from the YAML files.

    def test_chroma_mode_detects_yaml_drift(self, tmp_path):
        """If someone edits an NCCN YAML, chroma's canonical hash should flip."""
        # Stage a tiny fake corpus + config
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "test_indication_TEST.yaml").write_text(
            yaml.safe_dump({
                "indication_category": "test_indication",
                "modality": "TEST",
                "criteria": [
                    {"passage_id": "T-1", "criterion_text": "criterion v1"}
                ],
            }),
            encoding="utf-8",
        )

        # Compute the canonical document hash for the corpus
        from rag.index_validator import compute_canonical_document_hash
        canonical = compute_canonical_document_hash(corpus)

        config_file = tmp_path / "rag_index.yaml"
        config_file.write_text(yaml.safe_dump({
            "version": "0.2-test",
            "active_mode": "chroma",
            "modes": {
                "chroma": {
                    "retriever_kind": "chroma",
                    "embedding_model": "test-model",
                    "corpus_hash": canonical,
                    "corpus_path": "corpus",
                    "hash_strategy": "canonical_documents",
                },
            },
        }), encoding="utf-8")

        v = RAGIndexValidator(config_file, tmp_path)
        v.validate(mode="chroma")  # passes initially

        # Mutate the YAML
        (corpus / "test_indication_TEST.yaml").write_text(
            yaml.safe_dump({
                "indication_category": "test_indication",
                "modality": "TEST",
                "criteria": [
                    {"passage_id": "T-1", "criterion_text": "criterion v2 EDITED"}
                ],
            }),
            encoding="utf-8",
        )

        with pytest.raises(RAGIndexError, match="corpus_hash_drift"):
            v.validate(mode="chroma")


class TestUnknownHashStrategy:
    def test_raises_for_unimplemented_strategy(self, tmp_path):
        corpus = tmp_path / "corpus"
        corpus.mkdir()
        (corpus / "x.yaml").write_text("foo: 1\n", encoding="utf-8")

        config_file = tmp_path / "rag_index.yaml"
        config_file.write_text(yaml.safe_dump({
            "version": "0.2-test",
            "active_mode": "weird",
            "modes": {
                "weird": {
                    "retriever_kind": "weird",
                    "embedding_model": "none",
                    "corpus_hash": "sha256:abc",
                    "corpus_path": "corpus",
                    "hash_strategy": "merkle_tree_holographic",  # nonsense
                },
            },
        }), encoding="utf-8")

        v = RAGIndexValidator(config_file, tmp_path)
        with pytest.raises(RAGIndexError, match="unknown_hash_strategy"):
            v.validate()
