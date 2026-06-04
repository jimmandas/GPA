"""
Tests for the Phase 3a case dashboard: JSONLCaseStore + /api/v1/cases endpoints.

The dashboard goes through the CaseStore abstraction so the same UI works on
JSONL (default) or MongoDB. These tests cover the JSONL read path and the
endpoints' chain + signature verification annotations.
"""

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from api.main import app
from logs.bilateral_logger import BilateralLogger
from persistence.jsonl_store import JSONLCaseStore

client = TestClient(app)


# ---------------------------------------------------------------------------
# JSONLCaseStore — read path over a tmp decision_log
# ---------------------------------------------------------------------------

@pytest.fixture
def populated_store(tmp_path):
    """A JSONLCaseStore over a tmp dir with two signed cases committed."""
    log_dir = tmp_path / "decision_log"
    failures = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures)

    # case_aaa: agent event then nurse approval
    logger.commit("case_aaa", {"type": "agent_event", "agent": "evidence_summarizer", "at": "2026-06-04T10:00:00Z"})
    logger.commit("case_aaa", {"type": "nurse_action_record", "nurse_decision": "approve", "at": "2026-06-04T10:05:00Z"})

    # case_bbb: agent event then escalation
    logger.commit("case_bbb", {"type": "agent_event", "agent": "policy_mapper", "at": "2026-06-04T11:00:00Z"})
    logger.commit("case_bbb", {"type": "nurse_action_record", "nurse_decision": "escalate", "at": "2026-06-04T11:05:00Z"})

    return JSONLCaseStore(log_dir)


def test_jsonl_get_case_records_order(populated_store):
    records = populated_store.get_case_records("case_aaa")
    assert len(records) == 2
    assert records[0]["type"] == "agent_event"
    assert records[1]["type"] == "nurse_action_record"
    # Records carry chain + signature provenance
    assert records[0]["prev_record_hash"].startswith("sha256:")
    assert "jws_signature" in records[0]


def test_jsonl_get_case_records_missing(populated_store):
    assert populated_store.get_case_records("nope") == []


def test_jsonl_derives_status(populated_store):
    assert populated_store.get_case_summary("case_aaa")["status"] == "approved"
    assert populated_store.get_case_summary("case_bbb")["status"] == "escalated"


def test_jsonl_summary_has_no_records(populated_store):
    summary = populated_store.get_case_summary("case_aaa")
    assert "records" not in summary
    assert summary["record_count"] == 2
    assert summary["case_id"] == "case_aaa"


def test_jsonl_find_by_status(populated_store):
    approved = populated_store.find_by_status("approved")
    escalated = populated_store.find_by_status("escalated")
    assert [c["case_id"] for c in approved] == ["case_aaa"]
    assert [c["case_id"] for c in escalated] == ["case_bbb"]


def test_jsonl_list_all(populated_store):
    cases = populated_store.list_all()
    assert {c["case_id"] for c in cases} == {"case_aaa", "case_bbb"}


def test_jsonl_mark_exported_is_noop(populated_store):
    # file IS the archive; mark_exported must not raise
    assert populated_store.mark_exported("case_aaa") is None


# ---------------------------------------------------------------------------
# Endpoints — point the singleton at a tmp store
# ---------------------------------------------------------------------------

@pytest.fixture
def api_store(populated_store, monkeypatch):
    """Force get_case_store() to return our populated tmp store."""
    import persistence
    monkeypatch.setattr(persistence, "_case_store", populated_store)
    return populated_store


def test_list_cases_endpoint(api_store):
    res = client.get("/api/v1/cases")
    assert res.status_code == 200
    data = res.json()
    assert data["backend"] == "JSONLCaseStore"
    assert data["total"] == 2
    assert {c["case_id"] for c in data["cases"]} == {"case_aaa", "case_bbb"}


def test_list_cases_status_filter(api_store):
    res = client.get("/api/v1/cases?status=escalated")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert data["cases"][0]["case_id"] == "case_bbb"


def test_case_audit_endpoint_verifies(api_store):
    res = client.get("/api/v1/cases/case_aaa/audit")
    assert res.status_code == 200
    data = res.json()
    assert data["chain_verified"] is True
    assert data["signatures_present"] is True
    assert data["record_count"] == 2
    # Every record should report a verified signature
    assert all(r["signature_verified"] is True for r in data["records"])


def test_case_audit_endpoint_404(api_store):
    res = client.get("/api/v1/cases/does_not_exist/audit")
    assert res.status_code == 404


def test_case_audit_detects_tampering(api_store, populated_store):
    """Mutating a committed record must flip chain_verified to False."""
    log = populated_store.log_dir / "case_aaa.jsonl"
    lines = log.read_text().splitlines()
    records = [json.loads(l) for l in lines]
    records[0]["agent"] = "TAMPERED"  # mutate content, leave signature
    log.write_text("\n".join(json.dumps(r, separators=(",", ":")) for r in records) + "\n")

    res = client.get("/api/v1/cases/case_aaa/audit")
    assert res.status_code == 200
    assert res.json()["chain_verified"] is False
