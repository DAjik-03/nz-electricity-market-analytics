let
    Rows = if ReleaseGate then Value.NativeQuery(Source, "SELECT interval_id,offtake_kwh,priced_offtake_kwh,price_numerator,#(lf) weighted_price,demand_mw,generation_kwh,renewable_kwh,fossil_kwh,storage_kwh,#(lf) unclassified_kwh,known_zone_offtake_kwh,known_zone_generation_kwh,is_price_pressure,regional_price_spread,represented_zones,expected_zones#(lf)FROM analytics.mart_market_interval_national", null, [EnableFolding=false]) else error "Release gate failed"
in Rows
