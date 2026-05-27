"""
Tests for MODEL_SNAPSHOT_OVERRIDE env var behavior.

All 4 agents implement the same _load_model_snapshot() contract:
  - If MODEL_SNAPSHOT_OVERRIDE env var is set, return its value.
  - Otherwise, fall back to config/model.yaml's model_snapshot.

This override is what lets eval/runner.py hardcode Sonnet without
disturbing the production canonical config (Opus).
"""

import importlib
import os

import pytest


AGENT_MODULES = [
    "agents.evidence_summarizer.agent",
    "agents.context_retriever.agent",
    "agents.reasoning_drafter.agent",
    "agents.policy_mapper.agent",
]


@pytest.mark.parametrize("module_path", AGENT_MODULES)
def test_env_var_overrides_yaml(module_path, monkeypatch):
    """MODEL_SNAPSHOT_OVERRIDE wins over model.yaml when both present."""
    monkeypatch.setenv("MODEL_SNAPSHOT_OVERRIDE", "claude-test-override-2026-99-99")
    mod = importlib.import_module(module_path)
    assert mod._load_model_snapshot() == "claude-test-override-2026-99-99"


@pytest.mark.parametrize("module_path", AGENT_MODULES)
def test_yaml_loaded_when_no_env_var(module_path, monkeypatch):
    """Without the env var, the loader reads config/model.yaml as before."""
    monkeypatch.delenv("MODEL_SNAPSHOT_OVERRIDE", raising=False)
    mod = importlib.import_module(module_path)
    snapshot = mod._load_model_snapshot()
    # Should match the yaml's current production setting (Opus 4.1)
    assert snapshot == "claude-opus-4-1-20250805"


def test_eval_runner_sets_sonnet_override():
    """eval/runner.py must set MODEL_SNAPSHOT_OVERRIDE to Sonnet at import."""
    # Force a fresh import so module-level os.environ assignment fires
    import sys
    if "eval.runner" in sys.modules:
        del sys.modules["eval.runner"]
    import eval.runner  # noqa: F401
    assert os.environ.get("MODEL_SNAPSHOT_OVERRIDE") == "claude-sonnet-4-5-20250929"
