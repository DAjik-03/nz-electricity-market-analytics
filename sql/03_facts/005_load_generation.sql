CREATE FUNCTION core.load_generation(pid bigint,snapshot_pid bigint) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE total bigint; expected bigint; month_start date;
BEGIN
 SELECT source_month INTO STRICT month_start FROM metadata.source_publication WHERE publication_id=pid AND source_name='generation';
 PERFORM core.ensure_calendar(month_start);
 PERFORM set_config('warehouse.publication_id',pid::text,true);
 CREATE TEMP VIEW load_generation_unpivot AS
 SELECT s.publication_id,s.source_row_number,s."Trading_Date"::date AS trading_date,v.tp AS trading_period,
   s."POC_Code" AS poc,s."Nwk_Code" AS network,s."Gen_Code" AS gen_code,
   s."Site_Code" AS site_code,s."Fuel_Code" AS fuel_code,s."Tech_Code" AS tech_code,v.kwh::numeric AS kwh
 FROM staging.generation_daily s CROSS JOIN LATERAL (VALUES
      (1,s."TP1"),
      (2,s."TP2"),
      (3,s."TP3"),
      (4,s."TP4"),
      (5,s."TP5"),
      (6,s."TP6"),
      (7,s."TP7"),
      (8,s."TP8"),
      (9,s."TP9"),
      (10,s."TP10"),
      (11,s."TP11"),
      (12,s."TP12"),
      (13,s."TP13"),
      (14,s."TP14"),
      (15,s."TP15"),
      (16,s."TP16"),
      (17,s."TP17"),
      (18,s."TP18"),
      (19,s."TP19"),
      (20,s."TP20"),
      (21,s."TP21"),
      (22,s."TP22"),
      (23,s."TP23"),
      (24,s."TP24"),
      (25,s."TP25"),
      (26,s."TP26"),
      (27,s."TP27"),
      (28,s."TP28"),
      (29,s."TP29"),
      (30,s."TP30"),
      (31,s."TP31"),
      (32,s."TP32"),
      (33,s."TP33"),
      (34,s."TP34"),
      (35,s."TP35"),
      (36,s."TP36"),
      (37,s."TP37"),
      (38,s."TP38"),
      (39,s."TP39"),
      (40,s."TP40"),
      (41,s."TP41"),
      (42,s."TP42"),
      (43,s."TP43"),
      (44,s."TP44"),
      (45,s."TP45"),
      (46,s."TP46"),
      (47,s."TP47"),
      (48,s."TP48"),
      (49,s."TP49"),
      (50,s."TP50")
 ) v(tp,kwh)
 WHERE s.publication_id=current_setting('warehouse.publication_id')::bigint;
 IF EXISTS (SELECT 1 FROM load_generation_unpivot WHERE trading_date<month_start OR trading_date>=month_start+interval '1 month') THEN
   RAISE EXCEPTION 'Generation date outside source month';
 END IF;
 IF EXISTS (SELECT 1 FROM load_generation_unpivot s LEFT JOIN core.dim_trading_interval i USING(trading_date,trading_period)
     WHERE (i.interval_id IS NULL AND s.kwh IS NOT NULL) OR (i.interval_id IS NOT NULL AND s.kwh IS NULL)) THEN
   RAISE EXCEPTION 'Invalid generation structural padding or null valid TP';
 END IF;
 CREATE TEMP VIEW load_rows AS SELECT s.* FROM load_generation_unpivot s
 JOIN core.dim_trading_interval i USING(trading_date,trading_period);
 INSERT INTO core.dim_connection(poc,network) SELECT DISTINCT poc,network FROM load_rows ON CONFLICT DO NOTHING;
 INSERT INTO core.dim_generator(gen_code) SELECT DISTINCT gen_code FROM load_rows ON CONFLICT DO NOTHING;
 PERFORM core.prepare_load_mapping(snapshot_pid);
 INSERT INTO core.fact_generation_connection
 (publication_id,interval_id,generator_id,connection_id,source_row_number,source_tp,site_code,fuel_code,tech_code,
 kilowatt_hours,nsp_snapshot_publication_id,nsp_version_id,mapping_status)
 SELECT s.publication_id,i.interval_id,g.generator_id,c.connection_id,s.source_row_number,s.trading_period,
   s.site_code,s.fuel_code,s.tech_code,s.kwh,snapshot_pid,m.nsp_version_id,m.mapping_status
 FROM load_rows s JOIN core.dim_trading_interval i USING(trading_date,trading_period)
 JOIN core.dim_connection c USING(poc,network) JOIN core.dim_generator g USING(gen_code)
 JOIN load_mapping m USING(interval_id,connection_id);
 GET DIAGNOSTICS total = ROW_COUNT;
 SELECT count(*) INTO expected FROM load_rows;
 IF total<>expected THEN RAISE EXCEPTION 'Lost generation rows'; END IF;
 DROP VIEW load_rows;
 DROP VIEW load_generation_unpivot;
 RETURN total;
END $$;
