"""
GPA v4 Eval Runner — eval/runner.py

Runs the eval harness against the ground truth dataset.
Unit mode (SKIP_INTEGRATION_TESTS=1): scores only computable dimensions with stubs.
Integration mode: runs full pipeline via live Claude SDK calls.

Per scope §7, eval has two layers:
  - PER-CASE dimensions: source_citation, ai_decision_limit, faithfulness, reproducibility.
  - AGGREGATE dimensions: adversarial_gate_bypass_rate, false_escalation_rate,
    confidence_calibration. (cohens_kappa removed 2026-05-28 — see SCOPE_DELTAS.)

Eval tiers (set via EVAL_TIER env var):

  EVAL_TIER=dev   (default)  — generation runs on Sonnet 4.5 (fast, cheap).
                               Use for daily iteration: "is this prompt change
                               directionally better?" Results are a dev signal,
                               NOT a production guarantee.

  EVAL_TIER=ship             — generation runs on whatever config/model.yaml
                               says (production canonical, currently Opus 4.1).
                               Use for pre-release ship gates and audit-grade
                               eval runs that need to measure production.

The two tiers exist because eval-on-Sonnet ≠ eval-on-Opus: reproducibility,
adversarial robustness, and rationale faithfulness are all model-dependent.
Dev tier optimizes iteration speed; ship tier optimizes production fidelity.

Usage:
    PYTHONPATH=. python eval/runner.py                          # dev tier, unit mode
    SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py # dev tier, live
    EVAL_TIER=ship SKIP_INTEGRATION_TESTS=0 PYTHONPATH=. python eval/runner.py  # ship gate
"""

from __future__ import annotations

import os

# Eval tier gates the agent model. Must run before any agent import,
# because agents call _load_model_snapshot() at module-load time and
# read MODEL_SNAPSHOT_OVERRIDE before falling back to config/model.yaml.
_EVAL_TIER = os.environ.get("EVAL_TIER", "dev").lower()
if _EVAL_TIER not in {"dev", "ship"}:
    raise ValueError(
        f"EVAL_TIER must be 'dev' or 'ship', got {_EVAL_TIER!r}. "
        "See eval/runner.py docstring for tier semantics."
    )
if _EVAL_TIER == "dev":
    # Dev tier: hardcode Sonnet for fast iteration.
    os.environ["MODEL_SNAPSHOT_OVERRIDE"] = "claude-sonnet-4-5-20250929"
elif _EVAL_TIER == "ship":
    # Ship tier guard (standing policy 2026-05-28): ship-tier runs use the
    # production Opus model, take 90-120 min wall, and produce audit-grade
    # artifacts. Require an explicit acknowledgement env var so a ship-tier
    # run can't be kicked off by accident (e.g., a forgotten EVAL_TIER=ship
    # left over in a shell, or a script defaulting to ship without intent).
    if os.environ.get("SHIP_TIER_APPROVED") != "yes":
        raise ValueError(
            "EVAL_TIER=ship requires explicit SHIP_TIER_APPROVED=yes.\n"
            "Standing policy (2026-05-28): ship-tier eval runs cost ~90-120 min wall\n"
            "and produce audit-grade artifacts. Default to EVAL_TIER=dev for iteration.\n"
            "When a ship-tier run IS intended, set both:\n"
            "    EVAL_TIER=ship SHIP_TIER_APPROVED=yes python eval/save_report.py"
        )
    # leave MODEL_SNAPSHOT_OVERRIDE untouched so agents fall back to model.yaml

