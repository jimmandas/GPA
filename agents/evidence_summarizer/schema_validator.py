"""
Schema validator for Evidence Summarizer findings output.

Loads schemas/findings.json at import time and exposes validate_findings().
Raises jsonschema.ValidationError on any violation.
"""

import json
import pathlib

import jsonschema

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "schemas" / "findings.json"

with _SCHEMA_PATH.open("r", encoding="utf-8") as _f:
    FINDINGS_SCHEMA: dict = json.load(_f)


def validate_findings(parsed: dict) -> None:
    """
    Validate a parsed findings dict against the findings JSON Schema.

    Raises:
        jsonschema.ValidationError: if the dict does not conform to the schema.
    """
    jsonschema.validate(parsed, FINDINGS_SCHEMA)
