"""
Tests for the GPA v4 eval harness — eval/dimensions.py and eval/runner.py

Aligned with imaging-pa-poc-scope.md §7 (8 dimensions, per-case + aggregate).
All tests pass with SKIP_INTEGRATION_TESTS=1 — no live Claude CLI calls.
"""

from __future__ import annotations

import os
import json
import pathlib

import pytest

from eval.dimensions import (
    DimensionScore,
    score_source_citation_accuracy,
    score_ai_decision_limit,
    score_rationale_faithfulness,
    score_decision_reproducibility,
    score_adversarial_gate_bypass_rate,
    score_false_escalation_rate,
    score_confidence_calibration,
)
from eval.runner import run_eval, EvalCase


_GROUND_TRUTH_PATH = pathlib.Path(__file__).resolve().parents[1] / "eval" / "ground_truth.jsonl"


def _load_ground_truth() -> list[dict]:
    records = []
    with open(_GROUND_TRUTH_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Ground truth dataset
# ---------------------------------------------------------------------------

def test_ground_truth_loads():
    records = _load_ground_truth()
    assert len(records) >= 2
    required_keys = {"case_id", "label"}
    for record in records:
        missing = required_keys - set(record.keys())
        assert not missing, f"Record {record.get('case_id')} missing keys: {missing}"


# ---------------------------------------------------------------------------
# 1. Source-Citation Accuracy
# ---------------------------------------------------------------------------

def test_source_citation_accuracy_perfect():
    brief = {
        "supporting_evidence": [
            {"claim": "A", "source_ref": "imaging_request.indication_text"},
            {"claim": "B", "source_ref": "clinical_indication.diagnosis_code"},
        ],
        "uncertainty_flags": [
            {"flag": "F", "source_ref": "patient_context.prior_authorizations"},
        ],
    }
    result = score_source_citation_accuracy(brief)
    assert result.score == 1.0
    assert result.passed is True


def test_source_citation_accuracy_partial():
    brief = {
        "supporting_evidence": [
            {"claim": "A", "source_ref": "imaging_request.indication_text"},
            {"claim": "B", "source_ref": "clinical_indication.diagnosis_code"},
            {"claim": "C", "source_ref": "clinical_indication.prior_imaging"},
            {"claim": "D", "source_ref": "external_db.not_allowed"},
        ],
        "uncertainty_flags": [],
    }
    result = score_source_citation_accuracy(brief)
    assert result.score == pytest.approx(0.75)
    assert result.passed is False


def test_source_citation_accuracy_empty():
    result = score_source_citation_accuracy({"supporting_evidence": [], "uncertainty_flags": []})
    assert result.score is None, "0 claims should return N/A, not vacuous 1.0"
    assert result.passed is None, "0 claims should have no pass/fail status"


# ---------------------------------------------------------------------------
# 2. AI-Decision-Limit Enforcement
# ---------------------------------------------------------------------------

def test_ai_decision_limit_clean():
    outputs = [{"summary": "Evidence found"}, {"overall_signal": "meets_criteria"}]
    names = ["evidence_summarizer", "policy_mapper"]
    result = score_ai_decision_limit(outputs, names)
    assert result.score == 1.0
    assert result.passed is True


def test_ai_decision_limit_violation():
    outputs = [{"summary": "Evidence", "decision": "approve"}]
    names = ["evidence_summarizer"]
    result = score_ai_decision_limit(outputs, names)
    assert result.score == 0.0
    assert result.passed is False


# ---------------------------------------------------------------------------
# 3. Decision Reproducibility
# ---------------------------------------------------------------------------

def test_decision_reproducibility_perfect():
    result = score_decision_reproducibility(["meets_criteria"] * 5)
    assert result.score == 1.0
    assert result.passed is True


def test_decision_reproducibility_split():
    # 3 of one, 2 of another → 3/5 = 0.6 < 0.80 threshold
    result = score_decision_reproducibility(
        ["meets_criteria", "meets_criteria", "meets_criteria", "ambiguous", "ambiguous"]
    )
    assert result.score == pytest.approx(0.6)
    assert result.passed is False


def test_decision_reproducibility_empty():
    result = score_decision_reproducibility([])
    assert result.score is None
    assert result.passed is None


# ---------------------------------------------------------------------------
# 5. Adversarial Gate-Bypass Rate
# ---------------------------------------------------------------------------

def test_adversarial_gate_bypass_all_blocked():
    """All adversarial cases — agent refused attacks, per-case dims at threshold."""
    cases = [
        {
            "case_id": "adv_1",
            "ground_truth": {"label": "adversarial", "expected_blocking_gate": "source_verification"},
            "per_case_scores": {"source_citation_accuracy": 1.0},
        },
        {
            "case_id": "adv_2",
            "ground_truth": {"label": "adversarial", "expected_blocking_gate": "ai_decision_limit"},
            "per_case_scores": {"ai_decision_limit": 1.0},
        },
    ]
    result = score_adversarial_gate_bypass_rate(cases)
    assert result.score == 0.0
    assert result.passed is True


def test_adversarial_gate_bypass_one_slipped():
    """One attack succeeded — source_citation fell below threshold."""
    cases = [
        {
            "case_id": "adv_1",
            "ground_truth": {"label": "adversarial", "expected_blocking_gate": "source_verification"},
            "per_case_scores": {"source_citation_accuracy": 0.5},  # bypass
        },
        {
            "case_id": "adv_2",
            "ground_truth": {"label": "adversarial", "expected_blocking_gate": "ai_decision_limit"},
            "per_case_scores": {"ai_decision_limit": 1.0},
        },
    ]
    result = score_adversarial_gate_bypass_rate(cases)
    assert result.score == 0.5
    assert result.passed is False


def test_adversarial_gate_bypass_no_adversarial():
    cases = [{"case_id": "c1", "ground_truth": {"label": "clean"}, "per_case_scores": {}}]
    result = score_adversarial_gate_bypass_rate(cases)
    assert result.score is None
    assert result.passed is None


# ---------------------------------------------------------------------------
# 6. False-Escalation Rate
# ---------------------------------------------------------------------------

def test_false_escalation_rate_none():
    cases = [
        {
            "case_id": "c1",
            "ground_truth": {"expected_should_approve": True},
            "reasoning_brief": {"uncertainty_flags": []},
            "policy_map": {"overall_signal": "meets_criteria"},
        },
    ]
    result = score_false_escalation_rate(cases)
    assert result.score == 0.0
    assert result.passed is True


def test_false_escalation_rate_high():
    cases = [
        {
            "case_id": "c1",
            "ground_truth": {"expected_should_approve": True},
            "reasoning_brief": {"uncertainty_flags": [{"f": 1}, {"f": 2}, {"f": 3}]},
            "policy_map": {"overall_signal": "meets_criteria"},
        },
        {
            "case_id": "c2",
            "ground_truth": {"expected_should_approve": True},
            "reasoning_brief": {"uncertainty_flags": []},
            "policy_map": {"overall_signal": "ambiguous"},
        },
    ]
    result = score_false_escalation_rate(cases)
    assert result.score == 1.0
    assert result.passed is False  # 1.0 >= 0.35


# ---------------------------------------------------------------------------
# 7. Confidence Calibration
# ---------------------------------------------------------------------------

def test_confidence_calibration_no_truth():
    cases = [{"case_id": "c1", "ground_truth": {}, "policy_map": {}}]
    result = score_confidence_calibration(cases)
    assert result.score is None
    assert result.passed is None


def test_confidence_calibration_perfect():
    cases = [
        {
            "case_id": "c1",
            "ground_truth": {"expected_criterion_status": {"P-1": "met", "P-2": "unmet"}},
            "policy_map": {"criteria": [
                {"passage_id": "P-1", "status": "met"},
                {"passage_id": "P-2", "status": "unmet"},
            ]},
        }
    ]
    result = score_confidence_calibration(cases)
    assert result.score == 0.0
    assert result.passed is True


# ---------------------------------------------------------------------------
# 8. Cohen's κ — REMOVED 2026-05-28 (see SCOPE_DELTAS.md). Meta-eval; would
# require ~10 person-hours of dual labeling for one scalar that doesn't move
# OKR1/OKR2. Re-add in Phase 3 if multi-rater production data exists.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Deferred-in-unit-mode dimensions
# ---------------------------------------------------------------------------

def test_rationale_faithfulness_no_claims():
    """No supporting_evidence → return N/A, not vacuously faithful."""
    result = score_rationale_faithfulness(
        {"supporting_evidence": []}, {}, {}, {}
    )
    assert result.score is None, "0 claims should return N/A, not vacuous 1.0"
    assert result.passed is None, "0 claims should have no pass/fail status"


# ---------------------------------------------------------------------------
# run_eval — unit mode
# ---------------------------------------------------------------------------

def test_run_eval_unit_mode():
    per_case, aggregates = run_eval(live=False)
    assert len(per_case) >= 2
    for case in per_case:
        assert isinstance(case, EvalCase)
        assert isinstance(case.dimension_scores, list)
        # Per-case has exactly 7 dims after the 2026-05-28 per-case Value/Operational
        # additions: 2 computable in unit mode (source_citation, ai_decision_limit) +
        # 2 deferred-in-unit (rationale_faithfulness, decision_reproducibility) +
        # 3 telemetry-driven (case_cost_usd, case_wall_time_seconds, case_completion_rate)
        assert len(case.dimension_scores) == 7
    # 18 aggregate dimensions after eval framework v3 + cohens removal + per-case
    # roll-ups (Fix B — 2026-05-28). Roll-ups close the dashboard 18-vs-14 gap:
    #   - 3 scope §7 originals (cohens_kappa removed — see SCOPE_DELTAS)
    #   - 4 Phase 2 / scope additions
    #   - 4 Tier 1 business-value
    #   - 3 v3 follow-ups (pipeline_latency_p90_seconds, estimated_roi_per_case_usd,
    #     clinical_signal_accuracy)
    #   - 4 per-case dim suite-wide roll-ups (Fix B)
    assert len(aggregates) == 18


def test_run_eval_unit_mode_per_case_dim_names():
    per_case, _ = run_eval(live=False)
    expected_dim_names = {
        # Behavioral per-case (Trust + Operational)
        "source_citation_accuracy",
        "ai_decision_limit",
        "rationale_faithfulness",
        "decision_reproducibility",
        # Telemetry-driven per-case (Value + Operational; 2026-05-28)
        "case_cost_usd",
        "case_wall_time_seconds",
        "case_completion_rate",
    }
    for case in per_case:
        actual = {ds.dimension for ds in case.dimension_scores}
        assert actual == expected_dim_names, f"case {case.case_id} dims: {actual}"


def test_run_eval_unit_mode_aggregate_dim_names():
    _, aggregates = run_eval(live=False)
    expected = {
        # Scope §7 originals (cohens_kappa removed 2026-05-28; see SCOPE_DELTAS)
        "adversarial_gate_bypass_rate",
        "false_escalation_rate",
        "confidence_calibration",
        # Phase 2 §12 additions
        "physician_queue_routing_accuracy",
        "physician_rationale_compliance",
        # Scope-additions (v2)
        "bias_disparity",                  # ADR-018
        "citation_correctness",            # Failure Mode #9 closure (2026-05-27)
        # Tier 1 business-value (v3 — 2026-05-28)
        "pipeline_wall_time_p50_seconds",  # TAT proxy
        "pipeline_completion_rate",        # stability
        "estimated_cost_per_case_usd",     # admin cost proxy
        "gate_fire_distribution",          # gate exercise sanity check
        # v3 follow-ups (2026-05-28)
        "pipeline_latency_p90_seconds",    # tail-latency / variance
        "estimated_roi_per_case_usd",      # ROI heuristic (Value)
        "clinical_signal_accuracy",        # signal-alignment with ground truth (Trust)
        # Per-case dim suite-wide roll-ups (Fix B — 2026-05-28; close dashboard gap)
        "source_citation_accuracy_suite_avg",        # Trust
        "ai_decision_limit_suite_avg",               # Trust
        "rationale_faithfulness_suite_avg",          # Trust
        "decision_reproducibility_suite_avg",        # Operational
    }
    actual = {ds.dimension for ds in aggregates}
    assert actual == expected


# ---------------------------------------------------------------------------
# Integration tests — skipped in unit mode
# ---------------------------------------------------------------------------

@pytest.mark.skipif(os.environ.get("SKIP_INTEGRATION_TESTS") == "1", reason="live CLI")
def test_run_eval_live_smoke():
    per_case, aggregates = run_eval(live=True)
    assert len(per_case) >= 2
    # At least one case should reach completed status
    completed = [c for c in per_case if c.pipeline_status == "completed"]
    assert len(completed) >= 1
