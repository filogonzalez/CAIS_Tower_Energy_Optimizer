"""Idempotently provision Lakebase Autoscale and apply migrations."""

from __future__ import annotations

import argparse
from pathlib import Path

from common.databricks_auth import get_workspace_client
from config.settings import get_settings

from lakebase.db import lakebase_connection


def ensure_instance(name: str, capacity: str = "CU_1", client=None) -> None:
    """Create the Lakebase instance unless it already exists.

    Targets the ``databricks-sdk>=0.60,<0.70`` API, where
    ``create_database_instance`` takes a single ``DatabaseInstance`` object.
    Only ``NotFound`` triggers creation, so auth/permission failures surface
    instead of being masked by a create attempt.
    """
    from databricks.sdk.errors import NotFound, ResourceAlreadyExists
    from databricks.sdk.service.database import DatabaseInstance

    client = client or get_workspace_client()
    try:
        client.database.get_database_instance(name=name)
        return
    except NotFound:
        pass
    try:
        created = client.database.create_database_instance(
            database_instance=DatabaseInstance(name=name, capacity=capacity)
        )
    except ResourceAlreadyExists:
        # Created concurrently between the get and create calls.
        return
    # Newer SDKs in the pinned range return a long-running-operation waiter;
    # block until the instance is available so migrations can connect.
    if hasattr(created, "result"):
        created.result()


def apply_migrations(migration_root: Path) -> None:
    settings = get_settings()
    with lakebase_connection(settings, autocommit=True) as connection:
        for migration in sorted(migration_root.glob("*.sql")):
            with connection.cursor() as cursor:
                cursor.execute(migration.read_text(encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-provision", action="store_true")
    args = parser.parse_args()
    settings = get_settings()
    if not args.skip_provision:
        ensure_instance(settings.lakebase_instance_name)
    apply_migrations(Path(__file__).with_name("migrations"))
    print(f"Lakebase schema ready: {settings.lakebase_instance_name}/{settings.lakebase_database}")


if __name__ == "__main__":
    main()
