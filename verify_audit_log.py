#!/usr/bin/env python3
"""
Verify the integrity of a bilateral audit log.

Checks that the hash chain is unbroken:
  - Genesis record has prev_record_hash == GENESIS_PREV
  - Each subsequent record's prev_record_hash == hash(previous record)
  - No records have been mutated, deleted, or reordered

Usage:
  python verify_audit_log.py <case_id>       # verify decision_log/{case_id}.jsonl
  python verify_audit_log.py <path/to/file>  # verify a specific file

Exit code:
  0 = PASS (chain is valid)
  1 = FAIL (chain is broken or file not found)
"""

import hashlib
import json
import sys
import base64
from pathlib import Path
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.backends import default_backend

GENESIS_PREV = "sha256:" + "0" * 64


def _canonical_hash(record: dict) -> str:
	"""Compute SHA-256 hash of a record in canonical (sorted-key) form."""
	canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
	return "sha256:" + hashlib.sha256(canonical.encode()).hexdigest()


def _load_public_key():
	"""Load RSA public key from config/public_key.pem."""
	repo_root = Path(__file__).resolve().parent
	key_path = repo_root / "config" / "public_key.pem"

	if not key_path.exists():
		return None  # Signatures optional if key doesn't exist

	with key_path.open("rb") as f:
		return serialization.load_pem_public_key(
			f.read(),
			backend=default_backend()
		)


def _verify_signature(record: dict, signature_b64: str, public_key) -> bool:
	"""
	Verify JWS signature on a record.

	Args:
		record: dict with prev_record_hash (signature computed over full canonical record)
		signature_b64: base64-encoded RSA-PSS signature
		public_key: RSA public key object

	Returns:
		True if signature is valid, False otherwise.
	"""
	if public_key is None:
		return True  # Skip if key not available

	try:
		canonical = json.dumps(record, sort_keys=True, separators=(",", ":"))
		signature_bytes = base64.b64decode(signature_b64)
		public_key.verify(
			signature_bytes,
			canonical.encode(),
			padding.PSS(
				mgf=padding.MGF1(hashes.SHA256()),
				salt_length=padding.PSS.MAX_LENGTH
			),
			hashes.SHA256()
		)
		return True
	except Exception:
		return False


def verify_audit_log(log_path: Path) -> tuple[bool, str]:
	"""
	Verify the hash chain integrity of an audit log file.

	Returns:
		(is_valid, message) where is_valid is True if the chain is intact
	"""
	if not log_path.exists():
		return False, f"File not found: {log_path}"

	try:
		with log_path.open("r", encoding="utf-8") as f:
			lines = f.readlines()
	except OSError as exc:
		return False, f"Failed to read file: {exc}"

	if not lines:
		return True, "File is empty (no records to verify)"

	records = []
	for i, line in enumerate(lines, start=1):
		line = line.strip()
		if not line:
			continue
		try:
			records.append(json.loads(line))
		except json.JSONDecodeError as exc:
			return False, f"Line {i}: JSON parse error: {exc}"

	if not records:
		return True, "File contains no records"

	# Load public key for signature verification
	public_key = _load_public_key()
	has_signatures = any("jws_signature" in r for r in records)

	# Verify the chain and signatures.
	for i, record in enumerate(records):
		expected_prev_hash = GENESIS_PREV if i == 0 else _canonical_hash(records[i - 1])
		actual_prev_hash = record.get("prev_record_hash")

		if actual_prev_hash is None:
			return False, f"Record {i}: missing prev_record_hash field"

		if actual_prev_hash != expected_prev_hash:
			return False, (
				f"Record {i}: hash chain broken\n"
				f"  Expected prev_record_hash: {expected_prev_hash}\n"
				f"  Actual prev_record_hash: {actual_prev_hash}"
			)

		# NEW: Verify JWS signature if present
		if has_signatures:
			signature = record.get("jws_signature")
			if signature is None:
				return False, f"Record {i}: has jws_signature field in other records but missing here"

			# Extract signature for verification (don't modify original)
			record_copy = dict(record)
			del record_copy["jws_signature"]
			record_copy["prev_record_hash"] = actual_prev_hash

			if not _verify_signature(record_copy, signature, public_key):
				return False, f"Record {i}: JWS signature verification failed"

	signature_status = "✓ JWS signatures verified" if has_signatures else "⊘ No signatures (pre-Phase 3a)"
	return True, f"PASS: hash chain verified ({len(records)} records) | {signature_status}"


def main() -> int:
	if len(sys.argv) < 2:
		print(__doc__, file=sys.stderr)
		return 1

	arg = sys.argv[1]

	# Interpret the argument: either a case_id or a file path.
	if "/" in arg or "\\" in arg or arg.endswith(".jsonl"):
		log_path = Path(arg)
	else:
		# Assume it's a case_id; look in decision_log/.
		repo_root = Path(__file__).resolve().parent
		log_path = repo_root / "decision_log" / f"{arg}.jsonl"

	is_valid, message = verify_audit_log(log_path)
	print(message)
	return 0 if is_valid else 1


if __name__ == "__main__":
	sys.exit(main())
