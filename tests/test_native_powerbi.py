"""Generated source contracts; these tests do not substitute for Desktop QA."""
import hashlib
import json
import sys
import unittest
import tempfile
import shutil
from unittest.mock import patch
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'powerbi'))
from build_native_project import P, REPORT, MODEL, build, read, uid
from validate_native_project import validate
from repair_runtime_definitions import repair

class NativePowerBI(unittest.TestCase):
    def test_microsoft_schemas_and_references(self):
        self.assertEqual(validate()['approved_layout_containers'],34)

    def test_targeted_repair_is_idempotent(self):
        # Never mutate the real Desktop-saved project while running tests.
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp)/'Report'
            shutil.copytree(REPORT, report, ignore=shutil.ignore_patterns('.pbi'))
            with patch('repair_runtime_definitions.REPORT', report):
                repair()
                files=[p for p in report.rglob('*') if p.is_file()]
                before={p:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in files}
                repair()
                self.assertEqual(before,{p:(hashlib.sha256(p.read_bytes()).hexdigest(),p.stat().st_mtime_ns) for p in before})

    def test_disconnected_threshold_and_event_bridge(self):
        r=read(P/'relationships.json')
        self.assertFalse(any(x['one_table'] in ['FactNational','FactZone','EventInterval','Threshold'] for x in r))
        self.assertFalse(any(x['many_table'] in ['Threshold','DemandBenchmark'] for x in r))
        catalog={x['name']:x['expression'] for x in read(P/'measure_catalog.json')}
        for n in ['Full-period P99 threshold','Zone Full-period P99 threshold']:
            self.assertNotIn('PERCENTILE',catalog[n].upper())
            self.assertIn('Threshold',catalog[n])

    def test_event_bookmarks_are_scoped_to_one_slicer(self):
        for i in range(1,6):
            b=read(REPORT/'definition/bookmarks'/f'{uid("bookmark.E"+str(i))}.bookmark.json')
            self.assertEqual(b['options']['targetVisualNames'],[uid('P4.1.selector')])
            self.assertTrue(b['options']['suppressDisplay'])
            self.assertFalse(b['options'].get('suppressData',False))
            self.assertEqual(b['explorationState']['activeSection'],uid('page4'))
            state=b['explorationState']['sections'][uid('page4')]['visualContainers'][uid('P4.1.selector')]
            f=state['singleVisual']['objects']['merge']['general'][0]['properties']['filter']['filter']
            self.assertTrue(f['Where'])

    def test_interactions_prevent_scope_leakage(self):
        p=read(REPORT/'definition/pages'/uid('page2')/'page.json')
        pairs={(i['source'],i['target']):i['type'] for i in p['visualInteractions']}
        for target in ['P2.1.1','P2.2.1','P2.4','P2.6','P2.7']:
            self.assertEqual(pairs[uid('2.zone'),uid(target)],'NoFilter')
        self.assertEqual(pairs[uid('2.date'),uid('P2.7')],'NoFilter')
        p=read(REPORT/'definition/pages'/uid('page4')/'page.json')
        self.assertEqual(p['pageBinding']['acceptsFilterContext'],'None')
        for i in p['visualInteractions']:
            if i['source']==uid('P4.4') and i['target']==uid('P4.5.1'):
                self.assertEqual(i['type'],'NoFilter')

    def test_sources_preserve_unknown_and_release_gate(self):
        # Native partitions include the exact approved M text, not regenerated SQL.
        for query in (P/'queries').glob('*.pq'):
            target=MODEL/'definition/tables'/f'{query.stem}.tmdl'
            if not target.exists(): target=MODEL/'definition/expressions.tmdl'
            lines=[s.strip() for s in target.read_text(encoding='utf-8').splitlines()]
            prefix='expression '+query.stem+' = '
            lines=[s[len(prefix):] if s.startswith(prefix) else s for s in lines]
            for line in query.read_text(encoding='utf-8-sig').splitlines():
                if line.strip(): self.assertIn(line.strip(),lines)

if __name__=='__main__': unittest.main()
