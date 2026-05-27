"""
Tests for eval/rationale_judge.py configuration.

Specifically guards the judge-model snapshot pinning. Aliases like 'gpt-4o'
let OpenAI silently re-route the underlying model, which would drift
faithfulness scores without any change in our code. The default must be
a dated snapshot so the audit record names exactly which model produced
each verdict.
"""

import re

import pytest


def test_default_judge_snapshot_is_pinned_not_alias():
    """The default judge model must be a dated snapshot, not an alias."""
    from eval.rationale_judge import _DEFAULT_JUDGE_SNAPSHOT

    # Dated snapshot pattern: gpt-4o-YYYY-MM-DD (or future-tense variants).
    snapshot_re = re.compile(r"^gpt-\S+-\d{4}-\d{2}-\d{2}$")
    assert snapshot_re.match(_DEFAULT_JUDGE_SNAPSHOT), (
        f"Default judge must be a dated snapshot, got {_DEFAULT_JUDGE_SNAPSHOT!r}. "
        "Aliases (e.g. 'gpt-4o') drift silently and break audit defensibility."
    )


def test_env_var_override_still_works(monkeypatch):
    """FAITHFULNESS_JUDGE_MODEL env var lets ops swap the snapshot per-run."""
    monkeypatch.setenv("FAITHFULNESS_JUDGE_MODEL", "gpt-5-2026-99-99")
    import importlib
    import eval.rationale_judge as judge_mod
    importlib.reload(judge_mod)
    assert judge_mod._JUDGE_MODEL == "gpt-5-2026-99-99"


def test_judge_model_pinned_when_env_unset(monkeypatch):
    """Without the env var, _JUDGE_MODEL falls back to the pinned snapshot."""
    monkeypatch.delenv("FAITHFULNESS_JUDGE_MODEL", raising=False)
    import importlib
    import eval.rationale_judge as judge_mod
    importlib.reload(judge_mod)
    assert judge_mod._JUDGE_MODEL == judge_mod._DEFAULT_JUDGE_SNAPSHOT
