let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT DISTINCT zone FROM analytics.mart_market_interval_zone", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
