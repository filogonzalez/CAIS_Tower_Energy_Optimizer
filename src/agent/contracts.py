"""Structured recommendation contract."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str
    observed_at_ast: str
    value: str
    incident_ids: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    site_id: str
    asset_id: str | None = None
    action: str
    urgency: Literal["monitor", "schedule", "urgent"]
    score_status: Literal["scored", "unscored"]
    rationale: list[str]
    evidence: list[Evidence]
    narrative_en: str
    narrative_es: str
    estimated_value_usd: float | None = None
    proposal_key: str
    dispatch_authorized: Literal[False] = False
