"""Read-only PostgreSQL import and independent Phase 5 reconciliation.

No DQ/refresh/migration execution. --offline reuses the hashed validation snapshot.
This does not execute DAX or certify a Power BI report.
"""
from pathlib import Path
import argparse
import datetime as dt
import decimal
import gzip
import hashlib
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict

ROOT=Path(__file__).resolve().parents[1]
HERE=ROOT/'powerbi'
OUT=ROOT/'outputs/powerbi'
OUT.mkdir(parents=True,exist_ok=True)
def load(p): return json.loads(p.read_text(encoding='utf-8'))
def dump(p,v): p.write_text(json.dumps(v,indent=2,ensure_ascii=False,default=str)+'\n',encoding='utf-8')
def hashfile(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def near(a,b,tol=1e-7):
    assert math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=tol),(a,b)
def number(v): return None if v is None else float(v)
def percentile(values,q):
    v=sorted(values); r=(len(v)-1)*q; k=int(r)
    return v[k]+(v[min(k+1,len(v)-1)]-v[k])*(r-k)

def acquire():
    sys.path.insert(0,str(ROOT/'src'))
    from warehouse.db import connect
    manifest=load(HERE/'package_manifest.json')
    data={}; schemas={}; hashes={}
    with connect() as c:
        c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute('SET LOCAL max_parallel_workers_per_gather=0')
        c.execute("SET LOCAL statement_timeout='180s'")
        read_only=c.execute('SHOW transaction_read_only').fetchone()[0]
        before=c.execute('SELECT refresh_id,dq_run_id,input_fingerprint,is_current FROM analytics.refresh_status').fetchall()
        assert before==[(38,5,manifest['input_fingerprint'],True)],before
        types=dict(c.execute('SELECT oid,typname FROM pg_type').fetchall())
        for name in manifest['sql_queries']:
            path=HERE/'sql'/f'{name}.sql'
            statement=path.read_text(encoding='utf-8')
            assert not re.search(r'\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|REFRESH|CREATE)\b',statement,re.I)
            cur=c.execute(statement)
            columns=[d.name for d in cur.description]
            schemas[name]=[dict(name=d.name,postgres_type=types[d.type_code]) for d in cur.description]
            rows=[dict(zip(columns,r)) for r in cur.fetchall()]
            data[name]=rows
            hashes[name]=hashfile(path)
            print(name,len(rows),flush=True)
        after=c.execute('SELECT refresh_id,dq_run_id,input_fingerprint,is_current FROM analytics.refresh_status').fetchall()
        assert before==after
        c.execute('ROLLBACK')
    # Validation-only compressed mart exports, not raw source files or a replacement production source.
    payload=json.dumps(data,default=str,sort_keys=True).encode()
    (OUT/'import_snapshot.json.gz').write_bytes(gzip.compress(payload,mtime=0))
    dump(OUT/'source_validation.json',dict(read_only=read_only,before=before,after=after,sql_sha256=hashes,
        snapshot_sha256=hashfile(OUT/'import_snapshot.json.gz'),rows={k:len(v) for k,v in data.items()},columns=schemas))
    return json.loads(payload)

