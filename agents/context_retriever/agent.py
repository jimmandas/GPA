"""
Context Retriever Agent — GPA v4 MVP

Pre-fetch retriever: calls patient history and prior imaging tool functions
directly, injects results into the prompt, uses query() to format into a
schema-validated context dict. Fail-closed, audit-logged.

Module-level initialization (runs at import):
  - Loads system prompt from prompts/context_retriever.md
  - Computes and verifies SHA-256 against config/prompt_hashes.yaml
  - Raises PromptHashMismatchError if hashes do not match (agent will not load)
"""

import hashlib
import json
import os
import pathlib
from datetime import datetime, timezone

import jsonschema
import yaml

from claude_agent_sdk import ClaudeAgentOptions, query

from .schema_validator import validate_context
from logs.bilateral_logger import get_logger, BilateralLoggerError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROMPT_FILE = _REPO_ROOT / "prompts" / "context_retriever.md"
_PROMPT_HASHES_FILE = _REPO_ROOT / "config" / "prompt_hashes.yaml"
_MODEL_YAML_FILE = _REPO_ROOT / "config" / "model.yaml"
_TOOL_REGISTRY_FILE = _REPO_ROOT / "config" / "tool_registry.yaml"
_SCHEMA_FILE = _REPO_ROOT / "schemas" / "context.json"

_PATIENT_FIXTURES_DIR = _REPO_ROOT / "tools" / "fixtures" / "patients"
_IMAGING_FIXTURES_DIR = _REPO_ROOT / "tools" / "fixtures" / "imaging"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class ContextRetrieverError(Exception):
    """Raised for any recoverable failure in the Context Retriever call layer."""

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
    # Env var override lets eval/runner.py swap models for eval-only runs
    # without editing model.yaml (the production canonical config).
    override = os.environ.get("MODEL_SNAPSHOT_OVERRIDE")
    if override:
        return override
    with _MODEL_YAML_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["model_snapshot"]


def _load_registered_prompt_hash() -> str:
    with _PROMPT_HASHES_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["context_retriever"]


