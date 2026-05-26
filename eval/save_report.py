"""Save eval report to eval/results/eval_report.md"""
import os
from eval.runner import run_eval, print_report
import io
import sys
from datetime import datetime, timezone


def save():
    os.makedirs("eval/results", exist_ok=True)
    live = os.environ.get("SKIP_INTEGRATION_TESTS", "1") != "1"
    cases = run_eval(live=live)

    # Capture print_report output
    buf = io.StringIO()
    old_stdout = sys.stdout
    sys.stdout = buf
    print_report(cases)
    sys.stdout = old_stdout

    report = buf.getvalue()
    out_path = f"eval/results/eval_report_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.md"
    with open(out_path, "w") as f:
        f.write(report)
    print(f"Report saved to {out_path}")


if __name__ == "__main__":
    save()
