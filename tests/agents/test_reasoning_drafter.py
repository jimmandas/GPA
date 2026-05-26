"""
Unit tests for agents/reasoning_drafter/agent.py

All tests mock the SDK call layer except the live integration tests,
which are skipped when SKIP_INTEGRATION_TESTS=1.
"""

import asyncio
import importlib
import json
import os
import pathlib
import sys
from unittest.mock import patch

import pytest
import yaml
import jsonschema

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Import agent components
# ---------------------------------------------------------------------------

from agents.reasoning_drafter.schema_validator import validate_reasoning_brief
from agents.reasoning_drafter.agent import (
    ReasoningDrafterError,
    PromptHashMismatchError,
    run,
)

# ---------------------------------------------------------------------------
# Valid reasoning_brief fixture
# ---------------------------------------------------------------------------

VALID_REASONING_BRIEF = {
    "case_id": "case_0001",
    "supporting_evidence": [
        {
            "claim": "Biopsy-proven stage II NSCLC documented in indication text.",
            "source_ref": "imaging_request.indication_text",
            "type": "diagnosis",
        },
        {
            "claim": "CT chest performed 2026-02-15 per imaging history.",
            "source_ref": "patient_context.imaging_history",
            "type": "imaging",
        },
    ],
    "uncertainty_flags": [
        {
            "issue": "No documentation of adjuvant systemic therapy following resection.",
            "source_ref": "clinical_indication.supporting_notes",
            "resolution_hint": "Request oncology notes confirming adjuvant therapy status.",
        }
    ],
    "nurse_focal_points": [
        {
            "point": "Verify whether patient received adjuvant systemic therapy post-resection.",
            "why": "NCCN-NSCLC-SURV-3 criterion requires adjuvant therapy for surveillance imaging to be indicated.",
        },
        {
            "point": "Confirm timing of prior CT relative to current request.",
            "why": "NCCN guidelines require CT every 3-6 months within 2 years post-resection.",
        },
    ],
    "ai_rationale": (
        "The submission documents biopsy-proven stage II NSCLC with CT chest performed "
        "3 months post-resection per NCCN surveillance guidelines. The diagnosis code C34.10 "
        "is present and prior imaging is documented. Whether adjuvant systemic therapy was "
        "administered is not confirmed in the available notes; the nurse should verify this "
        "before making a determination."
    ),
}

# ---------------------------------------------------------------------------
# Fixtures: findings, context, policy_map for live tests
# ---------------------------------------------------------------------------

FINDINGS_CLEAN = {
    "case_id": "case_0001",
    "modality": "CT",
    "body_region": "chest",
    "indication_category": "post_treatment_surveillance",
    "completeness_flags": {
        "has_diagnosis_code": True,
        "has_prior_imaging": True,
        "has_treatment_history": True,
        "has_clinical_rationale": True,
    },
    "raw_quotes": [
        {"text": "biopsy-proven stage II NSCLC", "source_ref": "imaging_request.indication_text"},
        {"text": "3 months post-resection", "source_ref": "imaging_request.indication_text"},
        {"text": "surveillance per NCCN", "source_ref": "imaging_request.indication_text"},
    ],
}

CONTEXT_CLEAN = {
    "case_id": "case_0001",
    "prior_authorizations": [
        {"auth_id": "AUTH-2026-001", "modality": "CT", "status": "approved", "date": "2026-02-10"}
    ],
    "imaging_history": [
        {"modality": "CT", "body_region": "chest", "date": "2026-02-15", "indication": "post-resection surveillance"}
    ],
    "relevant_diagnoses": [
        {"code": "C34.10", "text": "Malignant neoplasm of upper lobe, right lung", "confirmed": True}
    ],
    "medications": [],
}

POLICY_MAP_CLEAN = {
    "case_id": "case_0001",
    "indication_category": "post_treatment_surveillance",
    "modality": "CT",
    "criteria": [
        {
            "passage_id": "NCCN-NSCLC-SURV-1",
            "criterion_text": "CT chest with or without contrast is recommended every 3-6 months for the first 2 years following curative-intent resection of NSCLC.",
            "status": "met",
            "evidence_ref": "patient_context.imaging_history",
        },
        {
            "passage_id": "NCCN-NSCLC-SURV-2",
            "criterion_text": "Patient must have a confirmed diagnosis of NSCLC with documented pathologic staging (Stage I-III) prior to surveillance imaging.",
            "status": "met",
            "evidence_ref": "clinical_indication.diagnosis_code",
        },
    ],
    "overall_signal": "met",
    "passage_ids_used": ["NCCN-NSCLC-SURV-1", "NCCN-NSCLC-SURV-2"],
}

