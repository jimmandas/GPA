"""
Bilateral Logger — GPA v4

Provides write-before-emit durability guarantees for audit records.
Each commit() call:
  1. Appends a JSONL record to log_dir/{case_id}.jsonl
  2. Calls flush() + fsync() to ensure the write is durable before returning
  3. On fsync failure: truncates the partial write, records the failure to
     failures_file (best-effort), and raises BilateralLoggerError

The name "bilateral" reflects the dual commitment: the write must succeed
on both sides (process memory + durable storage) before the caller can
treat the record as committed.
"""

import json
import os
import pathlib
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Error class
# ---------------------------------------------------------------------------

class BilateralLoggerError(Exception):
    """Raised when the bilateral logger fails to commit a record to disk."""

    def __init__(self, case_id: str, reason: str, detail: str) -> None:
        self.case_id = case_id
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{reason}] case_id={case_id!r}: {detail}")


# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------

class BilateralLogger:
    """
    Append-only, fsync-backed JSONL logger.

    Each case_id gets its own file: log_dir/{case_id}.jsonl
    """

    def __init__(self, log_dir: pathlib.Path, failures_file: pathlib.Path) -> None:
        self._log_dir = log_dir
        self._failures_file = failures_file
        # Eagerly create the log directory.
        self._log_dir.mkdir(parents=True, exist_ok=True)

    def commit(self, case_id: str, record: dict) -> None:
        """
        Append record to log_dir/{case_id}.jsonl and fsync.

        Raises:
            BilateralLoggerError: if fsync fails. The partial write is
                truncated before raising so no corrupt line remains.
        """
        # Ensure log_dir exists (handles the case where it was deleted at runtime).
        self._log_dir.mkdir(parents=True, exist_ok=True)

        log_path = self._log_dir / f"{case_id}.jsonl"
        line = json.dumps(record, separators=(",", ":")) + "\n"

        with log_path.open("a", encoding="utf-8") as f:
            # Capture position before writing so we can roll back on fsync failure.
            pre_write_pos = f.tell()
            f.write(line)
            f.flush()

            try:
                os.fsync(f.fileno())
            except OSError as exc:
                # Roll back: truncate the partial write so no corrupt line remains.
                f.seek(pre_write_pos)
                f.truncate()

                # Write failure record to failures_file — best-effort, no fsync.
                self._write_failure_record(case_id, str(exc))

                raise BilateralLoggerError(
                    case_id=case_id,
                    reason="fsync_error",
                    detail=str(exc),
                ) from exc

    def _write_failure_record(self, case_id: str, detail: str) -> None:
        """Append a failure record to failures_file. Best-effort: never raises."""
        try:
            record = {
                "type": "bilateral_logger_failure",
                "case_id": case_id,
                "reason": "fsync_error",
                "detail": detail,
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            }
            with self._failures_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(record, separators=(",", ":")) + "\n")
                f.flush()
        except Exception:
            # Never recurse or surface failures_file errors.
            pass


# ---------------------------------------------------------------------------
# Default singleton
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
_DEFAULT_LOG_DIR = _REPO_ROOT / "decision_log"
_DEFAULT_FAILURES_FILE = _REPO_ROOT / "system_failures.jsonl"

_DEFAULT_LOGGER: "BilateralLogger | None" = None


def get_logger() -> BilateralLogger:
    """Return the module-level default BilateralLogger singleton."""
    global _DEFAULT_LOGGER
    if _DEFAULT_LOGGER is None:
        _DEFAULT_LOGGER = BilateralLogger(_DEFAULT_LOG_DIR, _DEFAULT_FAILURES_FILE)
    return _DEFAULT_LOGGER
