"""
Schema validator for Reasoning Drafter reasoning_brief output.

Loads schemas/reasoning_brief.json at import time and exposes validate_reasoning_brief().
Raises jsonschema.ValidationError on any violation.
"""

import json
import pathlib

import jsonschema

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "schemas" / "reasoning_brief.json"

with _SCHEMA_PATH.open("r", encoding="utf-8") as _f:
    REASONING_BRIEF_SCHEMA: dict = json.load(_f)


def validate_reasoning_brief(parsed: dict) -> None:
    """
    Validate a parsed reasoning_brief dict against the reasoning_brief JSON Schema.

    Raises:
        jsonschema.ValidationError: if the dict does not conform to the schema.
    """
    jsonschema.validate(parsed, REASONING_BRIEF_SCHEMA)
