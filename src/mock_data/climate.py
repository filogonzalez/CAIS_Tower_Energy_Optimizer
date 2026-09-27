"""Shared deterministic climate model.

Both ``energy_telemetry`` (hourly ambient temperature) and ``weather_daily``
(daily high/low/humidity) derive from these functions so the two tables stay
mutually consistent without requiring a join at generation time.
"""

from __future__ import annotations

import math

REGION_BASE_TEMP_C = {
    "Metro": 27.5,
    "North": 26.5,
    "South": 28.5,
    "East": 26.0,
    "West": 27.0,
    "Central": 24.0,
    "Islands": 27.0,
}

REGION_HUMIDITY_BASE_PCT = {
    "Metro": 78.0,
    "North": 80.0,
    "South": 70.0,
    "East": 82.0,
    "West": 75.0,
    "Central": 76.0,
    "Islands": 80.0,
}


def seasonal_offset_c(day_of_year: int) -> float:
    """Peaks ~late July (day ~210), trough ~mid-January (day ~20)."""
    return 2.2 * math.sin(2 * math.pi * (day_of_year - 105) / 365.0)


def diurnal_offset_c(hour: int) -> float:
    """Peaks mid-afternoon (~15:00 local), trough pre-dawn (~05:00 local)."""
    return 4.0 * math.sin(2 * math.pi * (hour - 9) / 24.0)


def hourly_ambient_temp_c(
    region: str,
    day_of_year: int,
    hour: int,
    *,
    is_storm: bool = False,
    is_dust: bool = False,
    noise_c: float = 0.0,
) -> float:
    base = REGION_BASE_TEMP_C.get(region, 27.0)
    storm_adj = -1.5 if is_storm else 0.0
    dust_adj = 0.8 if is_dust else 0.0
    return base + seasonal_offset_c(day_of_year) + diurnal_offset_c(hour) + storm_adj + dust_adj + noise_c


def daily_high_low_c(
    region: str, day_of_year: int, *, is_storm: bool = False, is_dust: bool = False
) -> tuple[float, float]:
    values = [
        hourly_ambient_temp_c(region, day_of_year, h, is_storm=is_storm, is_dust=is_dust) for h in range(24)
    ]
    return max(values), min(values)


def humidity_pct(region: str, *, is_storm: bool = False, noise_pct: float = 0.0) -> float:
    base = REGION_HUMIDITY_BASE_PCT.get(region, 78.0)
    bump = 12.0 if is_storm else 0.0
    return max(40.0, min(99.0, base + bump + noise_pct))


def solar_derate(*, is_dust: bool = False, is_storm: bool = False) -> float:
    """Fraction of nameplate solar output available given atmospheric conditions."""
    derate = 1.0
    if is_dust:
        derate *= 0.65
    if is_storm:
        derate *= 0.20
    return derate
