SELECT scope,zone,p99_price,population_intervals,
 first_start_utc AT TIME ZONE 'UTC' AS first_start_utc,
 last_end_utc AT TIME ZONE 'UTC' AS last_end_utc,percentile,comparison
FROM analytics.mart_price_pressure_threshold;
