#!/usr/bin/env python3
"""
Generate synthetic demo cases for Phase 3a dashboard validation.

Creates 25 cases with varied statuses (pending, in_review, completed, escalated)
and realistic timestamps for dashboard volume demo.

Usage:
  source .spike-venv/bin/activate
  PYTHONPATH=. python ops/generate_demo_cases.py
"""

import json
import pathlib
from datetime import datetime, timedelta
import sys

# Add repo root to path
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from logs.bilateral_logger import BilateralLogger


def generate_demo_cases(log_dir: pathlib.Path, count: int = 25):
    """Generate synthetic cases with varied statuses and timestamps."""
    logger = BilateralLogger(log_dir, log_dir.parent / "failures.jsonl")

    # Base timestamp: 6 hours ago
    base_time = datetime.utcnow() - timedelta(hours=6)

    statuses = ["approved", "escalated", "pended"]
    status_map = {
        "approved": "approve",
        "escalated": "escalate",
        "pended": "pend",
    }

    created = 0
    for i in range(count):
        case_id = f"demo_{i+1:03d}"

        # 60% completed (approved/escalated), 40% still pending
        if i < int(count * 0.6):
            status = statuses[i % 3]  # rotate through statuses
            agent = ["evidence_summarizer", "context_retriever", "policy_mapper"][i % 3]
            agent_time = base_time + timedelta(minutes=i*5)
            nurse_time = agent_time + timedelta(minutes=2)

            # Agent event
            logger.commit(case_id, {
                "type": "agent_event",
                "agent": agent,
                "at": agent_time.isoformat() + "Z"
            })

            # Nurse decision
            logger.commit(case_id, {
                "type": "nurse_action_record",
                "nurse_decision": status_map[status],
                "at": nurse_time.isoformat() + "Z"
            })
        else:
            # Pending case: only agent event, no nurse decision
            agent = ["evidence_summarizer", "context_retriever"][i % 2]
            agent_time = base_time + timedelta(minutes=i*5)
            logger.commit(case_id, {
                "type": "agent_event",
                "agent": agent,
                "at": agent_time.isoformat() + "Z"
            })

        created += 1

    print(f"✅ Generated {created} demo cases in {log_dir}")
    print(f"   Breakdown: ~{int(count*0.6)} completed (approved/escalated/pended)")
    print(f"              ~{int(count*0.4)} pending review")


if __name__ == "__main__":
    repo_root = pathlib.Path(__file__).parent.parent
    log_dir = repo_root / "decision_log"
    log_dir.mkdir(exist_ok=True)

    generate_demo_cases(log_dir, count=25)
