"""
Schema validator for Context Retriever context output.

Loads schemas/context.json at import time and exposes validate_context().
Raises jsonschema.ValidationError on any violation.
"""

import json
import pathlib

import jsonschema

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "schemas" / "context.json"

with _SCHEMA_PATH.open("r", encoding="utf-8") as _f:
    CONTEXT_SCHEMA: dict = json.load(_f)


def validate_context(parsed: dict) -> None:
    """
    Validate a parsed context dict against the context JSON Schema.

    Raises:
        jsonschema.ValidationError: if the dict does not conform to the schema.
    """
    jsonschema.validate(parsed, CONTEXT_SCHEMA)
