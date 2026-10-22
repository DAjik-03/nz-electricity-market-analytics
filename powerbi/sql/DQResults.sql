SELECT run_id,rule_id,rule_snapshot::text AS rule_snapshot,result_status,
 affected_rows,observed_value::text AS observed_value,expected_value,
 coverage_pct,details::text AS details,as_of_date,refresh_id
FROM analytics.mart_quality_results;
