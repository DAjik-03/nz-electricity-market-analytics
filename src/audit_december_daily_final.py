"""Bounded December audit: immutable daily finals plus non-eligible monthly diagnostic."""
import json
import argparse
import logging
import re
from datetime import date
from urllib.parse import unquote,urljoin

from lxml import html
from ingestion.acquisition import fetch,store_payload,verify_version,write_json,utc_now,digest
from historical.daily_final import parse_prices,compare_populations,constituent_identity,build_aggregate
from ingestion.intervals import day_intervals
from warehouse.db import ROOT

OUT=ROOT/'outputs/scale_up/december'
PAGE='https://www.emi.ea.govt.nz/Wholesale/Datasets/DispatchAndPricing/FinalEnergyPrices'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--offline',action='store_true',help='Revalidate retained exact bytes and discovery; no network')
    parser.add_argument('--refresh',action='store_true',help='Observe possible new daily versions, preserving old bytes')
    args=parser.parse_args()
    if args.offline and args.refresh: raise ValueError('Offline and refresh are mutually exclusive')
    OUT.mkdir(parents=True,exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s')
    path=OUT/'source_manifest.json'
    manifest=json.loads(path.read_text(encoding='utf-8')) if path.exists() else dict(format_version=1,versions={},observed={})
    payload=b'' if args.offline else fetch(PAGE)[0]
    entries=json.loads((OUT/'discovery.json').read_text())['files'] if args.offline else {}
    for a in ([] if args.offline else html.fromstring(payload).xpath('//a[@href]')):
        name=unquote(a.get('href').rsplit('/',1)[-1])
        if re.fullmatch(r'202512\d{2}_FinalEnergyPrices\.csv',name):
            day=date(2025,12,int(name[6:8])).isoformat()
            entries[day]=dict(filename=name,source_url=urljoin(PAGE+'/',a.get('href')),
                              source='prices_daily',month='2025-12',trading_date=day,
                              source_form='official_daily',price_status='final',prepared_at_unzoned=None)
    expected={date(2025,12,d).isoformat() for d in range(1,32)}
    if not args.offline:
        write_json(OUT/'discovery.json',dict(retrieved_at_utc=utc_now(),url=PAGE,sha256=digest(payload),
                                           files=entries,missing_dates=sorted(expected-set(entries))))
    if set(entries)!=expected: raise ValueError('Not all 31 daily final files are listed')
    audit=json.loads((ROOT/'outputs/scale_up/availability_audit.json').read_text(encoding='utf-8'))
    diagnostic=next(s for s in audit['missing'] if s['source']=='prices' and s['month']=='2025-12')['rejected_candidates'][0]
    choices=list(sorted(entries.items()))+ [('incomplete_monthly',dict(diagnostic,source='prices_monthly_diagnostic',
             month='2025-12',source_form='official_monthly_incomplete',price_status='incomplete',prepared_at_unzoned=None))]
    daily={};reports=[];sources=[];monthly=None
    for key,choice in choices:
        if key in manifest['observed'] and not args.refresh:
            version=manifest['versions'][manifest['observed'][key]]
            raw=verify_version(ROOT,version).read_bytes()
        else:
            logging.info('Audit acquisition %s',choice['filename'])
            raw,headers,resolved=fetch(choice['source_url'])
            vid=store_payload(ROOT,{'raw_directory':'data/raw'},choice,raw,headers,resolved,manifest)
            manifest['observed'][key]=vid
            version=manifest['versions'][vid]
            write_json(path,manifest)
        if key=='incomplete_monthly':
            monthly=parse_prices(raw)
        else:
            population=parse_prices(raw,expected_date=key,require_complete=True)
            if set(population) & set(daily): raise ValueError('Daily-union key collision')
            daily.update(population);sources.append(version)
            reports.append(dict(date=key,rows=len(population),periods=len({k[1] for k in population}),schema_pass=True,natural_key_pass=True))
    comparison=compare_populations(daily,monthly)
    observed={(k[0],k[1]) for k in daily}
    expected_pairs={(d,p) for d in expected for p in range(1,len(day_intervals(d))+1)}
    identity=constituent_identity(sources)
    gates=dict(final_file_count_31=len(sources)==31,all_final=all(s['price_status']=='final' for s in sources),
               schema_dates_tp_keys=True,month_date_tp_coverage=observed==expected_pairs,
               zero_overlap_value_conflicts=comparison['mismatching_overlap_values']==0,
               deterministic_constituent_identity=identity==constituent_identity(list(reversed(sources))))
    result=dict(at=utc_now(),daily_files=reports,comparison=comparison,gates=gates,
                source_form='official_daily_aggregate',constituent_identity=identity,
                status='audit_passed_pending_packaging' if all(gates.values()) else 'BLOCKED',
                postgres_loaded=False,diagnostic_monthly_eligible=False)
    if all(gates.values()):
        group_id,artifact=build_aggregate(daily,sources)
        same_id,repeated=build_aggregate(dict(reversed(list(daily.items()))),list(reversed(sources)))
        if artifact!=repeated or group_id!=same_id: raise ValueError('Reconstruction is not deterministic')
        choice=dict(source='prices',month='2025-12',prepared_at_unzoned=None,
                    filename='202512_DailyFinalAggregate.csv.gz',source_form='official_daily_aggregate',
                    source_url=f'derived:official-daily-final:{group_id}',price_status='final',
                    constituent_identity=group_id,constituents=sources,
                    transformation='Exact-date schema/key/calendar validated union; sorted CSV; gzip mtime=0, constituent-bound member name')
        vid=store_payload(ROOT,{'raw_directory':'data/raw'},choice,artifact,{},choice['source_url'],manifest)
        manifest.setdefault('derived_groups',{})[group_id]=vid
        manifest['eligible_derived_version']=vid
        write_json(path,manifest)
        gates['idempotent_artifact_bytes']=artifact==repeated
        gates['explicit_source_lineage']=len(manifest['versions'][vid]['constituents'])==31
        result.update(status='PASSED',derived_version=vid,derived_sha256=digest(artifact))
    write_json(OUT/'audit.json',result)
    print(json.dumps(dict(status=result['status'],daily_files=len(sources),gates=gates,
                         comparison={k:v for k,v in comparison.items() if k not in ('value_mismatches','only_daily','only_incomplete_monthly')},
                         only_daily_keys=comparison['only_daily']['key_count'],
                         only_monthly_keys=comparison['only_incomplete_monthly']['key_count']),indent=2))
    if not all(gates.values()): raise SystemExit('December acceptance gate failed; do not scale up')


if __name__=='__main__': main()
