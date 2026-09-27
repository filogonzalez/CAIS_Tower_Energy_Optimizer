"""Phase 1 deterministic data-contract validation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from mock_data.geo import is_on_land


def dataframe_fingerprint(frame: pd.DataFrame, columns: list[str] | None = None) -> str:
    selected = frame[columns] if columns else frame
    normalized = selected.sort_values(list(selected.columns)).reset_index(drop=True)
    payload = normalized.to_json(orient="records", date_format="iso", force_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def validate_generation(datasets: dict[str, pd.DataFrame], expected_sites: int, telemetry_days: int) -> dict:
    sites = datasets["sites"]
    assets = datasets["equipment_assets"]
    telemetry = datasets["energy_telemetry"]
    outages = datasets["grid_outage_events"]
    work_orders = datasets["work_order_history"]
    faults = datasets["injected_faults"]
    expected_readings = expected_sites * telemetry_days * 24
    source_total = (
        telemetry.grid_kwh + telemetry.generator_kwh + telemetry.battery_discharge_kwh + telemetry.solar_kwh
    )
    sink_total = telemetry.served_load_kwh + telemetry.battery_charge_kwh
    checks = {
        "site_count": len(sites) == expected_sites,
        "telemetry_count": len(telemetry) == expected_readings,
        "telemetry_unique": telemetry[["site_id", "ts_utc"]].drop_duplicates().shape[0] == expected_readings,
        "fault_site_count": len(faults) == 36 and faults.site_id.nunique() == 36,
        "coordinates_on_land": all(is_on_land(row.longitude, row.latitude) for row in sites.itertuples()),
        "asset_site_fk": set(assets.site_id).issubset(set(sites.site_id)),
        "telemetry_site_fk": set(telemetry.site_id).issubset(set(sites.site_id)),
        "outage_site_fk": set(outages.site_id).issubset(set(sites.site_id)),
        "work_order_site_fk": set(work_orders.site_id).issubset(set(sites.site_id)),
        "fault_asset_fk": set(faults.asset_id).issubset(set(assets.asset_id)),
        "resolving_work_order_fk": set(faults.resolving_wo_id).issubset(set(work_orders.wo_id)),
        "soc_bounds": telemetry.battery_soc_pct.between(0, 100).all(),
        "nonnegative_energy": (
            telemetry[["grid_kwh", "generator_kwh", "battery_discharge_kwh", "solar_kwh"]] >= 0
        )
        .all()
        .all(),
        "source_balance": (source_total - sink_total).abs().max() <= 0.001,
        "fuel_bounds": (telemetry.fuel_level_gal.dropna() >= 0).all(),
        "deadline_causality": (faults.symptom_onset_ts_utc < faults.detection_deadline_ts_utc).all(),
    }
    native_checks = {name: bool(value) for name, value in checks.items()}
    return {
        "passed": all(native_checks.values()),
        "checks": native_checks,
        "counts": {name: int(len(frame)) for name, frame in datasets.items()},
        "fingerprints": {
            "sites": dataframe_fingerprint(
                sites, ["site_id", "region", "municipio", "longitude", "latitude"]
            ),
            "faults": dataframe_fingerprint(faults),
        },
    }


def write_validation_report(report: dict, path: str | Path) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    return output
