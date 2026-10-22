"""Failure contracts and DST/mapping/version regressions (synthetic unit fixtures)."""
import copy
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ingestion.acquisition import acquire, digest, listing_entries, load_config, restore_pinned, store_payload, verify_version, write_json
from ingestion.intervals import boundary, day_intervals
from ingestion.mapping import map_effective
from ingestion.parsers import attach_intervals, check_key, parse_month, read_source
from ingestion.revisions import reconciliation_delta


class AcquisitionTests(unittest.TestCase):
    def test_incomplete_files_are_rejected(self):
        payload = b'<table><tr><td><a href="202608_FinalEnergyPrices.csv">complete</a></td></tr><tr><td><a href="202609_FinalEnergyPrices.csv">incomplete</a></td></tr><tr><td><a href="202512_FinalEnergyPrices_INCOMPLETE.csv">x</a></td></tr></table>'
        accepted, rejected = listing_entries(payload, 'https://example.test/', 'prices')
        self.assertEqual([x['period'] for x in accepted], ['202608'])
        self.assertEqual(len(rejected), 2)
        self.assertTrue(all(x['reason'] == 'explicitly_incomplete' for x in rejected))

    def test_same_filename_revisions_keep_both_immutable_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = {'raw_directory': 'data/raw'}
            manifest = {'versions': {}}
            choice = dict(source='prices', filename='202608_FinalEnergyPrices.csv', month='2026-08')
            first = store_payload(root, config, choice, b'first', {}, 'https://example.test', manifest)
            metadata = copy.deepcopy(manifest)
            self.assertEqual(store_payload(root, config, choice, b'first', {}, 'https://example.test', manifest), first)
            self.assertEqual(manifest, metadata)
            second = store_payload(root, config, choice, b'revised', {}, 'https://example.test', manifest)
            self.assertNotEqual(first, second)
            self.assertEqual(len(manifest['versions']), 2)
            self.assertEqual(verify_version(root, manifest['versions'][first]).read_bytes(), b'first')

    def test_corrupt_raw_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manifest = {'versions': {}}
            choice = dict(source='prices', filename='x.csv')
            version = store_payload(root, {'raw_directory':'raw'}, choice, b'original', {}, '', manifest)
            (root / manifest['versions'][version]['local_path']).write_bytes(b'corrupt')
            with self.assertRaisesRegex(ValueError, 'corrupted'):
                store_payload(root, {'raw_directory':'raw'}, choice, b'original', {}, '', manifest)

    def test_failed_refresh_preserves_selected_version(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            config = dict(manifest='manifest.json', evidence_directory='evidence', raw_directory='raw')
            original = dict(format_version=1, versions={}, selected={'old': 'pinned'})
            write_json(root / 'manifest.json', original)
            discovered = {'selected': {'prices/2026-08': dict(source='prices', filename='x.csv', source_url='x')}}
            with patch('ingestion.acquisition.discover', return_value=discovered):
                with self.assertRaises(OSError):
                    acquire(root, config, True, fetcher=lambda url: (_ for _ in ()).throw(OSError('offline')))
            self.assertEqual(json.loads((root / 'manifest.json').read_text())['selected'], original['selected'])

    def test_json_idempotency(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.json'
            write_json(path, {'a': 1})
            stamp = path.stat().st_mtime_ns
            write_json(path, {'a': 1})
            self.assertEqual(stamp, path.stat().st_mtime_ns)

    def test_config_limits_historical_scope(self):
        config = load_config(ROOT / 'config/project_config.yml')
        self.assertEqual(len(config['pilot_months']), 3)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.yml'
            import yaml
            config['pilot_months'].append('2025-08')
            path.write_text(yaml.safe_dump(config))
            with self.assertRaises(ValueError):
                load_config(path)

    def test_restore_rejects_changed_publisher_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_json(root / 'manifest.json', dict(selected={'prices/2026-08':'v'}, versions={'v':dict(local_path='raw/missing.csv',
                source_url='https://example.test', filename='missing.csv', sha256=digest(b'original'))}))
            with self.assertRaisesRegex(ValueError, 'Publisher bytes changed'):
                restore_pinned(root, {'manifest':'manifest.json'}, fetcher=lambda url: (b'revised', {}, url))
            self.assertFalse((root / 'raw/missing.csv').exists())

    def test_reconciliation_revision_is_replacement_not_addition(self):
        common = dict(TradingDate='2026-08-01', TradingPeriod=1, Network='N', Participant='R', FlowDirection='Offtake')
        previous = pd.DataFrame([dict(common, PointOfConnection=p, KilowattHours=k) for p,k in [('A',10),('B',20),('C',30)]])
        current = pd.DataFrame([dict(common, PointOfConnection=p, KilowattHours=k) for p,k in [('A',12),('B',20),('D',40)]])
        delta = reconciliation_delta(previous, current)
        self.assertEqual([delta[x] for x in ['inserted_keys','removed_keys','changed_measure_keys','unchanged_keys']], [1,1,1,1])
        self.assertEqual(delta['signed_total_kwh_change'], 12)


class ParserTests(unittest.TestCase):
    def test_real_calendar_folds_and_gaps(self):
        fall = day_intervals('2026-04-05')
        spring = day_intervals('2025-09-28')
        self.assertEqual(len(fall), 50)
        self.assertEqual(len(spring), 46)
        self.assertEqual([fall[i]['fold'] for i in [4, 6]], [0, 1])
        self.assertNotEqual(fall[4]['interval_start_utc'], fall[6]['interval_start_utc'])
        self.assertFalse(any(x['local_start'][11:13] == '02' for x in spring))

    def test_invalid_spring_period_rejected(self):
        frame = pd.DataFrame(dict(TradingDate=['2025-09-28'], TradingPeriod=[48]))
        with self.assertRaisesRegex(ValueError, 'outside actual NZ day'):
            attach_intervals(frame, '2025-09')

    def test_wrong_month_and_fractional_tp_rejected(self):
        for day, tp in [('2026-04-01', 1), ('2025-09-01', 1.5)]:
            with self.assertRaises(ValueError):
                attach_intervals(pd.DataFrame(dict(TradingDate=[day], TradingPeriod=[tp])), '2025-09')

    def test_schema_additions_and_duplicate_headers_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'prices.csv'
            for header in ['TradingDate,TradingPeriod,PointOfConnection,DollarsPerMegawattHour,Extra',
                           'TradingDate,TradingPeriod,PointOfConnection,DollarsPerMegawattHour,TradingDate']:
                path.write_text(header + '\n')
                with self.assertRaisesRegex(ValueError, 'Schema drift'):
                    read_source(path, 'prices')

    def test_natural_key_collision_rejected(self):
        frame = pd.DataFrame(dict(TradingDate=['2026-08-01']*2, TradingPeriod=[1]*2, PointOfConnection=['X']*2))
        with self.assertRaisesRegex(ValueError, 'natural-key collision'):
            check_key(frame, 'prices')

    def test_generation_dst_padding_and_nulls(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'generation.csv'
            row = dict(Site_Code='S', POC_Code='P', Nwk_Code='N', Gen_Code='G', Fuel_Code='ELE', Tech_Code='BAT', Trading_Date='2025-09-28')
            row.update({f'TP{i}': 1 if i <= 46 else None for i in range(1, 51)})
            pd.DataFrame([row]).to_csv(path, index=False)
            frame, report = parse_month(path, 'generation', '2025-09')
            self.assertEqual(len(frame), 46)
            self.assertEqual(report['structural_padding_cells'], 4)
            row['TP47'] = 0
            pd.DataFrame([row]).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'structural DST padding'):
                parse_month(path, 'generation', '2025-09')
            row['TP47'], row['TP1'] = None, None
            pd.DataFrame([row]).to_csv(path, index=False)
            with self.assertRaisesRegex(ValueError, 'null data in a valid'):
                parse_month(path, 'generation', '2025-09')

    def test_end_inclusive_maps_to_next_interval_start(self):
        self.assertEqual(boundary('2026-04-05', 50, end=True), boundary('2026-04-06', 1))
        self.assertEqual(boundary('2025-09-28', 46, end=True), boundary('2025-09-29', 1))
        with self.assertRaises(ValueError):
            boundary('2014-09-28', 48, end=True)


class MappingTests(unittest.TestCase):
    def test_effective_boundary_and_unknown_are_explicit(self):
        nsp = pd.DataFrame([dict(NSP='N', **{'POC code':'P', 'Network participant':'NW', 'Zone':'A', 'Island':'NI',
            'Network reporting region ID':'1', 'I flow':'1', 'X flow':'1', 'Embedded under POC code':None,
            'Embedded under network participant':None}, source_start_position=2026080101, source_end_position=2026080102, boundary_valid=True),
            dict(NSP='N', **{'POC code':'P', 'Network participant':'NW', 'Zone':'B', 'Island':'NI',
            'Network reporting region ID':'2', 'I flow':'1', 'X flow':'1', 'Embedded under POC code':None,
            'Embedded under network participant':None}, source_start_position=2026080103, source_end_position=9999123150, boundary_valid=True)])
        frame = pd.DataFrame(dict(TradingDate=['2026-08-01']*3, TradingPeriod=[2,3,4], PointOfConnection=['P','P','Q'], Network=['NW']*3))
        mapped, report = map_effective(frame, nsp, True)
        self.assertEqual(mapped.mapped_Zone.tolist(), ['A','B','Unknown'])
        self.assertEqual(report['rows_without_nsp'], 1)
        nsp.loc[1, 'boundary_valid'] = False
        with self.assertRaisesRegex(ValueError, 'invalid NSP boundary'):
            map_effective(frame, nsp, True)


if __name__ == '__main__':
    unittest.main()
