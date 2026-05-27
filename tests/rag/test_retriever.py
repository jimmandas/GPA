"""
Tests for rag/retriever.py — PolicyRetriever interface + FixtureRetriever.
"""

import pathlib
import tempfile

import pytest
import yaml

from rag.retriever import FixtureRetriever, PolicyRetriever, RetrievedCorpus


_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_REAL_FIXTURES_DIR = _REPO_ROOT / "policy" / "nccn_fixtures"


class TestFixtureRetrieverHappyPath:
    def test_returns_retrieved_corpus_for_known_pair(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        corpus = r.retrieve("post_treatment_surveillance", "CT")
        assert isinstance(corpus, RetrievedCorpus)
        assert corpus.indication_category == "post_treatment_surveillance"
        assert corpus.modality == "CT"
        assert len(corpus.criteria) >= 1
        assert corpus.retriever_kind == "fixture"

    def test_content_hash_is_stable_across_reads(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        c1 = r.retrieve("post_treatment_surveillance", "CT")
        c2 = r.retrieve("post_treatment_surveillance", "CT")
        assert c1.content_hash == c2.content_hash
        assert c1.content_hash.startswith("sha256:")

    def test_payload_dict_has_expected_keys(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        corpus = r.retrieve("post_treatment_surveillance", "CT")
        payload = corpus.to_payload_dict()
        assert set(payload.keys()) == {
            "indication_category", "modality", "criteria", "overall_policy_reference"
        }

    def test_criteria_have_passage_ids(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        corpus = r.retrieve("post_treatment_surveillance", "CT")
        for criterion in corpus.criteria:
            assert "passage_id" in criterion
            assert criterion["passage_id"].startswith("NCCN-NSCLC-SURV-")


class TestFixtureRetrieverMissingFixture:
    def test_returns_empty_corpus_with_error_for_unknown_pair(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        corpus = r.retrieve("not_a_real_indication", "MRI")
        assert isinstance(corpus, RetrievedCorpus)
        assert corpus.criteria == []
        assert "error" in corpus.extra


class TestFixtureRetrieverJsonCompat:
    def test_retrieve_as_json_returns_string(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        s = r.retrieve_as_json("post_treatment_surveillance", "CT")
        assert isinstance(s, str)
        assert "criteria" in s

    def test_retrieve_as_json_returns_error_for_missing(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        s = r.retrieve_as_json("not_a_real_indication", "MRI")
        assert "error" in s


class TestPolicyRetrieverInterface:
    def test_abstract_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            PolicyRetriever()

    def test_fixture_retriever_is_a_policy_retriever(self):
        r = FixtureRetriever(_REAL_FIXTURES_DIR)
        assert isinstance(r, PolicyRetriever)


class TestFixtureRetrieverWithCustomCorpus:
    """Verify retriever works on an arbitrary corpus dir — not just the bundled NCCN one."""

    def test_loads_user_supplied_corpus(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = pathlib.Path(tmp)
            payload = {
                "indication_category": "test_indication",
                "modality": "TEST",
                "criteria": [
                    {"passage_id": "TEST-1", "criterion_text": "test criterion"}
                ],
                "overall_policy_reference": "Test ref",
            }
            (tmp_path / "test_indication_TEST.yaml").write_text(
                yaml.safe_dump(payload), encoding="utf-8"
            )
            r = FixtureRetriever(tmp_path)
            corpus = r.retrieve("test_indication", "TEST")
            assert corpus.criteria == payload["criteria"]
            assert corpus.overall_policy_reference == "Test ref"
