"""
Rationale Faithfulness Judge — eval/rationale_judge.py

LLM-as-judge for the rationale_faithfulness eval dimension. Per scope §7, the
judge MUST run on a different vendor than the agents under test to avoid
self-grading bias. The agents use Claude (Anthropic); the judge uses GPT-4
(OpenAI).

Given a reasoning_brief and the upstream findings + context it was supposed
to draw from, asks GPT-4 to judge each supporting_evidence claim as supported
or not.

Returns a dict shaped like:
    {
        "total": int,        # claims judged
        "supported": int,    # claims judged supported
        "judgments": [{"claim_index": int, "supported": bool, "reason": str}, ...],
        "error": str | None, # populated only if the judge failed
        "judge_model": str,  # which model produced the verdicts
    }

Requires OPENAI_API_KEY env var. If not set, returns error="missing_api_key"
so the eval can report this dimension as deferred rather than fall back to a
biased same-vendor judge.
"""

from __future__ import annotations

import json
import os
import re


# Pinned snapshot, not the `gpt-4o` alias. Aliases let OpenAI re-route the
# underlying model silently, which would drift faithfulness scores without
# any change on our side. A pinned snapshot makes the judge model part of
# the audit record — a regulator can see exactly which model produced the
# verdict. Bumping the snapshot requires a full eval re-run (same rule as
# config/model.yaml on the agent side).
_DEFAULT_JUDGE_SNAPSHOT = "gpt-4o-2024-11-20"
_JUDGE_MODEL = os.environ.get("FAITHFULNESS_JUDGE_MODEL", _DEFAULT_JUDGE_SNAPSHOT)

# Published per scope §7 — keep this prompt under version control so the eval
# report can reproduce judge behavior.
JUDGE_INSTRUCTIONS = """\
You are an evaluator measuring whether an AI-drafted reasoning brief is faithful
to its upstream evidence sources. You do not evaluate clinical correctness. You
only evaluate whether each claim is directly supported by the material at its
cited source_ref.

Each source_ref is a dotted path into the evidence_namespace object below:
- imaging_request.*    → fields of the original imaging request
- clinical_indication.* → fields describing the clinical indication
- patient_context.*    → fields retrieved from the patient record
- policy_map.criteria  → criterion-by-criterion mapping output

Walk the path. For each claim:
- supported = true  if the cited material at that path directly backs the claim
- supported = false if the cited material is absent, contradicts the claim, or
  does not contain enough information to back the claim

Return ONLY a JSON object — no prose, no markdown fences:

{
  "judgments": [
    {"claim_index": <int>, "supported": <bool>, "reason": "<one short sentence>"}
  ]
}

Include one judgment per claim, in order. Do not skip claims.
"""


def build_evidence_namespace(
    submission: dict, context: dict, policy_map: dict
) -> dict:
    """Assemble the dict the judge walks to resolve source_refs."""
    return {
        "imaging_request": (submission or {}).get("imaging_request", {}),
        "clinical_indication": (submission or {}).get("clinical_indication", {}),
        "patient_context": {
            "prior_authorizations": (context or {}).get("prior_authorizations", []),
            "imaging_history": (context or {}).get("imaging_history", []),
            "relevant_diagnoses": (context or {}).get("relevant_diagnoses", []),
            "medications": (context or {}).get("medications", []),
        },
        "policy_map": {
            "criteria": (policy_map or {}).get("criteria", []),
        },
    }


def _build_user_prompt(reasoning_brief: dict, evidence_namespace: dict) -> str:
    claims = reasoning_brief.get("supporting_evidence", []) or []
    indexed_claims = [
        {"claim_index": i, "claim": c.get("claim"), "source_ref": c.get("source_ref")}
        for i, c in enumerate(claims)
        if isinstance(c, dict)
    ]
    payload = {
        "evidence_namespace": evidence_namespace,
        "claims_to_judge": indexed_claims,
    }
    return json.dumps(payload, indent=2)


def _extract_json(text: str) -> dict:
    """Tolerate stray prose by extracting the first {...} object."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("No JSON object found in judge output")
    return json.loads(match.group(0))


def judge_rationale_faithfulness(
    reasoning_brief: dict,
    submission: dict,
    context: dict,
    policy_map: dict,
) -> dict:
    """
    Call GPT-4 to judge each supporting_evidence claim.
    Returns a result dict (see module docstring). Never raises — failures
    are encoded in the result's `error` field.
    """
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return {
            "total": 0,
            "supported": 0,
            "judgments": [],
            "error": (
                "missing_api_key: OPENAI_API_KEY not set. Scope §7 requires a "
                "non-Anthropic judge to avoid self-grading bias. Set OPENAI_API_KEY "
                "or set FAITHFULNESS_JUDGE_VENDOR=anthropic to opt into a biased fallback."
            ),
            "judge_model": None,
        }

    try:
        from openai import OpenAI
    except ImportError as exc:
        return {
            "total": 0,
            "supported": 0,
            "judgments": [],
            "error": f"openai_import_failed: {exc}. Run: pip install openai",
            "judge_model": None,
        }

    try:
        client = OpenAI(api_key=api_key)
        evidence_namespace = build_evidence_namespace(submission, context, policy_map)
        user_prompt = _build_user_prompt(reasoning_brief or {}, evidence_namespace)

        response = client.chat.completions.create(
            model=_JUDGE_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_INSTRUCTIONS},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        text = response.choices[0].message.content or ""
        if not text.strip():
            return {
                "total": 0,
                "supported": 0,
                "judgments": [],
                "error": "empty_response_from_judge",
                "judge_model": _JUDGE_MODEL,
            }

        parsed = _extract_json(text)
        judgments = parsed.get("judgments", [])
        supported = sum(1 for j in judgments if j.get("supported") is True)
        return {
            "total": len(judgments),
            "supported": supported,
            "judgments": judgments,
            "error": None,
            "judge_model": _JUDGE_MODEL,
        }
    except Exception as exc:
        return {
            "total": 0,
            "supported": 0,
            "judgments": [],
            "error": f"judge_exception: {exc}",
            "judge_model": _JUDGE_MODEL,
        }
