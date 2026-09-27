"""Run manifest: freezes the reference date and config digest for a run.

Non-negotiable contract #4/#5: reproducibility means the same configuration,
reference date, code version, and input snapshot — not just the same random
seed. The reference date ("yesterday in Puerto Rico") is resolved exactly
once, by ``generate_energy_data.py``, and every downstream job (pipeline,
ML, Lakebase refresh, simulator) must read it from this manifest rather than
recomputing "yesterday" independently — recomputing it a day later would
silently desynchronize generation from scoring.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from common.timeutils import UTC

MANIFEST_FILENAME = "generation_manifest.json"


@dataclass(frozen=True)
class RunManifest:
    reference_date: str  # ISO date, America/Puerto_Rico calendar day
    seed: int
    config_digest: str
    generated_at_utc: str
    site_count: int
    telemetry_days: int
    fault_site_count: int
    bundle_target: str
    run_id: str

    @property
    def reference_date_obj(self) -> date:
        return date.fromisoformat(self.reference_date)


def config_digest(settings: Any) -> str:
    """Stable hash of the config fields that affect generated data shape."""
    payload = {
        "seed": settings.seed,
        "site_count": settings.site_count,
        "telemetry_days": settings.telemetry_days,
        "work_order_months": settings.work_order_months,
        "fault_site_count": settings.fault_site_count,
        "storm_start_offset_days": settings.storm_start_offset_days,
        "storm_duration_days": settings.storm_duration_days,
        "dust_start_offset_days": settings.dust_start_offset_days,
        "dust_duration_days": settings.dust_duration_days,
        "grid_price_usd_per_kwh": settings.grid_price_usd_per_kwh,
        "diesel_price_usd_per_gal": settings.diesel_price_usd_per_gal,
        "diesel_emissions_kg_co2_per_gal": settings.diesel_emissions_kg_co2_per_gal,
        "diesel_gal_per_kwh": settings.diesel_gal_per_kwh,
        "hvac_capex_usd": settings.hvac_capex_usd,
        "rectifier_capex_usd": settings.rectifier_capex_usd,
        "battery_capex_usd": settings.battery_capex_usd,
        "solar_capex_usd": settings.solar_capex_usd,
        "brand": settings.brand,
    }
    blob = json.dumps(payload, sort_keys=True).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def build_manifest(settings: Any, reference_date: date, run_id: str) -> RunManifest:
    return RunManifest(
        reference_date=reference_date.isoformat(),
        seed=settings.seed,
        config_digest=config_digest(settings),
        generated_at_utc=datetime.now(tz=UTC).isoformat(),
        site_count=settings.site_count,
        telemetry_days=settings.telemetry_days,
        fault_site_count=settings.fault_site_count,
        bundle_target=settings.target,
        run_id=run_id,
    )


def manifest_local_path(local_root: str) -> Path:
    return Path(local_root) / MANIFEST_FILENAME


def save_manifest_local(manifest: RunManifest, local_root: str) -> Path:
    path = manifest_local_path(local_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True))
    return path


def load_manifest_local(local_root: str) -> RunManifest:
    path = manifest_local_path(local_root)
    if not path.exists():
        raise FileNotFoundError(
            f"No generation manifest at {path}. Run generate_energy_data.py "
            "first — downstream jobs must not guess the reference date."
        )
    data = json.loads(path.read_text())
    return RunManifest(**data)


def save_manifest_volume(manifest: RunManifest, volume_path: str) -> str:
    """Write the manifest into a UC Volume (Databricks runtime path)."""
    target = os.path.join(volume_path, MANIFEST_FILENAME)
    os.makedirs(volume_path, exist_ok=True)
    with open(target, "w") as fh:
        json.dump(asdict(manifest), fh, indent=2, sort_keys=True)
    return target


def load_manifest_volume(volume_path: str) -> RunManifest:
    target = os.path.join(volume_path, MANIFEST_FILENAME)
    if not os.path.exists(target):
        raise FileNotFoundError(
            f"No generation manifest at {target}. Run generate_energy_data.py "
            "first — downstream jobs must not guess the reference date."
        )
    with open(target) as fh:
        data = json.load(fh)
    return RunManifest(**data)