FINDINGS_AMBIGUOUS = {
    "case_id": "case_0002",
    "modality": "CT",
    "body_region": "chest",
    "indication_category": "post_treatment_surveillance",
    "completeness_flags": {
        "has_diagnosis_code": True,
        "has_prior_imaging": False,
        "has_treatment_history": False,
        "has_clinical_rationale": True,
    },
    "raw_quotes": [
        {"text": "suspected recurrence of NSCLC", "source_ref": "imaging_request.indication_text"},
    ],
}

CONTEXT_AMBIGUOUS = {
    "case_id": "case_0002",
    "prior_authorizations": [],
    "imaging_history": [],
    "relevant_diagnoses": [
        {"code": "C34.10", "text": "Malignant neoplasm of upper lobe, right lung", "confirmed": True}
    ],
    "medications": [],
}

POLICY_MAP_AMBIGUOUS = {
    "case_id": "case_0002",
    "indication_category": "post_treatment_surveillance",
    "modality": "CT",
    "criteria": [
        {
            "passage_id": "NCCN-NSCLC-SURV-1",
            "criterion_text": "CT chest with or without contrast is recommended every 3-6 months for the first 2 years following curative-intent resection of NSCLC.",
            "status": "ambiguous",
            "evidence_ref": "patient_context.imaging_history",
        },
        {
            "passage_id": "NCCN-NSCLC-SURV-2",
            "criterion_text": "Patient must have a confirmed diagnosis of NSCLC with documented pathologic staging (Stage I-III) prior to surveillance imaging.",
            "status": "ambiguous",
            "evidence_ref": "clinical_indication.diagnosis_code",
        },
        {
            "passage_id": "NCCN-NSCLC-SURV-3",
            "criterion_text": "Surveillance CT imaging is indicated for patients receiving adjuvant systemic therapy following resection.",
            "status": "unmet",
            "evidence_ref": "none",
        },
    ],
    "overall_signal": "ambiguous",
    "passage_ids_used": ["NCCN-NSCLC-SURV-1", "NCCN-NSCLC-SURV-2", "NCCN-NSCLC-SURV-3"],
}


# ---------------------------------------------------------------------------
# Schema enforcement tests
# ---------------------------------------------------------------------------

class TestReasoningBriefSchemaValidOutput:
    def test_reasoning_brief_schema_valid_output(self):
        """A fully valid reasoning_brief dict passes schema validation without error."""
        validate_reasoning_brief(VALID_REASONING_BRIEF)  # Should not raise


class TestReasoningBriefSchemaMissingField:
    def test_reasoning_brief_schema_rejects_missing_field(self):
        """Removing uncertainty_flags causes a ValidationError."""
        bad = {k: v for k, v in VALID_REASONING_BRIEF.items() if k != "uncertainty_flags"}
        with pytest.raises(jsonschema.ValidationError):
            validate_reasoning_brief(bad)


class TestReasoningBriefSchemaRejectsDecision:
    def test_reasoning_brief_schema_rejects_extra_field_decision(self):
        """Adding a decision field at top level causes ValidationError (governance test)."""
        bad = {**VALID_REASONING_BRIEF, "decision": "approve"}
        with pytest.raises(jsonschema.ValidationError):
            validate_reasoning_brief(bad)


class TestReasoningBriefSchemaRejectsRecommendation:
    def test_reasoning_brief_schema_rejects_extra_field_recommendation(self):
        """Adding a recommendation field at top level causes ValidationError."""
        bad = {**VALID_REASONING_BRIEF, "recommendation": "approve"}
        with pytest.raises(jsonschema.ValidationError):
            validate_reasoning_brief(bad)


class TestReasoningBriefSchemaRejectsConfidence:
    def test_reasoning_brief_schema_rejects_extra_field_confidence(self):
        """Adding a confidence field at top level causes ValidationError."""
        bad = {**VALID_REASONING_BRIEF, "confidence": 0.9}
        with pytest.raises(jsonschema.ValidationError):
            validate_reasoning_brief(bad)


class TestReasoningBriefSchemaRejectsInvalidEvidenceType:
    def test_reasoning_brief_schema_rejects_invalid_evidence_type(self):
        """An unknown type value in supporting_evidence causes ValidationError."""
        bad_evidence = [
            {**VALID_REASONING_BRIEF["supporting_evidence"][0], "type": "unknown"},
            *VALID_REASONING_BRIEF["supporting_evidence"][1:],
        ]
        bad = {**VALID_REASONING_BRIEF, "supporting_evidence": bad_evidence}
        with pytest.raises(jsonschema.ValidationError):
            validate_reasoning_brief(bad)


