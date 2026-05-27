"""
Tests for gates/confidence.py — Phase 2 §12 / ADR-015 Confidence Gate.

Pass conditions:
  1. overall_signal != "ambiguous"
  2. count of criteria with status in {"ambiguous", "unmet"} <= threshold
"""

import pytest

from gates.confidence import check, ConfidenceResult, _DEFAULT_MAX_AMBIGUOUS_OR_UNMET


def _policy_map(signal="meets_criteria", criteria=None):
    return {
        "case_id": "c1",
        "overall_signal": signal,
        "criteria": criteria if criteria is not None else [],
    }


def _crit(status: str):
    return {"name": "test_criterion", "status": status, "evidence_ref": "x"}


class TestConfidenceGatePassPaths:
    def test_clean_case_passes(self):
        pm = _policy_map(signal="meets_criteria", criteria=[_crit("met"), _crit("met")])
        result = check(pm)
        assert isinstance(result, ConfidenceResult)
        assert result.passed is True
        assert result.violations == []
        assert result.ambiguous_or_unmet_count == 0

    def test_one_ambiguous_under_threshold_passes(self):
        """Default threshold = 2 ambiguous/unmet; one ambiguous passes."""
        pm = _policy_map(signal="meets_criteria", criteria=[_crit("met"), _crit("ambiguous")])
        result = check(pm)
        assert result.passed is True
        assert result.ambiguous_or_unmet_count == 1

    def test_two_ambiguous_at_threshold_passes(self):
        """Default threshold = 2; two ambiguous/unmet sits exactly AT threshold (allowed)."""
        pm = _policy_map(signal="meets_criteria", criteria=[_crit("ambiguous"), _crit("ambiguous")])
        result = check(pm)
        assert result.passed is True
        assert result.ambiguous_or_unmet_count == 2

    def test_does_not_meet_overall_signal_still_passes_when_unmet_under_threshold(self):
        """overall_signal=does_not_meet doesn't itself fail the gate."""
        pm = _policy_map(signal="does_not_meet", criteria=[_crit("unmet")])
        result = check(pm)
        assert result.passed is True
        assert result.signal == "does_not_meet"


class TestConfidenceGateFailPaths:
    def test_ambiguous_overall_signal_fails(self):
        pm = _policy_map(signal="ambiguous", criteria=[_crit("met")])
        result = check(pm)
        assert result.passed is False
        assert any("ambiguous" in v.lower() for v in result.violations)

    def test_three_ambiguous_exceeds_threshold(self):
        """Default threshold = 2; three ambiguous EXCEEDS it."""
        pm = _policy_map(
            signal="meets_criteria",
            criteria=[_crit("met"), _crit("ambiguous"), _crit("ambiguous"), _crit("ambiguous")],
        )
        result = check(pm)
        assert result.passed is False
        assert result.ambiguous_or_unmet_count == 3

    def test_two_ambiguous_one_unmet_exceeds_threshold(self):
        """3 ambiguous/unmet exceeds the default threshold of 2."""
        pm = _policy_map(
            signal="meets_criteria",
            criteria=[_crit("ambiguous"), _crit("ambiguous"), _crit("unmet")],
        )
        result = check(pm)
        assert result.passed is False
        assert result.ambiguous_or_unmet_count == 3

    def test_both_ambiguous_signal_and_count_violations_named(self):
        """3 ambiguous/unmet criteria + signal=='ambiguous' → both violations recorded."""
        pm = _policy_map(
            signal="ambiguous",
            criteria=[_crit("ambiguous"), _crit("ambiguous"), _crit("unmet")],
        )
        result = check(pm)
        assert result.passed is False
        # Both violations should be in the list
        assert any("ambiguous" in v.lower() and "signal" in v.lower() for v in result.violations)
        assert any("exceed" in v.lower() for v in result.violations)


class TestConfidenceGateMissingFields:
    def test_non_dict_input_fails_loud(self):
        result = check("not a dict")
        assert result.passed is False
        assert "not a dict" in result.violations[0]

    def test_missing_overall_signal_fails(self):
        pm = {"case_id": "c1", "criteria": [_crit("met")]}
        result = check(pm)
        assert result.passed is False
        assert any("overall_signal" in v for v in result.violations)

    def test_missing_criteria_field_fails(self):
        pm = {"case_id": "c1", "overall_signal": "meets_criteria"}
        result = check(pm)
        assert result.passed is False
        assert any("criteria" in v for v in result.violations)

    def test_non_dict_criterion_entries_are_skipped(self):
        """Defensive: bad criterion entries don't crash the gate, just skip."""
        pm = _policy_map(
            signal="meets_criteria",
            criteria=[_crit("met"), "garbage_entry", _crit("met")],
        )
        result = check(pm)
        assert result.passed is True  # garbage skipped; 0 ambiguous/unmet


class TestConfidenceGateEnvOverride:
    def test_env_var_loosens_threshold(self, monkeypatch):
        """CONFIDENCE_GATE_MAX_AMBIGUOUS lets ops widen the gate per-run."""
        monkeypatch.setenv("CONFIDENCE_GATE_MAX_AMBIGUOUS", "5")
        pm = _policy_map(
            signal="meets_criteria",
            criteria=[_crit("ambiguous")] * 3,
        )
        result = check(pm)
        assert result.passed is True
        assert result.threshold == 5

    def test_env_var_tightens_threshold(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_GATE_MAX_AMBIGUOUS", "0")
        pm = _policy_map(signal="meets_criteria", criteria=[_crit("ambiguous")])
        result = check(pm)
        assert result.passed is False
        assert result.threshold == 0

    def test_env_var_allows_disabling_gate(self, monkeypatch):
        """Ops can effectively disable the count check via a huge threshold."""
        monkeypatch.setenv("CONFIDENCE_GATE_MAX_AMBIGUOUS", "999")
        pm = _policy_map(
            signal="meets_criteria",
            criteria=[_crit("ambiguous")] * 10,
        )
        result = check(pm)
        assert result.passed is True

    def test_garbage_env_var_falls_back_to_default(self, monkeypatch):
        monkeypatch.setenv("CONFIDENCE_GATE_MAX_AMBIGUOUS", "not_an_int")
        pm = _policy_map(signal="meets_criteria", criteria=[_crit("ambiguous")])
        result = check(pm)
        assert result.threshold == _DEFAULT_MAX_AMBIGUOUS_OR_UNMET


class TestConfidenceResultStructure:
    def test_result_carries_threshold_for_audit(self):
        """Threshold is part of the result so the audit log can record it."""
        result = check(_policy_map(signal="meets_criteria", criteria=[_crit("met")]))
        assert isinstance(result.threshold, int)
        assert result.threshold == _DEFAULT_MAX_AMBIGUOUS_OR_UNMET

    def test_result_carries_signal_value(self):
        result = check(_policy_map(signal="does_not_meet", criteria=[_crit("unmet")]))
        assert result.signal == "does_not_meet"
