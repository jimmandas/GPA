"""
ConfidenceCalibrator — Phase 2 §12 / ADR-015.

Reads eval per-case data and recommends a Confidence Gate threshold that
minimizes total escalation error against ground-truth labels. Outputs the
recommendation + the confusion matrix that produced it.

Inputs:
  Per-case records of the form:
    {
      "case_id": str,
      "ambiguous_or_unmet_count": int,
      "overall_signal": str,
      "expected_should_approve": bool,  # from ground_truth.jsonl
    }

  These records can be assembled from eval results today — they correspond
  to the policy_map output + ground truth `expected_should_approve` field.

Logic:
  For each candidate threshold T in [0, max_observed_count]:
    A case passes the gate iff overall_signal != "ambiguous" AND
                                  ambiguous_or_unmet_count <= T.
    A case is approved iff it passes the gate AND ground truth says approve.
    A case is escalated iff it fails the gate OR ground truth says escalate.

  Compute:
    false_escalations = approved_in_truth but failed_gate
    false_approvals   = should_escalate_in_truth but passed_gate
    total_error       = false_escalations + false_approvals

  Return the T that minimizes total_error. On ties, prefer the lower T
  (more conservative — escalates earlier).

Limits:
  - Single global threshold, NOT per-failure-mode (Phase 2 plan called out
    per-mode tuning; current dataset is too small at n=15 to fit reliably
    per-mode. Per-mode tuning is a Phase 3 enhancement).
  - Assumes ground-truth `expected_should_approve` is populated. Cases
    without it are skipped.

This module is pure-function. No side effects, no I/O at call time.
The eval runner can call this and surface the recommendation in the report.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ConfusionMatrix:
    """Counts at a given threshold."""
    threshold: int
    true_approvals: int           # passed gate AND ground-truth approves
    true_escalations: int         # failed gate AND ground-truth escalates
    false_approvals: int          # passed gate BUT ground-truth escalates
    false_escalations: int        # failed gate BUT ground-truth approves

    @property
    def total_error(self) -> int:
        return self.false_approvals + self.false_escalations

    @property
    def total_cases(self) -> int:
        return (
            self.true_approvals + self.true_escalations
            + self.false_approvals + self.false_escalations
        )


@dataclass
class CalibrationRecommendation:
    """Output of ConfidenceCalibrator.recommend()."""
    recommended_threshold: int
    confusion_at_recommendation: ConfusionMatrix
    confusions_per_threshold: list[ConfusionMatrix]
    skipped_cases: int  # ground_truth.expected_should_approve missing
    note: str


def _case_passes_at_threshold(
    overall_signal: str, ambig_count: int, threshold: int
) -> bool:
    """Match gates/confidence.py's pass logic exactly."""
    if overall_signal == "ambiguous":
        return False
    return ambig_count <= threshold


def _compute_confusion(cases: list[dict], threshold: int) -> ConfusionMatrix:
    ta = te = fa = fe = 0
    for c in cases:
        ambig = int(c["ambiguous_or_unmet_count"])
        signal = c.get("overall_signal", "meets_criteria")
        passed = _case_passes_at_threshold(signal, ambig, threshold)
        should_approve = bool(c["expected_should_approve"])
        if passed and should_approve:
            ta += 1
        elif not passed and not should_approve:
            te += 1
        elif passed and not should_approve:
            fa += 1
        else:  # not passed and should_approve
            fe += 1
    return ConfusionMatrix(
        threshold=threshold,
        true_approvals=ta,
        true_escalations=te,
        false_approvals=fa,
        false_escalations=fe,
    )


def recommend(case_records: list[dict]) -> CalibrationRecommendation:
    """
    Compute the threshold that minimizes total escalation error.

    Args:
        case_records: List of per-case dicts with keys:
          - ambiguous_or_unmet_count: int
          - overall_signal: str
          - expected_should_approve: bool (cases without this key are skipped)

    Returns:
        CalibrationRecommendation with the recommended threshold, the
        confusion matrix at that threshold, and the full sweep over
        threshold candidates.
    """
    # Filter to cases with labels
    labeled: list[dict] = []
    skipped = 0
    for c in case_records:
        if "expected_should_approve" not in c:
            skipped += 1
            continue
        labeled.append(c)

    if not labeled:
        return CalibrationRecommendation(
            recommended_threshold=2,  # default
            confusion_at_recommendation=ConfusionMatrix(2, 0, 0, 0, 0),
            confusions_per_threshold=[],
            skipped_cases=skipped,
            note="No labeled cases. Defaulted to threshold=2 (matches gate default).",
        )

    max_count = max(int(c["ambiguous_or_unmet_count"]) for c in labeled)
    candidates = list(range(0, max_count + 1))

    sweep = [_compute_confusion(labeled, t) for t in candidates]
    # Min total_error, tie-break on lower threshold (more conservative)
    best = min(sweep, key=lambda cm: (cm.total_error, cm.threshold))

    note_parts = [
        f"Calibrated on {len(labeled)} labeled cases (skipped {skipped} unlabeled).",
        f"Recommended threshold {best.threshold} yields total error {best.total_error} "
        f"(false escalations={best.false_escalations}, false approvals={best.false_approvals}).",
    ]
    if best.total_error == 0:
        note_parts.append("Perfect separation achieved at this threshold.")
    return CalibrationRecommendation(
        recommended_threshold=best.threshold,
        confusion_at_recommendation=best,
        confusions_per_threshold=sweep,
        skipped_cases=skipped,
        note=" ".join(note_parts),
    )
