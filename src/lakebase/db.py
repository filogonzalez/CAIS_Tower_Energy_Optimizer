"""Short-lived OAuth Lakebase connection helpers."""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager

import psycopg
from common.databricks_auth import mint_lakebase_oauth_token
from config.settings import Settings


@contextmanager
def lakebase_connection(settings: Settings, *, autocommit: bool = False) -> Iterator[psycopg.Connection]:
    managed_dsn = os.getenv("TEO_LAKEBASE_DSN")
    if managed_dsn:
        connection = psycopg.connect(managed_dsn, autocommit=autocommit, connect_timeout=15)
        try:
            yield connection
        finally:
            connection.close()
        return
    credential = mint_lakebase_oauth_token(
        settings.lakebase_instance_name,
        database=settings.lakebase_database,
    )
    connection = psycopg.connect(
        host=credential.host,
        port=credential.port,
        dbname=credential.database,
        user=credential.user,
        password=credential.password,
        sslmode="require",
        autocommit=autocommit,
        connect_timeout=15,
    )
    try:
        yield connection
    finally:
        connection.close()
