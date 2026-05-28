"""
Tests for the citation_correctness eval dim — scope §8 Failure Mode #9.

Catches "Faithful-but-Wrong": brief cites a real NCCN passage that is the
WRONG passage for the case. Precision over cited passage IDs vs. expected.
"""

import pytest

from eval.dimensions import score_citation_correctness


def _case(case_id, expected_status, policy_map):
    return {
        "case_id": case_id,
        "ground_truth": {"expected_criterion_status": expected_status},
        "policy_map": policy_map,
    }


class TestCitationCorrectnessNA:
    def test_no_cases_returns_na(self):
        result = score_citation_correctness([])
        assert result.score is None
        assert result.passed is None

    def test_no_expected_status_returns_na(self):
        cases = [{"case_id": "c1", "ground_truth": {}, "policy_map": {"criteria": [{"nccn_passage_id": "P1"}]}}]
        result = score_citation_correctness(cases)
        assert result.score is None

    def test_no_policy_map_returns_na(self):
        cases = [{"case_id": "c1", "ground_truth": {"expected_criterion_status": {"P1": "met"}}}]
        result = score_citation_correctness(cases)
        assert result.score is None

    def test_no_cited_passages_returns_na(self):
        cases = [_case("c1", {"P1": "met"}, {"criteria": []})]
        result = score_citation_correctness(cases)
        # No citations to score → N/A
        assert result.score is None


class TestCitationCorrectnessPerfect:
    def test_all_cited_are_expected(self):
        cases = [
            _case("c1", {"P1": "met", "P2": "met"},
                  {"criteria": [
                      {"nccn_passage_id": "P1", "status": "met"},
                      {"nccn_passage_id": "P2", "status": "met"},
                  ]}),
        ]
        result = score_citation_correctness(cases)
        assert result.score == 1.0
        assert result.passed is True

    def test_passage_ids_used_field(self):
        """citation_correctness also picks up passage_ids_used (not just criteria)."""
        cases = [
            _case("c1", {"P1": "met"}, {"passage_ids_used": ["P1"]}),
        ]
        result = score_citation_correctness(cases)
        assert result.score == 1.0


class TestCitationCorrectnessFailureMode9:
    def test_wrong_citation_lowers_precision(self):
        """Cite 1 right passage + 1 wrong passage → precision = 0.5"""
        cases = [
            _case("c1", {"P1": "met", "P2": "met"},
                  {"criteria": [
                      {"nccn_passage_id": "P1"},
                      {"nccn_passage_id": "P_wrong"},
                  ]}),
        ]
        result = score_citation_correctness(cases)
        assert result.score == 0.5
        assert result.passed is False
        assert "P_wrong" in result.notes

    def test_all_wrong_citations_zero(self):
        cases = [
            _case("c1", {"P1": "met"},
                  {"criteria": [
                      {"nccn_passage_id": "P_wrong_1"},
                      {"nccn_passage_id": "P_wrong_2"},
                  ]}),
        ]
        result = score_citation_correctness(cases)
        assert result.score == 0.0
        assert result.passed is False


class TestCitationCorrectnessAggregation:
    def test_mean_across_cases(self):
        cases = [
            _case("c1", {"P1": "met"}, {"criteria": [{"nccn_passage_id": "P1"}]}),               # 1.0
            _case("c2", {"P2": "met"}, {"criteria": [{"nccn_passage_id": "P2"}, {"nccn_passage_id": "P_wrong"}]}),  # 0.5
        ]
        result = score_citation_correctness(cases)
        assert result.score == 0.75  # (1.0 + 0.5) / 2

    def test_target_is_high(self):
        """Citation correctness target is >=0.95 — near-perfect."""
        cases = [_case("c1", {"P1": "met"}, {"criteria": [{"nccn_passage_id": "P1"}]})]
        result = score_citation_correctness(cases)
        assert result.target == ">=0.95"

    def test_passes_at_95(self):
        # 19/20 = 0.95 — passes
        crit = [{"nccn_passage_id": f"P{i}"} for i in range(20)]
        cases = [_case("c1",
                       {f"P{i}": "met" for i in range(19)},  # 19 expected
                       {"criteria": crit})]                  # 20 cited; 1 wrong
        result = score_citation_correctness(cases)
        assert result.score == 0.95
        assert result.passed is True
