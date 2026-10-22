SELECT event_id,scope,zone,start_utc AT TIME ZONE 'UTC' AS start_utc,
 end_utc AT TIME ZONE 'UTC' AS end_utc,local_start,local_end,local_start::date AS start_date,
 interval_count,duration_hours,weighted_price,peak_weighted_price,p99_threshold,
 average_demand_mw,peak_demand_mw,total_offtake_kwh,priced_offtake_kwh,price_numerator,
 average_regional_spread,peak_regional_spread,listed_generation_kwh,
 renewable_kwh,fossil_kwh,storage_kwh,unclassified_kwh,renewable_primary_share_pct,
 classification_coverage_pct,price_weighting_coverage_pct,offtake_zone_coverage_pct,
 generation_zone_coverage_pct,refresh_id,input_fingerprint,dq_run_id,dq_as_of_date,dq_status
FROM analytics.mart_price_event_context;
