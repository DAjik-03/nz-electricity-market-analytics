CREATE FUNCTION core.load_nsp(pid bigint) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE total bigint;
BEGIN
 INSERT INTO core.dim_connection(poc,network)
 SELECT DISTINCT "POC code","Network participant" FROM staging.network_supply_point
 WHERE publication_id=pid ON CONFLICT DO NOTHING;

 INSERT INTO core.dim_nsp_version
 (publication_id,source_row_number,nsp,connection_id,original_start_date,original_start_tp,
 original_end_date,original_end_tp,zone,island,network_reporting_region_id,network_reporting_region,
 parent_poc,parent_network,source_metadata,valid_from_utc,valid_to_utc_exclusive,boundary_status,exception_reason)
 WITH boundaries AS (
   SELECT s.*,c.connection_id,core.tp_start("Start date"::date,"Start TP"::integer) AS first_start,
      core.tp_start("End date"::date,"End TP"::integer)+interval '30 minutes' AS final_end,
      to_jsonb(s)-'publication_id'-'source_row_number' AS original_metadata
   FROM staging.network_supply_point s
   JOIN core.dim_connection c ON c.poc=s."POC code" AND c.network=s."Network participant"
   WHERE s.publication_id=pid
 ), assessed AS (
   SELECT *,CASE
     WHEN first_start IS NULL THEN 'Start TP does not exist on source date'
     WHEN ("End date" IS NULL)<>("End TP" IS NULL) THEN 'Partially null source end'
     WHEN "End date" IS NOT NULL AND final_end IS NULL THEN 'End TP does not exist on source date'
     WHEN final_end<=first_start THEN 'End precedes start'
     ELSE NULL END AS reason
   FROM boundaries
 )
 SELECT publication_id,source_row_number,"NSP",connection_id,"Start date","Start TP","End date","End TP",
   "Zone","Island","Network reporting region ID","Network reporting region",
   "Embedded under POC code","Embedded under network participant",original_metadata,
   CASE WHEN reason IS NULL THEN first_start END,CASE WHEN reason IS NULL THEN final_end END,
   CASE WHEN reason IS NOT NULL THEN 'invalid_boundary' WHEN "End date" IS NULL THEN 'valid_open' ELSE 'valid_bounded' END,reason
 FROM assessed;
 GET DIAGNOSTICS total = ROW_COUNT;
 -- Overlap is tested without treating invalid histories as open-ended.
 IF EXISTS (SELECT 1 FROM (
   SELECT valid_to_utc_exclusive,lead(valid_from_utc) OVER (PARTITION BY nsp ORDER BY valid_from_utc) next_start
   FROM core.dim_nsp_version WHERE publication_id=pid AND boundary_status<>'invalid_boundary'
 ) v WHERE next_start IS NOT NULL AND (valid_to_utc_exclusive IS NULL OR valid_to_utc_exclusive>next_start)) THEN
   RAISE EXCEPTION 'Overlapping valid NSP histories';
 END IF;
 RETURN total;
END $$;
