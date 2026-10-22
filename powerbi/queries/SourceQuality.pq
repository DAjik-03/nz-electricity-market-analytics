let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT run_id,source_name,source_month,denominator_unit,total_value,#(lf) known_value,unknown_value,coverage_pct,as_of_date,refresh_id#(lf)FROM analytics.mart_source_quality", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
