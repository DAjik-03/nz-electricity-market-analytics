"""Re-run the real loader and verify physical populations/selection are unchanged."""
from psycopg import sql
from ingestion.acquisition import write_json
from warehouse.db import ROOT, connect
from warehouse.loader import run


def snapshot():
    with connect() as conn:
        tables=conn.execute("SELECT schemaname,tablename FROM pg_tables WHERE schemaname IN ('staging','core') ORDER BY 1,2").fetchall()
        counts={f'{s}.{t}':conn.execute(sql.SQL('SELECT count(*) FROM {}.{}').format(sql.Identifier(s),sql.Identifier(t))).fetchone()[0] for s,t in tables}
        selections=[list(map(str,x)) for x in conn.execute('SELECT source_name,source_month,publication_id,selected_at FROM metadata.publication_selection ORDER BY 1,2')]
        publications=[list(map(str,x)) for x in conn.execute('SELECT publication_id,sha256,status,staged_rows,fact_rows,loaded_at FROM metadata.source_publication ORDER BY 1')]
        totals={}
        for table,measure,group in [('fact_price','dollars_per_mwh','publication_id'),
                ('fact_reconciled_volume','kilowatt_hours','publication_id,flow_direction'),
                ('fact_generation_connection','kilowatt_hours','publication_id')]:
            query=sql.SQL('SELECT {},count(*),sum({}) FROM core.{} GROUP BY {} ORDER BY {}').format(
                sql.SQL(group),sql.Identifier(measure),sql.Identifier(table),sql.SQL(group),sql.SQL(group))
            totals[table]=[list(map(str,row)) for row in conn.execute(query)]
        return dict(counts=counts,selections=selections,publications=publications,native_totals=totals)


if __name__=='__main__':
    before=snapshot()
    run('load')
    after=snapshot()
    if before!=after:
        raise AssertionError('Unchanged warehouse rerun altered populations, publication state or selection timestamps')
    write_json(ROOT/'outputs/warehouse/idempotency.json',dict(passed=True,
        physical_populations_unchanged=True,publication_states_unchanged=True,selection_timestamps_unchanged=True,native_totals_unchanged=True,**after))
    print('PASS: physical table counts, native totals, publication states and selection timestamps unchanged')
