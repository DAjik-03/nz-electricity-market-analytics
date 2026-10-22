CREATE FUNCTION core.load_price(pid bigint) RETURNS bigint LANGUAGE plpgsql AS $$
DECLARE total bigint; expected bigint; month_start date;
BEGIN
 SELECT source_month INTO STRICT month_start FROM metadata.source_publication WHERE publication_id=pid AND source_name='prices';
 PERFORM core.ensure_calendar(month_start);
 IF EXISTS (SELECT 1 FROM staging.final_energy_price WHERE publication_id=pid
   AND ("TradingDate"::date<month_start OR "TradingDate"::date>=month_start+interval '1 month')) THEN
   RAISE EXCEPTION 'Price date outside source month';
 END IF;
 INSERT INTO core.dim_pricing_node(pricing_poc)
 SELECT DISTINCT "PointOfConnection" FROM staging.final_energy_price WHERE publication_id=pid ON CONFLICT DO NOTHING;
 INSERT INTO core.fact_price
 SELECT s.publication_id,i.interval_id,n.pricing_node_id,s.source_row_number,s."DollarsPerMegawattHour"::numeric
 FROM staging.final_energy_price s
 JOIN core.dim_trading_interval i ON i.trading_date=s."TradingDate"::date AND i.trading_period=s."TradingPeriod"::integer
 JOIN core.dim_pricing_node n ON n.pricing_poc=s."PointOfConnection"
 WHERE s.publication_id=pid;
 GET DIAGNOSTICS total = ROW_COUNT;
 SELECT count(*) INTO expected FROM staging.final_energy_price WHERE publication_id=pid;
 IF total<>expected THEN RAISE EXCEPTION 'Invalid price intervals or lost source rows'; END IF;
 RETURN total;
END $$;
