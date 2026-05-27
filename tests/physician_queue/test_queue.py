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


class TestBilateralLoggerEmission:
    """
    record_action must write a physician_action_record to the bilateral
    logger so per-case decision_log JSONL has the full audit lineage.
    """

    def test_record_action_writes_physician_action_record(self, tmp_path, isolate_bilateral_logger):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        q.record_action(
            "case_0001",
            PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="all criteria met",
            guideline_citation="NCCN-NSCLC-SURV-1",
        )

        log_file = isolate_bilateral_logger._log_dir / "case_0001.jsonl"
        assert log_file.exists(), "bilateral logger must write to case_id JSONL"
        records = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        physician_records = [r for r in records if r.get("type") == "physician_action_record"]
        assert len(physician_records) == 1
        rec = physician_records[0]
        assert rec["case_id"] == "case_0001"
        assert rec["action"] == "approve"
        assert rec["physician_id"] == "dr_smith"
        assert rec["clinical_basis"] == "all criteria met"
        assert rec["guideline_citation"] == "NCCN-NSCLC-SURV-1"
        assert rec["queue_state_after"] == "completed"
        assert rec["at"]

    def test_record_action_deny_log_includes_evidence_gaps(self, tmp_path, isolate_bilateral_logger):
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")
        q.record_action(
            "case_0001",
            PhysicianAction.DENY,
            physician_id="dr_smith",
            clinical_basis="staging not documented",
            guideline_citation="NCCN-NSCLC-SURV-2",
            evidence_gaps=["missing pathology report"],
            rationale="See physician note.",
        )

        log_file = isolate_bilateral_logger._log_dir / "case_0001.jsonl"
        records = [json.loads(line) for line in log_file.read_text().splitlines() if line.strip()]
        rec = next(r for r in records if r.get("type") == "physician_action_record")
        assert rec["action"] == "deny"
        assert rec["evidence_gaps"] == ["missing pathology report"]
        assert rec["rationale"] == "See physician note."
        assert rec["queue_state_after"] == "completed"

    def test_logger_failure_blocks_state_update(self, tmp_path, monkeypatch):
        """Write-before-emit: if the bilateral logger fails, queue state stays unchanged."""
        from logs.bilateral_logger import BilateralLogger, BilateralLoggerError

        class FailingLogger(BilateralLogger):
            def commit(self, case_id, record):
                raise BilateralLoggerError(case_id, "test_failure", "simulated fsync failure")

        failing_logger = FailingLogger(tmp_path / "failing_log", tmp_path / "failures.jsonl")
        q = _new_queue(tmp_path)
        q.enqueue("case_0001", "test")

        with pytest.raises(BilateralLoggerError):
            q.record_action(
                "case_0001",
                PhysicianAction.APPROVE,
                physician_id="dr_smith",
                clinical_basis="ok",
                guideline_citation="NCCN-NSCLC-SURV-1",
                logger=failing_logger,
            )

        # Queue state.json must NOT have been modified — case still pending
        entry = q.get("case_0001")
        assert entry.state == QueueState.PENDING
        raw = json.loads((tmp_path / "state.json").read_text())
        assert len(raw["actions"]) == 0
