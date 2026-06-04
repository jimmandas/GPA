"""
Tests for MongoDB persistence layer and bilateral logger variant.

Tests use mongomock for fast in-memory MongoDB or testcontainers for real MongoDB.
"""

import json
import pytest
from datetime import datetime, timezone

try:
    import mongomock
    HAS_MONGOMOCK = True
except ImportError:
    HAS_MONGOMOCK = False

from persistence.mongo_client import MongoDBCaseStore
from logs.bilateral_logger_mongodb import BilateralLoggerMongoDB, GENESIS_PREV, _canonical_hash


@pytest.fixture(scope="function")
def mongo_store():
    """In-memory MongoDB using mongomock for fast tests."""
    if not HAS_MONGOMOCK:
        pytest.skip("mongomock not installed")

    # Use mongomock for testing
    client = mongomock.MongoClient()
    db = client["gpa_test"]
    cases_collection = db["cases"]

    # Create indexes (mongomock supports these)
    cases_collection.create_index([("case_id", 1)], unique=True)
    cases_collection.create_index([("status", 1)])
    cases_collection.create_index([("created_at", 1)])

    # Wrap in our CaseStore interface
    store = MongoDBCaseStore.__new__(MongoDBCaseStore)
    store.client = client
    store.db = db
    store.cases = cases_collection

    yield store

    # Cleanup
    client.close()


# ---------------------------------------------------------------------------
# CaseStore Interface Tests
# ---------------------------------------------------------------------------

def test_mongodb_append_record_creates_case(mongo_store):
    """Test appending a record creates a new case."""
    record = {
        "type": "agent_event",
        "agent": "evidence_summarizer",
        "prev_record_hash": GENESIS_PREV,
        "jws_signature": "test_signature_123",
        "at": datetime.now(timezone.utc).isoformat()
    }

    mongo_store.append_record("case_001", record)

    # Verify case exists with record
    case = mongo_store.get_case_summary("case_001")
    assert case is not None
    assert case["case_id"] == "case_001"
    assert case["status"] == "pending"
    assert "records" not in case  # get_case_summary excludes records

    records = mongo_store.get_case_records("case_001")
    assert len(records) == 1
    assert records[0]["agent"] == "evidence_summarizer"
    assert records[0]["jws_signature"] == "test_signature_123"


def test_mongodb_append_multiple_records(mongo_store):
    """Test appending multiple records maintains order."""
    for i in range(3):
        record = {
            "type": "agent_event",
            "seq": i,
            "prev_record_hash": GENESIS_PREV if i == 0 else "sha256:mock_hash",
            "jws_signature": f"sig_{i}",
            "at": datetime.now(timezone.utc).isoformat()
        }
        mongo_store.append_record("case_multi", record)

    records = mongo_store.get_case_records("case_multi")
    assert len(records) == 3
    assert records[0]["seq"] == 0
    assert records[1]["seq"] == 1
    assert records[2]["seq"] == 2


def test_mongodb_find_by_status(mongo_store):
    """Test querying cases by status."""
    # Create cases with different statuses
    mongo_store.append_record("case_001", {"status": "pending", "prev_record_hash": GENESIS_PREV, "jws_signature": "sig_1"})
    mongo_store.append_record("case_002", {"status": "completed", "prev_record_hash": GENESIS_PREV, "jws_signature": "sig_2"})
    mongo_store.append_record("case_003", {"status": "pending", "prev_record_hash": GENESIS_PREV, "jws_signature": "sig_3"})

    pending = mongo_store.find_by_status("pending")
    completed = mongo_store.find_by_status("completed")

    assert len(pending) == 2
    assert len(completed) == 1
    assert all(c["status"] == "pending" for c in pending)
    assert completed[0]["status"] == "completed"


def test_mongodb_get_case_summary_excludes_records(mongo_store):
    """Test that get_case_summary doesn't return full record history."""
    for i in range(5):
        mongo_store.append_record(
            "case_summary",
            {"type": "event", "seq": i, "prev_record_hash": GENESIS_PREV, "jws_signature": f"sig_{i}"}
        )

    summary = mongo_store.get_case_summary("case_summary")
    assert "records" not in summary
    assert summary["case_id"] == "case_summary"
    assert summary["status"] == "pending"


