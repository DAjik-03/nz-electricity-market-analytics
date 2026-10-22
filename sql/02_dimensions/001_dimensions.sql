CREATE TABLE core.dim_date (
    trading_date date PRIMARY KEY,
    calendar_year smallint NOT NULL,
    calendar_month smallint NOT NULL CHECK (calendar_month BETWEEN 1 AND 12),
    expected_periods smallint NOT NULL CHECK (expected_periods IN (46,48,50))
);
CREATE TABLE core.dim_trading_interval (
    interval_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    trading_date date NOT NULL REFERENCES core.dim_date,
    trading_period smallint NOT NULL CHECK (trading_period BETWEEN 1 AND 50),
    start_utc timestamptz NOT NULL UNIQUE,
    end_utc timestamptz NOT NULL,
    local_start timestamp NOT NULL,
    local_end timestamp NOT NULL,
    utc_offset_minutes smallint NOT NULL,
    end_utc_offset_minutes smallint NOT NULL,
    is_dst boolean NOT NULL,
    end_is_dst boolean NOT NULL,
    fold smallint NOT NULL CHECK (fold IN (0,1)),
    end_fold smallint NOT NULL CHECK (end_fold IN (0,1)),
    timezone text NOT NULL CHECK (timezone='Pacific/Auckland'),
    UNIQUE (trading_date,trading_period),
    CHECK (end_utc=start_utc+interval '30 minutes'),
    CHECK (local_start=start_utc AT TIME ZONE 'Pacific/Auckland'),
    CHECK (local_end=end_utc AT TIME ZONE 'Pacific/Auckland')
);
CREATE TABLE core.dim_pricing_node (
    pricing_node_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    pricing_poc text NOT NULL UNIQUE CHECK (pricing_poc<>'')
);
CREATE TABLE core.dim_connection (
    connection_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    poc text NOT NULL CHECK (poc<>''),
    network text NOT NULL CHECK (network<>''),
    UNIQUE (poc,network)
);
CREATE TABLE core.dim_participant (
    participant_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    participant_code text NOT NULL UNIQUE CHECK (participant_code<>'')
);
CREATE TABLE core.dim_generator (
    generator_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    gen_code text NOT NULL UNIQUE CHECK (gen_code<>'')
);
CREATE TABLE core.dim_nsp_version (
    nsp_version_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publication_id bigint NOT NULL REFERENCES metadata.source_publication,
    source_row_number bigint NOT NULL,
    nsp text NOT NULL,
    connection_id bigint NOT NULL REFERENCES core.dim_connection,
    original_start_date text NOT NULL,
    original_start_tp text NOT NULL,
    original_end_date text,
    original_end_tp text,
    zone text,
    island text,
    network_reporting_region_id text,
    network_reporting_region text,
    parent_poc text,
    parent_network text,
    source_metadata jsonb NOT NULL,
    valid_from_utc timestamptz,
    valid_to_utc_exclusive timestamptz,
    boundary_status text NOT NULL CHECK (boundary_status IN ('valid_bounded','valid_open','invalid_boundary')),
    exception_reason text,
    UNIQUE (publication_id,nsp,original_start_date,original_start_tp),
    UNIQUE (publication_id,source_row_number),
    UNIQUE (nsp_version_id,publication_id),
    FOREIGN KEY (publication_id,source_row_number) REFERENCES staging.network_supply_point,
    CHECK ((boundary_status='invalid_boundary' AND valid_from_utc IS NULL AND valid_to_utc_exclusive IS NULL AND exception_reason IS NOT NULL)
        OR (boundary_status='valid_open' AND valid_from_utc IS NOT NULL AND valid_to_utc_exclusive IS NULL AND exception_reason IS NULL)
        OR (boundary_status='valid_bounded' AND valid_from_utc IS NOT NULL AND valid_to_utc_exclusive>valid_from_utc AND exception_reason IS NULL))
);
CREATE INDEX nsp_effective_connection ON core.dim_nsp_version(publication_id,connection_id,valid_from_utc)
WHERE boundary_status <> 'invalid_boundary';

-- Called only for dates found in the source history; no historical fact archive
-- is loaded just to convert an NSP boundary.
CREATE FUNCTION core.tp_start(d date, tp integer) RETURNS timestamptz
LANGUAGE sql STABLE STRICT AS $$
 SELECT CASE WHEN tp BETWEEN 1 AND
    extract(epoch FROM ((d+1)::timestamp AT TIME ZONE 'Pacific/Auckland')-(d::timestamp AT TIME ZONE 'Pacific/Auckland'))/1800
 THEN (d::timestamp AT TIME ZONE 'Pacific/Auckland')+(tp-1)*interval '30 minutes' END
$$;
