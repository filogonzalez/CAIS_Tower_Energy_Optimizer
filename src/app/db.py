"""Server-side authorization and Lakebase queries for the NOC app."""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

import psycopg

APPROVER_GROUP = os.getenv("TEO_APPROVER_GROUP", "teo-approvers")


@contextmanager
def app_connection() -> Iterator[psycopg.Connection]:
    dsn = os.getenv("TEO_LAKEBASE_DSN")
    if not dsn:
        raise RuntimeError("The Databricks App must be bound to the Lakebase resource key 'database'")
    connection = psycopg.connect(dsn, sslmode="require", connect_timeout=15)
    try:
        yield connection
    finally:
        connection.close()


@dataclass(frozen=True)
class UserContext:
    email: str
    groups: frozenset[str]
    regions: frozenset[str]

    @property
    def can_approve(self) -> bool:
        return APPROVER_GROUP in self.groups


def user_context_from_headers(headers) -> UserContext:
    email = headers.get("X-Forwarded-Email") or headers.get("X-Databricks-User-Email")
    if not email:
        raise PermissionError("Authenticated Databricks Apps identity is required")
    groups = frozenset(filter(None, (headers.get("X-Databricks-User-Groups") or "").split(",")))
    regions = frozenset(filter(None, (headers.get("X-TEO-Regions") or "").split(",")))
    return UserContext(email=email, groups=groups, regions=regions)


def fetch_site_status(user: UserContext, limit: int = 500) -> list[dict]:
    if not user.regions:
        return []
    query = """
      SELECT site_id, region, municipio, site_type, priority_score, score_status,
             anomaly_score, failure_risk_14d, resilience_score, current_source,
             open_work_order_count, as_of_utc, payload
      FROM tower_energy.site_status
      WHERE region = ANY(%s)
      ORDER BY priority_score DESC NULLS LAST
      LIMIT %s
    """
    with app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(user.regions), min(max(limit, 1), 1_000)))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def fetch_proposals(user: UserContext) -> list[dict]:
    query = """
      SELECT w.work_order_id, w.site_id, w.asset_id, w.status, w.version,
             w.proposed_by, w.proposed_at_utc, w.recommendation
      FROM tower_energy.work_orders w
      JOIN tower_energy.site_status s ON s.site_id = w.site_id
      WHERE w.status = 'proposed' AND s.region = ANY(%s)
      ORDER BY w.proposed_at_utc DESC LIMIT 100
    """
    with app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, (list(user.regions),))
            columns = [item.name for item in cursor.description]
            return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def decide_work_order(
    user: UserContext,
    work_order_id: str,
    expected_version: int,
    decision: str,
    reason: str,
    idempotency_key: str,
) -> dict:
    if not user.can_approve:
        raise PermissionError("Approver group membership is required")
    with app_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM tower_energy.decide_work_order(%s,%s,%s,%s,%s,%s,%s)",
                (
                    uuid.UUID(work_order_id),
                    expected_version,
                    decision,
                    user.email,
                    reason,
                    idempotency_key,
                    list(user.regions),
                ),
            )
            result = cursor.fetchone()
            columns = [item.name for item in cursor.description]
        connection.commit()
    return dict(zip(columns, result, strict=True))
