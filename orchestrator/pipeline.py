"""
GPA v4 Pipeline — orchestrator/pipeline.py

Sequential pipeline function. Not a state machine.
Calls all gates and agents in fixed order.
Enforces write-before-emit: determination not returned until bilateral
logger confirms a durable write.

Entry point: run_pipeline(submission: dict) -> dict
"""

import asyncio
import json
import os
import hashlib
from datetime import datetime, timezone
from dataclasses import dataclass

from gates.admission import admit
from gates.source_verification import verify
from gates.ai_decision_limit import check as check_ai_decision_limit, AIDecisionAttemptError
from gates.denial import check as check_denial, DenialAttemptError
from gates.confidence import check as check_confidence

from agents.classifier import agent as classifier
from agents.evidence_summarizer import agent as evidence_summarizer

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from physician_queue.queue import PhysicianQueue
from agents.context_retriever import agent as context_retriever
from agents.policy_mapper import agent as policy_mapper
from agents.reasoning_drafter import agent as reasoning_drafter

from logs.bilateral_logger import get_logger, BilateralLoggerError


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class PipelineResult:
    case_id: str
    status: str                  # "completed" | "escalated" | "failed"
    determination: dict | None   # None if escalated or failed
    escalation_reason: str | None
    audit_log_ref: str           # path to decision_log/{case_id}.jsonl
    # Per-agent SDK telemetry captured during this run. Populated by the
    # orchestrator from the ContextVar collector. Empty list if no SDK calls
    # surfaced telemetry (e.g., tests with mocked SDK responses).
    agent_telemetry: list[dict] | None = None


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z"


