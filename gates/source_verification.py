"""
Source Verification Gate — pure Python, no LLM, no SDK.

Synchronous, deterministic check that every claim in a reasoning_brief
cites a verifiable source_ref before the brief reaches the nurse.
"""

from __future__ import annotations

from dataclasses import dataclass, field


ALLOWED_SOURCE_REFS: set[str] = {
    "imaging_request.indication_text",
    "imaging_request.modality",
    "imaging_request.body_region",
    "clinical_indication.diagnosis_code",
    "clinical_indication.diagnosis_text",
    "clinical_indication.supporting_notes",
    "clinical_indication.prior_imaging",
    "patient_context.prior_authorizations",
    "patient_context.imaging_history",
    "patient_context.relevant_diagnoses",
    "patient_context.medications",
    "patient_context.biomarkers",        # Phase 3b: Context Retriever biomarkers field
    "patient_context.prior_treatments",  # Phase 3b: Context Retriever prior_treatments field
    "policy_map.criteria",
    "none",
}


@dataclass
class SourceVerificationResult:
    passed: bool
    violations: list[str] = field(default_factory=list)
    rejection_reason: str | None = None


def verify(reasoning_brief: dict) -> SourceVerificationResult:
    """
    Check that every claim in supporting_evidence and uncertainty_flags
    has a valid source_ref.

    Rules:
    - supporting_evidence[*].source_ref must be in ALLOWED_SOURCE_REFS and NOT "none"
    - uncertainty_flags[*].source_ref must be in ALLOWED_SOURCE_REFS (including "none")
    - Never raises — always returns SourceVerificationResult
    - If reasoning_brief is missing expected keys, treat as violation
    """
    violations: list[str] = []

    try:
        supporting_evidence = reasoning_brief.get("supporting_evidence", [])
        if not isinstance(supporting_evidence, list):
            supporting_evidence = []
    except AttributeError:
        supporting_evidence = []

    try:
        uncertainty_flags = reasoning_brief.get("uncertainty_flags", [])
        if not isinstance(uncertainty_flags, list):
            uncertainty_flags = []
    except AttributeError:
        uncertainty_flags = []

    for i, item in enumerate(supporting_evidence):
        if not isinstance(item, dict):
            violations.append(f"supporting_evidence[{i}]: item is not a dict")
            continue
        source_ref = item.get("source_ref")
        if source_ref is None or source_ref == "":
            violations.append(
                f"supporting_evidence[{i}]: source_ref missing or empty"
            )
        elif source_ref == "none":
            violations.append(
                f"supporting_evidence[{i}]: source_ref 'none' not allowed in supporting_evidence"
            )
        elif source_ref not in ALLOWED_SOURCE_REFS:
            violations.append(
                f"supporting_evidence[{i}]: source_ref {source_ref!r} not allowed"
            )

    for i, item in enumerate(uncertainty_flags):
        if not isinstance(item, dict):
            violations.append(f"uncertainty_flags[{i}]: item is not a dict")
            continue
        source_ref = item.get("source_ref")
        if source_ref is None or source_ref == "":
            violations.append(
                f"uncertainty_flags[{i}]: source_ref missing or empty"
            )
        elif source_ref not in ALLOWED_SOURCE_REFS:
            violations.append(
                f"uncertainty_flags[{i}]: source_ref {source_ref!r} not allowed"
            )

    passed = len(violations) == 0
    return SourceVerificationResult(
        passed=passed,
        violations=violations,
        rejection_reason=None if passed else "invalid_source_refs",
    )
