"""
Unit tests for agents/context_retriever/agent.py

All tests run without a live Claude CLI. The integration test
(test_context_retriever_live) is skipped when SKIP_INTEGRATION_TESTS=1.
"""

import asyncio
import json
import os
import pathlib

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

from agents.context_retriever.schema_validator import validate_context
from agents.context_retriever.agent import (
    ContextRetrieverError,
    PromptHashMismatchError,
    patient_history_lookup,
    prior_imaging_lookup,
    run,
)

# ---------------------------------------------------------------------------
# Valid context fixture for schema tests
# ---------------------------------------------------------------------------

VALID_CONTEXT = {
    "case_id": "case_0001",
    "patient_id": "pt_anon_0001",
    "prior_authorizations": [
        {
            "auth_id": "auth_2026_0012",
            "date": "2026-02-10",
            "modality": "CT",
            "body_region": "chest",
            "outcome": "approved",
            "payer": "SimulatedPayer",
            "indication": "Pre-surgical staging, stage II NSCLC right upper lobe",
        }
    ],
    "imaging_history": [
        {
            "study_id": "img_2026_0112",
            "date": "2026-02-15",
            "modality": "CT",
            "body_region": "chest",
            "with_contrast": True,
            "finding": "3.2cm right upper lobe mass.",
            "ordering_indication": "Pre-surgical staging",
        }
    ],
    "relevant_diagnoses": [
        {
            "code": "C34.10",
            "text": "Malignant neoplasm of upper lobe, right lung",
            "date": "2025-09-20",
            "status": "active",
        }
    ],
    "data_source": "fixture",
}

# ---------------------------------------------------------------------------
# Schema enforcement tests
# ---------------------------------------------------------------------------

class TestContextSchemaValid:
    def test_context_schema_valid_output(self):
        """A fully valid context dict passes schema validation without error."""
        validate_context(VALID_CONTEXT)  # Should not raise


class TestContextSchemaMissingField:
    def test_context_schema_rejects_missing_field(self):
        """Removing prior_authorizations triggers ValidationError."""
        bad = {k: v for k, v in VALID_CONTEXT.items() if k != "prior_authorizations"}
        with pytest.raises(jsonschema.ValidationError):
            validate_context(bad)


class TestContextSchemaExtraField:
    def test_context_schema_rejects_extra_field(self):
        """Adding decision field is blocked by additionalProperties: false."""
        bad = {**VALID_CONTEXT, "decision": "approve"}
        with pytest.raises(jsonschema.ValidationError):
            validate_context(bad)


class TestContextSchemaInvalidDataSource:
    def test_context_schema_rejects_invalid_data_source(self):
        """data_source must be exactly 'fixture'; 'live' is rejected."""
        bad = {**VALID_CONTEXT, "data_source": "live"}
        with pytest.raises(jsonschema.ValidationError):
            validate_context(bad)


# ---------------------------------------------------------------------------
# Fixture file tests
# ---------------------------------------------------------------------------

