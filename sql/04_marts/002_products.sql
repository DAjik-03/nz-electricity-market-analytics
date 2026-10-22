CREATE TABLE analytics._threshold_cache (
 scope text NOT NULL,zone text NOT NULL,p99_price double precision NOT NULL,
 population_intervals bigint NOT NULL,first_start_utc timestamptz NOT NULL,last_end_utc timestamptz NOT NULL,
 population_months date[] NOT NULL,PRIMARY KEY(scope,zone)
);
REVOKE ALL ON analytics._threshold_cache FROM PUBLIC;

CREATE VIEW analytics.mart_price_pressure_threshold AS
SELECT t.*,0.99::double precision AS percentile,'interval weighted price >= P99'::text AS comparison
FROM analytics._threshold_cache t WHERE (SELECT analytics.assert_current());

CREATE VIEW analytics._interval_input AS
SELECT c.*,price_numerator/nullif(priced_offtake_kwh,0) AS weighted_price,
 offtake_kwh/500 AS demand_mw,
 100*priced_offtake_kwh/nullif(offtake_kwh,0) AS price_weighting_coverage_pct,
 100*known_zone_offtake_kwh/nullif(offtake_kwh,0) AS offtake_zone_coverage_pct,
 100*known_zone_generation_kwh/nullif(generation_kwh,0) AS generation_zone_coverage_pct,
 100*(generation_kwh-unclassified_kwh)/nullif(generation_kwh,0) AS classification_coverage_pct,
 100*renewable_kwh/nullif(renewable_kwh+fossil_kwh,0) AS renewable_primary_share_pct,
 100*fossil_kwh/nullif(renewable_kwh+fossil_kwh,0) AS fossil_primary_share_pct
FROM analytics._interval_cache c WHERE (SELECT analytics.assert_current());

CREATE VIEW analytics.mart_regional_spread AS
SELECT i.interval_id,count(*) FILTER(WHERE i.weighted_price IS NOT NULL) AS represented_zones,
 cardinality(c.expected_zones) AS expected_zones,
 CASE WHEN count(*) FILTER(WHERE i.weighted_price IS NOT NULL)=cardinality(c.expected_zones)
 THEN max(i.weighted_price)-min(i.weighted_price) END AS regional_price_spread
FROM analytics._interval_input i CROSS JOIN analytics.configuration c
WHERE i.scope='Zone' AND i.zone=ANY(c.expected_zones)
GROUP BY i.interval_id,c.expected_zones;

CREATE VIEW analytics.mart_market_interval AS
SELECT i.*,s.represented_zones,s.expected_zones,s.regional_price_spread,
 t.p99_price,coalesce(i.weighted_price>=t.p99_price,false) AS is_price_pressure,
 CASE WHEN lag(i.end_utc) OVER w=i.start_utc
      THEN i.weighted_price-lag(i.weighted_price) OVER w END AS price_change_previous_interval,
 CASE WHEN lag(i.end_utc) OVER w=i.start_utc
      THEN i.demand_mw-lag(i.demand_mw) OVER w END AS demand_change_previous_interval_mw
FROM analytics._interval_input i LEFT JOIN analytics.mart_regional_spread s USING(interval_id)
LEFT JOIN analytics.mart_price_pressure_threshold t USING(scope,zone)
WINDOW w AS (PARTITION BY i.scope,i.zone ORDER BY i.start_utc);

CREATE VIEW analytics.mart_market_interval_national AS SELECT * FROM analytics.mart_market_interval WHERE scope='National';
CREATE VIEW analytics.mart_market_interval_zone AS SELECT * FROM analytics.mart_market_interval WHERE scope='Zone';

