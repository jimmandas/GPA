"""
Schema validator for Policy Mapper policy_map output.

Loads schemas/policy_map.json at import time and exposes validate_policy_map().
Raises jsonschema.ValidationError on any violation.
"""

import json
import pathlib

import jsonschema

_SCHEMA_PATH = pathlib.Path(__file__).resolve().parents[2] / "schemas" / "policy_map.json"

with _SCHEMA_PATH.open("r", encoding="utf-8") as _f:
    POLICY_MAP_SCHEMA: dict = json.load(_f)


def validate_policy_map(parsed: dict) -> None:
    """
    Validate a parsed policy_map dict against the policy_map JSON Schema.

    Raises:
        jsonschema.ValidationError: if the dict does not conform to the schema.
    """
    jsonschema.validate(parsed, POLICY_MAP_SCHEMA)
