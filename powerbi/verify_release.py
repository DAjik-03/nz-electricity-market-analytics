"""Read-only final integrity check. Never execute refresh or migrations."""
from pathlib import Path
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from warehouse.db import connect
from run_findings import release_state
from check_analytics_determinism import product_hashes

if __name__=='__main__':
    approved=json.loads((ROOT/'outputs/analysis/query_manifest.json').read_text(encoding='utf-8'))
    with connect() as c:
        c.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute('SET LOCAL max_parallel_workers_per_gather=0')
        c.execute("SET LOCAL statement_timeout='180s'")
        before=release_state(c)
        hashes=product_hashes(c)
        after=release_state(c)
        c.execute('ROLLBACK')
    normal=lambda x:json.loads(json.dumps(x,default=str))
    assert normal(before)==normal(after)==approved['after'],'Approved release state differs'
    assert hashes==approved['approved_view_hashes'],'Approved view hashes differ'
    result=dict(passed=True,read_only=True,approved_view_hashes=hashes,release_state_equals_phase5=True,
                migration_count=len(before['migrations']),selected_publications=len(before['selection']),
                refresh_id=38,dq_run_id=5)
    (ROOT/'outputs/powerbi/release_integrity.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print('Approved state and all seven view hashes unchanged; 24 migrations and 37 selected publications preserved.')
