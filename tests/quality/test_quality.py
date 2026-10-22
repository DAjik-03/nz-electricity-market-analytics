"""Exercise the registered SQL with rollback-only quality-layer fixtures.

Core facts, constraints, source files and selected warehouse views are untouched.
"""
import json
from pathlib import Path
import sys
import unittest
from psycopg import sql

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from warehouse.db import connect
from warehouse.loader import LOCK_ID
from quality.runner import evaluate
from check_data_quality_determinism import substantive
from historical.regression import select_original_pilot_for_test


class QualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.conn=connect()
        cls.conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        cls.outer=cls.conn.transaction(force_rollback=True)
        cls.outer.__enter__()
        cls.release_coverage_count=cls.conn.execute("SELECT count(*) FROM metadata.publication_selection WHERE source_name<>'nsp'").fetchone()[0]
        select_original_pilot_for_test(cls.conn)
        cls.conn.execute("SET LOCAL work_mem='128MB'")
        cls.conn.execute('SET LOCAL jit=off')
        cls.conn.execute("SELECT set_config('quality.as_of_date','2026-09-21',true)")
        cls.conn.execute('SELECT quality.prepare_profiles()')

    @classmethod
    def tearDownClass(cls):
        cls.outer.__exit__(None,None,None)
        cls.conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))
        cls.conn.close()

    def setUp(self):
        self.tx=self.conn.transaction(force_rollback=True)
        self.tx.__enter__()

    def tearDown(self): self.tx.__exit__(None,None,None)

    def overlay(self,view,base):
        self.conn.execute(sql.SQL('CREATE TABLE quality.fixture AS SELECT * FROM {} WITH NO DATA').format(sql.Identifier('quality',view)))
        self.conn.execute(sql.SQL('INSERT INTO quality.fixture SELECT * FROM {} LIMIT 1').format(sql.Identifier('quality',view)))
        self.conn.execute(sql.SQL('CREATE OR REPLACE VIEW {} AS SELECT * FROM {} UNION ALL SELECT * FROM quality.fixture').format(
            sql.Identifier('quality',view),sql.Identifier('core',base)))

    def test_all_registered_rules_have_persisted_results(self):
        rows=self.conn.execute('SELECT rule_code,result_status,is_blocking FROM quality.v_latest_dq_results').fetchall()
        self.assertEqual(len(rows),29)
        self.assertEqual({x[0] for x in rows},{f'DQ{i:02}' for i in range(1,30)})
        self.assertFalse(any(s=='FAIL' and b for _,s,b in rows))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM quality.v_latest_coverage').fetchone()[0],self.release_coverage_count)

    def test_repeated_runs_are_substantively_identical(self):
        ids=[x[0] for x in self.conn.execute("SELECT run_id FROM quality.dq_run WHERE status='COMPLETED' ORDER BY run_id DESC LIMIT 2")]
        self.assertEqual(len(ids),2)
        self.assertEqual(substantive(self.conn,ids[0]),substantive(self.conn,ids[1]))

    def test_failed_run_retains_no_partial_results(self):
        rows=self.conn.execute("SELECT q.run_id,count(r.rule_id) FROM quality.dq_run q LEFT JOIN quality.rule_result r USING(run_id) WHERE q.status='ERROR' GROUP BY q.run_id").fetchall()
        self.assertTrue(all(n==0 for _,n in rows))

    def test_warning_and_blocking_failure_are_distinct(self):
        result=evaluate(self.conn,'DQ19')
        self.assertEqual(result['result_status'],'WARN')
        self.assertEqual(result['affected_rows'],3)
        # Delete only an isolated quality input row, never the real NSP history.
        self.conn.execute('CREATE TABLE quality.fixture AS SELECT * FROM core.dim_nsp_version')
        self.conn.execute("DELETE FROM quality.fixture WHERE nsp='WQG0011DMFLEN' AND boundary_status='invalid_boundary'")
        self.conn.execute('CREATE OR REPLACE VIEW quality.input_nsp AS SELECT * FROM quality.fixture')
        self.assertEqual(evaluate(self.conn,'DQ19')['result_status'],'FAIL')

    def test_duplicate_fact_grain_detected(self):
        self.overlay('input_price','fact_price')
        result=evaluate(self.conn,'DQ06')
        self.assertEqual((result['result_status'],result['affected_rows']),('FAIL',1))

    def test_orphan_dimension_detected(self):
        self.overlay('input_price','fact_price')
        self.conn.execute('UPDATE quality.fixture SET pricing_node_id=-12345')
        result=evaluate(self.conn,'DQ13')
        self.assertEqual((result['result_status'],result['affected_rows']),('FAIL',1))

    def test_invalid_date_specific_tp_detected(self):
        self.overlay('input_interval','dim_trading_interval')
        self.conn.execute("UPDATE quality.fixture SET interval_id=-12345,trading_date='2025-09-28',trading_period=47")
        self.assertEqual(evaluate(self.conn,'DQ11')['result_status'],'FAIL')

    def test_invalid_boundary_intersection_detected(self):
        # Clone a mapping profile row and give it an invalid-history source
        # ordinal range covering that actual interval. Derived endpoints stay null.
        self.conn.execute('CREATE TABLE quality.fixture AS SELECT * FROM core.dim_nsp_version WHERE boundary_status=\'invalid_boundary\' LIMIT 1')
        self.conn.execute('''UPDATE quality.fixture n SET nsp_version_id=-12345,
            connection_id=x.connection_id,publication_id=x.nsp_snapshot_publication_id,
            original_start_date=x.trading_date::text,original_start_tp='1',
            original_end_date=x.trading_date::text,original_end_tp='50'
            FROM (SELECT f.*,i.trading_date FROM dq_mapping f JOIN quality.input_interval i USING(interval_id) LIMIT 1) x''')
        self.conn.execute('CREATE OR REPLACE VIEW quality.input_nsp AS SELECT * FROM core.dim_nsp_version UNION ALL SELECT * FROM quality.fixture')
        self.assertEqual(evaluate(self.conn,'DQ21')['result_status'],'FAIL')

    def test_unknown_is_not_an_orphan_mapping(self):
        result=evaluate(self.conn,'DQ14')
        self.assertEqual(result['result_status'],'PASS')
        self.assertGreater(self.conn.execute("SELECT sum(rows) FROM dq_mapping WHERE mapping_status='unmapped'").fetchone()[0],0)
        self.assertEqual(evaluate(self.conn,'DQ25')['result_status'],'WARN')

    def test_selected_view_double_count_detected(self):
        self.overlay('input_selected_price','v_selected_price')
        self.assertEqual(evaluate(self.conn,'DQ29')['result_status'],'FAIL')

    def test_zero_total_coverage_is_undefined_not_perfect(self):
        self.conn.execute("UPDATE dq_coverage SET total_value=0,known_value=0,unknown_value=0 WHERE source_name='generation'")
        result=evaluate(self.conn,'DQ25')
        self.assertEqual(result['result_status'],'WARN')
        self.assertTrue(all(x['coverage_pct'] is None for x in result['observed_value']))

    def test_historical_freshness_is_not_a_blocking_failure(self):
        self.conn.execute("SELECT set_config('quality.as_of_date','2030-01-01',true)")
        result=evaluate(self.conn,'DQ28')
        self.assertEqual(result['result_status'],'WARN')
        self.assertTrue(all(x['days_since_latest_period']>0 for x in result['observed_value']))

    def test_existing_flow_diagnostic_matches_phase1(self):
        phase1=json.loads((ROOT/'outputs/pilot/validation.json').read_text(encoding='utf-8'))
        result=evaluate(self.conn,'DQ27')
        for row in result['observed_value']:
            prior=phase1['months'][row['source_month'][:7]]['reconciliation']['mapping']
            self.assertEqual(row['affected_aggregates'],prior['flow_flag_disagreement_matches'])
            self.assertEqual(row['affected_kwh'],prior['flow_flag_disagreement_kwh'])

    def test_coverage_matches_phase1(self):
        phase1=json.loads((ROOT/'outputs/pilot/validation.json').read_text(encoding='utf-8'))
        for code,source in [('DQ23','prices'),('DQ24','reconciliation'),('DQ25','generation')]:
            for row in evaluate(self.conn,code)['observed_value']:
                prior=phase1['months'][row['source_month'][:7]][source]['mapping']
                if source=='prices': expected=prior['unknown_zone_rows']
                elif source=='generation': expected=prior['unknown_zone_kwh']
                else: expected=next(x['unknown_zone_kwh'] for x in prior['by_flow'] if x['flow']=='Offtake')
                self.assertEqual(row['unknown_value'],expected)


if __name__=='__main__': unittest.main()
