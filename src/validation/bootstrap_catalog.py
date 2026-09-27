"""Idempotently create the configured Unity Catalog namespace and Volume."""

from __future__ import annotations

from config.settings import get_settings

from validation.spark import get_spark


def main() -> None:
    settings = get_settings()
    spark = get_spark()
    spark.sql(f"CREATE CATALOG IF NOT EXISTS {settings.catalog}")
    for schema in (
        settings.schema_raw,
        settings.schema_curated,
        settings.schema_analytics,
        settings.schema_ml,
        settings.schema_agents,
    ):
        spark.sql(f"CREATE SCHEMA IF NOT EXISTS {settings.catalog}.{schema}")
    spark.sql(
        f"CREATE VOLUME IF NOT EXISTS {settings.catalog}.{settings.schema_raw}.{settings.volume_name} "
        "COMMENT 'Versioned synthetic Tower Energy Optimizer source snapshots'"
    )
    print(f"Catalog ready: {settings.catalog}; source volume: {settings.volume_path}")


if __name__ == "__main__":
    main()
