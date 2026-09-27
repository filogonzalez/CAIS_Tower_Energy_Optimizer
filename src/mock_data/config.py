"""Domain constants for synthetic data generation.

Everything here shapes *how* synthetic records look (regions, site types,
component catalog, fault taxonomy, storm/dust calendars) — it is not
customer/tariff configuration, which lives in ``config.settings``. Region
and municipio names are public-domain Puerto Rico geography used purely as
flavor text for a fictional operator's synthetic sites.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# Seven synthetic regions covering Puerto Rico + offshore islands, weighted
# so Metro receives ~40% of sites (per the Phase 1 data contract).
REGIONS: dict[str, dict] = {
    "Metro": {
        "weight": 0.40,
        "municipios": ["San Juan", "Bayamón", "Carolina", "Guaynabo", "Cataño", "Trujillo Alto"],
    },
    "North": {
        "weight": 0.12,
        "municipios": ["Arecibo", "Manatí", "Vega Baja", "Vega Alta", "Barceloneta"],
    },
    "South": {
        "weight": 0.13,
        "municipios": ["Ponce", "Guayama", "Salinas", "Santa Isabel", "Juana Díaz"],
    },
    "East": {
        "weight": 0.10,
        "municipios": ["Fajardo", "Humacao", "Yabucoa", "Naguabo", "Ceiba"],
    },
    "West": {
        "weight": 0.11,
        "municipios": ["Mayagüez", "Aguadilla", "Cabo Rojo", "San Germán", "Rincón"],
    },
    "Central": {
        "weight": 0.11,
        "municipios": ["Caguas", "Cayey", "Cidra", "Aibonito", "Barranquitas"],
    },
    "Islands": {
        "weight": 0.03,
        "municipios": ["Vieques", "Culebra"],
    },
}

SITE_TYPES: dict[str, dict] = {
    "macro_tower": {"share": 0.55, "capacity_kw": (4.0, 9.0)},
    "rooftop": {"share": 0.20, "capacity_kw": (2.0, 5.0)},
    "small_cell": {"share": 0.15, "capacity_kw": (0.8, 2.0)},
    "colocation": {"share": 0.10, "capacity_kw": (6.0, 14.0)},
}

TERRAIN_TYPES = ["urban", "suburban", "rural", "mountain", "coastal"]
CRITICALITY_TIERS = ["tier1_critical", "tier2_high", "tier3_standard"]

# ~8 assets per site on average (2,400 / 300); not every site has every
# component — e.g. small_cell sites rarely carry a generator, so usable
# backup capacity must not be assumed uniformly.
COMPONENT_CATALOG: dict[str, dict] = {
    "rectifier": {"site_types": ["macro_tower", "rooftop", "small_cell", "colocation"], "p": 1.00},
    "battery_bank": {"site_types": ["macro_tower", "rooftop", "small_cell", "colocation"], "p": 0.95},
    "hvac_unit": {"site_types": ["macro_tower", "colocation"], "p": 0.85},
    "generator": {"site_types": ["macro_tower", "colocation"], "p": 0.55},
    "solar_array": {"site_types": ["macro_tower", "rooftop"], "p": 0.30},
    "fuel_tank": {"site_types": ["macro_tower", "colocation"], "p": 0.50},
    "controller": {"site_types": ["macro_tower", "rooftop", "small_cell", "colocation"], "p": 1.00},
    "antenna_system": {"site_types": ["macro_tower", "rooftop", "small_cell"], "p": 1.00},
}

ENERGY_SOURCES = ["grid", "generator", "battery", "solar"]

RECTIFIER_EFFICIENCY_RANGE = (0.94, 0.97)
COASTAL_WEAR_MULTIPLIER = 1.35  # accelerated corrosion/failure hazard for coastal terrain

# Six evening load-shedding clusters (region, hour window) used to correlate
# grid outages/brownouts with realistic utility load-shedding practice.
LOAD_SHEDDING_CLUSTERS = [
    {"cluster_id": "LS-1", "region": "Metro", "hours": (18, 20)},
    {"cluster_id": "LS-2", "region": "South", "hours": (19, 21)},
    {"cluster_id": "LS-3", "region": "West", "hours": (18, 21)},
    {"cluster_id": "LS-4", "region": "East", "hours": (19, 22)},
    {"cluster_id": "LS-5", "region": "Central", "hours": (18, 20)},
    {"cluster_id": "LS-6", "region": "North", "hours": (20, 22)},
]

# Fault taxonomy: 36 distinct-site faults, restricted to generation/eval use.
FAULT_TYPE_SPECS: list[dict] = [
    {"fault_type": "hvac_degradation", "count": 12, "lead_days": (10, 21), "component": "hvac_unit"},
    {"fault_type": "rectifier_drift", "count": 6, "lead_days": (14, 28), "component": "rectifier"},
    {"fault_type": "battery_fade", "count": 8, "lead_days": (7, 18), "component": "battery_bank"},
    {"fault_type": "generator_start_failure", "count": 3, "lead_days": (3, 9), "component": "generator"},
    {"fault_type": "fuel_loss_without_runtime", "count": 3, "lead_days": (2, 7), "component": "fuel_tank"},
    {"fault_type": "ghost_load", "count": 4, "lead_days": (5, 12), "component": "controller"},
]
TOTAL_FAULT_SITES = sum(spec["count"] for spec in FAULT_TYPE_SPECS)


@dataclass(frozen=True)
class StormWindow:
    name: str
    start_offset_days: int  # offset from telemetry window start
    duration_days: int
    affected_regions: tuple[str, ...]


# Synthetic three-day "Este/Sur" storm placed inside the telemetry window
# (never at day 0, so pre-storm baseline behavior is observable).
SYNTHETIC_STORM = StormWindow(
    name="Storm Elena (synthetic)",
    start_offset_days=int(os.getenv("TEO_STORM_START_OFFSET_DAYS", "95")),
    duration_days=int(os.getenv("TEO_STORM_DURATION_DAYS", "3")),
    affected_regions=("East", "South", "Islands"),
)

# Saharan-dust week: reduces solar output and elevates HVAC/particulate load.
DUST_WEEK_OFFSET_DAYS = int(os.getenv("TEO_DUST_START_OFFSET_DAYS", "40"))
DUST_WEEK_DURATION_DAYS = int(os.getenv("TEO_DUST_DURATION_DAYS", "7"))

WORK_ORDER_TYPES = ["preventive", "corrective", "emergency"]
WORK_ORDER_STATUSES = ["completed", "completed", "completed", "cancelled"]  # weighted toward completed
