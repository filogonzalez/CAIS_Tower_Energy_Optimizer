"""Upsert analytical projections without touching operational history."""

from __future__ import annotations

import json

from config.settings import get_settings
from validation.spark import get_spark

from lakebase.db import lakebase_connection

SITE_STATUS_UPSERT = """
INSERT INTO tower_energy.site_status (
  site_id, region, municipio, site_type, priority_score, score_status,
  anomaly_score, failure_risk_14d, resilience_score, current_source,
  open_work_order_count, as_of_utc, payload
) VALUES (
  %(site_id)s, %(region)s, %(municipio)s, %(site_type)s, %(priority_score)s,
  %(score_status)s, %(anomaly_score)s, %(failure_risk_14d)s,
  %(resilience_score)s, %(current_source)s,
  (SELECT count(*) FROM tower_energy.work_orders w
   WHERE w.site_id = %(site_id)s AND w.status IN ('proposed','approved')),
  %(as_of_utc)s, %(payload)s::jsonb
)
ON CONFLICT (site_id) DO UPDATE SET
  region = EXCLUDED.region,
  municipio = EXCLUDED.municipio,
  site_type = EXCLUDED.site_type,
  priority_score = EXCLUDED.priority_score,
  score_status = EXCLUDED.score_status,
  anomaly_score = EXCLUDED.anomaly_score,
  failure_risk_14d = EXCLUDED.failure_risk_14d,
  resilience_score = EXCLUDED.resilience_score,
  current_source = EXCLUDED.current_source,
  open_work_order_count = EXCLUDED.open_work_order_count,
  as_of_utc = EXCLUDED.as_of_utc,
  payload = EXCLUDED.payload
"""


def upsert_rows(rows: list[dict]) -> int:
    settings = get_settings()
    normalized = [{**row, "payload": json.dumps(row.get("payload", {}), sort_keys=True)} for row in rows]
    with lakebase_connection(settings) as connection:
        with connection.cursor() as cursor:
            cursor.executemany(SITE_STATUS_UPSERT, normalized)
        connection.commit()
    return len(rows)


def main() -> None:
    settings = get_settings()
    spark = get_spark()
    rows = [
        row.asDict(recursive=True)
        for row in spark.table(settings.table_analytics("site_status_projection")).collect()
    ]  # type: ignore[name-defined]
    print(f"Upserted {upsert_rows(rows)} site projections")


if __name__ == "__main__":
    main()