import json
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
    score_physician_queue_routing_accuracy,
    score_physician_rationale_compliance,
    score_bias_disparity,
    score_citation_correctness,
    # Tier 1 business-value dims (eval framework v3)
    score_pipeline_wall_time,
    score_pipeline_completion_rate,
    score_estimated_cost_per_case_usd,
    score_gate_fire_distribution,
    # v3 follow-ups (2026-05-28): ROI heuristic + latency p90 + signal accuracy
    score_pipeline_latency_p90_seconds,
    score_estimated_roi_per_case_usd,
    score_clinical_signal_accuracy,
    # Suite-wide roll-ups of per-case dims so bucket cards show all 18 dims
    # (Fix B — 2026-05-28; closes the per-case-vs-bucket-view gap)
    score_source_citation_accuracy_suite_avg,
    score_ai_decision_limit_suite_avg,
    score_rationale_faithfulness_suite_avg,
    score_decision_reproducibility_suite_avg,
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
    # Per-run telemetry (Tier 1 business-value dims; eval framework v3)
    # Length matches REPRODUCIBILITY_RUNS for live cases; empty in unit mode.
    pipeline_run_wall_seconds: list[float] = None  # type: ignore[assignment]
    pipeline_run_statuses: list[str] = None        # type: ignore[assignment]
    # Per-run agent SDK telemetry (eval framework v3+ — 2026-05-28). Each entry
    # is the list of per-agent-call dicts returned by PipelineResult.agent_telemetry.
    # Used by score_estimated_cost_per_case_usd to compute REAL per-case cost
    # from actual token usage / SDK cost data instead of the heuristic constant.
    pipeline_run_telemetry: list[list[dict]] = None  # type: ignore[assignment]


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

    Honors ONLY_CASES env var: comma-separated list of case_ids to include.
    Useful for v1↔v2 comparisons on the same subset, or for debugging a
    single flaky case without rerunning the whole suite.

    Fixture integrity is enforced via Determinism Contract invariant 4
    (tool fixture hashing in config/tool_registry.yaml), not via the
    removed RAGIndexValidator. Real RAG corpus validation comes back when
    Phase 3 builds a parse/chunk/embed pipeline (PHASE_3_BACKLOG.md #10).

    Returns:
        (per_case_results, aggregate_scores)
    """
    ground_truth_records = _load_ground_truth()

    only_cases = os.environ.get("ONLY_CASES", "").strip()
    if only_cases:
        wanted = {c.strip() for c in only_cases.split(",") if c.strip()}
        ground_truth_records = [r for r in ground_truth_records if r["case_id"] in wanted]
        if not ground_truth_records:
            raise ValueError(
                f"ONLY_CASES={only_cases!r} matched no ground truth records."
            )

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
            # Bias-disparity dim reads this key; mirror of per_case_scores
            # with a name that matches the dim's expected interface.
            "per_case_dim_scores": {
                ds.dimension: ds.score
                for ds in ec.dimension_scores
                if ds.score is not None
            },
            # Tier 1 business-value telemetry (eval framework v3)
            "pipeline_run_wall_seconds": ec.pipeline_run_wall_seconds or [],
            "pipeline_run_statuses": ec.pipeline_run_statuses or [],
            # Per-agent SDK telemetry (real per-case cost; eval framework v3+)
            "pipeline_run_telemetry": ec.pipeline_run_telemetry or [],
        }
        for ec in eval_cases
    ]

    # Pass the default physician_queue singleton to the physician dims.
    # These dims return N/A in default eval runs (queue is empty unless
    # the eval explicitly enqueues cases or runs in route mode).
    try:
        from physician_queue import get_queue
        _phys_queue = get_queue()
    except Exception:
        _phys_queue = None

    aggregate_scores = [
        # Scope §7 originals (cohens_kappa removed 2026-05-28; see SCOPE_DELTAS)
        score_adversarial_gate_bypass_rate(cases_for_aggregates),
        score_false_escalation_rate(cases_for_aggregates),
        score_confidence_calibration(cases_for_aggregates),
        # Phase 2 §12 + scope-additions
        score_physician_queue_routing_accuracy(cases_for_aggregates, physician_queue=_phys_queue),
        score_physician_rationale_compliance(physician_queue=_phys_queue),
        score_bias_disparity(cases_for_aggregates),
        score_citation_correctness(cases_for_aggregates),
        # Tier 1 business-value dims (eval framework v3 — 2026-05-28)
        score_pipeline_wall_time(cases_for_aggregates),
        score_pipeline_completion_rate(cases_for_aggregates),
        score_estimated_cost_per_case_usd(cases_for_aggregates),
        score_gate_fire_distribution(cases_for_aggregates),
        # v3 follow-ups: ROI + latency p90 + clinical signal accuracy
        score_pipeline_latency_p90_seconds(cases_for_aggregates),
        score_estimated_roi_per_case_usd(cases_for_aggregates),
        score_clinical_signal_accuracy(cases_for_aggregates),
        # Per-case dim roll-ups (Fix B — close 18-vs-14 dashboard gap)
        score_source_citation_accuracy_suite_avg(cases_for_aggregates),
        score_ai_decision_limit_suite_avg(cases_for_aggregates),
        score_rationale_faithfulness_suite_avg(cases_for_aggregates),
        score_decision_reproducibility_suite_avg(cases_for_aggregates),
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
    pipeline_run_telemetry: list[list[dict]] | None = None,
    pipeline_run_wall_seconds: list[float] | None = None,
    pipeline_run_statuses: list[str] | None = None,
) -> list[DimensionScore]:
    """Score the 7 per-case dimensions (4 behavioral + 3 telemetry-driven)."""
    from eval.dimensions import (
        BUCKET_TRUST,
        BUCKET_VALUE,
        BUCKET_OPERATIONAL,
        score_case_cost_usd,
        score_case_wall_time_seconds,
        score_case_completion_rate,
    )
    # Resolve the active agent model snapshot for per-case cost. Read the same
    # way the cost dim does — env override first (EVAL_TIER sets this), then
    # config/model.yaml.
    import os as _os
    import pathlib as _pl
    import yaml as _yaml
    model_snapshot = _os.environ.get("MODEL_SNAPSHOT_OVERRIDE")
    if not model_snapshot:
        try:
            cfg_path = _pl.Path(__file__).resolve().parents[1] / "config" / "model.yaml"
            model_snapshot = _yaml.safe_load(cfg_path.read_text(encoding="utf-8")).get(
                "model_snapshot", "unknown"
            )
        except Exception:
            model_snapshot = "unknown"

    return [
        score_source_citation_accuracy(reasoning_brief),
        score_ai_decision_limit(agent_outputs, agent_names),
        (
            score_rationale_faithfulness(reasoning_brief, submission, context, policy_map)
            if overall_signals is not None
            else _deferred("rationale_faithfulness", ">=0.80", BUCKET_TRUST)
        ),
        (
            score_decision_reproducibility(overall_signals)
            if overall_signals is not None
            else _deferred("decision_reproducibility", ">=0.80", BUCKET_OPERATIONAL)
        ),
        # Per-case Value + Operational dims (telemetry-driven; Phase 2 close-out
        # for the per-case bucket-distribution gap)
        score_case_cost_usd(pipeline_run_telemetry, model_snapshot),
        score_case_wall_time_seconds(pipeline_run_wall_seconds),
        score_case_completion_rate(pipeline_run_statuses),
    ]


def _deferred(name: str, target: str, bucket: str | None = None) -> DimensionScore:
    """
    Placeholder DimensionScore for dims that can't compute in unit mode.

    `bucket` must be passed explicitly when the real scorer assigns a non-Trust
    bucket — otherwise the deferred placeholder defaults to Trust and the report's
    Bucket column shows the wrong attribution (e.g., decision_reproducibility
    is Operational, not Trust). Default kept as None so existing callers that
    DON'T care about the bucket still work.
    """
    from eval.dimensions import BUCKET_TRUST
    return DimensionScore(
        dimension=name,
        score=None,
        target=target,
        passed=None,
        notes="Not computed in unit mode (requires live SDK run).",
        bucket=bucket if bucket is not None else BUCKET_TRUST,
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
        # All 5 hard control gates fire when the pipeline runs end-to-end
        # (confidence gate added as 5th in ADR-015, 2026-05-27).
        gates_fired=[
            "admission", "source_verification", "ai_decision_limit",
            "denial", "confidence",
        ],
        pipeline_run_wall_seconds=[],
        pipeline_run_statuses=[],
        pipeline_run_telemetry=[],
    )


def _run_live_case(case_id: str, ground_truth: dict) -> EvalCase:
    """Run the pipeline N times (for reproducibility) and score per-case dimensions."""
    import time as _time
    from orchestrator.pipeline import run_pipeline

    fixtures_dir = (
        pathlib.Path(__file__).resolve().parents[1]
        / "tools" / "fixtures" / "submissions"
    )
    submission_path = fixtures_dir / f"{case_id}.json"
    submission = json.loads(submission_path.read_text(encoding="utf-8"))

    # Capture per-run wall time, status, AND per-agent SDK telemetry for the
    # v3 business-value dims (pipeline_wall_time_p50_seconds,
    # pipeline_completion_rate, estimated_cost_per_case_usd — the latter now
    # uses real telemetry instead of a heuristic constant).
    pipeline_results = []
    run_wall_seconds: list[float] = []
    run_statuses: list[str] = []
    run_telemetry: list[list[dict]] = []
    for _ in range(REPRODUCIBILITY_RUNS):
        _t0 = _time.perf_counter()
        pr = run_pipeline(submission)
        run_wall_seconds.append(_time.perf_counter() - _t0)
        run_statuses.append(pr.status)
        run_telemetry.append(pr.agent_telemetry or [])
        pipeline_results.append(pr)

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

    # Track which gates fired for this case. All 5 hard controls fire on a
    # completed pipeline run. Source verification only reached if pipeline
    # didn't hit an earlier failure mode.
    gates_fired = ["admission"]
    if primary.status != "failed":
        gates_fired.append("source_verification")
    gates_fired.append("ai_decision_limit")
    gates_fired.append("denial")
    # Confidence gate fires after policy_mapper (ADR-015, added as 5th gate)
    if primary.status != "failed":
        gates_fired.append("confidence")

    scores = _per_case_scores(
        reasoning_brief=reasoning_brief,
        policy_map=policy_map,
        submission=submission,
        context=context,
        agent_outputs=agent_outputs,
        agent_names=agent_names,
        overall_signals=overall_signals,
        pipeline_run_telemetry=run_telemetry,
        pipeline_run_wall_seconds=run_wall_seconds,
        pipeline_run_statuses=run_statuses,
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
        pipeline_run_wall_seconds=run_wall_seconds,
        pipeline_run_statuses=run_statuses,
        pipeline_run_telemetry=run_telemetry,
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
    # Bucket label shorthand for the per-case table (so each per-case dim row
    # carries its bucket — completes Fix B / closes the dashboard-vs-report gap).
    _BUCKET_SHORT = {"value": "Value", "trust": "Trust", "operational": "Operational"}
    for ec in eval_cases:
        label = ec.ground_truth.get("label", "")
        status = "PASS" if ec.overall_pass else "FAIL"
        print(f"### {ec.case_id} ({label}) — {status}")
        print()
        print("| Dimension | Bucket | Score | Target | Status | Notes |")
        print("|---|---|---|---|---|---|")
        for ds in ec.dimension_scores:
            score_str = "N/A" if ds.score is None else f"{ds.score:.2f}"
            status_str = "—" if ds.passed is None else ("✓" if ds.passed else "✗")
            bucket_str = _BUCKET_SHORT.get(ds.bucket, ds.bucket)
            # Notes are how we surface WHY a dim is N/A or what the failure looks like.
            # Without this, an N/A score has no actionable detail — a real diagnostic gap
            # exposed by the 2026-05-27 eval where 12/15 cases had `rationale_faithfulness=N/A`
            # and no per-case detail to explain why.
            notes = (ds.notes or "").replace("|", "\\|").replace("\n", " ")[:120]
            if notes and len(ds.notes or "") > 120:
                notes += "…"
            print(f"| {ds.dimension} | {bucket_str} | {score_str} | {ds.target} | {status_str} | {notes} |")
        print()

    # Aggregate section — grouped by bucket (eval framework v3)
    # Buckets are the PM/audience-question grouping defined in eval/dimensions.py:
    #   value       — "Did it matter?"
    #   trust       — "Can we rely on it safely?"
    #   operational — "Can it reliably operate at scale?"
    from eval.dimensions import BUCKET_VALUE, BUCKET_TRUST, BUCKET_OPERATIONAL

    _BUCKET_DISPLAY = [
        (BUCKET_VALUE, "Value / Outcomes", "Did it matter? — ROI, TAT, cost, workflow compression"),
        (BUCKET_TRUST, "Trust", "Can we rely on it safely? — bounded behavior, RAI alignment"),
        (BUCKET_OPERATIONAL, "Operational Reliability", "Can it reliably operate at scale? — enforcement machinery, stability"),
    ]

    print("## Aggregate (Suite-Wide) Results — Grouped by Bucket")
    print()
    for bucket_key, bucket_label, bucket_desc in _BUCKET_DISPLAY:
        bucket_dims = [ds for ds in aggregate_scores if ds.bucket == bucket_key]
        if not bucket_dims:
            continue
        bucket_passing = sum(1 for ds in bucket_dims if ds.passed is True)
        bucket_total = sum(1 for ds in bucket_dims if ds.passed is not None)
        bucket_summary = (
            f"{bucket_passing}/{bucket_total} passing" if bucket_total > 0
            else "no scored dims"
        )
        print(f"### {bucket_label} — *{bucket_desc}*")
        print(f"_{bucket_summary}_")
        print()
        print("| Dimension | Score | Target | Status | Notes |")
        print("|---|---|---|---|---|")
        for ds in bucket_dims:
            score_str = "N/A" if ds.score is None else f"{ds.score:.3f}"
            status_str = "—" if ds.passed is None else ("✓" if ds.passed else "✗")
            notes_short = (ds.notes or "").replace("|", "\\|").replace("\n", " ")
            if len(notes_short) > 90:
                notes_short = notes_short[:87] + "..."
            print(f"| {ds.dimension} | {score_str} | {ds.target} | {status_str} | {notes_short} |")
            # Structured sub-bucket breakdown for dims with composite components
            # (e.g. cost = reasoning + retrieval + judge). Emitted as a fenced
            # JSON line that the dashboard API parses back out.
            if ds.breakdown:
                import json as _json
                print(f"`breakdown:{ds.dimension}` {_json.dumps(ds.breakdown)}")
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
