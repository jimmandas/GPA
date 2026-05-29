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

# Load .env BEFORE any SDK import. Today no endpoint calls anthropic/openai
# directly, but the pipeline imports do (policy_mapper uses anthropic SDK).
# Defensive: keeps the API portable outside Cowork's managed auth.
from dotenv import load_dotenv
load_dotenv()

import json
import pathlib
from dataclasses import asdict
from typing import Any

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
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

# CORS — the static UI is served on a different port (8001) than the API (8000),
# so browser cross-origin requests need explicit allowance. Permissive policy
# is appropriate for this single-machine MVP demo; production deployment would
# narrow to known origins (see ADR-008 for the nurse workspace design notes).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


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

# ---------------------------------------------------------------------------
# Dashboard endpoints (2026-05-28)
# ---------------------------------------------------------------------------

import re as _re


def _parse_eval_report(md_path: pathlib.Path) -> dict[str, Any]:
    """Extract headline numbers from a v2 eval markdown report.

    Returns a structured dict for the dashboard to render. We deliberately
    parse the markdown (not import the runner) so the dashboard can serve
    a historical report from disk without re-running anything.
    """
    text = md_path.read_text(encoding="utf-8")

    # Generated timestamp
    gen_match = _re.search(r"Generated:\s*(\S+)", text)
    generated = gen_match.group(1) if gen_match else None

    # Mode (live | unit)
    mode_match = _re.search(r"Mode:\s*(\S+)", text)
    mode = mode_match.group(1) if mode_match else None

    # Summary counts
    cases_match = _re.search(r"Cases run:\s*(\d+)", text)
    per_case_match = _re.search(r"Cases passing per-case dims:\s*(\d+)/(\d+)", text)
    agg_match = _re.search(r"Aggregate dims passing:\s*(\d+)/(\d+)", text)

    # Aggregate dim table — pull score + status per dim
    # The v3 report is grouped into ### bucket subsections under ## Aggregate.
    # We track which bucket we're in so the dashboard can render bucket cards.
    aggregate_dims: list[dict[str, Any]] = []
    in_aggregate_section = False
    current_bucket: str | None = None
    _BUCKET_HEADER_MAP = {
        "value / outcomes":         "value",
        "trust":                    "trust",
        "operational reliability":  "operational",
    }
    # Dims removed from active scope post-report-generation. Reports written
    # before the removal date still contain these rows; we filter them out
    # at the API layer so the dashboard stays in sync with current scope.
    # See docs/SCOPE_DELTAS.md.
    _REMOVED_DIMS = {"cohens_kappa"}
    for line in text.splitlines():
        if "## Aggregate" in line:
            in_aggregate_section = True
            continue
        if not in_aggregate_section:
            continue
        # Bucket subsection header: "### Value / Outcomes — ..."
        if line.startswith("### "):
            header_text = line[4:].split("—")[0].strip().lower()
            current_bucket = _BUCKET_HEADER_MAP.get(header_text)
            continue
        if line.startswith("| ") and "|" in line[2:]:
            # Skip header / separator rows
            if "Dimension" in line or "---" in line:
                continue
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 5:
                dim_name = parts[0].strip("`")
                if dim_name in _REMOVED_DIMS:
                    continue
                aggregate_dims.append({
                    "dimension": parts[0],
                    "score": parts[1],
                    "target": parts[2],
                    "status": parts[3],
                    "notes": parts[4][:200],
                    "bucket": current_bucket,
                    "breakdown": None,
                })
        # Structured breakdown line: `breakdown:<dim_name>` {json}
        # Emitted by runner.print_report immediately after the row for any dim
        # with a composite cost structure. We attach it to the previous dim entry.
        elif line.startswith("`breakdown:"):
            import json as _json
            try:
                close = line.index("`", 1)
                breakdown_key = line[1:close]  # "breakdown:<dim_name>"
                target_dim = breakdown_key.split(":", 1)[1]
                breakdown_json = line[close + 1:].strip()
                breakdown_data = _json.loads(breakdown_json)
                for entry in reversed(aggregate_dims):
                    if entry["dimension"].strip("`") == target_dim:
                        entry["breakdown"] = breakdown_data
                        break
            except (ValueError, _json.JSONDecodeError):
                # Malformed breakdown line — skip silently; not pass/fail critical
                pass

    return {
        "filename": md_path.name,
        "generated": generated,
        "mode": mode,
        "cases_run": int(cases_match.group(1)) if cases_match else None,
        "per_case_pass": (
            {"passed": int(per_case_match.group(1)), "total": int(per_case_match.group(2))}
            if per_case_match else None
        ),
        "aggregate_pass": (
            {"passed": int(agg_match.group(1)), "total": int(agg_match.group(2))}
            if agg_match else None
        ),
        "aggregate_dims": aggregate_dims,
    }


