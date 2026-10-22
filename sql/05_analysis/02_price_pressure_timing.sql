-- National events and intervals are different populations. Month/hour uses interval start.
-- name: national_event_distribution
SELECT count(*) AS events,sum(interval_count) AS intervals,sum(duration_hours) AS hours,
 count(*) FILTER(WHERE interval_count=1) AS isolated_events,
 percentile_cont(ARRAY[.5,.95]) WITHIN GROUP(ORDER BY duration_hours) AS duration_p50_p95,
 max(duration_hours) AS maximum_hours,
 percentile_cont(ARRAY[.5,.95]) WITHIN GROUP(ORDER BY peak_weighted_price) AS event_peak_p50_p95,
 max(peak_weighted_price) AS maximum_price
FROM analytics.mart_price_pressure_event WHERE scope='National';

-- name: pressure_by_month
SELECT date_trunc('month',trading_date)::date AS month,count(*) AS all_intervals,
 count(*) FILTER(WHERE is_price_pressure) AS pressure_intervals,
 100.0*count(*) FILTER(WHERE is_price_pressure)/count(*) AS pressure_rate_pct
FROM analytics.mart_market_interval_national GROUP BY 1 ORDER BY 1;

-- name: pressure_by_hour
SELECT extract(hour FROM local_start)::int AS local_hour,count(*) AS all_intervals,
 count(*) FILTER(WHERE is_price_pressure) AS pressure_intervals,
 100.0*count(*) FILTER(WHERE is_price_pressure)/count(*) AS pressure_rate_pct
FROM analytics.mart_market_interval_national GROUP BY 1 ORDER BY 1;

-- name: pressure_by_day_type
SELECT CASE WHEN extract(isodow FROM trading_date)>=6 THEN 'Weekend' ELSE 'Weekday' END AS day_type,
 count(*) AS all_intervals,count(*) FILTER(WHERE is_price_pressure) AS pressure_intervals,
 100.0*count(*) FILTER(WHERE is_price_pressure)/count(*) AS pressure_rate_pct
FROM analytics.mart_market_interval_national GROUP BY 1 ORDER BY 1;

-- name: event_starts_by_month
SELECT date_trunc('month',local_start)::date AS month,count(*) AS event_starts
FROM analytics.mart_price_pressure_event WHERE scope='National' GROUP BY 1 ORDER BY 1;
