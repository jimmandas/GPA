"""
agents/policy_mapper/aggregate.py — pure-function criterion aggregation.

Per scope §11 repo layout. Deterministic aggregation of per-criterion statuses
into a single `overall_signal`. This is the v2 fix for the reproducibility
flakiness identified in v1: the LLM was asked to apply the aggregation rule,
which introduced variance on judgment-intensive cases where per-criterion
ambiguity propagated to overall_signal.

By moving the aggregation out of the LLM and into Python, the LLM's role
narrows to producing per-criterion judgments. Aggregation becomes a pure
function — same input always yields the same output, no temperature wobble.

The aggregation rule matches the rule documented in
`prompts/policy_mapper.md:58-62`:
  - "meets_criteria"  — all criteria are "met"
  - "does_not_meet"   — one or more criteria are "unmet"
  - "ambiguous"       — one or more criteria are "ambiguous" and none are "unmet"
"""

from __future__ import annotations

from typing import Iterable, Literal

CriterionStatus = Literal["met", "unmet", "ambiguous"]
OverallSignal = Literal["meets_criteria", "does_not_meet", "ambiguous"]


def aggregate_overall_signal(criteria: Iterable[dict]) -> OverallSignal:
    """
    Compute the deterministic overall_signal from a list of criterion dicts.

    Args:
        criteria: iterable of criterion dicts each containing a "status" key
                  with value "met" | "unmet" | "ambiguous".

    Returns:
        "meets_criteria" | "does_not_meet" | "ambiguous"

    Raises:
        ValueError: if the criteria list is empty (no criteria → no signal)
        ValueError: if any criterion has a status outside the allowed enum
    """
    statuses: list[str] = []
    for crit in criteria:
        if not isinstance(crit, dict):
            raise ValueError(f"Criterion must be a dict, got {type(crit).__name__}")
        status = crit.get("status")
        if status not in {"met", "unmet", "ambiguous"}:
            raise ValueError(
                f"Criterion status must be one of {{met, unmet, ambiguous}}, "
                f"got {status!r} for criterion {crit.get('passage_id', '<no id>')}"
            )
        statuses.append(status)

    if not statuses:
        raise ValueError("Cannot aggregate overall_signal from empty criteria list")

    # Rule order matters: unmet trumps ambiguous trumps met.
    if "unmet" in statuses:
        return "does_not_meet"
    if "ambiguous" in statuses:
        return "ambiguous"
    return "meets_criteria"
