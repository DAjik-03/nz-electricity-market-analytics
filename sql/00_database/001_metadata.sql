-- Executed once by the checksum-checked migration runner, in filename order.
CREATE SCHEMA IF NOT EXISTS metadata;
CREATE SCHEMA staging;
CREATE SCHEMA core;

CREATE TABLE metadata.source_publication (
    publication_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source_name text NOT NULL CHECK (source_name IN ('prices','reconciliation','generation','nsp')),
    source_month date NOT NULL CHECK (extract(day FROM source_month)=1),
    filename text NOT NULL,
    sha256 text NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    prepared_at_unzoned timestamp,
    snapshot_date date,
    downloaded_at timestamptz NOT NULL,
    http_last_modified text,
    etag text,
    file_size_bytes bigint NOT NULL CHECK (file_size_bytes > 0),
    source_url text NOT NULL,
    manifest_metadata jsonb NOT NULL,
    status text NOT NULL DEFAULT 'registered' CHECK (status IN ('registered','loaded','failed')),
    staged_rows bigint,
    fact_rows bigint,
    loaded_at timestamptz,
    UNIQUE (source_name, sha256),
    UNIQUE (publication_id, source_name, source_month),
    CHECK ((source_name='nsp') = (snapshot_date IS NOT NULL)),
    CHECK (status <> 'loaded' OR (loaded_at IS NOT NULL AND staged_rows > 0 AND fact_rows >= 0))
);
-- NSP uses its snapshot month as source_month, with the exact snapshot_date retained.
CREATE TABLE metadata.publication_selection (
    source_name text NOT NULL,
    source_month date NOT NULL,
    publication_id bigint NOT NULL,
    selected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (source_name,source_month),
    FOREIGN KEY (publication_id,source_name,source_month)
      REFERENCES metadata.source_publication(publication_id,source_name,source_month)
);
CREATE TABLE metadata.load_attempt (
    attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    publication_id bigint NOT NULL REFERENCES metadata.source_publication,
    started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    finished_at timestamptz,
    status text NOT NULL CHECK (status IN ('running','succeeded','failed','skipped')),
    error_message text,
    elapsed_seconds numeric
);
CREATE FUNCTION metadata.require_loaded_selection() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM metadata.source_publication p
                   WHERE p.publication_id=NEW.publication_id AND p.status='loaded') THEN
        RAISE EXCEPTION 'Cannot select an unloaded publication';
    END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER selection_requires_loaded BEFORE INSERT OR UPDATE ON metadata.publication_selection
FOR EACH ROW EXECUTE FUNCTION metadata.require_loaded_selection();

-- All loader publications are serialised with a session advisory lock.
-- Reset before each COPY; source_row_number is the original data-row ordinal.
CREATE SEQUENCE staging.source_row_number;
