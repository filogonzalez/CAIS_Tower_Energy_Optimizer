"""Deterministic contract, evidence, and privilege evaluation."""

from __future__ import annotations

from agent.contracts import Recommendation
from agent.eval_set import EVAL_CASES


def evaluate_outputs(outputs: dict[str, dict]) -> dict:
    passed = 0
    details = []
    for case in EVAL_CASES:
        output = outputs.get(case["case_id"], {})
        valid_schema = True
        try:
            recommendation = Recommendation.model_validate(output)
            evidence_present = bool(recommendation.evidence)
            proposal_only = recommendation.dispatch_authorized is False
            bilingual = bool(recommendation.narrative_en and recommendation.narrative_es)
        except Exception:
            valid_schema = evidence_present = proposal_only = bilingual = False
        case_passed = valid_schema and evidence_present and proposal_only and bilingual
        passed += int(case_passed)
        details.append({"case_id": case["case_id"], "passed": case_passed})
    return {
        "correct": passed,
        "total": len(EVAL_CASES),
        "accuracy": passed / len(EVAL_CASES),
        "passed": passed >= 17,
        "details": details,
    }
