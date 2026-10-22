"""Two atomic refreshes of the same selected pilot; compare substantive products."""
import hashlib
import json
from warehouse.db import connect
from warehouse.loader import LOCK_ID
from analytics.runner import migrate, refresh, export, save


def product_hashes(conn):
    result = {}
    for view in ['mart_market_interval','mart_market_daily','mart_market_monthly',
                 'mart_market_daily_rolling','mart_market_daily_rolling_30d',
                 'mart_price_pressure_threshold','mart_price_pressure_event']:
        digest = hashlib.sha256()
        for row in conn.execute(f'SELECT to_jsonb(t)::text FROM analytics.{view} t ORDER BY to_jsonb(t)::text'):
            digest.update(row[0].encode('utf-8')+b'\n')
        result[view] = digest.hexdigest()
    return result


if __name__ == '__main__':
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
        try:
            migrate(conn)
            runs = []
            for _ in range(2):
                run = refresh(conn)
                run.update(export(conn))
                run['view_hashes'] = product_hashes(conn)
                runs.append(run)
                save(f"refresh_{run['refresh_id']}.json", run)
                print(f"Refresh {run['refresh_id']} complete", flush=True)
            checks = {key: runs[0][key] == runs[1][key] for key in
                      ['fingerprint','products_sha256','interval_cache_sha256','view_hashes']}
            result = {'runs': runs, 'checks': checks}
            save('determinism.json', result)
            print(json.dumps(checks, indent=2))
            if not all(checks.values()): raise SystemExit('Non-deterministic analytical products')
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
