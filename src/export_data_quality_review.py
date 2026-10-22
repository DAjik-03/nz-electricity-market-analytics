"""Format persisted SQL findings; this module performs no DQ calculations."""
import csv
import json
from pathlib import Path
from warehouse.db import ROOT, connect


def clean(value):
    return str(value).replace('|','/').replace('\n',' ')


def main():
    report=json.loads((ROOT/'outputs/data_quality/latest_summary.json').read_text(encoding='utf-8'))
    rows=report['results']
    lines=['# Data quality register','',
        f"Run {report['run']['run_id']}; as-of {report['run']['as_of_date']}. {len(rows)} rules; "+
        ', '.join(f'{k}: {v}' for k,v in report['counts'].items())+f"; blocking failures: {report['blocking_failures']}.",'',
        'This register describes the assessed selected release. Historical pilot exports remain under outputs/scale_up/pilot_archive. A WARN retains a known limitation; it does not authorise source repair. Affected units differ by rule and must not be added together. Full observations and monthly diagnostics are in `outputs/data_quality/latest_summary.json`. Registered SQL is under `sql/06_data_quality/`.','',
        '| Rule / dimension | Target / severity | Definition and expected result | Current result | Treatment and business implication |',
        '|---|---|---|---|---|']
    csv_rows=[]
    for row in rows:
        r=row['rule_snapshot']
        lines.append('| '+' | '.join(map(clean,[f"{r['rule_code']} — {r['rule_name']} / {r['quality_dimension']}",
            f"{r['target_object']} / {r['severity']} / blocking={r['is_blocking']}",
            r['description']+' Expected: '+r['expected_condition'],
            f"{row['result_status']}; affected={row['affected_rows']}",r['treatment']+' '+r['business_implication']]))+' |')
        csv_rows.append(dict(run_id=report['run']['run_id'],as_of_date=report['run']['as_of_date'],
            rule_code=r['rule_code'],rule_name=r['rule_name'],quality_dimension=r['quality_dimension'],severity=r['severity'],
            is_blocking=r['is_blocking'],result_status=row['result_status'],affected_rows=row['affected_rows'],
            observed_value=json.dumps(row['observed_value'],sort_keys=True),details=json.dumps(row['details'],sort_keys=True)))
    (ROOT/'docs/data_quality_register.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    for name,data in [('latest_results.csv',csv_rows),('latest_coverage.csv',report['coverage'])]:
        with (ROOT/'outputs/data_quality'/name).open('w',encoding='utf-8',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(data[0])); writer.writeheader(); writer.writerows(data)
    # Small read-only companion: exact SQL plus observed outputs, no raw facts.
    queries=[('Rule summary','SELECT * FROM quality.v_latest_dq_summary ORDER BY quality_dimension'),
             ('Mapping coverage','SELECT * FROM quality.v_latest_coverage ORDER BY source_name,source_month'),
             ('Run history','SELECT run_id,as_of_date,status,started_at,completed_at FROM quality.dq_run ORDER BY run_id'),
             ('Inspectable rule SQL',"SELECT rule_code,query_sql FROM quality.rule WHERE rule_code IN ('DQ19','DQ27') ORDER BY rule_code")]
    cells=[dict(cell_type='markdown',metadata={},source=['# PostgreSQL data quality review\nRead-only SQL companion to the framework and register. Requires the existing local PostgreSQL warehouse and project Python environment. Credentials remain in ignored .env.']),
        dict(cell_type='code',execution_count=1,metadata={},source=["from pathlib import Path\nimport sys\nroot = Path.cwd().parent if Path.cwd().name == 'notebooks' else Path.cwd()\nsys.path.insert(0, str(root / 'src'))\nfrom warehouse.db import connect\n"],outputs=[])]
    with connect() as conn:
        for n,(title,query) in enumerate(queries,2):
            records=conn.execute(query).fetchall()
            cells.append(dict(cell_type='markdown',metadata={},source=[title]))
            cells.append(dict(cell_type='code',execution_count=n,metadata={},source=[f"query = {query!r}\nwith connect() as conn:\n    for row in conn.execute(query):\n        print(row)\n"],
                outputs=[dict(output_type='stream',name='stdout',text=['\n'.join(map(str,records))+'\n'])]))
    notebook=dict(cells=cells,metadata={'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},nbformat=4,nbformat_minor=5)
    for n,cell in enumerate(cells): cell['id']=f'dq-review-{n}'
    (ROOT/'notebooks/data_quality_review.ipynb').write_text(json.dumps(notebook,indent=2)+'\n',encoding='utf-8')
    print('Exported rule register, CSV summaries and read-only SQL notebook')


if __name__=='__main__': main()
