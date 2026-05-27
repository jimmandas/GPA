"""
GPA v4 — Provider Explanation API
FastAPI app. Stateless. No auth in MVP.

Endpoints:
  POST /api/v1/pa/decide               — run full pipeline for a submission
  POST /api/v1/pa/nurse-decision       — record nurse decision after UI review
  GET  /api/v1/physician/queue         — list pending physician queue entries
  GET  /api/v1/physician/case/{id}     — get queue entry + AI brief for review
  POST /api/v1/physician/action        — record physician action (approve/deny/request_more)
  GET  /api/v1/health                  — liveness check
"""

import json
import pathlib
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from orchestrator.pipeline import _run_async, record_nurse_decision, PipelineResult
from gates.denial import DenialAttemptError
from logs.bilateral_logger import BilateralLoggerError
from physician_queue import get_queue, PhysicianAction, FilePhysicianQueueError


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class SubmissionRequest(BaseModel):
    case_id: str = Field(..., min_length=1)
    submitted_at: str
    patient: dict[str, Any]
    imaging_request: dict[str, Any]
    clinical_indication: dict[str, Any]
    policy_id: str = Field(..., min_length=1)


class NurseDecisionRequest(BaseModel):
    case_id: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|escalate|pend)$")
    rationale: str = Field(..., min_length=1)


class PipelineResponse(BaseModel):
    case_id: str
    status: str
    determination: dict[str, Any] | None
    escalation_reason: str | None
    audit_log_ref: str


class PhysicianActionRequest(BaseModel):
    case_id: str = Field(..., min_length=1)
    action: str = Field(..., pattern="^(approve|deny|request_additional_evidence)$")
    physician_id: str = Field(..., min_length=1)
    clinical_basis: str = Field(..., min_length=1)
    guideline_citation: str = Field(..., min_length=1)
    evidence_gaps: list[str] = Field(default_factory=list)
    rationale: str = ""


class PhysicianActionResponse(BaseModel):
    case_id: str
    action: str
    physician_id: str
    recorded_at: str
    queue_state_after: str


# ---------------------------------------------------------------------------
# App and endpoints
# ---------------------------------------------------------------------------

app = FastAPI(title="GPA v4 Provider Explanation API", version="1.0.0")


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "service": "gpa-v4"}


@app.post("/api/v1/pa/decide", response_model=PipelineResponse, status_code=status.HTTP_200_OK)
async def decide(request: SubmissionRequest):
    """
    Run the full GPA pipeline for a PA submission.
    Returns pending_nurse_review determination with AI brief.
    Write-before-emit honored: 500 returned on logger failure, no partial state.
    """
    submission = request.model_dump()
    try:
        result = await _run_async(submission)
    except BilateralLoggerError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logger failure — determination withheld: {exc}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Pipeline error: {exc}"
        )
    return PipelineResponse(
        case_id=result.case_id,
        status=result.status,
        determination=result.determination,
        escalation_reason=result.escalation_reason,
        audit_log_ref=result.audit_log_ref,
    )


@app.post("/api/v1/pa/nurse-decision", response_model=PipelineResponse, status_code=status.HTTP_200_OK)
def nurse_decision(request: NurseDecisionRequest):
    """
    Record nurse decision after UI review.
    Runs Denial Gate + bilateral post-write before returning.
    """
    try:
        result = record_nurse_decision(
            case_id=request.case_id,
            action=request.action,
            rationale=request.rationale,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except DenialAttemptError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except BilateralLoggerError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logger failure — determination withheld: {exc}"
        )
    return PipelineResponse(
        case_id=result.case_id,
        status=result.status,
        determination=result.determination,
        escalation_reason=result.escalation_reason,
        audit_log_ref=result.audit_log_ref,
    )


# ---------------------------------------------------------------------------
# Physician peer review endpoints (Phase 2 Week 11)
# ---------------------------------------------------------------------------

@app.get("/api/v1/physician/queue")
def list_physician_queue():
    """Return all pending physician queue entries, FIFO order."""
    q = get_queue()
    entries = q.list_pending()
    return {
        "pending_count": len(entries),
        "entries": [
            {
                "case_id": e.case_id,
                "reason": e.reason,
                "state": e.state.value,
                "enqueued_at": e.enqueued_at,
                "ai_brief_summary": e.ai_brief_summary,
                "nurse_note": e.nurse_note,
            }
            for e in entries
        ],
    }


@app.get("/api/v1/physician/case/{case_id}")
def get_physician_case(case_id: str):
    """Return the queue entry + audit log path for a single case."""
    q = get_queue()
    entry = q.get(case_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case {case_id!r} not in physician queue",
        )
    return {
        "case_id": entry.case_id,
        "reason": entry.reason,
        "state": entry.state.value,
        "enqueued_at": entry.enqueued_at,
        "ai_brief_summary": entry.ai_brief_summary,
        "nurse_note": entry.nurse_note,
        "physician_id": entry.physician_id,
        "audit_log_ref": f"decision_log/{case_id}.jsonl",
    }


@app.post("/api/v1/physician/action", response_model=PhysicianActionResponse, status_code=status.HTTP_200_OK)
def physician_action(request: PhysicianActionRequest):
    """
    Record a physician action against a queued case.
    Bilateral logger writes physician_action_record before queue state updates
    (write-before-emit). On logger failure, queue state is unchanged.
    """
    q = get_queue()
    try:
        action_enum = PhysicianAction(request.action)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Unknown action {request.action!r}",
        )

    try:
        record = q.record_action(
            case_id=request.case_id,
            action=action_enum,
            physician_id=request.physician_id,
            clinical_basis=request.clinical_basis,
            guideline_citation=request.guideline_citation,
            evidence_gaps=request.evidence_gaps,
            rationale=request.rationale,
        )
    except FilePhysicianQueueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except BilateralLoggerError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Logger failure — action withheld: {exc}",
        )

    # Fetch state-after via a fresh queue read
    entry = q.get(request.case_id)
    return PhysicianActionResponse(
        case_id=record.case_id,
        action=record.action.value,
        physician_id=record.physician_id,
        recorded_at=record.recorded_at,
        queue_state_after=entry.state.value if entry else "unknown",
    )
