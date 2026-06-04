"""
Nightly batch job: export completed cases from MongoDB to signed JSONL archive.

This preserves forensic admissibility by creating an immutable, independently
verifiable archive of all completed cases with cryptographic signatures.

Run via cron or systemd timer:
  0 2 * * * cd /path/to/gpa && PYTHONPATH=. python ops/export_signed_cases.py

Archive location: archive/signed_cases_{YYYYMMDD}.jsonl
Manifest: archive/manifest.jsonl (one entry per export)
"""

import json
import hashlib
import pathlib
import logging
from datetime import datetime, timezone
from typing import Optional

from persistence.mongo_client import MongoDBCaseStore


logger = logging.getLogger(__name__)


def compute_file_hash(file_path: pathlib.Path) -> str:
    """Compute SHA-256 hash of a file."""
    hasher = hashlib.sha256()
    with file_path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            hasher.update(chunk)
    return "sha256:" + hasher.hexdigest()


def count_records_in_file(file_path: pathlib.Path) -> int:
    """Count JSONL records in a file."""
    count = 0
    with file_path.open("r") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def export_signed_cases(
    case_store: MongoDBCaseStore,
    archive_dir: Optional[pathlib.Path] = None,
    dry_run: bool = False
) -> dict:
    """
    Export all completed, non-exported cases from MongoDB to signed JSONL archive.

    Args:
        case_store: MongoDBCaseStore instance
        archive_dir: Directory to write archive (default: repo/archive/)
        dry_run: If True, count records but don't write files

    Returns:
        Dict with export stats (cases_exported, records_exported, archive_file, archive_hash)
    """
    if archive_dir is None:
        archive_dir = pathlib.Path(__file__).parent.parent / "archive"

    archive_dir.mkdir(parents=True, exist_ok=True)

    # 1. Query MongoDB: status = 'completed' AND exported = False
    completed_cases = case_store.find_by_status("completed", exported_only=False, limit=None)

    if not completed_cases:
        logger.info("No completed cases to export")
        return {
            "cases_exported": 0,
            "records_exported": 0,
            "archive_file": None,
            "archive_hash": None
        }

    # 2. Write archive JSONL
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    archive_file = archive_dir / f"signed_cases_{timestamp}.jsonl"

    records_exported = 0

    if not dry_run:
        with archive_file.open("a" if archive_file.exists() else "w") as f:
            for case in completed_cases:
                case_id = case["case_id"]

                # Write all records for this case (they already have jws_signature)
                for record in case.get("records", []):
                    f.write(json.dumps(record, separators=(",", ":")) + "\n")
                    records_exported += 1

                # Mark case as exported
                case_store.mark_exported(case_id)
                logger.info(f"Exported case {case_id} ({len(case.get('records', []))} records)")

        # 3. Compute archive hash and log to manifest
        archive_hash = compute_file_hash(archive_file)
        manifest_file = archive_dir / "manifest.jsonl"

        manifest_entry = {
            "export_date": datetime.now(timezone.utc).isoformat(),
            "archive_file": str(archive_file),
            "archive_hash": archive_hash,
            "cases_exported": len(completed_cases),
            "records_exported": records_exported
        }

        with manifest_file.open("a") as f:
            f.write(json.dumps(manifest_entry, separators=(",", ":")) + "\n")

        logger.info(f"✓ Exported {len(completed_cases)} cases ({records_exported} records) to {archive_file}")
        logger.info(f"✓ Archive hash: {archive_hash}")

        return {
            "cases_exported": len(completed_cases),
            "records_exported": records_exported,
            "archive_file": str(archive_file),
            "archive_hash": archive_hash
        }
    else:
        # Dry run: count only
        for case in completed_cases:
            records_exported += len(case.get("records", []))

        logger.info(f"[DRY RUN] Would export {len(completed_cases)} cases ({records_exported} records)")

        return {
            "cases_exported": len(completed_cases),
            "records_exported": records_exported,
            "archive_file": None,
            "archive_hash": None
        }


if __name__ == "__main__":
    import sys

    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] %(levelname)s: %(message)s"
    )

    # Parse args
    dry_run = "--dry-run" in sys.argv

    # Get MongoDB URI from env or use default
    import os
    mongo_uri = os.getenv("MONGODB_URI", "mongodb://localhost:27017")

    # Export
    try:
        case_store = MongoDBCaseStore(mongo_uri)
        result = export_signed_cases(case_store, dry_run=dry_run)
        print(json.dumps(result, indent=2))
    except Exception as e:
        logger.error(f"Export failed: {e}", exc_info=True)
        sys.exit(1)
