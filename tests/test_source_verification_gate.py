"""
Tests for the Source Verification Gate (gates/source_verification.py).
"""

import pytest
from gates.source_verification import verify, SourceVerificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_brief() -> dict:
    """Return a minimal valid reasoning_brief."""
    return {
        "case_id": "CASE-001",
        "supporting_evidence": [
            {
                "claim": "Patient has prior MRI.",
                "source_ref": "patient_context.imaging_history",
                "type": "imaging",
            },
            {
                "claim": "Diagnosis matches criteria.",
                "source_ref": "clinical_indication.diagnosis_code",
                "type": "diagnosis",
            },
        ],
        "uncertainty_flags": [
            {
                "issue": "No prior authorization on file.",
                "source_ref": "patient_context.prior_authorizations",
                "resolution_hint": "Check with payer.",
            }
        ],
        "nurse_focal_points": [],
        "ai_rationale": "Standard review.",
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSourceVerificationGate:

    def test_passes_all_valid_refs(self):
        result = verify(_valid_brief())
        assert result.passed is True
        assert result.violations == []

    def test_blocks_unsourced_evidence_claim(self):
        brief = _valid_brief()
        brief["supporting_evidence"][0]["source_ref"] = "made_up_field"
        result = verify(brief)
        assert result.passed is False
        assert any("made_up_field" in v for v in result.violations)

    def test_blocks_none_in_supporting_evidence(self):
        brief = _valid_brief()
        brief["supporting_evidence"][0]["source_ref"] = "none"
        result = verify(brief)
        assert result.passed is False

    def test_allows_none_in_uncertainty_flags(self):
        brief = _valid_brief()
        brief["uncertainty_flags"][0]["source_ref"] = "none"
        result = verify(brief)
        assert result.passed is True

    def test_blocks_empty_source_ref(self):
        brief = _valid_brief()
        brief["supporting_evidence"][0]["source_ref"] = ""
        result = verify(brief)
        assert result.passed is False

    def test_blocks_missing_source_ref(self):
        brief = _valid_brief()
        del brief["supporting_evidence"][0]["source_ref"]
        result = verify(brief)
        assert result.passed is False

    def test_empty_supporting_evidence_passes(self):
        brief = _valid_brief()
        brief["supporting_evidence"] = []
        brief["uncertainty_flags"] = []
        result = verify(brief)
        assert result.passed is True

    def test_multiple_violations_all_reported(self):
        brief = _valid_brief()
        # 2 bad evidence refs
        brief["supporting_evidence"][0]["source_ref"] = "bad_ref_one"
        brief["supporting_evidence"][1]["source_ref"] = "bad_ref_two"
        # 1 bad uncertainty flag ref
        brief["uncertainty_flags"][0]["source_ref"] = "bad_flag_ref"
        result = verify(brief)
        assert len(result.violations) == 3

    def test_never_raises_on_malformed_brief(self):
        result = verify({})
        assert isinstance(result, SourceVerificationResult)

    def test_rejection_reason_set_on_failure(self):
        brief = _valid_brief()
        brief["supporting_evidence"][0]["source_ref"] = "bad_ref"
        result = verify(brief)
        assert result.passed is False
        assert result.rejection_reason is not None
