"""Run explicitly after pilot loading: python -m unittest discover -s tests/warehouse -v.

Synthetic revision/failure fixtures are transactionally rolled back. They never
become observed official publications or replace the retained pilot evidence.
"""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from decimal import Decimal
import psycopg

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from warehouse.db import connect
from warehouse.loader import load_publication, select_publications, validate_publication_totals
from warehouse.validation import collect
from ingestion.intervals import day_intervals
from historical.regression import select_original_pilot_for_test
from warehouse.loader import LOCK_ID
from run_historical_scale_up import recover_interrupted_attempts


def fixture_publication(conn,name,source='reconciliation',month='2026-08-01'):
    return conn.execute('''INSERT INTO metadata.source_publication
      (source_name,source_month,filename,sha256,downloaded_at,file_size_bytes,source_url,manifest_metadata)
      VALUES (%s,%s,%s,%s,now(),1,'fixture:rollback-only','{"fixture":true}') RETURNING publication_id''',
      (source,month,name,hashlib.sha256(name.encode()).hexdigest())).fetchone()[0]


def fixture_volume(conn,pid,kwh='12',flow='Offtake',ordinal=1):
    conn.execute('''INSERT INTO staging.reconciled_volume
      (publication_id,source_row_number,"PointOfConnection","Network","Island","Participant","TradingDate",
       "TradingPeriod","TradingPeriodStartTime","FlowDirection","KilowattHours")
      VALUES (%s,%s,'ABY0111','ALPE','SI','TEST_ONLY','2026-08-01','1','00:00',%s,%s)''',(pid,ordinal,flow,kwh))


def mark_loaded(conn,pid,rows):
    conn.execute("UPDATE metadata.source_publication SET status='loaded',staged_rows=%s,fact_rows=%s,loaded_at=now() WHERE publication_id=%s",(rows,rows,pid))


