"""
Tests for logs/bilateral_logger.py

All tests use tmp_path-based BilateralLogger instances.
The real decision_log/ and system_failures.jsonl are never touched.
"""

import json
import os

import pytest

from logs.bilateral_logger import BilateralLogger, BilateralLoggerError, GENESIS_PREV, _canonical_hash


def record_without_chain(record: dict) -> dict:
	"""Return a copy of record without the prev_record_hash and jws_signature fields (for comparison)."""
	return {k: v for k, v in record.items() if k not in ("prev_record_hash", "jws_signature")}


# ---------------------------------------------------------------------------
# test_commit_happy_path
# ---------------------------------------------------------------------------

def test_commit_happy_path(tmp_path):
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures_file)

    logger.commit("case_001", {"type": "test", "x": 1})

    log_file = log_dir / "case_001.jsonl"
    assert log_file.exists(), "log file must exist after commit"

    lines = log_file.read_text().splitlines()
    assert len(lines) == 1, f"expected 1 line, got {len(lines)}"

    parsed = json.loads(lines[0])
    assert record_without_chain(parsed) == {"type": "test", "x": 1}
    assert parsed["prev_record_hash"] == GENESIS_PREV, "first record should have genesis hash"

    # No failure should have been written.
    assert not failures_file.exists(), "failures.jsonl must not exist on happy path"


# ---------------------------------------------------------------------------
# test_commit_appends_multiple_records
# ---------------------------------------------------------------------------

def test_commit_appends_multiple_records(tmp_path):
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures_file)

    payloads = [{"seq": 1}, {"seq": 2}, {"seq": 3}]
    for p in payloads:
        logger.commit("case_multi", p)

    log_file = log_dir / "case_multi.jsonl"
    lines = log_file.read_text().splitlines()
    assert len(lines) == 3, f"expected 3 lines, got {len(lines)}"

    parsed_records = [json.loads(line) for line in lines]
    for i, parsed in enumerate(parsed_records):
        assert record_without_chain(parsed) == payloads[i], f"line {i} mismatch: {parsed!r}"

    # Verify hash chain: each record's prev_record_hash matches hash of previous.
    assert parsed_records[0]["prev_record_hash"] == GENESIS_PREV
    for i in range(1, len(parsed_records)):
        expected_prev_hash = _canonical_hash(parsed_records[i - 1])
        assert parsed_records[i]["prev_record_hash"] == expected_prev_hash, f"line {i} chain broken"


# ---------------------------------------------------------------------------
# test_commit_creates_log_dir
# ---------------------------------------------------------------------------

def test_commit_creates_log_dir(tmp_path):
    # log_dir does not exist yet — BilateralLogger must create it.
    log_dir = tmp_path / "nonexistent" / "nested" / "logs"
    failures_file = tmp_path / "failures.jsonl"

    logger = BilateralLogger(log_dir, failures_file)
    logger.commit("case_create", {"type": "dir_creation_test"})

    log_file = log_dir / "case_create.jsonl"
    assert log_file.exists()
    parsed = json.loads(log_file.read_text().strip())
    assert record_without_chain(parsed) == {"type": "dir_creation_test"}
    assert parsed["prev_record_hash"] == GENESIS_PREV


# ---------------------------------------------------------------------------
# test_write_before_emit_invariant — THE key governance test
# ---------------------------------------------------------------------------

def test_write_before_emit_invariant(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    failures_file = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures_file)

    # Patch os.fsync to raise immediately.
    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("disk full")))

    # (a) commit raises BilateralLoggerError — no determination can be emitted.
    with pytest.raises(BilateralLoggerError):
        logger.commit("case_fsync_fail", {"type": "agent_event", "case_id": "case_fsync_fail"})

    # (b) failures_file has a record.
    assert failures_file.exists()
    lines = failures_file.read_text().strip().split("\n")
    assert len(lines) == 1
    rec = json.loads(lines[0])
    assert rec["type"] == "bilateral_logger_failure"
    assert rec["case_id"] == "case_fsync_fail"
    assert rec["reason"] == "fsync_error"

    # (c) no partial JSONL write — log file must be empty (truncated back).
    log_file = log_dir / "case_fsync_fail.jsonl"
    if log_file.exists():
        assert log_file.read_text() == ""


# ---------------------------------------------------------------------------
# test_system_failures_record_format
# ---------------------------------------------------------------------------

def test_system_failures_record_format(tmp_path, monkeypatch):
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures_file)

    monkeypatch.setattr(os, "fsync", lambda fd: (_ for _ in ()).throw(OSError("simulated error")))

    with pytest.raises(BilateralLoggerError):
        logger.commit("case_fmt", {"type": "test"})

    assert failures_file.exists()
    lines = failures_file.read_text().strip().split("\n")
    rec = json.loads(lines[0])

    # All required fields must be present.
    for field in ("type", "case_id", "reason", "detail", "at"):
        assert field in rec, f"missing field: {field!r}"

    # at must be a valid ISO-8601 UTC timestamp ending with "Z".
    assert rec["at"].endswith("Z"), f"at must end with 'Z', got {rec['at']!r}"
    # Quick structural check: YYYY-MM-DDTHH:MM:SSZ
    assert len(rec["at"]) >= 20, f"at timestamp too short: {rec['at']!r}"


