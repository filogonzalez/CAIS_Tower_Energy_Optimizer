"""Hourly ``energy_telemetry`` generator: 300 sites x telemetry_days x 24.

Physical reconciliation invariant enforced on every row (non-negotiable
contract: "reconcile source energy, fuel/runtime, battery charge/discharge
and served load; avoid counting battery discharge as newly purchased
electricity a second time")::

    grid_kwh + generator_kwh + battery_discharge_kwh + solar_kwh
        == served_load_kwh + battery_charge_kwh

``solar_kwh`` is the *utilized* solar (delivered to load or battery this
hour); curtailed solar is not tracked as a column and is intentionally
dropped from the balance rather than double-counted.

Puerto Rico observes no daylight saving time (fixed AST, UTC-4 year-round),
so local hour-of-day == ``hour_index % 24`` and local day offset ==
``hour_index // 24`` exactly for the whole generated window — no DST edge
cases to handle here.

The 36 injected-fault symptoms (see ``inject_faults.py``) are the *only*
place fault ground truth leaks into telemetry: a deterministic severity
ramp from 0 (at ``symptom_onset_ts_utc``) to 1 (at ``detection_deadline_ts_utc``)
that holds at 1 until ``resolution_ts_utc``, then drops back to 0. Only the
*symptom* (degraded efficiency, extra load, a failed generator start, a fuel
leak) is written to this table — never the fault label itself.
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd
from common.timeutils import pr_midnight_utc

from mock_data import climate
from mock_data.config import COASTAL_WEAR_MULTIPLIER, REGIONS, SYNTHETIC_STORM
from mock_data.entities import _dust_window_dates, _storm_window_dates, telemetry_window
from mock_data.random_streams import stream

EPS = 1e-6

IT_LOAD_FRACTION = 0.30
HVAC_MAX_FRACTION = 0.35
GHOST_LOAD_FRACTION = 0.25

BATTERY_VOLTAGE = 48.0  # synthetic nominal pack voltage used to derive kWh from amp-hours
CHARGE_RATE_FRAC = 0.25
DISCHARGE_RATE_FRAC = 0.35
FLOAT_CHARGE_RATE_FRAC = 0.10
RESERVE_FLOOR_PCT = 20.0
FADE_FLOOR_BUMP_PCT = 20.0
FADE_CAPACITY_DERATE = 0.5

FUEL_REFILL_THRESHOLD_FRAC = 0.15
FUEL_LEAK_RATE_FRAC_PER_HOUR = 0.004  # of tank size, at full fault severity

FAULT_SEVERITY_FIELDS = {
    "hvac_degradation": "hvac_load_multiplier",
    "rectifier_drift": "rectifier_efficiency_drop_pct",
    "battery_fade": "battery_fade",
    "generator_start_failure": "generator_start_failure",
    "fuel_loss_without_runtime": "fuel_leak",
    "ghost_load": "ghost_load_extra_kw",
}


def _severity_at(ts, onset_ts, deadline_ts, resolution_ts) -> float:
    """0 before onset; linear ramp 0->1 between onset and deadline; holds at
    1 until resolution; 0 after resolution (component considered repaired).
    """
    if ts < onset_ts or ts >= resolution_ts:
        return 0.0
    if ts >= deadline_ts:
        return 1.0
    total = (deadline_ts - onset_ts).total_seconds()
    if total <= 0:
        return 1.0
    return max(0.0, min(1.0, (ts - onset_ts).total_seconds() / total))


def _solar_shape(hour: int) -> float:
    if hour < 6 or hour > 18:
        return 0.0
    return max(0.0, float(np.sin(np.pi * (hour - 6) / 12.0)))


def _traffic_shape(hour: int) -> float:
    """Baseline diurnal traffic shape, 0..1, peaking in the evening (18-22)."""
    daytime = 0.35 + 0.35 * max(0.0, float(np.sin(np.pi * (hour - 8) / 14.0)))
    evening_bump = 0.35 * max(0.0, 1.0 - abs(hour - 20) / 3.0)
    return min(1.0, daytime + evening_bump)


def _assets_by_site(assets: pd.DataFrame) -> dict[str, dict[str, pd.Series]]:
    out: dict[str, dict[str, pd.Series]] = {}
    for site_id, grp in assets.groupby("site_id"):
        out[site_id] = {row.component: row for row in grp.itertuples()}
    return out


def _outage_mask(outages_for_site: pd.DataFrame | None, window_start_utc, total_hours: int) -> np.ndarray:
    mask = np.zeros(total_hours, dtype=bool)
    if outages_for_site is None or outages_for_site.empty:
        return mask
    for row in outages_for_site.itertuples():
        start_idx = int((row.start_ts_utc - window_start_utc).total_seconds() // 3600)
        end_ts = row.end_ts_utc if pd.notna(row.end_ts_utc) else row.start_ts_utc
        end_idx = int((end_ts - window_start_utc).total_seconds() // 3600)
        start_idx = max(0, start_idx)
        end_idx = min(total_hours - 1, end_idx)
        if end_idx >= start_idx:
            mask[start_idx : end_idx + 1] = True
    return mask


def _region_hourly_temp(
    region: str, doy: np.ndarray, is_storm_day: np.ndarray, is_dust_day: np.ndarray, total_hours: int
) -> np.ndarray:
    temp = np.empty(total_hours)
    telemetry_days = len(doy)
    for d in range(telemetry_days):
        for h in range(24):
            temp[d * 24 + h] = climate.hourly_ambient_temp_c(
                region, int(doy[d]), h, is_storm=bool(is_storm_day[d]), is_dust=bool(is_dust_day[d])
            )
    return temp


def generate_energy_telemetry(
    seed: int,
    sites: pd.DataFrame,
    assets: pd.DataFrame,
    outage_events: pd.DataFrame,
    faults: pd.DataFrame,
    reference_date: date,
    telemetry_days: int,
    settings,
) -> pd.DataFrame:
    start_date, _end_date = telemetry_window(reference_date, telemetry_days)
    total_hours = telemetry_days * 24
    window_start_utc = pr_midnight_utc(start_date)

    storm_start, storm_end = _storm_window_dates(start_date)
    dust_start, dust_end = _dust_window_dates(start_date)
    day_dates = [start_date + timedelta(days=d) for d in range(telemetry_days)]
    is_storm_day = np.array([storm_start <= d <= storm_end for d in day_dates])
    is_dust_day = np.array([dust_start <= d <= dust_end for d in day_dates])
    doy = np.array([d.timetuple().tm_yday for d in day_dates])

    solar_shape = np.array([_solar_shape(h) for h in range(24)])
    traffic_shape = np.array([_traffic_shape(h) for h in range(24)])
    solar_derate_by_day = np.array(
        [
            climate.solar_derate(is_dust=bool(is_dust_day[d]), is_storm=bool(is_storm_day[d]))
            for d in range(telemetry_days)
        ]
    )

    region_temp_cache: dict[str, np.ndarray] = {}
    for region_name in REGIONS:
        region_storm_days = (
            is_storm_day
            if region_name in SYNTHETIC_STORM.affected_regions
            else np.zeros(telemetry_days, dtype=bool)
        )
        region_temp_cache[region_name] = _region_hourly_temp(
            region_name, doy, region_storm_days, is_dust_day, total_hours
        )

    assets_by_site = _assets_by_site(assets)
    faults_by_site = {row.site_id: row for row in faults.itertuples()} if "site_id" in faults.columns else {}
    outages_by_site = (
        {sid: grp for sid, grp in outage_events.groupby("site_id")}
        if "site_id" in outage_events.columns
        else {}
    )

    n = len(sites) * total_hours
    col_site_id = np.empty(n, dtype=object)
    col_ts = np.empty(n, dtype=object)
    col_interval = np.full(n, 1.0)
    col_grid_available = np.empty(n, dtype=bool)
    col_source_active = np.empty(n, dtype=object)
    col_grid = np.zeros(n)
    col_generator = np.zeros(n)
    col_batt_discharge = np.zeros(n)
    col_batt_charge = np.zeros(n)
    col_solar = np.zeros(n)
    col_served = np.zeros(n)
    col_it_load = np.zeros(n)
    col_hvac_load = np.zeros(n)
    col_rect_eff = np.zeros(n)
    col_soc = np.zeros(n)
    col_ambient = np.zeros(n)
    col_fuel_level = np.full(n, np.nan)
    col_fuel_consumed = np.zeros(n)
    col_gen_runtime = np.zeros(n)
    col_traffic = np.zeros(n)
    col_site_available = np.empty(n, dtype=bool)

    offset = 0
    for site in sites.itertuples():
        site_id = site.site_id
        rng = stream(seed, "telemetry", site_id)
        site_assets = assets_by_site.get(site_id, {})
        has_battery = "battery_bank" in site_assets
        has_generator = "generator" in site_assets
        has_solar = "solar_array" in site_assets
        has_hvac = "hvac_unit" in site_assets
        has_fuel = "fuel_tank" in site_assets

        capacity_kwh = (
            float(site_assets["battery_bank"].rated_capacity) * BATTERY_VOLTAGE / 1000.0
            if has_battery
            else 0.0
        )
        solar_nameplate_kw = float(site_assets["solar_array"].rated_capacity) if has_solar else 0.0
        tank_size_gal = float(site_assets["fuel_tank"].rated_capacity) if has_fuel else None

        grid_mask = ~_outage_mask(outages_by_site.get(site_id), window_start_utc, total_hours)
        region_temp = region_temp_cache[site.region]
        coastal_wear = COASTAL_WEAR_MULTIPLIER if site.terrain == "coastal" else 1.0

        rect_base = float(rng.uniform(94.0, 97.0))
        it_noise = rng.normal(0, 0.02, size=total_hours)
        rect_noise = rng.normal(0, 0.15, size=total_hours)

        fault = faults_by_site.get(site_id)
        fault_type = fault.fault_type if fault is not None else None
        onset_ts = fault.symptom_onset_ts_utc if fault is not None else None
        deadline_ts = fault.detection_deadline_ts_utc if fault is not None else None
        resolution_ts = fault.resolution_ts_utc if fault is not None else None

        soc = float(rng.uniform(60.0, 90.0))
        fuel_level = (
            float(rng.uniform(0.7, 1.0)) * tank_size_gal if has_fuel and tank_size_gal is not None else None
        )

        for h in range(total_hours):
            idx = offset + h
            ts = window_start_utc + timedelta(hours=h)
            day_idx = h // 24
            hour_of_day = h % 24

            severity = _severity_at(ts, onset_ts, deadline_ts, resolution_ts) if fault is not None else 0.0

            ambient = region_temp[h]
            wear_drift = -0.5 * coastal_wear * (h / total_hours)
            rect_eff = rect_base + wear_drift + float(rect_noise[h])
            if fault_type == "rectifier_drift":
                rect_eff -= 6.0 * severity
            rect_eff = float(np.clip(rect_eff, 80.0, 99.0))

            traffic_gb = max(
                0.0, site.capacity_kw * 0.8 * traffic_shape[hour_of_day] * (1 + float(rng.normal(0, 0.05)))
            )
            it_load = site.capacity_kw * IT_LOAD_FRACTION * (0.75 + 0.5 * traffic_shape[hour_of_day]) + float(
                it_noise[h]
            )
            it_load = max(0.0, it_load)
            if fault_type == "ghost_load":
                it_load += severity * site.capacity_kw * GHOST_LOAD_FRACTION

            if has_hvac:
                temp_factor = float(np.clip((ambient - 22.0) / 10.0, 0.0, 1.4))
                hvac_load = site.capacity_kw * HVAC_MAX_FRACTION * temp_factor
                if fault_type == "hvac_degradation":
                    hvac_load *= 1.0 + 0.6 * severity
            else:
                hvac_load = 0.0
            load = it_load + hvac_load

            solar_gen = (
                solar_nameplate_kw * solar_shape[hour_of_day] * solar_derate_by_day[day_idx]
                if has_solar
                else 0.0
            )
            solar_to_load = min(solar_gen, load)
            remaining = load - solar_to_load

            floor_pct = RESERVE_FLOOR_PCT
            eff_capacity_kwh = capacity_kwh
            if fault_type == "battery_fade" and has_battery:
                floor_pct += FADE_FLOOR_BUMP_PCT * severity
                eff_capacity_kwh = capacity_kwh * (1.0 - FADE_CAPACITY_DERATE * severity)

            max_charge = CHARGE_RATE_FRAC * eff_capacity_kwh if has_battery else 0.0
            max_discharge = DISCHARGE_RATE_FRAC * eff_capacity_kwh if has_battery else 0.0

            grid_available = bool(grid_mask[h])
            generator_start_ok = has_generator and not (
                fault_type == "generator_start_failure" and severity > 0
            )
            fuel_ok = True
            if has_fuel and fuel_level is not None and fuel_level <= 1.0:
                fuel_ok = False
            generator_available = generator_start_ok and fuel_ok

            batt_discharge = 0.0
            batt_charge = 0.0
            grid_kwh = 0.0
            generator_kwh = 0.0
            solar_utilized = solar_to_load
            served = load

            if grid_available:
                headroom = max(0.0, (100.0 - soc) / 100.0 * eff_capacity_kwh) if has_battery else 0.0
                charge_cap = min(max_charge, headroom)
                solar_excess = max(0.0, solar_gen - solar_to_load)
                charge_from_solar = min(solar_excess, charge_cap)
                remaining_room = charge_cap - charge_from_solar
                float_charge = (
                    min(FLOAT_CHARGE_RATE_FRAC * eff_capacity_kwh, remaining_room) if has_battery else 0.0
                )
                batt_charge = charge_from_solar + float_charge
                solar_utilized = solar_to_load + charge_from_solar
                grid_kwh = remaining + float_charge
                served = load
            else:
                if remaining > EPS:
                    avail_above_floor = (
                        max(0.0, (soc - floor_pct) / 100.0 * eff_capacity_kwh) if has_battery else 0.0
                    )
                    discharge_cap = min(max_discharge, avail_above_floor)
                    batt_discharge = min(remaining, discharge_cap)
                    remaining -= batt_discharge
                    if remaining > EPS and generator_available:
                        generator_kwh = remaining
                        remaining = 0.0
                    served = load - remaining
                else:
                    solar_excess = max(0.0, solar_gen - solar_to_load)
                    headroom = max(0.0, (100.0 - soc) / 100.0 * eff_capacity_kwh) if has_battery else 0.0
                    charge_from_solar = min(solar_excess, max_charge, headroom)
                    batt_charge = charge_from_solar
                    solar_utilized = solar_to_load + charge_from_solar
                    served = load

            fuel_consumed = generator_kwh * settings.diesel_gal_per_kwh
            if has_fuel:
                assert tank_size_gal is not None and fuel_level is not None
                leak = (
                    FUEL_LEAK_RATE_FRAC_PER_HOUR * severity * tank_size_gal
                    if fault_type == "fuel_loss_without_runtime"
                    else 0.0
                )
                fuel_level = max(0.0, fuel_level - fuel_consumed - leak)
                if hour_of_day == 0 and fuel_level < FUEL_REFILL_THRESHOLD_FRAC * tank_size_gal:
                    fuel_level = float(rng.uniform(0.85, 1.0)) * tank_size_gal

            if has_battery:
                soc_kwh_change = batt_charge - batt_discharge
                if eff_capacity_kwh > 0:
                    soc = float(np.clip(soc + soc_kwh_change / eff_capacity_kwh * 100.0, 0.0, 100.0))

            if grid_kwh > EPS:
                source_active = "grid"
            elif generator_kwh > EPS:
                source_active = "generator"
            elif batt_discharge > EPS:
                source_active = "battery"
            elif solar_utilized > EPS:
                source_active = "solar"
            else:
                source_active = "none"

            col_site_id[idx] = site_id
            col_ts[idx] = ts
            col_grid_available[idx] = grid_available
            col_source_active[idx] = source_active
            col_grid[idx] = grid_kwh
            col_generator[idx] = generator_kwh
            col_batt_discharge[idx] = batt_discharge
            col_batt_charge[idx] = batt_charge
            col_solar[idx] = solar_utilized
            col_served[idx] = served
            col_it_load[idx] = it_load
            col_hvac_load[idx] = hvac_load
            col_rect_eff[idx] = rect_eff
            col_soc[idx] = soc if has_battery else 0.0
            col_ambient[idx] = ambient
            col_fuel_level[idx] = fuel_level if has_fuel else np.nan
            col_fuel_consumed[idx] = fuel_consumed
            col_gen_runtime[idx] = 1.0 if generator_kwh > EPS else 0.0
            col_traffic[idx] = traffic_gb
            col_site_available[idx] = served >= load - 1e-3

        offset += total_hours

    return pd.DataFrame(
        {
            "site_id": col_site_id,
            "ts_utc": pd.to_datetime(col_ts, utc=True),
            "interval_hours": col_interval,
            "grid_available": col_grid_available,
            "energy_source_active": col_source_active,
            "grid_kwh": np.round(col_grid, 4),
            "generator_kwh": np.round(col_generator, 4),
            "battery_discharge_kwh": np.round(col_batt_discharge, 4),
            "battery_charge_kwh": np.round(col_batt_charge, 4),
            "solar_kwh": np.round(col_solar, 4),
            "served_load_kwh": np.round(col_served, 4),
            "it_load_kw": np.round(col_it_load, 4),
            "hvac_load_kw": np.round(col_hvac_load, 4),
            "rectifier_efficiency_pct": np.round(col_rect_eff, 3),
            "battery_soc_pct": np.round(col_soc, 2),
            "ambient_temp_c": np.round(col_ambient, 2),
            "fuel_level_gal": np.round(col_fuel_level, 2),
            "fuel_consumed_gal": np.round(col_fuel_consumed, 4),
            "generator_runtime_hours": col_gen_runtime,
            "network_traffic_gb": np.round(col_traffic, 4),
            "site_available": col_site_available,
        }
    )
