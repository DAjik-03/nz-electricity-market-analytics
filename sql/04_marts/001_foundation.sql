CREATE SCHEMA analytics;

CREATE TABLE analytics.ref_generation_classification (
    classification_version integer NOT NULL,
    fuel_code text NOT NULL,
    tech_code text NOT NULL,
    standard_category text NOT NULL,
    generation_role text NOT NULL CHECK (generation_role IN ('Primary','Storage','Unclassified')),
    energy_status text NOT NULL CHECK (energy_status IN ('Renewable','Fossil','Storage','Unclassified')),
    evidence_url text NOT NULL,
    review_status text NOT NULL,
    rationale text NOT NULL,
    PRIMARY KEY (classification_version,fuel_code,tech_code),
    CHECK ((generation_role='Primary' AND energy_status IN ('Renewable','Fossil')) OR
           (generation_role='Storage' AND energy_status='Storage') OR
           (generation_role='Unclassified' AND energy_status='Unclassified'))
);

INSERT INTO analytics.ref_generation_classification
SELECT 1,fuel,tech,category,'Primary','Renewable',
 'https://www.mbie.govt.nz/building-and-energy/energy-and-natural-resources/energy-statistics-and-modelling/energy-statistics/renewables-statistics',
 'Reviewed fuel descriptor','Fuel descriptor matched to MBIE renewable resource category; technology retained unchanged.'
FROM (VALUES ('Hydro','Hydro','Hydro'),('Wind','Wind','Wind'),('Solar','Solar','Solar'),
             ('Wood','Cogen','Bioenergy')) x(fuel,tech,category);

INSERT INTO analytics.ref_generation_classification VALUES
(1,'Geo','Geo','Geothermal','Primary','Renewable',
 'https://forum.emi.ea.govt.nz/thread/changes-in-tech-codes-for-generation-md-files-causing-automation-errors/',
 'Reviewed legacy descriptor','Legacy Geo/Geothermal correspondence appears in EMI discussion acknowledged by administrator; MBIE classifies geothermal as renewable. No case folding of other codes.');

INSERT INTO analytics.ref_generation_classification
SELECT 1,fuel,tech,'Fossil thermal','Primary','Fossil',
 'https://www.ea.govt.nz/news/eye-on-electricity/the-role-of-thermal-generation/',
 'Reviewed fuel descriptor','EA identifies coal, gas and diesel thermal generation; classification follows fuel, including gas cogeneration.'
FROM (VALUES ('Coal','Thrml'),('Diesel','Thrml'),('Gas','Thrml'),('Gas','Cogen')) x(fuel,tech);

INSERT INTO analytics.ref_generation_classification VALUES
(1,'ELE','BAT','Battery storage','Storage','Storage',
 'https://www.ea.govt.nz/news/eye-on-electricity/eye-on-electricity-battery-performance-in-new-zealand/',
 'Reviewed pilot plant evidence','Observed plants are rotohiko and ruakākā_energy_park; EA identifies both as batteries. Approved storage treatment; charging energy origin is not inferred.');

INSERT INTO analytics.ref_generation_classification
SELECT 1,fuel,tech,'Unclassified','Unclassified','Unclassified',
 'https://www.emi.ea.govt.nz/Wholesale/Datasets/Generation/Generation_MD',
 'Unresolved code legend','Dataset metadata defines fields but no authoritative mapping for this exact pair was confirmed. Preserve separately; do not silently expand abbreviations.'
FROM (VALUES ('GEO','GEO'),('HYD','HYD'),('SOL','PV'),('WIN','ONW')) x(fuel,tech);

CREATE TABLE analytics.configuration (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    classification_version integer NOT NULL,
    expected_zones text[] NOT NULL,
    pilot_months date[] NOT NULL,
    percentile double precision NOT NULL CHECK(percentile=0.99)
);
INSERT INTO analytics.configuration VALUES
(true,1,ARRAY['CNI','LNI','LSI','UNI','USI'],ARRAY[DATE '2025-09-01',DATE '2026-04-01',DATE '2026-08-01'],0.99);

