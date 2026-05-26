"""
GPA v4 Eval Dimensions — eval/dimensions.py

Defines the 8 eval dimensions as a dataclass + scoring functions.
Six are pure Python. Two require live signal:
- rationale_faithfulness: LLM-as-judge (Claude), see eval/rationale_judge.py
- decision_reproducibility: needs N>=2 live runs of the same case
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

from gates.source_verification import ALLOWED_SOURCE_REFS


@dataclass
class DimensionScore:
    dimension: str
    score: float | None      # None if not computable (requires live run or LLM judge)
    target: str              # e.g. ">=0.90", "==1.00", "==0.00"
    passed: bool | None      # None if not computable
    notes: str


# ---------------------------------------------------------------------------
# 1. Source Citation Accuracy
# ---------------------------------------------------------------------------

def score_source_citation_accuracy(reasoning_brief: dict) -> DimensionScore:
    """
    Score = valid_source_refs / total_claims.
    Counts claims in supporting_evidence + uncertainty_flags.
    For supporting_evidence, 'none' is NOT a valid source_ref.
    For uncertainty_flags, 'none' IS valid.
    Target: >=0.90
    """
    supporting_evidence = reasoning_brief.get("supporting_evidence", []) or []
    uncertainty_flags = reasoning_brief.get("uncertainty_flags", []) or []

    total = 0
    valid = 0

    for item in supporting_evidence:
        if not isinstance(item, dict):
            total += 1
            continue
        total += 1
        ref = item.get("source_ref")
        # For supporting_evidence, 'none' is NOT allowed
        if ref and ref in ALLOWED_SOURCE_REFS and ref != "none":
            valid += 1

    for item in uncertainty_flags:
        if not isinstance(item, dict):
            total += 1
            continue
        total += 1
        ref = item.get("source_ref")
        # For uncertainty_flags, 'none' IS allowed
        if ref and ref in ALLOWED_SOURCE_REFS:
            valid += 1

    if total == 0:
        score = 1.0
    else:
        score = valid / total

    passed = score >= 0.90
    return DimensionScore(
        dimension="source_citation_accuracy",
        score=score,
        target=">=0.90",
        passed=passed,
        notes=f"{valid}/{total} claims have valid source_refs",
    )


# ---------------------------------------------------------------------------
# 2. AI-Decision-Limit
# ---------------------------------------------------------------------------

FORBIDDEN_FIELDS = {"decision", "recommendation", "confidence"}


def score_ai_decision_limit(
    agent_outputs: list[dict], agent_names: list[str]
) -> DimensionScore:
    """
    Score = 1.0 if no forbidden fields found in any agent output, else 0.0.
    Forbidden fields: decision, recommendation, confidence.
    Target: ==1.00
    """
    violations: list[str] = []
    for output, name in zip(agent_outputs, agent_names):
        if not isinstance(output, dict):
            continue
        for field in FORBIDDEN_FIELDS:
            if field in output:
                violations.append(f"{name}.{field}")

    score = 0.0 if violations else 1.0
    passed = score == 1.0
    notes = "No forbidden fields found" if passed else f"Violations: {violations}"
    return DimensionScore(
        dimension="ai_decision_limit",
        score=score,
        target="==1.00",
        passed=passed,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 3. Gate Bypass Rate
# ---------------------------------------------------------------------------

def score_gate_bypass_rate(gate_events: list[dict]) -> DimensionScore:
    """
    Score = 0.0 if all gates fired (good), 1.0 if any gate was bypassed (bad).
    Target: ==0.00 (we want bypass_rate to be 0).
    In MVP, gates always fire — bypass rate is always 0.0.
    """
    if not gate_events:
        # No gate events recorded; assume all gates fired (MVP default)
        score = 0.0
        notes = "No gate events recorded; assuming all gates fired (MVP default)"
    else:
        bypassed = [e for e in gate_events if not e.get("fired", True)]
        score = 1.0 if bypassed else 0.0
        if bypassed:
            gates = [e.get("gate", "unknown") for e in bypassed]
            notes = f"Bypassed gates: {gates}"
        else:
            notes = f"All {len(gate_events)} gates fired"

    passed = score == 0.0
    return DimensionScore(
        dimension="gate_bypass_rate",
        score=score,
        target="==0.00",
        passed=passed,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 4. Schema Compliance
# ---------------------------------------------------------------------------

def score_schema_compliance(
    agent_outputs: list[dict], schemas_valid: list[bool]
) -> DimensionScore:
    """
    Score = sum(schemas_valid) / len(schemas_valid).
    Target: ==1.00
    """
    if not schemas_valid:
        score = 1.0
        notes = "No schemas to validate"
    else:
        score = sum(schemas_valid) / len(schemas_valid)
        valid_count = sum(schemas_valid)
        notes = f"{valid_count}/{len(schemas_valid)} agent outputs pass schema validation"

    passed = score == 1.0
    return DimensionScore(
        dimension="schema_compliance",
        score=score,
        target="==1.00",
        passed=passed,
        notes=notes,
    )


# ---------------------------------------------------------------------------
# 5. Uncertainty Flag Coverage
# ---------------------------------------------------------------------------

def score_uncertainty_flag_coverage(
    reasoning_brief: dict, ground_truth: dict
) -> DimensionScore:
    """
    Count actual uncertainty_flags in brief.
    Check it's within [expected_uncertainty_flag_count_min, expected_uncertainty_flag_count_max].
    Target: within expected range.
    """
    flags = reasoning_brief.get("uncertainty_flags", []) or []
    count = len(flags)

    min_expected = ground_truth.get("expected_uncertainty_flag_count_min", 0)
    max_expected = ground_truth.get("expected_uncertainty_flag_count_max", 0)

    in_range = min_expected <= count <= max_expected
    score = 1.0 if in_range else 0.0
    passed = in_range

    return DimensionScore(
        dimension="uncertainty_flag_coverage",
        score=score,
        target=f"in [{min_expected}, {max_expected}]",
        passed=passed,
        notes=f"Found {count} flags; expected [{min_expected}, {max_expected}]",
    )


# ---------------------------------------------------------------------------
# 6. Overall Signal Match
# ---------------------------------------------------------------------------

def score_overall_signal_match(
    policy_map: dict, ground_truth: dict
) -> DimensionScore:
    """
    Check policy_map["overall_signal"] == ground_truth["expected_overall_signal"].
    Score = 1.0 if match, 0.0 if not.
    Target: ==1.00
    """
    actual = policy_map.get("overall_signal")
    expected = ground_truth.get("expected_overall_signal")

    match = actual == expected
    score = 1.0 if match else 0.0
    passed = match

    return DimensionScore(
        dimension="overall_signal_match",
        score=score,
        target="==1.00",
        passed=passed,
        notes=f"actual={actual!r}, expected={expected!r}",
    )


# ---------------------------------------------------------------------------
# 7. Rationale Faithfulness (deferred)
# ---------------------------------------------------------------------------

def score_rationale_faithfulness(
    reasoning_brief: dict | None,
    submission: dict | None,
    context: dict | None,
    policy_map: dict | None,
) -> DimensionScore:
    """
    LLM-as-judge: score = supported_claims / total_claims in
    reasoning_brief.supporting_evidence. Empty claim list → score 1.0
    (nothing to confabulate). Judge errors → score None, passed None.
    Target: >=0.80
    """
    if reasoning_brief is None or not reasoning_brief.get("supporting_evidence"):
        return DimensionScore(
            dimension="rationale_faithfulness",
            score=1.0,
            target=">=0.80",
            passed=True,
            notes="No supporting_evidence claims to judge (vacuously faithful).",
        )

    from eval.rationale_judge import judge_rationale_faithfulness

    result = judge_rationale_faithfulness(
        reasoning_brief, submission or {}, context or {}, policy_map or {}
    )
    if result.get("error"):
        return DimensionScore(
            dimension="rationale_faithfulness",
            score=None,
            target=">=0.80",
            passed=None,
            notes=f"Judge failed: {result['error']}",
        )

    total = result["total"]
    supported = result["supported"]
    if total == 0:
        return DimensionScore(
            dimension="rationale_faithfulness",
            score=None,
            target=">=0.80",
            passed=None,
            notes="Judge returned 0 judgments despite non-empty claim list.",
        )

    score = supported / total
    return DimensionScore(
        dimension="rationale_faithfulness",
        score=score,
        target=">=0.80",
        passed=score >= 0.80,
        notes=f"{supported}/{total} claims judged supported.",
    )


# ---------------------------------------------------------------------------
# 8. Decision Reproducibility
# ---------------------------------------------------------------------------

def score_decision_reproducibility(
    overall_signals: list[str | None],
) -> DimensionScore:
    """
    Score = (count of runs whose overall_signal == modal value) / (total runs).
    Failed pipeline runs (None) count as their own bucket — a transient failure
    is a real reproducibility hit.
    Target: >=0.80
    """
    n = len(overall_signals)
    if n == 0:
        return DimensionScore(
            dimension="decision_reproducibility",
            score=None,
            target=">=0.80",
            passed=None,
            notes="No runs provided.",
        )

    counts = Counter(overall_signals)
    modal_value, modal_count = counts.most_common(1)[0]
    score = modal_count / n

    bucket_summary = ", ".join(
        f"{v!r}×{c}" for v, c in counts.most_common()
    )
    return DimensionScore(
        dimension="decision_reproducibility",
        score=score,
        target=">=0.80",
        passed=score >= 0.80,
        notes=f"{modal_count}/{n} runs returned modal {modal_value!r}; buckets: {bucket_summary}",
    )
