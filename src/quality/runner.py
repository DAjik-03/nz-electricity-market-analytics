"""Run registered SQL in one repeatable snapshot; retain attempts and evidence."""
import argparse
import hashlib
import json
import logging
import subprocess
from datetime import datetime
from zoneinfo import ZoneInfo
from psycopg.types.json import Jsonb
from warehouse.db import ROOT, connect
from warehouse.loader import LOCK_ID, migrate as warehouse_migrate
from ingestion.acquisition import write_json

LOG=logging.getLogger(__name__)


def migrate(conn):
    warehouse_migrate(conn)
    for path in sorted((ROOT/'sql/06_data_quality').glob('*.sql')):
        body=path.read_text(encoding='utf-8').replace('\r\n','\n')
        digest=hashlib.sha256(body.encode()).hexdigest()
        name=path.relative_to(ROOT).as_posix()
        prior=conn.execute('SELECT sha256 FROM metadata.schema_migration WHERE path=%s',(name,)).fetchone()
        if prior:
            if prior[0]!=digest: raise ValueError(f'Applied migration changed: {name}')
            continue
        with conn.transaction():
            conn.execute(body)
            conn.execute('INSERT INTO metadata.schema_migration(path,sha256) VALUES (%s,%s)',(name,digest))


def code_hash():
    files=sorted((ROOT/'sql/06_data_quality').glob('*.sql'))+sorted((ROOT/'src/quality').glob('*.py'))
    return hashlib.sha256(b''.join(p.relative_to(ROOT).as_posix().encode()+p.read_bytes().replace(b'\r\n',b'\n') for p in files)).hexdigest()


def evaluate(conn, code):
    query=conn.execute('SELECT query_sql FROM quality.rule WHERE rule_code=%s AND active_flag',(code,)).fetchone()
    if not query: raise ValueError(f'Unknown active rule {code}')
    return conn.execute(query[0]).fetchone()[0]


def execute(conn, as_of):
    commit=subprocess.check_output(['git','-c',f'safe.directory={ROOT.as_posix()}','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    run_id=conn.execute("INSERT INTO quality.dq_run(as_of_date,code_sha256,git_commit,status) VALUES (%s,%s,%s,'RUNNING') RETURNING run_id",(as_of,code_hash(),commit)).fetchone()[0]
    try:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            conn.execute("SET LOCAL work_mem='128MB'")
            conn.execute('SET LOCAL jit=off')
            conn.execute("SELECT set_config('quality.as_of_date',%s,true)",(str(as_of),))
            LOG.info('Run %s: preparing SQL profiles',run_id)
            conn.execute('SELECT quality.prepare_profiles()')
            publications=conn.execute('SELECT to_jsonb(p) FROM metadata.source_publication p ORDER BY publication_id').fetchall()
            selections=conn.execute('SELECT to_jsonb(s) FROM metadata.publication_selection s ORDER BY source_name,source_month').fetchall()
            populations=conn.execute('SELECT to_jsonb(p) FROM dq_population p ORDER BY source,publication_id,flow').fetchall()
            inputs=dict(publications=[x[0] for x in publications],selections=[x[0] for x in selections],populations=[x[0] for x in populations])
            fingerprint=hashlib.sha256(json.dumps(inputs,sort_keys=True,default=str).encode()).hexdigest()
            conn.execute('UPDATE quality.dq_run SET warehouse_fingerprint=%s,input_manifest=%s WHERE run_id=%s',(fingerprint,Jsonb(inputs),run_id))
            rules=conn.execute('SELECT rule_id,rule_code,to_jsonb(r)-\'query_sql\' FROM quality.rule r WHERE active_flag ORDER BY rule_code').fetchall()
            for rule_id,code,snapshot in rules:
                LOG.info('Run %s: %s %s',run_id,code,snapshot['rule_name'])
                result=evaluate(conn,code)
                conn.execute('''INSERT INTO quality.rule_result(run_id,rule_id,rule_snapshot,result_status,affected_rows,
                    observed_value,expected_value,coverage_pct,details) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                    (run_id,rule_id,Jsonb(snapshot),result['result_status'],result['affected_rows'],Jsonb(result['observed_value']),
                     snapshot['expected_condition'],result['coverage_pct'],Jsonb(result['details'])))
            conn.execute('''INSERT INTO quality.coverage_metric SELECT %s,source_name,source_month,denominator_unit,
                total_value,known_value,unknown_value,100*known_value/nullif(total_value,0) FROM dq_coverage''',(run_id,))
            blocking=conn.execute("SELECT count(*) FROM quality.rule_result WHERE run_id=%s AND result_status='FAIL' AND (rule_snapshot->>'is_blocking')::boolean",(run_id,)).fetchone()[0]
            conn.execute("UPDATE quality.dq_run SET status=%s,completed_at=clock_timestamp() WHERE run_id=%s",('BLOCKED' if blocking else 'COMPLETED',run_id))
    except Exception as error:
        conn.execute("UPDATE quality.dq_run SET status='ERROR',completed_at=clock_timestamp(),error_message=%s WHERE run_id=%s",(str(error)[:2000],run_id))
        raise
    return run_id


def export(conn, run_id):
    run=conn.execute('SELECT to_jsonb(q)-\'input_manifest\' FROM quality.dq_run q WHERE run_id=%s',(run_id,)).fetchone()[0]
    rows=[x[0] for x in conn.execute('SELECT to_jsonb(r) FROM quality.rule_result r WHERE run_id=%s ORDER BY rule_id',(run_id,))]
    coverage=[x[0] for x in conn.execute('SELECT to_jsonb(c) FROM quality.coverage_metric c WHERE run_id=%s ORDER BY source_name,source_month',(run_id,))]
    counts={s:sum(x['result_status']==s for x in rows) for s in ['PASS','WARN','FAIL']}
    result=dict(run=run,active_rules=len(rows),counts=counts,blocking_failures=sum(x['result_status']=='FAIL' and x['rule_snapshot']['is_blocking'] for x in rows),results=rows,coverage=coverage)
    write_json(ROOT/'outputs/data_quality/latest_summary.json',result)
    write_json(ROOT/f'outputs/data_quality/run_{run_id}.json',result)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['init','run'])
    parser.add_argument('--as-of',default=datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat())
    args=parser.parse_args()
    datetime.strptime(args.as_of,'%Y-%m-%d')
    folder=ROOT/'outputs/data_quality'; folder.mkdir(exist_ok=True)
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',handlers=[logging.StreamHandler(),logging.FileHandler(folder/'run.log',encoding='utf-8')])
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        try:
            migrate(conn)
            if args.command=='init': return
            result=export(conn,execute(conn,args.as_of))
            print(json.dumps({k:result[k] for k in ['active_rules','counts','blocking_failures']}))
            if result['blocking_failures']: raise SystemExit(2)
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))


if __name__=='__main__': main()
