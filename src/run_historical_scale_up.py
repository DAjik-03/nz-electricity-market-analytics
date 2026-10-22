"""Bounded incremental historical release; never deletes retained sources or facts."""
import argparse
import json
import logging
import shutil
import time
from pathlib import Path
from urllib.request import Request, urlopen

from ingestion.acquisition import discover, fetch, store_payload, verify_version, write_json, utc_now
from historical.config import load_config
from warehouse.db import ROOT, connect
from warehouse.loader import load_publication, select_publications, LOCK_ID

OUT = ROOT/'outputs/scale_up'
LOG = logging.getLogger(__name__)


def discover_release(config):
    audit=json.loads((OUT/'december/audit.json').read_text(encoding='utf-8'))
    if audit['status']!='PASSED' or not all(audit['gates'].values()):
        raise ValueError('December daily-final acceptance gate has not passed')
    daily_manifest=json.loads((OUT/'december/source_manifest.json').read_text(encoding='utf-8'))
    derived=daily_manifest['versions'][audit['derived_version']]
    verify_version(ROOT,derived)
    for source in derived['constituents']: verify_version(ROOT,source)
    result=dict(retrieved_at_utc=utc_now(),pages=[],selected={})
    for source,url in config['sources'].items():
        part=dict(config,sources={source:url})
        if source=='prices': part['pilot_months']=[m for m in config['pilot_months'] if m!='2025-12']
        found=discover(part)
        for choice in found['selected'].values():
            choice['source_form']='official_snapshot' if source=='nsp' else 'official_monthly'
        result['pages']+=found['pages'];result['selected'].update(found['selected'])
    result['selected']['prices/2025-12']=derived
    return result


def benchmark(conn):
    tables = {}
    for schema, table in conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('staging','core') ORDER BY 1,2"):
        rows = conn.execute(f'SELECT count(*) FROM {schema}.{table}').fetchone()[0]
        size = conn.execute('SELECT pg_total_relation_size(%s)', (f'{schema}.{table}',)).fetchone()[0]
        tables[f'{schema}.{table}'] = dict(rows=rows, bytes=size)
    loads = [dict(source=s,month=str(m),seconds=float(t)) for s,m,t in conn.execute("""SELECT p.source_name,p.source_month,a.elapsed_seconds
       FROM metadata.load_attempt a JOIN metadata.source_publication p USING(publication_id)
       WHERE a.status='succeeded' ORDER BY p.source_month,p.source_name""")]
    return dict(at=utc_now(),database_bytes=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0],
                raw_bytes=sum(p.stat().st_size for p in (ROOT/'data/raw').rglob('*') if p.is_file()),
                host_disk=shutil.disk_usage('C:/')._asdict(),tables=tables,successful_loads=loads)


def manifest(config):
    path = ROOT/config['manifest']
    if not path.exists():
        write_json(path,json.loads((ROOT/'outputs/pilot/source_manifest.json').read_text(encoding='utf-8')))
    return json.loads(path.read_text(encoding='utf-8'))


def acquire_incremental(config):
    # Re-discovery is explicit; retained discovery pins a resumable acquisition attempt.
    discovery = json.loads((OUT/'discovery.json').read_text(encoding='utf-8'))
    state = manifest(config)
    chosen = {}
    timings = []
    for key, choice in discovery['selected'].items():
        start = time.perf_counter()
        old_id = state['selected'].get(key)
        if choice.get('source_form')=='official_daily_aggregate':
            verify_version(ROOT,choice)
            for child in choice['constituents']: verify_version(ROOT,child)
            vid=f"prices:{choice['filename']}:{choice['sha256']}"
            state['versions'][vid]=choice;state['selected'][key]=vid;chosen[key]=vid
            write_json(ROOT/config['manifest'],state)
            timings.append(dict(slot=key,action='validated_daily_aggregate_reused',previous_version=old_id,
                                selected_version=vid,seconds=round(time.perf_counter()-start,3)))
            continue
        candidates = [(vid,v) for vid,v in state['versions'].items()
                      if v['source']==choice['source'] and v['filename']==choice['filename']]
        reuse = None
        if choice['source']=='nsp':
            reuse = next(((vid,v) for vid,v in candidates if v['filename']==config['nsp_snapshot']),None)
        elif candidates:
            with urlopen(Request(choice['source_url'],method='HEAD'),timeout=120) as response:
                headers = {k.lower():v for k,v in response.headers.items()}
            # Only reuse when publication metadata positively agrees. A changed or
            # unavailable validator triggers content fetch and SHA-based versioning.
            for vid,v in candidates:
                if v.get('http_last_modified') and headers.get('last-modified')==v['http_last_modified'] and (
                    not v.get('etag') or headers.get('etag')==v['etag']):
                    reuse=(vid,v)
        if reuse:
            verify_version(ROOT,reuse[1]); vid=reuse[0]; action='verified_reused'
        else:
            if shutil.disk_usage('C:/').free < 70*1024**3:
                raise RuntimeError('Host free disk below reviewed 70 GiB guard; do not delete data to continue')
            LOG.info('Acquiring %s',choice['filename'])
            payload,headers,resolved=fetch(choice['source_url'])
            vid=store_payload(ROOT,config,choice,payload,headers,resolved,state)
            action='downloaded_new_content' if old_id!=vid else 'downloaded_unchanged_content'
        chosen[key]=vid
        # Persist each verified choice; a crash resumes already acquired publications.
        state['selected'][key]=vid
        write_json(ROOT/config['manifest'],state)
        timings.append(dict(slot=key,action=action,previous_version=old_id,selected_version=vid,
                            seconds=round(time.perf_counter()-start,3)))
        write_json(OUT/'acquisition.json',dict(status='running',publications=timings))
    state['selected']=chosen
    write_json(ROOT/config['manifest'],state)
    write_json(OUT/'acquisition.json',dict(status='completed',publications=timings))


