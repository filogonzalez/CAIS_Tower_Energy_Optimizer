"""Databricks-side SQL checks that fail jobs when a phase gate is unmet."""

from __future__ import annotations

import argparse

from config.settings import get_settings

from validation.spark import get_spark

CHECKS = {
    "phase2": [
        (
            "telemetry_drop_rate",
            "SELECT assert_true(count(*) >= 1283040) FROM {curated}.silver_energy_telemetry",
        ),
        (
            "note_extraction",
            "SELECT assert_true(avg(CAST(extraction_valid AS DOUBLE)) >= 0.95) "
            "FROM {curated}.silver_work_order_notes",
        ),
        (
            "fault_labels_absent",
            "SELECT assert_true(count(*) = 0) FROM {raw}.information_schema.columns "
            "WHERE lower(column_name) LIKE '%fault_id%'",
        ),
    ],
    "phase3": [
        ("scores_present", "SELECT assert_true(count(DISTINCT site_id) > 0) FROM {ml}.asset_health_scores"),
        (
            "unscored_explicit",
            "SELECT assert_true(count(*) = 0) FROM {analytics}.gold_site_priority WHERE score_status IS NULL",
        ),
    ],
    "phase4": [
        (
            "scenario_nonnegative",
            "SELECT assert_true(min(time_to_dark_hours) >= 0 AND min(unserved_kwh) >= 0) "
            "FROM {analytics}.outage_scenario_results",
        ),
        (
            "roi_versioned",
            "SELECT assert_true(count(DISTINCT scenario_version) = 1) FROM {analytics}.retrofit_roi",
        ),
    ],
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=CHECKS)
    args = parser.parse_args()
    settings = get_settings()
    spark = get_spark()
    namespaces = {
        "raw": f"{settings.catalog}.{settings.schema_raw}",
        "curated": f"{settings.catalog}.{settings.schema_curated}",
        "analytics": f"{settings.catalog}.{settings.schema_analytics}",
        "ml": f"{settings.catalog}.{settings.schema_ml}",
    }
    for name, statement in CHECKS[args.phase]:
        spark.sql(statement.format(**namespaces)).collect()
        print(f"PASS {name}")


if __name__ == "__main__":
    main()
