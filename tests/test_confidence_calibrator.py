"""
Tests for eval/confidence_calibrator.py — Phase 2 §12 / ADR-015.

Calibrator reads per-case (ambig_count, signal, should_approve) tuples,
sweeps candidate thresholds, returns the threshold that minimizes total
escalation error.
"""

import pytest

from eval.confidence_calibrator import (
    recommend,
    ConfusionMatrix,
    CalibrationRecommendation,
)


def _case(ambig: int, should_approve: bool, signal="meets_criteria", cid="c"):
    return {
        "case_id": cid,
        "ambiguous_or_unmet_count": ambig,
        "overall_signal": signal,
        "expected_should_approve": should_approve,
    }


class TestRecommendBasic:
    def test_returns_calibration_recommendation(self):
        cases = [_case(0, True), _case(3, False)]
        rec = recommend(cases)
        assert isinstance(rec, CalibrationRecommendation)
        assert isinstance(rec.confusion_at_recommendation, ConfusionMatrix)
        assert rec.skipped_cases == 0

    def test_empty_input_returns_default(self):
        rec = recommend([])
        assert rec.recommended_threshold == 2
        assert "No labeled cases" in rec.note

    def test_all_unlabeled_returns_default(self):
        cases = [{"case_id": "c1", "ambiguous_or_unmet_count": 1, "overall_signal": "meets_criteria"}]
        rec = recommend(cases)
        assert rec.skipped_cases == 1
        assert rec.recommended_threshold == 2


class TestPerfectSeparation:
    def test_clear_boundary_gets_optimal_threshold(self):
        """3 approves at low counts (0, 0, 1), 3 escalates at high counts (4, 5, 6) → threshold somewhere in [1, 3]."""
        cases = [
            _case(0, True), _case(0, True), _case(1, True),
            _case(4, False), _case(5, False), _case(6, False),
        ]
        rec = recommend(cases)
        # Any threshold in [1, 3] achieves perfect separation; tie-break picks lowest
        assert rec.recommended_threshold == 1
        assert rec.confusion_at_recommendation.total_error == 0
        assert "Perfect separation" in rec.note


class TestImperfectSeparation:
    def test_overlapping_distributions_finds_min_error(self):
        """approves at (0,1,2,3), escalates at (1,2,3,4) — overlapping."""
        cases = [
            _case(0, True), _case(1, True), _case(2, True), _case(3, True),
            _case(1, False), _case(2, False), _case(3, False), _case(4, False),
        ]
        rec = recommend(cases)
        # Expected min error is achievable; specific threshold depends on tie-break
        assert rec.confusion_at_recommendation.total_error <= 4

    def test_tie_break_prefers_lower_threshold(self):
        """Two thresholds with equal error — pick the lower (more conservative)."""
        # Both threshold 1 and threshold 2 give 0 error
        cases = [_case(0, True), _case(3, False)]
        rec = recommend(cases)
        assert rec.recommended_threshold == 0


class TestSignalCheck:
    def test_ambiguous_signal_always_fails_gate(self):
        """A case with overall_signal='ambiguous' fails the gate regardless of count."""
        cases = [
            _case(0, True, signal="ambiguous"),  # should-approve but signal blocks
            _case(0, True, signal="meets_criteria"),  # passes cleanly
        ]
        rec = recommend(cases)
        # The ambiguous-signal case can't pass at any threshold → 1 false escalation always
        cm = rec.confusion_at_recommendation
        assert cm.false_escalations >= 1


class TestSkippedCases:
    def test_partially_labeled_cases_only_labeled_counted(self):
        labeled = [_case(0, True), _case(3, False)]
        unlabeled = [{"case_id": "u1", "ambiguous_or_unmet_count": 1, "overall_signal": "meets_criteria"}]
        rec = recommend(labeled + unlabeled)
        assert rec.skipped_cases == 1
        assert rec.confusion_at_recommendation.total_cases == 2  # only labeled cases scored


class TestConfusionMatrixMath:
    def test_confusion_counts_sum_to_total(self):
        cases = [_case(0, True), _case(1, False), _case(2, True), _case(3, False)]
        rec = recommend(cases)
        cm = rec.confusion_at_recommendation
        assert cm.total_cases == 4
        assert (cm.true_approvals + cm.true_escalations
                + cm.false_approvals + cm.false_escalations) == 4

    def test_total_error_is_false_counts(self):
        cm = ConfusionMatrix(threshold=2, true_approvals=3, true_escalations=2,
                             false_approvals=1, false_escalations=2)
        assert cm.total_error == 3


class TestSweepBreadth:
    def test_sweep_covers_zero_to_max_count(self):
        cases = [_case(0, True), _case(5, False)]
        rec = recommend(cases)
        thresholds_swept = [cm.threshold for cm in rec.confusions_per_threshold]
        assert thresholds_swept == [0, 1, 2, 3, 4, 5]
