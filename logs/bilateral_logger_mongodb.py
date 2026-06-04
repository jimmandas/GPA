"""
MongoDB-backed bilateral logger for GPA audit trail.

Mirrors bilateral_logger.py but writes to MongoDB instead of JSONL.
Preserves write-before-emit semantics and cryptographic signing.

Each commit():
  1. Computes prev_record_hash (existing hash-chain logic)
  2. Signs record with RSA-PSS SHA-256 (jws_signature field)
  3. Atomically appends to MongoDB case.records array
  4. On failure: raises BilateralLoggerError (fail-closed)
"""

import hashlib
import json
import pathlib
import base64
from datetime import datetime, timezone
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

from persistence.mongo_client import CaseStore


GENESIS_PREV = "sha256:" + "0" * 64


def _canonical_hash(record: dict) -> str:
    """Compute SHA-256 hash of record in canonical form."""
    canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


class BilateralLoggerError(Exception):
    """Raised when MongoDB write fails."""

    def __init__(self, case_id: str, reason: str, detail: str) -> None:
        self.case_id = case_id
        self.reason = reason
        self.detail = detail
        super().__init__(f"BilateralLoggerError: case_id={case_id}, reason={reason}, detail={detail}")


class BilateralLoggerMongoDB:
    """
    Bilateral logger backed by MongoDB.

    Write-before-emit: record is persisted to MongoDB with durability
    guarantee before commit() returns. On failure, raises BilateralLoggerError.
    """

    def __init__(self, case_store: CaseStore) -> None:
        """
        Initialize with MongoDB case store.

        Args:
            case_store: Instance of MongoDBCaseStore
        """
        self.case_store = case_store
        self._private_key = self._load_private_key()

    def _load_private_key(self):
        """Load RSA private key from config/private_key.pem."""
        key_path = pathlib.Path(__file__).parent.parent / "config" / "private_key.pem"
        with key_path.open("rb") as f:
            return serialization.load_pem_private_key(
                f.read(),
                password=None,
                backend=default_backend()
            )

    def _sign_record(self, record: dict) -> str:
        """
        Sign record with RSA-PSS SHA-256.

        Returns base64-encoded signature string.
        Signature is computed over canonical JSON including prev_record_hash.
        """
        canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
        signature_bytes = self._private_key.sign(
            canonical.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH
            ),
            hashes.SHA256()
        )
        return base64.b64encode(signature_bytes).decode('ascii')

    def commit(self, case_id: str, record: dict) -> None:
        """
        Commit a signed record to MongoDB (write-before-emit).

        Args:
            case_id: Unique case identifier
            record: Event record to append

        Raises:
            BilateralLoggerError if write fails
        """
        # 1. Compute hash chain: prev_record_hash ties to prior record
        records = self.case_store.get_case_records(case_id)
        if not records:
            prev_hash = GENESIS_PREV
        else:
            prev_hash = _canonical_hash(records[-1])

        record["prev_record_hash"] = prev_hash

        # 2. Sign the record (includes prev_record_hash in signature)
        record["jws_signature"] = self._sign_record(record)

        # 3. Write to MongoDB (atomic $push, write concern w=1)
        try:
            self.case_store.append_record(case_id, record)
        except Exception as e:
            raise BilateralLoggerError(
                case_id,
                "mongo_write_error",
                str(e)
            ) from e
