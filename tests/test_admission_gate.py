"""
Tests for the Admission Gate (gates/admission.py).
"""

import pytest
from gates.admission import admit, AdmissionResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _valid_submission() -> dict:
    """Return a fully-populated, valid submission."""
    return {
        "case_id": "CASE-001",
        "imaging_request": {
            "modality": "MRI",
            "body_region": "Brain",
            "indication_text": "Headache with visual disturbance",
        },
        "clinical_indication": {
            "diagnosis_code": "G43.909",
        },
        "policy_id": "POL-2024-MRI",
    }


def _drop(submission: dict, dot_path: str) -> dict:
    """Remove a nested key (dot-notation) from a copy of the submission."""
    import copy
    s = copy.deepcopy(submission)
    keys = dot_path.split(".")
    node = s
    for key in keys[:-1]:
        node = node[key]
    del node[keys[-1]]
    return s


def _set(submission: dict, dot_path: str, value) -> dict:
    """Set a nested key (dot-notation) to *value* in a copy of the submission."""
    import copy
    s = copy.deepcopy(submission)
    keys = dot_path.split(".")
    node = s
    for key in keys[:-1]:
        node = node[key]
    node[keys[-1]] = value
    return s


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestAdmissionGate:

    def test_valid_submission_is_admitted(self):
        result = admit(_valid_submission())
        assert result.admitted is True
        assert result.missing_fields == []
        assert result.rejection_reason is None

    # -----------------------------------------------------------------------
    # Each required field — missing (key absent)
    # -----------------------------------------------------------------------

    def test_missing_case_id_key(self):
        result = admit(_drop(_valid_submission(), "case_id"))
        assert result.admitted is False
        assert "case_id" in result.missing_fields
        assert result.rejection_reason == "missing_required_fields"

    def test_missing_modality_key(self):
        result = admit(_drop(_valid_submission(), "imaging_request.modality"))
        assert result.admitted is False
        assert "imaging_request.modality" in result.missing_fields

    def test_missing_body_region_key(self):
        result = admit(_drop(_valid_submission(), "imaging_request.body_region"))
        assert result.admitted is False
        assert "imaging_request.body_region" in result.missing_fields

    def test_missing_indication_text_key(self):
        result = admit(_drop(_valid_submission(), "imaging_request.indication_text"))
        assert result.admitted is False
        assert "imaging_request.indication_text" in result.missing_fields

    def test_missing_diagnosis_code_key(self):
        result = admit(_drop(_valid_submission(), "clinical_indication.diagnosis_code"))
        assert result.admitted is False
        assert "clinical_indication.diagnosis_code" in result.missing_fields

    def test_missing_policy_id_key(self):
        result = admit(_drop(_valid_submission(), "policy_id"))
        assert result.admitted is False
        assert "policy_id" in result.missing_fields

    # -----------------------------------------------------------------------
    # Each required field — null value
    # -----------------------------------------------------------------------

    def test_null_case_id(self):
        result = admit(_set(_valid_submission(), "case_id", None))
        assert result.admitted is False
        assert "case_id" in result.missing_fields

    def test_null_modality(self):
        result = admit(_set(_valid_submission(), "imaging_request.modality", None))
        assert result.admitted is False
        assert "imaging_request.modality" in result.missing_fields

    def test_null_body_region(self):
        result = admit(_set(_valid_submission(), "imaging_request.body_region", None))
        assert result.admitted is False
        assert "imaging_request.body_region" in result.missing_fields

    def test_null_indication_text(self):
        result = admit(_set(_valid_submission(), "imaging_request.indication_text", None))
        assert result.admitted is False
        assert "imaging_request.indication_text" in result.missing_fields

    def test_null_diagnosis_code(self):
        result = admit(_set(_valid_submission(), "clinical_indication.diagnosis_code", None))
        assert result.admitted is False
        assert "clinical_indication.diagnosis_code" in result.missing_fields

    def test_null_policy_id(self):
        result = admit(_set(_valid_submission(), "policy_id", None))
        assert result.admitted is False
        assert "policy_id" in result.missing_fields

    # -----------------------------------------------------------------------
    # Each required field — empty string
    # -----------------------------------------------------------------------

    def test_empty_string_case_id(self):
        result = admit(_set(_valid_submission(), "case_id", ""))
        assert result.admitted is False
        assert "case_id" in result.missing_fields

    def test_empty_string_modality(self):
        result = admit(_set(_valid_submission(), "imaging_request.modality", ""))
        assert result.admitted is False
        assert "imaging_request.modality" in result.missing_fields

    def test_empty_string_body_region(self):
        result = admit(_set(_valid_submission(), "imaging_request.body_region", ""))
        assert result.admitted is False
        assert "imaging_request.body_region" in result.missing_fields

    def test_empty_string_indication_text(self):
        result = admit(_set(_valid_submission(), "imaging_request.indication_text", ""))
        assert result.admitted is False
        assert "imaging_request.indication_text" in result.missing_fields

    def test_empty_string_diagnosis_code(self):
        result = admit(_set(_valid_submission(), "clinical_indication.diagnosis_code", ""))
        assert result.admitted is False
        assert "clinical_indication.diagnosis_code" in result.missing_fields

    def test_empty_string_policy_id(self):
        result = admit(_set(_valid_submission(), "policy_id", ""))
        assert result.admitted is False
        assert "policy_id" in result.missing_fields

    # -----------------------------------------------------------------------
    # Each required field — whitespace-only string
    # -----------------------------------------------------------------------

    def test_whitespace_case_id(self):
        result = admit(_set(_valid_submission(), "case_id", "   "))
        assert result.admitted is False
        assert "case_id" in result.missing_fields

    def test_whitespace_modality(self):
        result = admit(_set(_valid_submission(), "imaging_request.modality", "\t"))
        assert result.admitted is False
        assert "imaging_request.modality" in result.missing_fields

    def test_whitespace_body_region(self):
        result = admit(_set(_valid_submission(), "imaging_request.body_region", "  \n  "))
        assert result.admitted is False
        assert "imaging_request.body_region" in result.missing_fields

    def test_whitespace_indication_text(self):
        result = admit(_set(_valid_submission(), "imaging_request.indication_text", " "))
        assert result.admitted is False
        assert "imaging_request.indication_text" in result.missing_fields

    def test_whitespace_diagnosis_code(self):
        result = admit(_set(_valid_submission(), "clinical_indication.diagnosis_code", "   "))
        assert result.admitted is False
        assert "clinical_indication.diagnosis_code" in result.missing_fields

    def test_whitespace_policy_id(self):
        result = admit(_set(_valid_submission(), "policy_id", "   "))
        assert result.admitted is False
        assert "policy_id" in result.missing_fields

    # -----------------------------------------------------------------------
    # Multiple missing fields
    # -----------------------------------------------------------------------

    def test_multiple_missing_fields_all_reported(self):
        s = _drop(_valid_submission(), "case_id")
        s = _drop(s, "imaging_request.modality")
        s = _drop(s, "policy_id")
        result = admit(s)
        assert result.admitted is False
        assert set(result.missing_fields) == {
            "case_id",
            "imaging_request.modality",
            "policy_id",
        }

    def test_empty_submission_reports_all_required_fields(self):
        result = admit({})
        assert result.admitted is False
        expected = {
            "case_id",
            "imaging_request.modality",
            "imaging_request.body_region",
            "imaging_request.indication_text",
            "clinical_indication.diagnosis_code",
            "policy_id",
        }
        assert set(result.missing_fields) == expected

    # -----------------------------------------------------------------------
    # Dot-notation paths — nested vs flat
    # -----------------------------------------------------------------------

    def test_nested_field_path_not_flat(self):
        """
        Missing imaging_request.modality must appear as the full dot-notation
        path, not just "modality".
        """
        s = _drop(_valid_submission(), "imaging_request.modality")
        result = admit(s)
        assert "imaging_request.modality" in result.missing_fields
        assert "modality" not in result.missing_fields

    def test_flat_modality_key_does_not_satisfy_nested_requirement(self):
        """
        A top-level 'modality' key does NOT satisfy imaging_request.modality.
        """
        s = _drop(_valid_submission(), "imaging_request.modality")
        s["modality"] = "CT"  # flat key — should not satisfy the nested check
        result = admit(s)
        assert result.admitted is False
        assert "imaging_request.modality" in result.missing_fields

    # -----------------------------------------------------------------------
    # Never raises
    # -----------------------------------------------------------------------

    def test_does_not_raise_on_none_submission_value(self):
        """admit() must return an AdmissionResult even with deeply broken input."""
        result = admit({"imaging_request": None, "clinical_indication": None})
        assert isinstance(result, AdmissionResult)
        assert result.admitted is False

    def test_return_type_is_always_admission_result(self):
        assert isinstance(admit(_valid_submission()), AdmissionResult)
        assert isinstance(admit({}), AdmissionResult)
