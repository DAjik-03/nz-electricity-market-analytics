"""Small, source-linked diagnostics for the Phase 1A review (no acquisition)."""
import json
from pathlib import Path
import pandas as pd
from ingestion.acquisition import write_json, verify_version
from ingestion.parsers import parse_nsp, parse_month

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'outputs/pilot/source_manifest.json').read_text())
    selected = {k:manifest['versions'][v] for k,v in manifest['selected'].items()}
    nsp, _ = parse_nsp(verify_version(ROOT, selected['nsp/snapshot']))
    result = {'selected_versions': manifest['selected'], 'generation_history': {}, 'nsp_hwa_history':
        nsp.loc[nsp['POC code'].isin(['HWA1101','HWA1102']), ['NSP','POC code','Network participant','Start date','Start TP','End date','End TP']].astype('string').fillna('').to_dict('records')}
    for month in sorted(k.split('/')[1] for k in selected if k.startswith('generation/')):
        frame, _ = parse_month(verify_version(ROOT, selected['generation/'+month]), 'generation', month)
        unknown = frame.PointOfConnection.isin(['HWA1101','HWA1102']) & frame.Network.eq('KIWI')
        series = frame.groupby(['Gen_Code','PointOfConnection','Network'],observed=True).KilowattHours.agg(['sum','size'])
        result['generation_history'][month] = dict(hwa_kiwi_rows=int(unknown.sum()), hwa_kiwi_kwh=float(frame.loc[unknown,'KilowattHours'].sum()),
            hwa_kiwi_generators=sorted(str(x) for x in frame.loc[unknown,'Gen_Code'].unique()),
            all_zero_series=series.loc[series['sum']==0].reset_index().astype(object).to_dict('records'))
    columns = ['NSP','POC code','Network participant','I flow','X flow','Start date','Start TP','End date','End TP']
    # The largest observed August flag disagreements are retained for manual
    # source-owner clarification, not reclassified using a guessed explanation.
    result['flow_flag_nsp_examples'] = nsp.loc[nsp['POC code'].isin(['TAK0331','BLN0331','BOB1101','RDF0331']),columns].astype('string').fillna('').to_dict('records')
    write_json(ROOT / 'outputs/pilot/investigations.json',result)


if __name__ == '__main__':
    main()
