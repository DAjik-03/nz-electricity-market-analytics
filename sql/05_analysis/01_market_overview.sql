-- Approved marts only; monthly components retain native denominators.
-- name: monthly_overview
SELECT m.*,100*m.fossil_thermal_gwh/nullif(m.renewable_gwh+m.fossil_thermal_gwh,0) AS fossil_primary_share_pct,
 100*m.storage_gwh/nullif(m.listed_generation_gwh,0) AS storage_listed_share_pct,
 100*m.unclassified_gwh/nullif(m.listed_generation_gwh,0) AS unclassified_listed_share_pct,
 d.mean_spread,d.p95_spread,d.spread_intervals
FROM analytics.mart_market_monthly m
JOIN (SELECT date_trunc('month',trading_date)::date AS source_month,
 avg(regional_price_spread) AS mean_spread,
 percentile_cont(.95) WITHIN GROUP(ORDER BY regional_price_spread) AS p95_spread,
 count(regional_price_spread) AS spread_intervals
 FROM analytics.mart_market_interval_national GROUP BY 1) d USING(source_month)
WHERE m.scope='National' ORDER BY source_month;

-- name: release_population
SELECT scope,zone,count(*) AS intervals,count(DISTINCT interval_id) AS distinct_intervals,
 min(trading_date) AS first_date,max(trading_date) AS last_date,
 count(weighted_price) AS priced_intervals,
 sum(price_numerator)/sum(priced_offtake_kwh) AS weighted_price,
 sum(offtake_kwh)/1000000 AS demand_gwh,
 sum(generation_kwh)/1000000 AS generation_gwh,
 min(price_weighting_coverage_pct) AS minimum_price_coverage,
 count(*) FILTER(WHERE is_price_pressure) AS pressure_intervals
FROM analytics.mart_market_interval GROUP BY scope,zone ORDER BY scope,zone;
