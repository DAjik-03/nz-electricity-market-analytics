"""Persist a second run and compare substantive results with the preceding run."""
import argparse
import json
from ingestion.acquisition import write_json
from warehouse.db import ROOT, connect
from warehouse.loader import LOCK_ID
from quality.runner import execute, export, migrate


def substantive(conn,run_id):
    run=conn.execute('SELECT as_of_date,warehouse_fingerprint,code_sha256,status FROM quality.dq_run WHERE run_id=%s',(run_id,)).fetchone()
    results=conn.execute('''SELECT rule_snapshot->>'rule_code',result_status,affected_rows,observed_value,
        expected_value,coverage_pct,details FROM quality.rule_result WHERE run_id=%s ORDER BY rule_snapshot->>'rule_code' ''',(run_id,)).fetchall()
    coverage=conn.execute('''SELECT source_name,source_month,denominator_unit,total_value,known_value,unknown_value,coverage_pct
        FROM quality.coverage_metric WHERE run_id=%s ORDER BY source_name,source_month''',(run_id,)).fetchall()
    return dict(run=run,results=results,coverage=coverage)


def main():
    with connect() as conn:
        conn.execute('SELECT pg_advisory_lock(%s)',(LOCK_ID,))
        try:
            migrate(conn)
            prior=conn.execute("SELECT run_id,as_of_date FROM quality.dq_run WHERE status IN ('COMPLETED','BLOCKED') ORDER BY run_id DESC LIMIT 1").fetchone()
            if prior is None: raise ValueError('Run DQ first')
            before=substantive(conn,prior[0])
            current=execute(conn,prior[1])
            after=substantive(conn,current)
            passed=before==after
            write_json(ROOT/'outputs/data_quality/determinism.json',dict(passed=passed,first_run_id=prior[0],second_run_id=current,
                as_of_date=str(prior[1]),comparison='Same code, as-of date, lineage/population fingerprint, statuses, affected values, JSON diagnostics and all monthly coverage metrics; excludes run IDs and execution timestamps.'))
            export(conn,current)
            if not passed: raise AssertionError('DQ substantive results changed; inspect retained runs')
            print('PASS: repeated DQ execution preserved all substantive results')
        finally:
            conn.execute('SELECT pg_advisory_unlock(%s)',(LOCK_ID,))


if __name__=='__main__': main()
