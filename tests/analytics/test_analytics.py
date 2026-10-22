"""Small rollback-only analytical fixtures exercise the production SQL views.

Core facts and applied migrations are never changed. Cache fixtures disappear
on rollback; the advisory lock prevents a concurrent production refresh.
"""
import json
import statistics
from datetime import date
from decimal import Decimal
from pathlib import Path
import sys
import unittest

import psycopg

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'src'))
from warehouse.db import connect
from warehouse.loader import LOCK_ID
from analytics.runner import SQL


class AnalyticsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn = connect()
        cls.conn.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
        cls.conn.execute('SELECT analytics.assert_current()')

    @classmethod
    def tearDownClass(cls):
        cls.conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
        cls.conn.close()

    def setUp(self):
        self.tx = self.conn.transaction(force_rollback=True)
        self.tx.__enter__()

    def tearDown(self):
        self.tx.__exit__(None, None, None)

    def empty(self):
        self.conn.execute('DELETE FROM analytics._interval_cache')
        self.conn.execute('DELETE FROM analytics._threshold_cache')

    def interval(self, day='2026-08-01', tp=1, price=100, kwh=500, zone='National',
                 gen=100, renewable=60, fossil=20, storage=10, unclassified=10):
        scope = 'National' if zone == 'National' else 'Zone'
        self.conn.execute("""INSERT INTO analytics._interval_cache
          SELECT %s,%s,i.interval_id,i.trading_date,i.trading_period,i.start_utc,i.end_utc,
          i.local_start,i.local_end,d.expected_periods,%s,%s,%s,1,1,1,%s,%s,%s,%s,%s,%s,%s
          FROM core.dim_trading_interval i JOIN core.dim_date d USING(trading_date)
          WHERE trading_date=%s AND trading_period=%s""",
          (scope,zone,kwh,kwh,Decimal(str(price))*Decimal(str(kwh)),gen,renewable,fossil,storage,unclassified,
           0 if zone=='Unknown' else kwh,0 if zone=='Unknown' else gen,day,tp))

    def threshold(self, price=100, zone='National'):
        self.conn.execute("""INSERT INTO analytics._threshold_cache VALUES
          (%s,%s,%s,10,'2026-08-01Z','2026-09-01Z',ARRAY[DATE '2026-08-01'])""",
          ('National' if zone=='National' else 'Zone',zone,price))

    def test_live_reconciliation_evidence(self):
        evidence = json.loads((ROOT/'outputs/analytics/validation.json').read_text(encoding='utf-8'))
        self.assertTrue(all(evidence['checks'].values()), evidence['checks'])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM analytics.mart_market_interval_national WHERE date_trunc('month',trading_date)::date IN ('2025-09-01','2026-04-01','2026-08-01')").fetchone()[0],4368)
        expected=self.conn.execute('SELECT count(*) FROM core.dim_trading_interval i CROSS JOIN analytics.configuration c WHERE date_trunc(\'month\',i.trading_date)::date=ANY(c.pilot_months)').fetchone()[0]
        self.assertEqual(self.conn.execute('SELECT count(*) FROM analytics.mart_market_interval_national').fetchone()[0],expected)

    def test_weighted_price_and_reaggregation(self):
        self.empty()
        self.interval(tp=1,price=100,kwh=100)
        self.interval(tp=2,price=300,kwh=300)
        row = self.conn.execute('SELECT weighted_price,price_numerator,priced_offtake_kwh FROM analytics.mart_market_daily_national').fetchone()
        self.assertEqual(row,(Decimal(250),Decimal(100000),Decimal(400)))
        self.assertEqual(self.conn.execute('SELECT weighted_price FROM analytics.mart_market_monthly').fetchone()[0],250)

    def test_no_fanout_after_participant_aggregation(self):
        self.empty()
        iid = self.conn.execute("SELECT interval_id FROM core.dim_trading_interval WHERE trading_date='2026-08-01' AND trading_period=1").fetchone()[0]
        self.conn.execute('CREATE TEMP TABLE fixture_volume(interval_id bigint,connection_id bigint,zone text,kilowatt_hours numeric,flow_direction text) ON COMMIT DROP')
        self.conn.execute("INSERT INTO fixture_volume VALUES (%s,1,'CNI',10,'Offtake'),(%s,1,'CNI',20,'Offtake'),(%s,2,'Unknown',30,'Offtake')",(iid,iid,iid))
        self.conn.execute("CREATE TEMP TABLE fixture_connection ON COMMIT DROP AS SELECT 1::bigint connection_id,'POC0011'::text poc UNION ALL SELECT 2,'POC0011'")
        query = (SQL/'queries/offtake.sql').read_text().replace('core.v_selected_reconciled_volume','fixture_volume').replace('core.dim_connection','fixture_connection')
        self.conn.execute('CREATE TEMP TABLE analytics_offtake_poc ON COMMIT DROP AS '+query)
        self.conn.execute('CREATE TEMP TABLE analytics_price(interval_id bigint,poc text,dollars_per_mwh numeric,UNIQUE(interval_id,poc)) ON COMMIT DROP')
        self.conn.execute("INSERT INTO analytics_price VALUES(%s,'POC0011',100)",(iid,))
        self.conn.execute('''CREATE TEMP TABLE analytics_generation(interval_id bigint,zone text,source_rows bigint,generation_kwh numeric,
           renewable_kwh numeric,fossil_kwh numeric,storage_kwh numeric,unclassified_kwh numeric) ON COMMIT DROP''')
        self.conn.execute("INSERT INTO analytics_generation VALUES(%s,'CNI',2,500,500,0,0,0)",(iid,))
        self.conn.execute((SQL/'queries/combine.sql').read_text())
        self.assertEqual(self.conn.execute("SELECT offtake_kwh,price_numerator,generation_kwh,offtake_source_rows FROM analytics.mart_market_interval_national").fetchone(),(60,6000,500,3))
        self.assertEqual(self.conn.execute("SELECT offtake_kwh,weighted_price FROM analytics.mart_market_interval_zone WHERE zone='Unknown'").fetchone(),(30,100))

    def test_percentiles_and_population_volatility(self):
        self.empty()
        for tp,p in enumerate([0,10,20,30],1): self.interval(tp=tp,price=p)
        p95,sd = self.conn.execute('SELECT p95_interval_price,price_volatility_pop FROM analytics.mart_market_daily_national').fetchone()
        self.assertAlmostEqual(p95,28.5)
        self.assertAlmostEqual(float(sd),125**0.5)
        p99 = self.conn.execute('SELECT percentile_cont(0.99) WITHIN GROUP(ORDER BY weighted_price) FROM analytics._interval_input').fetchone()[0]
        self.assertAlmostEqual(p99,29.7)

    def test_interval_lag_respects_missing_intervals_and_months(self):
        self.empty()
        self.interval(day='2025-09-30',tp=48,price=80)
        for tp in [1,2,4]: self.interval(day='2026-04-01',tp=tp,price=100+tp)
        rows = self.conn.execute('SELECT price_change_previous_interval FROM analytics.mart_market_interval ORDER BY start_utc').fetchall()
        self.assertEqual(rows,[(None,),(None,),(1,),(None,)])

    def test_daily_lag_and_full_seven_day_windows(self):
        self.empty()
        self.interval(day='2026-04-30',tp=1)
        for d in range(1,9):
            for tp in range(1,49): self.interval(day=f'2026-08-{d:02}',tp=tp,price=d,kwh=d*500)
        rows = self.conn.execute("""SELECT trading_date,contiguous_block,price_change_previous_day,
            full_7_day_window,rolling_7d_weighted_price,rolling_7d_demand_gwh,rolling_7d_mean_daily_price
            FROM analytics.mart_market_daily_rolling ORDER BY trading_date""").fetchall()
        self.assertIsNone(rows[1][2])
        self.assertEqual(rows[1][1],2)
        self.assertTrue(all(r[4] is None for r in rows[:7]))
        self.assertTrue(rows[7][3])
        self.assertEqual(rows[7][4],5)  # sum(d*d)/sum(d), 1..7
        self.assertEqual(rows[7][5],Decimal('0.672'))
        self.assertEqual(rows[7][6],4)

    def test_seven_dates_with_missing_tp_are_incomplete(self):
        self.empty()
        for d in range(1,8): self.interval(day=f'2026-08-{d:02}',tp=1)
        row = self.conn.execute('SELECT rolling_days,full_7_day_window,rolling_7d_weighted_price FROM analytics.mart_market_daily_rolling ORDER BY trading_date DESC LIMIT 1').fetchone()
        self.assertEqual(row,(7,False,None))

    def test_full_thirty_day_window_includes_dst_without_weight_bias(self):
        self.empty()
        # Set-based fixture includes the actual 46-period September DST day.
        self.conn.execute("""INSERT INTO analytics._interval_cache
          SELECT 'National','National',i.interval_id,i.trading_date,i.trading_period,
          i.start_utc,i.end_utc,i.local_start,i.local_end,d.expected_periods,
          500,500,500*extract(day FROM i.trading_date),1,1,1,100,60,20,10,10,500,100
          FROM core.dim_trading_interval i JOIN core.dim_date d USING(trading_date)
          WHERE i.trading_date BETWEEN '2025-09-01' AND '2025-09-30'""")
        rows=self.conn.execute("SELECT full_30_day_window,rolling_30d_weighted_price,rolling_30d_demand_gwh,rolling_30d_interval_price_volatility_pop FROM analytics.mart_market_daily_rolling_30d ORDER BY trading_date").fetchall()
        self.assertEqual(len(rows),30)
        self.assertTrue(all(not r[0] and r[1] is None for r in rows[:29]))
        self.assertTrue(rows[-1][0])
        expected=self.conn.execute('SELECT sum(price_numerator)/sum(priced_offtake_kwh) FROM analytics._interval_cache').fetchone()[0]
        self.assertEqual(rows[-1][1],expected)
        self.assertEqual(rows[-1][2],Decimal('0.719'))
        # Independent interval population: September 28 has 46 observations.
        prices=[d for d in range(1,31) for _ in range(46 if d==28 else 48)]
        self.assertAlmostEqual(float(rows[-1][3]),statistics.pstdev(prices),places=10)
        self.conn.execute("DELETE FROM analytics._interval_cache WHERE trading_date='2025-09-15' AND trading_period=1")
        row=self.conn.execute("SELECT full_30_day_window,rolling_30d_weighted_price FROM analytics.mart_market_daily_rolling_30d WHERE trading_date='2025-09-30'").fetchone()
        self.assertEqual(row,(False,None))

        # The fall-back window has 1,442 intervals, not 30 * 48.
        self.empty()
        self.conn.execute("""INSERT INTO analytics._interval_cache
          SELECT 'National','National',i.interval_id,i.trading_date,i.trading_period,
          i.start_utc,i.end_utc,i.local_start,i.local_end,d.expected_periods,
          500,500,500*extract(day FROM i.trading_date),1,1,1,100,60,20,10,10,500,100
          FROM core.dim_trading_interval i JOIN core.dim_date d USING(trading_date)
          WHERE i.trading_date BETWEEN '2026-04-01' AND '2026-04-30'""")
        row=self.conn.execute("SELECT full_30_day_window,rolling_30d_demand_gwh,rolling_30d_interval_price_volatility_pop FROM analytics.mart_market_daily_rolling_30d WHERE trading_date='2026-04-30'").fetchone()
        prices=[d for d in range(1,31) for _ in range(50 if d==5 else 48)]
        self.assertEqual(row[:2],(True,Decimal('0.721')))
        self.assertAlmostEqual(float(row[2]),statistics.pstdev(prices),places=10)

    def test_thirty_day_window_does_not_bridge_missing_date(self):
        self.empty()
        self.conn.execute("""INSERT INTO analytics._interval_cache
          SELECT 'National','National',i.interval_id,i.trading_date,i.trading_period,
          i.start_utc,i.end_utc,i.local_start,i.local_end,d.expected_periods,
          500,500,50000,1,1,1,100,60,20,10,10,500,100
          FROM core.dim_trading_interval i JOIN core.dim_date d USING(trading_date)
          WHERE i.trading_date BETWEEN '2025-09-01' AND '2025-10-01'
          AND i.trading_date<>'2025-09-15'""")
        self.assertEqual(self.conn.execute('SELECT count(*) FROM analytics.mart_market_daily_rolling_30d WHERE full_30_day_window OR rolling_30d_weighted_price IS NOT NULL').fetchone()[0],0)

    def test_rolling_volatility_uses_all_interval_observations(self):
        self.empty()
        for d in range(1,8):
            for tp in range(1,49): self.interval(day=f'2026-08-{d:02}',tp=tp,price=d)
        row = self.conn.execute('SELECT rolling_7d_interval_price_volatility_pop FROM analytics.mart_market_daily_rolling ORDER BY trading_date DESC LIMIT 1').fetchone()
        self.assertAlmostEqual(float(row[0]),2.0)  # population SD of 1..7, each repeated 48 times

    def test_unpriced_offtake_remains_in_coverage_denominator(self):
        self.empty()
        self.interval(kwh=100)
        self.conn.execute('UPDATE analytics._interval_cache SET priced_offtake_kwh=60,price_numerator=12000')
        self.assertEqual(self.conn.execute('SELECT weighted_price,price_weighting_coverage_pct FROM analytics._interval_input').fetchone(),(200,60))

    def test_spread_requires_all_five_known_zones(self):
        self.empty()
        for z,p in [('CNI',100),('LNI',120),('Unknown',999)]: self.interval(zone=z,price=p)
        self.assertEqual(self.conn.execute('SELECT represented_zones,regional_price_spread FROM analytics.mart_regional_spread').fetchone(),(2,None))
        for z,p in [('LSI',90),('UNI',150),('USI',110)]: self.interval(zone=z,price=p)
        self.assertEqual(self.conn.execute('SELECT represented_zones,regional_price_spread FROM analytics.mart_regional_spread').fetchone(),(5,60))

    def test_events_split_on_unflagged_and_utc_gaps(self):
        self.empty()
        self.threshold()
        for tp,p in [(1,120),(2,130),(3,90),(4,120),(6,120)]: self.interval(tp=tp,price=p)
        self.interval(day='2026-04-30',tp=48,price=120)
        rows = self.conn.execute('SELECT interval_count,duration_hours FROM analytics.mart_price_pressure_event ORDER BY start_utc').fetchall()
        self.assertEqual(rows,[(1,Decimal('.5')),(2,Decimal('1')),(1,Decimal('.5')),(1,Decimal('.5'))])

    def test_threshold_ties_are_flagged_and_regions_do_not_merge(self):
        self.empty()
        for z in ['National','CNI']:
            self.threshold(zone=z)
            self.interval(zone=z,price=100)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM analytics.mart_price_pressure_event').fetchone()[0],2)

    def test_dst_daily_energy_and_event_duration(self):
        self.empty()
        self.threshold(price=1)
        for day,n in [('2025-09-28',46),('2026-04-05',50),('2026-08-01',48)]:
            for tp in range(1,n+1): self.interval(day=day,tp=tp,kwh=500)
        rows = self.conn.execute('SELECT observed_intervals,observed_hours,offtake_kwh FROM analytics.mart_market_daily_national ORDER BY trading_date').fetchall()
        self.assertEqual(rows,[(46,23,23000),(50,25,25000),(48,24,24000)])
        self.assertEqual([r[0] for r in self.conn.execute('SELECT duration_hours FROM analytics.mart_price_pressure_event ORDER BY start_utc')],[23,25,24])

    def test_classification_excludes_storage_and_unclassified(self):
        self.empty()
        self.interval()
        share,coverage = self.conn.execute('SELECT renewable_primary_share_pct,classification_coverage_pct FROM analytics._interval_input').fetchone()
        self.assertEqual((share,coverage),(75,90))

    def test_new_code_is_unclassified_not_dropped(self):
        self.conn.execute("""CREATE TEMP TABLE fixture_generation ON COMMIT DROP AS
          SELECT 1::bigint interval_id,'Unknown'::text zone,'NEW'::text fuel_code,'NEW'::text tech_code,50::numeric kilowatt_hours
          UNION ALL SELECT 1,'Unknown','ELE','BAT',30""")
        query = (SQL/'queries/generation.sql').read_text().replace('core.v_selected_generation','fixture_generation')
        row = self.conn.execute(query).fetchone()
        self.assertEqual(row[3:],(80,0,0,30,50))

    def test_zero_denominators_remain_null(self):
        self.empty()
        self.interval(kwh=0,gen=0,renewable=0,fossil=0,storage=0,unclassified=0)
        row = self.conn.execute('SELECT weighted_price,price_weighting_coverage_pct,renewable_primary_share_pct,classification_coverage_pct FROM analytics._interval_input').fetchone()
        self.assertEqual(row,(None,None,None,None))

    def test_selection_removal_blocks_all_public_marts(self):
        self.conn.execute("DELETE FROM metadata.publication_selection WHERE source_name='prices' AND source_month='2026-08-01'")
        for view in ['mart_market_interval','mart_market_daily','mart_market_monthly','mart_market_daily_rolling',
                     'mart_market_daily_rolling_30d',
                     'mart_price_pressure_threshold','mart_price_pressure_event','mart_price_event_context','mart_regional_spread']:
            with self.assertRaises(psycopg.errors.RaiseException):
                with self.conn.transaction(): self.conn.execute(f'SELECT * FROM analytics.{view} LIMIT 1').fetchall()

    def test_classification_change_blocks_stale_marts(self):
        self.conn.execute("UPDATE analytics.ref_generation_classification SET rationale=rationale||' fixture' WHERE fuel_code='ELE'")
        with self.assertRaises(psycopg.errors.RaiseException):
            with self.conn.transaction(): self.conn.execute('SELECT * FROM analytics.mart_market_interval_national LIMIT 1')

    def test_release_configuration_change_blocks_thirty_day_outputs(self):
        self.conn.execute("UPDATE analytics.configuration SET pilot_months=array_remove(pilot_months,DATE '2025-12-01')")
        with self.assertRaises(psycopg.errors.RaiseException):
            with self.conn.transaction(): self.conn.execute('SELECT * FROM analytics.mart_market_daily_rolling_30d LIMIT 1')

    def test_cache_unique_grain_prevents_duplicates(self):
        self.empty()
        self.interval()
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.conn.transaction(): self.interval()

    def test_actual_unknown_and_unclassified_remain_visible(self):
        self.assertGreater(self.conn.execute("SELECT sum(offtake_kwh) FROM analytics.mart_market_interval_zone WHERE zone='Unknown'").fetchone()[0],0)
        self.assertGreater(self.conn.execute('SELECT sum(unclassified_kwh) FROM analytics.mart_market_interval_national').fetchone()[0],0)
        self.assertEqual(self.conn.execute("SELECT generation_role FROM analytics.ref_generation_classification WHERE fuel_code='ELE' AND tech_code='BAT'").fetchone()[0],'Storage')


if __name__ == '__main__':
    unittest.main()
