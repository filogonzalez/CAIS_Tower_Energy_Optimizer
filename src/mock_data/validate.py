"""Phase 1 gate checks for a single generation run.

Every check returns a bool plus enough detail to report a denominator, per
the plan's evidence contract ("report approximate dataset counts and
deviations"). ``validate_generation`` aggregates all checks into one report
dict; callers decide whether to raise on failure (jobs) or just record
(tests exploring edge cases).
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pandas as pd

from mock_data.config import TOTAL_FAULT_SITES
from mock_data.entities import telemetry_window
from mock_data.geo import is_on_land

EPS_KWH = 1e-2


def _check_source_balance(telemetry: pd.DataFrame) -> dict[str, Any]:
    lhs = (
        telemetry["grid_kwh"]
        + telemetry["generator_kwh"]
        + telemetry["battery_discharge_kwh"]
        + telemetry["solar_kwh"]
    )
    rhs = telemetry["served_load_kwh"] + telemetry["battery_charge_kwh"]
    diff = (lhs - rhs).abs()
    bad = int((diff > EPS_KWH).sum())
    return {
        "passed": bad == 0,
        "checked_rows": int(len(telemetry)),
        "violations": bad,
        "max_abs_diff": float(diff.max()) if len(diff) else 0.0,
    }


def _check_orphans(
    name: str, child: pd.DataFrame, child_col: str, parent: pd.DataFrame, parent_col: str
) -> dict[str, Any]:
    orphans = child.loc[~child[child_col].isin(set(parent[parent_col])), child_col]
    return {"passed": orphans.empty, "orphan_count": int(len(orphans)), "check": name}


def validate_generation(
    *,
    sites: pd.DataFrame,
    assets: pd.DataFrame,
    telemetry: pd.DataFrame,
    outages: pd.DataFrame,
    weather: pd.DataFrame,
    work_orders: pd.DataFrame,
    tariffs: pd.DataFrame,
    faults: pd.DataFrame,
    settings: Any,
    reference_date: date,
) -> dict[str, Any]:
    start_date, end_date = telemetry_window(reference_date, settings.telemetry_days)
    expected_telemetry_rows = settings.site_count * settings.telemetry_days * 24

    checks: dict[str, Any] = {}

    checks["site_count"] = {
        "passed": len(sites) == settings.site_count,
        "expected": settings.site_count,
        "actual": int(len(sites)),
    }

    checks["telemetry_row_count"] = {
        "passed": len(telemetry) == expected_telemetry_rows,
        "expected": expected_telemetry_rows,
        "actual": int(len(telemetry)),
    }
    dupe_keys = int(telemetry.duplicated(subset=["site_id", "ts_utc"]).sum())
    checks["telemetry_unique_keys"] = {"passed": dupe_keys == 0, "duplicate_rows": dupe_keys}

    checks["fault_site_count"] = {
        "passed": faults["site_id"].nunique() == TOTAL_FAULT_SITES == settings.fault_site_count,
        "expected": settings.fault_site_count,
        "actual": int(faults["site_id"].nunique()),
    }
    fault_sites_in_telemetry = set(faults["site_id"]) <= set(telemetry["site_id"])
    checks["fault_sites_present_in_telemetry"] = {"passed": fault_sites_in_telemetry}

    land_ok = sites.apply(lambda r: is_on_land(r["longitude"], r["latitude"]), axis=1)
    checks["valid_land_coordinates"] = {
        "passed": bool(land_ok.all()),
        "off_land_count": int((~land_ok).sum()),
        "checked": int(len(sites)),
    }

    checks["orphans_assets_to_sites"] = _check_orphans("assets->sites", assets, "site_id", sites, "site_id")
    checks["orphans_outages_to_sites"] = _check_orphans(
        "outages->sites", outages, "site_id", sites, "site_id"
    )
    checks["orphans_wo_to_sites"] = _check_orphans(
        "work_orders->sites", work_orders, "site_id", sites, "site_id"
    )
    non_null_assets = work_orders.dropna(subset=["asset_id"])
    checks["orphans_wo_to_assets"] = _check_orphans(
        "work_orders->assets", non_null_assets, "asset_id", assets, "asset_id"
    )
    checks["orphans_faults_to_assets"] = _check_orphans(
        "faults->assets", faults, "asset_id", assets, "asset_id"
    )
    resolving_wo_present = faults["resolving_wo_id"].isin(set(work_orders["wo_id"])).all()
    checks["faults_resolving_wo_present"] = {"passed": bool(resolving_wo_present)}

    telemetry_dates_ok = telemetry["ts_utc"].between(
        pd.Timestamp(start_date, tz="UTC"), pd.Timestamp(end_date, tz="UTC") + pd.Timedelta(days=1)
    )
    checks["telemetry_date_bounds"] = {
        "passed": bool(telemetry_dates_ok.all()),
        "violations": int((~telemetry_dates_ok).sum()),
    }

    weather_dates = pd.to_datetime(weather["local_date"]).dt.date
    weather_dates_ok = weather_dates.between(start_date, end_date)
    checks["weather_date_bounds"] = {
        "passed": bool(weather_dates_ok.all()),
        "violations": int((~weather_dates_ok).sum()),
    }

    tariff_dates = pd.to_datetime(tariffs["local_date"]).dt.date
    tariff_dates_ok = tariff_dates.between(start_date, end_date)
    checks["tariff_date_bounds"] = {
        "passed": bool(tariff_dates_ok.all()),
        "violations": int((~tariff_dates_ok).sum()),
    }

    checks["source_energy_balance"] = _check_source_balance(telemetry)

    soc_ok = telemetry["battery_soc_pct"].between(0, 100)
    checks["battery_soc_bounded"] = {"passed": bool(soc_ok.all()), "violations": int((~soc_ok).sum())}

    fuel_present = telemetry["fuel_level_gal"].dropna()
    fuel_ok = (fuel_present >= 0).all() if not fuel_present.empty else True
    checks["fuel_level_bounded"] = {"passed": bool(fuel_ok), "checked": int(len(fuel_present))}

    checks["overall_passed"] = all(c.get("passed", False) for c in checks.values() if isinstance(c, dict))
    checks["reference_date"] = reference_date.isoformat()
    checks["telemetry_window"] = {"start": start_date.isoformat(), "end": end_date.isoformat()}
    return checks
