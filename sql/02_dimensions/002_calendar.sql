CREATE FUNCTION core.ensure_calendar(month_start date) RETURNS void LANGUAGE plpgsql AS $$
BEGIN
 IF extract(day FROM month_start)<>1 THEN RAISE EXCEPTION 'Expected month start'; END IF;
 INSERT INTO core.dim_date
 SELECT d::date, extract(year FROM d), extract(month FROM d),
   extract(epoch FROM (((d::date+1)::timestamp AT TIME ZONE 'Pacific/Auckland')-
                       (d::timestamp AT TIME ZONE 'Pacific/Auckland')))/1800
 FROM generate_series(month_start::timestamp,month_start+interval '1 month - 1 day',interval '1 day') d
 ON CONFLICT DO NOTHING;

 INSERT INTO core.dim_trading_interval
 (trading_date,trading_period,start_utc,end_utc,local_start,local_end,
  utc_offset_minutes,end_utc_offset_minutes,is_dst,end_is_dst,fold,end_fold,timezone)
 WITH instants AS (
   SELECT d.trading_date,t.u,t.u+interval '30 minutes' AS e,
     row_number() OVER (PARTITION BY d.trading_date ORDER BY t.u) AS tp
   FROM core.dim_date d
   CROSS JOIN LATERAL generate_series(d.trading_date::timestamp AT TIME ZONE 'Pacific/Auckland',
       (d.trading_date+1)::timestamp AT TIME ZONE 'Pacific/Auckland'-interval '30 minutes',interval '30 minutes') t(u)
   WHERE d.trading_date>=month_start AND d.trading_date<month_start+interval '1 month'
 ), offsets AS (
   SELECT *,u AT TIME ZONE 'Pacific/Auckland' AS ls,e AT TIME ZONE 'Pacific/Auckland' AS le,
     extract(epoch FROM ((u AT TIME ZONE 'Pacific/Auckland')-(u AT TIME ZONE 'UTC')))/60 AS off,
     extract(epoch FROM ((e AT TIME ZONE 'Pacific/Auckland')-(e AT TIME ZONE 'UTC')))/60 AS endoff
   FROM instants
 )
 SELECT trading_date,tp,u,e,ls,le,off,endoff,off=780,endoff=780,
   CASE WHEN (u-interval '1 hour') AT TIME ZONE 'Pacific/Auckland'=ls THEN 1 ELSE 0 END,
   CASE WHEN (e-interval '1 hour') AT TIME ZONE 'Pacific/Auckland'=le THEN 1 ELSE 0 END,'Pacific/Auckland'
 FROM offsets ON CONFLICT (trading_date,trading_period) DO NOTHING;
END $$;
