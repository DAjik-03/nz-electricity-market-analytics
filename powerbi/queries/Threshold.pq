let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT scope,zone,p99_price,population_intervals,#(lf) first_start_utc AT TIME ZONE 'UTC' AS first_start_utc,#(lf) last_end_utc AT TIME ZONE 'UTC' AS last_end_utc,percentile,comparison#(lf)FROM analytics.mart_price_pressure_threshold", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
