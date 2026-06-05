"""
Schema validation for Classifier Agent output.

Validates classification output against schemas/classifier.json.
"""

import json
import pathlib

import jsonschema

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SCHEMA_FILE = _REPO_ROOT / "schemas" / "classifier.json"


def _load_schema() -> dict:
    """Load and return the classifier JSON schema."""
    with _SCHEMA_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)


_SCHEMA = _load_schema()


def validate_classification(output: dict) -> dict:
    """
    Validate classifier output against schemas/classifier.json.

    Args:
        output: The raw dict from LLM response

    Returns:
        output: The validated dict (no modifications)

    Raises:
        jsonschema.ValidationError: If output does not match schema
    """
    jsonschema.validate(instance=output, schema=_SCHEMA)
    return output
