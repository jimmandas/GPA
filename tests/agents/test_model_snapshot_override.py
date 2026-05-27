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


def _reimport_runner():
    """Force a fresh import of eval.runner so module-level setup re-runs."""
    import sys
    if "eval.runner" in sys.modules:
        del sys.modules["eval.runner"]
    import eval.runner  # noqa: F401


def test_eval_runner_dev_tier_sets_sonnet_override(monkeypatch):
    """EVAL_TIER unset or 'dev' → MODEL_SNAPSHOT_OVERRIDE pinned to Sonnet."""
    monkeypatch.delenv("EVAL_TIER", raising=False)
    monkeypatch.delenv("MODEL_SNAPSHOT_OVERRIDE", raising=False)
    _reimport_runner()
    assert os.environ.get("MODEL_SNAPSHOT_OVERRIDE") == "claude-sonnet-4-5-20250929"


def test_eval_runner_dev_tier_explicit(monkeypatch):
    """EVAL_TIER=dev produces the same Sonnet override."""
    monkeypatch.setenv("EVAL_TIER", "dev")
    monkeypatch.delenv("MODEL_SNAPSHOT_OVERRIDE", raising=False)
    _reimport_runner()
    assert os.environ.get("MODEL_SNAPSHOT_OVERRIDE") == "claude-sonnet-4-5-20250929"


def test_eval_runner_ship_tier_does_not_override(monkeypatch):
    """EVAL_TIER=ship leaves MODEL_SNAPSHOT_OVERRIDE unset so model.yaml wins."""
    monkeypatch.setenv("EVAL_TIER", "ship")
    monkeypatch.delenv("MODEL_SNAPSHOT_OVERRIDE", raising=False)
    _reimport_runner()
    assert "MODEL_SNAPSHOT_OVERRIDE" not in os.environ


def test_eval_runner_rejects_invalid_tier(monkeypatch):
    """Typos like EVAL_TIER=develop must fail loud at import time."""
    monkeypatch.setenv("EVAL_TIER", "develop")
    monkeypatch.delenv("MODEL_SNAPSHOT_OVERRIDE", raising=False)
    import sys
    if "eval.runner" in sys.modules:
        del sys.modules["eval.runner"]
    with pytest.raises(ValueError, match="EVAL_TIER must be"):
        import eval.runner  # noqa: F401


def test_ship_tier_routes_to_production_opus(monkeypatch):
    """End-to-end: ship tier → agents read model.yaml → Opus snapshot."""
    monkeypatch.setenv("EVAL_TIER", "ship")
    monkeypatch.delenv("MODEL_SNAPSHOT_OVERRIDE", raising=False)
    _reimport_runner()
    # With the override unset, any agent's loader should fall back to yaml.
    from agents.policy_mapper.agent import _load_model_snapshot
    assert _load_model_snapshot() == "claude-opus-4-1-20250805"
