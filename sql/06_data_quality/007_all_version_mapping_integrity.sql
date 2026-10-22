-- Coverage concerns selected versions, but invalid mapping is forbidden in
-- every physical revision, including a retained unselected predecessor.
ALTER FUNCTION quality.prepare_profiles() RENAME TO prepare_selected_profiles;
CREATE FUNCTION quality.prepare_profiles() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 PERFORM quality.prepare_selected_profiles();
 CREATE TEMP TABLE dq_all_mapping ON COMMIT DROP AS
 SELECT * FROM dq_mapping
 UNION ALL SELECT 'reconciliation',f.publication_id,f.interval_id,f.connection_id,
 f.nsp_snapshot_publication_id,f.nsp_version_id,f.mapping_status,f.flow_direction,f.island_original,
 count(*),sum(f.kilowatt_hours)
 FROM quality.input_volume f JOIN metadata.source_publication p USING(publication_id)
 WHERE NOT EXISTS (SELECT 1 FROM metadata.publication_selection s WHERE s.publication_id=p.publication_id)
 GROUP BY 2,3,4,5,6,7,8,9
 UNION ALL SELECT 'generation',f.publication_id,f.interval_id,f.connection_id,
 f.nsp_snapshot_publication_id,f.nsp_version_id,f.mapping_status,'','',count(*),sum(f.kilowatt_hours)
 FROM quality.input_generation f JOIN metadata.source_publication p USING(publication_id)
 WHERE NOT EXISTS (SELECT 1 FROM metadata.publication_selection s WHERE s.publication_id=p.publication_id)
 GROUP BY 2,3,4,5,6,7;
 ANALYZE dq_all_mapping;
END $$;
UPDATE quality.rule SET query_sql=replace(query_sql,'FROM dq_mapping f','FROM dq_all_mapping f')
 WHERE rule_code IN ('DQ14','DQ21');
