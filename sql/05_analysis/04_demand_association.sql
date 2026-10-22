-- All comparisons are descriptive. National includes Unknown Offtake.
-- name: demand_comparison
SELECT is_price_pressure,count(*) AS intervals,avg(demand_mw) AS mean_demand_mw,
 percentile_cont(.5) WITHIN GROUP(ORDER BY demand_mw) AS median_demand_mw,
 percentile_cont(.95) WITHIN GROUP(ORDER BY demand_mw) AS p95_demand_mw,max(demand_mw) AS peak_demand_mw
FROM analytics.mart_market_interval_national GROUP BY is_price_pressure ORDER BY is_price_pressure;

-- name: demand_within_month
SELECT date_trunc('month',trading_date)::date AS month,is_price_pressure,count(*) AS intervals,
 avg(demand_mw) AS mean_demand_mw,percentile_cont(.5) WITHIN GROUP(ORDER BY demand_mw) AS median_demand_mw
FROM analytics.mart_market_interval_national GROUP BY 1,2 ORDER BY 1,2;

-- Pressure-weighted comparator: mean of non-pressure intervals in the same
-- local month AND hour. This is stratification, not causal matching; no date/weather control.
-- name: demand_hour_adjusted
WITH base AS MATERIALIZED (
 SELECT *,date_trunc('month',trading_date)::date AS month,extract(hour FROM local_start)::int AS hour
 FROM analytics.mart_market_interval_national
), control AS (
 SELECT month,hour,count(*) AS control_n,avg(demand_mw) AS control_mean FROM base
 WHERE NOT is_price_pressure GROUP BY month,hour
)
SELECT count(*) AS pressure_intervals,count(c.control_mean) AS matched_intervals,min(control_n) AS minimum_control_n,
 avg(p.demand_mw) AS pressure_mean_mw,avg(c.control_mean) AS matched_control_mean_mw,
 avg(p.demand_mw-c.control_mean) AS mean_difference_mw,
 100*(avg(p.demand_mw)/avg(c.control_mean)-1) AS difference_pct
FROM base p LEFT JOIN control c USING(month,hour) WHERE p.is_price_pressure;
