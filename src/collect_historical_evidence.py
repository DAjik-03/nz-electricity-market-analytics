"""Final read-only release/performance evidence, after DQ and marts are current."""
import hashlib
import json
import shutil
import time
from warehouse.db import ROOT,connect
from warehouse.loader import LOCK_ID
from ingestion.acquisition import write_json,utc_now


def main():
    with connect() as c:
        c.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        try:
            c.execute('SELECT analytics.assert_current()')
            c.execute("SET work_mem='128MB'")
            c.execute('SET jit=off')
            r=dict(at=utc_now(),database_bytes=c.execute('SELECT pg_database_size(current_database())').fetchone()[0],
                   raw_all_bytes=sum(p.stat().st_size for p in (ROOT/'data/raw').rglob('*') if p.is_file()),
                   host_disk=shutil.disk_usage('C:/')._asdict())
            r['publications']=[x[0] for x in c.execute("SELECT to_jsonb(p) FROM metadata.source_publication p ORDER BY source_name,source_month")]
            r['load_attempts']=[x[0] for x in c.execute('SELECT to_jsonb(a) FROM metadata.load_attempt a ORDER BY attempt_id')]
            r['calendar']=c.execute("SELECT min(trading_date),max(trading_date),count(DISTINCT trading_date),count(*) FROM core.dim_trading_interval").fetchone()
            r['fact_counts']={}
            for table in ['fact_price','fact_reconciled_volume','fact_generation_connection']:
                r['fact_counts'][table]=c.execute(f'SELECT count(*) FROM core.{table}').fetchone()[0]
            r['mapping_gaps']=[x[0] for x in c.execute("""SELECT jsonb_build_object('source','generation','month',p.source_month,'poc',d.poc,'network',d.network,'rows',count(*),'kwh',sum(f.kilowatt_hours))
                FROM core.v_selected_generation f JOIN metadata.source_publication p USING(publication_id)
                JOIN core.dim_connection d USING(connection_id) WHERE f.mapping_status='unmapped'
                GROUP BY p.source_month,d.poc,d.network ORDER BY p.source_month,d.poc,d.network""")]
            queries={
                'monthly_national':"SELECT * FROM analytics.mart_market_monthly WHERE scope='National' ORDER BY source_month",
                'rolling_30d_national':"SELECT trading_date,rolling_30d_weighted_price,rolling_30d_demand_gwh,rolling_30d_interval_price_volatility_pop FROM analytics.mart_market_daily_rolling_30d WHERE scope='National' ORDER BY trading_date",
                'event_context':"SELECT * FROM analytics.mart_price_event_context ORDER BY peak_weighted_price DESC LIMIT 20",
                'regional_spread':"SELECT * FROM analytics.mart_regional_spread ORDER BY interval_id",
            }
            r['query_plans']={}
            for name,query in queries.items():
                start=time.perf_counter()
                plan=c.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) '+query).fetchone()[0]
                r['query_plans'][name]=dict(wall_seconds=time.perf_counter()-start,plan=plan)
            r['migrations']=[]
            for path,expected in c.execute('SELECT path,sha256 FROM metadata.schema_migration ORDER BY path'):
                actual=hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()
                if actual!=expected: raise ValueError('Applied migration changed: '+path)
                r['migrations'].append(dict(path=path,sha256=actual))
            # write_json does not serialise Decimal/date; preserve exact values as strings.
            r=json.loads(json.dumps(r,default=str))
            write_json(ROOT/'outputs/scale_up/final_evidence.json',r)
            print(json.dumps({k:r[k] for k in ['database_bytes','raw_all_bytes','calendar','fact_counts']},indent=2))
        finally:
            c.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))

if __name__=='__main__': main()
