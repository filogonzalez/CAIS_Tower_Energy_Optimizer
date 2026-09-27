CREATE OR REPLACE FUNCTION ${catalog}.${schema_agents}.site_energy_profile(p_site_id STRING, p_days INT)
RETURNS TABLE (
  site_id STRING, local_date DATE, grid_kwh DOUBLE, generator_kwh DOUBLE,
  solar_kwh DOUBLE, served_load_kwh DOUBLE, total_energy_cost_usd DOUBLE,
  energy_per_gb DOUBLE
)
RETURN
  SELECT site_id, local_date, grid_kwh, generator_kwh, solar_kwh,
         served_load_kwh, total_energy_cost_usd, energy_per_gb
  FROM ${catalog}.${schema_analytics}.gold_daily_site_energy
  WHERE site_id = p_site_id
    AND local_date >= date_sub(current_date(), least(greatest(p_days, 1), 90));

CREATE OR REPLACE FUNCTION ${catalog}.${schema_agents}.asset_health(p_site_id STRING)
RETURNS TABLE (
  asset_id STRING, site_id STRING, component STRING, failure_risk_14d DOUBLE,
  anomaly_score DOUBLE, score_status STRING, score_ts_utc TIMESTAMP
)
RETURN
  SELECT asset_id, site_id, component, failure_risk_14d, anomaly_score,
         score_status, score_ts_utc
  FROM ${catalog}.${schema_ml}.asset_health_scores
  WHERE site_id = p_site_id;

CREATE OR REPLACE FUNCTION ${catalog}.${schema_agents}.site_resilience(p_site_id STRING)
RETURNS TABLE (
  site_id STRING, outage_count BIGINT, outage_minutes DOUBLE,
  downtime_minutes DOUBLE, generator_start_success DOUBLE
)
RETURN
  SELECT site_id, count(*) outage_count, sum(duration_minutes) outage_minutes,
         sum(downtime_minutes) downtime_minutes,
         avg(CAST(generator_started AS DOUBLE)) generator_start_success
  FROM ${catalog}.${schema_curated}.silver_power_events
  WHERE site_id = p_site_id
  GROUP BY site_id;

CREATE OR REPLACE FUNCTION ${catalog}.${schema_agents}.rank_maintenance(p_region STRING, p_limit INT)
RETURNS TABLE (
  site_id STRING, region STRING, priority_score DOUBLE, score_status STRING,
  failure_risk_14d DOUBLE, anomaly_score DOUBLE
)
RETURN
  SELECT site_id, region, priority_score, score_status, failure_risk_14d, anomaly_score
  FROM ${catalog}.${schema_analytics}.gold_site_priority
  WHERE region = p_region AND score_status = 'scored'
  ORDER BY priority_score DESC
  LIMIT least(greatest(p_limit, 1), 50);

CREATE OR REPLACE FUNCTION ${catalog}.${schema_agents}.estimate_fix_value(p_site_id STRING)
RETURNS TABLE (site_id STRING, trailing_cost_usd DOUBLE, peer_gap_ratio DOUBLE, estimated_monthly_savings_usd DOUBLE)
RETURN
  SELECT site_id, total_energy_cost_usd trailing_cost_usd,
         greatest(0D, 1D - efficiency_index) peer_gap_ratio,
         total_energy_cost_usd * greatest(0D, 1D - efficiency_index) / 6D estimated_monthly_savings_usd
  FROM ${catalog}.${schema_analytics}.gold_site_benchmark
  WHERE site_id = p_site_id;
