-- load_rows is a publication-scoped temporary SQL view created by the fact loader.
-- Resolve once per observed connection/interval, not once per participant row.
CREATE FUNCTION core.prepare_load_mapping(snapshot_pid bigint) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM metadata.source_publication WHERE publication_id=snapshot_pid AND source_name='nsp' AND status='loaded') THEN
   RAISE EXCEPTION 'NSP snapshot is not loaded';
 END IF;
 CREATE TEMP TABLE load_mapping ON COMMIT DROP AS
 WITH observed AS (
   SELECT DISTINCT trading_date,trading_period,poc,network FROM load_rows
 ), candidates AS (
   SELECT i.interval_id,c.connection_id,n.nsp_version_id
   FROM observed o
   JOIN core.dim_trading_interval i USING (trading_date,trading_period)
   JOIN core.dim_connection c USING (poc,network)
   LEFT JOIN core.dim_nsp_version n ON n.connection_id=c.connection_id
     AND n.publication_id=snapshot_pid AND n.boundary_status<>'invalid_boundary'
     AND i.start_utc>=n.valid_from_utc
     AND (n.boundary_status='valid_open' OR i.start_utc<n.valid_to_utc_exclusive)
 )
 SELECT interval_id,connection_id,
   CASE WHEN count(nsp_version_id)=1 THEN min(nsp_version_id) END AS nsp_version_id,
   CASE count(nsp_version_id) WHEN 0 THEN 'unmapped' WHEN 1 THEN 'mapped' ELSE 'ambiguous' END AS mapping_status
 FROM candidates GROUP BY interval_id,connection_id;
 CREATE UNIQUE INDEX ON load_mapping(interval_id,connection_id);
 ANALYZE load_mapping;
END $$;
