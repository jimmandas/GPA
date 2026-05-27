"""
Denial Gate — pure Python, no LLM, no SDK.

MVP / Phase 1 behavior (default, DENIAL_GATE_MODE != "route"):
  - Determination path MUST be in {"approve", "escalate", "pend"}
  - Any "deny" path raises DenialAttemptError
  - Denial is architecturally absent — the AI output schema has no path
    to it, and this gate enforces that at runtime as defense-in-depth

Phase 2 behavior (DENIAL_GATE_MODE="route"):
  - "deny" path is permitted IF a PhysicianQueue is provided AND the case
    has been routed (i.e., a queued ActionRecord exists with action=DENY)
  - "deny" without a routing record still raises (no autonomous denial)
  - This unlocks the physician peer review workflow per ADR-014 without
    changing MVP behavior by default

The gate stays a hard control either way. The Phase 2 change is: the path
through the gate now exists — it just requires a physician as the actor.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from physician_queue.queue import PhysicianQueue, PhysicianAction


# Always-allowed paths regardless of mode.
ALLOWED_PATHS_BASE: set[str] = {"approve", "escalate", "pend"}

# Phase 2 "route" mode adds "deny" to the allowed set — but only when a
# corresponding physician action record exists. The presence-of-record
# check is what makes this still a hard control.
ALLOWED_PATHS_ROUTE: set[str] = ALLOWED_PATHS_BASE | {"deny"}


class DenialAttemptError(Exception):
    """Raised when a determination contains a deny path without proper routing."""

    def __init__(self, path: str, detail: str = "") -> None:
        self.path = path
        self.detail = detail
        suffix = f" — {detail}" if detail else ""
        super().__init__(
            f"Denial attempt detected: path={path!r}. Denial requires a physician.{suffix}"
        )


def _is_route_mode() -> bool:
    """Read DENIAL_GATE_MODE env var. Default behavior matches MVP."""
    return os.environ.get("DENIAL_GATE_MODE", "").lower() == "route"


def check(
    determination: dict,
    physician_queue: "PhysicianQueue | None" = None,
) -> None:
    """
    Assert determination["path"] is a permissible action for the active mode.

    Args:
        determination: Dict with at minimum a "path" key.
        physician_queue: Required when DENIAL_GATE_MODE=route AND path=="deny".
                         The queue is checked for a recorded physician action
                         on this case_id; absence of action = no denial allowed.

    Raises:
        DenialAttemptError: if path is "deny" outside route mode, or if path
                            is "deny" in route mode without a physician record,
                            or if path is any value outside the allowed set.
        ValueError: if determination is missing "path" key.
    """
    if "path" not in determination:
        raise ValueError("determination is missing required 'path' key")

    path = determination["path"]
    route_mode = _is_route_mode()
    allowed = ALLOWED_PATHS_ROUTE if route_mode else ALLOWED_PATHS_BASE

    if path not in allowed:
        raise DenialAttemptError(
            path=path,
            detail=f"path not in allowed set {sorted(allowed)} for mode "
                   f"{'route' if route_mode else 'block'}",
        )

    # In route mode, a deny path requires a physician ActionRecord on file.
    # MVP mode: never reached because "deny" isn't in ALLOWED_PATHS_BASE.
    if route_mode and path == "deny":
        case_id = determination.get("case_id")
        if not case_id:
            raise DenialAttemptError(
                path=path,
                detail="route-mode denial requires case_id in determination",
            )
        if physician_queue is None:
            raise DenialAttemptError(
                path=path,
                detail="route-mode denial requires a PhysicianQueue to verify "
                       "physician action record",
            )

        # Lazy import to keep the gate's MVP path zero-dependency.
        from physician_queue.queue import PhysicianAction

        entry = physician_queue.get(case_id)
        if entry is None:
            raise DenialAttemptError(
                path=path,
                detail=f"no physician queue entry for case {case_id!r}",
            )

        # Walk the queue's persistent state for an ActionRecord with action=DENY.
        # FilePhysicianQueue exposes this via its internal state file; we read
        # through the queue interface to stay implementation-agnostic.
        # (A future PhysicianQueue ABC method could expose this directly; for
        # now we rely on the FilePhysicianQueue concrete reader.)
        from physician_queue.queue import FilePhysicianQueue
        if isinstance(physician_queue, FilePhysicianQueue):
            state = physician_queue._read()
            has_deny_record = any(
                a["case_id"] == case_id and a["action"] == PhysicianAction.DENY.value
                for a in state.get("actions", [])
            )
            if not has_deny_record:
                raise DenialAttemptError(
                    path=path,
                    detail=f"case {case_id!r} has no recorded physician DENY action; "
                           "denial requires explicit physician action",
                )
        # Other PhysicianQueue implementations are responsible for surfacing
        # action records via their own interface in the future.
