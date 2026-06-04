"""
JSONL-backed read store for GPA case audit records (Phase 3a default).

This is the READ side of the CaseStore abstraction over the file-based
decision_log/. Writes still flow through logs/bilateral_logger.py (which owns
the write-before-emit + fsync durability path); this store only reads back
what the bilateral logger has committed.

The point of this class is parity: the cases dashboard queries get_case_store(),
and the same UI works whether the backend is JSONL (here) or MongoDB. The only
behavioral difference is that mark_exported() is a no-op for JSONL — file-based
logs ARE the archive, so there is nothing to export.
"""

import json
import pathlib
from typing import List, Optional

from .mongo_client import CaseStore


# Status is derived from the latest nurse_action_record in a case's log.
# Mirrors api.main._case_status_from_decision_log so the dashboard and the
# nurse/audit views agree on a case's coarse status.
_NURSE_DECISION_TO_STATUS = {
    "approve": "approved",
    "escalate": "escalated",
    "pend": "pended",
}


def _derive_status(records: List[dict]) -> str:
    """Derive coarse case status from its record list (latest action wins)."""
    latest_action = None
    for rec in records:
        if rec.get("type") == "nurse_action_record":
            latest_action = rec.get("nurse_decision")
    return _NURSE_DECISION_TO_STATUS.get(latest_action, "pending_review")


def _record_timestamp(rec: dict) -> Optional[str]:
    """Best-effort ISO timestamp for a record (several field names in use)."""
    return rec.get("at") or rec.get("enqueued_at") or rec.get("recorded_at")


class JSONLCaseStore(CaseStore):
    """Read-only CaseStore over decision_log/*.jsonl (write path is bilateral_logger)."""

    def __init__(self, log_dir: pathlib.Path) -> None:
        self.log_dir = pathlib.Path(log_dir)

    # -- write side: owned by bilateral_logger, not this store ---------------

    def append_record(self, case_id: str, record: dict) -> None:
        raise NotImplementedError(
            "JSONL writes go through logs.bilateral_logger.commit() "
            "(write-before-emit + fsync). JSONLCaseStore is read-only."
        )

    def mark_exported(self, case_id: str) -> None:
        """No-op: file-based logs are themselves the immutable archive."""
        return None

    # -- read side -----------------------------------------------------------

    def get_case_records(self, case_id: str) -> List[dict]:
        """Return all records for a case in commit order (oldest first)."""
        log = self.log_dir / f"{case_id}.jsonl"
        if not log.exists():
            return []
        records: List[dict] = []
        try:
            with log.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
        except OSError:
            return []
        return records

    def get_case_summary(self, case_id: str) -> Optional[dict]:
        """Return case metadata (no full record history)."""
        log = self.log_dir / f"{case_id}.jsonl"
        if not log.exists():
            return None
        records = self.get_case_records(case_id)
        timestamps = [t for t in (_record_timestamp(r) for r in records) if t]
        return {
            "case_id": case_id,
            "status": _derive_status(records),
            "record_count": len(records),
            "created_at": timestamps[0] if timestamps else None,
            "updated_at": timestamps[-1] if timestamps else None,
            "exported": True,  # file IS the archive
        }

    def _all_case_ids(self) -> List[str]:
        if not self.log_dir.exists():
            return []
        return sorted(f.stem for f in self.log_dir.glob("case_*.jsonl"))

    def find_by_status(self, status: str, limit: int = 100) -> List[dict]:
        """Return case summaries matching a status (newest first)."""
        matches: List[dict] = []
        for case_id in self._all_case_ids():
            summary = self.get_case_summary(case_id)
            if summary and summary["status"] == status:
                matches.append(summary)
        matches.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        if limit is not None:
            matches = matches[:limit]
        return matches

    def list_all(self, limit: int = 200) -> List[dict]:
        """Return summaries for every case (newest first). Dashboard convenience."""
        summaries = [self.get_case_summary(cid) for cid in self._all_case_ids()]
        summaries = [s for s in summaries if s]
        summaries.sort(key=lambda s: s.get("updated_at") or "", reverse=True)
        if limit is not None:
            summaries = summaries[:limit]
        return summaries