def _sha256(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _build_pre_state_record(case_id, submission, findings, context, policy_map, reasoning_brief) -> dict:
    return {
        "type": "pre_state_record",
        "case_id": case_id,
        "submission_hash": _sha256(json.dumps(submission, sort_keys=True, separators=(',', ':'))),
        "findings_hash": _sha256(json.dumps(findings, sort_keys=True, separators=(',', ':'))),
        "context_hash": _sha256(json.dumps(context, sort_keys=True, separators=(',', ':'))),
        "policy_map_hash": _sha256(json.dumps(policy_map, sort_keys=True, separators=(',', ':'))),
        "reasoning_brief_hash": _sha256(json.dumps(reasoning_brief, sort_keys=True, separators=(',', ':'))),
        "denial_gate_mode": os.environ.get("DENIAL_GATE_MODE", "block"),
        "at": _now_iso(),
    }


def _log_escalation(case_id: str, reason: str, detail) -> None:
	"""
	Log an escalation event to the bilateral audit logger.

	Escalation logs are critical to the HITL pipeline. If the audit log write
	fails, this raises BilateralLoggerError so the caller (gate) can decide
	whether to fail-closed or retry. No silent failures.

	Raises:
		BilateralLoggerError: if the audit log write fails
	"""
	record = {
		"type": "escalation_event",
		"case_id": case_id,
		"reason": reason,
		"detail": str(detail),
		"at": _now_iso(),
	}
	get_logger().commit(case_id, record)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def run_pipeline(submission: dict) -> PipelineResult:
    """
    Synchronous entry point. Runs the full GPA pipeline for one submission.

    Args:
        submission: The raw submission dict.

    Returns:
        PipelineResult with status "completed", "escalated", or "failed".
    """
    return asyncio.run(_run_async(submission))


# ---------------------------------------------------------------------------
# Async pipeline implementation
# ---------------------------------------------------------------------------

async def _run_async(submission: dict) -> PipelineResult:
    """The actual pipeline — all steps run in sequence."""

    # STEP 0 — Start fresh per-run telemetry collection. Each agent appends
    # one record per SDK call; we attach the collected list to PipelineResult
    # at the end so the eval can compute real per-case cost.
    from orchestrator import telemetry as _telemetry
    _telemetry.start_collection()

    # STEP 1 — Extract case_id and patient_id
    case_id = submission.get("case_id", "unknown")
    patient_id = submission.get("patient", {}).get("patient_id", "unknown")

    try:
        # STEP 2 — Admission Gate
        result = admit(submission)
        if not result.admitted:
            return PipelineResult(
                case_id=case_id,
                status="escalated",
                determination=None,
                escalation_reason=f"admission_gate_failed: {result.missing_fields}",
                audit_log_ref=f"decision_log/{case_id}.jsonl",
                agent_telemetry=_telemetry.get_collected(),
            )

        # STEP 3 — Classifier (Agent 0 — NEW Phase 3b)
        # Extracts cancer type, stage, ICD-10, therapy line, urgency for RAG guideline retrieval
        classification = await classifier.classify(case_id, submission)

        # STEP 4 — Evidence Summarizer (Agent 1)
        findings = await evidence_summarizer.run(submission, case_id)
        check_ai_decision_limit(findings, "evidence_summarizer")

        # STEP 5 — Context Retriever (Agent 2)
        context = await context_retriever.run(findings, patient_id, case_id)
        check_ai_decision_limit(context, "context_retriever")

        # STEP 6 — Policy Mapper (Agent 3)
        # Now uses classification.cancer_type + classification.stage for RAG guideline retrieval (Phase 3b)
        policy_map = await policy_mapper.run(findings, context, case_id)
        check_ai_decision_limit(policy_map, "policy_mapper")

        # STEP 6.5 — Confidence Gate (5th hard control)
        # Fires BEFORE reasoning_drafter to save the cost of drafting a brief
        # on a case the system has declared low-confidence. ADR-015.
        conf_result = check_confidence(policy_map)
        if not conf_result.passed:
            try:
                _log_escalation(case_id, "confidence_gate_failed", {
                    "signal": conf_result.signal,
                    "ambiguous_or_unmet_count": conf_result.ambiguous_or_unmet_count,
                    "threshold": conf_result.threshold,
                    "violations": conf_result.violations,
                })
            except BilateralLoggerError:
                # Escalation logging failed — audit trail integrity is at risk.
                # Fail-closed: propagate the error, do not emit a partial determination.
                raise
            return PipelineResult(
                case_id=case_id,
                status="escalated",
                determination=None,
                escalation_reason=f"confidence_gate_failed: {conf_result.violations}",
                audit_log_ref=f"decision_log/{case_id}.jsonl",
                agent_telemetry=_telemetry.get_collected(),
            )

        # STEP 7 — Reasoning Drafter (Agent 4)
        reasoning_brief = await reasoning_drafter.run(findings, context, policy_map, case_id)
        check_ai_decision_limit(reasoning_brief, "reasoning_drafter")

        # STEP 8 — Source Verification Gate
        sv_result = verify(reasoning_brief)
        if not sv_result.passed:
            try:
                _log_escalation(case_id, "source_verification_failed", sv_result.violations)
            except BilateralLoggerError:
                # Escalation logging failed — audit trail integrity is at risk.
                # Fail-closed: propagate the error, do not emit a partial determination.
                raise
            return PipelineResult(
                case_id=case_id,
                status="escalated",
                determination=None,
                escalation_reason=f"source_verification_failed: {sv_result.violations}",
                audit_log_ref=f"decision_log/{case_id}.jsonl",
                agent_telemetry=_telemetry.get_collected(),
            )

        # STEP 9 — Bilateral Logger PRE-WRITE (write-before-emit)
        pre_state = _build_pre_state_record(
            case_id, submission, findings, context, policy_map, reasoning_brief
        )
        get_logger().commit(case_id, pre_state)
        # If this raises BilateralLoggerError → propagates up, do not emit

        # STEP 10 — Return reasoning_brief for nurse review
        # The full per-agent outputs are returned so a pipeline-trace UI
        # can show every stage. Production-mode consumers ignore the
        # findings field and read only reasoning_brief + policy_map +
        # context + classification (the nurse-facing data).
        determination = {
            "case_id": case_id,
            "status": "pending_nurse_review",
            "classification": classification,  # NEW Phase 3b: cancer type, stage, therapy, urgency
            "findings": findings,
            "context": context,
            "policy_map": policy_map,
            "reasoning_brief": reasoning_brief,
            "audit_log_ref": f"decision_log/{case_id}.jsonl"
        }

        return PipelineResult(
            case_id=case_id,
            status="completed",
            determination=determination,
            escalation_reason=None,
            audit_log_ref=f"decision_log/{case_id}.jsonl",
            agent_telemetry=_telemetry.get_collected(),
        )

    except (BilateralLoggerError, AIDecisionAttemptError) as exc:
        return PipelineResult(
            case_id=case_id,
            status="failed",
            determination=None,
            escalation_reason=str(exc),
            audit_log_ref=f"decision_log/{case_id}.jsonl",
            agent_telemetry=_telemetry.get_collected(),
        )
    except Exception as exc:
        return PipelineResult(
            case_id=case_id,
            status="failed",
            determination=None,
            escalation_reason=f"unexpected_error: {exc}",
            audit_log_ref=f"decision_log/{case_id}.jsonl",
            agent_telemetry=_telemetry.get_collected(),
        )


# ---------------------------------------------------------------------------
# Nurse decision recording
# ---------------------------------------------------------------------------

def record_nurse_decision(
    case_id: str,
    action: str,
    rationale: str,
    physician_queue: "PhysicianQueue | None" = None,
) -> PipelineResult:
    """
    Record a nurse's decision after reviewing the AI brief.

    - Runs Denial Gate check on action (MVP block mode by default, route mode with physician_queue)
    - Writes post-state record to bilateral logger (write-before-emit)
    - Returns PipelineResult with final determination

    Args:
        case_id:   The case identifier.
        action:    "approve" | "escalate" | "pend" (or "deny" in route mode with physician record).
        rationale: Required nurse rationale (non-empty).
        physician_queue: Optional PhysicianQueue for route mode denial validation.

    Raises:
        ValueError: if rationale is empty or whitespace-only.
        DenialAttemptError: if action is "deny" without proper physician authorization.
        BilateralLoggerError: if logger fails to commit.
    """
    if not rationale or not rationale.strip():
        raise ValueError("Nurse rationale is required and cannot be empty.")

    # Denial Gate (pass case_id + physician_queue for route mode support)
    check_denial({"path": action, "case_id": case_id}, physician_queue=physician_queue)

    # Post-state bilateral log record
    post_state = {
        "type": "nurse_action_record",
        "case_id": case_id,
        "nurse_decision": action,
        "denial_gate_mode": os.environ.get("DENIAL_GATE_MODE", "block"),
        "rationale": rationale,
        "at": _now_iso(),
    }
    get_logger().commit(case_id, post_state)

    # Phase 2 handoff: an "escalate" action puts the case on the physician queue.
    # Lazy-init the default queue if no explicit one was provided. Idempotent —
    # if the case is already pending on the queue, we silently skip (avoids
    # double-enqueue when a nurse hits escalate twice).
    if action == "escalate":
        if physician_queue is None:
            from physician_queue import get_queue
            physician_queue = get_queue()
        from physician_queue import FilePhysicianQueueError
        try:
            physician_queue.enqueue(
                case_id=case_id,
                reason="nurse_escalated",
                nurse_note=rationale,
            )
        except FilePhysicianQueueError as exc:
            # duplicate_pending is the only expected error here — case is
            # already on the queue from a prior escalation. Safe to skip.
            if getattr(exc, "reason", "") == "duplicate_pending":
                pass  # silently skip; case already queued
            else:
                # Unexpected physician-queue error. Audit to system_failures and re-raise.
                failure_record = {
                    "type": "physician_enqueue_error",
                    "case_id": case_id,
                    "reason": getattr(exc, "reason", "unknown"),
                    "detail": str(exc),
                    "at": _now_iso(),
                }
                try:
                    get_logger().commit(case_id, failure_record)
                except BilateralLoggerError:
                    pass  # audit failure, but we still need to raise the original error
                raise
        except Exception as exc:
            # Non-queue errors (e.g., file system, permissions). Audit and fail-closed.
            failure_record = {
                "type": "physician_enqueue_error",
                "case_id": case_id,
                "reason": "unexpected_error",
                "detail": str(exc),
                "at": _now_iso(),
            }
            try:
                get_logger().commit(case_id, failure_record)
            except BilateralLoggerError:
                pass  # audit failure, but we still need to raise the original error
            raise

    determination = {
        "case_id": case_id,
        "path": action,
        "rationale": rationale,
        "audit_log_ref": f"decision_log/{case_id}.jsonl",
        "at": _now_iso(),
    }

    return PipelineResult(
        case_id=case_id,
        status="completed",
        determination=determination,
        escalation_reason=None,
        audit_log_ref=f"decision_log/{case_id}.jsonl"
    )
