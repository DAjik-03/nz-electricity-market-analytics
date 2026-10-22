"""Execute named Phase 5 SELECTs in one read-only snapshot; save exact evidence.

No acquisition, migrations, refresh or persistent database writes. SQL owns metrics.
"""
import hashlib
import gzip
import json
import re
import subprocess
from datetime import datetime, timezone
from warehouse.db import ROOT, connect
from check_analytics_determinism import product_hashes


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def rows(conn, query):
    cur = conn.execute(query)
    names = [c.name for c in cur.description]
    return [dict(zip(names, row)) for row in cur]


def release_state(conn):
    return {
        'refresh': rows(conn, 'SELECT * FROM analytics.refresh_status'),
        'selection': rows(conn, 'SELECT * FROM metadata.publication_selection ORDER BY source_name,source_month'),
        'cache': rows(conn, "SELECT count(*) AS rows,md5(string_agg(md5(to_jsonb(c)::text),'' ORDER BY scope,zone,interval_id)) AS hash FROM analytics._interval_cache c"),
        'thresholds': rows(conn, 'SELECT * FROM analytics.mart_price_pressure_threshold ORDER BY scope,zone'),
        'migrations': rows(conn, 'SELECT * FROM metadata.schema_migration ORDER BY path'),
    }


def main():
    out = ROOT / 'outputs/analysis'
    out.mkdir(parents=True, exist_ok=True)
    evidence = {'at': datetime.now(timezone.utc).isoformat(), 'git_commit': subprocess.check_output(['git','-c','safe.directory='+ROOT.as_posix(),'rev-parse','HEAD'], cwd=ROOT, text=True).strip(), 'queries': {}}
    with connect() as conn:
        conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        try:
            conn.execute('SET LOCAL max_parallel_workers_per_gather=0')
            conn.execute("SET LOCAL statement_timeout='180s'")
            conn.execute('SELECT analytics.assert_current()')
            evidence['before'] = release_state(conn)
            # Reuse only the read-only hash helper, never its refresh command.
            evidence['approved_view_hashes'] = product_hashes(conn)
            approved = json.loads((ROOT/'outputs/analytics/refresh_38.json').read_text(encoding='utf-8'))
            assert evidence['approved_view_hashes'] == approved['view_hashes'], 'Approved analytical products changed'
            evidence['matches_approved_phase4b'] = True
            evidence['catalog'] = rows(conn, "SELECT table_schema,table_name,column_name,data_type FROM information_schema.columns WHERE table_schema='analytics' ORDER BY table_name,ordinal_position")
            for path in sorted((ROOT/'sql/05_analysis').glob('*.sql')):
                content = path.read_text(encoding='utf-8')
                parts = re.split(r'^-- name: ([a-z0-9_]+)\s*$', content, flags=re.M)
                for name, sql in zip(parts[1::2], parts[2::2]):
                    if name in evidence['queries']:
                        raise ValueError('Duplicate query name: '+name)
                    result = rows(conn, sql)
                    payload = (json.dumps(result, indent=2, default=str)+'\n').encode('utf-8')
                    filename = name+'.json'+('.gz' if len(result)>1000 else '')
                    (out/filename).write_bytes(gzip.compress(payload, mtime=0) if filename.endswith('.gz') else payload)
                    evidence['queries'][name] = {'sql': path.relative_to(ROOT).as_posix(), 'output': filename, 'sql_sha256': hashlib.sha256(sql.encode()).hexdigest(), 'rows': len(result), 'result_sha256': digest(result)}
                    print(name, len(result), flush=True)
            evidence['after'] = release_state(conn)
            assert evidence['before'] == evidence['after'], 'Approved release changed'
            evidence['read_only'] = conn.execute('SHOW transaction_read_only').fetchone()[0]
            assert evidence['read_only'] == 'on'
        finally:
            conn.execute('ROLLBACK')
    (out/'query_manifest.json').write_text(json.dumps(evidence, indent=2, default=str)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
