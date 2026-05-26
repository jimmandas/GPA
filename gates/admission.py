"""
Admission Gate — pure Python, no LLM, no SDK.

Synchronous, deterministic field-completeness check.
Runs before any agent is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass, field


REQUIRED_FIELDS: list[tuple[str, ...]] = [
    ("case_id",),
    ("imaging_request", "modality"),
    ("imaging_request", "body_region"),
    ("imaging_request", "indication_text"),
    ("clinical_indication", "diagnosis_code"),
    ("policy_id",),
]


@dataclass
class AdmissionResult:
    admitted: bool
    missing_fields: list[str] = field(default_factory=list)
    rejection_reason: str | None = None


def _get_nested(submission: dict, path: tuple[str, ...]):
    """
    Walk a nested dict by path tuple.
    Returns the value if found, or a sentinel _MISSING if any step is absent.
    """
    node = submission
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return _MISSING
        node = node[key]
    return node


_MISSING = object()


def _is_blank(value) -> bool:
    """
    A value counts as missing if it is:
    - the sentinel _MISSING
    - None
    - an empty string
    - a whitespace-only string
    """
    if value is _MISSING or value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    return False


def admit(submission: dict) -> AdmissionResult:
    """
    Check that all required fields are present and non-blank.

    Returns AdmissionResult(admitted=True) when all fields pass.
    Returns AdmissionResult(admitted=False, missing_fields=[...],
        rejection_reason="missing_required_fields") when any field fails.

    Never raises — always returns a result object.
    """
    missing: list[str] = []

    for path in REQUIRED_FIELDS:
        value = _get_nested(submission, path)
        if _is_blank(value):
            missing.append(".".join(path))

    if missing:
        return AdmissionResult(
            admitted=False,
            missing_fields=missing,
            rejection_reason="missing_required_fields",
        )

    return AdmissionResult(admitted=True, missing_fields=[], rejection_reason=None)
