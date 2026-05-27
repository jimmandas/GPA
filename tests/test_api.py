"""
Tests for the GPA v4 Provider Explanation API (api/main.py).
"""

import json
import os
import pathlib
import pytest

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

# ---------------------------------------------------------------------------
# Fixture paths
# ---------------------------------------------------------------------------

_FIXTURE_DIR = pathlib.Path(__file__).resolve().parents[1] / "tools" / "fixtures" / "submissions"
_CASE_0001 = _FIXTURE_DIR / "case_0001.json"

SKIP_INTEGRATION = pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="Integration tests skipped (SKIP_INTEGRATION_TESTS=1)"
)

# ---------------------------------------------------------------------------
# Minimal valid body (used as base for mutated tests)
# ---------------------------------------------------------------------------

MINIMAL_VALID_BODY = {
    "case_id": "case_test",
    "submitted_at": "2026-05-25T00:00:00Z",
    "patient": {"patient_id": "pt_anon_test", "age": 45, "sex": "M"},
    "imaging_request": {"modality": "CT", "body_region": "chest", "with_contrast": False},
    "clinical_indication": {"diagnosis_code": "Z00.00", "diagnosis_text": "Routine checkup"},
    "policy_id": "test_policy_v1",
}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


# ---------------------------------------------------------------------------
# /decide — validation failures
# ---------------------------------------------------------------------------

def test_decide_rejects_missing_case_id():
    body = {k: v for k, v in MINIMAL_VALID_BODY.items() if k != "case_id"}
    response = client.post("/api/v1/pa/decide", json=body)
    assert response.status_code == 422


def test_decide_rejects_missing_policy_id():
    body = {k: v for k, v in MINIMAL_VALID_BODY.items() if k != "policy_id"}
    response = client.post("/api/v1/pa/decide", json=body)
    assert response.status_code == 422


def test_decide_rejects_empty_case_id():
    body = {**MINIMAL_VALID_BODY, "case_id": ""}
    response = client.post("/api/v1/pa/decide", json=body)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# /decide — Admission Gate blocks incomplete submission
# ---------------------------------------------------------------------------

