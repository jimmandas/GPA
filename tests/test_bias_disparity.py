"""
Tests for the bias_disparity eval dim — scope addition 2026-05-27, ADR-018.

Detects whether the system performs systematically worse on certain
case cohorts (indication category, label category).
"""

import pytest

from eval.dimensions import score_bias_disparity


def _case(case_id, label_cat, indication_cat, scores):
    return {
        "case_id": case_id,
        "ground_truth": {
            "label_category": label_cat,
            "indication_category": indication_cat,
        },
        "per_case_dim_scores": scores,
    }


class TestBiasDisparityBasic:
    def test_empty_input_returns_na(self):
        result = score_bias_disparity([])
        assert result.score is None
        assert result.passed is None

    def test_single_cohort_value_no_disparity_possible(self):
        """If every case is in the same cohort, spread is 0."""
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "clean", "staging", {"source_citation_accuracy": 1.0}),
        ]
        result = score_bias_disparity(cases)
        # No 2nd cohort to compare → score should be max (no bias detected)
        assert result.passed is True


class TestBiasDisparityDetection:
    def test_uniform_scores_pass(self):
        """All cohorts score the same → no disparity."""
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "judgment_intensive", "staging", {"source_citation_accuracy": 1.0}),
            _case("c3", "adversarial", "staging", {"source_citation_accuracy": 1.0}),
        ]
        result = score_bias_disparity(cases)
        assert result.passed is True
        assert result.score == 1.0

    def test_large_spread_fails(self):
        """Score spread of 0.40 across label_category cohorts → fail."""
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c3", "adversarial", "staging", {"source_citation_accuracy": 0.6}),
            _case("c4", "adversarial", "staging", {"source_citation_accuracy": 0.6}),
        ]
        result = score_bias_disparity(cases)
        assert result.passed is False
        assert "label_category/source_citation_accuracy" in result.notes
        assert "clean=1.00" in result.notes
        assert "adversarial=0.60" in result.notes

    def test_just_under_threshold_passes(self):
        """Spread of 0.19 (< 0.20 threshold) → passes."""
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "adversarial", "staging", {"source_citation_accuracy": 0.81}),
        ]
        result = score_bias_disparity(cases)
        assert result.passed is True

    def test_clearly_above_threshold_fails(self):
        """Spread clearly above 0.20 → fails."""
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "adversarial", "staging", {"source_citation_accuracy": 0.75}),
        ]
        result = score_bias_disparity(cases)
        assert result.passed is False


class TestBiasDisparityMultipleCuts:
    def test_disparity_in_any_cut_fails(self):
        """Disparity only in indication_category → still fails."""
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "clean", "surveillance", {"source_citation_accuracy": 0.5}),
        ]
        result = score_bias_disparity(cases)
        assert result.passed is False
        assert "indication_category" in result.notes

    def test_multiple_disparate_dims_all_reported(self):
        """If two dims show disparity, both should be named in notes."""
        cases = [
            _case("c1", "clean", "staging", {
                "source_citation_accuracy": 1.0,
                "rationale_faithfulness": 1.0,
            }),
            _case("c2", "adversarial", "staging", {
                "source_citation_accuracy": 0.6,
                "rationale_faithfulness": 0.5,
            }),
        ]
        result = score_bias_disparity(cases)
        assert result.passed is False
        # Both dims show in the notes
        assert "source_citation_accuracy" in result.notes
        assert "rationale_faithfulness" in result.notes


class TestBiasDisparityIgnoresMissingData:
    def test_cases_without_label_category_skipped(self):
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            {"case_id": "c2", "ground_truth": {}, "per_case_dim_scores": {"source_citation_accuracy": 0.5}},
        ]
        # Only c1 has label_category set; not enough cohorts → no disparity
        result = score_bias_disparity(cases)
        # Either pass (one cohort) or NA — both acceptable
        assert result.passed in (True, None)

    def test_cases_without_dim_scores_skipped(self):
        cases = [
            _case("c1", "clean", "staging", {"source_citation_accuracy": 1.0}),
            _case("c2", "adversarial", "staging", {}),
        ]
        result = score_bias_disparity(cases)
        # Only c1 has scores → only one cohort for the dim → no disparity computable
        assert result.passed is True
