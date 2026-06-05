"""Save eval report to eval/results/eval_report.md

Wraps eval.runner.run_eval and persists the report to disk. The previous
implementation called print_report(cases) — but run_eval returns a tuple
(cases, aggregate_scores), so the report-write step crashed after a
successful 97-min eval run. This fix unpacks the tuple correctly and
adds a defensive fallback so any future signature drift surfaces loudly
WITHOUT losing the eval data.

Env loading: explicitly loads .env at startup so the OPENAI_API_KEY needed
by the cross-vendor faithfulness judge propagates into the python process
regardless of how the caller's shell handles `source .env`. (`source` sets
shell vars without exporting; child python processes don't see them unless
the .env line uses `export X=Y` or the caller uses `set -a; source .env;
set +a`. Loading dotenv here makes the entry point self-sufficient.)
"""
# Load .env BEFORE importing anything that captures env state.
# Without this, the GPT-4o faithfulness judge fails with 'missing_api_key'
# and every per-case rationale_faithfulness score is N/A — exactly the
# bug the 2026-05-28 ship-tier eval surfaced (12/15 cases lost).
from dotenv import load_dotenv
load_dotenv()

import io
import json
import os
import pathlib
import sys
import traceback
from datetime import datetime, timezone

from eval.runner import run_eval, print_report


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _dim_to_dict(d) -> dict:
    """Serialize one DimensionScore to a plain dict (diff-view friendly)."""
    return {
        "dimension": getattr(d, "dimension", None),
        "score": getattr(d, "score", None),
        "target": getattr(d, "target", None),
        "passed": getattr(d, "passed", None),
        "bucket": getattr(d, "bucket", None),
        "is_aggregate": getattr(d, "is_aggregate", None),
        "breakdown": getattr(d, "breakdown", None),
        "notes": getattr(d, "notes", None),
    }


def _machine_report(cases, aggregate_scores, timestamp: str) -> dict:
    """Build the machine-readable companion to the markdown report.

    This is the canonical data source for the eval diff/trend view. It is
    comparability-aware BY CONSTRUCTION: every run records the metadata needed
    to decide whether two runs can be honestly compared (tier, model snapshot,
    framework version, case set, mode). The diff view MUST refuse to diff runs
    whose `comparability_key` differs, or flag it loudly — that's the guardrail
    that prevents the small-sample / changed-ruler misreads.

    Per-dimension `n` (sample size) is captured where the scorer exposes it via
    notes, so a denominator shift (e.g. clinical_signal 6→12 cases) is visible
    in the diff rather than hidden behind a moved score.
    """
    tier = os.environ.get("EVAL_TIER", "dev").lower()
    model_override = os.environ.get("MODEL_SNAPSHOT_OVERRIDE")
    case_ids = sorted((getattr(c, "case_id", None) or "") for c in (cases or []))
    live = os.environ.get("SKIP_INTEGRATION_TESTS", "1") != "1"

    per_case_pass = sum(1 for c in (cases or []) if getattr(c, "overall_pass", False))
    agg_pass = sum(1 for a in (aggregate_scores or []) if getattr(a, "passed", None) is True)
    agg_scored = sum(1 for a in (aggregate_scores or []) if getattr(a, "passed", None) is not None)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat() + "Z",
        "timestamp": timestamp,
        "mode": "live" if live else "unit",
        # --- comparability metadata (the diff-view guardrail) ---------------
        "tier": tier,
        "model_snapshot": model_override or "config/model.yaml",
        "eval_framework_version": "v3",
        "case_set": case_ids,
        "case_count": len(case_ids),
        # A single key two runs must share to be honestly comparable. The diff
        # view compares this before plotting anything on a shared axis.
        "comparability_key": f"{tier}|fw=v3|n={len(case_ids)}|mode={'live' if live else 'unit'}",
        # --- headline rollups ----------------------------------------------
        "summary": {
            "cases_run": len(case_ids),
            "per_case_passed": per_case_pass,
            "aggregate_passed": agg_pass,
            "aggregate_scored": agg_scored,
        },
        # --- full per-case + aggregate scores ------------------------------
        "per_case": [
            {
                "case_id": getattr(c, "case_id", None),
                "label": (getattr(c, "ground_truth", {}) or {}).get("label"),
                "overall_pass": getattr(c, "overall_pass", None),
                "pipeline_status": getattr(c, "pipeline_status", None),
                "dimensions": [_dim_to_dict(d) for d in getattr(c, "dimension_scores", []) or []],
            }
            for c in (cases or [])
        ],
        "aggregate": [_dim_to_dict(a) for a in (aggregate_scores or [])],
    }


