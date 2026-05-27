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


def test_record_nurse_decision_escalate_enqueues_to_physician_queue(monkeypatch, tmp_path):
    """
    Phase 2 handoff: nurse escalate action MUST place the case on the physician queue
    so the physician workflow has visible work.
    """
    from physician_queue.queue import FilePhysicianQueue
    from physician_queue import queue as queue_mod

    _patch_logger(monkeypatch, tmp_path)

    # Swap the default physician queue singleton to a tmp instance
    tmp_queue = FilePhysicianQueue(tmp_path / "phys_state.json")
    monkeypatch.setattr(queue_mod, "_DEFAULT_QUEUE", tmp_queue)

    case_id = "case_escalation_test"
    result = record_nurse_decision(
        case_id,
        "escalate",
        "Patient comorbidities make this judgment-intensive; needs physician review.",
    )
    assert result.status == "completed"
    assert result.determination["path"] == "escalate"

    # The case should now be on the physician queue
    entry = tmp_queue.get(case_id)
    assert entry is not None, "escalate must enqueue to physician queue"
    assert entry.reason == "nurse_escalated"
    assert "comorbidities" in entry.nurse_note


def test_record_nurse_decision_escalate_is_idempotent(monkeypatch, tmp_path):
    """Re-clicking escalate (double-submit) must not raise duplicate_pending."""
    from physician_queue.queue import FilePhysicianQueue
    from physician_queue import queue as queue_mod

    _patch_logger(monkeypatch, tmp_path)
    tmp_queue = FilePhysicianQueue(tmp_path / "phys_state.json")
    monkeypatch.setattr(queue_mod, "_DEFAULT_QUEUE", tmp_queue)

    case_id = "case_double_escalate"
    record_nurse_decision(case_id, "escalate", "first")
    # Second call must not raise — silently no-op on the queue
    result = record_nurse_decision(case_id, "escalate", "second")
    assert result.status == "completed"


def test_record_nurse_decision_approve_does_not_enqueue(monkeypatch, tmp_path):
    """approve / pend must NOT touch the physician queue."""
    from physician_queue.queue import FilePhysicianQueue
    from physician_queue import queue as queue_mod

    _patch_logger(monkeypatch, tmp_path)
    tmp_queue = FilePhysicianQueue(tmp_path / "phys_state.json")
    monkeypatch.setattr(queue_mod, "_DEFAULT_QUEUE", tmp_queue)

    record_nurse_decision("case_approved", "approve", "All criteria met.")
    record_nurse_decision("case_pended", "pend", "Awaiting additional records.")

    assert tmp_queue.get("case_approved") is None
    assert tmp_queue.get("case_pended") is None


def test_record_nurse_decision_deny_with_physician_queue(monkeypatch, tmp_path):
    """
    Route mode: denial is permitted when a PhysicianQueue has a recorded DENY action.
    """
    from physician_queue.queue import FilePhysicianQueue, PhysicianAction
    from logs.bilateral_logger import BilateralLogger

    monkeypatch.setenv("DENIAL_GATE_MODE", "route")
    _patch_logger(monkeypatch, tmp_path)

    queue_dir = tmp_path / "queue"
    queue_dir.mkdir()
    physician_queue = FilePhysicianQueue(queue_dir / "state.json")
    tmp_log = BilateralLogger(tmp_path / "physician_log", tmp_path / "phys_failures.jsonl")

    case_id = "case_physician_deny"
    physician_queue.enqueue(case_id, reason="ai_brief_flags_unmet_criteria")
    physician_queue.record_action(
        case_id=case_id,
        action=PhysicianAction.DENY,
        physician_id="dr_smith",
        clinical_basis="pathologic staging not documented",
        guideline_citation="NCCN-NSCLC-SURV-2",
        evidence_gaps=["missing pathology report"],
        logger=tmp_log,
    )

    # Should NOT raise — physician has acted
    result = record_nurse_decision(
        case_id,
        "deny",
        "Physician review required; clinical criteria unmet.",
        physician_queue=physician_queue,
    )
    assert result.status == "completed"
    assert result.determination["path"] == "deny"


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
