"""
Evidence Summarizer Agent — GPA v4 MVP

Single-turn extractor: transforms a validated submission dict into a
schema-validated findings dict. No tools, no retries, fail-closed.

Module-level initialization (runs at import):
  - Loads system prompt from prompts/evidence_summarizer.md
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

from .schema_validator import validate_findings
from logs.bilateral_logger import get_logger, BilateralLoggerError

# ---------------------------------------------------------------------------
# Paths (resolved relative to this file so the repo root doesn't need to be
# in sys.path)
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROMPT_FILE = _REPO_ROOT / "prompts" / "evidence_summarizer.md"
_PROMPT_HASHES_FILE = _REPO_ROOT / "config" / "prompt_hashes.yaml"
_MODEL_YAML_FILE = _REPO_ROOT / "config" / "model.yaml"
_DECISION_LOG_DIR = _REPO_ROOT / "decision_log"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class EvidenceSummarizerError(Exception):
    """Raised for any recoverable failure in the Evidence Summarizer call layer."""

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
    return cfg["evidence_summarizer"]


# ---------------------------------------------------------------------------
# System prompt loading
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Read prompts/evidence_summarizer.md and return its full text."""
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
            f"Prompt hash mismatch for evidence_summarizer.\n"
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

async def _call_evidence_summarizer(submission: dict) -> tuple[str, dict]:
    """
    Invoke the Claude SDK and return (raw_text, telemetry).

    Telemetry is the per-call usage dict pulled off the terminal ResultMessage
    (when the SDK emits one). Empty dict when the call layer is mocked in tests.

    Raises:
        EvidenceSummarizerError("sdk_error", ...) on SDK exception.
        EvidenceSummarizerError("empty_response", ...) if response is blank.
    """
    user_prompt = json.dumps(submission, separators=(",", ":"), sort_keys=True)

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
        # ResultMessage carries total_cost_usd + usage; capture if present.
        from orchestrator.telemetry import extract_usage_from_message
        extracted = extract_usage_from_message(message)
        if extracted:
            telemetry.update(extracted)

    return final_text, telemetry


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

async def run(submission: dict, case_id: str) -> dict:
    """
    Run the Evidence Summarizer for one submission.

    Args:
        submission: Validated submission dict (post-Admission Gate).
        case_id:    The case identifier (must equal submission["case_id"]).

    Returns:
        Parsed and schema-validated findings dict.

    Raises:
        EvidenceSummarizerError: on any failure (sdk_error, empty_response,
            json_parse_error, jsonschema_validation_error).
        PromptHashMismatchError: if the prompt hash drifted (checked at import,
            but callers may also trigger re-verification).
    """
    # Pre-call: compute hashes for audit fields
    user_prompt = json.dumps(submission, separators=(",", ":"), sort_keys=True)
    user_prompt_hash = _sha256_hex(user_prompt)

    # --- SDK call -----------------------------------------------------------
    sdk_exception: Exception | None = None
    final_text: str = ""
    telemetry: dict = {}

    try:
        final_text, telemetry = await _call_evidence_summarizer(submission)
    except Exception as exc:
        sdk_exception = exc

    # Compute output hash (use hash of empty string if SDK failed)
    if sdk_exception is not None:
        output_hash = _sha256_hex("")
    else:
        output_hash = _sha256_hex(final_text) if final_text.strip() else _sha256_hex("")

    # Record telemetry for the eval cost dim (no-op when called outside pipeline)
    from orchestrator.telemetry import record_agent_call
    record_agent_call(
        "evidence_summarizer",
        input_tokens=telemetry.get("input_tokens"),
        output_tokens=telemetry.get("output_tokens"),
        total_cost_usd=telemetry.get("total_cost_usd"),
        duration_ms=telemetry.get("duration_ms"),
        sdk="claude_agent_sdk",
    )

    # --- Write agent_event BEFORE raising (§4, §5 step 7) ------------------
    agent_event: dict = {
        "type": "agent_event",
        "agent": "evidence_summarizer",
        "case_id": case_id,
        "model_snapshot": _MODEL_SNAPSHOT,
        "prompt_hash": _PROMPT_HASH,
        "user_prompt_hash": user_prompt_hash,
        "output_hash": output_hash if sdk_exception is None else None,
        "tool_calls_made": [],
        "raw_response_length": len(final_text) if sdk_exception is None else 0,
        "input_tokens": telemetry.get("input_tokens"),
        "output_tokens": telemetry.get("output_tokens"),
        "total_cost_usd": telemetry.get("total_cost_usd"),
        "at": _now_iso(),
    }
    get_logger().commit(case_id, agent_event)

    # Raise SDK error after writing audit log
    if sdk_exception is not None:
        raise EvidenceSummarizerError(
            "sdk_error",
            f"SDK raised an exception: {sdk_exception}",
        ) from sdk_exception

    # Empty response check
    if not final_text.strip():
        raise EvidenceSummarizerError("empty_response", "Model returned no text")

    # --- JSON parse ---------------------------------------------------------
    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "evidence_summarizer",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "json_parse_error",
            "failure_detail": str(exc),
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise EvidenceSummarizerError(
            "json_parse_error",
            f"Model output is not valid JSON: {exc}",
        ) from exc

    # --- Schema validation --------------------------------------------------
    try:
        validate_findings(parsed)
    except jsonschema.ValidationError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "evidence_summarizer",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "jsonschema_validation_error",
            "failure_detail": exc.message,
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise EvidenceSummarizerError(
            "jsonschema_validation_error",
            f"Schema validation failed: {exc.message}",
        ) from exc

    # --- case_id pass-through assertion (§5 step 10) -----------------------
    if parsed.get("case_id") != submission.get("case_id"):
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "evidence_summarizer",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "jsonschema_validation_error",
            "failure_detail": (
                f"case_id mismatch: expected {submission.get('case_id')!r}, "
                f"got {parsed.get('case_id')!r}"
            ),
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise EvidenceSummarizerError(
            "jsonschema_validation_error",
            f"case_id mismatch: expected {submission.get('case_id')!r}, "
            f"got {parsed.get('case_id')!r}",
        )

    return parsed
