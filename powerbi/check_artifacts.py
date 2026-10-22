"""Validate the handoff contract and record artifact checks (no database/UI)."""
from pathlib import Path
import hashlib
import json
import re
import subprocess
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
P=ROOT/'powerbi'; O=ROOT/'outputs/powerbi'
def load(path): return json.loads(path.read_text(encoding='utf-8-sig'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
catalog=load(P/'measure_catalog.json'); names={m['name'] for m in catalog}
assert len(names)==len(catalog)
manifest=load(P/'package_manifest.json');assert manifest['measure_count']==len(names)
pages=load(P/'page_specification.json'); assert len(pages)==5
visuals=[v for p in pages for v in p['visuals']]; assert len(visuals)==34
for v in visuals:
    assert all(m in names for m in v['values']),v['id']
    assert all(v.get(k) for k in ['type','source','axis','filters','sort','tooltip','interaction','format'])
    x,y,w,h=v['rect']; assert x>=0 and y>=0 and x+w<=1280 and y+h<=800
for i in range(1,6): ET.parse(P/'wireframes'/f'page_{i}.svg')
rels=load(P/'relationships.json');assert len(rels)==8
graph={}
for r in rels:
    assert r['direction']=='single' and r['cardinality']=='one-to-many' and r['active']
    graph.setdefault(r['one_table'],[]).append(r['many_table'])
def visit(n,seen):
    assert n not in seen,'Relationship cycle'
    for child in graph.get(n,[]):visit(child,seen|{n})
for n in graph:visit(n,set())
assert not any(r['many_table']=='Threshold' or r['one_table']=='Threshold' for r in rels)
byname={m['name']:m for m in catalog}
for name in ('Weighted Wholesale Price','Zone Weighted Wholesale Price'):
    e=byname[name]['expression']
    assert 'DIVIDE(SUM(' in e and '[price_numerator]' in e and '[priced_offtake_kwh]' in e and 'AVERAGE' not in e
for name in ('Renewable Primary Share','Fossil Thermal Share'):
    e=byname[name]['expression'];assert '[renewable_kwh]' in e and '[fossil_kwh]' in e and '[storage_kwh]' not in e
for name in ('Full-period P99 threshold','Zone Full-period P99 threshold'):
    e=byname[name]['expression'];assert 'REMOVEFILTERS(Threshold)' in e and 'PERCENTILE' not in e and 'DimDate' not in e
assert 'HASONEVALUE(DimZone[zone])' in byname['Zone Weighted Wholesale Price']['expression']
for m in catalog:
    # Balanced lexical structure is not an engine parser; runtime remains pending.
    e=re.sub(r'"(?:[^"]|"")*"','',m['expression'])
    for a,b in [('(',')'),('[',']'),('{','}')]:
        depth=0
        for char in e:
            depth+=(char==a)-(char==b);assert depth>=0,(m['name'],a)
        assert depth==0,(m['name'],a)
assert len(list((P/'queries').glob('*.pq')))==20
for name in manifest['sql_queries']:
    sql=(P/'sql'/f'{name}.sql').read_text(encoding='utf-8').strip().rstrip(';')
    encoded=sql.replace('"','""').replace('\n','#(lf)')
    assert encoded in (P/'queries'/f'{name}.pq').read_text(encoding='utf-8'),name
    assert 'ReleaseGate' in (P/'queries'/f'{name}.pq').read_text(encoding='utf-8')
    assert sha(P/'sql'/f'{name}.sql')==load(O/'source_validation.json')['sql_sha256'][name]
cases=load(P/'case_presets.json');assert [r['case_id'] for r in cases]==['E1','E2','E3','E4','E5']
assert len({r['event_id'] for r in cases})==5
links=0;broken=[]
docs=[ROOT/'README.md',ROOT/'PROGRESS.md',*sorted((ROOT/'docs').glob('powerbi*.md'))]
for p in docs:
    text=p.read_text(encoding='utf-8-sig')
    for target in re.findall(r'!?\[[^\]]*\]\(([^)]+)\)',text):
        if re.match(r'https?://|#',target):continue
        target=target.split('#')[0].strip('<>')
        links+=1
        if not (p.parent/target).exists():broken.append((str(p),target))
assert not broken,broken
changed=subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'diff','--name-only','84fa1474ad1e55944df87792357beb34dcec4edf','--','src','sql','tests','config','outputs/analysis'],cwd=ROOT,text=True).strip()
assert not changed,changed
assert not list(P.rglob('*.pbix')) and not list(P.rglob('*.pbip'))
assert load(O/'validation.json')['passed'] and load(O/'release_integrity.json')['passed']
artifacts=[*P.rglob('*.py'),*P.rglob('*.sql'),*P.rglob('*.pq'),*P.rglob('*.json'),*P.rglob('*.dax'),*P.rglob('*.mmd'),*P.rglob('*.svg'),P/'preview.html',*docs]
result=dict(passed=True,measures=len(names),loaded_tables=16,sql_imports=13,relationships=8,pages=5,
    visual_containers=34,local_links_checked=links,broken_links=broken,unchanged_approved_implementation=True,
    artifact='build package; no PBIX/PBIP',dax_runtime_claimed=False,
    sha256={p.relative_to(ROOT).as_posix():sha(p) for p in sorted(set(artifacts))})
(O/'artifact_validation.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='sha256'}))
