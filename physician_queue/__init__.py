"""
physician_queue/ — Phase 2 physician peer review workflow.

Provides the PhysicianQueue interface, an entry/action dataclass set, and
a FilePhysicianQueue implementation that backs the queue with a JSON file.
Future implementations (Postgres-backed, queue-service-backed) drop into
the same interface.

The queue exists to enforce ADR-000 + ADR-014: denial authority belongs to
a licensed physician, never to the AI or to a nurse acting on AI output
alone. Cases that the AI brief flags as deny-candidates, or that a nurse
explicitly escalates, get enqueued. A physician dequeues, reviews, and
records the action with full rationale.

See ADR-014 for the rationale on why this exists and how the Denial Gate
unlocks to route to it.
"""

from .queue import (
    PhysicianQueue,
    FilePhysicianQueue,
    FilePhysicianQueueError,
    QueueEntry,
    QueueState,
    PhysicianAction,
    ActionRecord,
)

__all__ = [
    "PhysicianQueue",
    "FilePhysicianQueue",
    "FilePhysicianQueueError",
    "QueueEntry",
    "QueueState",
    "PhysicianAction",
    "ActionRecord",
]
