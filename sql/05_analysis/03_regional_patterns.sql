-- name: regional_events
SELECT t.scope,t.zone,t.p99_price,t.population_intervals,count(e.event_id) AS events,
 sum(e.interval_count) AS flagged_intervals,sum(e.duration_hours) AS flagged_hours,
 percentile_cont(.5) WITHIN GROUP(ORDER BY e.duration_hours) AS median_event_hours,
 max(e.duration_hours) AS longest_event_hours,max(e.peak_weighted_price) AS peak_price
FROM analytics.mart_price_pressure_threshold t JOIN analytics.mart_price_pressure_event e USING(scope,zone)
GROUP BY t.scope,t.zone,t.p99_price,t.population_intervals ORDER BY t.scope,t.zone;

-- name: regional_overlap
WITH zones AS (
 SELECT interval_id,count(*) FILTER(WHERE is_price_pressure) AS zones_flagged
 FROM analytics.mart_market_interval_zone WHERE zone IN ('CNI','LNI','LSI','UNI','USI') GROUP BY interval_id
)
SELECT zones_flagged,n.is_price_pressure AS national_pressure,count(*) AS intervals
FROM zones JOIN analytics.mart_market_interval_national n USING(interval_id)
GROUP BY zones_flagged,n.is_price_pressure ORDER BY zones_flagged,n.is_price_pressure;

-- Analysis-only episode: contiguous UTC half-hours with >=1 known Zone flagged.
-- Adjacent flagged half-hours are grouped even when the flagged Zone changes.
-- name: cross_regional_episodes
WITH flags AS (
 SELECT interval_id,min(start_utc) AS start_utc,max(end_utc) AS end_utc,
 count(*) FILTER(WHERE is_price_pressure) AS zones_flagged
 FROM analytics.mart_market_interval_zone WHERE zone IN ('CNI','LNI','LSI','UNI','USI') GROUP BY interval_id
), marked AS (
 SELECT *,CASE WHEN lag(end_utc) OVER(ORDER BY start_utc)=start_utc THEN 0 ELSE 1 END AS begins
 FROM flags WHERE zones_flagged>0
), grouped AS (
 SELECT *,sum(begins) OVER(ORDER BY start_utc) AS episode FROM marked
)
SELECT episode,min(start_utc) AS start_utc,max(end_utc) AS end_utc,count(*) AS intervals,
 count(*)*.5 AS hours,max(zones_flagged) AS maximum_simultaneous_zones
FROM grouped GROUP BY episode ORDER BY episode;

-- Only existing five-known-Zone-complete spreads are eligible; count exclusions.
-- name: spread_comparison
WITH zones AS (
 SELECT interval_id,count(*) FILTER(WHERE is_price_pressure) AS zones_flagged
 FROM analytics.mart_market_interval_zone WHERE zone IN ('CNI','LNI','LSI','UNI','USI') GROUP BY interval_id
), population AS (
 SELECT n.*,zones_flagged FROM analytics.mart_market_interval_national n JOIN zones USING(interval_id)
), labels AS (
 SELECT 'No National pressure' AS population,* FROM population WHERE NOT is_price_pressure
 UNION ALL SELECT 'National pressure',* FROM population WHERE is_price_pressure
 UNION ALL SELECT 'Zone-only pressure',* FROM population WHERE zones_flagged>0 AND NOT is_price_pressure
 UNION ALL SELECT 'No National or Zone pressure',* FROM population WHERE zones_flagged=0 AND NOT is_price_pressure
)
SELECT population,count(*) AS intervals,count(regional_price_spread) AS complete_intervals,
 avg(regional_price_spread) AS mean_spread,
 percentile_cont(.5) WITHIN GROUP(ORDER BY regional_price_spread) AS median_spread,
 percentile_cont(.95) WITHIN GROUP(ORDER BY regional_price_spread) AS p95_spread,
 max(regional_price_spread) AS max_spread
FROM labels GROUP BY population ORDER BY population;

-- Each Zone's own pressure flag, with a same-Zone non-pressure comparison.
-- Spread still measures the common five-Zone range; groups across Zones overlap.
-- name: spread_by_zone_pressure
SELECT zone,is_price_pressure,count(*) AS intervals,count(regional_price_spread) AS complete_intervals,
 avg(regional_price_spread) AS mean_spread,
 percentile_cont(.5) WITHIN GROUP(ORDER BY regional_price_spread) AS median_spread,
 percentile_cont(.95) WITHIN GROUP(ORDER BY regional_price_spread) AS p95_spread,
 max(regional_price_spread) AS max_spread
FROM analytics.mart_market_interval_zone WHERE zone IN ('CNI','LNI','LSI','UNI','USI')
GROUP BY zone,is_price_pressure ORDER BY zone,is_price_pressure;