def validate(data):
    checks=[]
    for name,sha in load(OUT/'source_validation.json')['sql_sha256'].items():
        assert hashfile(HERE/'sql'/f'{name}.sql')==sha, 'SQL changed; acquire a new read-only snapshot'
    n=data['FactNational']; z=data['FactZone']; intervals=data['DimInterval']; events=data['Events']; signals=data['RegionalSignal']
    ids={r['interval_id'] for r in intervals}
    assert len(n)==len(ids)==len(intervals)==17520
    assert len({r['interval_id'] for r in n})==17520
    assert len(z)==105120 and len({(r['zone'],r['interval_id']) for r in z})==len(z)
    assert {r['zone'] for r in z}=={'CNI','LNI','LSI','UNI','USI','Unknown'}
    assert all(r['interval_id'] in ids for r in z)
    assert len(signals)==17520 and len({r['interval_id'] for r in signals})==17520
    checks.append('National/Zone/interval/RegionalSignal keys, foreign keys and separate grains')
    byday=Counter(r['trading_date'] for r in intervals)
    assert len(byday)==365 and min(byday)=='2025-09-01' and max(byday)=='2026-08-31'
    assert byday['2025-09-28']==46 and byday['2026-04-05']==50
    assert all(byday[r['trading_date']]==r['expected_periods'] for r in intervals)
    assert sum(r['fold']==1 for r in intervals)==2
    assert {r['utc_offset_minutes'] for r in intervals}=={720,780}
    checks.append('365 NZ dates, 17,520 UTC intervals, 46/50 DST days and fold/offset preservation')
    threshold={r['zone']:r for r in data['Threshold']}
    near(threshold['National']['p99_price'],227.84134669510667)
    assert len(threshold)==6 and 'Unknown' not in threshold
    assert sum(r['is_price_pressure'] for r in n)==176
    assert len([e for e in events if e['scope']=='National'])==68
    assert len(events)==429 and sum(float(e['duration_hours']) for e in events if e['scope']=='National')==88
    assert sum(r['zones_flagged']>0 for r in signals)==264
    assert len({r['episode_id'] for r in signals if r['episode_id'] is not None})==108
    assert sum(r['zone_only'] for r in signals)==88
    assert sum(r['zones_flagged']==5 for r in signals)==104
    checks.append('Fixed six P99 thresholds; 68/176/88 National and 264/108/88 deduplicated regional measures')
    members=data['EventInterval']; event_ids={e['event_id'] for e in events}
    assert len(members)==1056 and len({(r['event_id'],r['interval_id']) for r in members})==1056
    assert all(r['event_id'] in event_ids and r['interval_id'] in ids for r in members)
    membercounts=Counter(r['event_id'] for r in members)
    assert all(membercounts[e['event_id']]==e['interval_count'] for e in events)
    checks.append('1,056 scoped event memberships; no date-only joins or membership fanout')
    imap={r['interval_id']:r for r in intervals}
    monthly=defaultdict(list)
    for r in n: monthly[imap[r['interval_id']]['trading_date'][:7]].append(r)
    for saved in load(ROOT/'outputs/analysis/monthly_overview.json'):
        month=saved.get('source_month',saved.get('month'))[:7]
        rows=monthly[month]; prices=[float(r['weighted_price']) for r in rows if r['weighted_price'] is not None]
        near(sum(float(r['price_numerator']) for r in rows)/sum(float(r['priced_offtake_kwh']) for r in rows),saved['weighted_price'])
        near(percentile(prices,.95),saved['p95_interval_price'])
        near(statistics.pstdev(prices),saved['price_volatility_pop'])
        near(sum(float(r['offtake_kwh']) for r in rows)/1e6,saved['demand_gwh'])
    release=load(ROOT/'outputs/analysis/release_population.json')[0]
    annual=sum(float(r['price_numerator']) for r in n)/sum(float(r['priced_offtake_kwh']) for r in n)
    near(annual,release['weighted_price'])
    naive=statistics.mean(float(r['weighted_price']) for r in load(ROOT/'outputs/analysis/monthly_overview.json'))
    assert abs(annual-naive)>.01
    checks.append('All 12 monthly weighted prices/P95/population SD/demand; annual ratio differs from average of monthly prices')
    for r in n:
        near(sum(float(r[c]) for c in ['renewable_kwh','fossil_kwh','storage_kwh','unclassified_kwh']),r['generation_kwh'],1e-5)
    knownz=defaultdict(float); unknown=defaultdict(float)
    for r in z:
        # SQL SUM ignores NULL. This is only an aggregate reconciliation;
        # the exported/imported record keeps NULL (not an invented zero).
        if r['offtake_kwh'] is not None:
            (unknown if r['zone']=='Unknown' else knownz)[r['interval_id']]+=float(r['offtake_kwh'])
    for r in n:
        near(knownz[r['interval_id']]+unknown[r['interval_id']],r['offtake_kwh'],1e-5)
        near(knownz[r['interval_id']],r['known_zone_offtake_kwh'],1e-5)
    assert sum(unknown.values())>0
    classification=data['Classification']
    assert next(r for r in classification if r['fuel_code']=='ELE' and r['tech_code']=='BAT')['energy_status']=='Storage'
    checks.append('Unknown retained in National; component sums, coverage denominators and ELE/BAT Storage preserved')
    quality=data['DQResults']; assert len(quality)==29
    assert Counter(r['result_status'] for r in quality)=={'PASS':21,'WARN':8}
    savedquality=load(ROOT/'outputs/analysis/monthly_quality.json')
    assert data['SourceQuality']==savedquality or sorted(data['SourceQuality'],key=lambda r:(r['source_name'],r['source_month']))==[{k:v for k,v in r.items() if k!='dq_run_status'} for r in sorted(savedquality,key=lambda r:(r['source_name'],r['source_month']))]
    checks.append('Retained DQ 29 rules / 21 PASS / 8 WARN / 0 FAIL; source/month coverage equals Phase 5')
    b=data['DemandBenchmark'][0]
    for k,v in load(ROOT/'outputs/analysis/demand_hour_adjusted.json')[0].items(): near(b[k],v)
    near(b['pressure_mean_mw'],5371.152659090909)
    near(b['matched_control_mean_mw'],5031.6687421848,1e-6)
    checks.append('Full-release pressure-weighted month/hour comparator reconciled; all 176 matched')
    controls=defaultdict(list)
    pressure=[r for r in n if r['is_price_pressure']]
    stratum=lambda r:(imap[r['interval_id']]['trading_date'][:7],imap[r['interval_id']]['local_hour'])
    for r in n:
        if not r['is_price_pressure']: controls[stratum(r)].append(r)
    savedgen=load(ROOT/'outputs/analysis/generation_hour_adjusted.json')[0]
    pooled={}
    for label,col in [('listed','generation_kwh'),('renewable','renewable_kwh'),('fossil','fossil_kwh'),('storage','storage_kwh'),('unclassified','unclassified_kwh')]:
        pvals=[float(r[col]) for r in pressure]
        cvals=[statistics.mean(float(c[col]) for c in controls[stratum(r)]) for r in pressure]
        near(statistics.mean(pvals)/1000,savedgen['pressure_'+label+'_mwh'])
        near(statistics.mean(cvals)/1000,savedgen['control_'+label+'_mwh'])
        pooled[label]=(sum(pvals),sum(cvals))
    for i,prefix in enumerate(('pressure','control')):
        near(100*pooled['renewable'][i]/(pooled['renewable'][i]+pooled['fossil'][i]),savedgen[prefix+'_renewable_primary_pct'])
        near(100*(pooled['listed'][i]-pooled['unclassified'][i])/pooled['listed'][i],savedgen[prefix+'_classification_pct'])
    checks.append('Generation pressure/matched comparator absolute components and pooled primary/classification shares')
    smap={r['interval_id']:r for r in signals}
    populations={
        'National pressure':lambda r:r['is_price_pressure'],
        'No National pressure':lambda r:not r['is_price_pressure'],
        'Zone-only pressure':lambda r:smap[r['interval_id']]['zone_only'],
        'No National or Zone pressure':lambda r:not r['is_price_pressure'] and smap[r['interval_id']]['zones_flagged']==0}
    for saved in load(ROOT/'outputs/analysis/spread_comparison.json'):
        rows=[r for r in n if populations[saved['population']](r)]
        vals=[float(r['regional_price_spread']) for r in rows if r['regional_price_spread'] is not None]
        assert len(rows)==saved['intervals'] and len(vals)==saved['complete_intervals']
        for actual,key in [(statistics.mean(vals),'mean_spread'),(percentile(vals,.5),'median_spread'),(percentile(vals,.95),'p95_spread'),(max(vals),'max_spread')]:near(actual,saved[key])
    checks.append('Four regional-spread populations: count, eligible count, mean, median, P95 and maximum')
    emap={r['event_id']:r for r in events}; nmap={r['interval_id']:r for r in n}
    for case in load(ROOT/'outputs/analysis/representative_events.json'):
        e=emap[case['event_id']]
        for col in ['duration_hours','interval_count','weighted_price','peak_weighted_price','p99_threshold']: near(e[col],case[col])
        rows=[nmap[r['interval_id']] for r in members if r['event_id']==e['event_id']]
        near(statistics.mean(float(r['demand_mw']) for r in rows),case['national_mean_demand_mw'])
        near(100*sum(float(r['renewable_kwh']) for r in rows)/sum(float(r['renewable_kwh'])+float(r['fossil_kwh']) for r in rows),case['national_renewable_primary_pct'])
    checks.append('E1–E5 scoped metrics and independent National context reconciled')
    # Date slicing uses stored flags/thresholds and stable full-release episode IDs.
    march=[r for r in n if imap[r['interval_id']]['trading_date'].startswith('2026-03')]
    assert all(r['is_price_pressure']==(float(r['weighted_price'])>=float(threshold['National']['p99_price'])) for r in march)
    assert len(march)==1488
    for row in z:
        if row['zone'] in threshold:
            expected=row['weighted_price'] is not None and float(row['weighted_price'])>=float(threshold[row['zone']]['p99_price'])
            assert row['is_price_pressure']==expected
    rels=load(HERE/'relationships.json')
    assert all(r['direction']=='single' for r in rels)
    assert not any(r['many_table'] in ['Events','Threshold','DemandBenchmark','DQResults'] for r in rels)
    assert not any(r['one_table']=='EventInterval' for r in rels)
    checks.append('Date-slice reference checks and unambiguous one-way graph; fixed thresholds/benchmarks disconnected')
    catalog=load(HERE/'measure_catalog.json')
    assert len({m['name'] for m in catalog})==len(catalog)
    schema=load(OUT/'source_validation.json')['columns']
    schema.update(DimDate=[{'name':'Date'}],DimMonth=[{'name':'MonthStart'}])
    for m in catalog:
        for table,col in re.findall(r'\b(\w+)\[([^\]]+)\]',m['expression']):
            assert table in schema and col in [x['name'] for x in schema[table]],(m['name'],table,col)
        without_columns=re.sub(r'\b\w+\[[^\]]+\]','',m['expression'])
        for ref in re.findall(r'\[([^\]]+)\]',without_columns):
            assert ref in {x['name'] for x in catalog},(m['name'],ref)
    checks.append('DAX table/column references resolve against live import schema (not DAX engine execution)')
    keys={'FactNational':['interval_id'],'FactZone':['zone','interval_id'],'DimInterval':['interval_id'],
          'DimZone':['zone'],'Threshold':['scope','zone'],'Events':['event_id'],
          'EventInterval':['event_id','interval_id'],'RegionalSignal':['interval_id'],
          'SourceQuality':['source_name','source_month'],'DQResults':['rule_id'],'Release':['refresh_id'],
          'Classification':['classification_version','fuel_code','tech_code'],'DemandBenchmark':[]}
    contract=[]
    for name,cols in keys.items():
        rows=data[name]
        assert len({tuple(r[c] for c in cols) for r in rows})==len(rows),(name,cols)
        contract.append(dict(table=name,query='powerbi/sql/'+name+'.sql',unique_key=cols or ['singleton'],
            rows=len(rows),window='2025-09-01 through 2026-08-31' if name!='Classification' else 'classification version 1 reference',
            scope=('National including Unknown' if name in ('FactNational','DemandBenchmark') else
                   'Zone including explicit Unknown' if name in ('FactZone','DimZone') else
                   'Five known Zones only' if name=='RegionalSignal' else 'Reference / scoped context; see model specification'),
            refresh='Import; ReleaseGate requires refresh 38 / DQ 5 / approved fingerprint; no warehouse writes'))
    dump(OUT/'reporting_input_contract.json',contract)
    result=dict(passed=True,checks=checks,check_groups=len(checks),dax_engine_validated=False,
        power_query_runtime_validated=False,report_rendered=False,existing_suite=load(ROOT/'outputs/analysis/full_test_results.json'),
        national_weighted_price=annual,naive_monthly_average=naive,sql_source_evidence='source_validation.json',
        limits='PostgreSQL/Python reconciliation and static graph/reference checks; Desktop filter/render/credential acceptance remains manual.')
    dump(OUT/'validation.json',result)
    print(json.dumps(dict(passed=True,check_groups=len(checks),dax_engine_validated=False)))

if __name__=='__main__':
    ap=argparse.ArgumentParser(); ap.add_argument('--offline',action='store_true'); args=ap.parse_args()
    if args.offline:
        assert hashfile(OUT/'import_snapshot.json.gz')==load(OUT/'source_validation.json')['snapshot_sha256']
        data=json.loads(gzip.decompress((OUT/'import_snapshot.json.gz').read_bytes()))
    else: data=acquire()
    validate(data)