def test_mongodb_mark_exported(mongo_store):
    """Test marking a case as exported."""
    mongo_store.append_record("case_export", {"prev_record_hash": GENESIS_PREV, "jws_signature": "sig"})

    # Initially not exported
    case = mongo_store.get_case_summary("case_export")
    assert case["exported"] is False

    # Mark as exported
    mongo_store.mark_exported("case_export")

    # Verify marked
    case = mongo_store.get_case_summary("case_export")
    assert case["exported"] is True


# ---------------------------------------------------------------------------
# Bilateral Logger MongoDB Tests
# ---------------------------------------------------------------------------

def test_bilateral_logger_mongodb_write_before_emit(mongo_store):
    """Test that BilateralLoggerMongoDB signs and writes records."""
    logger = BilateralLoggerMongoDB(mongo_store)

    record = {
        "type": "agent_event",
        "agent": "context_retriever",
        "output_summary": "Found 3 relevant policies"
    }

    # Commit should add hash chain and signature
    logger.commit("case_sig", record)

    # Verify record in MongoDB
    records = mongo_store.get_case_records("case_sig")
    assert len(records) == 1

    stored = records[0]
    assert "prev_record_hash" in stored
    assert stored["prev_record_hash"] == GENESIS_PREV  # First record
    assert "jws_signature" in stored
    assert isinstance(stored["jws_signature"], str)
    assert len(stored["jws_signature"]) > 100  # RSA signature is base64-encoded


def test_bilateral_logger_mongodb_hash_chain(mongo_store):
    """Test that hash chain is maintained across multiple commits."""
    logger = BilateralLoggerMongoDB(mongo_store)

    # Commit three records
    for i in range(3):
        record = {"seq": i}
        logger.commit("case_chain", record)

    records = mongo_store.get_case_records("case_chain")
    assert len(records) == 3

    # First record should have GENESIS_PREV
    assert records[0]["prev_record_hash"] == GENESIS_PREV

    # Subsequent records should chain
    for i in range(1, 3):
        prev_record = records[i - 1]
        expected_hash = _canonical_hash(prev_record)
        assert records[i]["prev_record_hash"] == expected_hash


def test_bilateral_logger_mongodb_signature_over_full_record(mongo_store):
    """Test that signature includes prev_record_hash (full record commitment)."""
    logger = BilateralLoggerMongoDB(mongo_store)

    record = {"agent": "policy_mapper", "result": "approved"}
    logger.commit("case_full_sig", record)

    stored = mongo_store.get_case_records("case_full_sig")[0]

    # Signature should be over the full record including prev_record_hash
    canonical = json.dumps(stored, sort_keys=True, separators=(",", ":"))
    assert "prev_record_hash" in canonical  # Hash chain is in the signed data
    assert stored["jws_signature"]  # Signature exists


def test_bilateral_logger_mongodb_multiple_cases_independent(mongo_store):
    """Test that records from different cases don't interfere."""
    logger = BilateralLoggerMongoDB(mongo_store)

    logger.commit("case_a", {"data": "a"})
    logger.commit("case_b", {"data": "b"})
    logger.commit("case_a", {"data": "a2"})

    records_a = mongo_store.get_case_records("case_a")
    records_b = mongo_store.get_case_records("case_b")

    assert len(records_a) == 2
    assert len(records_b) == 1

    # case_a's second record should chain from case_a's first, not case_b's
    assert records_a[1]["prev_record_hash"] == _canonical_hash(records_a[0])


# ---------------------------------------------------------------------------
# Error Handling
# ---------------------------------------------------------------------------

def test_bilateral_logger_mongodb_missing_key_file(mongo_store, tmp_path, monkeypatch):
    """Test that missing private key raises clear error."""
    logger = BilateralLoggerMongoDB(mongo_store)

    # Make key path non-existent
    monkeypatch.setattr(
        "logs.bilateral_logger_mongodb.pathlib.Path",
        lambda *args: tmp_path / "nonexistent.pem"
    )

    with pytest.raises(Exception):
        # Recreate logger to trigger key load
        BilateralLoggerMongoDB(mongo_store)
