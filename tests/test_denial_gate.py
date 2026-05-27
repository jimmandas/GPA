"""
Tests for the Denial Gate (gates/denial.py).

Covers MVP "block" mode (default) AND Phase 2 "route" mode that unlocks
denial as a path through the gate when a PhysicianQueue has a recorded
DENY action for the case.
"""

import pytest
from gates.denial import check, DenialAttemptError
from physician_queue.queue import FilePhysicianQueue, PhysicianAction


class TestDenialGateMVPBlockMode:
    """Default mode — denial always raises. Same as Phase 1 behavior."""

    def test_passes_approve(self):
        check({"path": "approve"})

    def test_passes_escalate(self):
        check({"path": "escalate"})

    def test_passes_pend(self):
        check({"path": "pend"})

    def test_raises_on_deny(self):
        with pytest.raises(DenialAttemptError):
            check({"path": "deny"})

    def test_raises_on_unknown_path(self):
        with pytest.raises(DenialAttemptError):
            check({"path": "auto_approve"})

    def test_raises_on_missing_path_key(self):
        with pytest.raises(ValueError):
            check({})

    def test_denial_attempt_error_has_path(self):
        with pytest.raises(DenialAttemptError) as exc_info:
            check({"path": "deny"})
        assert exc_info.value.path == "deny"


class TestDenialGateRouteModeBasic:
    """DENIAL_GATE_MODE=route — denial is permitted only with physician record."""

    def test_route_mode_still_allows_base_paths(self, monkeypatch):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        check({"path": "approve"})
        check({"path": "escalate"})
        check({"path": "pend"})

    def test_route_mode_still_raises_for_invalid_path(self, monkeypatch):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        with pytest.raises(DenialAttemptError):
            check({"path": "auto_approve"})

    def test_route_mode_deny_without_queue_raises(self, monkeypatch):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        with pytest.raises(DenialAttemptError, match="requires a PhysicianQueue"):
            check({"path": "deny", "case_id": "case_0001"})

    def test_route_mode_deny_without_case_id_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        q = FilePhysicianQueue(tmp_path / "state.json")
        with pytest.raises(DenialAttemptError, match="requires case_id"):
            check({"path": "deny"}, physician_queue=q)

    def test_route_mode_deny_without_queue_entry_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        q = FilePhysicianQueue(tmp_path / "state.json")
        # No enqueue happened
        with pytest.raises(DenialAttemptError, match="no physician queue entry"):
            check({"path": "deny", "case_id": "case_0001"}, physician_queue=q)

    def test_route_mode_deny_without_physician_action_raises(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        q = FilePhysicianQueue(tmp_path / "state.json")
        q.enqueue("case_0001", reason="nurse_escalated")
        # Entry exists but no physician DENY action recorded
        with pytest.raises(DenialAttemptError, match="no recorded physician DENY action"):
            check({"path": "deny", "case_id": "case_0001"}, physician_queue=q)


class TestDenialGateRouteModeWithPhysicianAction:
    """The whole reason for route mode: physician-authored denials get through."""

    def test_route_mode_deny_with_physician_action_passes(self, monkeypatch, tmp_path):
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        q = FilePhysicianQueue(tmp_path / "state.json")
        q.enqueue("case_0001", reason="ai_brief_flags_unmet_criteria")
        q.record_action(
            case_id="case_0001",
            action=PhysicianAction.DENY,
            physician_id="dr_smith",
            clinical_basis="pathologic staging not documented; SURV-2 unmet",
            guideline_citation="NCCN-NSCLC-SURV-2",
            evidence_gaps=["missing pathology report from initial staging"],
        )
        # Should NOT raise — physician has acted
        check({"path": "deny", "case_id": "case_0001"}, physician_queue=q)

    def test_route_mode_approve_action_does_not_authorize_deny(self, monkeypatch, tmp_path):
        """Physician approve record must not satisfy the deny check."""
        monkeypatch.setenv("DENIAL_GATE_MODE", "route")
        q = FilePhysicianQueue(tmp_path / "state.json")
        q.enqueue("case_0001", reason="test")
        q.record_action(
            case_id="case_0001",
            action=PhysicianAction.APPROVE,  # not DENY
            physician_id="dr_smith",
            clinical_basis="criteria met after review",
            guideline_citation="NCCN-NSCLC-SURV-1",
        )
        with pytest.raises(DenialAttemptError, match="no recorded physician DENY action"):
            check({"path": "deny", "case_id": "case_0001"}, physician_queue=q)