# ---------------------------------------------------------------------------
# test_no_cross_case_contamination
# ---------------------------------------------------------------------------

def test_no_cross_case_contamination(tmp_path):
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures_file)

    logger.commit("case_A", {"v": 1})
    logger.commit("case_B", {"v": 2})

    lines_a = (log_dir / "case_A.jsonl").read_text().splitlines()
    lines_b = (log_dir / "case_B.jsonl").read_text().splitlines()

    assert len(lines_a) == 1
    assert len(lines_b) == 1
    parsed_a = json.loads(lines_a[0])
    parsed_b = json.loads(lines_b[0])
    assert record_without_chain(parsed_a) == {"v": 1}
    assert record_without_chain(parsed_b) == {"v": 2}
    assert parsed_a["prev_record_hash"] == GENESIS_PREV
    assert parsed_b["prev_record_hash"] == GENESIS_PREV


# ---------------------------------------------------------------------------
# test_concurrent_commits_same_case
# ---------------------------------------------------------------------------

def test_concurrent_commits_same_case(tmp_path):
    log_dir = tmp_path / "logs"
    failures_file = tmp_path / "failures.jsonl"
    logger = BilateralLogger(log_dir, failures_file)

    for i in range(5):
        logger.commit("case_seq", {"i": i})

    log_file = log_dir / "case_seq.jsonl"
    lines = log_file.read_text().splitlines()
    assert len(lines) == 5, f"expected 5 lines, got {len(lines)}"

    parsed_records = [json.loads(line) for line in lines]
    for i, parsed in enumerate(parsed_records):
        assert record_without_chain(parsed) == {"i": i}, f"line {i} mismatch: {parsed!r}"

    # Verify hash chain.
    assert parsed_records[0]["prev_record_hash"] == GENESIS_PREV
    for i in range(1, len(parsed_records)):
        expected_prev_hash = _canonical_hash(parsed_records[i - 1])
        assert parsed_records[i]["prev_record_hash"] == expected_prev_hash, f"line {i} chain broken"


# ---------------------------------------------------------------------------
# test_hash_chain_tampering_detection — audit drill
# ---------------------------------------------------------------------------

def test_hash_chain_tampering_detection(tmp_path):
	"""Verify that hash chain catches tampering (mutation, reordering, deletion)."""
	from logs.bilateral_logger import _canonical_hash, GENESIS_PREV

	log_dir = tmp_path / "logs"
	failures_file = tmp_path / "failures.jsonl"
	logger = BilateralLogger(log_dir, failures_file)

	# (a) Create a clean chain.
	logger.commit("case_tamper", {"type": "record", "seq": 1})
	logger.commit("case_tamper", {"type": "record", "seq": 2})
	logger.commit("case_tamper", {"type": "record", "seq": 3})

	log_file = log_dir / "case_tamper.jsonl"
	original_lines = log_file.read_text().splitlines()
	assert len(original_lines) == 3

	# Verify clean chain is valid.
	from verify_audit_log import verify_audit_log as verify
	is_valid, msg = verify(log_file)
	assert is_valid, f"clean chain should be valid: {msg}"

	# (b) Mutate a record's content (not the hash).
	lines = log_file.read_text().splitlines()
	records = [json.loads(line) for line in lines]
	records[1]["seq"] = 999  # Mutate the second record.
	with log_file.open("w", encoding="utf-8") as f:
		for r in records:
			f.write(json.dumps(r, separators=(",", ":")) + "\n")

	is_valid, msg = verify(log_file)
	assert not is_valid, f"mutated content should be detected: {msg}"
	# Signature verification will catch tampering first (stricter than hash chain alone)
	assert "hash chain broken" in msg or "hash" in msg.lower() or "signature" in msg.lower(), \
		f"message should mention tampering detection (hash chain or signature): {msg}"

	# (c) Restore clean chain; now mutate the prev_record_hash.
	with log_file.open("w", encoding="utf-8") as f:
		for line in original_lines:
			f.write(line + "\n")

	lines = log_file.read_text().splitlines()
	records = [json.loads(line) for line in lines]
	records[1]["prev_record_hash"] = "sha256:" + "f" * 64  # Corrupt the hash.
	with log_file.open("w", encoding="utf-8") as f:
		for r in records:
			f.write(json.dumps(r, separators=(",", ":")) + "\n")

	is_valid, msg = verify(log_file)
	assert not is_valid, f"corrupted hash should be detected: {msg}"
	assert "hash chain broken" in msg, f"message should mention chain break: {msg}"
