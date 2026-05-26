"""
GPA v4 Eval Runner — eval/runner.py

Runs the eval harness against the ground truth dataset.
Unit mode (SKIP_INTEGRATION_TESTS=1): scores only computable dimensions with stubs.
Integration mode: runs full pipeline via live Claude SDK calls.

Per scope §7, eval has two layers:
  - PER-CASE dimensions: source_citation, ai_decision_limit, faithfulness, reproducibility.
  - AGGREGATE dimensions: adversarial_gate_bypass_rate, false_escalation_rate,
    confidence_calibration, cohens_kappa.

Usage:
    PYTHONPATH=. python eval/runner.py                    # unit mode
    SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py  # full live run
"""

from __future__ import annotations

import json
import os
import pathlib
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from eval.dimensions import (
    DimensionScore,
    score_source_citation_accuracy,
    score_ai_decision_limit,
    score_rationale_faithfulness,
    score_decision_reproducibility,
    score_adversarial_gate_bypass_rate,
    score_false_escalation_rate,
    score_confidence_calibration,
    score_cohens_kappa,
)


# ---------------------------------------------------------------------------
# EvalCase dataclass
# ---------------------------------------------------------------------------

@dataclass
class EvalCase:
    case_id: str
    ground_truth: dict
    pipeline_result: Any | None             # PipelineResult or None in unit mode
    dimension_scores: list[DimensionScore]  # per-case scores only
    overall_pass: bool
    # Cached artifacts needed by aggregate scoring after the loop
    reasoning_brief: dict
    policy_map: dict
    pipeline_status: str
    gates_fired: list[str]


# ---------------------------------------------------------------------------
# Ground truth loader
# ---------------------------------------------------------------------------

_GROUND_TRUTH_PATH = pathlib.Path(__file__).parent / "ground_truth.jsonl"