class PostgreSQLTests(unittest.TestCase):
    def test_interrupted_empty_attempt_recovered_without_source_change(self):
        pid=fixture_publication(self.conn,'fixture-interrupted-empty')
        aid=self.conn.execute("INSERT INTO metadata.load_attempt(publication_id,status) VALUES(%s,'running') RETURNING attempt_id",(pid,)).fetchone()[0]
        with tempfile.TemporaryDirectory() as folder, patch('run_historical_scale_up.OUT',Path(folder)):
            recover_interrupted_attempts(self.conn)
            self.assertTrue((Path(folder)/'interrupted_attempts.json').is_file())
        self.assertEqual(self.conn.execute('SELECT status FROM metadata.load_attempt WHERE attempt_id=%s',(aid,)).fetchone()[0],'failed')
        self.assertEqual(self.conn.execute('SELECT filename,status FROM metadata.source_publication WHERE publication_id=%s',(pid,)).fetchone(),('fixture-interrupted-empty','failed'))

    def test_interrupted_attempt_with_rows_is_not_silently_repaired(self):
        pid=fixture_publication(self.conn,'fixture-interrupted-with-rows')
        fixture_volume(self.conn,pid)
        self.conn.execute("INSERT INTO metadata.load_attempt(publication_id,status) VALUES(%s,'running')",(pid,))
        with self.assertRaisesRegex(ValueError,'committed rows'):
            recover_interrupted_attempts(self.conn)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM staging.reconciled_volume WHERE publication_id=%s',(pid,)).fetchone()[0],1)

    @classmethod
    def setUpClass(cls):
        cls.conn=connect()
        cls.conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        cls.outer=cls.conn.transaction(force_rollback=True)
        cls.outer.__enter__()
        select_original_pilot_for_test(cls.conn)
        cls.conn.execute('SET jit=off')
        cls.result=collect(cls.conn)
        cls.snapshot=cls.conn.execute("SELECT publication_id FROM metadata.publication_selection WHERE source_name='nsp'").fetchone()[0]

    @classmethod
    def tearDownClass(cls):
        cls.outer.__exit__(None,None,None)
        cls.conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))
        cls.conn.close()

    def setUp(self):
        self.tx=self.conn.transaction(force_rollback=True)
        self.tx.__enter__()

    def tearDown(self): self.tx.__exit__(None,None,None)

    def test_staging_and_core_populations_and_totals(self):
        self.assertTrue(all(self.result['checks'].values()))
        self.assertEqual(sum(x['core_rows'] for x in self.result['sources']['reconciliation']),17896294)
        self.assertEqual(sum(x['core_rows'] for x in self.result['sources']['generation']),418710)

    def test_native_totals_guard_all_real_publications(self):
        for pid,source in self.conn.execute('SELECT publication_id,source_name FROM metadata.source_publication WHERE status=\'loaded\'').fetchall():
            validate_publication_totals(self.conn,source,pid)

    def test_sql_calendar_roundtrip_all_fields(self):
        rows=self.conn.execute('''SELECT trading_date,trading_period,start_utc,end_utc,local_start,local_end,
           utc_offset_minutes,end_utc_offset_minutes,is_dst,end_is_dst,fold,end_fold FROM core.dim_trading_interval ORDER BY trading_date,trading_period''')
        for d,tp,start,end,ls,le,off,eoff,dst,edst,fold,efold in rows:
            p=day_intervals(d)[tp-1]
            self.assertEqual([start.isoformat(),end.isoformat(),ls.isoformat(),le.isoformat(),off,eoff,dst,edst,fold,efold],
                [p['interval_start_utc'],p['interval_end_utc'],p['local_start'][:19],p['local_end'][:19],
                 p['utc_offset_minutes'],p['end_utc_offset_minutes'],p['is_dst'],p['end_is_dst'],p['fold'],p['end_fold']])
        self.assertEqual(self.result['calendar']['intervals'],4368)

    def test_nsp_invalid_is_not_open_and_source_fields_survive(self):
        self.assertEqual({x['status']:x['rows'] for x in self.result['nsp_boundaries']},
            {'valid_bounded':1837,'valid_open':777,'invalid_boundary':3})
        mismatches=self.conn.execute('''SELECT count(*) FROM core.dim_nsp_version n JOIN staging.network_supply_point s
          USING(publication_id,source_row_number) WHERE n.original_start_date IS DISTINCT FROM s."Start date"
          OR n.original_start_tp IS DISTINCT FROM s."Start TP" OR n.original_end_date IS DISTINCT FROM s."End date"
          OR n.original_end_tp IS DISTINCT FROM s."End TP"''').fetchone()[0]
        self.assertEqual(mismatches,0)

    def test_hwa_kiwi_not_backfilled(self):
        rows=self.conn.execute('''SELECT p.source_month,count(*),sum(f.kilowatt_hours),bool_and(f.nsp_version_id IS NULL)
          FROM core.v_selected_generation f JOIN metadata.source_publication p USING(publication_id)
          JOIN core.dim_connection c USING(connection_id)
          WHERE c.poc IN ('HWA1101','HWA1102') AND c.network='KIWI' AND p.source_month<'2026-08-01'
          GROUP BY 1 ORDER BY 1''').fetchall()
        self.assertEqual([(r[1],r[2],r[3]) for r in rows],[(2876,Decimal('11040597'),True),(2884,Decimal('10319602'),True)])

    def test_reconciliation_revisions_selected_transactionally(self):
        ids=[]
        for name,amount in [('fixture-old','12'),('fixture-new','15')]:
            pid=fixture_publication(self.conn,name)
            fixture_volume(self.conn,pid,amount)
            self.assertEqual(self.conn.execute('SELECT core.load_volume(%s,%s)',(pid,self.snapshot)).fetchone()[0],1)
            self.conn.execute('DROP TABLE load_mapping')
            mark_loaded(self.conn,pid,1)
            ids.append(pid)
        select_publications(self.conn,[ids[0]])
        self.assertEqual(self.conn.execute('SELECT sum(kilowatt_hours) FROM core.v_selected_reconciled_volume WHERE publication_id=ANY(%s)',(ids,)).fetchone()[0],12)
        select_publications(self.conn,[ids[1]])
        self.assertEqual(self.conn.execute('SELECT sum(kilowatt_hours) FROM core.v_selected_reconciled_volume WHERE publication_id=ANY(%s)',(ids,)).fetchone()[0],15)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM core.fact_reconciled_volume WHERE publication_id=ANY(%s)',(ids,)).fetchone()[0],2)

    def test_unloaded_publication_cannot_be_selected(self):
        pid=fixture_publication(self.conn,'fixture-unloaded')
        with self.assertRaises(psycopg.errors.RaiseException):
            with self.conn.transaction(): select_publications(self.conn,[pid])

    def test_duplicate_business_grain_fails(self):
        pid=fixture_publication(self.conn,'fixture-duplicate')
        fixture_volume(self.conn,pid,ordinal=1)
        fixture_volume(self.conn,pid,ordinal=2)
        with self.assertRaises(psycopg.errors.UniqueViolation):
            with self.conn.transaction(): self.conn.execute('SELECT core.load_volume(%s,%s)',(pid,self.snapshot))
        self.assertEqual(self.conn.execute('SELECT count(*) FROM core.fact_reconciled_volume WHERE publication_id=%s',(pid,)).fetchone()[0],0)

    def test_generation_padding_rejected_not_zeroed(self):
        pid=fixture_publication(self.conn,'fixture-padding','generation','2025-09-01')
        self.conn.execute('''INSERT INTO staging.generation_daily
          (publication_id,source_row_number,"Site_Code","POC_Code","Nwk_Code","Gen_Code","Fuel_Code","Tech_Code","Trading_Date","TP47")
          VALUES (%s,1,'T','ABY0111','ALPE','fixture-plant','ELE','BAT','2025-09-28','0')''',(pid,))
        with self.assertRaisesRegex(psycopg.errors.RaiseException,'padding'):
            with self.conn.transaction(): self.conn.execute('SELECT core.load_generation(%s,%s)',(pid,self.snapshot))

    def test_foreign_key_and_flow_constraints_enforced(self):
        with self.assertRaises(psycopg.errors.ForeignKeyViolation):
            with self.conn.transaction():
                self.conn.execute("INSERT INTO core.fact_price VALUES (-999,-999,-999,1,1)")
        pid=fixture_publication(self.conn,'fixture-flow')
        fixture_volume(self.conn,pid,flow='Invented')
        with self.assertRaises(psycopg.errors.CheckViolation):
            with self.conn.transaction(): self.conn.execute('SELECT core.load_volume(%s,%s)',(pid,self.snapshot))

    def test_failed_copy_transaction_does_not_leave_loaded_rows(self):
        self.assert_loader_rollback('1', True, 'Injected failure')

    def test_native_precision_loss_rolls_back_after_transform(self):
        # Numeric(20,8) would round this synthetic value; totals gate rejects it.
        self.assert_loader_rollback('1.000000001', False, 'native totals')

    def assert_loader_rollback(self, amount, fail_after_copy, message):
        folder=ROOT/'data/interim'
        with tempfile.TemporaryDirectory(dir=folder) as directory:
            path=Path(directory)/'fixture_price.csv'
            payload=f'TradingDate,TradingPeriod,PointOfConnection,DollarsPerMegawattHour\n2026-08-01,1,FIXTURE,{amount}\n'.encode()
            path.write_bytes(payload)
            version=dict(source='prices',month='2026-08',filename=path.name,sha256=hashlib.sha256(payload).hexdigest(),
                snapshot_date=None,prepared_at_unzoned=None,downloaded_at_utc='2026-09-19T00:00:00+00:00',
                http_last_modified=None,etag=None,bytes=len(payload),source_url='fixture:rollback-only',local_path=path.relative_to(ROOT).as_posix())
            with self.assertRaisesRegex((RuntimeError,ValueError),message):
                load_publication(self.conn,version,fail_after_copy=fail_after_copy)
            pid,status=self.conn.execute('SELECT publication_id,status FROM metadata.source_publication WHERE sha256=%s',(version['sha256'],)).fetchone()
            self.assertEqual(status,'failed')
            self.assertEqual(self.conn.execute('SELECT count(*) FROM staging.final_energy_price WHERE publication_id=%s',(pid,)).fetchone()[0],0)
            self.assertEqual(self.conn.execute('SELECT count(*) FROM core.fact_price WHERE publication_id=%s',(pid,)).fetchone()[0],0)


if __name__=='__main__': unittest.main()
