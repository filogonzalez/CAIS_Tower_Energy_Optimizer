"""Databricks SDK authentication — the only place credentials are touched.

Every remote-facing script in this repository (Volume upload, Lakebase
setup, Vector Search index creation, agent deployment, Genie setup, the Dash
app's database layer) must obtain its ``WorkspaceClient``/``Config`` through
this module rather than constructing one inline.

Rules enforced here:
  * Credentials are resolved exclusively via the Databricks SDK's standard
    resolution order (env vars ``DATABRICKS_HOST``/``DATABRICKS_TOKEN``/
    ``DATABRICKS_CLIENT_ID``/``DATABRICKS_CLIENT_SECRET``, a named CLI
    profile, or the ambient identity of Databricks compute/Apps). Nothing in
    this repository reads, stores, or writes a token or password to a file.
  * When no credential can be resolved, callers get a clear, actionable
    ``AuthenticationRequiredError`` instead of a confusing downstream 401 —
    per the plan's contract, deployment/setup scripts must fail clearly
    rather than silently no-op or fall back to an insecure path.
  * Lakebase OAuth tokens are generated at call time via
    ``mint_lakebase_oauth_token`` and are never cached to disk; callers are
    expected to refresh before the token's (short) TTL expires.
  * Model-serving/AI Gateway bearer tokens for direct HTTP calls (see
    ``src/pipeline/note_extraction.py``) are resolved at call time via
    ``fetch_secret`` from a Databricks secret scope — never from a literal,
    an env var default, or a file — and are held only in local variables for
    the duration of a single request/batch.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass


class AuthenticationRequiredError(RuntimeError):
    """Raised when no secure Databricks credential is available.

    This is intentionally loud: scripts that provision or write to a live
    workspace must stop here rather than proceeding with partial/anonymous
    access.
    """


def _import_sdk():
    try:
        from databricks.sdk import WorkspaceClient
        from databricks.sdk.core import Config
    except ImportError as exc:  # pragma: no cover - exercised only if sdk missing
        raise AuthenticationRequiredError(
            "databricks-sdk is not installed. Install project dependencies "
            "(`pip install -e .` / `uv sync`) before running Databricks-facing "
            "scripts."
        ) from exc
    return Config, WorkspaceClient


def build_config():
    """Resolve a Databricks SDK ``Config`` or raise ``AuthenticationRequiredError``.

    Resolution order follows the SDK default: explicit constructor args (none
    given here) -> environment variables -> a ``~/.databrickscfg`` profile ->
    the ambient identity of Databricks-managed compute (job cluster, Apps,
    model serving). We never pass a token/profile literal from this codebase;
    it is entirely environment/host-managed.
    """
    Config, _ = _import_sdk()
    cfg = Config()
    try:
        cfg.authenticate()
    except Exception as exc:  # noqa: BLE001 - re-raised as a clearer error type
        raise AuthenticationRequiredError(
            "No secure Databricks credential was found. Set DATABRICKS_HOST "
            "plus one of: DATABRICKS_TOKEN, DATABRICKS_CLIENT_ID/"
            "DATABRICKS_CLIENT_SECRET, or configure a profile via "
            "`databricks configure`. This script refuses to proceed without "
            "an authenticated identity — never store a token in this repo."
        ) from exc
    return cfg


def get_workspace_client():
    """Return an authenticated ``WorkspaceClient`` or raise clearly."""
    Config, WorkspaceClient = _import_sdk()
    cfg = build_config()
    return WorkspaceClient(config=cfg)


def assert_endpoint_available(client, endpoint_name: str, kind: str = "serving") -> bool:
    """Check whether a named model-serving endpoint exists and is ready.

    Used before binding an LLM/embedding endpoint name from configuration —
    per the spec, endpoint availability must be *discovered*, not assumed.
    Returns True/False; callers decide whether missing availability is fatal
    (e.g. fall back from the primary agent LLM to its configured fallback).
    """
    try:
        ep = client.serving_endpoints.get(endpoint_name)
    except Exception:
        return False
    state = getattr(ep, "state", None)
    ready = getattr(state, "ready", None)
    return str(ready).upper() == "READY" if ready is not None else ep is not None


@dataclass(frozen=True)
class LakebaseCredential:
    """Short-lived Lakebase connection credential. Never persisted."""

    host: str
    port: int
    database: str
    user: str
    password: str  # OAuth token; held in memory only, for the life of a connection


def mint_lakebase_oauth_token(
    instance_name: str,
    *,
    database: str,
    user: str | None = None,
) -> LakebaseCredential:
    """Mint a fresh Lakebase (Postgres) OAuth credential for this process.

    The token is generated via the Databricks SDK against the target
    Database instance and must be treated as short-lived: callers should
    call this again (not cache the result) whenever a pool creates a new
    physical connection.
    """
    client = get_workspace_client()
    instance = client.database.get_database_instance(name=instance_name)
    host = instance.read_write_dns or instance.pgwire_endpoint
    if not host:
        raise AuthenticationRequiredError(
            f"Lakebase instance '{instance_name}' has no reachable endpoint yet "
            "(instance may still be provisioning)."
        )
    identity_user = user or client.current_user.me().user_name
    cred = client.database.generate_database_credential(
        request_id=f"teo-{instance_name}",
        instance_names=[instance_name],
    )
    if not identity_user or not cred or not cred.token:
        raise AuthenticationRequiredError(
            "Failed to mint a Lakebase OAuth credential for the current identity."
        )
    return LakebaseCredential(
        host=host,
        port=5432,
        database=database,
        user=identity_user,
        password=cred.token,
    )


def fetch_secret(scope: str, key: str) -> str:
    """Resolve a secret value at call time. Never logs or returns it wrapped.

    Tries, in order:
      1. ``dbutils.secrets.get`` — available on Databricks driver/job compute
         (notebook, job cluster, or Lakeflow pipeline driver). Values read
         this way are automatically redacted from notebook/driver stdout by
         the runtime.
      2. The Databricks SDK's ``WorkspaceClient.secrets.get_secret`` — works
         from any authenticated context (including Spark executors and
         Databricks Connect clients), decoded from its base64 wire format.

    Raises ``AuthenticationRequiredError`` if neither path resolves the
    secret. Callers must treat the return value as sensitive: hold it in a
    local variable only, never log/print it, and never write it to disk or
    include it in an exception message.
    """
    try:
        from pyspark.sql import SparkSession  # noqa: PLC0415

        spark = SparkSession.getActiveSession()
        if spark is not None:
            from pyspark.dbutils import DBUtils  # noqa: PLC0415

            dbutils = DBUtils(spark)
            value = dbutils.secrets.get(scope=scope, key=key)
            if value:
                return value
    except Exception:  # noqa: BLE001 - dbutils unavailable outside Databricks compute
        pass

    client = get_workspace_client()
    try:
        secret = client.secrets.get_secret(scope=scope, key=key)
    except Exception as exc:  # noqa: BLE001 - re-raised as a clearer error type
        raise AuthenticationRequiredError(
            f"Could not read secret '{key}' from scope '{scope}' via dbutils or "
            "the Databricks SDK. Create the scope/key (`databricks secrets "
            "create-scope` / `put-secret`) and grant this identity READ access."
        ) from exc
    if not secret or not secret.value:
        raise AuthenticationRequiredError(f"Secret '{key}' in scope '{scope}' is empty or inaccessible.")
    return base64.b64decode(secret.value).decode("utf-8")


def serving_endpoint_invocation_url(host: str, endpoint_name: str) -> str:
    """Direct model-serving invocation URL for a same-workspace endpoint.

    Used for the Python/pandas-UDF extraction path (``note_extraction.py``)
    when the workspace's SQL ``ai_query`` path is unavailable (legacy
    serving-endpoint registry lookup failing) but direct HTTPS POSTs from the
    driver/executors to the workspace's own AI Gateway succeed — this stays
    same-workspace, so it is not subject to an external egress IP ACL.
    """
    return f"{host.rstrip('/')}/serving-endpoints/{endpoint_name}/invocations"
