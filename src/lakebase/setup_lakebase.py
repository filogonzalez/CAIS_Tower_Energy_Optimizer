"""Idempotently provision Lakebase Autoscale and apply migrations."""

from __future__ import annotations

import argparse
from pathlib import Path

from common.databricks_auth import get_workspace_client
from config.settings import get_settings

from lakebase.db import lakebase_connection


def ensure_instance(name: str, capacity: str = "CU_1") -> None:
    client = get_workspace_client()
    try:
        client.database.get_database_instance(name=name)
        return
    except Exception:
        pass
    if not hasattr(client.database, "create_database_instance"):
        raise RuntimeError(
            "Installed databricks-sdk does not expose Lakebase Autoscale creation; upgrade SDK"
        )
    client.database.create_database_instance(name=name, capacity=capacity)


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
