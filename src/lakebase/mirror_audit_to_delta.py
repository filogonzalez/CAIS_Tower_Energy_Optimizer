"""Idempotently mirror Lakebase audit events into governed Delta."""

from __future__ import annotations

import pandas as pd
from config.settings import get_settings
from validation.spark import get_spark

from lakebase.db import lakebase_connection


def main() -> None:
    settings = get_settings()
    spark = get_spark()
    with lakebase_connection(settings) as connection:
        frame = pd.read_sql_query("SELECT * FROM tower_energy.agent_audit_log", connection)
    incoming = spark.createDataFrame(frame)  # type: ignore[name-defined]
    incoming.createOrReplaceTempView("incoming_audit")
    target = settings.table_analytics("agent_audit_log")
    spark.sql(  # type: ignore[name-defined]
        f"""
        CREATE TABLE IF NOT EXISTS {target} USING DELTA AS SELECT * FROM incoming_audit WHERE 1=0;
        MERGE INTO {target} target
        USING incoming_audit source
        ON target.audit_id = source.audit_id
        WHEN NOT MATCHED THEN INSERT *
        """
    )


if __name__ == "__main__":
    main()
