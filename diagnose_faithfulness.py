"""
One-off diagnostic: for each eval case, run the pipeline once, then call the
rationale faithfulness judge and dump the per-claim judgments alongside the
underlying source material. Helps decide whether low faithfulness scores
reflect agent confabulation or a too-strict judge prompt.

Not part of the eval harness. Not committed long-term.
"""

from __future__ import annotations

# Load .env BEFORE importing rationale_judge (which inits the OpenAI client)
from dotenv import load_dotenv
load_dotenv()

import json
import pathlib
import sys

from orchestrator.pipeline import run_pipeline
from eval.rationale_judge import judge_rationale_faithfulness, build_evidence_namespace


_REPO = pathlib.Path(__file__).resolve().parent
_SUBS = _REPO / "tools" / "fixtures" / "submissions"


def _resolve_source(source_ref: str, evidence: dict) -> str:
    """Walk evidence namespace by dotted path, return a snippet of the material."""
    if not source_ref or source_ref == "none":
        return "<no source_ref>"
    parts = source_ref.split(".")
    node: object = evidence
    for p in parts:
        if isinstance(node, dict) and p in node:
            node = node[p]
        else:
            return f"<path '{source_ref}' not resolvable in evidence_namespace>"
    try:
        return json.dumps(node, indent=2)[:600]
    except TypeError:
        return str(node)[:600]


def diagnose(case_id: str) -> None:
    submission = json.loads((_SUBS / f"{case_id}.json").read_text())
    print(f"\n{'='*70}\nCASE: {case_id}\n{'='*70}")

    res = run_pipeline(submission)
    print(f"pipeline status: {res.status}")
    if not res.determination:
        print(f"escalation_reason: {res.escalation_reason}")
        return

    det = res.determination
    reasoning_brief = det.get("reasoning_brief", {})
    context = det.get("context", {})
    policy_map = det.get("policy_map", {})
    claims = reasoning_brief.get("supporting_evidence", []) or []
    print(f"claims in supporting_evidence: {len(claims)}")

    evidence = build_evidence_namespace(submission, context, policy_map)
    judge_result = judge_rationale_faithfulness(
        reasoning_brief, submission, context, policy_map
    )
    if judge_result.get("error"):
        print(f"JUDGE ERROR: {judge_result['error']}")
        return

    print(f"\nJudge totals: {judge_result['supported']}/{judge_result['total']} supported")
    judgments_by_idx = {j.get("claim_index"): j for j in judge_result["judgments"]}

    for i, claim in enumerate(claims):
        j = judgments_by_idx.get(i, {})
        verdict = "SUPPORTED" if j.get("supported") else "UNSUPPORTED"
        print(f"\n--- claim #{i} [{verdict}]")
        print(f"  claim     : {claim.get('claim')}")
        print(f"  source_ref: {claim.get('source_ref')}")
        print(f"  reason    : {j.get('reason', '<no reason>')}")
        source_material = _resolve_source(claim.get("source_ref"), evidence)
        print(f"  source material at that ref:\n    {source_material.replace(chr(10), chr(10)+'    ')}")


if __name__ == "__main__":
    cases = sys.argv[1:] or ["case_0001", "case_0002"]
    for cid in cases:
        diagnose(cid)
