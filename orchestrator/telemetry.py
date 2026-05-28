"""
Per-pipeline-run telemetry collector (eval framework v3+ — 2026-05-28).

Captures real per-agent-call token usage and cost from the SDK so the
eval can compute *actual* per-case cost instead of a hard-coded estimate.

Why ContextVar (and not signature changes):
- The 4 agents have a public `async def run(...) -> dict` contract called
  from orchestrator/pipeline.py and from tests. Threading a telemetry
  collector through the call graph would touch every test mock.
- ContextVar is task-local: each `asyncio.run()` gets its own context, so
  the eval's 5-rep loop captures 5 independent telemetry sets without
  cross-contamination.
- Agents that don't capture telemetry (because the test patches `query()`
  with a mock that doesn't yield ResultMessage) simply don't append —
  the collector ends up empty for that run, and the cost dim falls back
  to its heuristic.

Telemetry-record schema (one dict per agent SDK call):
  {
    "agent":          str           # "evidence_summarizer" | ... | "reasoning_drafter"
    "input_tokens":   int | None    # from SDK response.usage.input_tokens
    "output_tokens":  int | None    # from SDK response.usage.output_tokens
    "total_cost_usd": float | None  # from claude_agent_sdk ResultMessage.total_cost_usd
                                    # None for paths that don't surface cost (e.g.
                                    # policy_mapper's anthropic-direct path — cost
                                    # is computed downstream from tokens × rates)
    "duration_ms":    int | None    # from claude_agent_sdk ResultMessage.duration_ms
    "sdk":            str           # "claude_agent_sdk" | "anthropic_direct"
  }
"""

from __future__ import annotations

import contextvars
from typing import Any

_telemetry_var: contextvars.ContextVar[list[dict] | None] = contextvars.ContextVar(
    "gpa_pipeline_telemetry", default=None
)


def start_collection() -> None:
    """Reset the collector for a fresh pipeline run."""
    _telemetry_var.set([])


def record_agent_call(
    agent: str,
    *,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_cost_usd: float | None = None,
    duration_ms: int | None = None,
    sdk: str = "claude_agent_sdk",
) -> None:
    """Append one agent SDK call's telemetry. No-op if collection not started."""
    collector = _telemetry_var.get()
    if collector is None:
        # Not started — agent is being called outside an active pipeline
        # (e.g., from a unit test that doesn't go through pipeline.run_pipeline).
        # That's fine; we just don't capture.
        return
    collector.append({
        "agent": agent,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_cost_usd": total_cost_usd,
        "duration_ms": duration_ms,
        "sdk": sdk,
    })


def get_collected() -> list[dict] | None:
    """Return the collected telemetry (or None if collection not started)."""
    return _telemetry_var.get()


def extract_usage_from_message(message: Any) -> dict:
    """
    Pull telemetry fields off a claude_agent_sdk message (typically a
    ResultMessage). Safe to call on any message type — returns an empty
    dict if the fields aren't present.
    """
    out: dict = {}
    # claude_agent_sdk.ResultMessage exposes total_cost_usd + usage dict
    cost = getattr(message, "total_cost_usd", None)
    if cost is not None:
        out["total_cost_usd"] = float(cost)
    usage = getattr(message, "usage", None)
    if isinstance(usage, dict):
        if "input_tokens" in usage:
            out["input_tokens"] = int(usage["input_tokens"])
        if "output_tokens" in usage:
            out["output_tokens"] = int(usage["output_tokens"])
    duration = getattr(message, "duration_ms", None)
    if duration is not None:
        out["duration_ms"] = int(duration)
    return out
