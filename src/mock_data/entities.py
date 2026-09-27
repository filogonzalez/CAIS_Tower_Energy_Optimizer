"""Pure pandas/numpy generators for every non-telemetry synthetic dataset.

Kept Spark-agnostic so each generator is directly unit-testable; the Spark
orchestration (distributed conversion + Volume writes) lives in
``generate_energy_data.py``.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
from common.timeutils import pr_midnight_utc

from mock_data import climate
from mock_data.config import (
    COMPONENT_CATALOG,
    CRITICALITY_TIERS,
    DUST_WEEK_DURATION_DAYS,
    DUST_WEEK_OFFSET_DAYS,
    LOAD_SHEDDING_CLUSTERS,
    REGIONS,
    SITE_TYPES,
    SYNTHETIC_STORM,
    TERRAIN_TYPES,
    WORK_ORDER_STATUSES,
    WORK_ORDER_TYPES,
)
from mock_data.geo import CULEBRA_POLYGON, PR_MAIN_POLYGON, VIEQUES_POLYGON, sample_land_point
from mock_data.random_streams import stream, weighted_choice

TERRAIN_BY_REGION = {
    "Metro": ["urban", "urban", "suburban"],
    "North": ["coastal", "suburban", "rural"],
    "South": ["coastal", "rural", "suburban"],
    "East": ["coastal", "rural", "mountain"],
    "West": ["coastal", "rural", "suburban"],
    "Central": ["mountain", "rural", "mountain"],
    "Islands": ["coastal", "coastal"],
}

CRITICALITY_WEIGHTS = [0.10, 0.30, 0.60]  # tier1_critical, tier2_high, tier3_standard


def telemetry_window(reference_date: date, telemetry_days: int) -> tuple[date, date]:
    end_date = reference_date
    start_date = end_date - timedelta(days=telemetry_days - 1)
    return start_date, end_date


def _region_polygon(region: str):
    return VIEQUES_POLYGON if region == "Islands" else PR_MAIN_POLYGON


def generate_sites(seed: int, site_count: int, reference_date: date) -> pd.DataFrame:
    region_names = list(REGIONS.keys())
    region_weights = [REGIONS[r]["weight"] for r in region_names]
    site_type_names = list(SITE_TYPES.keys())
    site_type_weights = [SITE_TYPES[t]["share"] for t in site_type_names]

    rows = []
    for i in range(site_count):
        site_id = f"SITE-{i:04d}"
        rng = stream(seed, "site", site_id)
        region = weighted_choice(rng, region_names, region_weights)
        municipio = rng.choice(REGIONS[region]["municipios"])
        site_type = weighted_choice(rng, site_type_names, site_type_weights)
        cap_lo, cap_hi = SITE_TYPES[site_type]["capacity_kw"]
        capacity_kw = round(float(rng.uniform(cap_lo, cap_hi)), 2)

        # Culebra gets a couple of dedicated sites within the Islands region.
        polygon = CULEBRA_POLYGON if (region == "Islands" and i % 11 == 0) else _region_polygon(region)
        lon, lat = sample_land_point(rng, polygon)

        terrain = rng.choice(TERRAIN_BY_REGION.get(region, TERRAIN_TYPES))
        criticality_tier = weighted_choice(rng, CRITICALITY_TIERS, CRITICALITY_WEIGHTS)
        truck_roll_km = round(float(rng.uniform(3.0, 65.0)), 1)
        truck_roll_minutes = int(truck_roll_km * rng.uniform(1.6, 2.4))
        commissioned_days_ago = int(rng.integers(365, 15 * 365))
        commissioned_date = reference_date - timedelta(days=commissioned_days_ago)

        rows.append(
            {
                "site_id": site_id,
                "site_name": f"{municipio} {site_type.replace('_', ' ').title()} {i:04d}",
                "region": region,
                "municipio": municipio,
                "site_type": site_type,
                "capacity_kw": capacity_kw,
                "longitude": lon,
                "latitude": lat,
                "terrain": terrain,
                "criticality_tier": criticality_tier,
                "truck_roll_distance_km": truck_roll_km,
                "truck_roll_minutes": truck_roll_minutes,
                "commissioned_date": commissioned_date.isoformat(),
                "coord_shape_provenance": "hand-digitized simplified coastline (mock_data/geo.py)",
                "coord_tolerance_deg": 0.01,
            }
        )
    return pd.DataFrame(rows)


COMPONENT_CAPACITY_RANGES = {
    "rectifier": (50.0, 400.0, "amps"),
    "battery_bank": (200.0, 1200.0, "amp_hours"),
    "hvac_unit": (2.0, 10.0, "tons"),
    "generator": (10.0, 60.0, "kw"),
    "solar_array": (2.0, 20.0, "kw"),
    "fuel_tank": (100.0, 1000.0, "gallons"),
    "controller": (1.0, 1.0, "unit"),
    "antenna_system": (1.0, 6.0, "sectors"),
}
MANUFACTURERS = ["Vertiv", "Eaton", "Cummins", "Generac", "Trojan", "Delta", "Huawei", "Ericsson"]


def generate_equipment_assets(seed: int, sites: pd.DataFrame, reference_date: date) -> pd.DataFrame:
    rows = []
    counter = 0
    for site in sites.itertuples():
        for component, spec in COMPONENT_CATALOG.items():
            if site.site_type not in spec["site_types"]:
                continue
            rng = stream(seed, "asset", site.site_id, component)
            if rng.random() > spec["p"]:
                continue
            quantity = 2 if component in {"rectifier", "battery_bank", "hvac_unit"} else 1
            for unit_index in range(quantity):
                asset_id = f"ASSET-{counter:05d}"
                counter += 1
                cap_lo, cap_hi, unit = COMPONENT_CAPACITY_RANGES[component]
                rated_capacity = round(float(rng.uniform(cap_lo, cap_hi)), 1)
                commissioned = date.fromisoformat(site.commissioned_date)
                install_offset = int(rng.integers(0, 45))
                installation_date = commissioned + timedelta(days=install_offset)
                age_days = (reference_date - installation_date).days
                last_pm_offset = int(rng.integers(15, 200)) if age_days > 200 else None
                last_pm_date = (
                    (reference_date - timedelta(days=last_pm_offset)).isoformat() if last_pm_offset else None
                )
                warranty_years = int(rng.integers(2, 6))
                warranty_expiration_date = installation_date + timedelta(days=warranty_years * 365)
                rows.append(
                    {
                        "asset_id": asset_id,
                        "site_id": site.site_id,
                        "component": component,
                        "manufacturer": str(rng.choice(MANUFACTURERS)),
                        "model_number": (
                            f"{component[:3].upper()}-{unit_index + 1}-" f"{int(rng.integers(1000, 9999))}"
                        ),
                        "rated_capacity": rated_capacity,
                        "rated_capacity_unit": unit,
                        "installation_date": installation_date.isoformat(),
                        "last_pm_date": last_pm_date,
                        "warranty_expiration_date": warranty_expiration_date.isoformat(),
                    }
                )
    return pd.DataFrame(rows)


def _storm_window_dates(start_date: date) -> tuple[date, date]:
    storm_start = start_date + timedelta(days=SYNTHETIC_STORM.start_offset_days)
    storm_end = storm_start + timedelta(days=SYNTHETIC_STORM.duration_days - 1)
    return storm_start, storm_end


def _dust_window_dates(start_date: date) -> tuple[date, date]:
    dust_start = start_date + timedelta(days=DUST_WEEK_OFFSET_DAYS)
    dust_end = dust_start + timedelta(days=DUST_WEEK_DURATION_DAYS - 1)
    return dust_start, dust_end


def generate_grid_outage_events(
    seed: int, sites: pd.DataFrame, reference_date: date, telemetry_days: int
) -> pd.DataFrame:
    start_date, end_date = telemetry_window(reference_date, telemetry_days)
    storm_start, storm_end = _storm_window_dates(start_date)
    rows = []
    counter = 0

    cluster_by_region = {c["region"]: c for c in LOAD_SHEDDING_CLUSTERS}

    for site in sites.itertuples():
        rng = stream(seed, "outages", site.site_id)
        feeder_id = f"FDR-{site.municipio[:3].upper()}-{int(rng.integers(1, 25)):02d}"

        # Baseline brownout/outage rate: ~0.5-2 short outages/month.
        n_baseline = int(rng.integers(6, 13))
        for _ in range(n_baseline):
            day_offset = int(rng.integers(0, telemetry_days))
            outage_day = start_date + timedelta(days=day_offset)
            if storm_start <= outage_day <= storm_end:
                continue  # storm outages handled separately below
            hour = int(rng.integers(0, 24))
            start_ts = pr_midnight_utc(outage_day) + timedelta(hours=hour)
            duration_min = int(rng.integers(15, 240))
            cause = str(
                rng.choice(["equipment_failure", "vegetation", "vehicle_accident", "scheduled_maint"])
            )
            rows.append(
                {
                    "outage_id": f"OUT-{counter:05d}",
                    "site_id": site.site_id,
                    "feeder_id": feeder_id,
                    "municipio": site.municipio,
                    "start_ts_utc": start_ts,
                    "end_ts_utc": start_ts + timedelta(minutes=duration_min),
                    "cause": cause,
                    "is_storm_related": False,
                    "load_shedding_cluster": None,
                }
            )
            counter += 1

        # Evening load-shedding, only for sites in a clustered region.
        cluster = cluster_by_region.get(site.region)
        if cluster is not None and rng.random() < 0.50:
            n_shed = int(rng.integers(5, 12))
            for _ in range(n_shed):
                day_offset = int(rng.integers(0, telemetry_days))
                outage_day = start_date + timedelta(days=day_offset)
                if storm_start <= outage_day <= storm_end:
                    continue
                h0, h1 = (int(value) for value in cluster["hours"])
                start_ts = pr_midnight_utc(outage_day) + timedelta(hours=h0)
                duration_min = int((h1 - h0) * 60 * rng.uniform(0.5, 1.0))
                rows.append(
                    {
                        "outage_id": f"OUT-{counter:05d}",
                        "site_id": site.site_id,
                        "feeder_id": feeder_id,
                        "municipio": site.municipio,
                        "start_ts_utc": start_ts,
                        "end_ts_utc": start_ts + timedelta(minutes=duration_min),
                        "cause": "load_shedding",
                        "is_storm_related": False,
                        "load_shedding_cluster": cluster["cluster_id"],
                    }
                )
                counter += 1

        # Storm outage: applies to sites in SYNTHETIC_STORM.affected_regions.
        if site.region in SYNTHETIC_STORM.affected_regions:
            storm_start_ts = pr_midnight_utc(storm_start) + timedelta(hours=int(rng.integers(0, 6)))
            storm_duration_hours = float(rng.uniform(30.0, SYNTHETIC_STORM.duration_days * 24))
            rows.append(
                {
                    "outage_id": f"OUT-{counter:05d}",
                    "site_id": site.site_id,
                    "feeder_id": feeder_id,
                    "municipio": site.municipio,
                    "start_ts_utc": storm_start_ts,
                    "end_ts_utc": storm_start_ts + timedelta(hours=storm_duration_hours),
                    "cause": "storm",
                    "is_storm_related": True,
                    "load_shedding_cluster": None,
                }
            )
            counter += 1

    return pd.DataFrame(rows)


def generate_weather_daily(reference_date: date, telemetry_days: int) -> pd.DataFrame:
    start_date, end_date = telemetry_window(reference_date, telemetry_days)
    storm_start, storm_end = _storm_window_dates(start_date)
    dust_start, dust_end = _dust_window_dates(start_date)
    rows = []
    for region_name, region in REGIONS.items():
        for municipio in region["municipios"]:
            rng = stream(0, "weather", municipio)  # weather is a shared civic fact, not per-run-secret
            for day_offset in range(telemetry_days):
                day = start_date + timedelta(days=day_offset)
                doy = day.timetuple().tm_yday
                is_storm = storm_start <= day <= storm_end and region_name in SYNTHETIC_STORM.affected_regions
                is_dust = dust_start <= day <= dust_end
                high, low = climate.daily_high_low_c(region_name, doy, is_storm=is_storm, is_dust=is_dust)
                noise = float(rng.normal(0, 0.4))
                humidity = climate.humidity_pct(
                    region_name, is_storm=is_storm, noise_pct=float(rng.normal(0, 3))
                )
                rainfall = float(rng.exponential(3.0)) if not is_storm else float(rng.uniform(80, 220))
                wind = float(rng.uniform(8, 20)) if not is_storm else float(rng.uniform(55, 110))
                rows.append(
                    {
                        "municipio": municipio,
                        "local_date": day.isoformat(),
                        "high_temp_c": round(high + noise, 1),
                        "low_temp_c": round(low + noise, 1),
                        "humidity_pct": round(humidity, 1),
                        "rainfall_mm": round(max(0.0, rainfall), 1),
                        "wind_kph": round(wind, 1),
                        "is_storm_day": bool(is_storm),
                        "is_dust_day": bool(is_dust),
                        "storm_name": SYNTHETIC_STORM.name if is_storm else None,
                    }
                )
    return pd.DataFrame(rows)


def generate_energy_tariffs(reference_date: date, telemetry_days: int, settings) -> pd.DataFrame:
    start_date, end_date = telemetry_window(reference_date, telemetry_days)
    rows = []
    for day_offset in range(telemetry_days):
        day = start_date + timedelta(days=day_offset)
        rows.append(
            {
                "local_date": day.isoformat(),
                "grid_price_usd_per_kwh": settings.grid_price_usd_per_kwh,
                "diesel_price_usd_per_gal": settings.diesel_price_usd_per_gal,
                "diesel_emissions_kg_co2_per_gal": settings.diesel_emissions_kg_co2_per_gal,
                "diesel_gal_per_kwh": settings.diesel_gal_per_kwh,
            }
        )
    return pd.DataFrame(rows)


def hash_technician(seed: int, name: str) -> str:
    import hashlib

    return hashlib.sha256(f"{seed}|{name}".encode()).hexdigest()[:16]


def generate_work_order_history(
    seed: int,
    sites: pd.DataFrame,
    assets: pd.DataFrame,
    faults: pd.DataFrame,
    reference_date: date,
    work_order_months: int,
    target_count: int = 10_000,
) -> pd.DataFrame:
    """Create synthetic bilingual work orders plus causal fault resolutions."""
    start_date = reference_date - timedelta(days=work_order_months * 30)
    rows: list[dict] = []
    asset_groups = {site_id: group.reset_index(drop=True) for site_id, group in assets.groupby("site_id")}
    notes = {
        "en": [
            "Inspected {component}; cleaned terminals and verified normal operation.",
            "Corrective visit for {component}; replaced worn part after heat and humidity exposure.",
            "Emergency restoration of {component}; service returned after diagnostics.",
        ],
        "es": [
            "Se inspeccionó {component}; se limpiaron terminales y se verificó operación normal.",
            "Visita correctiva para {component}; pieza desgastada reemplazada por calor y humedad.",
            "Restauración de emergencia de {component}; servicio recuperado tras diagnóstico.",
        ],
    }
    for index in range(max(0, target_count - len(faults))):
        rng = stream(seed, "work_order", index)
        site = sites.iloc[int(rng.integers(0, len(sites)))]
        site_assets = asset_groups[site.site_id]
        asset = site_assets.iloc[int(rng.integers(0, len(site_assets)))]
        wo_type = str(rng.choice(WORK_ORDER_TYPES, p=[0.52, 0.36, 0.12]))
        opened_day = start_date + timedelta(
            days=int(rng.integers(0, max(1, (reference_date - start_date).days)))
        )
        opened = pr_midnight_utc(opened_day) + timedelta(hours=int(rng.integers(6, 20)))
        status = str(rng.choice(WORK_ORDER_STATUSES))
        close_hours = int(rng.integers(2, 96))
        closed = min(
            opened + timedelta(hours=close_hours), pr_midnight_utc(reference_date + timedelta(days=1))
        )
        language = "es" if rng.random() < 0.58 else "en"
        note_template = notes[language][{"preventive": 0, "corrective": 1, "emergency": 2}[wo_type]]
        rows.append(
            {
                "wo_id": f"WO-{index:06d}",
                "site_id": site.site_id,
                "asset_id": asset.asset_id,
                "component": asset.component,
                "wo_type": wo_type,
                "status": status,
                "opened_ts_utc": opened,
                "closed_ts_utc": closed if status == "completed" else None,
                "downtime_minutes": round(float(rng.uniform(0, 480)), 1) if wo_type != "preventive" else 0.0,
                "cost_usd": round(float(rng.uniform(80, 4_500)), 2),
                "parts_used": [] if wo_type == "preventive" else [f"{asset.component}_service_kit"],
                "technician_hash": hash_technician(seed, f"tech-{int(rng.integers(1, 80)):03d}"),
                "notes_raw_text": note_template.format(component=asset.component.replace("_", " ")),
                "notes_language": language,
            }
        )

    for fault in faults.itertuples():
        rows.append(
            {
                "wo_id": fault.resolving_wo_id,
                "site_id": fault.site_id,
                "asset_id": fault.asset_id,
                "component": fault.component,
                "wo_type": "emergency" if "failure" in fault.fault_type else "corrective",
                "status": "completed",
                "opened_ts_utc": fault.detection_deadline_ts_utc,
                "closed_ts_utc": fault.resolution_ts_utc,
                "downtime_minutes": 120.0,
                "cost_usd": 1_250.0,
                "parts_used": [f"{fault.component}_replacement"],
                "technician_hash": hash_technician(seed, f"fault-tech-{fault.fault_id}"),
                "notes_raw_text": (
                    f"Confirmed synthetic {fault.fault_type.replace('_', ' ')}; "
                    f"repaired {fault.component.replace('_', ' ')} and verified recovery."
                ),
                "notes_language": "en",
            }
        )
    return pd.DataFrame(rows).sort_values("opened_ts_utc").reset_index(drop=True)
