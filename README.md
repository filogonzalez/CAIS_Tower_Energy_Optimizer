# Tower Energy Optimizer — Puerto Rico

Synthetic Energy NOC for a fictional Puerto Rico telecom operator (default: **IslaNet Telecom**) on Databricks. The implementation covers deterministic source generation, Lakeflow Spark Declarative Pipelines, ML scoring, Lakebase operational workflows, Vector Search, a proposal-only maintenance agent, Genie, a Dash cockpit, a Databricks Connect simulator, and Declarative Automation Bundles.

This repository never stores OAuth tokens, personal access tokens, client secrets, or Lakebase passwords. Remote code uses Databricks SDK `Config()` / `WorkspaceClient()` resolution and mints Lakebase OAuth credentials only in memory. Do not add credentials to `.env`, bundle variables, job parameters, source, logs, or artifacts.

## Data contract

- Seed: `42`; reference date is frozen in `generation_manifest.json`.
- Default scale: 300 sites, 180 days, 1,296,000 hourly readings, approximately 2,400 assets, approximately 4,000 outages, 10,000 work orders, and 36 distinct-site injected faults.
- Geography: coordinates are sampled inside simplified Puerto Rico, Vieques, and Culebra land polygons and validated with a recorded tolerance/provenance.
- Time: UTC at rest; `America/Puerto_Rico` for local day/hour/display conversion.
- Ground truth: `injected_faults` is restricted to generation and evaluation and is not a Bronze source, app/Genie input, agent tool, or vector-index column.

See `docs/architecture.md` for source accounting, cohort, resilience, missing-value, and priority definitions.

## Local setup and tests

Python 3.11 or 3.12 is supported.

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m compileall -q src tests
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check src tests
```

For a small local generation smoke test, override scale while preserving the production defaults:

```bash
TEO_SITE_COUNT=300 TEO_TELEMETRY_DAYS=60 TEO_REFERENCE_DATE=2026-09-26 \
  .venv/bin/python -m mock_data.generate_energy_data --output data/generated
```

The full default snapshot is intentionally large. Generated data and manifests are ignored by git.

## Secure Databricks deployment

The CLI must be at least 1.12 for the local-environment workflow; this project was validated with CLI 1.15.0. Profile selection is always explicit:

```bash
databricks auth profiles
./scripts/deploy.sh <PROFILE> dev
```

Set target-specific variables without secrets, for example:

```bash
databricks bundle validate --strict -t dev --profile <PROFILE> \
  --var warehouse_id=<SERVERLESS_WAREHOUSE_ID> \
  --var reference_date=2026-09-26
```

Initial acceptance order:

```bash
databricks bundle run generate_mock_data -t dev --profile <PROFILE>
databricks bundle run energy_pipeline -t dev --profile <PROFILE>
databricks bundle run train_models -t dev --profile <PROFILE>
databricks bundle run deploy_agent -t dev --profile <PROFILE>
databricks bundle run daily_refresh -t dev --profile <PROFILE>
databricks bundle run run_simulator -t dev --profile <PROFILE>
databricks bundle run setup_genie -t dev --profile <PROFILE>
```

No schedule is declared. A human deployment owner must authorize any recurring schedule after acceptance.

## Databricks-only validation

Run capability discovery before provisioning:

```bash
databricks auth profiles
databricks bundle run capability_manifest -t dev --profile <PROFILE>
```

After deployment, validate resource and data state with an explicitly selected profile:

```bash
databricks bundle validate --strict -t dev --profile <PROFILE>
databricks pipelines get ${resources.pipelines.energy_pipeline.id} --profile <PROFILE>
databricks vector-search-indexes get-index <catalog>.<agents_schema>.resolved_incidents_index --profile <PROFILE>
databricks apps get <app-name> --profile <PROFILE>
```

Workspace acceptance must record run IDs, resource IDs, timestamps, exact denominators, and limitations for each phase. Bundle deployment alone is not acceptance. Required unverified remote gates include serverless availability, Lakebase Autoscale, endpoint/model availability, Vector Search sync, 29/36 detection with healthy-site FPR below 5%, 17/20 agent correctness, seven Genie reference answers, app authorization/latency, governance negative tests, safe rerun, and fresh-workspace deployment.

## Repository map

- `src/mock_data/`: deterministic generation, causal faults, Volume upload, geography/data validation.
- `src/pipeline/`: seven-source Bronze plus Silver and Gold SDP.
- `src/ml/`: baseline, anomaly, failure-risk training, scoring, and frozen gate metrics.
- `src/lakebase/`: Autoscale setup, migrations, runtime OAuth, projections, and audit mirror.
- `src/vector_search/`: storage-optimized Delta Sync index.
- `src/agent/`: bounded UC tools, structured bilingual agent, fixed evaluation, gated deploy.
- `src/genie/`: governed bilingual space and trusted SQL assets.
- `src/app/`: Dash NOC cockpit with server-side user/region authorization.
- `src/connect/`: deterministic resilience and retrofit simulator.
- `resources/`, `databricks.yml`: serverless pipelines, jobs, app, variables, and targets.

See `docs/demo_script.md` for the demo flow.