class TestFixtureFilesExist:
    def test_fixture_files_exist(self):
        """Both fixture files exist on disk and are valid JSON."""
        patient_path = _REPO_ROOT / "tools" / "fixtures" / "patients" / "pt_anon_0001.json"
        imaging_path = _REPO_ROOT / "tools" / "fixtures" / "imaging" / "pt_anon_0001_CT.json"

        assert patient_path.exists(), f"Patient fixture missing: {patient_path}"
        assert imaging_path.exists(), f"Imaging fixture missing: {imaging_path}"

        # Both must be valid JSON
        json.loads(patient_path.read_text(encoding="utf-8"))
        json.loads(imaging_path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Tool registry hash verification
# ---------------------------------------------------------------------------

class TestToolRegistryHashesMatchFixtures:
    def test_tool_registry_hashes_match_fixtures(self):
        """Computed SHA-256 of each fixture file matches config/tool_registry.yaml."""
        import hashlib

        registry_path = _REPO_ROOT / "config" / "tool_registry.yaml"
        assert registry_path.exists(), f"tool_registry.yaml missing: {registry_path}"

        with registry_path.open("r", encoding="utf-8") as f:
            registry = yaml.safe_load(f)

        patient_path = _REPO_ROOT / "tools" / "fixtures" / "patients" / "pt_anon_0001.json"
        imaging_path = _REPO_ROOT / "tools" / "fixtures" / "imaging" / "pt_anon_0001_CT.json"

        computed_patient = "sha256:" + hashlib.sha256(patient_path.read_bytes()).hexdigest()
        computed_imaging = "sha256:" + hashlib.sha256(imaging_path.read_bytes()).hexdigest()

        registered_patient = registry["patient_history_lookup"]["pt_anon_0001"]
        registered_imaging = registry["prior_imaging_lookup"]["pt_anon_0001_CT"]

        assert computed_patient == registered_patient, (
            f"patient fixture hash mismatch:\n  computed  : {computed_patient}\n"
            f"  registered: {registered_patient}"
        )
        assert computed_imaging == registered_imaging, (
            f"imaging fixture hash mismatch:\n  computed  : {computed_imaging}\n"
            f"  registered: {registered_imaging}"
        )


# ---------------------------------------------------------------------------
# Prompt hash registered
# ---------------------------------------------------------------------------

class TestPromptHashRegistered:
    def test_prompt_hash_registered(self):
        """config/prompt_hashes.yaml has a context_retriever key starting with 'sha256:'."""
        hashes_path = _REPO_ROOT / "config" / "prompt_hashes.yaml"
        with hashes_path.open("r", encoding="utf-8") as f:
            hashes = yaml.safe_load(f)

        assert "context_retriever" in hashes, (
            "context_retriever key missing from prompt_hashes.yaml"
        )
        assert hashes["context_retriever"].startswith("sha256:"), (
            f"context_retriever hash does not start with 'sha256:': {hashes['context_retriever']}"
        )


# ---------------------------------------------------------------------------
# Tool function unit tests
# ---------------------------------------------------------------------------

class TestPatientHistoryLookup:
    def test_patient_history_lookup_returns_fixture(self):
        """patient_history_lookup returns valid JSON with expected patient_id and prior_authorizations."""
        result = patient_history_lookup("pt_anon_0001")
        parsed = json.loads(result)
        assert parsed["patient_id"] == "pt_anon_0001"
        assert isinstance(parsed["prior_authorizations"], list)


class TestPriorImagingLookup:
    def test_prior_imaging_lookup_returns_fixture(self):
        """prior_imaging_lookup returns valid JSON with expected modality and imaging_history."""
        result = prior_imaging_lookup("pt_anon_0001", "CT")
        parsed = json.loads(result)
        assert parsed["modality"] == "CT"
        assert isinstance(parsed["imaging_history"], list)

    def test_prior_imaging_lookup_missing_fixture(self):
        """Calling with an unknown patient_id returns JSON containing 'error' key."""
        result = prior_imaging_lookup("pt_unknown_9999", "CT")
        parsed = json.loads(result)
        assert "error" in parsed


# ---------------------------------------------------------------------------
# Integration test (skipped in unit mode)
# ---------------------------------------------------------------------------

VALID_FINDINGS = {
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
        {
            "text": "biopsy-proven stage II NSCLC",
            "source_ref": "imaging_request.indication_text",
        }
    ],
}


@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="SKIP_INTEGRATION_TESTS=1 — live CLI not available",
)
def test_context_retriever_live():
    """
    Live integration test: calls run() with real Claude CLI, verifies:
    - result passes schema validation
    - both tool calls appear in the bilateral log
    """
    case_id = "case_live_ctx_0001"
    result = asyncio.run(run(VALID_FINDINGS, "pt_anon_0001", case_id))

    # Must pass schema validation
    validate_context(result)

    # Check bilateral log for tool calls
    log_path = _REPO_ROOT / "decision_log" / f"{case_id}.jsonl"
    assert log_path.exists(), f"Bilateral log not found: {log_path}"

    records = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    agent_events = [r for r in records if r.get("type") == "agent_event"]
    assert agent_events, "No agent_event found in bilateral log"

    tool_names = [
        tc["name"]
        for event in agent_events
        for tc in event.get("tool_calls_made", [])
    ]
    assert "patient_history_lookup" in tool_names, (
        f"patient_history_lookup not in tool_calls_made: {tool_names}"
    )
    assert "prior_imaging_lookup" in tool_names, (
        f"prior_imaging_lookup not in tool_calls_made: {tool_names}"
    )
