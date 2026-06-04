"""
Persistence layer factory for GPA audit trail storage.

Provides get_case_store() singleton factory to switch between JSONL (Phase 3a)
and MongoDB (Phase 3b+) storage backends via environment variable.

Usage:
  from persistence import get_case_store
  store = get_case_store()
  store.append_record(case_id, record)
"""

import os
import pathlib
from typing import Optional

from .mongo_client import CaseStore, MongoDBCaseStore, JSONLCaseStore

_case_store: Optional[CaseStore] = None


def get_case_store() -> CaseStore:
    """
    Factory: returns CaseStore instance based on PERSISTENCE_MODE.

    Modes:
      - "jsonl" (default): File-based JSONL (Phase 3a)
      - "mongodb": MongoDB-backed (Phase 3b+)

    Environment Variables:
      - PERSISTENCE_MODE: "jsonl" or "mongodb"
      - MONGODB_URI: MongoDB connection string (defaults to localhost:27017)

    Returns:
        CaseStore instance (singleton pattern within a session)
    """
    global _case_store

    if _case_store is not None:
        return _case_store

    mode = os.getenv("PERSISTENCE_MODE", "jsonl").lower()

    if mode == "mongodb":
        mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
        _case_store = MongoDBCaseStore(mongo_uri)
    elif mode == "jsonl":
        log_dir = pathlib.Path(__file__).parent.parent / "decision_log"
        _case_store = JSONLCaseStore(log_dir)
    else:
        raise ValueError(
            f"Unknown PERSISTENCE_MODE: {mode!r}. "
            f"Expected 'jsonl' or 'mongodb'."
        )

    return _case_store


def reset_case_store() -> None:
    """Reset the singleton (used in testing)."""
    global _case_store
    if _case_store is not None:
        if hasattr(_case_store, "close"):
            _case_store.close()
    _case_store = None
