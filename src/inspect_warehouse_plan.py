"""Read-only fact mapping SELECT plan; no source reload or fact mutation."""
from warehouse.db import ROOT, connect
from ingestion.acquisition import write_json


def main():
    body=(ROOT/'sql/03_facts/006_mapping_plan.sql').read_text(encoding='utf-8')
    query=body[body.index('WITH observed AS MATERIALIZED'):body.index(';\n CREATE UNIQUE INDEX')]
    with connect() as conn, conn.transaction(force_rollback=True):
        pid,snapshot=conn.execute('''SELECT v.publication_id,n.publication_id
            FROM metadata.publication_selection v CROSS JOIN metadata.publication_selection n
            WHERE v.source_name='reconciliation' AND v.source_month='2025-09-01' AND n.source_name='nsp' ''').fetchone()
        conn.execute("SET LOCAL work_mem='128MB'")
        conn.execute('SET LOCAL jit=off')
        conn.execute("SELECT set_config('warehouse.publication_id',%s,true)",(str(pid),))
        conn.execute('''CREATE TEMP VIEW load_rows AS SELECT "TradingDate"::date AS trading_date,
            "TradingPeriod"::integer AS trading_period,"PointOfConnection" AS poc,"Network" AS network
            FROM staging.reconciled_volume WHERE publication_id=current_setting('warehouse.publication_id')::bigint''')
        plan=conn.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) '+query.replace('snapshot_pid',str(snapshot))).fetchone()[0]
    write_json(ROOT/'outputs/warehouse/mapping_plan.json',dict(
        scope='Full September 2025 reconciliation mapping SELECT only; excludes COPY, fact INSERT and constraint-trigger costs',
        publication_id=pid,nsp_snapshot_publication_id=snapshot,work_mem='128MB',jit=False,plan=plan))
    print('Mapping SELECT execution milliseconds:',plan[0]['Execution Time'])


if __name__=='__main__': main()
