"""
Unit tests for agents/evidence_summarizer/agent.py

All tests mock the SDK call layer except test_summarizer_determinism,
which requires a live CLI and is skipped when SKIP_INTEGRATION_TESTS=1.
"""

import asyncio
import json
import os
import pathlib
import sys
import tempfile
from typing import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]

VALID_SUBMISSION = {
    "case_id": "case_0001",
    "submitted_at": "2026-05-25T14:02:11Z",
    "patient": {
        "patient_id": "pt_anon_0001",
        "age": 62,
        "sex": "F",
    },
    "imaging_request": {
        "modality": "CT",
        "body_region": "chest",
        "with_contrast": True,
        "indication_text": "Follow-up of biopsy-proven stage II NSCLC, 3 months post-resection, surveillance per NCCN.",
    },
    "clinical_indication": {
        "diagnosis_code": "C34.10",
        "diagnosis_text": "Malignant neoplasm of upper lobe, right lung",
        "prior_imaging": [{"modality": "CT", "date": "2026-02-15"}],
        "supporting_notes": "Post-resection surveillance. Oncologist recommendation enclosed.",
    },
    "policy_id": "oncology_imaging_routine_v1",
}

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
        },
        {
            "text": "3 months post-resection",
            "source_ref": "imaging_request.indication_text",
        },
        {
            "text": "surveillance per NCCN",
            "source_ref": "imaging_request.indication_text",
        },
    ],
}


def _make_sdk_async_gen(text: str):
    """
    Return an async generator that yields a single AssistantMessage
    containing the supplied text, mimicking the claude_agent_sdk query() interface.
    """
    from claude_agent_sdk import AssistantMessage, TextBlock

    async def _gen(*args, **kwargs):
        msg = AssistantMessage(
            content=[TextBlock(text=text)],
            model="claude-opus-4-1-20250805",
        )
        yield msg

    return _gen


def _make_empty_sdk_async_gen():
    """Return an async generator that yields a message with empty text."""
    from claude_agent_sdk import AssistantMessage, TextBlock

    async def _gen(*args, **kwargs):
        msg = AssistantMessage(
            content=[TextBlock(text="")],
            model="claude-opus-4-1-20250805",
        )
        yield msg

    return _gen


def _read_decision_log(case_id: str) -> list[dict]:
    """Read all JSONL records from decision_log/{case_id}.jsonl."""
    log_path = _REPO_ROOT / "decision_log" / f"{case_id}.jsonl"
    if not log_path.exists():
        return []
    records = []
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


def _unique_case_id(suffix: str) -> str:
    """Generate a unique case_id per test to avoid log cross-contamination."""
    import uuid
    return f"test_{suffix}_{uuid.uuid4().hex[:8]}"


# ---------------------------------------------------------------------------
# Import the agent (must succeed with correct hash)
# ---------------------------------------------------------------------------

