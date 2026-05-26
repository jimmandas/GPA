"""
Tests for orchestrator/pipeline.py

All tests pass with SKIP_INTEGRATION_TESTS=1 — no live Claude CLI calls.
"""

import json
import os
import pathlib

import pytest

from logs.bilateral_logger import BilateralLogger, BilateralLoggerError
from orchestrator.pipeline import PipelineResult, run_pipeline, record_nurse_decision
from gates.denial import DenialAttemptError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_submission() -> dict:
    """Return a fully-populated, valid submission."""
    return {
        "case_id": "CASE-PIPELINE-001",
        "imaging_request": {
            "modality": "MRI",
            "body_region": "Brain",
            "indication_text": "Headache with visual disturbance",
        },
        "clinical_indication": {
            "diagnosis_code": "G43.909",
        },
        "policy_id": "POL-2024-MRI",
        "patient": {
            "patient_id": "PAT-001",
        },
    }


# ---------------------------------------------------------------------------
# test_admission_gate_blocks_incomplete_submission
# ---------------------------------------------------------------------------

def test_admission_gate_blocks_incomplete_submission():
    """
    A submission missing case_id must be escalated at the Admission Gate.
    No agents are called; no live SDK needed.
    """
    submission = {
        # case_id intentionally omitted
        "imaging_request": {
            "modality": "MRI",
            "body_region": "Brain",
            "indication_text": "Headache",
        },
        "clinical_indication": {
            "diagnosis_code": "G43.909",
        },
        "policy_id": "POL-2024-MRI",
    }
    result = run_pipeline(submission)
    assert result.status == "escalated"
    assert "admission_gate_failed" in result.escalation_reason


# ---------------------------------------------------------------------------
# test_pipeline_result_dataclass_fields
# ---------------------------------------------------------------------------

def test_pipeline_result_dataclass_fields():
    """PipelineResult must expose the required fields."""
    result = PipelineResult(
        case_id="test-case",
        status="completed",
        determination={"foo": "bar"},
        escalation_reason=None,
        audit_log_ref="decision_log/test-case.jsonl",
    )
    assert hasattr(result, "case_id")
    assert hasattr(result, "status")
    assert hasattr(result, "determination")
    assert hasattr(result, "escalation_reason")
    assert hasattr(result, "audit_log_ref")


# ---------------------------------------------------------------------------
# Nurse decision tests — require a monkeypatched bilateral logger
# ---------------------------------------------------------------------------

def _patch_logger(monkeypatch, tmp_path):
    """
    Replace the module-level get_logger() with a fresh BilateralLogger
    backed by tmp_path so tests don't touch the real decision_log/.
    """
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    test_logger = BilateralLogger(log_dir, failures_file)

    import orchestrator.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "get_logger", lambda: test_logger)
    return test_logger, log_dir


def test_record_nurse_decision_approve(monkeypatch, tmp_path):
    _patch_logger(monkeypatch, tmp_path)
    result = record_nurse_decision(
        "case_test", "approve", "Evidence supports medical necessity."
    )
    assert result.status == "completed"
    assert result.determination["path"] == "approve"


def test_record_nurse_decision_escalate(monkeypatch, tmp_path):
    _patch_logger(monkeypatch, tmp_path)
    result = record_nurse_decision(
        "case_test", "escalate", "Needs physician review."
    )
    assert result.status == "completed"
    assert result.determination["path"] == "escalate"


def test_record_nurse_decision_pend(monkeypatch, tmp_path):
    _patch_logger(monkeypatch, tmp_path)
    result = record_nurse_decision(
        "case_test", "pend", "Awaiting additional documentation."
    )
    assert result.status == "completed"
    assert result.determination["path"] == "pend"


def test_record_nurse_decision_empty_rationale_raises(monkeypatch, tmp_path):
    _patch_logger(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        record_nurse_decision("case_test", "approve", "")


def test_record_nurse_decision_whitespace_rationale_raises(monkeypatch, tmp_path):
    _patch_logger(monkeypatch, tmp_path)
    with pytest.raises(ValueError):
        record_nurse_decision("case_test", "approve", "   ")


def test_record_nurse_decision_deny_raises(monkeypatch, tmp_path):
    _patch_logger(monkeypatch, tmp_path)
    with pytest.raises(DenialAttemptError):
        record_nurse_decision("case_test", "deny", "Not covered.")


def test_record_nurse_decision_writes_bilateral_log(monkeypatch, tmp_path):
    """
    record_nurse_decision must write a nurse_action_record to the bilateral log.
    """
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    test_logger = BilateralLogger(log_dir, failures_file)

    import orchestrator.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "get_logger", lambda: test_logger)

    case_id = "case_log_test"
    record_nurse_decision(case_id, "approve", "All criteria met.")

    log_file = log_dir / f"{case_id}.jsonl"
    assert log_file.exists(), "log file must exist after record_nurse_decision"

    lines = log_file.read_text().splitlines()
    assert len(lines) >= 1, "at least one log record expected"

    records = [json.loads(line) for line in lines]
    types = [r.get("type") for r in records]
    assert "nurse_action_record" in types, f"nurse_action_record not found; got: {types}"


def test_record_nurse_decision_logger_failure_propagates(monkeypatch, tmp_path):
    """
    If os.fsync raises, BilateralLoggerError must propagate from record_nurse_decision.
    """
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    test_logger = BilateralLogger(log_dir, failures_file)

    import orchestrator.pipeline as pipeline_module
    monkeypatch.setattr(pipeline_module, "get_logger", lambda: test_logger)
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk full")))

    with pytest.raises(BilateralLoggerError):
        record_nurse_decision("case_fsync_fail", "approve", "Evidence supports approval.")


# ---------------------------------------------------------------------------
# Integration test — skipped in unit mode
# ---------------------------------------------------------------------------

@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="live CLI"
)
def test_pipeline_end_to_end_clean_case():
    """
    Load case_0001.json and run the full pipeline.
    Requires live Claude CLI — skipped in unit mode.
    """
    fixtures_dir = pathlib.Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "submissions"
    submission_file = fixtures_dir / "case_0001.json"
    submission = json.loads(submission_file.read_text(encoding="utf-8"))

    result = run_pipeline(submission)

    assert result.status == "completed"
    assert result.determination is not None
    assert result.determination["status"] == "pending_nurse_review"
    assert "reasoning_brief" in result.determination
