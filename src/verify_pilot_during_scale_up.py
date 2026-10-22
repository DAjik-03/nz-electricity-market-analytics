"""Read-only exact original hash/count/total regression during incremental loads."""
import json
from decimal import Decimal
from warehouse.db import ROOT,connect
from ingestion.acquisition import write_json,utc_now


def main():
    manifest=json.loads((ROOT/'outputs/pilot/source_manifest.json').read_text(encoding='utf-8'))
    result=dict(at=utc_now(),publications=[])
    with connect() as c, c.transaction():
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
        c.execute('SET LOCAL jit=off')
        for slot,vid in sorted(manifest['selected'].items()):
            v=manifest['versions'][vid]
            p=c.execute("SELECT p.publication_id,p.sha256,p.fact_rows FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id) WHERE p.source_name=%s AND p.sha256=%s AND p.status='loaded'",(v['source'],v['sha256'])).fetchone()
            if p is None: raise AssertionError('Original pilot selection changed: '+slot)
            baseline=c.execute('SELECT baseline_fact_rows,baseline_total,tolerance FROM quality.expected_publication WHERE source_name=%s AND baseline_sha256=%s',(v['source'],v['sha256'])).fetchone()
            table,measure={'prices':('fact_price','dollars_per_mwh'),'generation':('fact_generation_connection','kilowatt_hours'),'reconciliation':('fact_reconciled_volume','kilowatt_hours'),'nsp':('dim_nsp_version',None)}[v['source']]
            total='sum('+measure+')' if measure else 'NULL::numeric'
            count,actual=c.execute(f'SELECT count(*),{total} FROM core.{table} WHERE publication_id=%s',(p[0],)).fetchone()
            if count!=baseline[0] or count!=p[2] or (baseline[1] is not None and abs(actual-baseline[1])>baseline[2]):
                raise AssertionError('Original pilot population changed: '+slot)
            result['publications'].append(dict(slot=slot,publication_id=p[0],sha256=p[1],rows=count,total=str(actual) if actual is not None else None))
    result['passed']=True
    write_json(ROOT/'outputs/scale_up/pilot_regression_during_load.json',result)
    print('PASS: ten original selected hashes and native populations/totals unchanged')

if __name__=='__main__': main()
