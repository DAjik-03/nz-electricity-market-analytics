"""Independent standard-library recomputation of saved Phase 5 SQL results."""
import bisect
from collections import Counter, defaultdict
from datetime import datetime
import gzip
import hashlib
import json
import math
import re
from pathlib import Path
import statistics

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs/analysis'


def load(name):
    path = OUT/(name+'.json')
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else json.loads(gzip.decompress((OUT/(name+'.json.gz')).read_bytes()))


def quantile(values, fraction):
    values = sorted(values)
    position = (len(values)-1)*fraction
    lo, hi = math.floor(position), math.ceil(position)
    return values[lo]+(values[hi]-values[lo])*(position-lo)


def check_close(actual, expected):
    assert math.isclose(float(actual), float(expected), rel_tol=1e-10, abs_tol=1e-7), (actual, expected)


def main():
    checks = []
    manifest = load('query_manifest')
    assert manifest['read_only']=='on' and manifest['before']==manifest['after']
    assert manifest['matches_approved_phase4b']
    assert manifest['approved_view_hashes']==json.loads((ROOT/'outputs/analytics/refresh_38.json').read_text(encoding='utf-8'))['view_hashes']
    assert len(manifest['before']['selection'])==37
    for migration in manifest['before']['migrations']:
        actual=hashlib.sha256((ROOT/migration['path']).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
        assert actual==migration['sha256']
    initial=load('initial_query_manifest')
    repeat={name:meta['result_sha256']==manifest['queries'][name]['result_sha256'] for name,meta in initial['queries'].items()}
    assert all(repeat.values()), 'Repeated SQL results changed'
    assert initial['before']['cache']==manifest['before']['cache']
    assert initial['before']['selection']==manifest['before']['selection']
    checks.append('All seven approved mart hashes, applied migration checksums and repeated SQL outputs unchanged after full tests')
    assert manifest['before']['refresh'][0]['input_fingerprint']=='b87ef82066c5bcd7055d350da94b28811467c3e0c2687489fb8363c5cd6e2cf6'
    for name, meta in manifest['queries'].items():
        result = load(name)
        assert len(result)==meta['rows']
        assert hashlib.sha256(json.dumps(result,sort_keys=True,default=str).encode()).hexdigest()==meta['result_sha256'], name
        parts=re.split(r'^-- name: ([a-z0-9_]+)\s*$',(ROOT/meta['sql']).read_text(encoding='utf-8'),flags=re.M)
        sql=dict(zip(parts[1::2],parts[2::2]))[name]
        assert hashlib.sha256(sql.encode()).hexdigest()==meta['sql_sha256'], 'SQL changed since execution: '+name
    checks.append('Read-only snapshot, approved fingerprint, 37 selections and all saved output hashes')
    n = load('national_intervals')
    z = load('zone_flags')
    assert len(n)==17520==len({r['interval_id'] for r in n})
    assert len(z)==87600==len({(r['interval_id'],r['zone']) for r in z})
    assert n[0]['trading_date']=='2025-09-01' and n[-1]['trading_date']=='2026-08-31'
    dates = Counter(r['trading_date'] for r in n)
    assert len(dates)==365 and dates['2025-09-28']==46 and dates['2026-04-05']==50
    assert all(a['end_utc']==b['start_utc'] for a,b in zip(n,n[1:]))
    checks.append('National and Zone grain, full date range, UTC continuity and actual DST populations')
    def nums(pop,key): return [float(r[key]) for r in pop]
    def total(pop,key): return math.fsum(nums(pop,key))
    def mean(pop,key): return statistics.fmean(nums(pop,key))
    threshold=manifest['before']['thresholds'][0]['p99_price']
    check_close(quantile(nums(n,'weighted_price'),.99),threshold)
    assert all(r['is_price_pressure']==(float(r['weighted_price'])>=threshold) for r in n)
    for month in load('monthly_overview'):
        pop=[r for r in n if r['trading_date'][:7]==month['source_month'][:7]]
        assert len(pop)==month['observed_intervals']
        check_close(total(pop,'price_numerator')/total(pop,'priced_offtake_kwh'),month['weighted_price'])
        check_close(total(pop,'offtake_kwh')/1e6,month['demand_gwh'])
        check_close(total(pop,'generation_kwh')/1e6,month['listed_generation_gwh'])
        check_close(quantile(nums(pop,'weighted_price'),.95),month['p95_interval_price'])
        check_close(statistics.pstdev(nums(pop,'weighted_price')),month['price_volatility_pop'])
        check_close(max(nums(pop,'demand_mw')),month['peak_demand_mw'])
        check_close(100*total(pop,'renewable_kwh')/(total(pop,'renewable_kwh')+total(pop,'fossil_kwh')),month['renewable_primary_share_pct'])
    checks.append('Monthly weighted numerators/denominators, P95, population SD, demand and generation')
    pressure=[r for r in n if r['is_price_pressure']]
    control=[r for r in n if not r['is_price_pressure']]
    for query,key,column in [('pressure_by_month',lambda r:r['trading_date'][:7]+'-01','month'),('pressure_by_hour',lambda r:int(r['local_start'][11:13]),'local_hour'),('pressure_by_day_type',lambda r:'Weekend' if datetime.fromisoformat(r['trading_date']).weekday()>=5 else 'Weekday','day_type')]:
        populations=Counter(key(r) for r in n)
        flagged=Counter(key(r) for r in pressure)
        for row in load(query):
            assert row['all_intervals']==populations[row[column]] and row['pressure_intervals']==flagged[row[column]]
            check_close(100*flagged[row[column]]/populations[row[column]],row['pressure_rate_pct'])
    checks.append('Local month/hour/day-type exposure denominators and flag rates')
    for row in load('demand_comparison'):
        pop=pressure if row['is_price_pressure'] else control
        check_close(mean(pop,'demand_mw'),row['mean_demand_mw'])
        check_close(quantile(nums(pop,'demand_mw'),.5),row['median_demand_mw'])
        check_close(quantile(nums(pop,'demand_mw'),.95),row['p95_demand_mw'])
    strata=defaultdict(list)
    def stratum(row): return row['trading_date'][:7],row['local_start'][11:13]
    for row in control: strata[stratum(row)].append(row)
    adjusted=load('demand_hour_adjusted')[0]
    comparator=statistics.fmean(mean(strata[stratum(r)],'demand_mw') for r in pressure)
    check_close(comparator,adjusted['matched_control_mean_mw'])
    check_close(mean(pressure,'demand_mw')-comparator,adjusted['mean_difference_mw'])
    assert min(len(strata[stratum(r)]) for r in pressure)==adjusted['minimum_control_n']
    monthly_deltas=[]
    for month in sorted({r['trading_date'][:7] for r in pressure}):
        p=[r for r in pressure if r['trading_date'][:7]==month]
        c=[r for r in control if r['trading_date'][:7]==month]
        monthly_deltas.append(dict(month=month,pressure_n=len(p),control_n=len(c),difference_mw=mean(p,'demand_mw')-mean(c,'demand_mw')))
    checks.append('Demand mean/median/P95 and pressure-weighted month/hour comparator independently recomputed')
    g=load('generation_hour_adjusted')[0]
    for key,column in [('generation_kwh','listed'),('renewable_kwh','renewable'),('fossil_kwh','fossil'),('storage_kwh','storage'),('unclassified_kwh','unclassified')]:
        check_close(mean(pressure,key)/1000,g['pressure_'+column+'_mwh'])
        check_close(statistics.fmean(mean(strata[stratum(r)],key) for r in pressure)/1000,g['control_'+column+'_mwh'])
    for row in load('generation_comparison'):
        pop=pressure if row['is_price_pressure'] else control
        r,f,s,u,gwh=[total(pop,k) for k in ['renewable_kwh','fossil_kwh','storage_kwh','unclassified_kwh','generation_kwh']]
        check_close(r+f+s+u,gwh)
        check_close(100*r/(r+f),row['renewable_primary_share_pct'])
        check_close(100*(gwh-u)/gwh,row['classification_coverage_pct'])
        check_close(100*r/gwh,row['renewable_all_listed_lower_pct'])
        check_close(100*(r+u)/gwh,row['renewable_all_listed_upper_pct'])
    checks.append('Absolute generation, pooled primary/listed shares, classification coverage and sensitivity bounds')
    flags=Counter(r['interval_id'] for r in z if r['is_price_pressure'])
    overlap=Counter((flags[r['interval_id']],r['is_price_pressure']) for r in n)
    assert overlap==Counter({(r['zones_flagged'],r['national_pressure']):r['intervals'] for r in load('regional_overlap')})
    episodes=[]
    for row in n:
        if flags[row['interval_id']]:
            if not episodes or episodes[-1][-1]['end_utc']!=row['start_utc']: episodes.append([])
            episodes[-1].append(row)
    saved=load('cross_regional_episodes')
    assert len(saved)==len(episodes)
    for row,episode in zip(saved,episodes):
        assert row['start_utc']==episode[0]['start_utc'] and row['end_utc']==episode[-1]['end_utc']
        assert row['intervals']==len(episode)
    checks.append('Zone overlap deduplicated by interval and analysis-only UTC episodes independently reconstructed')
    by_id={r['interval_id']:r for r in n}
    for row in load('spread_by_zone_pressure'):
        ids=[r['interval_id'] for r in z if r['zone']==row['zone'] and r['is_price_pressure']==row['is_price_pressure']]
        pop=[by_id[i] for i in ids]
        assert len(pop)==row['intervals']==row['complete_intervals']
        check_close(mean(pop,'regional_price_spread'),row['mean_spread'])
        check_close(quantile(nums(pop,'regional_price_spread'),.5),row['median_spread'])
        check_close(quantile(nums(pop,'regional_price_spread'),.95),row['p95_spread'])
    checks.append('Every Zone-specific pressure/non-pressure spread comparison')
    for row in load('spread_comparison'):
        pop={'National pressure':pressure,'No National pressure':control,
             'Zone-only pressure':[r for r in control if flags[r['interval_id']]],
             'No National or Zone pressure':[r for r in control if not flags[r['interval_id']]]}[row['population']]
        assert all(r['represented_zones']==5 and r['expected_zones']==5 for r in pop)
        assert len(pop)==row['intervals']==row['complete_intervals']
        for key,value in [('mean_spread',mean(pop,'regional_price_spread')),('median_spread',quantile(nums(pop,'regional_price_spread'),.5)),('p95_spread',quantile(nums(pop,'regional_price_spread'),.95)),('max_spread',max(nums(pop,'regional_price_spread')))]: check_close(value,row[key])
    checks.append('Spread eligibility, mean/median/P95/max for normal, National and Zone-only pressure')
    events=load('event_investigation')
    demands=sorted(nums(n,'demand_mw'))
    for e in events:
        pop=[r for r in n if e['start_utc']<=r['start_utc']<e['end_utc']]
        assert len(pop)==e['interval_count']
        check_close(len(pop)*.5,e['duration_hours'])
        check_close(total(pop,'price_numerator')/total(pop,'priced_offtake_kwh'),e['national_weighted_price'])
        check_close(mean(pop,'demand_mw'),e['national_mean_demand_mw'])
        check_close(statistics.fmean(100*bisect.bisect_right(demands,float(r['demand_mw']))/len(demands) for r in pop),e['mean_annual_demand_percentile'])
    national=[e for e in events if e['scope']=='National']
    assert sum(e['interval_count'] for e in national)==len(pressure)==176
    assert len(national)==68 and len(events)==429
    checks.append('Every scoped event duration, National context and annual demand cume_dist; event totals')
    # Fixed data-first selection rules, before official context was retrieved.
    choices=[('E1','Highest-peak National event with all five Zones flagged throughout',max([e for e in national if e['minimum_zones_flagged']==5],key=lambda e:float(e['peak_weighted_price']))),
             ('E2','Longest National event; earliest start breaks ties',sorted(national,key=lambda e:(-float(e['duration_hours']),e['start_utc']))[0]),
             ('E3','Largest maximum spread among Zone events with no National flagged interval',max([e for e in events if e['scope']=='Zone' and e['national_pressure_intervals']==0],key=lambda e:float(e['max_spread']))),
             ('E4','Highest-peak isolated National half-hour',max([e for e in national if e['interval_count']==1],key=lambda e:float(e['peak_weighted_price']))),
             ('E5','Lowest mean-demand National event: counterexample to high-demand-only interpretation',min(national,key=lambda e:float(e['national_mean_demand_mw'])))]
    selected=[dict(case_id=case,selection_reason=reason,**e) for case,reason,e in choices]
    (OUT/'representative_events.json').write_text(json.dumps(selected,indent=2)+'\n',encoding='utf-8')
    derived={'monthly_demand_deltas':monthly_deltas,'months_with_positive_demand_difference':sum(r['difference_mw']>0 for r in monthly_deltas),
             'month_count_with_pressure':len(monthly_deltas),'annual_demand_difference_pct':100*(mean(pressure,'demand_mw')/mean(control,'demand_mw')-1),
             'september_march_pressure_share_pct':100*sum(r['trading_date'][:7] in ['2025-09','2026-03'] for r in pressure)/len(pressure),
             'unique_zone_pressure_intervals':sum(flags[r['interval_id']]>0 for r in n), 'cross_regional_episodes':len(episodes),
             'zone_only_intervals':sum(flags[r['interval_id']]>0 for r in control), 'five_zone_pressure_intervals':sum(v==5 for v in flags.values()),
             'all_five_share_of_national_pressure_pct':100*sum(flags[r['interval_id']]==5 for r in pressure)/len(pressure)}
    (OUT/'derived_comparisons.json').write_text(json.dumps(derived,indent=2)+'\n',encoding='utf-8')
    (OUT/'analysis_validation.json').write_text(json.dumps({'passed':True,'checks':checks,'repeat_query_hashes':repeat,'approved_view_hashes_match':True,'applied_migrations':len(manifest['before']['migrations']),'case_ids':[r['event_id'] for r in selected]},indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':len(checks),'derived':derived},indent=2))


if __name__=='__main__': main()
