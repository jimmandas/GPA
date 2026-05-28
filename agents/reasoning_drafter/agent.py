"""
Reasoning Drafter Agent — GPA v4 MVP

Single-turn synthesizer: transforms validated findings, patient context, and
policy_map into a schema-validated reasoning_brief dict for the nurse reviewer.
No tools, no retries, fail-closed.

Module-level initialization (runs at import):
  - Loads system prompt from prompts/reasoning_drafter.md
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

from .schema_validator import validate_reasoning_brief
from logs.bilateral_logger import get_logger, BilateralLoggerError

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so the repo root doesn't need to be
# in sys.path)
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROMPT_FILE = _REPO_ROOT / "prompts" / "reasoning_drafter.md"
_PROMPT_HASHES_FILE = _REPO_ROOT / "config" / "prompt_hashes.yaml"
_MODEL_YAML_FILE = _REPO_ROOT / "config" / "model.yaml"
_SCHEMA_FILE = _REPO_ROOT / "schemas" / "reasoning_brief.json"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class ReasoningDrafterError(Exception):
    """Raised for any recoverable failure in the Reasoning Drafter call layer."""

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
    return cfg["reasoning_drafter"]


# ---------------------------------------------------------------------------
# System prompt loading
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Read prompts/reasoning_drafter.md and return its full text."""
    with _PROMPT_FILE.open("r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Module-level singletons (constructed once at import)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT: str = _load_system_prompt()
_PROMPT_HASH: str = "sha256:" + hashlib.sha256(_SYSTEM_PROMPT.encode("utf-8")).hexdigest()

_MODEL_SNAPSHOT: str = _load_model_snapshot()

_AGENT_OPTIONS = ClaudeAgentOptions(
    system_prompt=_SYSTEM_PROMPT,
    max_turns=1,
    allowed_tools=[]
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
            f"Prompt hash mismatch for reasoning_drafter.\n"
            f"  Computed : {_PROMPT_HASH}\n"
            f"  Registered: {registered}\n"
            "Update config/prompt_hashes.yaml after editing the prompt file."
        )


# Run at module import — agent will not load if hash is wrong.
_verify_prompt_hash()


# ---------------------------------------------------------------------------
# Audit log helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-5] + "Z"


def _sha256_hex(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# SDK call layer
# ---------------------------------------------------------------------------

async def _call_reasoning_drafter(user_prompt: str) -> tuple[str, dict]:
    """
    Invoke the Claude SDK and return (raw_text, telemetry).

    Raises:
        ReasoningDrafterError("sdk_error", ...) on SDK exception.
        ReasoningDrafterError("empty_response", ...) if response is blank.
    """
    from orchestrator.telemetry import extract_usage_from_message
    final_text = ""
    telemetry: dict = {}
    async for message in query(
        prompt=user_prompt,
        options=_AGENT_OPTIONS,
    ):
        if hasattr(message, "content") and message.content:
            for block in message.content:
                if hasattr(block, "text"):
                    final_text += block.text
        extracted = extract_usage_from_message(message)
        if extracted:
            telemetry.update(extracted)

    return final_text, telemetry


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run(findings: dict, context: dict, policy_map: dict, case_id: str) -> dict:
    """
    Run the Reasoning Drafter for one case.

    Args:
        findings:   Schema-validated findings dict from Evidence Summarizer.
        context:    Schema-validated context dict from Context Retriever.
        policy_map: Schema-validated policy_map dict from Policy Mapper.
        case_id:    Must equal findings["case_id"].

    Returns:
        Parsed and schema-validated reasoning_brief dict.

    Raises:
        ReasoningDrafterError: on any failure (sdk_error, empty_response,
            json_parse_error, jsonschema_validation_error).
        PromptHashMismatchError: if the prompt hash drifted (checked at import,
            but callers may also trigger re-verification).
    """
    # Build user prompt
    user_prompt = json.dumps({
        "case_id": case_id,
        "findings": findings,
        "patient_context": context,
        "policy_map": policy_map,
        "instruction": "Draft the reasoning brief for the nurse. Surface all uncertainty flags from ambiguous or unmet criteria."
    }, separators=(',', ':'), sort_keys=True)

    user_prompt_hash = _sha256_hex(user_prompt)

    # --- SDK call -----------------------------------------------------------
    sdk_exception: Exception | None = None
    final_text: str = ""
    telemetry: dict = {}

    try:
        final_text, telemetry = await _call_reasoning_drafter(user_prompt)
    except Exception as exc:
        sdk_exception = exc

    # Compute output hash (use hash of empty string if SDK failed)
    if sdk_exception is not None:
        output_hash = _sha256_hex("")
    else:
        output_hash = _sha256_hex(final_text) if final_text.strip() else _sha256_hex("")

    # Record telemetry for eval cost dim
    from orchestrator.telemetry import record_agent_call
    record_agent_call(
        "reasoning_drafter",
        input_tokens=telemetry.get("input_tokens"),
        output_tokens=telemetry.get("output_tokens"),
        total_cost_usd=telemetry.get("total_cost_usd"),
        duration_ms=telemetry.get("duration_ms"),
        sdk="claude_agent_sdk",
    )

    # --- Write agent_event BEFORE raising -----------------------------------
    agent_event: dict = {
        "type": "agent_event",
        "agent": "reasoning_drafter",
        "case_id": case_id,
        "model_snapshot": _MODEL_SNAPSHOT,
        "prompt_hash": _PROMPT_HASH,
        "user_prompt_hash": user_prompt_hash,
        "output_hash": output_hash,
        "tool_calls_made": [],
        "input_tokens": telemetry.get("input_tokens"),
        "output_tokens": telemetry.get("output_tokens"),
        "total_cost_usd": telemetry.get("total_cost_usd"),
        "at": _now_iso(),
    }
    get_logger().commit(case_id, agent_event)

    # Raise SDK error after writing audit log
    if sdk_exception is not None:
        raise ReasoningDrafterError(
            "sdk_error",
            f"SDK raised an exception: {sdk_exception}",
        ) from sdk_exception

    # Empty response check
    if not final_text.strip():
        raise ReasoningDrafterError("empty_response", "Model returned no text")

    # --- JSON parse ---------------------------------------------------------
    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "reasoning_drafter",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "json_parse_error",
            "failure_detail": str(exc),
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise ReasoningDrafterError(
            "json_parse_error",
            f"Model output is not valid JSON: {exc}",
        ) from exc

    # --- Schema validation --------------------------------------------------
    try:
        validate_reasoning_brief(parsed)
    except jsonschema.ValidationError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "reasoning_drafter",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "jsonschema_validation_error",
            "failure_detail": exc.message,
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise ReasoningDrafterError(
            "jsonschema_validation_error",
            f"Schema validation failed: {exc.message}",
        ) from exc

    return parsed
