"""
Rationale Faithfulness Judge — eval/rationale_judge.py

LLM-as-judge for the rationale_faithfulness eval dimension. Given a
reasoning_brief and the upstream findings + context it was supposed to
draw from, asks Claude to judge each supporting_evidence claim as
supported or not.

Returns a dict shaped like:
    {
        "total": int,        # claims judged
        "supported": int,    # claims judged supported
        "judgments": [{"claim_index": int, "supported": bool, "reason": str}, ...],
        "error": str | None, # populated only if the judge failed
    }
"""

from __future__ import annotations

import asyncio
import json
import re

from claude_agent_sdk import ClaudeAgentOptions, query


_JUDGE_INSTRUCTIONS = """\
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
        "imaging_request": submission.get("imaging_request", {}) if submission else {},
        "clinical_indication": (
            submission.get("clinical_indication", {}) if submission else {}
        ),
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
    return _JUDGE_INSTRUCTIONS + "\n\n---\n\n" + json.dumps(payload, indent=2)


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


async def _judge_async(reasoning_brief: dict, evidence_namespace: dict) -> dict:
    user_prompt = _build_user_prompt(reasoning_brief, evidence_namespace)
    options = ClaudeAgentOptions()

    final_text = ""
    async for message in query(prompt=user_prompt, options=options):
        if hasattr(message, "content") and message.content:
            for block in message.content:
                if hasattr(block, "text"):
                    final_text += block.text

    if not final_text.strip():
        return {"total": 0, "supported": 0, "judgments": [], "error": "empty_response"}

    parsed = _extract_json(final_text)
    judgments = parsed.get("judgments", [])
    supported = sum(1 for j in judgments if j.get("supported") is True)
    return {
        "total": len(judgments),
        "supported": supported,
        "judgments": judgments,
        "error": None,
    }


def judge_rationale_faithfulness(
    reasoning_brief: dict,
    submission: dict,
    context: dict,
    policy_map: dict,
) -> dict:
    """Sync wrapper. Builds the evidence namespace and dispatches to the judge."""
    try:
        evidence_namespace = build_evidence_namespace(submission, context, policy_map)
        return asyncio.run(
            _judge_async(reasoning_brief or {}, evidence_namespace)
        )
    except Exception as exc:
        return {
            "total": 0,
            "supported": 0,
            "judgments": [],
            "error": f"judge_exception: {exc}",
        }
