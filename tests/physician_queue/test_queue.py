"""
Tests for physician_queue/queue.py — PhysicianQueue interface + FilePhysicianQueue.

Every test uses a tmp_path-scoped queue so no test touches real state files.
"""

import json
import pathlib

import pytest

from physician_queue.queue import (
    PhysicianQueue,
    FilePhysicianQueue,
    FilePhysicianQueueError,
    QueueEntry,
    QueueState,
    PhysicianAction,
    ActionRecord,
)


def _new_queue(tmp_path: pathlib.Path) -> FilePhysicianQueue:
    return FilePhysicianQueue(tmp_path / "state.json")


class TestQueueInterface:
    def test_abstract_class_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            PhysicianQueue()

    def test_file_queue_is_a_physician_queue(self, tmp_path):
        q = _new_queue(tmp_path)
        assert isinstance(q, PhysicianQueue)


class TestEnqueue:
    def test_basic_enqueue_creates_pending_entry(self, tmp_path):
        q = _new_queue(tmp_path)
        entry = q.enqueue(
            case_id="case_0001",
            reason="nurse_escalated",
            ai_brief_summary="surveillance CT, criteria met",
        )
        assert isinstance(entry, QueueEntry)
        assert entry.case_id == "case_0001"
        assert entry.state == QueueState.PENDING
        assert entry.enqueued_at  # timestamp populated

    def test_enqueue_persists_to_disk(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        # Re-read from disk via a fresh instance
        q2 = _new_queue(tmp_path)
        pending = q2.list_pending()
        assert len(pending) == 1
        assert pending[0].case_id == "case_0001"

    def test_enqueue_rejects_empty_case_id(self, tmp_path):
        q = _new_queue(tmp_path)
        with pytest.raises(FilePhysicianQueueError, match="invalid_enqueue"):
            q.enqueue("", "test")

    def test_enqueue_rejects_empty_reason(self, tmp_path):
        q = _new_queue(tmp_path)
        with pytest.raises(FilePhysicianQueueError, match="invalid_enqueue"):
            q.enqueue("case_0001", "   ")

    def test_enqueue_rejects_duplicate_pending(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "first")
        with pytest.raises(FilePhysicianQueueError, match="duplicate_pending"):
            q.enqueue("case_0001", "second")


class TestListPending:
    def test_list_pending_returns_only_pending(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test_a")
        q.enqueue("case_0002", "test_b")
        q.record_action(
            "case_0001",
            PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="criteria all met",
            guideline_citation="NCCN-NSCLC-SURV-1",
        )
        pending = q.list_pending()
        assert len(pending) == 1
        assert pending[0].case_id == "case_0002"

    def test_list_pending_empty_when_no_entries(self, tmp_path):
        q = _new_queue(tmp_path)
        assert q.list_pending() == []


class TestGet:
    def test_get_returns_entry_for_known_case(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        entry = q.get("case_0001")
        assert entry is not None
        assert entry.case_id == "case_0001"

    def test_get_returns_none_for_unknown_case(self, tmp_path):
        q = _new_queue(tmp_path)
        assert q.get("nonexistent") is None


class TestRecordAction:
    def test_approve_action_completes_case(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        record = q.record_action(
            "case_0001",
            PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="criteria met",
            guideline_citation="NCCN-NSCLC-SURV-1",
        )
        assert isinstance(record, ActionRecord)
        assert record.action == PhysicianAction.APPROVE
        assert record.recorded_at
        # Entry transitioned to COMPLETED
        entry = q.get("case_0001")
        assert entry.state == QueueState.COMPLETED

    def test_deny_action_requires_evidence_gaps(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        with pytest.raises(FilePhysicianQueueError, match="deny_requires_evidence_gaps"):
            q.record_action(
                "case_0001",
                PhysicianAction.DENY,
                physician_id="dr_smith",
                clinical_basis="criteria unmet",
                guideline_citation="NCCN-NSCLC-SURV-2",
                evidence_gaps=[],  # empty list — rejected
            )

    def test_deny_action_with_evidence_gaps_succeeds(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        record = q.record_action(
            "case_0001",
            PhysicianAction.DENY,
            physician_id="dr_smith",
            clinical_basis="pathologic staging not documented",
            guideline_citation="NCCN-NSCLC-SURV-2",
            evidence_gaps=["missing pathologic staging report"],
        )
        assert record.action == PhysicianAction.DENY
        assert record.evidence_gaps == ["missing pathologic staging report"]

    def test_request_additional_evidence_marks_returned(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        q.record_action(
            "case_0001",
            PhysicianAction.REQUEST_ADDITIONAL_EVIDENCE,
            physician_id="dr_smith",
            clinical_basis="need pathology report",
            guideline_citation="NCCN-NSCLC-SURV-2",
        )
        entry = q.get("case_0001")
        assert entry.state == QueueState.RETURNED

    def test_action_rejects_missing_physician_id(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        with pytest.raises(FilePhysicianQueueError, match="missing_physician_id"):
            q.record_action(
                "case_0001",
                PhysicianAction.APPROVE,
                physician_id="",
                clinical_basis="ok",
                guideline_citation="NCCN-NSCLC-SURV-1",
            )

    def test_action_rejects_missing_clinical_basis(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        with pytest.raises(FilePhysicianQueueError, match="missing_clinical_basis"):
            q.record_action(
                "case_0001",
                PhysicianAction.APPROVE,
                physician_id="dr_smith",
                clinical_basis="   ",
                guideline_citation="NCCN-NSCLC-SURV-1",
            )

    def test_action_rejects_missing_guideline_citation(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        with pytest.raises(FilePhysicianQueueError, match="missing_guideline_citation"):
            q.record_action(
                "case_0001",
                PhysicianAction.APPROVE,
                physician_id="dr_smith",
                clinical_basis="ok",
                guideline_citation="",
            )

    def test_action_on_unqueued_case_fails(self, tmp_path):
        q = _new_queue(tmp_path)
        with pytest.raises(FilePhysicianQueueError, match="case_not_in_queue"):
            q.record_action(
                "case_0001",
                PhysicianAction.APPROVE,
                physician_id="dr_smith",
                clinical_basis="ok",
                guideline_citation="NCCN-NSCLC-SURV-1",
            )


class TestStateFilePersistence:
    def test_state_file_is_valid_json_after_writes(self, tmp_path):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        q.record_action(
            "case_0001",
            PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="ok",
            guideline_citation="NCCN-NSCLC-SURV-1",
        )
        raw = json.loads((tmp_path / "state.json").read_text())
        assert "entries" in raw
        assert "actions" in raw
        assert len(raw["entries"]) == 1
        assert len(raw["actions"]) == 1

    def test_corrupt_state_file_raises_clearly(self, tmp_path):
        state_path = tmp_path / "state.json"
        state_path.write_text("not valid json {{{", encoding="utf-8")
        q = FilePhysicianQueue(state_path)
        with pytest.raises(FilePhysicianQueueError, match="corrupt_state"):
            q.list_pending()
