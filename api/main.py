"""
GPA v4 — Provider Explanation API
FastAPI app. Stateless. No auth in MVP.

Endpoints:
  POST /api/v1/pa/decide          — run full pipeline for a submission
  POST /api/v1/pa/nurse-decision  — record nurse decision after UI review
  GET  /api/v1/health             — liveness check
"""

from typing import Any

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from orchestrator.pipeline import _run_async, record_nurse_decision, PipelineResult
from gates.denial import DenialAttemptError
from logs.bilateral_logger import BilateralLoggerError


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
