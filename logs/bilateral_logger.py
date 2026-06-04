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

import hashlib
import json
import os
import pathlib
import base64
from datetime import datetime, timezone
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend


# ---------------------------------------------------------------------------
# Hash-chaining constants and helpers
# ---------------------------------------------------------------------------

GENESIS_PREV = "sha256:" + "0" * 64


def _canonical_hash(record: dict) -> str:
	"""
	Compute SHA-256 hash of a record in canonical (sorted-key) form.
	Used for hash-chaining to detect tampering.
	"""
	canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
	return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


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
        # Load private key for JWS signatures (lazy-loaded on first use)
        self._private_key = None

    def commit(self, case_id: str, record: dict) -> None:
        """
        Append record to log_dir/{case_id}.jsonl and fsync.

        Each record includes prev_record_hash for cryptographic hash-chaining
        to detect tampering (mutation, reordering, deletion).

        Raises:
            BilateralLoggerError: if fsync fails. The partial write is
                truncated before raising so no corrupt line remains.
        """
        # Ensure log_dir exists (handles the case where it was deleted at runtime).
        self._log_dir.mkdir(parents=True, exist_ok=True)

        log_path = self._log_dir / f"{case_id}.jsonl"

        # Compute hash of the previous record (if it exists) to chain to.
        prev_hash = GENESIS_PREV
        if log_path.exists():
            with log_path.open("r", encoding="utf-8") as f:
                lines = f.readlines()
                if lines:
                    last_line = lines[-1].strip()
                    if last_line:
                        try:
                            last_record = json.loads(last_line)
                            prev_hash = _canonical_hash(last_record)
                        except (json.JSONDecodeError, ValueError):
                            # If the last record is corrupted, treat it as genesis.
                            prev_hash = GENESIS_PREV

        # Create a copy of the record to avoid mutating the caller's object.
        record_with_chain = dict(record)
        record_with_chain["prev_record_hash"] = prev_hash

        # Sign the record with JWS signature (computed over canonical JSON with hash chain)
        record_with_chain["jws_signature"] = self._sign_record(record_with_chain)

        line = json.dumps(record_with_chain, separators=(",", ":")) + "\n"

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

    def _load_private_key(self):
        """Load RSA private key from config/private_key.pem (lazy-loaded)."""
        if self._private_key is not None:
            return self._private_key

        key_path = pathlib.Path(__file__).parent.parent / "config" / "private_key.pem"
        if not key_path.exists():
            # Auto-generate if missing
            from config.key_generation import ensure_keys_exist
            ensure_keys_exist(key_path.parent)

        with key_path.open("rb") as f:
            self._private_key = serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend()
            )
        return self._private_key

    def _sign_record(self, record: dict) -> str:
        """
        Sign record with RSA private key using PSS padding.
        Returns base64-encoded signature.

        The signature is computed over the canonical (sorted-key) JSON of the record
        INCLUDING the prev_record_hash field.
        """
        private_key = self._load_private_key()
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        signature_bytes = private_key.sign(
            canonical.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature_bytes).decode('ascii')

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
