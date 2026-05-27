"""
Confidence Gate — Phase 2 §12 / ADR-015.

Fifth hard control. Sits alongside the existing four (admission, source
verification, ai_decision_limit, denial). Fires BEFORE the reasoning_drafter
runs — if the policy_map signals low confidence, the case is auto-escalated
to the nurse / physician path without spending compute on drafting a brief
the system can't stand behind.

Why this exists (strategy doc §6 / §7):
  - "Confidence gating" is named as part of Responsible AI execution architecture
  - The system declares what it is competent to assist on, rather than producing
    a low-confidence brief that wastes nurse review time
  - Threshold is held as a module constant for now; ADR-015 + ConfidenceCalibrator
    will tune it per failure mode against eval confusion-matrix data

This gate is a pure function — no LLM, no I/O, no shared state. It reads
the policy_map and returns a structured pass/fail result. The pipeline
catches failures and routes the case to escalation, same as the
Source Verification Gate.

Tunable via CONFIDENCE_GATE_MAX_AMBIGUOUS env var (for ops experimentation
or to disable the gate by setting it to a high integer).
"""

from __future__ import annotations

import os
from dataclasses import dataclass


# Default: permissive starting point — fires only when the policy_mapper
# can't decide (overall_signal=="ambiguous") OR there's compounding
# uncertainty (>2 ambiguous/unmet criteria). Judgment-intensive cases with
# 1-2 ambiguous criteria are exactly what the system is supposed to assist
# on; those pass. ConfidenceCalibrator tunes against real eval data later.
_DEFAULT_MAX_AMBIGUOUS_OR_UNMET = 2


def _max_threshold() -> int:
    """Read threshold from env var if set, else use the default constant."""
    raw = os.environ.get("CONFIDENCE_GATE_MAX_AMBIGUOUS")
    if raw is None or not raw.strip():
        return _DEFAULT_MAX_AMBIGUOUS_OR_UNMET
    try:
        return int(raw)
    except ValueError:
        return _DEFAULT_MAX_AMBIGUOUS_OR_UNMET


@dataclass
class ConfidenceResult:
    """Output of the Confidence Gate check.

    Attributes:
        passed: True if the case has sufficient AI confidence to surface
            a brief to the nurse; False if the system declined to assist.
        signal: The overall_signal value from the policy_map.
        ambiguous_or_unmet_count: Number of criteria with status in
            {"ambiguous", "unmet"}.
        threshold: The max permitted ambiguous/unmet count at gate-evaluation
            time (recorded so the audit log can verify which threshold fired).
        violations: Human-readable list of reasons the gate failed, empty
            list if passed.
    """
    passed: bool
    signal: str
    ambiguous_or_unmet_count: int
    threshold: int
    violations: list[str]


def check(policy_map: dict) -> ConfidenceResult:
    """
    Run the Confidence Gate against a policy_map.

    Pass conditions (all must hold):
      1. policy_map.overall_signal is NOT "ambiguous"
      2. count of criteria with status in {"ambiguous", "unmet"} <= threshold

    Args:
        policy_map: The policy_map dict produced by the Policy Mapper agent.
            Must include "overall_signal" and "criteria" fields.

    Returns:
        ConfidenceResult.

    Notes:
        - This is a pure function. No I/O, no LLM, no shared state.
        - Missing required fields are treated as gate failures with explicit
          violation reasons — fail loud, don't silently default.
    """
    threshold = _max_threshold()
    violations: list[str] = []

    if not isinstance(policy_map, dict):
        return ConfidenceResult(
            passed=False,
            signal="<missing>",
            ambiguous_or_unmet_count=-1,
            threshold=threshold,
            violations=["policy_map is not a dict"],
        )

    signal = policy_map.get("overall_signal", "<missing>")
    if signal == "<missing>":
        violations.append("policy_map missing 'overall_signal'")

    criteria = policy_map.get("criteria")
    if not isinstance(criteria, list):
        violations.append("policy_map.criteria is not a list")
        criteria = []

    ambig_unmet = 0
    for c in criteria:
        if not isinstance(c, dict):
            continue
        status = c.get("status", "")
        if status in {"ambiguous", "unmet"}:
            ambig_unmet += 1

    if violations:
        # Required-field violations are themselves failures
        return ConfidenceResult(
            passed=False,
            signal=signal,
            ambiguous_or_unmet_count=ambig_unmet,
            threshold=threshold,
            violations=violations,
        )

    # Signal check
    if signal == "ambiguous":
        violations.append(
            f"overall_signal=='ambiguous' — system declines to assist on this case"
        )

    # Threshold check
    if ambig_unmet > threshold:
        violations.append(
            f"{ambig_unmet} ambiguous/unmet criteria exceed threshold ({threshold})"
        )

    return ConfidenceResult(
        passed=not violations,
        signal=signal,
        ambiguous_or_unmet_count=ambig_unmet,
        threshold=threshold,
        violations=violations,
    )
