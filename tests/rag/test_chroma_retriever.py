"""
Tests for rag/chroma_retriever.py — ChromaRetriever implementation.

These tests require the .chroma index to be built. They auto-skip if the
index isn't present, so they don't break unit-mode CI on a fresh clone.
"""

import pathlib

import pytest

from rag.retriever import FixtureRetriever, PolicyRetriever, RetrievedCorpus


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CHROMA_PATH = _REPO_ROOT / ".chroma"
_FIXTURES_DIR = _REPO_ROOT / "policy" / "nccn_fixtures"


# Skip the entire module if the local Chroma index isn't built.
pytestmark = pytest.mark.skipif(
    not _CHROMA_PATH.exists(),
    reason=".chroma index not built; run: PYTHONPATH=. python rag/build_chroma_index.py",
)


# Import here so the skipif fires before the import (chromadb is heavy)
from rag.chroma_retriever import ChromaRetriever  # noqa: E402


class TestChromaRetrieverImplementsInterface:
    def test_chroma_retriever_is_a_policy_retriever(self):
        r = ChromaRetriever()
        assert isinstance(r, PolicyRetriever)

    def test_chroma_retriever_kind_label(self):
        r = ChromaRetriever()
        corpus = r.retrieve("post_treatment_surveillance", "CT")
        assert corpus.retriever_kind == "chroma"
        assert corpus.source_identifier.startswith("chroma://")


class TestChromaRetrieverHappyPath:
    def test_returns_criteria_for_known_indication(self):
        r = ChromaRetriever()
        corpus = r.retrieve("post_treatment_surveillance", "CT")
        assert isinstance(corpus, RetrievedCorpus)
        assert len(corpus.criteria) >= 1
        for criterion in corpus.criteria:
            assert "passage_id" in criterion
            assert "criterion_text" in criterion
            assert "required_evidence" in criterion

    def test_criteria_are_passage_id_ordered(self):
        r = ChromaRetriever()
        corpus = r.retrieve("post_treatment_surveillance", "CT")
        passage_ids = [c["passage_id"] for c in corpus.criteria]
        assert passage_ids == sorted(passage_ids)

    def test_content_hash_is_stable_across_reads(self):
        r = ChromaRetriever()
        c1 = r.retrieve("post_treatment_surveillance", "CT")
        c2 = r.retrieve("post_treatment_surveillance", "CT")
        assert c1.content_hash == c2.content_hash


class TestChromaRetrieverMissingData:
    def test_returns_empty_corpus_for_unknown_indication(self):
        r = ChromaRetriever()
        corpus = r.retrieve("not_a_real_indication", "MRI")
        assert isinstance(corpus, RetrievedCorpus)
        assert corpus.criteria == []
        assert "error" in corpus.extra


class TestChromaVsFixtureEquivalence:
    """Both retrievers must return semantically equivalent criteria on the same input."""

    def test_same_passage_ids_in_same_order(self):
        fixture_r = FixtureRetriever(_FIXTURES_DIR)
        chroma_r = ChromaRetriever()

        f = fixture_r.retrieve("post_treatment_surveillance", "CT")
        c = chroma_r.retrieve("post_treatment_surveillance", "CT")

        assert [x["passage_id"] for x in f.criteria] == [
            x["passage_id"] for x in c.criteria
        ]

    def test_same_criterion_text(self):
        fixture_r = FixtureRetriever(_FIXTURES_DIR)
        chroma_r = ChromaRetriever()

        f = fixture_r.retrieve("post_treatment_surveillance", "CT")
        c = chroma_r.retrieve("post_treatment_surveillance", "CT")

        for fx, cx in zip(f.criteria, c.criteria):
            assert fx["criterion_text"].strip() == cx["criterion_text"].strip()

    def test_same_required_evidence(self):
        fixture_r = FixtureRetriever(_FIXTURES_DIR)
        chroma_r = ChromaRetriever()

        f = fixture_r.retrieve("post_treatment_surveillance", "CT")
        c = chroma_r.retrieve("post_treatment_surveillance", "CT")

        for fx, cx in zip(f.criteria, c.criteria):
            assert fx.get("required_evidence", []) == cx.get("required_evidence", [])


class TestChromaRetrieverMissingIndex:
    """If .chroma is missing, the retriever raises a clear error pointing at the build script."""

    def test_raises_clear_error_for_missing_collection(self, tmp_path):
        # Point at an empty directory — not a real Chroma collection
        empty_dir = tmp_path / "empty_chroma"
        r = ChromaRetriever(chroma_path=empty_dir)
        with pytest.raises(FileNotFoundError, match="build_chroma_index"):
            r.retrieve("post_treatment_surveillance", "CT")
