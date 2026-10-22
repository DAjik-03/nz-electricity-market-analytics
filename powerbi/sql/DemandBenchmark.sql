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