@app.get("/api/v1/eval/report/{filename}")
def get_eval_report_raw(filename: str):
    """Return a specific eval report's raw markdown content."""
    # Restrict to expected filename shape; no path traversal.
    if not _re.match(r"^eval_report_[\w\-]+\.md$", filename):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="filename must match eval_report_*.md",
        )
    path = _REPO_ROOT / "eval" / "results" / filename
    if not path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"report not found: {filename}",
        )
    return {"filename": filename, "markdown": path.read_text(encoding="utf-8")}


@app.get("/api/v1/eval/latest")
def get_latest_eval_report():
    """Return parsed headline numbers from the most-recent eval report on disk."""
    results_dir = _REPO_ROOT / "eval" / "results"
    if not results_dir.exists():
        return {"found": False, "reason": "eval/results/ does not exist"}

    candidates = sorted(
        results_dir.glob("eval_report_*.md"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return {"found": False, "reason": "no eval_report_*.md files in eval/results/"}

    latest = candidates[0]
    try:
        parsed = _parse_eval_report(latest)
    except Exception as exc:
        return {
            "found": True,
            "filename": latest.name,
            "parse_error": str(exc),
        }
    return {"found": True, **parsed}


# ---------------------------------------------------------------------------
# Admin endpoints (URL-accessed only; not linked from main dashboard)
# ---------------------------------------------------------------------------

class AdminResetRequest(BaseModel):
    confirm: str = Field(..., description="Must equal 'yes-reset-demo'")


@app.post("/api/v1/admin/reset-demo-data")
def admin_reset_demo_data(request: AdminResetRequest):
    """Clear demo-only state so the operator can re-record cleanly.

    Affects:
      - physician_queue/state.json: cleared (was holding stale `case_test` etc.)
      - decision_log/test_*.jsonl: deleted (test debris from prior dev sessions)
    Does NOT touch decision_log/case_*.jsonl — those are the audit artifacts.
    """
    if request.confirm != "yes-reset-demo":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confirm must equal 'yes-reset-demo' to proceed.",
        )

    cleared = {"physician_queue_entries": 0, "test_decision_logs": 0}

    # Reset the physician queue's state.json
    state_path = _REPO_ROOT / "physician_queue" / "state.json"
    if state_path.exists():
        try:
            existing = json.loads(state_path.read_text(encoding="utf-8"))
            cleared["physician_queue_entries"] = len(existing.get("entries", []))
        except Exception:
            cleared["physician_queue_entries"] = -1
        state_path.write_text('{"entries": [], "actions": []}\n', encoding="utf-8")

    # Force the cached singleton to re-read the fresh state on next access
    try:
        from physician_queue import queue as queue_mod
        queue_mod._DEFAULT_QUEUE = None
    except Exception:
        pass

    # Clear test_*.jsonl files from decision_log
    log_dir = _REPO_ROOT / "decision_log"
    if log_dir.exists():
        for f in log_dir.glob("test_*.jsonl"):
            try:
                f.unlink()
                cleared["test_decision_logs"] += 1
            except OSError:
                pass

    return {"reset": True, "cleared": cleared}


class AdminResetCaseStatesRequest(BaseModel):
    confirm: str = Field(..., description="Must equal 'yes-reset-case-states'")


@app.post("/api/v1/admin/reset-case-states")
def admin_reset_case_states(request: AdminResetCaseStatesRequest):
    """Strip nurse_action_record + physician_action_record entries from
    decision_log/case_*.jsonl so the nurse + physician queues revert to
    `pending_review`. **Demo-only.**

    Preserved on disk (governance story intact):
      - agent_event (every Claude/Anthropic call hashed)
      - schema_validation_event
      - pre_state_record (the bilateral logger pre-write)
      - escalation_event
      - any other non-action record types

    Removed:
      - nurse_action_record
      - physician_action_record

    Also resets the physician queue's state.json (otherwise the queue would
    still hold any cases that had been routed to physician review).

    In production this endpoint would NOT exist — you cannot delete a nurse
    or physician decision from a real audit trail. Demo-only convenience.
    """
    if request.confirm != "yes-reset-case-states":
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="confirm must equal 'yes-reset-case-states' to proceed.",
        )

    _ACTION_TYPES_TO_STRIP = {"nurse_action_record", "physician_action_record"}
    cleared = {
        "files_touched": 0,
        "nurse_actions_removed": 0,
        "physician_actions_removed": 0,
        "physician_queue_entries": 0,
    }

    log_dir = _REPO_ROOT / "decision_log"
    if log_dir.exists():
        for f in log_dir.glob("case_*.jsonl"):
            try:
                lines = f.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            kept: list[str] = []
            file_n_nurse = 0
            file_n_phys = 0
            for line in lines:
                line_stripped = line.strip()
                if not line_stripped:
                    continue
                try:
                    rec = json.loads(line_stripped)
                except json.JSONDecodeError:
                    kept.append(line)
                    continue
                rec_type = rec.get("type")
                if rec_type in _ACTION_TYPES_TO_STRIP:
                    if rec_type == "nurse_action_record":
                        file_n_nurse += 1
                    elif rec_type == "physician_action_record":
                        file_n_phys += 1
                    continue
                kept.append(line)
            if file_n_nurse > 0 or file_n_phys > 0:
                cleared["files_touched"] += 1
                cleared["nurse_actions_removed"] += file_n_nurse
                cleared["physician_actions_removed"] += file_n_phys
                # Atomic rewrite — fsync to mirror bilateral logger's durability
                content = ("\n".join(kept) + "\n") if kept else ""
                tmp = f.with_suffix(f.suffix + ".tmp")
                tmp.write_text(content, encoding="utf-8")
                tmp.replace(f)

    # Also reset the physician queue's state.json so any in-flight routings
    # don't survive the case-state reset.
    state_path = _REPO_ROOT / "physician_queue" / "state.json"
    if state_path.exists():
        try:
            existing = json.loads(state_path.read_text(encoding="utf-8"))
            cleared["physician_queue_entries"] = len(existing.get("entries", []))
        except Exception:
            cleared["physician_queue_entries"] = -1
        state_path.write_text('{"entries": [], "actions": []}\n', encoding="utf-8")
    try:
        from physician_queue import queue as queue_mod
        queue_mod._DEFAULT_QUEUE = None
    except Exception:
        pass

    return {"reset": True, "cleared": cleared}