def test_decide_admission_gate_blocks_incomplete_submission():
    """
    imaging_request missing modality and body_region → Admission Gate escalates.
    All top-level required fields are present so Pydantic passes, but the gate fails.
    """
    body = {
        **MINIMAL_VALID_BODY,
        "imaging_request": {"with_contrast": False},  # missing modality and body_region
    }
    response = client.post("/api/v1/pa/decide", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "escalated"


# ---------------------------------------------------------------------------
# /decide — full pipeline (integration, skipped in unit CI)
# ---------------------------------------------------------------------------

@SKIP_INTEGRATION
def test_decide_valid_submission_returns_pending_review():
    with open(_CASE_0001) as f:
        submission = json.load(f)
    response = client.post("/api/v1/pa/decide", json=submission)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "completed"
    assert data["determination"]["status"] == "pending_nurse_review"


# ---------------------------------------------------------------------------
# /nurse-decision — happy paths
# ---------------------------------------------------------------------------

def test_nurse_decision_approve():
    body = {"case_id": "case_test", "action": "approve", "rationale": "Meets criteria."}
    response = client.post("/api/v1/pa/nurse-decision", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["determination"]["path"] == "approve"


def test_nurse_decision_escalate():
    body = {"case_id": "case_test", "action": "escalate", "rationale": "Needs physician review."}
    response = client.post("/api/v1/pa/nurse-decision", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["determination"]["path"] == "escalate"


def test_nurse_decision_pend():
    body = {"case_id": "case_test", "action": "pend", "rationale": "Awaiting records."}
    response = client.post("/api/v1/pa/nurse-decision", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["determination"]["path"] == "pend"


# ---------------------------------------------------------------------------
# /nurse-decision — validation failures
# ---------------------------------------------------------------------------

def test_nurse_decision_rejects_deny():
    """Pydantic pattern validation blocks 'deny' before it reaches the gate."""
    body = {"case_id": "case_test", "action": "deny", "rationale": "Denied."}
    response = client.post("/api/v1/pa/nurse-decision", json=body)
    assert response.status_code == 422


def test_nurse_decision_rejects_empty_rationale():
    body = {"case_id": "case_test", "action": "approve", "rationale": ""}
    response = client.post("/api/v1/pa/nurse-decision", json=body)
    assert response.status_code == 422


def test_nurse_decision_rejects_whitespace_rationale():
    """
    Pydantic min_length=1 passes for whitespace-only strings.
    record_nurse_decision raises ValueError, which the endpoint maps to 422.
    """
    body = {"case_id": "case_test", "action": "approve", "rationale": "   "}
    response = client.post("/api/v1/pa/nurse-decision", json=body)
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# Nurse queue + audit endpoints (Loom-readiness, 2026-05-27)
# ---------------------------------------------------------------------------

def test_nurse_queue_lists_case_fixtures():
    response = client.get("/api/v1/nurse/queue")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "cases" in data
    assert data["total"] >= 1
    case_ids = [c["case_id"] for c in data["cases"]]
    assert "case_0001" in case_ids


def test_nurse_case_returns_submission_for_known_fixture():
    response = client.get("/api/v1/nurse/case/case_0001")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "case_0001"
    assert "submission" in data
    assert data["submission"]["case_id"] == "case_0001"
    assert "audit_log_ref" in data


def test_nurse_case_404_for_unknown_case():
    response = client.get("/api/v1/nurse/case/case_does_not_exist")
    assert response.status_code == 404


def test_audit_cases_lists_logs():
    response = client.get("/api/v1/audit/cases")
    assert response.status_code == 200
    data = response.json()
    assert "total" in data
    assert "cases" in data
    # decision_log/ holds many fixture logs from prior eval runs


def test_audit_case_404_for_unknown_case():
    response = client.get("/api/v1/audit/case/case_truly_does_not_exist_xyz123")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Physician peer review endpoints (Phase 2 Week 11)
# ---------------------------------------------------------------------------

@pytest.fixture
def isolated_queue(tmp_path, monkeypatch):
    """Swap the global physician queue singleton + bilateral logger for tmp paths."""
    from physician_queue import queue as queue_mod
    from physician_queue.queue import FilePhysicianQueue
    from logs import bilateral_logger as bl_mod
    from logs.bilateral_logger import BilateralLogger

    tmp_queue = FilePhysicianQueue(tmp_path / "state.json")
    tmp_logger = BilateralLogger(tmp_path / "phys_logs", tmp_path / "failures.jsonl")
    monkeypatch.setattr(queue_mod, "_DEFAULT_QUEUE", tmp_queue)
    monkeypatch.setattr(bl_mod, "_DEFAULT_LOGGER", tmp_logger)
    return tmp_queue


def test_physician_queue_empty_by_default(isolated_queue):
    response = client.get("/api/v1/physician/queue")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_count"] == 0
    assert data["entries"] == []


def test_physician_queue_lists_enqueued_cases(isolated_queue):
    isolated_queue.enqueue("case_alpha", reason="nurse_escalated", ai_brief_summary="surveillance CT")
    isolated_queue.enqueue("case_beta", reason="ai_brief_flags_unmet_criteria")

    response = client.get("/api/v1/physician/queue")
    assert response.status_code == 200
    data = response.json()
    assert data["pending_count"] == 2
    case_ids = [e["case_id"] for e in data["entries"]]
    assert "case_alpha" in case_ids
    assert "case_beta" in case_ids


def test_physician_case_404_for_unknown_case(isolated_queue):
    response = client.get("/api/v1/physician/case/case_does_not_exist")
    assert response.status_code == 404


def test_physician_case_returns_entry_details(isolated_queue):
    isolated_queue.enqueue(
        "case_gamma",
        reason="nurse_escalated",
        ai_brief_summary="Restaging MRI; 2 unmet criteria flagged.",
        nurse_note="Patient declined oral contrast; recommend physician review.",
    )

    response = client.get("/api/v1/physician/case/case_gamma")
    assert response.status_code == 200
    data = response.json()
    assert data["case_id"] == "case_gamma"
    assert data["state"] == "pending"
    assert "Restaging MRI" in data["ai_brief_summary"]
    assert "oral contrast" in data["nurse_note"]
    assert data["audit_log_ref"] == "decision_log/case_gamma.jsonl"


def test_physician_action_approve_records_to_queue(isolated_queue):
    isolated_queue.enqueue("case_delta", reason="test")
    body = {
        "case_id": "case_delta",
        "action": "approve",
        "physician_id": "dr_smith",
        "clinical_basis": "Criteria met; surveillance interval appropriate.",
        "guideline_citation": "NCCN-NSCLC-SURV-1",
    }
    response = client.post("/api/v1/physician/action", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "approve"
    assert data["physician_id"] == "dr_smith"
    assert data["queue_state_after"] == "completed"


def test_physician_action_deny_requires_evidence_gaps(isolated_queue):
    """DENY without evidence_gaps fails at the FilePhysicianQueue boundary (422)."""
    isolated_queue.enqueue("case_epsilon", reason="test")
    body = {
        "case_id": "case_epsilon",
        "action": "deny",
        "physician_id": "dr_smith",
        "clinical_basis": "Staging not documented",
        "guideline_citation": "NCCN-NSCLC-SURV-2",
        "evidence_gaps": [],
    }
    response = client.post("/api/v1/physician/action", json=body)
    assert response.status_code == 422
    assert "evidence_gaps" in response.json()["detail"]


def test_physician_action_deny_with_evidence_gaps_succeeds(isolated_queue):
    isolated_queue.enqueue("case_zeta", reason="test")
    body = {
        "case_id": "case_zeta",
        "action": "deny",
        "physician_id": "dr_smith",
        "clinical_basis": "Staging not documented; criteria unmet.",
        "guideline_citation": "NCCN-NSCLC-SURV-2",
        "evidence_gaps": ["Missing initial pathology report"],
        "rationale": "Cannot determine staging without pathology.",
    }
    response = client.post("/api/v1/physician/action", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "deny"
    assert data["queue_state_after"] == "completed"


def test_physician_action_request_more_returns_to_nurse(isolated_queue):
    isolated_queue.enqueue("case_eta", reason="test")
    body = {
        "case_id": "case_eta",
        "action": "request_additional_evidence",
        "physician_id": "dr_smith",
        "clinical_basis": "Need 90-day prior CT confirmation.",
        "guideline_citation": "NCCN-NSCLC-SURV-1",
    }
    response = client.post("/api/v1/physician/action", json=body)
    assert response.status_code == 200
    data = response.json()
    assert data["queue_state_after"] == "returned"


def test_physician_action_rejects_unknown_action(isolated_queue):
    body = {
        "case_id": "case_theta",
        "action": "burn_it_down",
        "physician_id": "dr_smith",
        "clinical_basis": "x",
        "guideline_citation": "x",
    }
    response = client.post("/api/v1/physician/action", json=body)
    # Pydantic pattern validator catches this at the request layer (422)
    assert response.status_code == 422


def test_physician_action_on_unqueued_case_fails(isolated_queue):
    body = {
        "case_id": "case_not_queued",
        "action": "approve",
        "physician_id": "dr_smith",
        "clinical_basis": "ok",
        "guideline_citation": "NCCN-NSCLC-SURV-1",
    }
    response = client.post("/api/v1/physician/action", json=body)
    assert response.status_code == 422
