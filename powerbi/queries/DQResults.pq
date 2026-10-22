let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT run_id,rule_id,rule_snapshot::text AS rule_snapshot,result_status,#(lf) affected_rows,observed_value::text AS observed_value,expected_value,#(lf) coverage_pct,details::text AS details,as_of_date,refresh_id#(lf)FROM analytics.mart_quality_results", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
