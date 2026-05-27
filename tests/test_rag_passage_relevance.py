"""
Tests for the rag_passage_relevance eval dim — Phase 2 §12.

Scores whether the policy mapper retrieved the NCCN passages the ground
truth says were relevant. Recall-based metric, mean across labeled cases.
"""

import pytest

from eval.dimensions import score_rag_passage_relevance


def _case(case_id, expected_status, policy_map):
    return {
        "case_id": case_id,
        "ground_truth": {"expected_criterion_status": expected_status},
        "policy_map": policy_map,
    }


class TestRAGPassageRelevanceNA:
    def test_no_cases_returns_na(self):
        result = score_rag_passage_relevance([])
        assert result.score is None
        assert result.passed is None

    def test_no_expected_criterion_status_returns_na(self):
        cases = [{"case_id": "c1", "ground_truth": {}, "policy_map": {}}]
        result = score_rag_passage_relevance(cases)
        assert result.score is None

    def test_missing_policy_map_treated_as_zero_recall(self):
        """A case with expected criteria but no policy_map → recall=0.0 (real miss)."""
        cases = [{"case_id": "c1", "ground_truth": {"expected_criterion_status": {"P1": "met"}}}]
        result = score_rag_passage_relevance(cases)
        assert result.score == 0.0
        assert result.passed is False


class TestRAGPassageRelevanceRecall:
    def test_perfect_recall(self):
        cases = [
            _case("c1", {"P1": "met", "P2": "met"},
                  {"passage_ids_used": ["P1", "P2"]}),
            _case("c2", {"P3": "met"},
                  {"passage_ids_used": ["P3"]}),
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 1.0
        assert result.passed is True

    def test_partial_recall(self):
        cases = [
            _case("c1", {"P1": "met", "P2": "met"},
                  {"passage_ids_used": ["P1"]}),  # recall = 0.5
            _case("c2", {"P3": "met", "P4": "met"},
                  {"passage_ids_used": ["P3", "P4"]}),  # recall = 1.0
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 0.75  # (0.5 + 1.0) / 2

    def test_no_recall_fails(self):
        cases = [
            _case("c1", {"P1": "met"}, {"passage_ids_used": ["P99"]}),
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 0.0
        assert result.passed is False
        assert "P1" in result.notes  # missing passage named


class TestRAGPassageRelevanceFallbackToCriteria:
    def test_falls_back_to_criteria_nccn_passage_id(self):
        """If passage_ids_used is missing, look at criteria[].nccn_passage_id."""
        cases = [
            _case("c1", {"P1": "met", "P2": "met"},
                  {"criteria": [
                      {"name": "k1", "status": "met", "nccn_passage_id": "P1"},
                      {"name": "k2", "status": "met", "nccn_passage_id": "P2"},
                  ]}),
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 1.0

    def test_dedupes_passage_ids_from_both_sources(self):
        """passage_ids_used + criteria nccn_passage_id should de-dupe."""
        cases = [
            _case("c1", {"P1": "met"},
                  {"passage_ids_used": ["P1"],
                   "criteria": [{"name": "k1", "status": "met", "nccn_passage_id": "P1"}]}),
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 1.0


class TestRAGPassageRelevanceTarget:
    def test_target_string(self):
        cases = [_case("c1", {"P1": "met"}, {"passage_ids_used": ["P1"]})]
        result = score_rag_passage_relevance(cases)
        assert result.target == ">=0.80"

    def test_passes_at_threshold(self):
        # 4 of 5 = 0.8 — pass
        cases = [
            _case("c1", {"P1": "met", "P2": "met", "P3": "met", "P4": "met", "P5": "met"},
                  {"passage_ids_used": ["P1", "P2", "P3", "P4"]}),  # recall = 0.8
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 0.8
        assert result.passed is True

    def test_fails_below_threshold(self):
        # 3 of 5 = 0.6 — fail
        cases = [
            _case("c1", {"P1": "met", "P2": "met", "P3": "met", "P4": "met", "P5": "met"},
                  {"passage_ids_used": ["P1", "P2", "P3"]}),  # recall = 0.6
        ]
        result = score_rag_passage_relevance(cases)
        assert result.score == 0.6
        assert result.passed is False