def _emergency_dump(cases, aggregate_scores, reason: str) -> str:
    """If print_report fails, at least dump raw per-case + aggregate data so
    the 90+ minutes of eval compute aren't lost."""
    out_dir = pathlib.Path("eval/results")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"eval_raw_{_timestamp()}.json"

    def _serialize(c):
        try:
            return {
                "case_id": getattr(c, "case_id", None),
                "overall_pass": getattr(c, "overall_pass", None),
                "dimension_scores": [
                    {
                        "dimension": getattr(d, "dimension", None),
                        "score": getattr(d, "score", None),
                        "target": getattr(d, "target", None),
                        "passed": getattr(d, "passed", None),
                        "notes": getattr(d, "notes", None),
                    }
                    for d in getattr(c, "dimension_scores", []) or []
                ],
            }
        except Exception:
            return {"error": "could_not_serialize", "repr": repr(c)}

    payload = {
        "reason": reason,
        "saved_at": datetime.now(timezone.utc).isoformat() + "Z",
        "cases": [_serialize(c) for c in (cases or [])],
        "aggregate_scores": [
            {
                "dimension": getattr(a, "dimension", None),
                "score": getattr(a, "score", None),
                "target": getattr(a, "target", None),
                "passed": getattr(a, "passed", None),
                "notes": getattr(a, "notes", None),
            }
            for a in (aggregate_scores or [])
        ],
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return str(path)


def save():
    os.makedirs("eval/results", exist_ok=True)
    live = os.environ.get("SKIP_INTEGRATION_TESTS", "1") != "1"
    result = run_eval(live=live)

    # Defensive unpack — run_eval returns (cases, aggregate_scores).
    if isinstance(result, tuple) and len(result) == 2:
        cases, aggregate_scores = result
    else:
        # Future-proof: if the signature drifts, dump everything we have
        emergency_path = _emergency_dump(result, [], "run_eval returned unexpected shape")
        raise RuntimeError(f"run_eval returned unexpected shape; raw dump at {emergency_path}")

    # Capture print_report output. If print_report itself fails, dump raw data.
    buf = io.StringIO()
    old_stdout = sys.stdout
    try:
        sys.stdout = buf
        print_report(cases, aggregate_scores)
    except Exception:
        sys.stdout = old_stdout
        tb = traceback.format_exc()
        emergency_path = _emergency_dump(cases, aggregate_scores, f"print_report failed:\n{tb}")
        print(f"print_report failed; raw dump at {emergency_path}", file=sys.stderr)
        raise
    finally:
        sys.stdout = old_stdout

    report = buf.getvalue()
    ts = _timestamp()
    out_path = f"eval/results/eval_report_{ts}.md"
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Report saved to {out_path}")

    # Machine-readable companion — canonical source for the eval diff/trend view.
    # Same timestamp stem as the .md so the pair is trivially linkable. Failure
    # to write JSON must NOT lose the markdown (already on disk above), so guard it.
    try:
        json_path = f"eval/results/eval_report_{ts}.json"
        payload = _machine_report(cases, aggregate_scores, ts)
        with open(json_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)
        print(f"Machine-readable report saved to {json_path}")
    except Exception:
        print(f"WARN: machine-readable JSON emit failed:\n{traceback.format_exc()}", file=sys.stderr)


if __name__ == "__main__":
    save()
