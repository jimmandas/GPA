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
