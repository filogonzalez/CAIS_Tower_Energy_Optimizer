"""Create/update the governed bilingual Genie space and validation prompts."""

from __future__ import annotations

import json
from pathlib import Path

from common.databricks_auth import get_workspace_client
from config.settings import get_settings

REFERENCE_QUESTIONS = [
    "Which regions had the highest HVAC energy per GB last complete month?",
    "¿Qué sitios tuvieron mayor costo de diésel el mes pasado?",
    "Show Tier 1 sites with low outage resilience and open work orders.",
    "Compare solar contribution and ambient temperature by region.",
    "Which scored assets have the highest 14-day failure risk?",
    "¿Qué sitios empeoraron frente a su cohorte de eficiencia?",
    "Show approved and rejected maintenance decisions from the governed audit.",
]


def space_payload() -> dict:
    settings = get_settings()
    return {
        "title": settings.genie_space_name,
        "description": f"Governed synthetic Energy NOC analytics for {settings.brand} in Puerto Rico.",
        "warehouse_id": settings.warehouse_id,
        "table_identifiers": [
            settings.table_curated("silver_sites"),
            settings.table_analytics("gold_daily_site_energy"),
            settings.table_analytics("gold_site_benchmark"),
            settings.table_analytics("gold_site_priority"),
            settings.table_analytics("outage_scenario_results"),
            settings.table_analytics("retrofit_roi"),
            settings.table_analytics("agent_audit_log"),
        ],
        "sample_questions": REFERENCE_QUESTIONS,
        "instructions": [
            "All timestamps are stored in UTC; display dates and hours in America/Puerto_Rico (AST).",
            "Use USD, kWh, kW and gallons explicitly. kW is not kWh unless interval_hours is one.",
            "Use only the last complete calendar month when a question says last month.",
            "Never query raw_telemetry or injected_faults.",
            "Spanish synonyms: sitio=site, apagón=outage, diésel=diesel, orden de trabajo=work order.",
            "Do not call unscored assets healthy; surface score_status.",
        ],
    }


def create_or_update_space() -> str:
    settings = get_settings()
    if not settings.warehouse_id:
        raise RuntimeError("TEO_WAREHOUSE_ID is required for Genie setup")
    client = get_workspace_client()
    payload = space_payload()
    spaces = client.api_client.do("GET", "/api/2.0/genie/spaces") or {}
    existing = next(
        (item for item in spaces.get("spaces", []) if item.get("title") == settings.genie_space_name), None
    )
    if existing:
        space_id = existing["space_id"]
        client.api_client.do("PATCH", f"/api/2.0/genie/spaces/{space_id}", body=payload)
    else:
        created = client.api_client.do("POST", "/api/2.0/genie/spaces", body=payload)
        space_id = created["space_id"]
    Path("artifacts").mkdir(exist_ok=True)
    Path("artifacts/genie_reference_questions.json").write_text(
        json.dumps({"space_id": space_id, "questions": REFERENCE_QUESTIONS}, indent=2), encoding="utf-8"
    )
    return str(space_id)


def main() -> None:
    print(create_or_update_space())


if __name__ == "__main__":
    main()
