"""
Denial Gate — pure Python, no LLM, no SDK.

Runtime assertion that the determination path is one of the allowed values.
Denial is architecturally absent; this gate provides a final safety layer.
"""

from __future__ import annotations


ALLOWED_PATHS: set[str] = {"approve", "escalate", "pend"}


class DenialAttemptError(Exception):
    """Raised when a determination contains a deny path."""

    def __init__(self, path: str) -> None:
        self.path = path
        super().__init__(
            f"Denial attempt detected: path={path!r}. Denial requires a physician."
        )


def check(determination: dict) -> None:
    """
    Assert determination["path"] is in ALLOWED_PATHS.

    Raises:
        DenialAttemptError: if path is "deny" or any value outside ALLOWED_PATHS.
        ValueError: if determination is missing "path" key.

    Args:
        determination: Dict with at minimum a "path" key.
    """
    if "path" not in determination:
        raise ValueError("determination is missing required 'path' key")

    path = determination["path"]
    if path not in ALLOWED_PATHS:
        raise DenialAttemptError(path=path)
