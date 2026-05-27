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
