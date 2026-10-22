WITH flags AS (
 SELECT interval_id,min(start_utc) AS start_utc,max(end_utc) AS end_utc,
 count(*) FILTER(WHERE is_price_pressure)::int AS zones_flagged
 FROM analytics.mart_market_interval_zone
 WHERE zone IN ('CNI','LNI','LSI','UNI','USI') GROUP BY interval_id
), marked AS (
 SELECT *,CASE WHEN lag(end_utc) OVER(ORDER BY start_utc)=start_utc THEN 0 ELSE 1 END AS begins
 FROM flags WHERE zones_flagged>0
), episodes AS (
 SELECT interval_id,sum(begins) OVER(ORDER BY start_utc)::bigint AS episode_id FROM marked
)
SELECT f.interval_id,f.zones_flagged,e.episode_id,
 f.zones_flagged>0 AND NOT n.is_price_pressure AS zone_only
FROM flags f LEFT JOIN episodes e USING(interval_id)
JOIN analytics.mart_market_interval_national n USING(interval_id);
