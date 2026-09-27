-- Trusted asset 1: last complete month energy summary
SELECT region, site_type,
       sum(grid_kwh) AS grid_kwh,
       sum(generator_kwh) AS generator_kwh,
       sum(total_energy_cost_usd) AS total_energy_cost_usd,
       sum(network_traffic_gb) AS network_traffic_gb
FROM ${catalog}.${schema_analytics}.gold_daily_site_energy
WHERE local_date >= add_months(trunc(current_date(), 'MM'), -1)
  AND local_date < trunc(current_date(), 'MM')
GROUP BY region, site_type;

-- Trusted asset 2: current maintenance priorities
SELECT site_id, region, site_type, priority_score, failure_risk_14d,
       anomaly_score, resilience_score, score_status
FROM ${catalog}.${schema_analytics}.gold_site_priority
WHERE score_status = 'scored'
ORDER BY priority_score DESC;

-- Trusted asset 3: governed approval audit
SELECT event_ts_utc, event_type, actor, work_order_id, snapshot
FROM ${catalog}.${schema_analytics}.agent_audit_log
ORDER BY event_ts_utc DESC;
