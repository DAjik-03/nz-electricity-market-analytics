"""Validate the entire pinned candidate before one atomic selection promotion."""
import calendar
import hashlib
import json
from datetime import date
from warehouse.db import ROOT,connect
from warehouse.loader import LOCK_ID,validate_publication_totals,select_publications
from ingestion.intervals import day_intervals
from ingestion.acquisition import write_json,utc_now
from historical.config import MONTHS


def selection_evidence(conn):
    rows=conn.execute('''SELECT s.source_name,s.source_month::text,s.publication_id,p.sha256
        FROM metadata.publication_selection s JOIN metadata.source_publication p USING(publication_id)
        ORDER BY s.source_name,s.source_month''').fetchall()
    digest=hashlib.sha256(json.dumps(rows,separators=(',',':')).encode('utf-8')).hexdigest()
    return dict(rows=rows,sha256=digest,
                algorithm='SHA-256 of compact UTF-8 JSON rows ordered by source/month: source, month, publication_id, source SHA-256')


def main():
    state=json.loads((ROOT/'outputs/scale_up/source_manifest.json').read_text(encoding='utf-8'))
    expected={f'{s}/{m}' for s in ['prices','generation','reconciliation'] for m in MONTHS}|{'nsp/snapshot'}
    if set(state['selected'])!=expected: raise ValueError('Candidate slots differ from approved scope')
    report=dict(started_at=utc_now(),status='validating',publications=[])
    with connect() as c:
        c.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        try:
            c.execute('SET jit=off')
            c.execute("SET work_mem='128MB'")
            before=c.execute('SELECT source_name,source_month::text,publication_id FROM metadata.publication_selection ORDER BY 1,2').fetchall()
            report['selection_before']=before
            report['selection_identity_before']=selection_evidence(c)
            if c.execute("SELECT count(*) FROM metadata.load_attempt WHERE status='running'").fetchone()[0]:
                raise ValueError('Unresolved running load attempt')
            for path,sha in c.execute('SELECT path,sha256 FROM metadata.schema_migration'):
                if hashlib.sha256((ROOT/path).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=sha:
                    raise ValueError('Applied migration changed: '+path)
            if c.execute("SELECT count(*) FROM pg_constraint WHERE connamespace IN ('core'::regnamespace,'staging'::regnamespace) AND NOT convalidated").fetchone()[0]:
                raise ValueError('Unvalidated grain/referential constraints')
            if c.execute("SELECT count(*) FROM pg_trigger t JOIN pg_class r ON r.oid=t.tgrelid JOIN pg_namespace n ON n.oid=r.relnamespace WHERE n.nspname IN ('core','staging') AND t.tgenabled<>'O'").fetchone()[0]:
                raise ValueError('Disabled/nonstandard constraint trigger')
            intervals=c.execute('SELECT trading_date,trading_period,start_utc,end_utc,local_start,local_end,utc_offset_minutes,end_utc_offset_minutes,is_dst,end_is_dst,fold,end_fold FROM core.dim_trading_interval ORDER BY trading_date,trading_period').fetchall()
            if len(intervals)!=17520 or len({r[0] for r in intervals})!=365:
                raise ValueError('Candidate calendar is not the exact approved year')
            for d,tp,start,end,ls,le,off,eoff,dst,edst,fold,efold in intervals:
                if d.strftime('%Y-%m') not in MONTHS: raise ValueError('Unexpected calendar month')
                expected_interval=day_intervals(d)[tp-1]
                actual=[start.isoformat(),end.isoformat(),ls.isoformat(),le.isoformat(),off,eoff,dst,edst,fold,efold]
                expected_values=[expected_interval['interval_start_utc'],expected_interval['interval_end_utc'],expected_interval['local_start'][:19],expected_interval['local_end'][:19],expected_interval['utc_offset_minutes'],expected_interval['end_utc_offset_minutes'],expected_interval['is_dst'],expected_interval['end_is_dst'],expected_interval['fold'],expected_interval['end_fold']]
                if actual!=expected_values: raise ValueError('Calendar UTC/local/DST/fold mismatch')
            report['calendar']=dict(days=365,intervals=17520,all_utc_local_fields_pass=True)
            ids=[]
            for slot,vid in sorted(state['selected'].items()):
                v=state['versions'][vid]
                row=c.execute("SELECT publication_id,source_month::text,staged_rows,fact_rows FROM metadata.source_publication WHERE source_name=%s AND sha256=%s AND status='loaded'",(v['source'],v['sha256'])).fetchone()
                if not row: raise ValueError('Candidate publication not loaded: '+slot)
                pid,month,stage,facts=row
                if v['month'] and month!=v['month']+'-01': raise ValueError('Candidate month mismatch')
                totals=validate_publication_totals(c,v['source'],pid)
                item=dict(slot=slot,publication_id=pid,sha256=v['sha256'],staging_rows=stage,fact_rows=facts,
                          native_totals_pass=True,native_totals=json.loads(json.dumps(totals,default=str)))
                if v['source']!='nsp':
                    table={'prices':'fact_price','generation':'fact_generation_connection','reconciliation':'fact_reconciled_volume'}[v['source']]
                    actual=c.execute(f'SELECT i.trading_date::text,count(DISTINCT f.interval_id),count(*) FROM core.{table} f LEFT JOIN core.dim_trading_interval i USING(interval_id) WHERE publication_id=%s GROUP BY i.trading_date ORDER BY i.trading_date',(pid,)).fetchall()
                    year,mon=map(int,v['month'].split('-'))
                    expected_days=[(date(year,mon,d).isoformat(),len(day_intervals(date(year,mon,d)))) for d in range(1,calendar.monthrange(year,mon)[1]+1)]
                    if [(d,n) for d,n,_ in actual]!=expected_days or sum(r[2] for r in actual)!=facts:
                        raise ValueError('Candidate date/interval/count mismatch: '+slot)
                    item['date_periods']=[(d,n) for d,n,_ in actual]
                ids.append(pid);report['publications'].append(item)
                write_json(ROOT/'outputs/scale_up/candidate_validation.json',report)
                print('Validated '+slot,flush=True)
            report.update(status='validated',completed_at=utc_now(),constraint_checks_pass=True)
            write_json(ROOT/'outputs/scale_up/candidate_validation.json',report)
            select_publications(c,ids)
            report['selection_identity_after']=selection_evidence(c)
            report.update(status='validated_and_promoted',promoted_at=utc_now(),selected_publications=len(ids))
            write_json(ROOT/'outputs/scale_up/candidate_validation.json',report)
            print('PASS: complete validated candidate promoted atomically')
        except Exception as exc:
            report.update(status='failed',error=str(exc))
            write_json(ROOT/'outputs/scale_up/candidate_validation.json',report)
            raise
        finally:
            c.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))

if __name__=='__main__': main()
