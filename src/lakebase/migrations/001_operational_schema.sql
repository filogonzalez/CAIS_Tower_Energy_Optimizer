CREATE SCHEMA IF NOT EXISTS tower_energy;

CREATE TABLE IF NOT EXISTS tower_energy.site_status (
  site_id text PRIMARY KEY,
  region text NOT NULL,
  municipio text NOT NULL,
  site_type text NOT NULL,
  priority_score double precision,
  score_status text NOT NULL CHECK (score_status IN ('scored', 'unscored')),
  anomaly_score double precision,
  failure_risk_14d double precision,
  resilience_score double precision,
  current_source text,
  open_work_order_count integer NOT NULL DEFAULT 0,
  as_of_utc timestamptz NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS tower_energy.work_orders (
  work_order_id uuid PRIMARY KEY,
  proposal_key text UNIQUE NOT NULL,
  site_id text NOT NULL,
  asset_id text,
  component text,
  recommendation jsonb NOT NULL,
  status text NOT NULL DEFAULT 'proposed' CHECK (status IN ('proposed', 'approved', 'rejected', 'cancelled')),
  version integer NOT NULL DEFAULT 1,
  proposed_by text NOT NULL,
  proposed_at_utc timestamptz NOT NULL DEFAULT now(),
  decided_by text,
  decided_at_utc timestamptz,
  decision_reason text
);

CREATE TABLE IF NOT EXISTS tower_energy.agent_audit_log (
  audit_id uuid PRIMARY KEY,
  idempotency_key text UNIQUE NOT NULL,
  event_type text NOT NULL,
  actor text NOT NULL,
  region_scope text[],
  work_order_id uuid,
  event_ts_utc timestamptz NOT NULL DEFAULT now(),
  snapshot jsonb NOT NULL
);

CREATE TABLE IF NOT EXISTS tower_energy.site_energy_7d (
  site_id text NOT NULL,
  local_date date NOT NULL,
  grid_kwh double precision NOT NULL,
  generator_kwh double precision NOT NULL,
  solar_kwh double precision NOT NULL,
  battery_discharge_kwh double precision NOT NULL,
  PRIMARY KEY (site_id, local_date)
);

CREATE TABLE IF NOT EXISTS tower_energy.component_health (
  asset_id text PRIMARY KEY,
  site_id text NOT NULL,
  component text NOT NULL,
  failure_risk_14d double precision,
  anomaly_score double precision,
  score_status text NOT NULL,
  as_of_utc timestamptz NOT NULL
);

CREATE INDEX IF NOT EXISTS work_orders_site_status_idx ON tower_energy.work_orders (site_id, status);
CREATE INDEX IF NOT EXISTS audit_event_ts_idx ON tower_energy.agent_audit_log (event_ts_utc DESC);
CREATE INDEX IF NOT EXISTS component_health_site_idx ON tower_energy.component_health (site_id);

CREATE OR REPLACE FUNCTION tower_energy.enforce_proposal_insert() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status <> 'proposed' OR NEW.decided_by IS NOT NULL OR NEW.decided_at_utc IS NOT NULL THEN
    RAISE EXCEPTION 'proposal role may only insert proposed work orders';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS work_order_proposal_guard ON tower_energy.work_orders;
CREATE TRIGGER work_order_proposal_guard BEFORE INSERT ON tower_energy.work_orders
FOR EACH ROW EXECUTE FUNCTION tower_energy.enforce_proposal_insert();

CREATE OR REPLACE FUNCTION tower_energy.decide_work_order(
  p_work_order_id uuid,
  p_expected_version integer,
  p_decision text,
  p_actor text,
  p_reason text,
  p_idempotency_key text,
  p_region_scope text[]
) RETURNS tower_energy.work_orders
LANGUAGE plpgsql SECURITY DEFINER AS $$
DECLARE
  updated tower_energy.work_orders;
BEGIN
  IF p_decision NOT IN ('approved', 'rejected') THEN
    RAISE EXCEPTION 'invalid decision';
  END IF;
  UPDATE tower_energy.work_orders
    SET status = p_decision,
        decided_by = p_actor,
        decided_at_utc = now(),
        decision_reason = p_reason,
        version = version + 1
    WHERE work_order_id = p_work_order_id
      AND status = 'proposed'
      AND version = p_expected_version
      AND EXISTS (
        SELECT 1 FROM tower_energy.site_status s
        WHERE s.site_id = work_orders.site_id AND s.region = ANY(p_region_scope)
      )
    RETURNING * INTO updated;
  IF updated.work_order_id IS NULL THEN
    RAISE EXCEPTION 'stale, unauthorized, or already-decided work order';
  END IF;
  INSERT INTO tower_energy.agent_audit_log (
    audit_id, idempotency_key, event_type, actor, region_scope, work_order_id, snapshot
  ) VALUES (
    gen_random_uuid(), p_idempotency_key, 'work_order_' || p_decision, p_actor,
    p_region_scope, updated.work_order_id, to_jsonb(updated)
  );
  RETURN updated;
END;
$$;

DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'teo_projection_writer') THEN CREATE ROLE teo_projection_writer; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'teo_proposal_writer') THEN CREATE ROLE teo_proposal_writer; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'teo_approval_service') THEN CREATE ROLE teo_approval_service; END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'teo_readonly') THEN CREATE ROLE teo_readonly; END IF;
END $$;

REVOKE ALL ON ALL TABLES IN SCHEMA tower_energy FROM PUBLIC;
GRANT USAGE ON SCHEMA tower_energy TO teo_projection_writer, teo_proposal_writer, teo_approval_service, teo_readonly;
GRANT SELECT, INSERT, UPDATE ON tower_energy.site_status, tower_energy.site_energy_7d, tower_energy.component_health TO teo_projection_writer;
GRANT SELECT, INSERT ON tower_energy.work_orders TO teo_proposal_writer;
REVOKE UPDATE, DELETE ON tower_energy.work_orders FROM teo_proposal_writer;
GRANT SELECT ON ALL TABLES IN SCHEMA tower_energy TO teo_readonly, teo_approval_service;
GRANT EXECUTE ON FUNCTION tower_energy.decide_work_order(uuid, integer, text, text, text, text, text[]) TO teo_approval_service;
