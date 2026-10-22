-- Transaction-local profiles avoid repeating the largest scans for every rule.
CREATE FUNCTION quality.prepare_profiles() RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 CREATE TEMP TABLE dq_population ON COMMIT DROP AS
 SELECT 'prices'::text source,publication_id,''::text flow,count(*) rows,sum(dollars_per_mwh) total
 FROM quality.input_price GROUP BY publication_id
 UNION ALL SELECT 'reconciliation',publication_id,flow_direction,count(*),sum(kilowatt_hours)
 FROM quality.input_volume GROUP BY publication_id,flow_direction
 UNION ALL SELECT 'generation',publication_id,'',count(*),sum(kilowatt_hours)
 FROM quality.input_generation GROUP BY publication_id;

 CREATE TEMP TABLE dq_stage ON COMMIT DROP AS
 SELECT 'prices'::text source,publication_id,''::text flow,count(*) rows,count(*) normalised_rows,
 sum(quality.number("DollarsPerMegawattHour")) total
 FROM staging.final_energy_price GROUP BY publication_id
 UNION ALL SELECT 'reconciliation',publication_id,"FlowDirection",count(*),count(*),sum(quality.number("KilowattHours"))
 FROM staging.reconciled_volume GROUP BY publication_id,"FlowDirection"
 UNION ALL SELECT 'generation',s.publication_id,'',count(DISTINCT source_row_number),count(v.value),sum(quality.number(v.value))
 FROM staging.generation_daily s CROSS JOIN LATERAL jsonb_each_text(to_jsonb(s)) v
 WHERE v.key ~ '^TP[0-9]+$' GROUP BY s.publication_id
 UNION ALL SELECT 'nsp',publication_id,'',count(*),count(*),NULL::numeric
 FROM staging.network_supply_point GROUP BY publication_id;

 CREATE TEMP TABLE dq_period ON COMMIT DROP AS
 SELECT 'prices'::text source,publication_id,interval_id,count(*) rows FROM quality.input_price GROUP BY 2,3
 UNION ALL SELECT 'reconciliation',publication_id,interval_id,count(*) FROM quality.input_volume GROUP BY 2,3
 UNION ALL SELECT 'generation',publication_id,interval_id,count(*) FROM quality.input_generation GROUP BY 2,3;

 CREATE TEMP TABLE dq_mapping ON COMMIT DROP AS
 SELECT 'reconciliation'::text source,f.publication_id,f.interval_id,f.connection_id,
 f.nsp_snapshot_publication_id,f.nsp_version_id,f.mapping_status,f.flow_direction AS flow,
 f.island_original,count(*) rows,sum(f.kilowatt_hours) kwh
 FROM quality.input_volume f JOIN metadata.publication_selection s USING(publication_id)
 WHERE s.source_name='reconciliation' GROUP BY 2,3,4,5,6,7,8,9
 UNION ALL SELECT 'generation',f.publication_id,f.interval_id,f.connection_id,
 f.nsp_snapshot_publication_id,f.nsp_version_id,f.mapping_status,'','',count(*),sum(f.kilowatt_hours)
 FROM quality.input_generation f JOIN metadata.publication_selection s USING(publication_id)
 WHERE s.source_name='generation' GROUP BY 2,3,4,5,6,7;
 ANALYZE dq_mapping;

 CREATE TEMP TABLE dq_expected_interval ON COMMIT DROP AS
 WITH months AS (SELECT DISTINCT source_month FROM quality.expected_publication WHERE source_name<>'nsp'),
 days AS (SELECT d::date trading_date FROM months CROSS JOIN LATERAL
 generate_series(source_month,source_month+interval '1 month'-interval '1 day',interval '1 day') d)
 SELECT trading_date,row_number() OVER (PARTITION BY trading_date ORDER BY t)::int trading_period,
 t AS start_utc,t+interval '30 minutes' AS end_utc
 FROM days CROSS JOIN LATERAL generate_series(trading_date::timestamp AT TIME ZONE 'Pacific/Auckland',
 (trading_date+1)::timestamp AT TIME ZONE 'Pacific/Auckland'-interval '30 minutes',interval '30 minutes') t;

 CREATE TEMP TABLE dq_nsp_edges ON COMMIT DROP AS
 SELECT n.*,lead(valid_from_utc) OVER (PARTITION BY publication_id,nsp ORDER BY valid_from_utc) next_start
 FROM quality.input_nsp n WHERE boundary_status<>'invalid_boundary';

 CREATE TEMP TABLE dq_series ON COMMIT DROP AS
 SELECT f.publication_id,p.source_month,f.generator_id,f.connection_id,g.gen_code,c.poc,c.network,
 count(*) intervals,count(DISTINCT i.trading_date) observed_days,min(i.trading_date) first_date,max(i.trading_date) last_date,
 bool_and(f.kilowatt_hours=0) all_zero,sum(f.kilowatt_hours) kwh,
 extract(day FROM p.source_month+interval '1 month'-interval '1 day')::int expected_days
 FROM quality.input_generation f JOIN metadata.publication_selection s USING(publication_id)
 JOIN metadata.source_publication p USING(publication_id) JOIN quality.input_interval i USING(interval_id)
 JOIN core.dim_generator g USING(generator_id) JOIN core.dim_connection c USING(connection_id)
 WHERE s.source_name='generation' GROUP BY 1,2,3,4,5,6,7;

 -- A price geography diagnostic only: unanimous non-null Zone across all
 -- effective candidates. Multiple candidates are counted, never multiplied into price rows.
 CREATE TEMP TABLE dq_price_geo ON COMMIT DROP AS
 SELECT f.publication_id,f.interval_id,f.pricing_node_id,count(n.nsp_version_id) matches,
 CASE WHEN count(n.nsp_version_id)>0 AND count(n.zone)=count(n.nsp_version_id)
 AND count(DISTINCT n.zone)=1 THEN min(n.zone) ELSE 'Unknown' END zone
 FROM quality.input_price f JOIN metadata.publication_selection s USING(publication_id)
 JOIN quality.input_interval i USING(interval_id) JOIN core.dim_pricing_node p USING(pricing_node_id)
 LEFT JOIN core.dim_connection c ON c.poc=p.pricing_poc
 LEFT JOIN quality.input_nsp n ON n.connection_id=c.connection_id
 AND n.publication_id=(SELECT publication_id FROM metadata.publication_selection WHERE source_name='nsp')
 AND n.boundary_status<>'invalid_boundary' AND i.start_utc>=n.valid_from_utc
 AND (n.boundary_status='valid_open' OR i.start_utc<n.valid_to_utc_exclusive)
 WHERE s.source_name='prices' GROUP BY 1,2,3;

 CREATE TEMP TABLE dq_coverage ON COMMIT DROP AS
 SELECT 'prices'::text source_name,p.source_month,'price rows'::text denominator_unit,
 count(*)::numeric total_value,count(*) FILTER (WHERE f.zone<>'Unknown')::numeric known_value,
 count(*) FILTER (WHERE f.zone='Unknown')::numeric unknown_value
 FROM dq_price_geo f JOIN metadata.source_publication p USING(publication_id) GROUP BY 2
 UNION ALL
 SELECT CASE f.source WHEN 'reconciliation' THEN 'reconciliation_offtake' ELSE 'generation' END,
 p.source_month,'kWh',sum(f.kwh),coalesce(sum(f.kwh) FILTER (WHERE n.zone IS NOT NULL),0),
 coalesce(sum(f.kwh) FILTER (WHERE n.zone IS NULL),0)
 FROM dq_mapping f JOIN metadata.source_publication p USING(publication_id)
 LEFT JOIN quality.input_nsp n ON n.nsp_version_id=f.nsp_version_id AND n.publication_id=f.nsp_snapshot_publication_id
 WHERE (f.source='generation' OR f.flow='Offtake') GROUP BY 1,2;
END $$;
