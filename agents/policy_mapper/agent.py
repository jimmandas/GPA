"""
Policy Mapper Agent — GPA v4 MVP

Pre-fetch mapper: calls nccn_passage_lookup directly, injects results into
the prompt, calls the LLM to map each criterion against submission evidence.
Returns a schema-validated policy_map dict. Fail-closed, audit-logged.

SDK choice is env-var-gated (v3 work):
  POLICY_MAPPER_SDK=anthropic_direct → direct anthropic SDK with temperature=0
                                       (closes ADR-002 determinism gap)
  default                            → claude_agent_sdk via CLI subprocess
                                       (matches the other 3 agents)

See ADR-010 for the rationale on why this agent specifically opts into a
different SDK stack.

Module-level initialization (runs at import):
  - Loads system prompt from prompts/policy_mapper.md
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

from .schema_validator import validate_policy_map
from .aggregate import aggregate_overall_signal
from logs.bilateral_logger import get_logger, BilateralLoggerError

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_PROMPT_FILE = _REPO_ROOT / "prompts" / "policy_mapper.md"
_PROMPT_HASHES_FILE = _REPO_ROOT / "config" / "prompt_hashes.yaml"
_MODEL_YAML_FILE = _REPO_ROOT / "config" / "model.yaml"
_TOOL_REGISTRY_FILE = _REPO_ROOT / "config" / "tool_registry.yaml"
_SCHEMA_FILE = _REPO_ROOT / "schemas" / "policy_map.json"
_NCCN_FIXTURES_DIR = _REPO_ROOT / "policy" / "nccn_fixtures"


# ---------------------------------------------------------------------------
# Error classes
# ---------------------------------------------------------------------------

class PolicyMapperError(Exception):
    """Raised for any recoverable failure in the Policy Mapper call layer."""

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
    with _MODEL_YAML_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["model_snapshot"]


def _load_registered_prompt_hash() -> str:
    with _PROMPT_HASHES_FILE.open("r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg["policy_mapper"]


def _load_tool_registry() -> dict:
    with _TOOL_REGISTRY_FILE.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# System prompt loading
# ---------------------------------------------------------------------------

def _load_system_prompt() -> str:
    """Read prompts/policy_mapper.md and return its full text."""
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
# Public tool function (callable directly for testing)
# ---------------------------------------------------------------------------

def nccn_passage_lookup(indication_category: str, modality: str) -> str:
    """
    Retrieve NCCN criteria passages for a given indication category and modality.
    Returns a JSON string. Returns error JSON if fixture not found.
    """
    fixture_key = f"{indication_category}_{modality}"
    fixture_path = _NCCN_FIXTURES_DIR / f"{fixture_key}.yaml"
    if not fixture_path.exists():
        return json.dumps({"error": f"No NCCN fixture for {indication_category}/{modality}"})
    data = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    return json.dumps(data, ensure_ascii=False)


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

# v3 SDK choice: env-var-gated. See ADR-010.
_USE_ANTHROPIC_DIRECT = (
    os.environ.get("POLICY_MAPPER_SDK", "").lower() == "anthropic_direct"
)

# Lazy-initialized so the agent module can import without ANTHROPIC_API_KEY set
# (e.g., during unit tests that mock the SDK call entirely).
_anthropic_client = None


def _get_anthropic_client():
    """Lazy-init the anthropic AsyncAnthropic client (v3 only)."""
    global _anthropic_client
    if _anthropic_client is None:
        from anthropic import AsyncAnthropic
        _anthropic_client = AsyncAnthropic()
    return _anthropic_client


async def _call_via_anthropic_direct(user_prompt: str) -> str:
    """
    v3 path: direct anthropic SDK with temperature=0.

    Closes the ADR-002 known gap (claude_agent_sdk does not support
    temperature parameter). Used for policy_mapper specifically because
    its per-criterion judgments are the dominant source of reproducibility
    flakiness on judgment-intensive cases (see v1-to-v2-delta.md).
    """
    client = _get_anthropic_client()
    response = await client.messages.create(
        model=_MODEL_SNAPSHOT,
        max_tokens=4096,
        temperature=0.0,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_parts = [block.text for block in response.content if hasattr(block, "text")]
    return "".join(text_parts)


async def _call_via_claude_agent_sdk(user_prompt: str) -> str:
    """v2 (default) path: claude_agent_sdk via CLI subprocess."""
    final_text = ""
    async for message in query(prompt=user_prompt, options=_AGENT_OPTIONS):
        if hasattr(message, "content") and message.content:
            for block in message.content:
                if hasattr(block, "text"):
                    final_text += block.text
    return final_text


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
            f"Prompt hash mismatch for policy_mapper.\n"
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
    Raises PolicyMapperError("fixture_hash_mismatch", ...) on mismatch.
    """
    registry = _load_tool_registry()
    registered_hash = registry.get(tool_name, {}).get(fixture_key)
    computed_hash = _sha256_file(fixture_path)

    if registered_hash is not None and computed_hash != registered_hash:
        raise PolicyMapperError(
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

async def run(findings: dict, context: dict, case_id: str) -> dict:
    """
    Run the Policy Mapper for one case.

    Calls nccn_passage_lookup directly, verifies fixture hash, then passes
    NCCN passages + submission evidence to the LLM via query() for mapping.

    Args:
        findings: Schema-validated findings dict from Evidence Summarizer.
        context:  Schema-validated context dict from Context Retriever.
        case_id:  Must equal findings["case_id"].

    Returns:
        Parsed and schema-validated policy_map dict.

    Raises:
        PolicyMapperError: on any failure (sdk_error, empty_response,
            json_parse_error, jsonschema_validation_error, fixture_hash_mismatch).
        PromptHashMismatchError: if the prompt hash drifted (checked at import).
    """
    indication_category = findings["indication_category"]
    modality = findings["modality"]
    fixture_key = f"{indication_category}_{modality}"
    fixture_path = _NCCN_FIXTURES_DIR / f"{fixture_key}.yaml"

    # --- Call tool directly and verify fixture hash -------------------------
    fixture_hash: str | None = None
    if fixture_path.exists():
        fixture_hash = _verify_fixture_hash("nccn_passage_lookup", fixture_key, fixture_path)
    nccn_data_str = nccn_passage_lookup(indication_category, modality)
    tool_calls_made = [{
        "name": "nccn_passage_lookup",
        "input": {"indication_category": indication_category, "modality": modality},
        "fixture_hash": fixture_hash,
    }]

    # --- Build prompt with pre-fetched NCCN passages ------------------------
    user_prompt = json.dumps(
        {
            "case_id": case_id,
            "indication_category": indication_category,
            "modality": modality,
            "nccn_passages": json.loads(nccn_data_str),
            "submission_evidence": {
                "imaging_request": {
                    "indication_text": findings.get("raw_quotes", []),
                    "modality": modality,
                    "body_region": findings["body_region"],
                },
                "clinical_indication": {
                    "diagnosis_code": findings["completeness_flags"].get("has_diagnosis_code"),
                },
            },
            "patient_context": {
                "prior_authorizations": context.get("prior_authorizations", []),
                "imaging_history": context.get("imaging_history", []),
                "relevant_diagnoses": context.get("relevant_diagnoses", []),
                "medications": context.get("medications", []),
            },
            "instruction": (
                "The NCCN passages have been pre-retrieved and are included above. "
                "Map each criterion against the evidence and return policy_map.json."
            ),
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    user_prompt_hash = _sha256_hex(user_prompt)

    # --- SDK call -----------------------------------------------------------
    # Dispatched on POLICY_MAPPER_SDK env var; see ADR-010.
    sdk_used = "anthropic-direct" if _USE_ANTHROPIC_DIRECT else "claude_agent_sdk"
    sdk_exception: Exception | None = None
    final_text: str = ""

    try:
        if _USE_ANTHROPIC_DIRECT:
            final_text = await _call_via_anthropic_direct(user_prompt)
        else:
            final_text = await _call_via_claude_agent_sdk(user_prompt)
    except PolicyMapperError:
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
        "agent": "policy_mapper",
        "case_id": case_id,
        "model_snapshot": _MODEL_SNAPSHOT,
        "sdk_used": sdk_used,
        "temperature": 0.0 if _USE_ANTHROPIC_DIRECT else None,
        "prompt_hash": _PROMPT_HASH,
        "user_prompt_hash": user_prompt_hash,
        "tool_calls_made": tool_calls_made,
        "output_hash": output_hash if sdk_exception is None else None,
        "at": _now_iso(),
    }
    get_logger().commit(case_id, agent_event)

    # Raise SDK error after writing audit log
    if sdk_exception is not None:
        raise PolicyMapperError(
            "sdk_error",
            f"SDK raised an exception: {sdk_exception}",
        ) from sdk_exception

    # Empty response check
    if not final_text.strip():
        raise PolicyMapperError("empty_response", "Model returned no text")

    # --- JSON parse ---------------------------------------------------------
    try:
        parsed = json.loads(final_text)
    except json.JSONDecodeError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "policy_mapper",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "json_parse_error",
            "failure_detail": str(exc),
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise PolicyMapperError(
            "json_parse_error",
            f"Model output is not valid JSON: {exc}",
        ) from exc

    # --- Schema validation --------------------------------------------------
    try:
        validate_policy_map(parsed)
    except jsonschema.ValidationError as exc:
        get_logger().commit(case_id, {
            "type": "schema_validation_event",
            "agent": "policy_mapper",
            "case_id": case_id,
            "result": "fail",
            "failure_reason": "jsonschema_validation_error",
            "failure_detail": exc.message,
            "escalation_triggered": True,
            "at": _now_iso(),
        })
        raise PolicyMapperError(
            "jsonschema_validation_error",
            f"Schema validation failed: {exc.message}",
        ) from exc

    # --- v2 fix: deterministic aggregation of overall_signal ---------------
    # Per ADR-002 / scope §11 / ADR-009: the LLM produces per-criterion
    # judgments, Python computes the aggregate. Removes the dominant source
    # of reproducibility flakiness on judgment-intensive cases.
    llm_overall = parsed.get("overall_signal")
    try:
        deterministic_overall = aggregate_overall_signal(parsed.get("criteria", []))
    except ValueError as exc:
        # Should not happen if schema validation passed, but fail-closed.
        raise PolicyMapperError(
            "aggregation_error",
            f"Could not aggregate overall_signal: {exc}",
        ) from exc

    if llm_overall != deterministic_overall:
        # Auditable record: when LLM and deterministic aggregator disagree,
        # the deterministic value wins but the divergence is logged.
        get_logger().commit(case_id, {
            "type": "policy_aggregation_override_event",
            "agent": "policy_mapper",
            "case_id": case_id,
            "llm_overall_signal": llm_overall,
            "deterministic_overall_signal": deterministic_overall,
            "criteria_statuses": [
                {"passage_id": c.get("passage_id"), "status": c.get("status")}
                for c in parsed.get("criteria", [])
            ],
            "at": _now_iso(),
        })
        parsed["overall_signal"] = deterministic_overall

    return parsed