from agents.evidence_summarizer.agent import (
    EvidenceSummarizerError,
    PromptHashMismatchError,
    run,
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEvidenceSummarizerSchemaEnforcement:
    """
    test_summarizer_schema_enforcement

    Patches the SDK to return three malformed outputs; asserts EvidenceSummarizerError
    is raised and schema_validation_event is written for each.
    """

    MALFORMED_CASES = [
        (
            "extra_field_decision",
            {**VALID_FINDINGS, "decision": "approve"},
        ),
        (
            "missing_indication_category",
            {k: v for k, v in VALID_FINDINGS.items() if k != "indication_category"},
        ),
        (
            "invalid_enum",
            {**VALID_FINDINGS, "indication_category": "unknown_category"},
        ),
    ]

    @pytest.mark.parametrize("label,bad_findings", MALFORMED_CASES)
    def test_each_malformed_output_raises_and_logs(self, label: str, bad_findings: dict):
        case_id = _unique_case_id(f"schema_{label}")
        submission = {**VALID_SUBMISSION, "case_id": case_id}
        raw_text = json.dumps(bad_findings)

        with patch(
            "agents.evidence_summarizer.agent.query",
            side_effect=_make_sdk_async_gen(raw_text),
        ):
            with pytest.raises(EvidenceSummarizerError):
                asyncio.run(run(submission, case_id))

        records = _read_decision_log(case_id)
        types = [r["type"] for r in records]
        assert "agent_event" in types, f"agent_event not found in log for {label}"
        assert "schema_validation_event" in types, (
            f"schema_validation_event not found in log for {label}"
        )
        fail_rec = next(r for r in records if r["type"] == "schema_validation_event")
        assert fail_rec["result"] == "fail"
        assert fail_rec["escalation_triggered"] is True


class TestSummarizerDeterminism:
    """
    test_summarizer_determinism

    Requires a live Claude CLI. Skipped when SKIP_INTEGRATION_TESTS=1.
    Runs run() 5 times and asserts byte-identical output + matching audit hashes.
    """

    @pytest.mark.skipif(
        os.environ.get("SKIP_INTEGRATION_TESTS") == "1",
        reason="SKIP_INTEGRATION_TESTS=1 — live CLI not available",
    )
    def test_five_runs_byte_identical(self):
        results = []
        for _ in range(5):
            findings = asyncio.run(run(VALID_SUBMISSION, VALID_SUBMISSION["case_id"]))
            results.append(json.dumps(findings, sort_keys=True))

        unique = set(results)
        assert len(unique) == 1, (
            f"Expected 1 unique output across 5 runs, got {len(unique)}: {unique}"
        )

        # Verify output_hash values are identical in the audit log
        records = _read_decision_log(VALID_SUBMISSION["case_id"])
        agent_events = [r for r in records if r["type"] == "agent_event"]
        output_hashes = {e["output_hash"] for e in agent_events[-5:]}
        assert len(output_hashes) == 1, (
            f"Expected 1 unique output_hash, got {output_hashes}"
        )


class TestSummarizerPromptHashEnforced:
    """
    test_summarizer_prompt_hash_enforced

    Temporarily patches config/prompt_hashes.yaml to a wrong hash and asserts
    PromptHashMismatchError is raised when the agent's _verify_prompt_hash() is called.
    """

    def test_wrong_hash_raises(self):
        wrong_hash = "sha256:0000000000000000000000000000000000000000000000000000000000000000"

        # We need to test _verify_prompt_hash() in isolation since the module
        # is already imported (and hash was already verified at import time).
        # Patch the registered hash loader and call _verify_prompt_hash directly.
        import agents.evidence_summarizer.agent as agent_mod

        with patch.object(agent_mod, "_load_registered_prompt_hash", return_value=wrong_hash):
            with pytest.raises(PromptHashMismatchError):
                agent_mod._verify_prompt_hash()


class TestSummarizerCaseIdPassthrough:
    """
    test_summarizer_case_id_passthrough

    Patches SDK to return valid JSON with a mismatched case_id.
    Asserts EvidenceSummarizerError is raised.
    """

    def test_wrong_case_id_raises(self):
        case_id = _unique_case_id("caseid")
        submission = {**VALID_SUBMISSION, "case_id": case_id}

        wrong_findings = {**VALID_FINDINGS, "case_id": "completely_different_id"}
        raw_text = json.dumps(wrong_findings)

        with patch(
            "agents.evidence_summarizer.agent.query",
            side_effect=_make_sdk_async_gen(raw_text),
        ):
            with pytest.raises(EvidenceSummarizerError) as exc_info:
                asyncio.run(run(submission, case_id))

        assert exc_info.value.reason in (
            "jsonschema_validation_error",
            "case_id_mismatch",
        )


class TestSummarizerEmptyResponse:
    """
    test_summarizer_empty_response

    Patches SDK to return an empty string.
    Asserts EvidenceSummarizerError("empty_response", ...) is raised.
    """

    def test_empty_response_raises(self):
        case_id = _unique_case_id("empty")
        submission = {**VALID_SUBMISSION, "case_id": case_id}

        with patch(
            "agents.evidence_summarizer.agent.query",
            side_effect=_make_empty_sdk_async_gen(),
        ):
            with pytest.raises(EvidenceSummarizerError) as exc_info:
                asyncio.run(run(submission, case_id))

        assert exc_info.value.reason == "empty_response"


class TestSummarizerNoDecisionField:
    """
    test_summarizer_no_decision_field

    Patches SDK to return JSON with a "decision" field.
    Asserts EvidenceSummarizerError is raised (additionalProperties: false).
    """

    def test_decision_field_blocked(self):
        case_id = _unique_case_id("decision")
        submission = {**VALID_SUBMISSION, "case_id": case_id}

        findings_with_decision = {**VALID_FINDINGS, "case_id": case_id, "decision": "approve"}
        raw_text = json.dumps(findings_with_decision)

        with patch(
            "agents.evidence_summarizer.agent.query",
            side_effect=_make_sdk_async_gen(raw_text),
        ):
            with pytest.raises(EvidenceSummarizerError):
                asyncio.run(run(submission, case_id))


class TestSummarizerAuditLogWrittenOnFailure:
    """
    test_summarizer_audit_log_written_on_failure

    Patches SDK to return invalid JSON.
    Asserts agent_event is written BEFORE the raise, and schema_validation_event
    is written AFTER agent_event (both before exception propagates to caller).
    """

    def test_audit_log_order_on_invalid_json(self):
        case_id = _unique_case_id("auditlog")
        submission = {**VALID_SUBMISSION, "case_id": case_id}

        not_json = "this is not json at all"

        with patch(
            "agents.evidence_summarizer.agent.query",
            side_effect=_make_sdk_async_gen(not_json),
        ):
            with pytest.raises(EvidenceSummarizerError) as exc_info:
                asyncio.run(run(submission, case_id))

        assert exc_info.value.reason == "json_parse_error"

        records = _read_decision_log(case_id)
        assert len(records) >= 2, f"Expected at least 2 records, got {records}"

        # agent_event must come first
        assert records[0]["type"] == "agent_event", (
            f"Expected agent_event first, got {records[0]['type']}"
        )
        # schema_validation_event must follow
        assert records[1]["type"] == "schema_validation_event", (
            f"Expected schema_validation_event second, got {records[1]['type']}"
        )
        assert records[1]["failure_reason"] == "json_parse_error"
        assert records[1]["escalation_triggered"] is True