def load_incremental(config):
    state=manifest(config)
    expected={f'{s}/{m}' for s in ('prices','reconciliation','generation') for m in config['pilot_months']}|{'nsp/snapshot'}
    if set(state['selected'])!=expected: raise ValueError('Acquire all required slots before loading')
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        try:
            recover_interrupted_attempts(conn)
            nsp=state['versions'][state['selected']['nsp/snapshot']]
            snapshot=load_publication(conn,nsp)['publication_id']
            items=[]
            for month in config['pilot_months']:
                for source in ('prices','generation','reconciliation'):
                    version=state['versions'][state['selected'][f'{source}/{month}']]
                    if shutil.disk_usage('C:/').free < 50*1024**3:
                        raise RuntimeError('Host disk guard reached; previously committed months preserved')
                    item=load_publication(conn,version,snapshot)
                    items.append(item)
                    write_json(OUT/'load.json',dict(status='running',publications=items))
            # A failed month leaves earlier loaded publications durable and keeps
            # the previous analytical selection intact. Promote only the full set.
            write_json(OUT/'load.json',dict(status='loaded_pending_candidate_validation',publications=items,
                                          selection_promoted=False))
        except Exception as exc:
            write_json(OUT/'load.json',dict(status='failed',error=str(exc),publications=locals().get('items',[])))
            raise
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))


def recover_interrupted_attempts(conn):
    """Caller holds loader lock: no live compliant loader can own these attempts.

    A process loss can leave the pre-transaction attempt marked running even
    though PostgreSQL rolled its COPY/facts back. Never infer success or remove
    rows: require both staging and facts to be empty before recording failure.
    """
    from psycopg import sql
    tables={'prices':('final_energy_price','fact_price'),
            'generation':('generation_daily','fact_generation_connection'),
            'reconciliation':('reconciled_volume','fact_reconciled_volume'),
            'nsp':('network_supply_point','dim_nsp_version')}
    recovered=[]
    with conn.transaction():
        rows=conn.execute("SELECT a.attempt_id,a.publication_id,p.source_name,p.status FROM metadata.load_attempt a JOIN metadata.source_publication p USING(publication_id) WHERE a.status='running'").fetchall()
        for aid,pid,source,status in rows:
            if status=='loaded': raise ValueError('Inconsistent running attempt on loaded publication; investigate')
            for schema,table in zip(('staging','core'),tables[source]):
                present=conn.execute(sql.SQL('SELECT EXISTS(SELECT 1 FROM {}.{} WHERE publication_id=%s)').format(sql.Identifier(schema),sql.Identifier(table)),(pid,)).fetchone()[0]
                if present: raise ValueError('Interrupted publication has committed rows; investigate before retry')
            reason='Interrupted process: no active loader under shared lock; no committed staging/core rows. Retrying immutable source.'
            conn.execute("UPDATE metadata.load_attempt SET status='failed',finished_at=clock_timestamp(),error_message=%s WHERE attempt_id=%s",(reason,aid))
            conn.execute("UPDATE metadata.source_publication SET status='failed' WHERE publication_id=%s",(pid,))
            recovered.append(dict(attempt_id=aid,publication_id=pid,reason=reason))
    if recovered:
        path=OUT/'interrupted_attempts.json'
        previous=json.loads(path.read_text(encoding='utf-8')) if path.exists() else []
        write_json(path,previous+[dict(at=utc_now(),attempts=recovered)])
        LOG.info('Recorded %s rolled-back interrupted attempts; immutable sources retained',len(recovered))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['benchmark','discover','acquire','load'])
    args=parser.parse_args()
    OUT.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(),logging.FileHandler(OUT/'scale_up.log',encoding='utf-8')])
    config=load_config(ROOT/'config/scale_up.yml')
    if args.command=='benchmark':
        with connect() as conn: result=benchmark(conn)
        target=OUT/('benchmark_before.json' if not (OUT/'benchmark_before.json').exists() else 'benchmark_after.json')
        write_json(target,result); print(target)
    elif args.command=='discover': write_json(OUT/'discovery.json',discover_release(config))
    elif args.command=='acquire': acquire_incremental(config)
    else: load_incremental(config)


if __name__=='__main__': main()