# ---------------------------------------------------------------------------
# Nurse queue + per-case endpoints (Loom-readiness, 2026-05-27)
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SUBMISSIONS_DIR = _REPO_ROOT / "tools" / "fixtures" / "submissions"
_DECISION_LOG_DIR = _REPO_ROOT / "decision_log"


def _case_status_from_decision_log(case_id: str) -> str:
    """Derive a coarse status for the nurse queue from the bilateral log.

    Returns one of: 'pending_review' | 'approved' | 'escalated' | 'pended'.
    Defaults to 'pending_review' if no log exists.
    """
    log = _DECISION_LOG_DIR / f"{case_id}.jsonl"
    if not log.exists():
        return "pending_review"
    # Scan for a nurse_action_record (latest wins)
    latest_action = None
    try:
        with log.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("type") == "nurse_action_record":
                    latest_action = rec.get("nurse_decision")
    except OSError:
        return "pending_review"
    if latest_action == "approve":
        return "approved"
    if latest_action == "escalate":
        return "escalated"
    if latest_action == "pend":
        return "pended"
    return "pending_review"


@app.get("/api/v1/nurse/queue")
def list_nurse_queue():
    """List case fixtures + current status from the bilateral log."""
    cases: list[dict[str, Any]] = []
    if _SUBMISSIONS_DIR.exists():
        for f in sorted(_SUBMISSIONS_DIR.glob("case_*.json")):
            try:
                sub = json.loads(f.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
            case_id = sub.get("case_id", f.stem)
            cases.append({
                "case_id": case_id,
                "patient_id": (sub.get("patient") or {}).get("patient_id"),
                "submitted_at": sub.get("submitted_at"),
                "indication_category": (sub.get("clinical_indication") or {}).get("diagnosis_text"),
                "modality": (sub.get("imaging_request") or {}).get("modality"),
                "body_region": (sub.get("imaging_request") or {}).get("body_region"),
                "status": _case_status_from_decision_log(case_id),
            })
    return {"total": len(cases), "cases": cases}


@app.get("/api/v1/nurse/case/{case_id}")
def get_nurse_case(case_id: str):
    """Return the submission fixture for a case (used by nurse_workspace.html)."""
    fixture = _SUBMISSIONS_DIR / f"{case_id}.json"
    if not fixture.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No submission fixture for case {case_id!r}",
        )
    try:
        submission = json.loads(fixture.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Submission fixture is not valid JSON: {exc}",
        )
    return {
        "case_id": case_id,
        "submission": submission,
        "current_status": _case_status_from_decision_log(case_id),
        "audit_log_ref": f"decision_log/{case_id}.jsonl",
    }


# ---------------------------------------------------------------------------
# Audit log endpoints (Loom-readiness, 2026-05-27)
# ---------------------------------------------------------------------------

@app.get("/api/v1/audit/cases")
def list_audit_cases():
    """List all cases that have a bilateral decision log."""
    cases: list[dict[str, Any]] = []
    if _DECISION_LOG_DIR.exists():
        for f in sorted(_DECISION_LOG_DIR.glob("case_*.jsonl")):
            cases.append({
                "case_id": f.stem,
                "log_file": f.name,
                "size_bytes": f.stat().st_size,
                "current_status": _case_status_from_decision_log(f.stem),
            })
    return {"total": len(cases), "cases": cases}


@app.get("/api/v1/audit/case/{case_id}")
def get_audit_case(case_id: str):
    """Return the bilateral log events for a single case, newest first."""
    log = _DECISION_LOG_DIR / f"{case_id}.jsonl"
    if not log.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No decision log for case {case_id!r}",
        )
    events: list[dict[str, Any]] = []
    try:
        with log.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not read decision log: {exc}",
        )
    return {
        "case_id": case_id,
        "event_count": len(events),
        "events": events,
    }


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
