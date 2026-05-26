"""
Tests for logs/bilateral_logger.py

All tests use tmp_path-based BilateralLogger instances.
The real decision_log/ and system_failures.jsonl are never touched.
"""

import json
import os

import pytest

from logs.bilateral_logger import BilateralLogger, BilateralLoggerError


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
    assert parsed == {"type": "test", "x": 1}

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

    for i, line in enumerate(lines):
        parsed = json.loads(line)
        assert parsed == payloads[i], f"line {i} mismatch: {parsed!r}"


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
    assert parsed == {"type": "dir_creation_test"}


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
    assert json.loads(lines_a[0]) == {"v": 1}
    assert json.loads(lines_b[0]) == {"v": 2}


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

    for i, line in enumerate(lines):
        parsed = json.loads(line)
        assert parsed == {"i": i}, f"line {i} mismatch: {parsed!r}"
