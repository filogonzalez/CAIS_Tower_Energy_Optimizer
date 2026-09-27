# ruff: noqa: F821
"""Model-dependent Gold and operational projection interfaces."""

from pyspark import pipelines as dp
from pyspark.sql import DataFrame
from pyspark.sql import functions as F


def _conf(name: str, default: str | None = None) -> str:
    value = spark.conf.get(name, default)  # type: ignore[name-defined]
    if value is None:
        raise ValueError(f"Missing pipeline configuration: {name}")
    return value


CATALOG = _conf("teo.catalog")
CURATED = _conf("teo.schema_curated", "curated")
ANALYTICS = _conf("teo.schema_analytics", "analytics")
ML_SCHEMA = _conf("teo.schema_ml", "ml")

SITES = f"{CATALOG}.{CURATED}.silver_sites"
TELEMETRY = f"{CATALOG}.{CURATED}.silver_energy_telemetry"
POWER_EVENTS = f"{CATALOG}.{CURATED}.silver_power_events"
BENCHMARK = f"{CATALOG}.{ANALYTICS}.gold_site_benchmark"
PRIORITY = f"{CATALOG}.{ANALYTICS}.gold_site_priority"
SCORES = f"{CATALOG}.{ML_SCHEMA}.asset_health_scores"


@dp.materialized_view(name=PRIORITY, comment="Model-dependent priority with explicit score state")
def gold_site_priority() -> DataFrame:
    benchmark = spark.read.table(BENCHMARK)  # type: ignore[name-defined]
    resilience = (
        spark.read.table(POWER_EVENTS)
        .groupBy("site_id")
        .agg(  # type: ignore[name-defined]
            (1 - F.sum("downtime_minutes") / F.greatest(F.sum("duration_minutes"), F.lit(1.0))).alias(
                "resilience_score"
            )
        )
    )
    site_scores = (
        spark.read.table(SCORES)
        .groupBy("site_id")
        .agg(  # type: ignore[name-defined]
            F.max("failure_risk_14d").alias("failure_risk_14d"),
            F.max("anomaly_score").alias("anomaly_score"),
        )
    )
    return (
        benchmark.join(resilience, "site_id", "left")
        .join(site_scores, "site_id", "left")
        .withColumn(
            "score_status", F.when(F.col("failure_risk_14d").isNull(), "unscored").otherwise("scored")
        )
        .withColumn(
            "priority_score",
            F.when(
                F.col("failure_risk_14d").isNotNull(),
                100
                * (
                    0.35 * F.least(F.greatest("failure_risk_14d", F.lit(0.0)), F.lit(1.0))
                    + 0.25 * F.least(F.greatest("anomaly_score", F.lit(0.0)), F.lit(1.0))
                    + 0.20 * (1 - F.least(F.greatest("resilience_score", F.lit(0.0)), F.lit(1.0)))
                    + 0.10 * F.least(F.col("total_energy_cost_usd") / F.lit(10_000.0), F.lit(1.0))
                    + 0.10
                    * F.when(F.col("criticality_tier") == "tier1_critical", 1.0)
                    .when(F.col("criticality_tier") == "tier2_high", 0.6)
                    .otherwise(0.2)
                ),
            ),
        )
    )


@dp.materialized_view(
    name=f"{CATALOG}.{ANALYTICS}.site_status_projection",
    comment="Current Lakebase site projection; operational work orders remain in Lakebase",
)
def site_status_projection() -> DataFrame:
    priority = spark.read.table(PRIORITY)  # type: ignore[name-defined]
    sites = spark.read.table(SITES)  # type: ignore[name-defined]
    latest = (
        spark.read.table(TELEMETRY)
        .groupBy("site_id")
        .agg(  # type: ignore[name-defined]
            F.max_by("energy_source_active", "ts_utc").alias("current_source"),
            F.max("ts_utc").alias("as_of_utc"),
        )
    )
    return (
        priority.join(sites, ["site_id", "region", "site_type"])
        .join(latest, "site_id")
        .select(
            "site_id",
            "region",
            "municipio",
            "site_type",
            "priority_score",
            "score_status",
            "anomaly_score",
            "failure_risk_14d",
            "resilience_score",
            "current_source",
            "as_of_utc",
            F.to_json(F.struct("latitude", "longitude", "criticality_tier", "terrain")).alias("payload"),
        )
    )


@dp.materialized_view(name=f"{CATALOG}.{ANALYTICS}.resilience_simulator_inputs")
def resilience_simulator_inputs() -> DataFrame:
    telemetry = spark.read.table(TELEMETRY)  # type: ignore[name-defined]
    sites = spark.read.table(SITES)  # type: ignore[name-defined]
    return (
        telemetry.groupBy("site_id")
        .agg(
            F.avg("served_load_kwh").alias("average_load_kw"),
            (F.max("battery_soc_pct") * F.avg("served_load_kwh") / 10).alias("battery_usable_kwh"),
            F.max(F.when(F.col("generator_runtime_hours") > 0, F.col("served_load_kwh")).otherwise(0)).alias(
                "generator_capacity_kw"
            ),
            F.max("fuel_level_gal").alias("fuel_available_gal"),
        )
        .join(sites.select("site_id", "region", "criticality_tier"), "site_id")
    )


@dp.materialized_view(name=f"{CATALOG}.{ANALYTICS}.retrofit_inputs")
def retrofit_inputs() -> DataFrame:
    return spark.read.table(BENCHMARK).select(  # type: ignore[name-defined]
        "site_id",
        "region",
        "site_type",
        (F.col("total_energy_cost_usd") * F.greatest(1 - F.col("efficiency_index"), F.lit(0.0))).alias(
            "annual_source_savings_usd"
        ),
        F.when(F.col("site_type") == "small_cell", 5_500.0).otherwise(18_000.0).alias("capex_usd"),
    )
