"""Save eval report to eval/results/eval_report.md

Wraps eval.runner.run_eval and persists the report to disk. The previous
implementation called print_report(cases) — but run_eval returns a tuple
(cases, aggregate_scores), so the report-write step crashed after a
successful 97-min eval run. This fix unpacks the tuple correctly and
adds a defensive fallback so any future signature drift surfaces loudly
WITHOUT losing the eval data.
"""
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
    out_path = f"eval/results/eval_report_{_timestamp()}.md"
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Report saved to {out_path}")


if __name__ == "__main__":
    save()
