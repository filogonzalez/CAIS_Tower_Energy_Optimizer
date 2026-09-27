"""Bundle-aware console entrypoint that applies non-secret runtime variables."""

from __future__ import annotations

import argparse
import importlib
import os
import sys
from pathlib import Path

RUNTIME_OPTIONS = {
    "target": "TARGET",
    "brand": "BRAND",
    "catalog": "CATALOG",
    "schema_raw": "SCHEMA_RAW",
    "schema_curated": "SCHEMA_CURATED",
    "schema_analytics": "SCHEMA_ANALYTICS",
    "schema_ml": "SCHEMA_ML",
    "schema_agents": "SCHEMA_AGENTS",
    "volume_name": "VOLUME_NAME",
    "seed": "SEED",
    "reference_date": "REFERENCE_DATE",
    "site_count": "SITE_COUNT",
    "telemetry_days": "TELEMETRY_DAYS",
    "storm_start_offset_days": "STORM_START_OFFSET_DAYS",
    "storm_duration_days": "STORM_DURATION_DAYS",
    "dust_start_offset_days": "DUST_START_OFFSET_DAYS",
    "dust_duration_days": "DUST_DURATION_DAYS",
    "grid_price": "GRID_PRICE",
    "diesel_price": "DIESEL_PRICE",
    "diesel_emissions_factor": "DIESEL_EMISSIONS_FACTOR",
    "diesel_burn_rate": "DIESEL_BURN_RATE",
    "hvac_capex_usd": "HVAC_CAPEX_USD",
    "rectifier_capex_usd": "RECTIFIER_CAPEX_USD",
    "battery_capex_usd": "BATTERY_CAPEX_USD",
    "solar_capex_usd": "SOLAR_CAPEX_USD",
    "retrofit_annual_maintenance_pct": "RETROFIT_ANNUAL_MAINTENANCE_PCT",
    "extraction_llm_endpoint": "EXTRACTION_LLM_ENDPOINT",
    "agent_llm_endpoint": "AGENT_LLM_ENDPOINT",
    "agent_llm_fallback_endpoint": "AGENT_LLM_FALLBACK_ENDPOINT",
    "embedding_endpoint": "EMBEDDING_ENDPOINT",
    "vector_search_endpoint": "VECTOR_SEARCH_ENDPOINT",
    "agent_serving_endpoint": "AGENT_SERVING_ENDPOINT",
    "warehouse_id": "WAREHOUSE_ID",
    "lakebase_instance": "LAKEBASE_INSTANCE",
    "lakebase_database": "LAKEBASE_DATABASE",
    "genie_space_name": "GENIE_SPACE_NAME",
    "app_name": "APP_NAME",
    "engineering_group": "ENGINEERING_GROUP",
    "analyst_group": "ANALYST_GROUP",
    "field_manager_group": "FIELD_MANAGER_GROUP",
    "finance_group": "FINANCE_GROUP",
    "approver_group": "APPROVER_GROUP",
}

DISPATCH = {
    "teo-bootstrap-catalog": ("validation.bootstrap_catalog", "main"),
    "teo-capabilities": ("validation.capability_manifest", "main"),
    "teo-generate": ("mock_data.generate_energy_data", "main"),
    "teo-upload": ("mock_data.upload_to_volume", "main"),
    "teo-train-baseline": ("ml.train_baseline_anomaly", "main"),
    "teo-train-failure": ("ml.train_failure_risk", "main"),
    "teo-batch-score": ("ml.batch_score", "main"),
    "teo-setup-lakebase": ("lakebase.setup_lakebase", "main"),
    "teo-upsert-lakebase": ("lakebase.upsert_site_status", "main"),
    "teo-mirror-audit": ("lakebase.mirror_audit_to_delta", "main"),
    "teo-create-index": ("vector_search.create_index", "main"),
    "teo-setup-genie": ("genie.setup_genie", "main"),
    "teo-simulate": ("connect.resilience_simulator", "main"),
    "teo-phase-checks": ("validation.phase_checks", "main"),
}


def main() -> object:
    command = Path(sys.argv[0]).name
    parser = argparse.ArgumentParser(add_help=False)
    for option in RUNTIME_OPTIONS:
        parser.add_argument(f"--{option.replace('_', '-')}")
    runtime, remaining = parser.parse_known_args()
    for option, env_suffix in RUNTIME_OPTIONS.items():
        value = getattr(runtime, option)
        if value not in {None, ""}:
            os.environ[f"TEO_{env_suffix}"] = str(value)
    if command not in DISPATCH:
        raise RuntimeError(f"Unknown Tower Energy Optimizer entrypoint: {command}")
    sys.argv = [command, *remaining]
    module_name, function_name = DISPATCH[command]
    function = getattr(importlib.import_module(module_name), function_name)
    return function()
