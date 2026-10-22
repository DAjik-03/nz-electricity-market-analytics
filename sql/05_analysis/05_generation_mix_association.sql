-- Absolute output is mean MWh per half-hour. Shares pool energy, not interval percentages.
-- Primary shares exclude Storage and Unclassified; listed shares include them.
-- name: generation_comparison
SELECT is_price_pressure,count(*) AS intervals,
 avg(generation_kwh)/1000 AS mean_listed_mwh,
 avg(renewable_kwh)/1000 AS mean_renewable_mwh,avg(fossil_kwh)/1000 AS mean_fossil_mwh,
 avg(storage_kwh)/1000 AS mean_storage_mwh,avg(unclassified_kwh)/1000 AS mean_unclassified_mwh,
 100*sum(renewable_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS renewable_primary_share_pct,
 100*sum(fossil_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS fossil_primary_share_pct,
 100*sum(storage_kwh)/nullif(sum(generation_kwh),0) AS storage_listed_share_pct,
 100*sum(unclassified_kwh)/nullif(sum(generation_kwh),0) AS unclassified_listed_share_pct,
 100*sum(generation_kwh-unclassified_kwh)/nullif(sum(generation_kwh),0) AS classification_coverage_pct,
 100*sum(renewable_kwh)/nullif(sum(generation_kwh),0) AS renewable_all_listed_lower_pct,
 100*sum(renewable_kwh+unclassified_kwh)/nullif(sum(generation_kwh),0) AS renewable_all_listed_upper_pct
FROM analytics.mart_market_interval_national GROUP BY is_price_pressure ORDER BY is_price_pressure;

-- Comparable month/hour strata; pool pressure and counterfactual descriptive energy separately.
-- name: generation_hour_adjusted
WITH b AS MATERIALIZED (
 SELECT *,date_trunc('month',trading_date)::date AS month,extract(hour FROM local_start)::int AS hour
 FROM analytics.mart_market_interval_national
), c AS (
 SELECT month,hour,avg(renewable_kwh) AS r,avg(fossil_kwh) AS f,avg(storage_kwh) AS s,
 avg(unclassified_kwh) AS u,avg(generation_kwh) AS g FROM b WHERE NOT is_price_pressure GROUP BY month,hour
)
SELECT count(*) AS intervals,count(c.g) AS matched_intervals,
 avg(p.generation_kwh)/1000 AS pressure_listed_mwh,avg(c.g)/1000 AS control_listed_mwh,
 avg(p.renewable_kwh)/1000 AS pressure_renewable_mwh,avg(c.r)/1000 AS control_renewable_mwh,
 avg(p.fossil_kwh)/1000 AS pressure_fossil_mwh,avg(c.f)/1000 AS control_fossil_mwh,
 avg(p.storage_kwh)/1000 AS pressure_storage_mwh,avg(c.s)/1000 AS control_storage_mwh,
 avg(p.unclassified_kwh)/1000 AS pressure_unclassified_mwh,avg(c.u)/1000 AS control_unclassified_mwh,
 100*sum(p.renewable_kwh)/sum(p.renewable_kwh+p.fossil_kwh) AS pressure_renewable_primary_pct,
 100*sum(c.r)/sum(c.r+c.f) AS control_renewable_primary_pct,
 100*sum(p.generation_kwh-p.unclassified_kwh)/sum(p.generation_kwh) AS pressure_classification_pct,
 100*sum(c.g-c.u)/sum(c.g) AS control_classification_pct
FROM b p LEFT JOIN c USING(month,hour) WHERE p.is_price_pressure;
