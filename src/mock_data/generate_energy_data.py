"""Generate the versioned Puerto Rico synthetic source snapshot."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import pandas as pd
from common.manifest import build_manifest, save_manifest_local
from common.timeutils import yesterday_in_puerto_rico
from config.settings import Settings, get_settings

from mock_data.entities import (
    generate_energy_tariffs,
    generate_equipment_assets,
    generate_grid_outage_events,
    generate_sites,
    generate_weather_daily,
    generate_work_order_history,
)
from mock_data.inject_faults import generate_injected_faults
from mock_data.telemetry import generate_energy_telemetry
from mock_data.validation import validate_generation, write_validation_report


def resolve_reference_date(settings: Settings) -> date:
    return (
        date.fromisoformat(settings.reference_date_override)
        if settings.reference_date_override
        else yesterday_in_puerto_rico()
    )


def _write_frame(frame: pd.DataFrame, root: Path, name: str, fmt: str = "parquet") -> None:
    output = root / name
    output.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        frame.to_json(
            output / "part-00000.json", orient="records", lines=True, date_format="iso", force_ascii=False
        )
    else:
        frame.to_parquet(output / "part-00000.parquet", index=False)


def generate_snapshot(settings: Settings, output_root: str | Path) -> tuple[Path, dict]:
    reference_date = resolve_reference_date(settings)
    run_id = f"seed-{settings.seed}-asof-{reference_date.isoformat()}"
    root = Path(output_root) / run_id
    root.mkdir(parents=True, exist_ok=True)
    manifest = build_manifest(settings, reference_date, run_id)
    existing_manifest = root / "generation_manifest.json"
    if existing_manifest.exists():
        existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
        if existing.get("config_digest") != manifest.config_digest:
            raise RuntimeError(f"Refusing to overwrite {root}: manifest configuration differs")

    sites = generate_sites(settings.seed, settings.site_count, reference_date)
    assets = generate_equipment_assets(settings.seed, sites, reference_date)
    outages = generate_grid_outage_events(settings.seed, sites, reference_date, settings.telemetry_days)
    weather = generate_weather_daily(reference_date, settings.telemetry_days)
    tariffs = generate_energy_tariffs(reference_date, settings.telemetry_days, settings)
    faults = generate_injected_faults(settings.seed, sites, assets, reference_date, settings.telemetry_days)
    work_orders = generate_work_order_history(
        settings.seed, sites, assets, faults, reference_date, settings.work_order_months
    )
    telemetry = generate_energy_telemetry(
        settings.seed,
        sites,
        assets,
        outages,
        faults,
        reference_date,
        settings.telemetry_days,
        settings,
    )
    datasets = {
        "sites": sites,
        "equipment_assets": assets,
        "energy_telemetry": telemetry,
        "grid_outage_events": outages,
        "weather_daily": weather,
        "work_order_history": work_orders,
        "energy_tariffs": tariffs,
        "injected_faults": faults,
    }
    for name, frame in datasets.items():
        _write_frame(frame, root, name, "json" if name == "work_order_history" else "parquet")
    save_manifest_local(manifest, str(root))
    report = validate_generation(datasets, settings.site_count, settings.telemetry_days)
    write_validation_report(report, root / "validation_report.json")
    if not report["passed"]:
        raise RuntimeError(f"Generation validation failed: {report['checks']}")
    return root, report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/generated")
    args = parser.parse_args()
    root, report = generate_snapshot(get_settings(), args.output)
    print(json.dumps({"output": str(root), "counts": report["counts"], "passed": True}, sort_keys=True))


if __name__ == "__main__":
    main()
