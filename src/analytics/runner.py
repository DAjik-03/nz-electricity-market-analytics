"""Atomic analytical refresh; source acquisition and warehouse loading are separate."""
import argparse
import hashlib
import json
import logging
import subprocess
import time

from psycopg.types.json import Jsonb
from warehouse.db import ROOT, connect
from warehouse.loader import LOCK_ID
from quality.runner import migrate as quality_migrate

LOG = logging.getLogger(__name__)
SQL = ROOT / 'sql/04_marts'
OUT = ROOT / 'outputs/analytics'


def migrate(conn):
    quality_migrate(conn)
    for path in sorted(SQL.glob('*.sql')):
        body = path.read_text(encoding='utf-8').replace('\r\n', '\n')
        digest = hashlib.sha256(body.encode()).hexdigest()
        name = path.relative_to(ROOT).as_posix()
        prior = conn.execute('SELECT sha256 FROM metadata.schema_migration WHERE path=%s', (name,)).fetchone()
        if prior:
            if prior[0] != digest:
                raise ValueError(f'Applied migration changed: {name}')
            continue
        with conn.transaction():
            conn.execute(body)
            conn.execute('INSERT INTO metadata.schema_migration(path,sha256) VALUES (%s,%s)', (name, digest))


def code_hash():
    paths = sorted(SQL.rglob('*.sql')) + sorted((ROOT/'src/analytics').glob('*.py'))
    return hashlib.sha256(b''.join(p.relative_to(ROOT).as_posix().encode() +
                                  p.read_bytes().replace(b'\r\n', b'\n') for p in paths)).hexdigest()


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/name).write_text(json.dumps(obj, indent=2, default=str, ensure_ascii=False)+'\n', encoding='utf-8')


