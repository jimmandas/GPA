"""
Tests for the Denial Gate (gates/denial.py).
"""

import pytest
from gates.denial import check, DenialAttemptError


class TestDenialGate:

    def test_passes_approve(self):
        check({"path": "approve"})

    def test_passes_escalate(self):
        check({"path": "escalate"})

    def test_passes_pend(self):
        check({"path": "pend"})

    def test_raises_on_deny(self):
        with pytest.raises(DenialAttemptError):
            check({"path": "deny"})

    def test_raises_on_unknown_path(self):
        with pytest.raises(DenialAttemptError):
            check({"path": "auto_approve"})

    def test_raises_on_missing_path_key(self):
        with pytest.raises(ValueError):
            check({})

    def test_denial_attempt_error_has_path(self):
        with pytest.raises(DenialAttemptError) as exc_info:
            check({"path": "deny"})
        assert exc_info.value.path == "deny"
