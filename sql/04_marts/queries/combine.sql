-- Temporary inputs have UNIQUE keys. Left joins retain unpriced Offtake and Unknown.
CREATE TEMP TABLE analytics_offtake_zone ON COMMIT DROP AS
SELECT o.interval_id,o.zone,sum(o.offtake_kwh) AS offtake_kwh,
 sum(CASE WHEN p.dollars_per_mwh IS NOT NULL THEN o.offtake_kwh ELSE 0 END) AS priced_offtake_kwh,
 sum(CASE WHEN p.dollars_per_mwh IS NOT NULL THEN p.dollars_per_mwh*o.offtake_kwh ELSE 0 END) AS price_numerator,
 sum(o.source_rows)::bigint AS offtake_source_rows,count(*) AS offtake_poc_zone_rows
FROM analytics_offtake_poc o LEFT JOIN analytics_price p USING(interval_id,poc)
GROUP BY o.interval_id,o.zone;
CREATE UNIQUE INDEX ON analytics_offtake_zone(interval_id,zone);

-- National is aggregated across ALL Zones, including Unknown, before any filtering.
WITH zones AS (
 SELECT coalesce(o.interval_id,g.interval_id) AS interval_id,coalesce(o.zone,g.zone) AS zone,
 o.offtake_kwh,o.priced_offtake_kwh,o.price_numerator,o.offtake_source_rows,o.offtake_poc_zone_rows,
 g.source_rows AS generation_source_rows,g.generation_kwh,g.renewable_kwh,g.fossil_kwh,g.storage_kwh,g.unclassified_kwh,
 CASE WHEN o.zone<>'Unknown' THEN o.offtake_kwh ELSE 0 END AS known_zone_offtake_kwh,
 CASE WHEN g.zone<>'Unknown' THEN g.generation_kwh ELSE 0 END AS known_zone_generation_kwh
 FROM analytics_offtake_zone o FULL JOIN analytics_generation g USING(interval_id,zone)
), totals AS (
 SELECT 'Zone' AS scope,z.* FROM zones z
 UNION ALL
 SELECT 'National',interval_id,'National',sum(offtake_kwh),sum(priced_offtake_kwh),sum(price_numerator),
 sum(offtake_source_rows)::bigint,sum(offtake_poc_zone_rows)::bigint,sum(generation_source_rows)::bigint,
 sum(generation_kwh),sum(renewable_kwh),sum(fossil_kwh),sum(storage_kwh),sum(unclassified_kwh),
 sum(known_zone_offtake_kwh),sum(known_zone_generation_kwh)
 FROM zones GROUP BY interval_id
)
INSERT INTO analytics._interval_cache
SELECT t.scope,t.zone,t.interval_id,i.trading_date,i.trading_period,i.start_utc,i.end_utc,
 i.local_start,i.local_end,d.expected_periods,
 t.offtake_kwh,t.priced_offtake_kwh,t.price_numerator,t.offtake_source_rows,t.offtake_poc_zone_rows,
 t.generation_source_rows,t.generation_kwh,t.renewable_kwh,t.fossil_kwh,t.storage_kwh,t.unclassified_kwh,
 t.known_zone_offtake_kwh,t.known_zone_generation_kwh
FROM totals t JOIN core.dim_trading_interval i USING(interval_id) JOIN core.dim_date d USING(trading_date);