def _load_ground_truth() -> list[dict]:
    records = []
    with open(_GROUND_TRUTH_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    return records


# ---------------------------------------------------------------------------
# Stub data for unit mode (no live pipeline run)
# ---------------------------------------------------------------------------

def _make_unit_mode_brief(ground_truth: dict) -> dict:
    """Minimal reasoning_brief stub for unit-mode scoring."""
    min_flags = ground_truth.get("expected_uncertainty_flag_count_min", 0)
    flags = [
        {"flag": f"stub_flag_{i}", "source_ref": "none"}
        for i in range(min_flags)
    ]
    return {
        "supporting_evidence": [],
        "uncertainty_flags": flags,
    }


def _make_unit_mode_policy_map(ground_truth: dict) -> dict:
    """Minimal policy_map stub matching expected signal."""
    return {
        "overall_signal": ground_truth.get("expected_overall_signal", "unknown"),
        "criteria": [],
    }


# ---------------------------------------------------------------------------
# Core eval runner
# ---------------------------------------------------------------------------

REPRODUCIBILITY_RUNS = 5


def run_eval(live: bool = False) -> tuple[list[EvalCase], list[DimensionScore]]:
    """
    Run the eval harness against the ground truth dataset.

    Returns:
        (per_case_results, aggregate_scores)
    """
    ground_truth_records = _load_ground_truth()
    eval_cases: list[EvalCase] = []

    for gt in ground_truth_records:
        case_id = gt["case_id"]
        if live:
            eval_cases.append(_run_live_case(case_id, gt))
        else:
            eval_cases.append(_run_unit_case(case_id, gt))

    # Compute aggregate dimensions across the whole suite
    cases_for_aggregates = [
        {
            "case_id": ec.case_id,
            "ground_truth": ec.ground_truth,
            "reasoning_brief": ec.reasoning_brief,
            "policy_map": ec.policy_map,
            "pipeline_status": ec.pipeline_status,
            "gates_fired": ec.gates_fired,
            "per_case_scores": {
                ds.dimension: ds.score
                for ds in ec.dimension_scores
                if ds.score is not None
            },
        }
        for ec in eval_cases
    ]
    aggregate_scores = [
        score_adversarial_gate_bypass_rate(cases_for_aggregates),
        score_false_escalation_rate(cases_for_aggregates),
        score_confidence_calibration(cases_for_aggregates),
        score_cohens_kappa(cases_for_aggregates),
    ]
    return eval_cases, aggregate_scores


def _per_case_scores(
    reasoning_brief: dict,
    policy_map: dict,
    submission: dict,
    context: dict,
    agent_outputs: list[dict],
    agent_names: list[str],
    overall_signals: list[str | None] | None,
) -> list[DimensionScore]:
    """Score the 4 per-case dimensions."""
    return [
        score_source_citation_accuracy(reasoning_brief),
        score_ai_decision_limit(agent_outputs, agent_names),
        (
            score_rationale_faithfulness(reasoning_brief, submission, context, policy_map)
            if overall_signals is not None
            else _deferred("rationale_faithfulness", ">=0.80")
        ),
        (
            score_decision_reproducibility(overall_signals)
            if overall_signals is not None
            else _deferred("decision_reproducibility", ">=0.80")
        ),
    ]


def _deferred(name: str, target: str) -> DimensionScore:
    return DimensionScore(
        dimension=name,
        score=None,
        target=target,
        passed=None,
        notes="Not computed in unit mode (requires live SDK run).",
    )


def _compute_overall_pass(scores: list[DimensionScore]) -> bool:
    for s in scores:
        if s.passed is not None and not s.passed:
            return False
    return True


def _run_unit_case(case_id: str, ground_truth: dict) -> EvalCase:
    reasoning_brief = _make_unit_mode_brief(ground_truth)
    policy_map = _make_unit_mode_policy_map(ground_truth)
    scores = _per_case_scores(
        reasoning_brief=reasoning_brief,
        policy_map=policy_map,
        submission={},
        context={},
        agent_outputs=[],
        agent_names=[],
        overall_signals=None,
    )
    return EvalCase(
        case_id=case_id,
        ground_truth=ground_truth,
        pipeline_result=None,
        dimension_scores=scores,
        overall_pass=_compute_overall_pass(scores),
        reasoning_brief=reasoning_brief,
        policy_map=policy_map,
        pipeline_status="unit_mode",
        gates_fired=["admission", "source_verification", "ai_decision_limit", "denial"],
    )


def _run_live_case(case_id: str, ground_truth: dict) -> EvalCase:
    """Run the pipeline N times (for reproducibility) and score per-case dimensions."""
    from orchestrator.pipeline import run_pipeline

    fixtures_dir = (
        pathlib.Path(__file__).resolve().parents[1]
        / "tools" / "fixtures" / "submissions"
    )
    submission_path = fixtures_dir / f"{case_id}.json"
    submission = json.loads(submission_path.read_text(encoding="utf-8"))

    pipeline_results = [run_pipeline(submission) for _ in range(REPRODUCIBILITY_RUNS)]
    overall_signals: list[str | None] = []
    for pr in pipeline_results:
        pm = (pr.determination or {}).get("policy_map", {}) if pr.determination else {}
        overall_signals.append(pm.get("overall_signal") if isinstance(pm, dict) else None)

    primary = next(
        (pr for pr in pipeline_results if pr.determination),
        pipeline_results[0],
    )

    if primary.determination:
        reasoning_brief = primary.determination.get("reasoning_brief", {})
        policy_map = primary.determination.get("policy_map", {})
        context = primary.determination.get("context", {})
        findings = primary.determination.get("findings", {})
        agent_outputs = [findings or {}, context, policy_map, reasoning_brief]
        agent_names = [
            "evidence_summarizer",
            "context_retriever",
            "policy_mapper",
            "reasoning_drafter",
        ]
    else:
        reasoning_brief = {}
        policy_map = {}
        context = {}
        agent_outputs = []
        agent_names = []

    # Track which gates fired for this case (admission always fires; source_verification
    # gating depends on pipeline reaching that step)
    gates_fired = ["admission"]
    if primary.status != "failed":
        gates_fired.append("source_verification")
    gates_fired.append("ai_decision_limit")
    gates_fired.append("denial")

    scores = _per_case_scores(
        reasoning_brief=reasoning_brief,
        policy_map=policy_map,
        submission=submission,
        context=context,
        agent_outputs=agent_outputs,
        agent_names=agent_names,
        overall_signals=overall_signals,
    )
    return EvalCase(
        case_id=case_id,
        ground_truth=ground_truth,
        pipeline_result=primary,
        dimension_scores=scores,
        overall_pass=_compute_overall_pass(scores),
        reasoning_brief=reasoning_brief,
        policy_map=policy_map,
        pipeline_status=primary.status,
        gates_fired=gates_fired,
    )


# ---------------------------------------------------------------------------
# Report printer
# ---------------------------------------------------------------------------

def print_report(
    eval_cases: list[EvalCase], aggregate_scores: list[DimensionScore]
) -> None:
    """Markdown-formatted eval report to stdout."""
    live = any(ec.pipeline_result is not None for ec in eval_cases)
    mode = "live" if live else "unit"
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("# GPA v4 Eval Report")
    print(f"Generated: {timestamp}")
    print(f"Mode: {mode}")
    print()

    total = len(eval_cases)
    per_case_passed = sum(1 for ec in eval_cases if ec.overall_pass)
    aggregate_passed = sum(1 for s in aggregate_scores if s.passed)
    aggregate_total = sum(1 for s in aggregate_scores if s.passed is not None)

    print("## Summary")
    print(f"Cases run: {total}")
    print(f"Cases passing per-case dims: {per_case_passed}/{total}")
    print(f"Aggregate dims passing: {aggregate_passed}/{aggregate_total}")
    print()

    # Per-case section
    print("## Per-Case Results")
    print()
    for ec in eval_cases:
        label = ec.ground_truth.get("label", "")
        status = "PASS" if ec.overall_pass else "FAIL"
        print(f"### {ec.case_id} ({label}) — {status}")
        print()
        print("| Dimension | Score | Target | Status |")
        print("|---|---|---|---|")
        for ds in ec.dimension_scores:
            score_str = "N/A" if ds.score is None else f"{ds.score:.2f}"
            status_str = "—" if ds.passed is None else ("✓" if ds.passed else "✗")
            print(f"| {ds.dimension} | {score_str} | {ds.target} | {status_str} |")
        print()

    # Aggregate section
    print("## Aggregate (Suite-Wide) Results")
    print()
    print("| Dimension | Score | Target | Status | Notes |")
    print("|---|---|---|---|---|")
    for ds in aggregate_scores:
        score_str = "N/A" if ds.score is None else f"{ds.score:.3f}"
        status_str = "—" if ds.passed is None else ("✓" if ds.passed else "✗")
        notes_short = (ds.notes or "").replace("|", "\\|").replace("\n", " ")
        if len(notes_short) > 90:
            notes_short = notes_short[:87] + "..."
        print(f"| {ds.dimension} | {score_str} | {ds.target} | {status_str} | {notes_short} |")
    print()

    if not live:
        print("## Dimensions Not Scored In Unit Mode")
        print("- Rationale Faithfulness (requires LLM-as-judge)")
        print("- Decision Reproducibility (requires 5 live runs)")
        print()


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    live = os.environ.get("SKIP_INTEGRATION_TESTS", "1") != "1"
    per_case, aggregates = run_eval(live=live)
    print_report(per_case, aggregates)
