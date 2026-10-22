CREATE SCHEMA quality;
CREATE TABLE quality.rule (
 rule_id integer GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 rule_code text NOT NULL UNIQUE,
 rule_name text NOT NULL,
 quality_dimension text NOT NULL CHECK (quality_dimension IN
 ('Completeness','Uniqueness','Validity','Consistency','Referential Integrity','Timeliness','Versioning')),
 target_object text NOT NULL,
 severity text NOT NULL CHECK (severity IN ('Critical','High','Medium','Low')),
 description text NOT NULL,
 business_implication text NOT NULL,
 expected_condition text NOT NULL,
 treatment text NOT NULL,
 is_blocking boolean NOT NULL,
 active_flag boolean NOT NULL DEFAULT true,
 query_sql text NOT NULL
);
CREATE TABLE quality.dq_run (
 run_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 completed_at timestamptz,
 as_of_date date NOT NULL,
 warehouse_fingerprint text,
 code_sha256 text NOT NULL,
 git_commit text NOT NULL,
 input_manifest jsonb,
 status text NOT NULL CHECK (status IN ('RUNNING','COMPLETED','BLOCKED','ERROR')),
 error_message text
);
CREATE TABLE quality.rule_result (
 run_id bigint NOT NULL REFERENCES quality.dq_run,
 rule_id integer NOT NULL REFERENCES quality.rule,
 rule_snapshot jsonb NOT NULL,
 result_status text NOT NULL CHECK (result_status IN ('PASS','WARN','FAIL')),
 affected_rows bigint NOT NULL CHECK (affected_rows>=0),
 observed_value jsonb NOT NULL,
 expected_value text NOT NULL,
 coverage_pct numeric,
 details jsonb NOT NULL,
 PRIMARY KEY (run_id,rule_id)
);
CREATE TABLE quality.coverage_metric (
 run_id bigint NOT NULL REFERENCES quality.dq_run,
 source_name text NOT NULL,
 source_month date NOT NULL,
 denominator_unit text NOT NULL,
 total_value numeric NOT NULL,
 known_value numeric NOT NULL,
 unknown_value numeric NOT NULL,
 coverage_pct numeric,
 PRIMARY KEY (run_id,source_name,source_month)
);
-- Approved slots and original content are configuration, not guessed current availability.
CREATE TABLE quality.expected_publication (
 source_name text NOT NULL, source_month date NOT NULL, baseline_sha256 text NOT NULL,
 baseline_staged_rows bigint NOT NULL, baseline_fact_rows bigint NOT NULL,
 baseline_total numeric, tolerance numeric NOT NULL DEFAULT 0,
 PRIMARY KEY(source_name,source_month)
);
CREATE VIEW quality.v_latest_dq_results AS
 SELECT r.*,q.started_at,q.completed_at,q.as_of_date,q.status AS run_status,
 r.rule_snapshot->>'rule_code' AS rule_code,
 r.rule_snapshot->>'rule_name' AS rule_name,
 r.rule_snapshot->>'quality_dimension' AS quality_dimension,
 r.rule_snapshot->>'severity' AS severity,
 (r.rule_snapshot->>'is_blocking')::boolean AS is_blocking
 FROM quality.rule_result r JOIN quality.dq_run q USING(run_id)
 WHERE q.run_id=(SELECT max(run_id) FROM quality.dq_run WHERE status IN ('COMPLETED','BLOCKED'));
CREATE VIEW quality.v_latest_dq_summary AS
 SELECT run_id,quality_dimension,count(*) AS rules,
 count(*) FILTER (WHERE result_status='PASS') AS pass_count,
 count(*) FILTER (WHERE result_status='WARN') AS warn_count,
 count(*) FILTER (WHERE result_status='FAIL') AS fail_count,
 count(*) FILTER (WHERE result_status='FAIL' AND is_blocking) AS blocking_failures
 FROM quality.v_latest_dq_results GROUP BY run_id,quality_dimension;
CREATE VIEW quality.v_latest_coverage AS
 SELECT c.* FROM quality.coverage_metric c WHERE run_id=
 (SELECT max(run_id) FROM quality.dq_run WHERE status IN ('COMPLETED','BLOCKED'));

CREATE FUNCTION quality.outcome(affected bigint, observed jsonb DEFAULT '{}'::jsonb,
 warning boolean DEFAULT false, diagnostic jsonb DEFAULT '{}'::jsonb, coverage numeric DEFAULT NULL)
 RETURNS jsonb LANGUAGE sql IMMUTABLE AS $$
 SELECT jsonb_build_object('result_status',CASE WHEN affected=0 THEN 'PASS' WHEN warning THEN 'WARN' ELSE 'FAIL' END,
 'affected_rows',affected,'observed_value',observed,'details',diagnostic,'coverage_pct',coverage)
$$;
CREATE FUNCTION quality.number(value text) RETURNS numeric LANGUAGE sql STABLE AS $$
 SELECT CASE WHEN pg_input_is_valid(value,'numeric') THEN value::numeric END
$$;

-- Thin physical-input views let rollback-only DQ fixtures test the same queries
-- without removing core constraints or modifying the real fact populations.
CREATE VIEW quality.input_price AS SELECT * FROM core.fact_price;
CREATE VIEW quality.input_volume AS SELECT * FROM core.fact_reconciled_volume;
CREATE VIEW quality.input_generation AS SELECT * FROM core.fact_generation_connection;
CREATE VIEW quality.input_interval AS SELECT * FROM core.dim_trading_interval;
CREATE VIEW quality.input_nsp AS SELECT * FROM core.dim_nsp_version;
