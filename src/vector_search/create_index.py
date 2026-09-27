"""Provision a storage-optimized Delta Sync index for resolved incidents."""

from __future__ import annotations

import argparse
import time

from common.databricks_auth import assert_endpoint_available, get_workspace_client
from config.settings import get_settings
from databricks.sdk.service.vectorsearch import (
    DeltaSyncVectorIndexSpecRequest,
    EmbeddingSourceColumn,
    EndpointType,
    PipelineType,
    VectorIndexType,
)

SAFE_SYNC_COLUMNS = [
    "wo_id",
    "incident_text",
    "component",
    "region",
    "site_type",
    "environment",
    "closed_ts_utc",
]


def ensure_endpoint_and_index(wait: bool = True) -> str:
    settings = get_settings()
    client = get_workspace_client()
    if not assert_endpoint_available(client, settings.embedding_endpoint):
        raise RuntimeError(f"Embedding endpoint is unavailable: {settings.embedding_endpoint}")
    endpoint_name = settings.vector_search_endpoint
    try:
        client.vector_search_endpoints.get_endpoint(endpoint_name)
    except Exception:
        client.vector_search_endpoints.create_endpoint_and_wait(
            name=endpoint_name,
            endpoint_type=EndpointType.STORAGE_OPTIMIZED,
        )
    index_name = settings.table_agents("resolved_incidents_index")
    source_table = settings.table_agents("resolved_incidents_for_index")
    try:
        client.vector_search_indexes.get_index(index_name=index_name)
    except Exception:
        client.vector_search_indexes.create_index(
            name=index_name,
            endpoint_name=endpoint_name,
            primary_key="wo_id",
            index_type=VectorIndexType.DELTA_SYNC,
            delta_sync_index_spec=DeltaSyncVectorIndexSpecRequest(
                source_table=source_table,
                pipeline_type=PipelineType.TRIGGERED,
                embedding_source_columns=[
                    EmbeddingSourceColumn(
                        name="incident_text",
                        embedding_model_endpoint_name=settings.embedding_endpoint,
                    )
                ],
                columns_to_sync=SAFE_SYNC_COLUMNS,
            ),
        )
    client.vector_search_indexes.sync_index(index_name=index_name)
    if wait:
        for _ in range(60):
            status = client.vector_search_indexes.get_index(index_name=index_name)
            ready = str(getattr(getattr(status, "status", None), "ready", "")).upper()
            if ready == "READY":
                return index_name
            time.sleep(10)
        raise TimeoutError(f"Vector index did not become ready: {index_name}")
    return index_name


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-wait", action="store_true")
    args = parser.parse_args()
    print(ensure_endpoint_and_index(wait=not args.no_wait))


if __name__ == "__main__":
    main()