class TestReasoningBriefSchemaRejectsTooManyFocalPoints:
    def test_reasoning_brief_schema_rejects_too_many_focal_points(self):
        """Four nurse_focal_points items (maxItems is 3) causes ValidationError."""
        extra_point = {"point": "Extra point", "why": "Extra why"}
        bad = {
            **VALID_REASONING_BRIEF,
            "nurse_focal_points": [*VALID_REASONING_BRIEF["nurse_focal_points"], extra_point, extra_point],
        }
        # Make sure we actually have 4 items
        assert len(bad["nurse_focal_points"]) == 4
        with pytest.raises(jsonschema.ValidationError):
            validate_reasoning_brief(bad)


class TestReasoningBriefSchemaAllowsEmptyUncertaintyFlags:
    def test_reasoning_brief_schema_allows_empty_uncertainty_flags(self):
        """Empty uncertainty_flags array is valid (clean cases with all criteria met)."""
        clean = {**VALID_REASONING_BRIEF, "uncertainty_flags": []}
        validate_reasoning_brief(clean)  # Should not raise


# ---------------------------------------------------------------------------
# Prompt hash tests
# ---------------------------------------------------------------------------

class TestPromptHashRegistered:
    def test_prompt_hash_registered(self):
        """config/prompt_hashes.yaml must have a reasoning_drafter key starting with 'sha256:'."""
        hashes_path = _REPO_ROOT / "config" / "prompt_hashes.yaml"
        with hashes_path.open("r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        assert "reasoning_drafter" in cfg, "reasoning_drafter key missing from prompt_hashes.yaml"
        assert cfg["reasoning_drafter"].startswith("sha256:"), (
            f"Expected sha256: prefix, got: {cfg['reasoning_drafter']}"
        )


class TestPromptHashVerifiedAtImport:
    def test_prompt_hash_verified_at_import(self):
        """A wrong hash in prompt_hashes.yaml causes PromptHashMismatchError."""
        import agents.reasoning_drafter.agent as agent_mod

        wrong_hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

        with patch.object(agent_mod, "_load_registered_prompt_hash", return_value=wrong_hash):
            with pytest.raises(PromptHashMismatchError):
                agent_mod._verify_prompt_hash()


# ---------------------------------------------------------------------------
# Live integration tests (skipped in unit mode)
# ---------------------------------------------------------------------------

class TestReasoningDrafterLiveCleanCase:
    @pytest.mark.skipif(
        os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
        reason="live CLI not available",
    )
    def test_reasoning_drafter_live_clean_case(self):
        """
        Live test: all criteria met for case_0001.
        Asserts schema-valid output, empty or minimal uncertainty_flags,
        and no decision field.
        """
        result = asyncio.run(run(
            findings=FINDINGS_CLEAN,
            context=CONTEXT_CLEAN,
            policy_map=POLICY_MAP_CLEAN,
            case_id="case_0001",
        ))

        # Must be schema-valid
        validate_reasoning_brief(result)

        # Must not contain a decision field
        assert "decision" not in result

        # Clean case: uncertainty_flags should be empty or minimal (0-1)
        assert len(result["uncertainty_flags"]) <= 1, (
            f"Expected 0-1 uncertainty flags for a clean case, got {len(result['uncertainty_flags'])}"
        )


class TestReasoningDrafterLiveAmbiguousCase:
    @pytest.mark.skipif(
        os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
        reason="live CLI not available",
    )
    def test_reasoning_drafter_live_ambiguous_case(self):
        """
        Live test: SURV-1 ambiguous, SURV-2 ambiguous, SURV-3 unmet for case_0002.
        Asserts schema-valid output, >= 2 uncertainty_flags, >= 2 nurse_focal_points.
        """
        result = asyncio.run(run(
            findings=FINDINGS_AMBIGUOUS,
            context=CONTEXT_AMBIGUOUS,
            policy_map=POLICY_MAP_AMBIGUOUS,
            case_id="case_0002",
        ))

        # Must be schema-valid
        validate_reasoning_brief(result)

        # Must not contain a decision field
        assert "decision" not in result

        # Ambiguous case: must surface >= 2 uncertainty flags
        assert len(result["uncertainty_flags"]) >= 2, (
            f"Expected >= 2 uncertainty flags for ambiguous case, got {len(result['uncertainty_flags'])}"
        )

        # Must have >= 2 nurse focal points
        assert len(result["nurse_focal_points"]) >= 2, (
            f"Expected >= 2 nurse focal points for ambiguous case, got {len(result['nurse_focal_points'])}"
        )
