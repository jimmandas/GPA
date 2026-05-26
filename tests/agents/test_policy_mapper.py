"""
Unit tests for agents/policy_mapper/agent.py

All tests run without a live Claude CLI. The integration test
(test_policy_mapper_live) is skipped when SKIP_INTEGRATION_TESTS=1.
"""

import asyncio
import hashlib
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

from agents.policy_mapper.schema_validator import validate_policy_map
from agents.policy_mapper.agent import (
    PolicyMapperError,
    PromptHashMismatchError,
    nccn_passage_lookup,
    run,
)

# ---------------------------------------------------------------------------
# Valid policy_map fixture for schema tests
# ---------------------------------------------------------------------------

VALID_POLICY_MAP = {
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
        {
            "passage_id": "NCCN-NSCLC-SURV-3",
            "criterion_text": "Surveillance CT imaging is indicated for patients receiving adjuvant systemic therapy following resection.",
            "status": "ambiguous",
            "evidence_ref": "none",
        },
    ],
    "overall_signal": "ambiguous",
    "passage_ids_used": ["NCCN-NSCLC-SURV-1", "NCCN-NSCLC-SURV-2", "NCCN-NSCLC-SURV-3"],
}

# ---------------------------------------------------------------------------
# Schema enforcement tests
# ---------------------------------------------------------------------------


class TestPolicyMapSchemaValid:
    def test_policy_map_schema_valid_output(self):
        """A fully valid policy_map dict with 3 criteria passes schema validation without error."""
        validate_policy_map(VALID_POLICY_MAP)  # Should not raise


class TestPolicyMapSchemaMissingField:
    def test_policy_map_schema_rejects_missing_field(self):
        """Removing overall_signal triggers ValidationError."""
        bad = {k: v for k, v in VALID_POLICY_MAP.items() if k != "overall_signal"}
        with pytest.raises(jsonschema.ValidationError):
            validate_policy_map(bad)


class TestPolicyMapSchemaExtraField:
    def test_policy_map_schema_rejects_extra_field(self):
        """Adding decision field is blocked by additionalProperties: false."""
        bad = {**VALID_POLICY_MAP, "decision": "approve"}
        with pytest.raises(jsonschema.ValidationError):
            validate_policy_map(bad)


class TestPolicyMapSchemaInvalidStatus:
    def test_policy_map_schema_rejects_invalid_status(self):
        """Criterion status 'maybe' is rejected (must be met/unmet/ambiguous)."""
        bad_criteria = [
            {**c, "status": "maybe"} if i == 0 else c
            for i, c in enumerate(VALID_POLICY_MAP["criteria"])
        ]
        bad = {**VALID_POLICY_MAP, "criteria": bad_criteria}
        with pytest.raises(jsonschema.ValidationError):
            validate_policy_map(bad)


class TestPolicyMapSchemaInvalidOverallSignal:
    def test_policy_map_schema_rejects_invalid_overall_signal(self):
        """overall_signal 'deny' is rejected (must be meets_criteria/does_not_meet/ambiguous)."""
        bad = {**VALID_POLICY_MAP, "overall_signal": "deny"}
        with pytest.raises(jsonschema.ValidationError):
            validate_policy_map(bad)


# ---------------------------------------------------------------------------
# NCCN fixture file tests
# ---------------------------------------------------------------------------


class TestNccnFixtureExists:
    def test_nccn_fixture_exists(self):
        """policy/nccn_fixtures/post_treatment_surveillance_CT.yaml exists and loads with a criteria key."""
        fixture_path = _REPO_ROOT / "policy" / "nccn_fixtures" / "post_treatment_surveillance_CT.yaml"
        assert fixture_path.exists(), f"NCCN fixture missing: {fixture_path}"
        data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
        assert "criteria" in data, "NCCN fixture missing 'criteria' key"
        assert isinstance(data["criteria"], list), "'criteria' is not a list"


# ---------------------------------------------------------------------------
# Tool registry hash verification
# ---------------------------------------------------------------------------


class TestNccnToolRegistryHashMatches:
    def test_nccn_tool_registry_hash_matches(self):
        """Computed SHA-256 of NCCN fixture matches config/tool_registry.yaml."""
        registry_path = _REPO_ROOT / "config" / "tool_registry.yaml"
        assert registry_path.exists(), f"tool_registry.yaml missing: {registry_path}"

        with registry_path.open("r", encoding="utf-8") as f:
            registry = yaml.safe_load(f)

        fixture_path = (
            _REPO_ROOT / "policy" / "nccn_fixtures" / "post_treatment_surveillance_CT.yaml"
        )
        computed = "sha256:" + hashlib.sha256(fixture_path.read_bytes()).hexdigest()
        registered = registry["nccn_passage_lookup"]["post_treatment_surveillance_CT"]

        assert computed == registered, (
            f"NCCN fixture hash mismatch:\n  computed  : {computed}\n"
            f"  registered: {registered}"
        )


# ---------------------------------------------------------------------------
# Tool function unit tests
# ---------------------------------------------------------------------------


class TestNccnPassageLookupReturnsData:
    def test_nccn_passage_lookup_returns_data(self):
        """nccn_passage_lookup returns JSON with criteria list of at least 1 entry."""
        result = nccn_passage_lookup("post_treatment_surveillance", "CT")
        parsed = json.loads(result)
        assert "criteria" in parsed, "Result missing 'criteria' key"
        assert isinstance(parsed["criteria"], list), "'criteria' is not a list"
        assert len(parsed["criteria"]) >= 1, "criteria list is empty"


class TestNccnPassageLookupMissingFixture:
    def test_nccn_passage_lookup_missing_fixture(self):
        """Calling with an unknown combination returns JSON containing 'error' key."""
        result = nccn_passage_lookup("unknown_indication", "MRI")
        parsed = json.loads(result)
        assert "error" in parsed, f"Expected 'error' key in result: {parsed}"


# ---------------------------------------------------------------------------
# Prompt hash registered
# ---------------------------------------------------------------------------


class TestPromptHashRegistered:
    def test_prompt_hash_registered(self):
        """config/prompt_hashes.yaml has a policy_mapper key starting with 'sha256:'."""
        hashes_path = _REPO_ROOT / "config" / "prompt_hashes.yaml"
        with hashes_path.open("r", encoding="utf-8") as f:
            hashes = yaml.safe_load(f)

        assert "policy_mapper" in hashes, (
            "policy_mapper key missing from prompt_hashes.yaml"
        )
        assert hashes["policy_mapper"].startswith("sha256:"), (
            f"policy_mapper hash does not start with 'sha256:': {hashes['policy_mapper']}"
        )


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


@pytest.mark.skipif(
    os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
    reason="SKIP_INTEGRATION_TESTS=1 — live CLI not available",
)
def test_policy_mapper_live():
    """
    Live integration test: calls run() with real Claude CLI, verifies:
    - result passes schema validation
    - nccn_passage_lookup appears in bilateral log
    """
    case_id = "case_live_pm_0001"
    result = asyncio.run(run(VALID_FINDINGS, VALID_CONTEXT, case_id))

    # Must pass schema validation
    validate_policy_map(result)

    # Check bilateral log for nccn_passage_lookup tool call
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
    assert "nccn_passage_lookup" in tool_names, (
        f"nccn_passage_lookup not in tool_calls_made: {tool_names}"
    )
