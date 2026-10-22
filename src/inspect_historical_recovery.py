"""Read-only recovery evidence; never reruns discovery or changes publications."""
import json
import argparse
from datetime import datetime
from zoneinfo import ZoneInfo
from warehouse.db import ROOT,connect
from ingestion.acquisition import verify_version,write_json,utc_now

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify-raw',action='store_true')
    args=parser.parse_args()
    manifest=json.loads((ROOT/'outputs/scale_up/source_manifest.json').read_text(encoding='utf-8'))
    if args.verify_raw:
        for vid in manifest['selected'].values(): verify_version(ROOT,manifest['versions'][vid])
    with connect() as c:
        result=dict(at=utc_now(),manifest_slots=len(manifest['selected']),verified_raw_slots=len(manifest['selected']) if args.verify_raw else None)
        queries={
            'publications':'SELECT to_jsonb(p) FROM metadata.source_publication p ORDER BY publication_id',
            'selections':'SELECT to_jsonb(s) FROM metadata.publication_selection s ORDER BY source_name,source_month',
            'attempts':'SELECT to_jsonb(a) FROM metadata.load_attempt a ORDER BY attempt_id',
            'activity':"SELECT jsonb_build_object('pid',pid,'state',state,'wait_type',wait_event_type,'wait',wait_event,'query',left(query,200)) FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()",
        }
        for name,query in queries.items(): result[name]=[r[0] for r in c.execute(query)]
        result['database_bytes']=c.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    day=datetime.now(ZoneInfo('Pacific/Auckland')).strftime('%Y%m%d')
    write_json(ROOT/f'outputs/scale_up/recovery_{day}.json',result)
    print(json.dumps({k:result[k] for k in ['verified_raw_slots','database_bytes','activity']},indent=2))
    print('Publications',[(p['publication_id'],p['source_name'],p['source_month'],p['status'],p['fact_rows']) for p in result['publications']])
    print('Selections',len(result['selections']))
    print('Running attempts',[a for a in result['attempts'] if a['status']=='running'])

if __name__=='__main__': main()