CREATE TABLE analytics.refresh_run (
    refresh_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    completed_at timestamptz,
    status text NOT NULL CHECK(status IN ('RUNNING','COMPLETED','ERROR')),
    input_fingerprint text,
    input_manifest jsonb,
    code_sha256 text NOT NULL,
    git_commit text NOT NULL,
    dq_run_id bigint REFERENCES quality.dq_run,
    error_message text
);
CREATE TABLE analytics.current_refresh (
    singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
    refresh_id bigint NOT NULL REFERENCES analytics.refresh_run
);

-- Private refresh storage. Consumers use guarded mart views, never this table.
CREATE TABLE analytics._interval_cache (
    scope text NOT NULL CHECK(scope IN ('National','Zone')),
    zone text NOT NULL,
    interval_id bigint NOT NULL,
    trading_date date NOT NULL,
    trading_period integer NOT NULL,
    start_utc timestamptz NOT NULL,
    end_utc timestamptz NOT NULL,
    local_start timestamp NOT NULL,
    local_end timestamp NOT NULL,
    expected_periods integer NOT NULL,
    offtake_kwh numeric,
    priced_offtake_kwh numeric,
    price_numerator numeric,
    offtake_source_rows bigint,
    offtake_poc_zone_rows bigint,
    generation_source_rows bigint,
    generation_kwh numeric,
    renewable_kwh numeric,
    fossil_kwh numeric,
    storage_kwh numeric,
    unclassified_kwh numeric,
    known_zone_offtake_kwh numeric,
    known_zone_generation_kwh numeric,
    PRIMARY KEY(scope,zone,interval_id),
    UNIQUE(scope,zone,start_utc),
    CHECK(end_utc=start_utc+INTERVAL '30 minutes')
);
REVOKE ALL ON analytics._interval_cache FROM PUBLIC;

CREATE FUNCTION analytics.input_manifest() RETURNS jsonb LANGUAGE sql STABLE AS $$
 SELECT jsonb_build_object(
 'selections',(SELECT jsonb_agg(jsonb_build_object('source',s.source_name,'month',s.source_month,
                 'publication',s.publication_id,'sha256',p.sha256) ORDER BY s.source_name,s.source_month)
               FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id)),
 'configuration',(SELECT to_jsonb(c) FROM analytics.configuration c),
 'classification',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.fuel_code,r.tech_code)
                    FROM analytics.ref_generation_classification r JOIN analytics.configuration c USING(classification_version)),
 'migrations',(SELECT jsonb_agg(to_jsonb(m) - 'applied_at' ORDER BY path)
                FROM metadata.schema_migration m))
$$;
CREATE FUNCTION analytics.input_fingerprint() RETURNS text LANGUAGE sql STABLE AS $$
 SELECT encode(sha256(convert_to(analytics.input_manifest()::text,'UTF8')),'hex')
$$;
CREATE FUNCTION analytics.assert_current() RETURNS boolean LANGUAGE plpgsql STABLE AS $$
DECLARE stored text;
BEGIN
 SELECT r.input_fingerprint INTO stored FROM analytics.current_refresh c
 JOIN analytics.refresh_run r USING(refresh_id) WHERE r.status='COMPLETED';
 IF stored IS NULL OR stored<>analytics.input_fingerprint() THEN
   RAISE EXCEPTION 'Analytical marts absent or stale: run the approved analytics refresh';
 END IF;
 RETURN true;
END $$;

CREATE VIEW analytics.refresh_status AS
SELECT r.*,r.input_fingerprint=analytics.input_fingerprint() AS is_current,
       q.as_of_date AS dq_as_of_date,q.status AS dq_status
FROM analytics.current_refresh c JOIN analytics.refresh_run r USING(refresh_id)
LEFT JOIN quality.dq_run q ON q.run_id=r.dq_run_id;
