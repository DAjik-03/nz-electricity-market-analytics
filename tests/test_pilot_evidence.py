"""Actual full-file evidence regression checks; run validation before these tests."""
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from ingestion.acquisition import digest
from ingestion.validation import code_fingerprint
from ingestion.parsers import parse_nsp


class PilotEvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads((ROOT / 'outputs/pilot/validation.json').read_text(encoding='utf-8'))
        cls.manifest = json.loads((ROOT / 'outputs/pilot/source_manifest.json').read_text(encoding='utf-8'))

    def test_evidence_matches_code_and_source_selection(self):
        self.assertEqual(self.result['code_sha256'], code_fingerprint())
        self.assertEqual(self.result['selected_versions'], self.manifest['selected'])
        self.assertEqual(len(self.manifest['selected']), 10)
        for vid in self.manifest['selected'].values():
            item = self.manifest['versions'][vid]
            self.assertEqual(digest((ROOT / item['local_path']).read_bytes()), item['sha256'])

    def test_real_dst_rows_all_three_sources(self):
        for month, day, expected in [('2025-09','2025-09-28',46), ('2026-04','2026-04-05',50)]:
            for source in ['prices', 'reconciliation', 'generation']:
                evidence = self.result['months'][month][source]['dst_days'][0]
                self.assertEqual(evidence['date'], day)
                self.assertEqual(evidence['observed_periods'], list(range(1,expected+1)))
                self.assertGreater(evidence['rows'], expected)
                self.assertIn(str(expected), [x['TradingPeriod'] for x in evidence['actual_rows']])
            self.assertEqual(self.result['months'][month]['reconciliation']['local_start_time_validation']['mismatched_rows'], 0)

    def test_keys_schemas_and_eligible_months(self):
        for month in self.result['months'].values():
            self.assertTrue(month['eligibility']['eligible_for_versioned_pilot'])
            for source in ['prices', 'reconciliation', 'generation']:
                self.assertEqual(month[source]['natural_key']['duplicates'], 0)
                self.assertEqual(month[source]['schema']['missing'], [])
                self.assertEqual(month[source]['schema']['added'], [])
                self.assertFalse(month[source]['schema']['reordered'])
                self.assertFalse(month[source]['calendar']['missing_intervals'])
            self.assertEqual(month['generation']['valid_interval_null_cells'], 0)

    def test_invalid_nsp_history_not_silently_fixed(self):
        nsp = self.result['nsp']
        self.assertEqual(len(nsp['invalid_boundaries']), 3)
        self.assertEqual(nsp['overlap_pairs'], 0)
        self.assertEqual(nsp['inclusive_source_overlaps'], 0)
        self.assertGreater(nsp['intraday_adjacent_pairs'], 500)

    def test_actual_intraday_nsp_transition_selects_one_version(self):
        source = self.manifest['versions'][self.manifest['selected']['nsp/snapshot']]
        frame, report = parse_nsp(ROOT / source['local_path'])
        example = report['intraday_transition_examples'][0]
        versions = frame.loc[frame.NSP == example['NSP']]
        old_end = int(example['End date'].replace('-',''))*100 + int(example['End TP'])
        old_match = versions.loc[(versions.source_start_position <= old_end) & (versions.source_end_position >= old_end)]
        new_match = versions.loc[(versions.source_start_position <= old_end+1) & (versions.source_end_position >= old_end+1)]
        self.assertEqual(len(old_match),1)
        self.assertEqual(len(new_match),1)
        self.assertNotEqual(old_match.index[0],new_match.index[0])
        self.assertEqual(old_match.effective_end_utc_exclusive.iloc[0],new_match.effective_start_utc.iloc[0])

    def test_unknown_and_sparse_activity_remain_visible(self):
        for month in self.result['months'].values():
            self.assertGreater(month['prices']['mapping']['unknown_zone_rows'], 0)
            self.assertGreater(month['generation']['series_days']['short_series'], 0)
            self.assertEqual(month['reconciliation']['mapping']['rows_without_nsp'], 0)
            self.assertEqual(month['reconciliation']['direct_price_coverage']['unmatched_rows'], 0)
        self.assertGreater(self.result['months']['2025-09']['generation']['mapping']['rows_without_nsp'], 0)
        self.assertEqual(self.result['months']['2026-08']['generation']['mapping']['rows_without_nsp'], 0)

    def test_unchanged_bytes_are_not_invented_revisions(self):
        self.assertTrue(all(x['same_sha256'] for x in self.result['source_version_comparison_to_phase0']))
        for month in self.result['months'].values():
            self.assertEqual(month['reconciliation']['observed_distinct_content_versions'], 1)
            self.assertEqual(month['reconciliation']['revision_comparisons'], [])


if __name__ == '__main__':
    unittest.main()
