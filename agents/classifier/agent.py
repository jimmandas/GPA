"""
Classifier Agent — GPA v4 Phase 3b

Single-turn extractor: transforms a prior authorization submission into
structured cancer type, stage, ICD-10, therapy line, and urgency classification.
No tools, no retries, fail-closed.

Module-level initialization (runs at import):
  - Loads system prompt from prompts/classifier.md
  - Computes and verifies SHA-256 against config/prompt_hashes.yaml
  - Constructs the _AGENT_OPTIONS singleton
  - Raises PromptHashMismatchError if hashes do not match (agent will not load)
"""

import asyncio
import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone

import jsonschema
import yaml

from claude_agent_sdk import ClaudeAgentOptions, query

from .schema_validator import validate_classification
from logs.bilateral_logger import get_logger, BilateralLoggerError

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so the repo root doesn't need to be
# in sys.path)
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROMPT_FILE = _REPO_ROOT / "prompts" / "classifier.md"
_PROMPT_HASHES_FILE = _REPO_ROOT / "config" / "prompt_hashes.yaml"
_MODEL_YAML_FILE = _REPO_ROOT / "config" / "model.yaml"
_DECISION_LOG_DIR = _REPO_ROOT / "decision_log"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class ClassifierError(Exception):
    """Raised for any recoverable failure in the Classifier call layer."""

    def __init__(self, reason: str, detail: str) -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"[{reason}] {detail}")


class PromptHashMismatchError(Exception):
    """Raised at module import if the system prompt hash does not match the registered hash."""
    pass


# ---------------------------------------------------------------------------
# Config loading helpers
# ---------------------------------------------------------------------------

def _load_model_snapshot() -> str:
    override = os.environ.get("MODEL_SNAPSHOT_OVERRIDE")
    if override:
        return override
    with _MODEL_YAML_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["model_snapshot"]


def _load_registered_prompt_hash() -> str:
    with _PROMPT_HASHES_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["classifier"]


# ---------------------------------------------------------------------------
# Prompt loading + hash verification
# ---------------------------------------------------------------------------

def _load_and_verify_prompt() -> str:
    """Load prompt, compute SHA-256, verify against registered hash."""
    with _PROMPT_FILE.open("r", encoding="utf-8") as f:
        prompt_text = f.read()

    computed_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
    registered_hash = _load_registered_prompt_hash().replace("sha256:", "")

    if computed_hash != registered_hash:
        raise PromptHashMismatchError(
            f"Classifier prompt hash mismatch.\n"
            f"Computed:  sha256:{computed_hash}\n"
            f"Registered: sha256:{registered_hash}\n"
            f"Update config/prompt_hashes.yaml and re-run eval."
        )

    return prompt_text


# ---------------------------------------------------------------------------
# Module initialization (runs at import)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = _load_and_verify_prompt()
_MODEL_SNAPSHOT = _load_model_snapshot()
_AGENT_OPTIONS = ClaudeAgentOptions(
    system_prompt=_SYSTEM_PROMPT,
    max_turns=1,
    allowed_tools=[]
)


# ---------------------------------------------------------------------------
# Main classifier function
# ---------------------------------------------------------------------------

async def classify(
    case_id: str,
    submission: dict,
) -> dict:
    """
    Classify a prior authorization submission into cancer type, stage, ICD-10,
    therapy line, and urgency.

    Args:
        case_id: Unique case identifier
        submission: Dict with keys 'imaging_request', 'clinical_indication', 'patient_context'

    Returns:
        classification: Dict matching schemas/classifier.json

    Raises:
        ClassifierError: If classification fails (schema validation, LLM error, etc.)
        BilateralLoggerError: If bilateral logger fails
    """
    try:
        logger = get_logger()
    except Exception as e:
        raise ClassifierError("logger_init", str(e))

    # Build user prompt
    user_prompt = f"""Case ID: {case_id}

Submission:
{json.dumps(submission, indent=2)}

Classify this case."""

    # Call LLM
    classification_text = ""
    try:
        async for message in query(prompt=user_prompt, options=_AGENT_OPTIONS):
            classification_text += message.text or ""
    except Exception as e:
        raise ClassifierError("llm_call", str(e))

    # Parse JSON
    try:
        classification = json.loads(classification_text)
    except json.JSONDecodeError as e:
        raise ClassifierError("json_parse", f"Invalid JSON in LLM response: {e}")

    # Validate schema
    try:
        classification = validate_classification(classification)
    except jsonschema.ValidationError as e:
        raise ClassifierError("schema_validation", str(e))

    # Audit log (write-before-emit pattern)
    try:
        event = {
            "type": "classifier_event",
            "case_id": case_id,
            "agent": "classifier",
            "classification": classification,
            "at": datetime.now(timezone.utc).isoformat() + "Z",
        }
        logger.commit(case_id, event)
    except BilateralLoggerError as e:
        raise ClassifierError("audit_log", str(e))

    return classification


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def run(case_id: str, submission: dict) -> dict:
    """
    Synchronous wrapper for the async classify() function.

    Args:
        case_id: Unique case identifier
        submission: Dict with keys 'imaging_request', 'clinical_indication', 'patient_context'

    Returns:
        classification: Dict matching schemas/classifier.json
    """
    return asyncio.run(classify(case_id, submission))
