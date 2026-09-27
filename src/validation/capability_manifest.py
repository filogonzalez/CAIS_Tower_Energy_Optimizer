"""Read-only workspace capability discovery with secret-free output."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from common.databricks_auth import get_workspace_client
from config.settings import get_settings


def _probe(callable_) -> dict:
    try:
        value = callable_()
        return {"available": True, "detail": str(value)[:240]}
    except Exception as exc:
        return {"available": False, "detail": f"{type(exc).__name__}: {exc}"[:240]}


def build_manifest() -> dict:
    settings = get_settings()
    client = get_workspace_client()
    identity = client.current_user.me()
    return {
        "observed_at_utc": datetime.now(UTC).isoformat(),
        "workspace_host": client.config.host,
        "principal": identity.user_name,
        "target": settings.target,
        "capabilities": {
            "catalog": _probe(lambda: client.catalogs.get(settings.catalog)),
            "serverless_sql": _probe(lambda: list(client.warehouses.list())[:5]),
            "serverless_jobs": _probe(lambda: list(client.jobs.list(limit=1))),
            "pipelines": _probe(lambda: list(client.pipelines.list_pipelines(max_results=1))),
            "apps": _probe(lambda: list(client.apps.list())[:1]),
            "lakebase_autoscale": _probe(
                lambda: client.database.get_database_instance(settings.lakebase_instance_name)
            ),
            "vector_search": _probe(
                lambda: client.vector_search_endpoints.get_endpoint(settings.vector_search_endpoint)
            ),
            "embedding_endpoint": _probe(lambda: client.serving_endpoints.get(settings.embedding_endpoint)),
            "agent_model_primary": _probe(lambda: client.serving_endpoints.get(settings.agent_llm_endpoint)),
            "agent_model_fallback": _probe(
                lambda: client.serving_endpoints.get(settings.agent_llm_fallback_endpoint)
            ),
            "genie_api": _probe(lambda: client.api_client.do("GET", "/api/2.0/genie/spaces")),
        },
        "limitations": [
            "This manifest is read-only and does not establish resource creation permission.",
            "Quota and regional availability require an authenticated target-specific acceptance run.",
        ],
    }


def main() -> None:
    manifest = build_manifest()
    Path("artifacts").mkdir(exist_ok=True)
    output = Path("artifacts/capability_manifest.json")
    output.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    print(output)


if __name__ == "__main__":
    main()
