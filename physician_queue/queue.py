"""
physician_queue/queue.py — PhysicianQueue interface + FilePhysicianQueue.

The queue accepts cases the Denial Gate routes to physician review. A
physician dequeues, reviews, and records an action (approve / deny /
request_additional_evidence). Every action requires:

  - clinical_basis  (free text, non-empty)
  - guideline_citation (a source_ref string from the ALLOWED set OR a
    real NCCN passage_id)
  - evidence_gaps   (list of strings; empty list is allowed but explicit)

The interface is intentionally narrow:
  enqueue(case_id, reason, ai_brief)             -> QueueEntry
  list_pending()                                  -> list[QueueEntry]
  get(case_id)                                    -> QueueEntry | None
  record_action(case_id, action, rationale, ...) -> ActionRecord

FilePhysicianQueue persists state in a single JSON file (gitignored). It's
the bridge implementation — same pattern as FixtureRetriever bridging into
ChromaRetriever. Future PostgresPhysicianQueue / SQSPhysicianQueue
implementations satisfy the same contract.

See ADR-014.
"""

from __future__ import annotations

import json
import pathlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from logs.bilateral_logger import BilateralLogger


# ---------------------------------------------------------------------------
# Enums + dataclasses
# ---------------------------------------------------------------------------

class QueueState(str, Enum):
    """Lifecycle states for a queued case."""
    PENDING = "pending"        # awaiting physician dequeue
    IN_REVIEW = "in_review"    # physician has picked it up
    COMPLETED = "completed"    # action recorded
    RETURNED = "returned"      # request_additional_evidence sent back


class PhysicianAction(str, Enum):
    """Actions a physician may record on a queued case."""
    APPROVE = "approve"                                  # concurs with nurse approval
    DENY = "deny"                                        # denial — requires full rationale
    REQUEST_ADDITIONAL_EVIDENCE = "request_additional_evidence"  # bounces back to nurse


@dataclass
class QueueEntry:
    """An item on the physician queue."""

    case_id: str
    reason: str                                          # why this case was routed
    state: QueueState = QueueState.PENDING
    enqueued_at: str = ""
    ai_brief_summary: str = ""                           # short summary for the queue view
    nurse_note: str = ""                                 # optional nurse comment
    physician_id: str = ""                               # set when picked up
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class ActionRecord:
    """Outcome of a physician's review of a queued case."""

    case_id: str
    action: PhysicianAction
    physician_id: str
    clinical_basis: str                                  # required non-empty
    guideline_citation: str                              # required: source_ref or passage_id
    evidence_gaps: list[str] = field(default_factory=list)
    rationale: str = ""                                  # optional longer narrative
    recorded_at: str = ""


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class PhysicianQueue(ABC):
    """Abstract contract. All physician queue implementations satisfy this."""

    @abstractmethod
    def enqueue(self, case_id: str, reason: str, ai_brief_summary: str = "", nurse_note: str = "") -> QueueEntry:
        raise NotImplementedError

    @abstractmethod
    def list_pending(self) -> list[QueueEntry]:
        raise NotImplementedError

    @abstractmethod
    def get(self, case_id: str) -> QueueEntry | None:
        raise NotImplementedError

    @abstractmethod
    def record_action(
        self,
        case_id: str,
        action: PhysicianAction,
        physician_id: str,
        clinical_basis: str,
        guideline_citation: str,
        evidence_gaps: list[str] | None = None,
        rationale: str = "",
        logger: "BilateralLogger | None" = None,
    ) -> ActionRecord:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# FilePhysicianQueue — JSON-file-backed implementation
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-5] + "Z"


