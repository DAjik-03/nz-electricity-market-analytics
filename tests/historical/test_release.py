"""Acceptance of the selected continuous release, separate from frozen pilot tests."""
import json
import sys
import unittest
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from warehouse.db import connect
from warehouse.loader import LOCK_ID
from ingestion.acquisition import verify_version
from validate_and_promote_historical import selection_evidence


def native_values(value):
    """Compare retained exact decimals numerically, preserving flow labels."""
    if isinstance(value,list): return [native_values(item) for item in value]
    if isinstance(value,str):
        try: return Decimal(value)
        except InvalidOperation: return value
    return value


class HistoricalReleaseTests(unittest.TestCase):
    def test_complete_candidate_was_validated_before_promotion(self):
        evidence=json.loads((ROOT/'outputs/scale_up/candidate_validation.json').read_text(encoding='utf-8'))
        self.assertEqual(evidence['status'],'validated_and_promoted')
        self.assertEqual(evidence['selected_publications'],37)
        self.assertTrue(evidence['constraint_checks_pass'])
        self.assertEqual(evidence['calendar'],dict(days=365,intervals=17520,all_utc_local_fields_pass=True))
        self.assertTrue(all(p['native_totals_pass'] for p in evidence['publications']))
        self.assertTrue(all(native_values(p['native_totals']['staging'])==native_values(p['native_totals']['core']) for p in evidence['publications']))
        self.assertEqual(len(evidence['selection_identity_before']['rows']),10)
        self.assertEqual(len(evidence['selection_identity_after']['rows']),37)
        self.assertEqual(evidence['selection_identity_after']['sha256'],selection_evidence(self.conn)['sha256'])
        self.assertEqual({p['publication_id'] for p in evidence['publications']},{r[0] for r in self.conn.execute('SELECT publication_id FROM metadata.publication_selection')})

    @classmethod
    def setUpClass(cls):
        cls.conn=connect()
        cls.conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        cls.conn.execute('SET jit=off')
        cls.manifest=json.loads((ROOT/'outputs/scale_up/source_manifest.json').read_text(encoding='utf-8'))

    @classmethod
    def tearDownClass(cls):
        cls.conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))
        cls.conn.close()

    def test_all_37_selected_versions_match_verified_manifest(self):
        expected=[]
        for vid in self.manifest['selected'].values():
            version=self.manifest['versions'][vid]
            verify_version(ROOT,version)
            expected.append((version['source'],version['sha256']))
        actual=self.conn.execute("SELECT p.source_name,p.sha256 FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id) WHERE p.status='loaded' ORDER BY 1,2").fetchall()
        self.assertEqual(len(actual),37)
        self.assertEqual(actual,sorted(expected))

    def test_complete_annual_calendar_and_actual_fact_dst(self):
        self.assertEqual(self.conn.execute("SELECT count(DISTINCT trading_date),count(*),min(trading_date)::text,max(trading_date)::text FROM core.dim_trading_interval").fetchone(),(365,17520,'2025-09-01','2026-08-31'))
        for view in ['v_selected_price','v_selected_reconciled_volume','v_selected_generation']:
            rows=self.conn.execute(f"SELECT i.trading_date::text,count(DISTINCT i.trading_period) FROM core.{view} f JOIN core.dim_trading_interval i USING(interval_id) WHERE i.trading_date IN ('2025-09-28','2026-04-05') GROUP BY 1 ORDER BY 1").fetchall()
            self.assertEqual(rows,[('2025-09-28',46),('2026-04-05',50)])

    def test_december_lineage_and_native_grain(self):
        row=self.conn.execute("SELECT v.publication_id,v.source_form,v.constituent_count,p.fact_rows FROM metadata.v_source_packaging v JOIN metadata.publication_selection s USING(publication_id) JOIN metadata.source_publication p USING(publication_id) WHERE v.source_name='prices' AND v.source_month='2025-12-01'").fetchone()
        self.assertEqual(row[1:],('official_daily_aggregate',31,361584))
        children=self.conn.execute('SELECT source_metadata FROM metadata.v_source_constituent WHERE publication_id=%s ORDER BY trading_date',(row[0],)).fetchall()
        version=self.manifest['versions'][self.manifest['selected']['prices/2025-12']]
        self.assertEqual([r[0] for r in children],sorted(version['constituents'],key=lambda x:x['trading_date']))
        self.assertTrue(all(r[0]['price_status']=='final' for r in children))
        for r in children: verify_version(ROOT,r[0])
        self.assertEqual(self.conn.execute("SELECT count(*) FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id) WHERE p.filename LIKE '%incomplete%'").fetchone()[0],0)

    def test_full_release_dq_and_rolling_scope(self):
        self.assertEqual(self.conn.execute('SELECT count(*) FROM quality.v_latest_coverage').fetchone()[0],36)
        self.assertEqual(self.conn.execute("SELECT count(*) FROM quality.v_latest_dq_results WHERE result_status='FAIL' AND is_blocking").fetchone()[0],0)
        self.assertEqual(self.conn.execute("SELECT count(*),count(*) FILTER(WHERE full_30_day_window) FROM analytics.mart_market_daily_rolling_30d WHERE scope='National'").fetchone(),(365,336))
        self.assertEqual(self.conn.execute("SELECT count(*),min(population_intervals),max(population_intervals) FROM analytics.mart_price_pressure_threshold").fetchone(),(6,17520,17520))

    def test_repeat_refresh_evidence_matches_current_release(self):
        evidence=json.loads((ROOT/'outputs/analytics/determinism.json').read_text(encoding='utf-8'))
        self.assertTrue(all(evidence['checks'].values()))
        current=self.conn.execute('SELECT analytics.input_fingerprint()').fetchone()[0]
        self.assertTrue(all(run['fingerprint']==current for run in evidence['runs']))
        self.assertIn('mart_market_daily_rolling_30d',evidence['runs'][-1]['view_hashes'])
