"""
MongoDB-backed case storage for GPA audit trail.

Provides CaseStore ABC interface with MongoDBCaseStore implementation.
Preserves write-before-emit semantics using MongoDB write concern (w=1 default).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import os
import pymongo
from pymongo import MongoClient, ASCENDING


class CaseStore(ABC):
    """Abstract interface for case audit record storage."""

    @abstractmethod
    def append_record(self, case_id: str, record: dict) -> None:
        """
        Append a signed audit record to a case's history.

        Args:
            case_id: Unique case identifier
            record: Dict with prev_record_hash, jws_signature, and event data

        Raises:
            Exception if write fails (write-before-emit)
        """
        pass

    @abstractmethod
    def get_case_records(self, case_id: str) -> List[dict]:
        """
        Retrieve all records for a case in order (oldest first).

        Args:
            case_id: Unique case identifier

        Returns:
            List of records with prev_record_hash and jws_signature fields
        """
        pass

    @abstractmethod
    def find_by_status(self, status: str, limit: int = 100) -> List[dict]:
        """
        Query cases by current status (for dashboards).

        Args:
            status: Status value (e.g., 'pending', 'completed', 'escalated')
            limit: Max number of results

        Returns:
            List of case documents with summary metadata
        """
        pass

    @abstractmethod
    def get_case_summary(self, case_id: str) -> Optional[dict]:
        """
        Get case metadata without full record history.

        Args:
            case_id: Unique case identifier

        Returns:
            Case doc with status, created_at, updated_at, or None if not found
        """
        pass

    @abstractmethod
    def mark_exported(self, case_id: str) -> None:
        """Mark a case as exported to the signed JSONL archive."""
        pass


class MongoDBCaseStore(CaseStore):
    """MongoDB implementation of CaseStore."""

    def __init__(self, mongo_uri: Optional[str] = None):
        """
        Initialize MongoDB connection.

        Args:
            mongo_uri: Connection string (defaults to env var MONGODB_URI or localhost)
        """
        uri = mongo_uri or os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)

        # Verify connection
        try:
            self.client.admin.command("ping")
        except pymongo.errors.ServerSelectionTimeoutError as e:
            raise RuntimeError(f"MongoDB connection failed: {e}") from e

        self.db = self.client["gpa_audit"]
        self.cases = self.db["cases"]

        # Ensure indexes for query performance
        self.cases.create_index([("case_id", ASCENDING)], unique=True)
        self.cases.create_index([("status", ASCENDING)])
        self.cases.create_index([("created_at", ASCENDING)])
        self.cases.create_index([("exported", ASCENDING)])

    def append_record(self, case_id: str, record: dict) -> None:
        """Atomically append signed record to case.records array."""
        now = datetime.now(timezone.utc)

        try:
            result = self.cases.update_one(
                {"case_id": case_id},
                {
                    "$push": {"records": record},
                    "$set": {
                        "status": record.get("status", "pending"),
                        "updated_at": now
                    },
                    "$setOnInsert": {
                        "created_at": now,
                        "exported": False
                    }
                },
                upsert=True
            )

            if result.matched_count == 0 and result.upserted_id is None:
                raise pymongo.errors.OperationFailure("append_record: update failed")

        except pymongo.errors.PyMongoError as e:
            raise RuntimeError(f"MongoDB write failed for case {case_id}: {e}") from e

    def get_case_records(self, case_id: str) -> List[dict]:
        """Retrieve full record history for a case."""
        case = self.cases.find_one({"case_id": case_id})
        return case.get("records", []) if case else []

    def find_by_status(self, status: str, limit: int = 100, exported_only: bool = False) -> List[dict]:
        """Query cases by status, optionally filtering for exported status."""
        query = {"status": status}
        if exported_only:
            query["exported"] = True

        return list(
            self.cases.find(query)
            .sort("created_at", -1)
            .limit(limit)
        )

    def get_case_summary(self, case_id: str) -> Optional[dict]:
        """Get case metadata (without full records array)."""
        return self.cases.find_one(
            {"case_id": case_id},
            {"records": 0}  # Exclude full record history
        )

    def mark_exported(self, case_id: str) -> None:
        """Mark a case as exported to the signed JSONL archive."""
        self.cases.update_one(
            {"case_id": case_id},
            {"$set": {"exported": True}}
        )

    def close(self) -> None:
        """Close MongoDB connection."""
        self.client.close()


class JSONLCaseStore(CaseStore):
    """
    Fallback JSONL-based case storage (Phase 3a default).

    This is a minimal shim to support persistence factory mode toggling.
    Full JSONL implementation lives in bilateral_logger.py (write-before-emit).
    """

    def __init__(self, log_dir):
        self.log_dir = log_dir

    def append_record(self, case_id: str, record: dict) -> None:
        """Not implemented; bilateral_logger handles JSONL writes."""
        raise NotImplementedError("JSONL writes happen via bilateral_logger.commit()")

    def get_case_records(self, case_id: str) -> List[dict]:
        """Stub for factory pattern compatibility."""
        raise NotImplementedError("Use bilateral_logger for JSONL reads")

    def find_by_status(self, status: str, limit: int = 100) -> List[dict]:
        raise NotImplementedError("JSONL queries not yet implemented")

    def get_case_summary(self, case_id: str) -> Optional[dict]:
        raise NotImplementedError("JSONL summary not implemented")

    def mark_exported(self, case_id: str) -> None:
        raise NotImplementedError("JSONL export not yet implemented")
