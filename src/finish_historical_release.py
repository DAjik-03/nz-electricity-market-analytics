"""Explicit post-load stages; stop on failure and retain restartable stage evidence."""
import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from zoneinfo import ZoneInfo
from warehouse.db import ROOT
from ingestion.acquisition import utc_now,write_json


def main():
    names=['candidate','dq','dq_repeat','analytics_repeat','analytics_validation','evidence','tests','dq_export','report']
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-stage',choices=names)
    parser.add_argument('--as-of',default=datetime.now(ZoneInfo('Pacific/Auckland')).date().isoformat())
    args=parser.parse_args()
    out=ROOT/'outputs/scale_up'
    state_path=out/'completion_stages.json'
    if state_path.exists() and args.from_stage is None:
        raise ValueError('Completion attempt exists; inspect it and explicitly choose --from-stage')
    if json.loads((out/'load.json').read_text(encoding='utf-8'))['status'] not in ('loaded_pending_candidate_validation','completed'):
        raise ValueError('Finish warehouse loading before post-load stages')
    steps=[['src/validate_and_promote_historical.py'],
           ['src/run_data_quality.py','run','--as-of',args.as_of],
           ['src/check_data_quality_determinism.py'],
           ['src/check_analytics_determinism.py'],
           ['src/validate_analytics.py'],
           ['src/collect_historical_evidence.py'],
           ['src/run_all_tests.py','--output','outputs/scale_up/final_tests.json'],
           ['src/export_data_quality_review.py'],
           ['src/write_phase4b_report.py']]
    state=json.loads(state_path.read_text(encoding='utf-8')) if state_path.exists() else dict(attempts=[])
    first=names.index(args.from_stage) if args.from_stage else 0
    for name,command in zip(names[first:],steps[first:]):
        item=dict(stage=name,started_at=utc_now(),command=command,status='running')
        state['attempts'].append(item);write_json(state_path,state)
        print('START '+name,flush=True)
        start=time.perf_counter()
        with (out/'completion.log').open('a',encoding='utf-8') as log:
            process=subprocess.Popen([sys.executable,*command],cwd=ROOT,stdout=subprocess.PIPE,
                                     stderr=subprocess.STDOUT,text=True,encoding='utf-8',errors='replace')
            for line in process.stdout:
                print(line,end='',flush=True);log.write(line);log.flush()
            result=process.wait()
        item.update(status='passed' if result==0 else 'failed',exit_code=result,
                    completed_at=utc_now(),seconds=time.perf_counter()-start)
        write_json(state_path,state)
        if result: raise SystemExit(f'Stage {name} failed; inspect actual evidence before resume')
        print('PASS '+name,flush=True)
    print('All technical completion stages passed; finish documentation, Git checks and publication.',flush=True)

if __name__=='__main__': main()
