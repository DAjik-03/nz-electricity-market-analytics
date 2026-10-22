-- Additive continuous-release configuration; original seven-day contract remains.
UPDATE analytics.configuration SET pilot_months=ARRAY(
 SELECT m::date FROM generate_series(date '2025-09-01',date '2026-08-01',interval '1 month') m);

CREATE VIEW analytics.mart_market_daily_rolling_30d AS
WITH previous AS (
 SELECT d.*,lag(trading_date) OVER w AS previous_date,lag(weighted_price) OVER w AS previous_price,
 lag(demand_gwh) OVER w AS previous_demand_gwh
 FROM analytics.mart_market_daily d WINDOW w AS (PARTITION BY scope,zone ORDER BY trading_date)
), blocks AS (
 SELECT p.*,sum(CASE WHEN previous_date=trading_date-1 THEN 0 ELSE 1 END)
 OVER(PARTITION BY scope,zone ORDER BY trading_date ROWS UNBOUNDED PRECEDING) AS contiguous_block,
 CASE WHEN previous_date=trading_date-1 THEN weighted_price-previous_price END AS price_change_previous_day,
 CASE WHEN previous_date=trading_date-1 THEN demand_gwh-previous_demand_gwh END AS demand_change_previous_day_gwh
 FROM previous p
), windows AS (
 SELECT b.*,count(*) OVER w AS rolling_days,
 bool_and(price_day_complete AND demand_day_complete) OVER w AS rolling_days_complete,
 sum(price_numerator) OVER w AS rolling_numerator,sum(priced_offtake_kwh) OVER w AS rolling_priced_kwh,
 sum(demand_gwh) OVER w AS rolling_demand_sum,avg(weighted_price) OVER w AS rolling_daily_price_mean,
 sum(price_observations) OVER w AS rolling_price_n,sum(interval_price_sum) OVER w AS rolling_price_sum,
 sum(interval_price_squared_sum) OVER w AS rolling_price_squared_sum
 FROM blocks b WINDOW w AS (PARTITION BY scope,zone,contiguous_block ORDER BY trading_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
)
SELECT w.*,rolling_days=30 AND rolling_days_complete AS full_30_day_window,
 CASE WHEN rolling_days=30 AND rolling_days_complete THEN rolling_numerator/nullif(rolling_priced_kwh,0) END AS rolling_30d_weighted_price,
 CASE WHEN rolling_days=30 AND rolling_days_complete THEN rolling_daily_price_mean END AS rolling_30d_mean_daily_price,
 CASE WHEN rolling_days=30 AND rolling_days_complete THEN rolling_demand_sum END AS rolling_30d_demand_gwh,
 CASE WHEN rolling_days=30 AND rolling_days_complete THEN
 sqrt(greatest(0,rolling_price_squared_sum/nullif(rolling_price_n,0)-power(rolling_price_sum/nullif(rolling_price_n,0),2)))
 END AS rolling_30d_interval_price_volatility_pop
FROM windows w;
