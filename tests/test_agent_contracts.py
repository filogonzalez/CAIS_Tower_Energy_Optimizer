import pytest
from agent.contracts import Recommendation
from pydantic import ValidationError


def test_agent_cannot_authorize_dispatch():
    payload = {
        "site_id": "SITE-0001",
        "action": "inspect rectifier",
        "urgency": "schedule",
        "score_status": "scored",
        "rationale": ["risk"],
        "evidence": [{"source": "scores", "observed_at_ast": "2026-09-26 10:00 AST", "value": "0.7"}],
        "narrative_en": "Review.",
        "narrative_es": "Revisar.",
        "proposal_key": "key",
        "dispatch_authorized": True,
    }
    with pytest.raises(ValidationError):
        Recommendation.model_validate(payload)
