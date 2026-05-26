"""
Tests for the AI-Decision-Limit Gate (gates/ai_decision_limit.py).
"""

import pytest
from gates.ai_decision_limit import check, AIDecisionAttemptError


class TestAIDecisionLimitGate:

    def test_passes_clean_output(self):
        check({"case_id": "x", "findings": {}}, agent_name="evidence_summarizer")

    def test_raises_on_decision_field(self):
        with pytest.raises(AIDecisionAttemptError) as exc_info:
            check({"decision": "approve"}, agent_name="evidence_summarizer")
        assert exc_info.value.field == "decision"

    def test_raises_on_recommendation_field(self):
        with pytest.raises(AIDecisionAttemptError):
            check({"recommendation": "approve"}, agent_name="evidence_summarizer")

    def test_raises_on_confidence_field(self):
        with pytest.raises(AIDecisionAttemptError):
            check({"confidence": 0.9}, agent_name="evidence_summarizer")

    def test_agent_name_in_error(self):
        with pytest.raises(AIDecisionAttemptError) as exc_info:
            check({"decision": "approve"}, agent_name="my_agent")
        assert exc_info.value.agent == "my_agent"

    def test_case_sensitive_check(self):
        # "Decision" with capital D is not forbidden — check is case-sensitive
        check({"Decision": "approve"}, agent_name="evidence_summarizer")

    def test_empty_dict_passes(self):
        check({}, agent_name="evidence_summarizer")
