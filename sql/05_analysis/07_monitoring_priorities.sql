-- Saved review extract permits independent recomputation without repeating warehouse queries.
-- No raw participant/POC data exported. National grain exactly one half-hour.
-- name: national_intervals
SELECT * FROM analytics.mart_market_interval_national ORDER BY start_utc;

-- name: zone_flags
SELECT interval_id,start_utc,zone,weighted_price,p99_price,is_price_pressure
FROM analytics.mart_market_interval_zone WHERE zone IN ('CNI','LNI','LSI','UNI','USI') ORDER BY start_utc,zone;

-- name: monthly_quality
SELECT * FROM analytics.mart_source_quality ORDER BY source_name,source_month;
