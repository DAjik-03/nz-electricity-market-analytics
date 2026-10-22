-- Each National/Zone event is joined to National context once per UTC interval.
-- Annual demand percentile is cume_dist; event statistic is mean interval rank,
-- not the percentile of an event aggregate. Regional flags use each Zone's own P99.
-- name: event_investigation
WITH n AS MATERIALIZED (
 SELECT *,100*cume_dist() OVER(ORDER BY demand_mw) AS annual_demand_percentile
 FROM analytics.mart_market_interval_national
), z AS MATERIALIZED (
 SELECT interval_id,count(*) FILTER(WHERE is_price_pressure) AS zones_flagged,
 string_agg(zone,',' ORDER BY zone) FILTER(WHERE is_price_pressure) AS flagged_zones
 FROM analytics.mart_market_interval_zone WHERE zone IN ('CNI','LNI','LSI','UNI','USI') GROUP BY interval_id
)
SELECT e.event_id,e.scope,e.zone,e.local_start,e.local_end,e.start_utc,e.end_utc,e.duration_hours,e.interval_count,
 e.weighted_price,e.peak_weighted_price,e.p99_threshold,
 avg(n.demand_mw) AS national_mean_demand_mw,max(n.demand_mw) AS national_peak_demand_mw,
 avg(n.annual_demand_percentile) AS mean_annual_demand_percentile,
 sum(n.price_numerator)/sum(n.priced_offtake_kwh) AS national_weighted_price,
 max(n.weighted_price) AS national_peak_price,
 avg(n.regional_price_spread) AS mean_spread,max(n.regional_price_spread) AS max_spread,
 count(n.regional_price_spread) AS complete_spread_intervals,
 min(z.zones_flagged) AS minimum_zones_flagged,max(z.zones_flagged) AS maximum_zones_flagged,
 string_agg(DISTINCT z.flagged_zones,'; ' ORDER BY z.flagged_zones) AS zone_combinations,
 count(*) FILTER(WHERE n.is_price_pressure) AS national_pressure_intervals,
 avg(n.generation_kwh)/1000 AS national_mean_listed_mwh,
 avg(n.storage_kwh)/1000 AS national_mean_storage_mwh,
 avg(n.unclassified_kwh)/1000 AS national_mean_unclassified_mwh,
 100*sum(n.renewable_kwh)/sum(n.renewable_kwh+n.fossil_kwh) AS national_renewable_primary_pct,
 100*sum(n.generation_kwh-n.unclassified_kwh)/sum(n.generation_kwh) AS national_classification_pct,
 100*sum(n.priced_offtake_kwh)/sum(n.offtake_kwh) AS price_coverage_pct,
 100*sum(n.known_zone_offtake_kwh)/sum(n.offtake_kwh) AS offtake_zone_coverage_pct,
 100*sum(n.known_zone_generation_kwh)/sum(n.generation_kwh) AS generation_zone_coverage_pct
FROM analytics.mart_price_pressure_event e JOIN n ON n.start_utc>=e.start_utc AND n.start_utc<e.end_utc
JOIN z USING(interval_id)
GROUP BY e.event_id,e.scope,e.zone,e.local_start,e.local_end,e.start_utc,e.end_utc,e.duration_hours,e.interval_count,
 e.weighted_price,e.peak_weighted_price,e.p99_threshold ORDER BY e.start_utc,e.scope,e.zone;
