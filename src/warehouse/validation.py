"""Database acceptance checks against the frozen Phase 1 full-file evidence."""
import json
import time
from decimal import Decimal
from psycopg import sql
from ingestion.acquisition import write_json
from .db import ROOT, connect
from .loader import TABLES


def collect(conn):
    started=time.perf_counter()
    phase1=json.loads((ROOT/'outputs/pilot/validation.json').read_text(encoding='utf-8'))
    result={'server_version':conn.execute('SHOW server_version').fetchone()[0], 'sources':{},'checks':{}}
    manifest=json.loads((ROOT/'outputs/pilot/source_manifest.json').read_text(encoding='utf-8'))
    expected_publications=sorted((manifest['versions'][v]['source'],manifest['versions'][v]['sha256']) for v in manifest['selected'].values())
    actual_publications=conn.execute('''SELECT p.source_name,p.sha256 FROM metadata.publication_selection s
        JOIN metadata.source_publication p USING(publication_id) WHERE p.status='loaded' ORDER BY 1,2''').fetchall()
    if actual_publications!=expected_publications:
        raise AssertionError('Selected publication lineage differs from pinned manifest')
    running=conn.execute("SELECT count(*) FROM metadata.load_attempt WHERE status='running'").fetchone()[0]
    if running: raise AssertionError('Unresolved running load attempt')
    result['checks']['manifest_lineage_and_no_running_attempts']=True
    for source,table in TABLES.items():
        counts=conn.execute(sql.SQL('''SELECT p.publication_id,p.source_month,p.filename,count(s.source_row_number)
          FROM metadata.publication_selection chosen JOIN metadata.source_publication p USING(publication_id)
          JOIN staging.{} s USING(publication_id) WHERE chosen.source_name=%s
          GROUP BY p.publication_id,p.source_month,p.filename ORDER BY p.source_month''').format(sql.Identifier(table)),(source,)).fetchall()
        result['sources'][source]=[]
        for pid,month,name,count in counts:
            expected=2617 if source=='nsp' else phase1['months'][month.strftime('%Y-%m')][source]['source_rows']
            if count!=expected: raise AssertionError(f'Staging count mismatch {name}: {count} != {expected}')
            result['sources'][source].append(dict(publication_id=pid,month=month.isoformat(),filename=name,staging_rows=count))
    result['checks']['staging_populations']=True
    views={'prices':'v_selected_price','reconciliation':'v_selected_reconciled_volume','generation':'v_selected_generation'}
    for source,view in views.items():
        measure='dollars_per_mwh' if source=='prices' else 'kilowatt_hours'
        rows=conn.execute(sql.SQL('''SELECT p.source_month,count(*),sum(f.{}),
          count(*) FILTER (WHERE i.interval_id IS NULL),count(DISTINCT f.publication_id)
          FROM core.{} f JOIN metadata.source_publication p USING(publication_id)
          LEFT JOIN core.dim_trading_interval i USING(interval_id)
          GROUP BY p.source_month ORDER BY p.source_month''').format(sql.Identifier(measure),sql.Identifier(view))).fetchall()
        if len(rows)!=3: raise AssertionError('Expected three selected pilot months')
        for month,count,total,orphans,versions in rows:
            expected=phase1['months'][month.strftime('%Y-%m')][source]
            difference=total-Decimal(str(expected['measure']['sum']))
            tolerance=Decimal('0.00000001') if source=='prices' else Decimal(0)
            if (count!=expected['natural_key']['rows'] or abs(difference)>tolerance or orphans or versions!=1):
                raise AssertionError(f'Core reconciliation failed: {source}/{month}')
            item=next(x for x in result['sources'][source] if x['month']==month.isoformat())
            item.update(core_rows=count,measure_total=str(total),phase1_total_delta=str(difference),
                comparison_tolerance=str(tolerance),interval_orphans=orphans,selected_versions=versions)
    result['checks']['facts_counts_totals_intervals_selected_versions']=True
    rows=conn.execute('''SELECT p.source_month,f.flow_direction,count(*),sum(f.kilowatt_hours),
       sum(f.kilowatt_hours) FILTER (WHERE f.zone='Unknown'),count(*) FILTER (WHERE f.mapping_status<>'mapped')
       FROM core.v_selected_reconciled_volume f JOIN metadata.source_publication p USING(publication_id)
       GROUP BY p.source_month,f.flow_direction ORDER BY 1,2''').fetchall()
    result['volume_by_flow']=[]
    for month,flow,count,total,unknown,unmapped in rows:
        expected=next(x for x in phase1['months'][month.strftime('%Y-%m')]['reconciliation']['mapping']['by_flow'] if x['flow']==flow)
        if total!=Decimal(str(expected['total_kwh'])) or (unknown or 0)!=Decimal(str(expected['unknown_zone_kwh'])) or unmapped:
            raise AssertionError('Volume flow/mapping/Unknown differs from Phase 1')
        result['volume_by_flow'].append(dict(month=month.isoformat(),flow=flow,rows=count,kwh=str(total),unknown_zone_kwh=str(unknown or 0),unmapped=unmapped))
    rows=conn.execute('''SELECT p.source_month,count(*) FILTER (WHERE f.mapping_status='unmapped'),
        coalesce(sum(f.kilowatt_hours) FILTER (WHERE f.zone='Unknown'),0)
        FROM core.v_selected_generation f JOIN metadata.source_publication p USING(publication_id)
        GROUP BY p.source_month ORDER BY 1''').fetchall()
    result['generation_mapping']=[]
    for month,unmapped,unknown in rows:
        expected=phase1['months'][month.strftime('%Y-%m')]['generation']['mapping']
        if unmapped!=expected['rows_without_nsp'] or unknown!=Decimal(str(expected['unknown_zone_kwh'])):
            raise AssertionError('Generation mapping differs from Phase 1')
        result['generation_mapping'].append(dict(month=month.isoformat(),unmapped=unmapped,unknown_zone_kwh=str(unknown)))
    result['nsp_boundaries']=[dict(status=s,rows=n) for s,n in conn.execute('SELECT boundary_status,count(*) FROM core.dim_nsp_version GROUP BY 1 ORDER BY 1')]
    invalid=conn.execute("SELECT nsp,original_end_date,original_end_tp,valid_from_utc,valid_to_utc_exclusive FROM core.dim_nsp_version WHERE boundary_status='invalid_boundary' ORDER BY nsp").fetchall()
    expected_invalid=sorted((x['NSP'],x['end_date'],x['end_tp'],None,None) for x in phase1['nsp']['invalid_boundaries'])
    if invalid!=expected_invalid: raise AssertionError('NSP quarantine mismatch')
    result['invalid_nsp']=[dict(nsp=x[0],end_date=x[1],end_tp=x[2]) for x in invalid]
    calendar=conn.execute('''SELECT trading_date,count(*),sum(fold),count(DISTINCT start_utc)
        FROM core.dim_trading_interval
        WHERE date_trunc('month',trading_date)::date=ANY(%s::date[])
        GROUP BY trading_date ORDER BY trading_date''',
        ([m+'-01' for m in phase1['months']],)).fetchall()
    from ingestion.intervals import day_intervals
    for day,count,folds,distinct in calendar:
        expected=day_intervals(day)
        if count!=len(expected) or count!=distinct or folds!=sum(x['fold'] for x in expected):
            raise AssertionError('PostgreSQL calendar differs from Phase 1')
    result['calendar']={'days':len(calendar),'intervals':sum(x[1] for x in calendar),
        'transition_days':[dict(date=d.isoformat(),periods=n,fold_sum=f) for d,n,f,_ in calendar if n!=48]}
    result['fact_period_coverage']={}
    for source,view in views.items():
        days=conn.execute(sql.SQL('''SELECT i.trading_date,count(DISTINCT i.trading_period)
            FROM core.{} f JOIN core.dim_trading_interval i USING(interval_id) GROUP BY 1 ORDER BY 1''').format(sql.Identifier(view))).fetchall()
        if [(d,n) for d,n in days]!=[(d,n) for d,n,_,_ in calendar]:
            raise AssertionError(f'Actual fact trading-period coverage differs: {source}')
        result['fact_period_coverage'][source]=dict(days=len(days),transition_days=[dict(date=d.isoformat(),periods=n) for d,n in days if n!=48])
    padding=conn.execute('''SELECT count(*) FROM core.fact_generation_connection f
        JOIN core.dim_trading_interval i USING(interval_id) WHERE f.source_tp<>i.trading_period''').fetchone()[0]
    if padding: raise AssertionError('Generation source TP differs from calendar')
    result['checks']['actual_fact_periods_and_generation_padding']=True
    constraints=conn.execute('''SELECT count(*),count(*) FILTER (WHERE NOT convalidated) FROM pg_constraint
        WHERE connamespace IN ('metadata'::regnamespace,'staging'::regnamespace,'core'::regnamespace)''').fetchone()
    if constraints[1]: raise AssertionError('Unvalidated database constraint')
    result['constraints']={'total':constraints[0],'unvalidated':constraints[1]}
    result['objects']=[dict(schema=s,name=n,kind=k,bytes=b) for s,n,k,b in conn.execute('''
        SELECT ns.nspname,c.relname,c.relkind,CASE WHEN c.relkind='r' THEN pg_total_relation_size(c.oid) ELSE 0 END
        FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
        WHERE ns.nspname IN ('metadata','staging','core') AND c.relkind IN ('r','v') ORDER BY 1,2''')]
    result['database_bytes']=conn.execute('SELECT pg_database_size(current_database())').fetchone()[0]
    result['load_attempts']=[dict(filename=f,status=s,seconds=str(t) if t is not None else None,
        error=e) for f,s,t,e in conn.execute('''SELECT p.filename,a.status,a.elapsed_seconds,a.error_message
        FROM metadata.load_attempt a JOIN metadata.source_publication p USING(publication_id) ORDER BY attempt_id''')]
    result['publication_status']=[dict(source=s,status=t,count=n) for s,t,n in conn.execute('SELECT source_name,status,count(*) FROM metadata.source_publication GROUP BY 1,2 ORDER BY 1,2')]
    result['checks'].update(unknown_retained=True,flow_totals=True,nsp_quarantine=True,dst_calendar=True,enforced_constraints=True)
    result['elapsed_seconds']=round(time.perf_counter()-started,3)
    return result


def main():
    with connect() as conn:
        result=collect(conn)
    write_json(ROOT/'outputs/warehouse/validation.json',result)
    print(json.dumps({'checks':result['checks'],'database_bytes':result['database_bytes'],'elapsed_seconds':result['elapsed_seconds']}))


if __name__=='__main__': main()
