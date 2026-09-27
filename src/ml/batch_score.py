"""Batch score canonical ML tables and preserve explicit score status."""

from __future__ import annotations

import argparse

import mlflow
from config.settings import get_settings
from pyspark.sql import functions as F
from validation.spark import get_spark

from ml.features import ANOMALY_FEATURES, FAILURE_FEATURES


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-uri", required=True)
    parser.add_argument("--anomaly-uri", required=True)
    parser.add_argument("--failure-uri", required=True)
    args = parser.parse_args()
    settings = get_settings()
    spark = get_spark()
    energy = spark.table(settings.table_ml("scoring_energy_features"))  # type: ignore[name-defined]
    assets = spark.table(settings.table_ml("scoring_failure_features"))  # type: ignore[name-defined]
    baseline_udf = mlflow.pyfunc.spark_udf(spark, args.baseline_uri, result_type="double")  # type: ignore[name-defined]
    anomaly_udf = mlflow.pyfunc.spark_udf(spark, args.anomaly_uri, result_type="double")  # type: ignore[name-defined]
    failure_udf = mlflow.pyfunc.spark_udf(spark, args.failure_uri, result_type="double")  # type: ignore[name-defined]
    energy_scored = (
        energy.withColumn(
            "expected_energy_kwh",
            baseline_udf(
                F.struct(
                    *[
                        F.col(name)
                        for name in [
                            "it_load_kw",
                            "hvac_load_kw",
                            "ambient_temp_c",
                            "network_traffic_gb",
                            "local_hour",
                        ]
                    ]
                )
            ),
        )
        .withColumn("anomaly_score_raw", anomaly_udf(F.struct(*[F.col(name) for name in ANOMALY_FEATURES])))
        .withColumn("anomaly_score", 1 / (1 + F.exp(F.col("anomaly_score_raw"))))
        .withColumn("score_ts_utc", F.current_timestamp())
    )
    energy_scored.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        settings.table_ml("site_anomalies")
    )
    asset_scored = (
        assets.withColumn(
            "failure_risk_14d", failure_udf(F.struct(*[F.col(name) for name in FAILURE_FEATURES]))
        )
        .join(
            energy_scored.groupBy("site_id").agg(F.max("anomaly_score").alias("anomaly_score")),
            "site_id",
            "left",
        )
        .withColumn("score_status", F.lit("scored"))
        .withColumn("score_ts_utc", F.current_timestamp())
    )
    asset_scored.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable(
        settings.table_ml("asset_health_scores")
    )


if __name__ == "__main__":
    main()
