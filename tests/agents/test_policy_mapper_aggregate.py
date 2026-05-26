"""
Tests for agents/policy_mapper/aggregate.py — pure-function criterion aggregation.

This is the v2 fix for reproducibility flakiness. Aggregation must be deterministic
and total (every valid input produces an output).
"""

import pytest

from agents.policy_mapper.aggregate import aggregate_overall_signal


class TestHappyPath:
    def test_all_met_returns_meets_criteria(self):
        criteria = [
            {"passage_id": "P-1", "status": "met"},
            {"passage_id": "P-2", "status": "met"},
            {"passage_id": "P-3", "status": "met"},
        ]
        assert aggregate_overall_signal(criteria) == "meets_criteria"

    def test_one_unmet_returns_does_not_meet(self):
        criteria = [
            {"passage_id": "P-1", "status": "met"},
            {"passage_id": "P-2", "status": "unmet"},
            {"passage_id": "P-3", "status": "met"},
        ]
        assert aggregate_overall_signal(criteria) == "does_not_meet"

    def test_one_ambiguous_no_unmet_returns_ambiguous(self):
        criteria = [
            {"passage_id": "P-1", "status": "met"},
            {"passage_id": "P-2", "status": "ambiguous"},
            {"passage_id": "P-3", "status": "met"},
        ]
        assert aggregate_overall_signal(criteria) == "ambiguous"

    def test_unmet_trumps_ambiguous(self):
        """Per rule order: unmet wins over ambiguous."""
        criteria = [
            {"passage_id": "P-1", "status": "ambiguous"},
            {"passage_id": "P-2", "status": "unmet"},
            {"passage_id": "P-3", "status": "ambiguous"},
        ]
        assert aggregate_overall_signal(criteria) == "does_not_meet"

    def test_single_criterion_met(self):
        assert aggregate_overall_signal([{"passage_id": "P-1", "status": "met"}]) == "meets_criteria"

    def test_single_criterion_unmet(self):
        assert aggregate_overall_signal([{"passage_id": "P-1", "status": "unmet"}]) == "does_not_meet"

    def test_single_criterion_ambiguous(self):
        assert aggregate_overall_signal([{"passage_id": "P-1", "status": "ambiguous"}]) == "ambiguous"


class TestDeterminism:
    """The whole point of this module: same input → same output, every time."""

    def test_same_input_same_output_across_many_calls(self):
        criteria = [
            {"passage_id": "P-1", "status": "ambiguous"},
            {"passage_id": "P-2", "status": "unmet"},
            {"passage_id": "P-3", "status": "met"},
        ]
        results = {aggregate_overall_signal(criteria) for _ in range(100)}
        assert len(results) == 1

    def test_order_does_not_affect_result(self):
        criteria_a = [
            {"passage_id": "P-1", "status": "met"},
            {"passage_id": "P-2", "status": "unmet"},
            {"passage_id": "P-3", "status": "ambiguous"},
        ]
        criteria_b = list(reversed(criteria_a))
        assert aggregate_overall_signal(criteria_a) == aggregate_overall_signal(criteria_b)


class TestErrors:
    def test_empty_criteria_raises(self):
        with pytest.raises(ValueError, match="empty criteria list"):
            aggregate_overall_signal([])

    def test_invalid_status_raises(self):
        with pytest.raises(ValueError, match="status must be one of"):
            aggregate_overall_signal([{"passage_id": "P-1", "status": "maybe"}])

    def test_missing_status_raises(self):
        with pytest.raises(ValueError, match="status must be one of"):
            aggregate_overall_signal([{"passage_id": "P-1"}])

    def test_non_dict_criterion_raises(self):
        with pytest.raises(ValueError, match="must be a dict"):
            aggregate_overall_signal(["just a string"])
