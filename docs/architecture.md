# Architecture and modeling contracts

The system stores telemetry and analytical/model outputs in Delta. Lakebase owns operational work-order state and immutable decision audit history. Projection refreshes upsert analytical state and never truncate operational tables.

All timestamps are stored as UTC instants. `America/Puerto_Rico` is used only for local dates, hours, labels, and display strings. Synthetic history ends on the manifest reference date and every interface must display that as-of time.

## Source and cost accounting

- `served_load_kwh` is delivered energy during an explicit `interval_hours` period.
- Purchased grid energy includes battery charging. Battery discharge is not counted as newly purchased energy a second time.
- Diesel cost and carbon use measured `fuel_consumed_gal`, not generator kWh alone.
- Solar offsets instantaneous load and is not assigned a fuel or grid cost.
- Missing traffic produces a null efficiency ratio rather than division by zero.

## Cohorts and resilience

Peer cohorts are `(region, site_type)` bands. Efficiency compares site energy/GB to the cohort median. Resilience is observed served time during grid-loss events, bounded to `[0,1]`; missing event history stays missing instead of becoming perfect resilience.

Priority is `100 × (0.35 failure risk + 0.25 anomaly + 0.20 resilience deficit + 0.10 cost pressure + 0.10 criticality)`. Every input is bounded to `[0,1]`. If model scores are missing, `score_status='unscored'` and priority remains null.

## Security boundary

Injected fault ground truth is generated under the versioned source snapshot but is absent from all seven Bronze declarations, Genie assets, app queries, UC tools, and Vector Search metadata. Technician identifiers are one-way synthetic hashes and are not indexed. The agent can insert only `proposed` work orders. Approval/rejection executes through a database function that verifies optimistic version, regional scope, and writes the audit snapshot in the same transaction.
