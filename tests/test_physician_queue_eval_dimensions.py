"""
Tests for the two physician-queue eval dimensions added per Phase 2 §12:
  - score_physician_queue_routing_accuracy
  - score_physician_rationale_compliance

Both dims return N/A until route mode is exercised in the eval; these tests
populate fixtures directly to exercise the scoring logic.
"""

import pytest

from eval.dimensions import (
    score_physician_queue_routing_accuracy,
    score_physician_rationale_compliance,
)
from physician_queue.queue import FilePhysicianQueue, PhysicianAction


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def isolate_logger(tmp_path, monkeypatch):
    """Redirect bilateral logger singleton so record_action doesn't dirty real logs."""
    from logs import bilateral_logger as bl_module
    from logs.bilateral_logger import BilateralLogger
    test_logger = BilateralLogger(tmp_path / "test_logs", tmp_path / "failures.jsonl")
    monkeypatch.setattr(bl_module, "_DEFAULT_LOGGER", test_logger)
    return test_logger


def _case(case_id: str, expected_routing: bool | None = None) -> dict:
    gt: dict = {}
    if expected_routing is not None:
        gt["expected_physician_routing"] = expected_routing
    return {"case_id": case_id, "ground_truth": gt}


# ---------------------------------------------------------------------------
# physician_queue_routing_accuracy
# ---------------------------------------------------------------------------

class TestRoutingAccuracyNAPaths:
    def test_no_queue_returns_na(self):
        score = score_physician_queue_routing_accuracy(
            cases=[_case("c1", True)], physician_queue=None
        )
        assert score.score is None
        assert score.passed is None
        assert "No PhysicianQueue" in score.notes

    def test_no_ground_truth_field_returns_na(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        score = score_physician_queue_routing_accuracy(
            cases=[_case("c1"), _case("c2")], physician_queue=q
        )
        assert score.score is None
        assert "expected_physician_routing" in score.notes


class TestRoutingAccuracyScoring:
    def test_all_correct(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        q.enqueue("c1", "test")  # expected=True, actually routed
        # c2: expected=False, not routed → also correct

        cases = [_case("c1", True), _case("c2", False)]
        score = score_physician_queue_routing_accuracy(cases=cases, physician_queue=q)
        assert score.score == 1.0
        assert score.passed is True

    def test_misrouted_case_flagged(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        # c1: expected=True but NOT in queue → misrouted
        # c2: expected=False and not in queue → correct
        cases = [_case("c1", True), _case("c2", False)]
        score = score_physician_queue_routing_accuracy(cases=cases, physician_queue=q)
        assert score.score == 0.5
        assert score.passed is False
        assert "c1" in score.notes

    def test_false_positive_routing_flagged(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        q.enqueue("c_extra", "test")  # routed but no ground truth says it should be
        # c1: expected=False but actually routed → incorrect (false positive)
        q.enqueue("c1", "test")
        cases = [_case("c1", False)]
        score = score_physician_queue_routing_accuracy(cases=cases, physician_queue=q)
        assert score.score == 0.0
        assert score.passed is False


# ---------------------------------------------------------------------------
# physician_rationale_compliance
# ---------------------------------------------------------------------------

class TestRationaleComplianceNAPaths:
    def test_no_queue_returns_na(self):
        score = score_physician_rationale_compliance(physician_queue=None)
        assert score.score is None
        assert score.passed is None

    def test_empty_queue_returns_na(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        score = score_physician_rationale_compliance(physician_queue=q)
        assert score.score is None
        assert "no recorded physician actions" in score.notes


class TestRationaleComplianceScoring:
    def _seed_compliant_action(self, q, case_id="c1", action=PhysicianAction.APPROVE):
        q.enqueue(case_id, "test")
        q.record_action(
            case_id=case_id,
            action=action,
            physician_id="dr_smith",
            clinical_basis="All NCCN criteria met after detailed chart review.",
            guideline_citation="NCCN-NSCLC-SURV-1",
            evidence_gaps=["Initial pathology report confirms staging."] if action == PhysicianAction.DENY else [],
        )

    def test_one_compliant_action(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        self._seed_compliant_action(q)
        score = score_physician_rationale_compliance(physician_queue=q)
        assert score.score == 1.0
        assert score.passed is True

    def test_short_clinical_basis_flagged(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        q.enqueue("c1", "test")
        q.record_action(
            case_id="c1",
            action=PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="ok",  # too short, fails compliance
            guideline_citation="NCCN-NSCLC-SURV-1",
        )
        score = score_physician_rationale_compliance(physician_queue=q)
        assert score.score == 0.0
        assert score.passed is False
        assert "clinical_basis" in score.notes

    def test_citation_without_separator_flagged(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        q.enqueue("c1", "test")
        q.record_action(
            case_id="c1",
            action=PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="All NCCN criteria met after detailed chart review.",
            guideline_citation="NCCNguidelineX",  # no separator
        )
        score = score_physician_rationale_compliance(physician_queue=q)
        assert score.score == 0.0
        assert "citation_no_structured_id" in score.notes

    def test_deny_with_short_evidence_gap_flagged(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        q.enqueue("c1", "test")
        q.record_action(
            case_id="c1",
            action=PhysicianAction.DENY,
            physician_id="dr_smith",
            clinical_basis="Criteria unmet; staging not documented in record.",
            guideline_citation="NCCN-NSCLC-SURV-2",
            evidence_gaps=["short"],  # too short
        )
        score = score_physician_rationale_compliance(physician_queue=q)
        assert score.score == 0.0
        assert "evidence_gap_short" in score.notes

    def test_mixed_compliance(self, tmp_path):
        q = FilePhysicianQueue(tmp_path / "s.json")
        self._seed_compliant_action(q, case_id="c1")
        self._seed_compliant_action(q, case_id="c2")
        # Add a non-compliant one
        q.enqueue("c3", "test")
        q.record_action(
            case_id="c3",
            action=PhysicianAction.APPROVE,
            physician_id="dr_smith",
            clinical_basis="ok",  # short → non-compliant
            guideline_citation="NCCN-X-Y",
        )
        score = score_physician_rationale_compliance(physician_queue=q)
        assert abs(score.score - (2 / 3)) < 1e-9
        assert score.passed is False  # 0.67 < 0.95