def _load_tool_registry() -> dict:
    with _TOOL_REGISTRY_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# System prompt loading
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Read prompts/context_retriever.md and return its full text."""
    with _PROMPT_FILE.open("r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Audit / hash helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-5] + "Z"


def _sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Public tool functions (callable directly, return JSON string)
# ---------------------------------------------------------------------------

def patient_history_lookup(patient_id: str) -> str:
    """
    Retrieve prior authorizations, diagnoses, and medications for a patient.
    Returns a JSON string. Returns error JSON if fixture not found.
    """
    fixture_path = _PATIENT_FIXTURES_DIR / f"{patient_id}.json"
    if not fixture_path.exists():
        return json.dumps({"error": f"No fixture found for patient_id={patient_id!r}"})
    return fixture_path.read_text(encoding="utf-8")


def prior_imaging_lookup(patient_id: str, modality: str) -> str:
    """
    Retrieve prior imaging studies for a patient and modality.
    Returns a JSON string. Returns error JSON if fixture not found.
    """
    fixture_path = _IMAGING_FIXTURES_DIR / f"{patient_id}_{modality}.json"
    if not fixture_path.exists():
        return json.dumps(
            {"error": f"No fixture found for patient_id={patient_id!r}, modality={modality!r}"}
        )
    return fixture_path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Module-level singletons (constructed once at import)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = _load_system_prompt()
_PROMPT_HASH: str = "sha256:" + hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()
_MODEL_SNAPSHOT: str = _load_model_snapshot()

_AGENT_OPTIONS = ClaudeAgentOptions(
    system_prompt=_SYSTEM_PROMPT,
    max_turns=1,
    allowed_tools=[],
)


# ---------------------------------------------------------------------------
# Prompt hash verification (called at module import)
# ---------------------------------------------------------------------------

def _verify_prompt_hash() -> None:
    """
    Compare computed _PROMPT_HASH against the registered hash in
    config/prompt_hashes.yaml.  Raises PromptHashMismatchError if they differ.
    """
    registered = _load_registered_prompt_hash()
    if _PROMPT_HASH != registered:
        raise PromptHashMismatchError(
            f"Prompt hash mismatch for context_retriever.\n"
            f"  Computed : {_PROMPT_HASH}\n"
            f"  Registered: {registered}\n"
            "Update config/prompt_hashes.yaml after editing the prompt file."
        )


# Run at module import — agent will not load if hash is wrong.
_verify_prompt_hash()


# ---------------------------------------------------------------------------
# Fixture hash verification helpers
# ---------------------------------------------------------------------------

def _verify_fixture_hash(tool_name: str, fixture_key: str, fixture_path: pathlib.Path) -> str:
    """
    Compute SHA-256 of fixture bytes and compare against tool_registry.yaml.
    Returns the computed hash string.
    Raises ContextRetrieverError("fixture_hash_mismatch", ...) on mismatch.
    """
    registry = _load_tool_registry()
    registered_hash = registry.get(tool_name, {}).get(fixture_key)
    computed_hash = _sha256_file(fixture_path)

    if registered_hash is not None and computed_hash != registered_hash:
        raise ContextRetrieverError(
            "fixture_hash_mismatch",
            f"Fixture hash mismatch for {tool_name}/{fixture_key}.\n"
            f"  Computed  : {computed_hash}\n"
            f"  Registered: {registered_hash}\n"
            "Update config/tool_registry.yaml after editing the fixture file.",
        )
    return computed_hash


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run(findings: dict, patient_id: str, case_id: str) -> dict:
    """
    Run the Context Retriever for one case.

    Calls patient_history_lookup and prior_imaging_lookup directly, verifies
    fixture hashes, then passes results to the LLM via query() for formatting.

    Args:
        findings:   Validated findings dict from Evidence Summarizer.
        patient_id: The patient identifier for fixture lookup.
        case_id:    Must equal findings["case_id"].

    Returns:
        Parsed and schema-validated context dict.

    Raises:
        ContextRetrieverError: on any failure (sdk_error, empty_response,
            json_parse_error, jsonschema_validation_error, fixture_hash_mismatch).
        PromptHashMismatchError: if the prompt hash drifted (checked at import).
    """
    modality = findings.get("modality", "CT")

    # --- Call tools directly and verify fixture hashes ----------------------
    tool_calls_made: list[dict] = []

    patient_fixture_path = _PATIENT_FIXTURES_DIR / f"{patient_id}.json"
    patient_fixture_hash: str | None = None
    if patient_fixture_path.exists():
        patient_fixture_hash = _verify_fixture_hash(
            "patient_history_lookup", patient_id, patient_fixture_path
        )
    patient_data_str = patient_history_lookup(patient_id)
    tool_calls_made.append({
        "name": "patient_history_lookup",
        "input": {"patient_id": patient_id},
        "fixture_hash": patient_fixture_hash,
    })

    imaging_fixture_key = f"{patient_id}_{modality}"
    imaging_fixture_path = _IMAGING_FIXTURES_DIR / f"{imaging_fixture_key}.json"
    imaging_fixture_hash: str | None = None
    if imaging_fixture_path.exists():
        imaging_fixture_hash = _verify_fixture_hash(
            "prior_imaging_lookup", imaging_fixture_key, imaging_fixture_path
        )
    imaging_data_str = prior_imaging_lookup(patient_id, modality)
    tool_calls_made.append({
        "name": "prior_imaging_lookup",
        "input": {"patient_id": patient_id, "modality": modality},
        "fixture_hash": imaging_fixture_hash,
    })

    # --- Build prompt with pre-fetched data ---------------------------------
    user_prompt = json.dumps(
        {
            "case_id": case_id,
            "patient_id": patient_id,
            "patient_history": json.loads(patient_data_str),
            "prior_imaging": json.loads(imaging_data_str),
            "instruction": (
                "The tool data has been pre-retrieved and is included above. "
                "Format it into context.json exactly per the output schema."
            ),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    user_prompt_hash = _sha256_hex(user_prompt)

    # --- SDK call -----------------------------------------------------------
    sdk_exception: Exception | None = None
    final_text: str = ""

    try:
        async for message in query(prompt=user_prompt, options=_AGENT_OPTIONS):
            if hasattr(message, "content") and message.content:
                for block in message.content:
                    if hasattr(block, "text"):
                        final_text += block.text
    except ContextRetrieverError:
        raise
    except Exception as exc:
        sdk_exception = exc

    # Compute output hash
    if sdk_exception is not None:
        output_hash = _sha256_hex("")
    else:
        output_hash = _sha256_hex(final_text) if final_text.strip() else _sha256_hex("")

    # --- Write agent_event BEFORE raising ----------------------------------
    agent_event: dict = {
        "type": "agent_event",
        "agent": "context_retriever",
        "case_id": case_id,
        "model_snapshot": _MODEL_SNAPSHOT,
        "prompt_hash": _PROMPT_HASH,
        "user_prompt_hash": user_prompt_hash,
        "tool_calls_made": tool_calls_made,
        "output_hash": output_hash if sdk_exception is None else None,
        "at": _now_iso(),
    }
    get_logger().commit(case_id, agent_event)

    # Raise SDK error after writing audit log
    if sdk_exception is not None:
        raise ContextRetrieverError(
            "sdk_error",
            f"SDK raised an exception: {sdk_exception}",
        ) from sdk_exception

    # Empty response check
    if not final_text.strip():
        raise ContextRetrieverError("empty_response", "Model returned no text")

    # --- JSON parse ---------------------------------------------------------
    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "context_retriever",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "json_parse_error",
            "failure_detail": str(exc),
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise ContextRetrieverError(
            "json_parse_error",
            f"Model output is not valid JSON: {exc}",
        ) from exc

    # --- Schema validation --------------------------------------------------
    try:
        validate_context(parsed)
    except jsonschema.ValidationError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "context_retriever",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "jsonschema_validation_error",
            "failure_detail": exc.message,
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise ContextRetrieverError(
            "jsonschema_validation_error",
            f"Schema validation failed: {exc.message}",
        ) from exc

    return parsed
