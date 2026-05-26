"""
Tests for the ambiguous test case (pt_anon_0002) fixtures.
Validates fixture existence, structure, and the data signals that drive
SURV-1 (ambiguous), SURV-2 (ambiguous), and SURV-3 (unmet).
"""

import hashlib
import json
import pathlib
from datetime import date

import pytest
import yaml

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = pathlib.Path(__file__).parent.parent
PATIENT_FIXTURE = REPO_ROOT / "tools/fixtures/patients/pt_anon_0002.json"
IMAGING_FIXTURE = REPO_ROOT / "tools/fixtures/imaging/pt_anon_0002_CT.json"
TOOL_REGISTRY = REPO_ROOT / "config/tool_registry.yaml"
SUBMISSION_0001 = REPO_ROOT / "tools/fixtures/submissions/case_0001.json"
SUBMISSION_0002 = REPO_ROOT / "tools/fixtures/submissions/case_0002.json"

REFERENCE_DATE = date(2026, 5, 25)


# ---------------------------------------------------------------------------
# Fixture existence and structure
# ---------------------------------------------------------------------------

def test_pt_anon_0002_patient_fixture_exists():
    assert PATIENT_FIXTURE.exists(), f"Missing patient fixture: {PATIENT_FIXTURE}"
    data = json.loads(PATIENT_FIXTURE.read_text())
    assert data["patient_id"] == "pt_anon_0002"


def test_pt_anon_0002_imaging_fixture_exists():
    assert IMAGING_FIXTURE.exists(), f"Missing imaging fixture: {IMAGING_FIXTURE}"
    data = json.loads(IMAGING_FIXTURE.read_text())
    assert isinstance(data["imaging_history"], list)
    assert len(data["imaging_history"]) >= 1


# ---------------------------------------------------------------------------
# SURV-3 driver: no medications → unmet
# ---------------------------------------------------------------------------

def test_pt_anon_0002_medications_empty():
    data = json.loads(PATIENT_FIXTURE.read_text())
    assert data["medications"] == [], (
        "medications must be an empty list to drive SURV-3 unmet"
    )


# ---------------------------------------------------------------------------
# SURV-2 driver: clinical staging only → ambiguous
# ---------------------------------------------------------------------------

def test_pt_anon_0002_staging_note_is_clinical_only():
    data = json.loads(PATIENT_FIXTURE.read_text())
    staging_note = data["relevant_diagnoses"][0]["staging_note"]
    assert "pathologic staging not documented" in staging_note, (
        f"staging_note must contain 'pathologic staging not documented'. Got: {staging_note!r}"
    )


# ---------------------------------------------------------------------------
# SURV-1 driver: last CT > 180 days before reference date → ambiguous
# ---------------------------------------------------------------------------

def test_pt_anon_0002_imaging_date_outside_window():
    data = json.loads(IMAGING_FIXTURE.read_text())
    last_ct_str = data["imaging_history"][0]["date"]
    last_ct = date.fromisoformat(last_ct_str)
    delta = (REFERENCE_DATE - last_ct).days
    assert delta > 180, (
        f"Last CT ({last_ct}) must be more than 180 days before {REFERENCE_DATE}. "
        f"Got {delta} days."
    )


# ---------------------------------------------------------------------------
# Tool registry hash integrity
# ---------------------------------------------------------------------------

def test_pt_anon_0002_tool_registry_hashes_match():
    registry = yaml.safe_load(TOOL_REGISTRY.read_text())

    patient_expected = registry["patient_history_lookup"]["pt_anon_0002"]
    patient_actual = "sha256:" + hashlib.sha256(PATIENT_FIXTURE.read_bytes()).hexdigest()
    assert patient_actual == patient_expected, (
        f"Patient fixture hash mismatch.\n"
        f"  Registry : {patient_expected}\n"
        f"  Computed : {patient_actual}"
    )

    imaging_expected = registry["prior_imaging_lookup"]["pt_anon_0002_CT"]
    imaging_actual = "sha256:" + hashlib.sha256(IMAGING_FIXTURE.read_bytes()).hexdigest()
    assert imaging_actual == imaging_expected, (
        f"Imaging fixture hash mismatch.\n"
        f"  Registry : {imaging_expected}\n"
        f"  Computed : {imaging_actual}"
    )


# ---------------------------------------------------------------------------
# Admission gate — both submission fixtures pass
# ---------------------------------------------------------------------------

def test_case_0002_submission_passes_admission_gate():
    from gates.admission import admit
    submission = json.loads(SUBMISSION_0002.read_text())
    result = admit(submission)
    assert result.admitted is True, (
        f"case_0002 should be admitted. Missing fields: {result.missing_fields}"
    )


def test_case_0001_submission_passes_admission_gate():
    from gates.admission import admit
    submission = json.loads(SUBMISSION_0001.read_text())
    result = admit(submission)
    assert result.admitted is True, (
        f"case_0001 should be admitted. Missing fields: {result.missing_fields}"
    )