class FilePhysicianQueueError(Exception):
    """Raised on invalid queue operations (empty rationale, missing case, etc.)."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{reason}] {detail}")


class FilePhysicianQueue(PhysicianQueue):
    """
    JSON-file-backed physician queue.

    Storage format (`physician_queue/state.json`):
      {
        "entries": [QueueEntry, ...],
        "actions": [ActionRecord, ...]
      }

    Single-writer assumption — no concurrent-physician handling. Phase 2
    follow-up: replace with Postgres + row locks if multi-physician
    concurrency becomes a real requirement.
    """

    def __init__(self, state_path: pathlib.Path):
        self.state_path = state_path
        self.state_path.parent.mkdir(parents=True, exist_ok=True)

    # --- persistence helpers -----------------------------------------------

    def _read(self) -> dict[str, list]:
        if not self.state_path.exists():
            return {"entries": [], "actions": []}
        try:
            return json.loads(self.state_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise FilePhysicianQueueError(
                "corrupt_state",
                f"Queue state file is not valid JSON: {self.state_path} ({exc})",
            ) from exc

    def _write(self, state: dict[str, list]) -> None:
        # Atomic write via tmp file + replace; same defensive pattern as
        # the bilateral logger.
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(state, indent=2, default=_serialize_default), encoding="utf-8")
        tmp.replace(self.state_path)

    # --- interface methods --------------------------------------------------

    def enqueue(
        self,
        case_id: str,
        reason: str,
        ai_brief_summary: str = "",
        nurse_note: str = "",
    ) -> QueueEntry:
        if not case_id or not reason.strip():
            raise FilePhysicianQueueError(
                "invalid_enqueue",
                "enqueue requires non-empty case_id and reason",
            )

        state = self._read()
        # Reject duplicate-pending enqueues for the same case
        for entry_dict in state["entries"]:
            if entry_dict["case_id"] == case_id and entry_dict["state"] == QueueState.PENDING.value:
                raise FilePhysicianQueueError(
                    "duplicate_pending",
                    f"Case {case_id!r} is already pending in the physician queue.",
                )

        entry = QueueEntry(
            case_id=case_id,
            reason=reason,
            state=QueueState.PENDING,
            enqueued_at=_now_iso(),
            ai_brief_summary=ai_brief_summary,
            nurse_note=nurse_note,
        )
        state["entries"].append(asdict(entry))
        self._write(state)
        return entry

    def list_pending(self) -> list[QueueEntry]:
        state = self._read()
        return [
            _entry_from_dict(e)
            for e in state["entries"]
            if e["state"] == QueueState.PENDING.value
        ]

    def get(self, case_id: str) -> QueueEntry | None:
        state = self._read()
        for e in state["entries"]:
            if e["case_id"] == case_id:
                return _entry_from_dict(e)
        return None

    def record_action(
        self,
        case_id: str,
        action: PhysicianAction,
        physician_id: str,
        clinical_basis: str,
        guideline_citation: str,
        evidence_gaps: list[str] | None = None,
        rationale: str = "",
        logger: "BilateralLogger | None" = None,
    ) -> ActionRecord:
        # Validation — fail loud
        if not physician_id.strip():
            raise FilePhysicianQueueError(
                "missing_physician_id",
                "Every physician action must record a physician_id",
            )
        if not clinical_basis.strip():
            raise FilePhysicianQueueError(
                "missing_clinical_basis",
                "Every physician action must record a non-empty clinical_basis",
            )
        if not guideline_citation.strip():
            raise FilePhysicianQueueError(
                "missing_guideline_citation",
                "Every physician action must record a guideline_citation",
            )
        if action == PhysicianAction.DENY and not evidence_gaps:
            raise FilePhysicianQueueError(
                "deny_requires_evidence_gaps",
                "DENY actions must explicitly enumerate evidence_gaps (even if a "
                "short single-item list explaining why no further evidence is sought)",
            )

        state = self._read()
        # Find the entry and transition state
        for entry in state["entries"]:
            if entry["case_id"] == case_id and entry["state"] in (
                QueueState.PENDING.value, QueueState.IN_REVIEW.value
            ):
                new_state = (
                    QueueState.RETURNED.value
                    if action == PhysicianAction.REQUEST_ADDITIONAL_EVIDENCE
                    else QueueState.COMPLETED.value
                )
                break
        else:
            raise FilePhysicianQueueError(
                "case_not_in_queue",
                f"Case {case_id!r} has no pending or in-review entry in the queue",
            )

        record = ActionRecord(
            case_id=case_id,
            action=action,
            physician_id=physician_id,
            clinical_basis=clinical_basis,
            guideline_citation=guideline_citation,
            evidence_gaps=evidence_gaps or [],
            rationale=rationale,
            recorded_at=_now_iso(),
        )

        # Write-before-emit: commit the bilateral audit record first.
        # If the durable write fails, queue state is unchanged.
        # Lazy import to keep physician_queue free of logger dependency at import time.
        from logs.bilateral_logger import get_logger
        active_logger = logger if logger is not None else get_logger()
        audit_record = {
            "type": "physician_action_record",
            "case_id": case_id,
            "action": action.value,
            "physician_id": physician_id,
            "clinical_basis": clinical_basis,
            "guideline_citation": guideline_citation,
            "evidence_gaps": evidence_gaps or [],
            "rationale": rationale,
            "queue_state_after": new_state,
            "at": record.recorded_at,
        }
        active_logger.commit(case_id, audit_record)

        # Now update queue state (durable audit already committed)
        entry["state"] = new_state
        entry["physician_id"] = physician_id
        state["actions"].append(asdict(record))
        self._write(state)
        return record


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _serialize_default(obj):
    """Make dataclasses + enums serialize cleanly to JSON."""
    if isinstance(obj, Enum):
        return obj.value
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def _entry_from_dict(d: dict) -> QueueEntry:
    return QueueEntry(
        case_id=d["case_id"],
        reason=d["reason"],
        state=QueueState(d["state"]),
        enqueued_at=d.get("enqueued_at", ""),
        ai_brief_summary=d.get("ai_brief_summary", ""),
        nurse_note=d.get("nurse_note", ""),
        physician_id=d.get("physician_id", ""),
        extra=d.get("extra", {}),
    )


# ---------------------------------------------------------------------------
# Module-level singleton (mirror of logs.bilateral_logger.get_logger pattern)
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DEFAULT_STATE_PATH = _REPO_ROOT / "physician_queue" / "state.json"

_DEFAULT_QUEUE: "FilePhysicianQueue | None" = None


def get_queue() -> FilePhysicianQueue:
    """Return the module-level default FilePhysicianQueue singleton.

    The default state file is `physician_queue/state.json` at the repo root
    (gitignored). Tests should swap the singleton via monkeypatching
    `physician_queue.queue._DEFAULT_QUEUE` to a tmp_path-scoped instance.
    """
    global _DEFAULT_QUEUE
    if _DEFAULT_QUEUE is None:
        _DEFAULT_QUEUE = FilePhysicianQueue(_DEFAULT_STATE_PATH)
    return _DEFAULT_QUEUE
