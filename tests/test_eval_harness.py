"""
Tests for the GPA v4 eval harness — eval/dimensions.py and eval/runner.py

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
    score_gate_bypass_rate,
    score_schema_compliance,
    score_uncertainty_flag_coverage,
    score_overall_signal_match,
    score_rationale_faithfulness,
    score_decision_reproducibility,
)
from eval.runner import run_eval, EvalCase


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
    assert len(records) == 2
    required_keys = {
        "case_id",
        "expected_overall_signal",
        "expected_uncertainty_flag_count_min",
        "expected_uncertainty_flag_count_max",
        "expected_gate_bypass",
        "expected_decision_field_emitted",
    }
    for record in records:
        missing = required_keys - set(record.keys())
        assert not missing, f"Record {record.get('case_id')} missing keys: {missing}"


# ---------------------------------------------------------------------------
# score_source_citation_accuracy
# ---------------------------------------------------------------------------

def test_score_source_citation_accuracy_perfect():
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


def test_score_source_citation_accuracy_partial():
    # 3 valid + 1 invalid = 0.75
    brief = {
        "supporting_evidence": [
            {"claim": "A", "source_ref": "imaging_request.indication_text"},
            {"claim": "B", "source_ref": "clinical_indication.diagnosis_code"},
            {"claim": "C", "source_ref": "clinical_indication.prior_imaging"},
            {"claim": "D", "source_ref": "external_db.not_allowed"},  # invalid
        ],
        "uncertainty_flags": [],
    }
    result = score_source_citation_accuracy(brief)
    assert result.score == pytest.approx(0.75)
    assert result.passed is False


def test_score_source_citation_accuracy_empty():
    brief = {
        "supporting_evidence": [],
        "uncertainty_flags": [],
    }
    result = score_source_citation_accuracy(brief)
    assert result.score == 1.0
    assert result.passed is True


# ---------------------------------------------------------------------------
# score_ai_decision_limit
# ---------------------------------------------------------------------------

def test_score_ai_decision_limit_clean():
    outputs = [
        {"summary": "Evidence found", "criteria": ["A"]},
        {"overall_signal": "meets_criteria"},
    ]
    names = ["evidence_summarizer", "policy_mapper"]
    result = score_ai_decision_limit(outputs, names)
    assert result.score == 1.0
    assert result.passed is True


def test_score_ai_decision_limit_violation():
    outputs = [
        {"summary": "Evidence found", "decision": "approve"},
    ]
    names = ["evidence_summarizer"]
    result = score_ai_decision_limit(outputs, names)
    assert result.score == 0.0
    assert result.passed is False


# ---------------------------------------------------------------------------
# score_gate_bypass_rate
# ---------------------------------------------------------------------------

def test_score_gate_bypass_all_fired():
    gate_events = [
        {"gate": "admission", "fired": True},
        {"gate": "source_verification", "fired": True},
        {"gate": "ai_decision_limit", "fired": True},
    ]
    result = score_gate_bypass_rate(gate_events)
    assert result.score == 0.0
    assert result.passed is True


# ---------------------------------------------------------------------------
# score_schema_compliance
# ---------------------------------------------------------------------------

def test_score_schema_compliance_all_valid():
    outputs = [{"a": 1}, {"b": 2}, {"c": 3}]
    schemas_valid = [True, True, True]
    result = score_schema_compliance(outputs, schemas_valid)
    assert result.score == 1.0
    assert result.passed is True


def test_score_schema_compliance_one_invalid():
    outputs = [{"a": 1}, {"b": 2}, {"c": 3}, {"d": 4}]
    schemas_valid = [True, True, False, True]
    result = score_schema_compliance(outputs, schemas_valid)
    assert result.score == pytest.approx(0.75)
    assert result.passed is False


# ---------------------------------------------------------------------------
# score_uncertainty_flag_coverage
# ---------------------------------------------------------------------------

def test_score_uncertainty_flag_coverage_in_range():
    brief = {
        "uncertainty_flags": [
            {"flag": "timing gap"},
            {"flag": "clinical staging only"},
        ]
    }
    ground_truth = {
        "expected_uncertainty_flag_count_min": 2,
        "expected_uncertainty_flag_count_max": 3,
    }
    result = score_uncertainty_flag_coverage(brief, ground_truth)
    assert result.passed is True


def test_score_uncertainty_flag_coverage_out_of_range():
    brief = {
        "uncertainty_flags": []
    }
    ground_truth = {
        "expected_uncertainty_flag_count_min": 2,
        "expected_uncertainty_flag_count_max": 3,
    }
    result = score_uncertainty_flag_coverage(brief, ground_truth)
    assert result.passed is False


# ---------------------------------------------------------------------------
# score_overall_signal_match
# ---------------------------------------------------------------------------

def test_score_overall_signal_match():
    policy_map = {"overall_signal": "meets_criteria"}
    ground_truth = {"expected_overall_signal": "meets_criteria"}
    result = score_overall_signal_match(policy_map, ground_truth)
    assert result.passed is True


def test_score_overall_signal_mismatch():
    policy_map = {"overall_signal": "meets_criteria"}
    ground_truth = {"expected_overall_signal": "ambiguous"}
    result = score_overall_signal_match(policy_map, ground_truth)
    assert result.passed is False


# ---------------------------------------------------------------------------
# Deferred dimensions
# ---------------------------------------------------------------------------

def test_score_rationale_faithfulness_deferred():
    result = score_rationale_faithfulness()
    assert result.score is None
    assert result.passed is None


def test_score_decision_reproducibility_deferred():
    result = score_decision_reproducibility()
    assert result.score is None
    assert result.passed is None


# ---------------------------------------------------------------------------
# run_eval — unit mode
# ---------------------------------------------------------------------------

def test_run_eval_unit_mode():
    cases = run_eval(live=False)
    assert len(cases) == 2
    for case in cases:
        assert isinstance(case, EvalCase)
        assert isinstance(case.dimension_scores, list)
        assert len(case.dimension_scores) > 0


def test_eval_case_computable_dimensions_have_scores():
    cases = run_eval(live=False)
    computable_dimensions = {
        "source_citation_accuracy",
        "ai_decision_limit",
        "gate_bypass_rate",
        "schema_compliance",
    }
    for case in cases:
        by_name = {ds.dimension: ds for ds in case.dimension_scores}
        for dim in computable_dimensions:
            assert dim in by_name, f"Missing dimension '{dim}' in case {case.case_id}"
            assert by_name[dim].score is not None, (
                f"Dimension '{dim}' has None score in unit mode for case {case.case_id}"
            )


# ---------------------------------------------------------------------------
# Integration tests — skipped in unit mode
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="live CLI"
)
def test_run_eval_live_clean_case():
    cases = run_eval(live=True)
    case_0001 = next((c for c in cases if c.case_id == "case_0001"), None)
    assert case_0001 is not None
    assert case_0001.overall_pass is True
    # Check overall signal
    signal_dim = next(
        (ds for ds in case_0001.dimension_scores if ds.dimension == "overall_signal_match"),
        None
    )
    assert signal_dim is not None
    assert signal_dim.passed is True


@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="live CLI"
)
def test_run_eval_live_ambiguous_case():
    cases = run_eval(live=True)
    case_0002 = next((c for c in cases if c.case_id == "case_0002"), None)
    assert case_0002 is not None
    # Check overall signal is ambiguous
    signal_dim = next(
        (ds for ds in case_0002.dimension_scores if ds.dimension == "overall_signal_match"),
        None
    )
    assert signal_dim is not None
    assert signal_dim.passed is True  # should match "ambiguous"
    # Check uncertainty flag count >= 2
    flag_dim = next(
        (ds for ds in case_0002.dimension_scores if ds.dimension == "uncertainty_flag_coverage"),
        None
    )
    assert flag_dim is not None
    assert flag_dim.passed is True
