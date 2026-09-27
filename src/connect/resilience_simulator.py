"""Deterministic outage resilience and retrofit ROI simulator."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass

from config.settings import get_settings
from pyspark.sql import DataFrame
from pyspark.sql import functions as F
from validation.spark import get_spark


@dataclass(frozen=True)
class ScenarioAssumptions:
    scenario_version: str = "v1"
    outage_hours: float = 24.0
    fuel_delivery_lag_hours: float = 12.0
    generator_fuel_capacity_gal: float = 250.0
    synthetic_population_per_tier1_site: int = 2_500
    coverage_overlap_factor: float = 0.65
    hvac_capex_usd: float = 8_000.0
    rectifier_capex_usd: float = 5_500.0
    battery_capex_usd: float = 18_000.0
    solar_capex_usd: float = 32_000.0
    annual_maintenance_pct: float = 0.02


def calculate_site_scenario(
    average_load_kw: float,
    battery_usable_kwh: float,
    generator_capacity_kw: float,
    fuel_available_gal: float,
    diesel_gal_per_kwh: float,
    outage_hours: float,
    fuel_delivery_lag_hours: float,
) -> dict:
    load = max(0.0, average_load_kw)
    if load == 0:
        return {"time_to_dark_hours": outage_hours, "fuel_truck_required": False, "unserved_kwh": 0.0}
    battery_hours = max(0.0, battery_usable_kwh) / load
    generator_kw = min(max(0.0, generator_capacity_kw), load)
    generator_hours = 0.0
    if generator_kw > 0 and diesel_gal_per_kwh > 0:
        generator_hours = max(0.0, fuel_available_gal) / (generator_kw * diesel_gal_per_kwh)
    time_to_dark = min(outage_hours, battery_hours + generator_hours)
    fuel_needed_before_delivery = (
        max(0.0, fuel_delivery_lag_hours - battery_hours) * generator_kw * diesel_gal_per_kwh
    )
    return {
        "time_to_dark_hours": max(0.0, time_to_dark),
        "fuel_truck_required": fuel_needed_before_delivery > max(0.0, fuel_available_gal),
        "unserved_kwh": max(0.0, outage_hours - time_to_dark) * load,
    }


def calculate_roi(capex_usd: float, annual_savings_usd: float, annual_maintenance_pct: float) -> dict:
    net = annual_savings_usd - capex_usd * max(0.0, annual_maintenance_pct)
    return {
        "net_annual_savings_usd": net,
        "payback_years": None if net <= 0 else capex_usd / net,
        "has_positive_savings": net > 0,
    }


def build_scenario_results(site_inputs: DataFrame, assumptions: ScenarioAssumptions) -> DataFrame:
    battery_hours = F.greatest(F.lit(0.0), F.col("battery_usable_kwh")) / F.greatest(
        F.col("average_load_kw"), F.lit(0.001)
    )
    generator_kw = F.least(
        F.greatest(F.col("generator_capacity_kw"), F.lit(0.0)),
        F.greatest(F.col("average_load_kw"), F.lit(0.0)),
    )
    generator_hours = F.when(
        generator_kw > 0,
        F.greatest(F.col("fuel_available_gal"), F.lit(0.0)) / (generator_kw * F.lit(0.088)),
    ).otherwise(0.0)
    time_to_dark = F.least(F.lit(assumptions.outage_hours), battery_hours + generator_hours)
    return (
        site_inputs.withColumn("scenario_version", F.lit(assumptions.scenario_version))
        .withColumn("outage_hours", F.lit(assumptions.outage_hours))
        .withColumn("fuel_delivery_lag_hours", F.lit(assumptions.fuel_delivery_lag_hours))
        .withColumn("time_to_dark_hours", F.greatest(F.lit(0.0), time_to_dark))
        .withColumn(
            "unserved_kwh",
            F.greatest(F.lit(0.0), F.lit(assumptions.outage_hours) - time_to_dark)
            * F.greatest(F.col("average_load_kw"), F.lit(0.0)),
        )
        .withColumn(
            "synthetic_population_at_risk",
            F.when(
                F.col("criticality_tier") == "tier1_critical",
                F.lit(assumptions.synthetic_population_per_tier1_site * assumptions.coverage_overlap_factor),
            ).otherwise(0),
        )
        .withColumn(
            "assumptions_json",
            F.to_json(F.struct(*[F.lit(value).alias(key) for key, value in asdict(assumptions).items()])),
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--outage-hours", type=float, default=24)
    parser.add_argument("--fuel-delivery-lag-hours", type=float, default=12)
    args = parser.parse_args()
    settings = get_settings()
    spark = get_spark()
    assumptions = ScenarioAssumptions(
        outage_hours=args.outage_hours,
        fuel_delivery_lag_hours=args.fuel_delivery_lag_hours,
        hvac_capex_usd=settings.hvac_capex_usd,
        rectifier_capex_usd=settings.rectifier_capex_usd,
        battery_capex_usd=settings.battery_capex_usd,
        solar_capex_usd=settings.solar_capex_usd,
        annual_maintenance_pct=settings.retrofit_annual_maintenance_pct,
    )
    inputs = spark.table(settings.table_analytics("resilience_simulator_inputs"))  # type: ignore[name-defined]
    build_scenario_results(inputs, assumptions).write.mode("overwrite").option(
        "overwriteSchema", "true"
    ).saveAsTable(settings.table_analytics("outage_scenario_results"))
    roi = spark.table(settings.table_analytics("retrofit_inputs"))  # type: ignore[name-defined]
    roi.withColumn("scenario_version", F.lit(assumptions.scenario_version)).withColumn(
        "net_annual_savings_usd",
        F.col("annual_source_savings_usd") - F.col("capex_usd") * F.lit(assumptions.annual_maintenance_pct),
    ).withColumn(
        "payback_years",
        F.when(F.col("net_annual_savings_usd") > 0, F.col("capex_usd") / F.col("net_annual_savings_usd")),
    ).write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        settings.table_analytics("retrofit_roi")
    )


if __name__ == "__main__":
    main()
