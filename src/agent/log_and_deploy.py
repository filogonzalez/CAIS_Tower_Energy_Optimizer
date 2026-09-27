"""Log and deploy the agent only after deterministic evaluation passes."""

from __future__ import annotations

import json

import mlflow
from common.databricks_auth import get_workspace_client
from config.settings import get_settings


def deploy(model_uri: str, evaluation_path: str) -> None:
    evaluation = json.loads(open(evaluation_path, encoding="utf-8").read())
    if not evaluation.get("passed") or float(evaluation.get("accuracy", 0)) < 0.85:
        raise RuntimeError("Agent evaluation gate failed; refusing deployment")
    settings = get_settings()
    client = get_workspace_client()
    registered = mlflow.register_model(model_uri, settings.table_agents("maintenance_agent"))
    client.serving_endpoints.create_and_wait(
        name=settings.agent_serving_endpoint,
        config={
            "served_entities": [
                {
                    "entity_name": settings.table_agents("maintenance_agent"),
                    "entity_version": registered.version,
                    "workload_size": "Small",
                    "scale_to_zero_enabled": True,
                }
            ]
        },
    )


if __name__ == "__main__":
    raise SystemExit("Invoke deploy(model_uri, evaluation_path) from a gated job task")
