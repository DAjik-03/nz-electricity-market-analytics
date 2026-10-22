"""Phase 0 evidence and time-contract checks, without a database or network."""
import hashlib
import json
import sys
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from audit_mapping_and_time import trading_intervals


class TradingTimeTests(unittest.TestCase):
    def test_nz_transition_days_2024_to_2026(self):
        for day, expected in [('2024-04-07',50),('2024-09-29',46),('2025-04-06',50),
                              ('2025-09-28',46),('2026-04-05',50),('2026-09-27',46),('2026-08-01',48)]:
            with self.subTest(day=day):
                self.assertEqual(len(trading_intervals(date.fromisoformat(day))), expected)

    def test_autumn_repeated_hour_keeps_distinct_instants(self):
        rows = trading_intervals(date(2026,4,5))
        self.assertEqual(rows[4]['start_local'], '2026-04-05T02:00:00+13:00')
        self.assertEqual(rows[6]['start_local'], '2026-04-05T02:00:00+12:00')
        self.assertEqual(rows[4]['fold'], 0)
        self.assertEqual(rows[6]['fold'], 1)
        self.assertNotEqual(rows[4]['start_utc'], rows[6]['start_utc'])

    def test_spring_skips_nonexistent_local_hour(self):
        rows = trading_intervals(date(2026,9,27))
        self.assertEqual(rows[3]['start_local'], '2026-09-27T01:30:00+12:00')
        self.assertEqual(rows[4]['start_local'], '2026-09-27T03:00:00+13:00')
        self.assertFalse(any(x['start_local'][11:13]=='02' for x in rows))

    def test_all_intervals_contiguous_over_three_calendar_years(self):
        day = date(2024,1,1)
        previous_end = None
        while day < date(2027,1,1):
            rows = trading_intervals(day)
            self.assertIn(len(rows), [46,48,50])
            for number,row in enumerate(rows,1):
                start,end = map(datetime.fromisoformat,[row['start_utc'],row['end_utc']])
                self.assertEqual(end-start, timedelta(minutes=30))
                self.assertEqual(row['trading_period'],number)
                if previous_end is not None:
                    self.assertEqual(start,previous_end)
                previous_end=end
            day += timedelta(days=1)

    def test_energy_power_conversion(self):
        # A 500 kWh interval is 0.5 MWh and averages 1 MW, on DST days too.
        for day in [date(2026,4,5),date(2026,9,27),date(2026,8,1)]:
            row=trading_intervals(day)[4]
            hours=(datetime.fromisoformat(row['end_utc'])-datetime.fromisoformat(row['start_utc'])).total_seconds()/3600
            self.assertEqual((500/1000)/hours,1)


class AuditEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((ROOT/'outputs/audit/source_manifest.json').read_text())
        cls.profiles=json.loads((ROOT/'outputs/audit/profiles.json').read_text())
        cls.mapping=json.loads((ROOT/'outputs/audit/mapping_and_time.json').read_text())

    def test_four_original_files_match_recorded_hashes_and_sizes(self):
        self.assertEqual({x['source_name'] for x in self.manifest['files']},{'prices','reconciliation','generation','nsp'})
        self.assertEqual(len(self.manifest['files']),4)
        for item in self.manifest['files']:
            payload=(ROOT/item['local_path']).read_bytes()
            self.assertEqual(hashlib.sha256(payload).hexdigest(),item['sha256'])
            self.assertEqual(len(payload),item['file_size_bytes'])

    def test_selected_natural_keys_unique(self):
        indexes={'prices':0,'reconciliation':1,'generation':1,'nsp':1}
        for source,index in indexes.items():
            self.assertEqual(self.profiles[source]['candidate_keys'][index]['duplicate_rows_beyond_first'],0)

    def test_price_month_full_grid_and_no_nonfinite(self):
        profile=self.profiles['prices']
        self.assertEqual(profile['point_series_coverage'],{'1488':246})
        self.assertEqual(profile['rows'],246*31*48)
        self.assertEqual(profile['measure']['non_finite'],0)

    def test_reconciliation_price_join_has_no_loss_or_fanout(self):
        evidence=self.mapping['reconciliation_to_prices']
        self.assertEqual(evidence['missing_price_rows'],0)
        self.assertEqual(evidence['offtake_kwh_without_price'],0)
        self.assertEqual(evidence['aggregate_rows'],self.mapping['reconciliation_to_nsp']['input_aggregate_rows'])

    def test_effective_nsp_joins_unique_for_volume_and_generation(self):
        for source in ['reconciliation_to_nsp','generation_to_nsp']:
            evidence=self.mapping[source]
            self.assertEqual(evidence['rows_without_nsp'],0)
            self.assertEqual(evidence['rows_with_multiple_nsp'],0)

    def test_known_quality_exceptions_are_preserved(self):
        self.assertGreater(self.mapping['prices_to_nsp']['rows_without_nsp'],0)
        self.assertGreater(self.mapping['reconciliation_to_nsp']['kwh_without_unambiguous_zone'],0)
        self.assertGreater(self.profiles['generation']['candidate_keys'][0]['duplicate_rows_beyond_first'],0)
        self.assertEqual(self.profiles['generation']['measure']['nulls'],0)
        self.assertFalse(self.mapping['time']['historical_dst_source_files_tested'])

    def test_actual_august_clock_labels_match_calendar(self):
        self.assertEqual(self.mapping['time']['distinct_source_clock_labels_tested'],1488)
        self.assertEqual(self.mapping['time']['clock_mismatches'],0)

    def test_embedded_generation_route_preserves_rows_and_price_coverage(self):
        route=self.mapping['generation_to_prices_after_official_parent_route']
        self.assertEqual(route['input_rows'],route['routed_rows'])
        self.assertEqual(route['missing_price_rows'],0)
        self.assertEqual(route['kwh_without_price'],0)


if __name__=='__main__':
    unittest.main(verbosity=2)
