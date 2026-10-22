SELECT interval_id,trading_date,trading_period,
 start_utc AT TIME ZONE 'UTC' AS start_utc,end_utc AT TIME ZONE 'UTC' AS end_utc,
 local_start,local_end,expected_periods,extract(hour FROM local_start)::int AS local_hour,
 extract(epoch FROM (local_start-(start_utc AT TIME ZONE 'UTC')))::int/60 AS utc_offset_minutes,
 (extract(epoch FROM (local_start-(start_utc AT TIME ZONE 'UTC')))::int=46800) AS is_dst,
 (row_number() OVER(PARTITION BY local_start ORDER BY start_utc)-1)::int AS fold
FROM analytics.mart_market_interval_national;
