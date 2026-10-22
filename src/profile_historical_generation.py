"""Offline source-code/activity profile; no classification inference or downloads."""
import csv
import json
from collections import defaultdict
from decimal import Decimal
from ingestion.acquisition import write_json
from warehouse.db import ROOT


def main():
    manifest=json.loads((ROOT/'outputs/scale_up/source_manifest.json').read_text(encoding='utf-8'))
    result={}
    for slot,vid in sorted(manifest['selected'].items()):
        if not slot.startswith('generation/'): continue
        version=manifest['versions'][vid]
        pairs=defaultdict(lambda:dict(daily_rows=0,kwh=Decimal(0)))
        activity=defaultdict(set)
        zeros=0
        with (ROOT/version['local_path']).open(encoding='utf-8-sig',newline='') as f:
            for row in csv.DictReader(f):
                values=[Decimal(row[f'TP{n}']) for n in range(1,51) if row[f'TP{n}']!='']
                pair=(row['Fuel_Code'],row['Tech_Code'])
                pairs[pair]['daily_rows']+=1
                pairs[pair]['kwh']+=sum(values)
                zeros+=bool(values) and all(x==0 for x in values)
                activity[(row['Gen_Code'],row['POC_Code'],row['Nwk_Code'])].add(row['Trading_Date'])
        result[slot.split('/')[1]]=dict(sha256=version['sha256'],
            pairs=[dict(fuel=f,technology=t,daily_rows=v['daily_rows'],kwh=str(v['kwh'])) for (f,t),v in sorted(pairs.items())],
            all_zero_daily_rows=zeros,connection_series=len(activity),
            series_date_counts=[dict(generator=k[0],poc=k[1],network=k[2],observed_dates=len(v),first=min(v),last=max(v)) for k,v in sorted(activity.items())])
    pilot={'2025-09','2026-04','2026-08'}
    prior={(p['fuel'],p['technology']) for m,v in result.items() if m in pilot for p in v['pairs']}
    all_pairs={(p['fuel'],p['technology']) for v in result.values() for p in v['pairs']}
    report=dict(months=result,pairs_not_in_original_pilot=sorted(all_pairs-prior),
                note='Sparse activity is diagnostic, not fabricated zero rows or automatic incomplete-file rejection.')
    write_json(ROOT/'outputs/scale_up/generation_source_profile.json',report)
    print(json.dumps(dict(months=len(result),distinct_pairs=len(all_pairs),new_pairs=sorted(all_pairs-prior))))

if __name__=='__main__': main()
