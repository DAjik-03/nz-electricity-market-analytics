import json
from warehouse.db import connect
from warehouse.loader import LOCK_ID
from analytics.validation import collect

if __name__ == '__main__':
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)', (LOCK_ID,))
        try:
            # Bound this independent read-only check to process-local memory.
            # Parallel hash allocation exceeded the container's 256 MiB /dev/shm.
            conn.execute('SET max_parallel_workers_per_gather=0')
            result = collect(conn)
            print(json.dumps(result, indent=2, default=str))
            if not all(result['checks'].values()):
                raise SystemExit('Analytical validation failed')
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)', (LOCK_ID,))
