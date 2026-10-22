let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT e.event_id,i.interval_id#(lf)FROM analytics.mart_price_pressure_event e#(lf)JOIN analytics.mart_market_interval_national i#(lf) ON i.start_utc>=e.start_utc AND i.start_utc<e.end_utc", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
