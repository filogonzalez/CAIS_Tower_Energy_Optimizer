"""Explicit Spark schemas for every Bronze-bound synthetic dataset.

Ground-truth fault labels (``injected_faults``) are intentionally declared
here for the generation/evaluation path only — non-negotiable contract #7
excludes them from any of the seven Bronze streaming declarations consumed
by the pipeline, agent, Genie, app, or vector index.
"""

from __future__ import annotations

from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)

SITES_SCHEMA = StructType(
    [
        StructField("site_id", StringType(), False),
        StructField("site_name", StringType(), False),
        StructField("region", StringType(), False),
        StructField("municipio", StringType(), False),
        StructField("site_type", StringType(), False),
        StructField("capacity_kw", DoubleType(), False),
        StructField("longitude", DoubleType(), False),
        StructField("latitude", DoubleType(), False),
        StructField("terrain", StringType(), False),
        StructField("criticality_tier", StringType(), False),
        StructField("truck_roll_distance_km", DoubleType(), False),
        StructField("truck_roll_minutes", IntegerType(), False),
        StructField("commissioned_date", StringType(), False),
        StructField("coord_shape_provenance", StringType(), False),
        StructField("coord_tolerance_deg", DoubleType(), False),
    ]
)

EQUIPMENT_ASSETS_SCHEMA = StructType(
    [
        StructField("asset_id", StringType(), False),
        StructField("site_id", StringType(), False),
        StructField("component", StringType(), False),
        StructField("manufacturer", StringType(), False),
        StructField("model_number", StringType(), False),
        StructField("rated_capacity", DoubleType(), False),
        StructField("rated_capacity_unit", StringType(), False),
        StructField("installation_date", StringType(), False),
        StructField("last_pm_date", StringType(), True),
        StructField("warranty_expiration_date", StringType(), False),
    ]
)

ENERGY_TELEMETRY_SCHEMA = StructType(
    [
        StructField("site_id", StringType(), False),
        StructField("ts_utc", TimestampType(), False),
        StructField("interval_hours", DoubleType(), False),
        StructField("grid_available", BooleanType(), False),
        StructField("energy_source_active", StringType(), False),
        StructField("grid_kwh", DoubleType(), False),
        StructField("generator_kwh", DoubleType(), False),
        StructField("battery_discharge_kwh", DoubleType(), False),
        StructField("battery_charge_kwh", DoubleType(), False),
        StructField("solar_kwh", DoubleType(), False),
        StructField("served_load_kwh", DoubleType(), False),
        StructField("it_load_kw", DoubleType(), False),
        StructField("hvac_load_kw", DoubleType(), False),
        StructField("rectifier_efficiency_pct", DoubleType(), False),
        StructField("battery_soc_pct", DoubleType(), False),
        StructField("ambient_temp_c", DoubleType(), False),
        StructField("fuel_level_gal", DoubleType(), True),
        StructField("fuel_consumed_gal", DoubleType(), False),
        StructField("generator_runtime_hours", DoubleType(), False),
        StructField("network_traffic_gb", DoubleType(), False),
        StructField("site_available", BooleanType(), False),
    ]
)

GRID_OUTAGE_EVENTS_SCHEMA = StructType(
    [
        StructField("outage_id", StringType(), False),
        StructField("site_id", StringType(), False),
        StructField("feeder_id", StringType(), False),
        StructField("municipio", StringType(), False),
        StructField("start_ts_utc", TimestampType(), False),
        StructField("end_ts_utc", TimestampType(), True),
        StructField("cause", StringType(), False),
        StructField("is_storm_related", BooleanType(), False),
        StructField("load_shedding_cluster", StringType(), True),
    ]
)

WEATHER_DAILY_SCHEMA = StructType(
    [
        StructField("municipio", StringType(), False),
        StructField("local_date", StringType(), False),
        StructField("high_temp_c", DoubleType(), False),
        StructField("low_temp_c", DoubleType(), False),
        StructField("humidity_pct", DoubleType(), False),
        StructField("rainfall_mm", DoubleType(), False),
        StructField("wind_kph", DoubleType(), False),
        StructField("is_storm_day", BooleanType(), False),
        StructField("is_dust_day", BooleanType(), False),
        StructField("storm_name", StringType(), True),
    ]
)

WORK_ORDER_HISTORY_SCHEMA = StructType(
    [
        StructField("wo_id", StringType(), False),
        StructField("site_id", StringType(), False),
        StructField("asset_id", StringType(), True),
        StructField("component", StringType(), True),
        StructField("wo_type", StringType(), False),
        StructField("status", StringType(), False),
        StructField("opened_ts_utc", TimestampType(), False),
        StructField("closed_ts_utc", TimestampType(), True),
        StructField("downtime_minutes", DoubleType(), True),
        StructField("cost_usd", DoubleType(), False),
        StructField("parts_used", ArrayType(StringType()), True),
        StructField("technician_hash", StringType(), False),
        StructField("notes_raw_text", StringType(), True),
        StructField("notes_language", StringType(), True),
    ]
)

ENERGY_TARIFFS_SCHEMA = StructType(
    [
        StructField("local_date", StringType(), False),
        StructField("grid_price_usd_per_kwh", DoubleType(), False),
        StructField("diesel_price_usd_per_gal", DoubleType(), False),
        StructField("diesel_emissions_kg_co2_per_gal", DoubleType(), False),
        StructField("diesel_gal_per_kwh", DoubleType(), False),
    ]
)

# Restricted: ground truth only. Excluded from Bronze/serving/agent/Genie/
# vector-index inputs; consumed solely by inject_faults.py, evaluation, and
# the Phase 1/3 validation reports.
INJECTED_FAULTS_SCHEMA = StructType(
    [
        StructField("fault_id", StringType(), False),
        StructField("site_id", StringType(), False),
        StructField("asset_id", StringType(), False),
        StructField("component", StringType(), False),
        StructField("fault_type", StringType(), False),
        StructField("symptom_onset_ts_utc", TimestampType(), False),
        StructField("detection_deadline_ts_utc", TimestampType(), False),
        StructField("resolution_ts_utc", TimestampType(), False),
        StructField("resolving_wo_id", StringType(), False),
    ]
)

ALL_BRONZE_SCHEMAS = {
    "sites": SITES_SCHEMA,
    "equipment_assets": EQUIPMENT_ASSETS_SCHEMA,
    "energy_telemetry": ENERGY_TELEMETRY_SCHEMA,
    "grid_outage_events": GRID_OUTAGE_EVENTS_SCHEMA,
    "weather_daily": WEATHER_DAILY_SCHEMA,
    "work_order_history": WORK_ORDER_HISTORY_SCHEMA,
    "energy_tariffs": ENERGY_TARIFFS_SCHEMA,
}