-- Aggregate numerators/denominators directly; never average previously averaged prices.
CREATE VIEW analytics.mart_market_daily AS
SELECT scope,zone,trading_date,count(*) AS observed_intervals,max(expected_periods) AS expected_intervals,
 count(*)*0.5 AS observed_hours,
 count(offtake_kwh)=max(expected_periods) AS demand_day_complete,
 count(weighted_price)=max(expected_periods) AS price_day_complete,
 sum(offtake_kwh) AS offtake_kwh,sum(priced_offtake_kwh) AS priced_offtake_kwh,
 sum(price_numerator) AS price_numerator,sum(price_numerator)/nullif(sum(priced_offtake_kwh),0) AS weighted_price,
 sum(offtake_kwh)/1000000 AS demand_gwh,max(demand_mw) AS peak_demand_mw,
 sum(generation_kwh) AS generation_kwh,sum(generation_kwh)/1000000 AS listed_generation_gwh,
 sum(renewable_kwh) AS renewable_kwh,sum(fossil_kwh) AS fossil_kwh,
 sum(storage_kwh) AS storage_kwh,sum(unclassified_kwh) AS unclassified_kwh,
 min(weighted_price) AS min_interval_price,max(weighted_price) AS max_interval_price,
 percentile_cont(0.95) WITHIN GROUP(ORDER BY weighted_price) AS p95_interval_price,
 stddev_pop(weighted_price) AS price_volatility_pop,
 count(weighted_price) AS price_observations,sum(weighted_price) AS interval_price_sum,
 sum(weighted_price*weighted_price) AS interval_price_squared_sum,
 count(*) FILTER(WHERE is_price_pressure) AS high_price_intervals,
 sum(known_zone_offtake_kwh) AS known_zone_offtake_kwh,sum(known_zone_generation_kwh) AS known_zone_generation_kwh,
 100*sum(priced_offtake_kwh)/nullif(sum(offtake_kwh),0) AS price_weighting_coverage_pct,
 100*sum(known_zone_offtake_kwh)/nullif(sum(offtake_kwh),0) AS offtake_zone_coverage_pct,
 100*sum(known_zone_generation_kwh)/nullif(sum(generation_kwh),0) AS generation_zone_coverage_pct,
 100*(sum(generation_kwh)-sum(unclassified_kwh))/nullif(sum(generation_kwh),0) AS classification_coverage_pct,
 100*sum(renewable_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS renewable_primary_share_pct,
 100*sum(fossil_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS fossil_primary_share_pct,
 avg(regional_price_spread) AS average_regional_spread,
 count(regional_price_spread) AS spread_observations
FROM analytics.mart_market_interval GROUP BY scope,zone,trading_date;

CREATE VIEW analytics.mart_market_daily_national AS SELECT * FROM analytics.mart_market_daily WHERE scope='National';
CREATE VIEW analytics.mart_market_daily_zone AS SELECT * FROM analytics.mart_market_daily WHERE scope='Zone';

CREATE VIEW analytics.mart_market_monthly AS
SELECT scope,zone,date_trunc('month',trading_date)::date AS source_month,
 count(*) AS observed_intervals,sum(offtake_kwh)/1000000 AS demand_gwh,
 sum(generation_kwh)/1000000 AS listed_generation_gwh,
 sum(price_numerator) AS price_numerator,sum(priced_offtake_kwh) AS priced_offtake_kwh,
 sum(price_numerator)/nullif(sum(priced_offtake_kwh),0) AS weighted_price,
 percentile_cont(0.95) WITHIN GROUP(ORDER BY weighted_price) AS p95_interval_price,
 stddev_pop(weighted_price) AS price_volatility_pop,max(demand_mw) AS peak_demand_mw,
 count(*) FILTER(WHERE is_price_pressure) AS high_price_intervals,
 sum(renewable_kwh)/1000000 AS renewable_gwh,sum(fossil_kwh)/1000000 AS fossil_thermal_gwh,
 sum(storage_kwh)/1000000 AS storage_gwh,sum(unclassified_kwh)/1000000 AS unclassified_gwh,
 100*sum(renewable_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS renewable_primary_share_pct,
 100*(sum(generation_kwh)-sum(unclassified_kwh))/nullif(sum(generation_kwh),0) AS classification_coverage_pct,
 100*sum(priced_offtake_kwh)/nullif(sum(offtake_kwh),0) AS price_weighting_coverage_pct,
 100*sum(known_zone_offtake_kwh)/nullif(sum(offtake_kwh),0) AS offtake_zone_coverage_pct,
 100*sum(known_zone_generation_kwh)/nullif(sum(generation_kwh),0) AS generation_zone_coverage_pct
FROM analytics.mart_market_interval GROUP BY scope,zone,date_trunc('month',trading_date)::date;

CREATE VIEW analytics.mart_market_daily_rolling AS
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
 FROM blocks b WINDOW w AS (PARTITION BY scope,zone,contiguous_block ORDER BY trading_date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)
)
SELECT w.*,rolling_days=7 AND rolling_days_complete AS full_7_day_window,
 CASE WHEN rolling_days=7 AND rolling_days_complete THEN rolling_numerator/nullif(rolling_priced_kwh,0) END AS rolling_7d_weighted_price,
 CASE WHEN rolling_days=7 AND rolling_days_complete THEN rolling_daily_price_mean END AS rolling_7d_mean_daily_price,
 CASE WHEN rolling_days=7 AND rolling_days_complete THEN rolling_demand_sum END AS rolling_7d_demand_gwh,
 CASE WHEN rolling_days=7 AND rolling_days_complete THEN
 sqrt(greatest(0,rolling_price_squared_sum/nullif(rolling_price_n,0)-power(rolling_price_sum/nullif(rolling_price_n,0),2)))
 END AS rolling_7d_interval_price_volatility_pop
FROM windows w;

CREATE VIEW analytics._event_members AS
WITH previous AS (
 SELECT i.*,lag(is_price_pressure) OVER w AS previous_flag,lag(end_utc) OVER w AS previous_end
 FROM analytics.mart_market_interval i
 WHERE p99_price IS NOT NULL
 WINDOW w AS (PARTITION BY scope,zone ORDER BY start_utc)
), grouped AS (
 SELECT p.*,sum(CASE WHEN is_price_pressure AND
   (NOT coalesce(previous_flag,false) OR previous_end IS DISTINCT FROM start_utc) THEN 1 ELSE 0 END)
 OVER(PARTITION BY scope,zone ORDER BY start_utc ROWS UNBOUNDED PRECEDING) AS event_group
 FROM previous p
)
SELECT * FROM grouped WHERE is_price_pressure;

CREATE VIEW analytics.mart_price_pressure_event AS
SELECT scope||':'||zone||':'||to_char(min(start_utc) AT TIME ZONE 'UTC','YYYYMMDDHH24MI') AS event_id,
 scope,zone,min(start_utc) AS start_utc,max(end_utc) AS end_utc,
 (array_agg(local_start ORDER BY start_utc))[1] AS local_start,
 (array_agg(local_end ORDER BY start_utc DESC))[1] AS local_end,
 count(*) AS interval_count,count(*)*0.5 AS duration_hours,
 sum(price_numerator)/nullif(sum(priced_offtake_kwh),0) AS weighted_price,
 avg(weighted_price) AS mean_interval_weighted_price,max(weighted_price) AS peak_weighted_price,
 min(p99_price) AS p99_threshold,avg(demand_mw) AS average_demand_mw,max(demand_mw) AS peak_demand_mw,
 sum(offtake_kwh) AS total_offtake_kwh,sum(priced_offtake_kwh) AS priced_offtake_kwh,
 sum(price_numerator) AS price_numerator,
 avg(regional_price_spread) AS average_regional_spread,max(regional_price_spread) AS peak_regional_spread,
 count(regional_price_spread) AS spread_observations,
 sum(generation_kwh) AS listed_generation_kwh,sum(renewable_kwh) AS renewable_kwh,sum(fossil_kwh) AS fossil_kwh,
 sum(storage_kwh) AS storage_kwh,sum(unclassified_kwh) AS unclassified_kwh,
 100*sum(renewable_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS renewable_primary_share_pct,
 100*sum(fossil_kwh)/nullif(sum(renewable_kwh+fossil_kwh),0) AS fossil_primary_share_pct,
 100*(sum(generation_kwh)-sum(unclassified_kwh))/nullif(sum(generation_kwh),0) AS classification_coverage_pct,
 100*sum(priced_offtake_kwh)/nullif(sum(offtake_kwh),0) AS price_weighting_coverage_pct,
 100*sum(known_zone_offtake_kwh)/nullif(sum(offtake_kwh),0) AS offtake_zone_coverage_pct,
 100*sum(known_zone_generation_kwh)/nullif(sum(generation_kwh),0) AS generation_zone_coverage_pct
FROM analytics._event_members GROUP BY scope,zone,event_group;

CREATE VIEW analytics.mart_price_event_context AS
SELECT e.*,dense_rank() OVER(PARTITION BY scope,zone ORDER BY peak_weighted_price DESC) AS peak_price_rank_within_region,
 r.refresh_id,r.input_fingerprint,r.dq_run_id,r.dq_as_of_date,r.dq_status
FROM analytics.mart_price_pressure_event e CROSS JOIN analytics.refresh_status r;
