"""
AI-Decision-Limit Gate — pure Python, no LLM, no SDK.

Belt-and-suspenders assertion that no agent output contains a decision,
recommendation, or confidence field at the top level.
"""

from __future__ import annotations


FORBIDDEN_FIELDS: set[str] = {"decision", "recommendation", "confidence"}


class AIDecisionAttemptError(Exception):
    """Raised when an agent output contains a forbidden field."""

    def __init__(self, field: str, agent: str) -> None:
        self.field = field
        self.agent = agent
        super().__init__(f"Agent '{agent}' emitted forbidden field '{field}'")


def check(agent_output: dict, agent_name: str) -> None:
    """
    Assert no forbidden field is present at the top level of agent_output.

    Raises:
        AIDecisionAttemptError: if any forbidden field is found.

    Args:
        agent_output: The dict output from any agent.
        agent_name:   Name of the agent (for error context).
    """
    for forbidden in FORBIDDEN_FIELDS:
        if forbidden in agent_output:
            raise AIDecisionAttemptError(field=forbidden, agent=agent_name)