def refresh(conn):
    """Caller holds shared warehouse/DQ advisory lock. Failed work preserves last cache."""
    commit = subprocess.check_output(['git', '-c', f'safe.directory={ROOT.as_posix()}', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    run = conn.execute("""INSERT INTO analytics.refresh_run(status,code_sha256,git_commit)
                          VALUES ('RUNNING',%s,%s) RETURNING refresh_id""", (code_hash(), commit)).fetchone()[0]
    started = time.perf_counter()
    try:
        with conn.transaction():
            conn.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ')
            conn.execute("SET LOCAL work_mem='128MB'")
            conn.execute('SET LOCAL jit=off')
            # Explicit approved release only; no accidental extra historical months.
            extra = conn.execute("""SELECT count(*) FROM metadata.publication_selection s
               CROSS JOIN analytics.configuration c WHERE s.source_name<>'nsp'
               AND NOT s.source_month=ANY(c.pilot_months)""").fetchone()[0]
            expected = conn.execute("""SELECT cardinality(pilot_months)*3 FROM analytics.configuration""").fetchone()[0]
            selected = conn.execute("SELECT count(*) FROM metadata.publication_selection WHERE source_name<>'nsp'").fetchone()[0]
            if extra or selected != expected:
                raise ValueError('Selected publications do not match the approved three-source release months')
            dq = conn.execute("SELECT run_id FROM quality.dq_run WHERE status='COMPLETED' ORDER BY run_id DESC LIMIT 1").fetchone()
            if not dq:
                raise ValueError('A completed DQ assessment is required; freshness is disclosed separately')
            manifest = conn.execute('SELECT analytics.input_manifest()').fetchone()[0]
            assessed = conn.execute('SELECT input_manifest FROM quality.dq_run WHERE run_id=%s', dq).fetchone()[0]
            old_selection = sorted((s['source_name'], s['source_month'], s['publication_id'])
                                   for s in assessed['selections'])
            new_selection = sorted((s['source'], s['month'], s['publication']) for s in manifest['selections'])
            if old_selection != new_selection:
                raise ValueError('Selected publications differ from the completed DQ assessment; assess the new selection first')
            fingerprint = conn.execute('SELECT analytics.input_fingerprint()').fetchone()[0]
            LOG.info('Refresh %s: independent Offtake and generation aggregation', run)
            off = (SQL/'queries/offtake.sql').read_text(encoding='utf-8')
            gen = (SQL/'queries/generation.sql').read_text(encoding='utf-8')
            conn.execute('CREATE TEMP TABLE analytics_offtake_poc ON COMMIT DROP AS '+off)
            conn.execute('CREATE UNIQUE INDEX ON analytics_offtake_poc(interval_id,poc,zone)')
            conn.execute("""CREATE TEMP TABLE analytics_price ON COMMIT DROP AS
               SELECT p.interval_id,n.pricing_poc AS poc,p.dollars_per_mwh
               FROM core.v_selected_price p JOIN core.dim_pricing_node n USING(pricing_node_id)""")
            conn.execute('CREATE UNIQUE INDEX ON analytics_price(interval_id,poc)')
            conn.execute('CREATE TEMP TABLE analytics_generation ON COMMIT DROP AS '+gen)
            conn.execute('CREATE UNIQUE INDEX ON analytics_generation(interval_id,zone)')
            for table in ('analytics_offtake_poc', 'analytics_price', 'analytics_generation'):
                conn.execute('ANALYZE '+table)
            conn.execute('DELETE FROM analytics._interval_cache')
            conn.execute((SQL/'queries/combine.sql').read_text(encoding='utf-8'))
            conn.execute('ANALYZE analytics._interval_cache')
            conn.execute('DELETE FROM analytics._threshold_cache')
            conn.execute("""INSERT INTO analytics._threshold_cache
               SELECT i.scope,i.zone,percentile_cont(c.percentile) WITHIN GROUP
               (ORDER BY i.price_numerator/nullif(i.priced_offtake_kwh,0)),
               count(*),min(start_utc),max(end_utc),
               array_agg(DISTINCT date_trunc('month',trading_date)::date ORDER BY date_trunc('month',trading_date)::date)
               FROM analytics._interval_cache i CROSS JOIN analytics.configuration c
               WHERE (i.scope='National' OR i.zone=ANY(c.expected_zones)) AND i.priced_offtake_kwh<>0
               GROUP BY i.scope,i.zone,c.percentile""")
            conn.execute("""UPDATE analytics.refresh_run SET status='COMPLETED',completed_at=clock_timestamp(),
               input_fingerprint=%s,input_manifest=%s,dq_run_id=%s WHERE refresh_id=%s""",
                         (fingerprint, Jsonb(manifest), dq[0], run))
            conn.execute("""INSERT INTO analytics.current_refresh VALUES(true,%s)
               ON CONFLICT(singleton) DO UPDATE SET refresh_id=excluded.refresh_id""", (run,))
            conn.execute('SELECT analytics.assert_current()')
    except Exception as exc:
        conn.execute("UPDATE analytics.refresh_run SET status='ERROR',completed_at=clock_timestamp(),error_message=%s WHERE refresh_id=%s",
                     (str(exc)[:2000], run))
        raise
    duration = time.perf_counter()-started
    LOG.info('Refresh %s complete in %.3fs', run, duration)
    return {'refresh_id': run, 'seconds': duration, 'fingerprint': fingerprint}


def export(conn):
    products = {
        'thresholds': 'mart_price_pressure_threshold',
        'events': 'mart_price_pressure_event',
        'monthly': 'mart_market_monthly',
    }
    result = {}
    for key, view in products.items():
        rows = [r[0] for r in conn.execute(f'SELECT to_jsonb(t) FROM analytics.{view} t ORDER BY to_jsonb(t)::text')]
        result[key] = rows
        save(key+'.json', rows)
    cache_hash = conn.execute("""SELECT encode(sha256(convert_to(string_agg(to_jsonb(c)::text,E'\\n'
               ORDER BY scope,zone,interval_id),'UTF8')),'hex') FROM analytics._interval_cache c""").fetchone()[0]
    digest = hashlib.sha256(json.dumps(result, sort_keys=True, default=str).encode()).hexdigest()
    save('export_lineage.json', conn.execute('SELECT to_jsonb(r) FROM analytics.refresh_status r').fetchone()[0])
    return {'products_sha256': digest, 'interval_cache_sha256': cache_hash,
            'thresholds': len(result['thresholds']), 'events': len(result['events'])}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['init', 'refresh', 'export'])
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
        try:
            migrate(conn)
            if args.command == 'refresh':
                timing = refresh(conn)
                timing.update(export(conn))
                save(f"refresh_{timing['refresh_id']}.json", timing)
                print(json.dumps(timing, indent=2))
            elif args.command == 'export':
                print(json.dumps(export(conn), indent=2))
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))


if __name__ == '__main__':
    main()
