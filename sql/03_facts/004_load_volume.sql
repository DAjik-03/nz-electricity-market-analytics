CREATE FUNCTION core.load_volume(pid bigint,snapshot_pid bigint) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE total bigint; expected bigint; month_start date;
BEGIN
 SELECT source_month INTO STRICT month_start FROM metadata.source_publication WHERE publication_id=pid AND source_name='reconciliation';
 PERFORM core.ensure_calendar(month_start);
 PERFORM set_config('warehouse.publication_id',pid::text,true);
 CREATE TEMP VIEW load_rows AS
 SELECT publication_id,source_row_number,"TradingDate"::date AS trading_date,"TradingPeriod"::integer AS trading_period,
   "PointOfConnection" AS poc,"Network" AS network,"Participant" AS participant,
   "FlowDirection" AS flow,"Island" AS island,"TradingPeriodStartTime" AS label,"KilowattHours"::numeric AS kwh
 FROM staging.reconciled_volume WHERE publication_id=current_setting('warehouse.publication_id')::bigint;
 IF EXISTS (SELECT 1 FROM load_rows WHERE trading_date<month_start OR trading_date>=month_start+interval '1 month') THEN
   RAISE EXCEPTION 'Volume date outside source month';
 END IF;
 INSERT INTO core.dim_connection(poc,network) SELECT DISTINCT poc,network FROM load_rows ON CONFLICT DO NOTHING;
 INSERT INTO core.dim_participant(participant_code) SELECT DISTINCT participant FROM load_rows ON CONFLICT DO NOTHING;
 PERFORM core.prepare_load_mapping(snapshot_pid);
 IF EXISTS (SELECT 1 FROM load_rows s JOIN core.dim_trading_interval i USING(trading_date,trading_period)
            WHERE s.label<>to_char(i.local_start,'HH24:MI') OR s.label IS NULL) THEN
   RAISE EXCEPTION 'Reconciliation local clock label disagrees with NZ calendar';
 END IF;
 INSERT INTO core.fact_reconciled_volume
 (publication_id,interval_id,connection_id,participant_id,flow_direction,source_row_number,island_original,
 local_start_label,kilowatt_hours,nsp_snapshot_publication_id,nsp_version_id,mapping_status)
 SELECT s.publication_id,i.interval_id,c.connection_id,p.participant_id,s.flow,s.source_row_number,s.island,
   s.label,s.kwh,snapshot_pid,m.nsp_version_id,m.mapping_status
 FROM load_rows s JOIN core.dim_trading_interval i USING(trading_date,trading_period)
 JOIN core.dim_connection c USING(poc,network)
 JOIN core.dim_participant p ON p.participant_code=s.participant
 JOIN load_mapping m USING(interval_id,connection_id);
 GET DIAGNOSTICS total = ROW_COUNT;
 SELECT count(*) INTO expected FROM load_rows;
 IF total<>expected THEN RAISE EXCEPTION 'Invalid volume intervals or lost source rows'; END IF;
 DROP VIEW load_rows;
 RETURN total;
END $$;
