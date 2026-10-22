"""Independent native-grain SQL and analytical invariants for the approved pilot."""
import time
from .runner import save


def collect(conn):
    start = time.perf_counter()
    conn.execute('SELECT analytics.assert_current()')
    conn.execute("SET work_mem='128MB'")
    conn.execute('SET jit=off')
    # Deliberately different from refresh: join each participant row to its unique
    # price, then aggregate monthly. No generation/NSP join is needed nationally.
    independent = conn.execute("""SELECT date_trunc('month',i.trading_date)::date,
       sum(r.kilowatt_hours),sum(CASE WHEN p.dollars_per_mwh IS NOT NULL THEN r.kilowatt_hours ELSE 0 END),
       sum(CASE WHEN p.dollars_per_mwh IS NOT NULL THEN r.kilowatt_hours*p.dollars_per_mwh ELSE 0 END)
       FROM core.v_selected_reconciled_volume r
       JOIN core.dim_trading_interval i USING(interval_id)
       JOIN core.dim_connection c USING(connection_id)
       LEFT JOIN core.dim_pricing_node n ON n.pricing_poc=c.poc
       LEFT JOIN core.v_selected_price p ON p.interval_id=r.interval_id AND p.pricing_node_id=n.pricing_node_id
       WHERE r.flow_direction='Offtake' GROUP BY 1 ORDER BY 1""").fetchall()
    mart = conn.execute("""SELECT source_month,demand_gwh*1000000,priced_offtake_kwh,price_numerator
       FROM analytics.mart_market_monthly WHERE scope='National' ORDER BY 1""").fetchall()
    generation = conn.execute("""SELECT date_trunc('month',i.trading_date)::date,sum(f.kilowatt_hours)
       FROM core.v_selected_generation f JOIN core.dim_trading_interval i USING(interval_id) GROUP BY 1 ORDER BY 1""").fetchall()
    gen_mart = conn.execute("""SELECT source_month,listed_generation_gwh*1000000
       FROM analytics.mart_market_monthly WHERE scope='National' ORDER BY 1""").fetchall()
    checks = {'independent_weighted_numerator_denominator_exact': independent == mart,
              'listed_generation_native_totals_exact': generation == gen_mart}
    queries = {
        'zone_totals_equal_national_including_unknown': """SELECT count(*) FROM
          (SELECT interval_id,sum(offtake_kwh) o,sum(generation_kwh) g,sum(price_numerator) n,sum(priced_offtake_kwh) d
           FROM analytics._interval_input WHERE scope='Zone' GROUP BY 1) z
          JOIN analytics._interval_input n USING(interval_id) WHERE n.scope='National' AND
          (z.o IS DISTINCT FROM n.offtake_kwh OR z.g IS DISTINCT FROM n.generation_kwh OR
           z.n IS DISTINCT FROM n.price_numerator OR z.d IS DISTINCT FROM n.priced_offtake_kwh)""",
        'classification_components_reconcile': """SELECT count(*) FROM analytics._interval_input
          WHERE generation_kwh IS DISTINCT FROM renewable_kwh+fossil_kwh+storage_kwh+unclassified_kwh""",
        'calendar_daily_counts': """SELECT count(*) FROM analytics.mart_market_daily
          WHERE observed_intervals<>expected_intervals""",
        'national_known_zone_complete_days': """SELECT count(*) FROM analytics.mart_market_daily
          WHERE zone<>'Unknown' AND (NOT demand_day_complete OR NOT price_day_complete)""",
        'no_cross_gap_lag': """SELECT count(*) FROM analytics.mart_market_daily_rolling
          WHERE previous_date IS DISTINCT FROM trading_date-1
          AND (price_change_previous_day IS NOT NULL OR demand_change_previous_day_gwh IS NOT NULL)""",
        'incomplete_windows_null': """SELECT count(*) FROM analytics.mart_market_daily_rolling
          WHERE NOT full_7_day_window AND (rolling_7d_weighted_price IS NOT NULL OR rolling_7d_demand_gwh IS NOT NULL
                                         OR rolling_7d_interval_price_volatility_pop IS NOT NULL)""",
        'full_zone_spread': """SELECT count(*) FROM analytics.mart_regional_spread
          WHERE (represented_zones<expected_zones AND regional_price_spread IS NOT NULL)
             OR (represented_zones=expected_zones AND regional_price_spread IS NULL)""",
        'incomplete_30_day_windows_null': """SELECT count(*) FROM analytics.mart_market_daily_rolling_30d
          WHERE NOT full_30_day_window AND (rolling_30d_weighted_price IS NOT NULL
             OR rolling_30d_demand_gwh IS NOT NULL OR rolling_30d_interval_price_volatility_pop IS NOT NULL)""",
        'annual_national_population': """SELECT abs(count(*)-17520)
          FROM analytics.mart_market_interval_national""",
        'event_utc_duration': """SELECT count(*) FROM analytics.mart_price_pressure_event
          WHERE duration_hours<>interval_count*0.5 OR extract(epoch FROM end_utc-start_utc)/3600<>duration_hours""",
        'event_members_equal_flagged_intervals': """SELECT abs(
          (SELECT count(*) FROM analytics.mart_market_interval WHERE is_price_pressure)-
          (SELECT sum(interval_count) FROM analytics.mart_price_pressure_event))""",
        'threshold_recalculation': """SELECT count(*) FROM analytics.mart_price_pressure_threshold t
          JOIN (SELECT scope,zone,percentile_cont(0.99) WITHIN GROUP(ORDER BY weighted_price) p
                FROM analytics._interval_input GROUP BY scope,zone) r USING(scope,zone) WHERE t.p99_price<>r.p""",
        'no_unknown_threshold': "SELECT count(*) FROM analytics.mart_price_pressure_threshold WHERE zone='Unknown'",
        'no_unexpected_zones': """SELECT count(*) FROM analytics._interval_input CROSS JOIN analytics.configuration c
          WHERE scope='Zone' AND zone<>'Unknown' AND NOT zone=ANY(c.expected_zones)""",
    }
    for name, query in queries.items():
        checks[name] = conn.execute(query).fetchone()[0] == 0
    coverage = [r[0] for r in conn.execute("""SELECT jsonb_build_object('month',source_month,
       'priced_offtake_pct',price_weighting_coverage_pct,'offtake_zone_pct',offtake_zone_coverage_pct,
       'generation_zone_pct',generation_zone_coverage_pct,'classification_pct',classification_coverage_pct,
       'unclassified_gwh',unclassified_gwh,'storage_gwh',storage_gwh)
       FROM analytics.mart_market_monthly WHERE scope='National' ORDER BY source_month""")]
    dst = conn.execute("""SELECT trading_date,observed_intervals,observed_hours FROM analytics.mart_market_daily_national
      WHERE trading_date IN ('2025-09-28','2026-04-05','2026-08-01') ORDER BY trading_date""").fetchall()
    checks['dst_actual_46_50_48'] = [(x[1], float(x[2])) for x in dst] == [(46,23.0),(50,25.0),(48,24.0)]
    events = conn.execute("SELECT scope,zone,count(*),sum(interval_count) FROM analytics.mart_price_pressure_event GROUP BY 1,2 ORDER BY 1,2").fetchall()
    missing = conn.execute("""SELECT scope,zone,date_trunc('month',trading_date)::date,count(*)
       FROM analytics.mart_market_daily WHERE NOT demand_day_complete OR NOT price_day_complete
       GROUP BY 1,2,3 ORDER BY 1,2,3""").fetchall()
    result = {'checks': checks, 'independent_monthly_price_components': independent,
              'independent_generation_totals': generation, 'coverage': coverage, 'dst': dst,
              'event_counts': events, 'days_without_complete_demand_price_population': missing,
              'seconds': time.perf_counter()-start}
    save('validation.json', result)
    return result
